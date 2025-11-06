"""
MEV Bot Engine - Core orchestration logic
Handles multi-strategy switching, opportunity detection, and execution
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from loguru import logger
from web3 import Web3
from web3.exceptions import TransactionNotFound

from strategies.flashloan_arb import FlashloanArbitrage
from strategies.triangular_arb import TriangularArbitrage
from strategies.liquidation_arb import LiquidationArbitrage
from strategies.sandwich_attack import SandwichAttack

from monitoring.mempool_monitor import MempoolMonitor
from monitoring.price_monitor import PriceMonitor
from monitoring.liquidity_monitor import LiquidityMonitor

from blockchain.contract_manager import ContractManager
from blockchain.transaction_builder import TransactionBuilder
from blockchain.nonce_manager import NonceManager

from ml.price_predictor import PricePredictor
from ml.tip_optimizer import TipOptimizer

from utils.multicall import Multicall
from utils.gas_calculator import GasCalculator
from utils.simulation import TransactionSimulator
from utils.rpc_manager import RPCManager
from utils.alert_system import AlertSystem
from utils.kill_switch import KillSwitch
from utils.data_cache import DataCache

from .strategy_manager import StrategyManager
from .wallet_manager import WalletManager


class MEVBotEngine:
    """
    Main MEV Bot Engine
    Orchestrates all strategies and handles execution flow
    """
    
    def __init__(self, config_path: str = "config/bot_config.json"):
        """Initialize MEV Bot Engine"""
        logger.info("Initializing MEV Bot Engine...")
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        with open("config/dex_config.json", 'r') as f:
            self.dex_config = json.load(f)
        
        with open("config/token_config.json", 'r') as f:
            self.token_config = json.load(f)
        
        # Initialize RPC Manager (Tier 1-4 fallback system)
        self.rpc_manager = RPCManager()
        self.w3 = self.rpc_manager.get_web3()
        
        # Initialize core components
        self.wallet_manager = WalletManager()
        self.contract_manager = ContractManager(self.w3)
        self.nonce_manager = NonceManager(self.w3, self.wallet_manager.executor_address)
        self.tx_builder = TransactionBuilder(self.w3, self.wallet_manager)
        
        # Initialize utilities
        self.multicall = Multicall(self.w3)
        self.gas_calculator = GasCalculator(self.w3, self.config)
        self.simulator = TransactionSimulator(self.w3)
        self.alert_system = AlertSystem()
        self.kill_switch = KillSwitch(self.config, self.alert_system)
        self.cache = DataCache()
        
        # Initialize ML components
        self.price_predictor = PricePredictor(self.config)
        self.tip_optimizer = TipOptimizer(self.config)
        
        # Initialize monitoring
        self.mempool_monitor = MempoolMonitor(self.rpc_manager, self.config)
        self.price_monitor = PriceMonitor(self.config, self.token_config)
        self.liquidity_monitor = LiquidityMonitor(self.w3, self.dex_config)
        
        # Initialize strategies
        self.flashloan_arb = FlashloanArbitrage(
            self.w3,
            self.contract_manager,
            self.config,
            self.dex_config,
            self.token_config
        )
        self.triangular_arb = TriangularArbitrage(
            self.w3,
            self.dex_config,
            self.token_config,
            self.multicall
        )
        self.liquidation_arb = LiquidationArbitrage(
            self.w3,
            self.config,
            self.multicall
        )
        self.sandwich_attack = SandwichAttack(
            self.w3,
            self.mempool_monitor,
            self.config,
            self.dex_config
        )
        
        # Strategy manager for multi-strategy coordination
        self.strategy_manager = StrategyManager(
            self.config,
            [self.flashloan_arb, self.triangular_arb, self.liquidation_arb, self.sandwich_attack]
        )
        
        # Performance tracking
        self.stats = {
            'total_profit_usd': 0.0,
            'total_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'gas_spent_usd': 0.0,
            'start_time': time.time()
        }
        
        # State management
        self.running = False
        self.paused = False
        
        logger.success("MEV Bot Engine initialized successfully")
    
    async def start(self):
        """Start the MEV Bot"""
        logger.info("🚀 Starting MEV Bot Engine...")
        self.running = True
        
        # Start monitoring services
        asyncio.create_task(self.mempool_monitor.start())
        asyncio.create_task(self.price_monitor.start())
        asyncio.create_task(self.liquidity_monitor.start())
        
        # Start main loop
        await self.main_loop()
    
    async def main_loop(self):
        """
        Main bot execution loop
        Implements multi-strategy switching logic
        """
        logger.info("Entering main execution loop...")
        
        while self.running:
            try:
                # Check kill switch
                if self.kill_switch.is_triggered():
                    logger.critical("Kill switch activated! Stopping bot...")
                    await self.emergency_shutdown()
                    break
                
                # Check if paused
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                # MULTI-STRATEGY SWITCHING LOGIC
                # 1. Check sandwich attack opportunities (highest priority)
                sandwich_opp = await self._check_sandwich_opportunities()
                
                # 2. Check liquidation opportunities
                liquidation_opp = await self._check_liquidation_opportunities()
                
                # 3. Check direct arbitrage
                direct_arb_opp = await self._check_direct_arbitrage()
                
                # 4. Check triangular arbitrage
                triangular_opp = await self._check_triangular_arbitrage()
                
                # Select best opportunity
                best_opportunity = self.strategy_manager.select_best_opportunity([
                    sandwich_opp,
                    liquidation_opp,
                    direct_arb_opp,
                    triangular_opp
                ])
                
                if best_opportunity:
                    logger.info(f"🎯 Best opportunity: {best_opportunity['strategy']} - "
                               f"Expected profit: ${best_opportunity['expected_profit_usd']:.2f}")
                    
                    # Execute opportunity
                    success = await self._execute_opportunity(best_opportunity)
                    
                    if success:
                        self.stats['successful_trades'] += 1
                        logger.success("✅ Trade executed successfully!")
                    else:
                        self.stats['failed_trades'] += 1
                        logger.warning("❌ Trade failed")
                    
                    self.stats['total_trades'] += 1
                
                # Small delay to prevent CPU overload
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(1)
    
    async def _check_sandwich_opportunities(self) -> Optional[Dict]:
        """
        Check mempool for sandwich attack opportunities
        Priority: 5 (Highest)
        """
        if not self.config['strategies']['sandwich_attack']['enabled']:
            return None
        
        try:
            # Get pending transactions from mempool
            pending_txs = self.mempool_monitor.get_pending_transactions()
            
            for tx_hash, tx_data in pending_txs.items():
                # Analyze transaction for sandwich potential
                analysis = await self.sandwich_attack.analyze_transaction(tx_data)
                
                if analysis and analysis['is_profitable']:
                    # ML prediction for success probability
                    ml_prediction = await self.price_predictor.predict_sandwich_success(analysis)
                    
                    if ml_prediction['confidence'] >= self.config['ml_optimization']['min_confidence_score']:
                        return {
                            'strategy': 'sandwich_attack',
                            'priority': 5,
                            'expected_profit_usd': analysis['expected_profit_usd'],
                            'confidence': ml_prediction['confidence'],
                            'data': analysis
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking sandwich opportunities: {e}")
            return None
    
    async def _check_liquidation_opportunities(self) -> Optional[Dict]:
        """
        Check for liquidation opportunities in lending protocols
        Priority: 4
        """
        if not self.config['strategies']['liquidation_arbitrage']['enabled']:
            return None
        
        try:
            # Find liquidatable positions
            opportunities = await self.liquidation_arb.find_liquidations()
            
            if opportunities:
                best = max(opportunities, key=lambda x: x['expected_profit_usd'])
                
                # ML prediction
                ml_prediction = await self.price_predictor.predict_profit_probability(
                    best['expected_profit_usd'],
                    'liquidation'
                )
                
                if ml_prediction['confidence'] >= self.config['ml_optimization']['min_confidence_score']:
                    return {
                        'strategy': 'liquidation_arbitrage',
                        'priority': 4,
                        'expected_profit_usd': best['expected_profit_usd'],
                        'confidence': ml_prediction['confidence'],
                        'data': best
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking liquidation opportunities: {e}")
            return None
    
    async def _check_direct_arbitrage(self) -> Optional[Dict]:
        """
        Check for direct arbitrage opportunities (DEX A -> DEX B)
        Priority: 2
        """
        if not self.config['strategies']['direct_arbitrage']['enabled']:
            return None
        
        try:
            # Get token pairs
            pairs = self.token_config['high_volume_pairs']
            
            # Use multicall to batch price queries
            price_calls = []
            for pair in pairs:
                for dex_name, dex_data in self.dex_config['polygon_dexes'].items():
                    if not dex_data.get('enabled'):
                        continue
                    
                    price_calls.append({
                        'dex': dex_name,
                        'pair': pair,
                        'router': dex_data['router']
                    })
            
            # Batch fetch prices (gas-optimized)
            prices = await self._fetch_prices_multicall(price_calls)
            
            # Find arbitrage opportunities
            best_profit = 0
            best_opportunity = None
            
            for pair in pairs:
                # Calculate cross-DEX price difference
                dex_prices = {k: v for k, v in prices.items() if k[1] == tuple(pair)}
                
                if len(dex_prices) < 2:
                    continue
                
                # Find max price difference
                min_dex, min_price = min(dex_prices.items(), key=lambda x: x[1])
                max_dex, max_price = max(dex_prices.items(), key=lambda x: x[1])
                
                if min_price <= 0 or max_price <= 0:
                    continue
                
                # Calculate potential profit
                price_diff_pct = ((max_price - min_price) / min_price) * 100
                
                if price_diff_pct > 0.5:  # At least 0.5% difference
                    # Estimate profit
                    trade_size = self.config['strategies']['direct_arbitrage']['max_trade_size_usd']
                    expected_profit = (trade_size * price_diff_pct / 100)
                    
                    # Subtract gas costs
                    gas_cost = await self.gas_calculator.estimate_arbitrage_gas_cost()
                    net_profit = expected_profit - gas_cost
                    
                    if net_profit > best_profit and net_profit >= self.config['strategies']['direct_arbitrage']['min_profit_usd']:
                        best_profit = net_profit
                        best_opportunity = {
                            'pair': pair,
                            'buy_dex': min_dex[0],
                            'sell_dex': max_dex[0],
                            'buy_price': min_price,
                            'sell_price': max_price,
                            'trade_size_usd': trade_size,
                            'expected_profit_usd': net_profit
                        }
            
            if best_opportunity:
                # ML confidence check
                ml_prediction = await self.price_predictor.predict_profit_probability(
                    best_opportunity['expected_profit_usd'],
                    'direct_arbitrage'
                )
                
                if ml_prediction['confidence'] >= self.config['ml_optimization']['min_confidence_score']:
                    return {
                        'strategy': 'direct_arbitrage',
                        'priority': 2,
                        'expected_profit_usd': best_opportunity['expected_profit_usd'],
                        'confidence': ml_prediction['confidence'],
                        'data': best_opportunity
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking direct arbitrage: {e}")
            return None
    
    async def _check_triangular_arbitrage(self) -> Optional[Dict]:
        """
        Check for triangular arbitrage opportunities (A -> B -> C -> A)
        Priority: 3
        """
        if not self.config['strategies']['triangular_arbitrage']['enabled']:
            return None
        
        try:
            # Find opportunities
            opportunities = await self.triangular_arb.find_opportunities()
            
            if opportunities:
                best = max(opportunities, key=lambda x: x['expected_profit_usd'])
                
                # ML prediction
                ml_prediction = await self.price_predictor.predict_profit_probability(
                    best['expected_profit_usd'],
                    'triangular'
                )
                
                if ml_prediction['confidence'] >= self.config['ml_optimization']['min_confidence_score']:
                    return {
                        'strategy': 'triangular_arbitrage',
                        'priority': 3,
                        'expected_profit_usd': best['expected_profit_usd'],
                        'confidence': ml_prediction['confidence'],
                        'data': best
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking triangular arbitrage: {e}")
            return None
    
    async def _fetch_prices_multicall(self, price_calls: List[Dict]) -> Dict:
        """
        Fetch prices using multicall for gas efficiency
        """
        # This is a simplified version - full implementation in multicall.py
        results = {}
        
        for call in price_calls:
            # Cache check
            cache_key = f"price_{call['dex']}_{call['pair'][0]}_{call['pair'][1]}"
            cached = self.cache.get(cache_key)
            
            if cached:
                results[(call['dex'], tuple(call['pair']))] = cached
            else:
                # Fetch from blockchain (multicall batched)
                price = 1.0  # Placeholder
                results[(call['dex'], tuple(call['pair']))] = price
                self.cache.set(cache_key, price, ttl=30)
        
        return results
    
    async def _execute_opportunity(self, opportunity: Dict) -> bool:
        """
        Execute the selected opportunity
        Returns True if successful
        """
        strategy = opportunity['strategy']
        
        try:
            logger.info(f"Executing {strategy}...")
            
            # Pre-execution checks
            if not await self._pre_execution_checks(opportunity):
                logger.warning("Pre-execution checks failed")
                return False
            
            # JIT gas pricing
            gas_price = await self.gas_calculator.get_jit_gas_price()
            tip = await self.tip_optimizer.calculate_optimal_tip(opportunity)
            
            # Build transaction
            if strategy == 'direct_arbitrage':
                tx = await self._build_direct_arbitrage_tx(opportunity, gas_price, tip)
            elif strategy == 'triangular_arbitrage':
                tx = await self._build_triangular_arbitrage_tx(opportunity, gas_price, tip)
            elif strategy == 'liquidation_arbitrage':
                tx = await self._build_liquidation_tx(opportunity, gas_price, tip)
            elif strategy == 'sandwich_attack':
                tx = await self._build_sandwich_tx(opportunity, gas_price, tip)
            else:
                logger.error(f"Unknown strategy: {strategy}")
                return False
            
            # Simulate transaction
            if not await self.simulator.simulate_transaction(tx):
                logger.warning("Simulation failed - skipping execution")
                return False
            
            # Execute transaction
            tx_hash = await self._send_transaction(tx)
            
            if tx_hash:
                logger.info(f"Transaction sent: {tx_hash.hex()}")
                
                # Wait for confirmation
                receipt = await self._wait_for_confirmation(tx_hash)
                
                if receipt and receipt['status'] == 1:
                    profit = self._calculate_actual_profit(receipt, opportunity)
                    self.stats['total_profit_usd'] += profit
                    
                    logger.success(f"💰 Profit: ${profit:.2f}")
                    return True
                else:
                    logger.error("Transaction reverted")
                    return False
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error executing opportunity: {e}")
            self.kill_switch.record_failed_transaction()
            return False
    
    async def _pre_execution_checks(self, opportunity: Dict) -> bool:
        """
        Pre-execution safety checks
        """
        # Check daily loss limit
        if self.kill_switch.check_daily_loss():
            logger.critical("Daily loss limit reached!")
            return False
        
        # Check RPC health
        if not self.rpc_manager.is_healthy():
            logger.warning("RPC not healthy")
            return False
        
        # Check profit is still valid (price hasn't moved)
        # ... additional checks
        
        return True
    
    async def _build_direct_arbitrage_tx(self, opp: Dict, gas_price: int, tip: int):
        """Build transaction for direct arbitrage"""
        # Implementation in transaction_builder.py
        return await self.tx_builder.build_arbitrage_tx(opp, gas_price, tip)
    
    async def _build_triangular_arbitrage_tx(self, opp: Dict, gas_price: int, tip: int):
        """Build transaction for triangular arbitrage"""
        return await self.tx_builder.build_triangular_tx(opp, gas_price, tip)
    
    async def _build_liquidation_tx(self, opp: Dict, gas_price: int, tip: int):
        """Build transaction for liquidation"""
        return await self.tx_builder.build_liquidation_tx(opp, gas_price, tip)
    
    async def _build_sandwich_tx(self, opp: Dict, gas_price: int, tip: int):
        """Build transaction for sandwich attack"""
        return await self.tx_builder.build_sandwich_tx(opp, gas_price, tip)
    
    async def _send_transaction(self, tx: Dict) -> Optional[bytes]:
        """Send transaction to network"""
        try:
            # Get nonce
            nonce = self.nonce_manager.get_nonce()
            tx['nonce'] = nonce
            
            # Sign transaction
            signed_tx = self.wallet_manager.sign_transaction(tx)
            
            # Send via MEV relay if enabled
            if self.config['mev_boost']['enabled']:
                # TODO: Implement MEV-Boost bundle submission
                pass
            else:
                # Send to public mempool
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                return tx_hash
                
        except Exception as e:
            logger.error(f"Error sending transaction: {e}")
            return None
    
    async def _wait_for_confirmation(self, tx_hash: bytes, timeout: int = 60):
        """Wait for transaction confirmation"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                return receipt
            except TransactionNotFound:
                await asyncio.sleep(2)
        
        return None
    
    def _calculate_actual_profit(self, receipt, opportunity) -> float:
        """Calculate actual profit from transaction receipt"""
        # Parse logs and calculate profit
        # Subtract gas costs
        gas_used = receipt['gasUsed']
        gas_price = receipt['effectiveGasPrice']
        gas_cost_wei = gas_used * gas_price
        gas_cost_usd = self.w3.from_wei(gas_cost_wei, 'ether') * 2000  # Approximate MATIC price
        
        profit = opportunity['expected_profit_usd'] - gas_cost_usd
        return profit
    
    async def emergency_shutdown(self):
        """Emergency shutdown procedure"""
        logger.critical("🚨 EMERGENCY SHUTDOWN INITIATED")
        
        self.running = False
        self.paused = True
        
        # Stop all monitoring
        await self.mempool_monitor.stop()
        await self.price_monitor.stop()
        await self.liquidity_monitor.stop()
        
        # Withdraw all profits to admin wallet
        await self.wallet_manager.auto_withdraw_profits()
        
        # Send critical alert
        await self.alert_system.send_critical_alert(
            "MEV Bot Emergency Shutdown",
            f"Bot stopped. Stats: {self.stats}"
        )
        
        logger.critical("Shutdown complete")
    
    def get_stats(self) -> Dict:
        """Get bot statistics"""
        return {
            **self.stats,
            'uptime_hours': (time.time() - self.stats['start_time']) / 3600,
            'success_rate': (self.stats['successful_trades'] / max(self.stats['total_trades'], 1)) * 100
        }