"""
Gas Calculator
JIT (Just-In-Time) gas pricing for optimal transaction execution
"""

import time
from typing import Dict, Optional
from collections import deque
from web3 import Web3
from loguru import logger


class GasCalculator:
    """
    Calculates optimal gas prices using JIT strategy
    Tracks historical gas prices for ML-based prediction
    """
    
    def __init__(self, w3: Web3, config: Dict):
        """
        Initialize Gas Calculator
        
        Args:
            w3: Web3 instance
            config: Bot configuration
        """
        self.w3 = w3
        self.config = config
        
        # Gas settings
        self.max_gas_price_gwei = config['gas_settings']['max_gas_price_gwei']
        self.priority_fee_gwei = config['gas_settings']['priority_fee_gwei']
        
        # Historical gas prices
        self.gas_history = deque(maxlen=100)
        
        # MATIC price cache
        self.matic_price_usd = 0.80  # Approximate
        
        logger.info("Gas Calculator initialized")
    
    async def get_jit_gas_price(self) -> int:
        """
        Get Just-In-Time gas price
        Fetches current network gas price at the moment of sending
        
        Returns:
            Gas price in wei
        """
        try:
            # Get current gas price from network
            gas_price_wei = self.w3.eth.gas_price
            gas_price_gwei = self.w3.from_wei(gas_price_wei, 'gwei')
            
            # Apply buffer (5% increase for faster inclusion)
            buffered_price_gwei = gas_price_gwei * 1.05
            
            # Cap at max
            final_price_gwei = min(buffered_price_gwei, self.max_gas_price_gwei)
            
            # Convert back to wei
            final_price_wei = self.w3.to_wei(final_price_gwei, 'gwei')
            
            # Record in history
            self.gas_history.append({
                'timestamp': time.time(),
                'gas_price_gwei': final_price_gwei
            })
            
            logger.debug(f"JIT gas price: {final_price_gwei:.2f} gwei")
            
            return int(final_price_wei)
            
        except Exception as e:
            logger.error(f"Error getting JIT gas price: {e}")
            # Return safe default
            return self.w3.to_wei(50, 'gwei')
    
    async def get_eip1559_gas_params(self) -> Dict[str, int]:
        """
        Get EIP-1559 gas parameters (maxFeePerGas, maxPriorityFeePerGas)
        
        Returns:
            Dict with gas parameters in wei
        """
        try:
            # Get base fee from latest block
            latest_block = self.w3.eth.get_block('latest')
            base_fee_wei = latest_block.get('baseFeePerGas', 0)
            
            # Priority fee (tip)
            priority_fee_wei = self.w3.to_wei(self.priority_fee_gwei, 'gwei')
            
            # Max fee = base fee * 2 + priority fee (buffer for fluctuations)
            max_fee_wei = (base_fee_wei * 2) + priority_fee_wei
            
            # Cap at max
            max_allowed_wei = self.w3.to_wei(self.max_gas_price_gwei, 'gwei')
            max_fee_wei = min(max_fee_wei, max_allowed_wei)
            
            return {
                'maxFeePerGas': int(max_fee_wei),
                'maxPriorityFeePerGas': int(priority_fee_wei)
            }
            
        except Exception as e:
            logger.error(f"Error getting EIP-1559 params: {e}")
            return {
                'maxFeePerGas': self.w3.to_wei(100, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(35, 'gwei')
            }
    
    async def estimate_arbitrage_gas_cost(self) -> float:
        """
        Estimate gas cost for arbitrage transaction in USD
        
        Returns:
            Gas cost in USD
        """
        try:
            # Arbitrage typically uses 500k gas
            gas_limit = self.config['gas_settings']['gas_limit_arbitrage']
            
            # Get current gas price
            gas_price_wei = await self.get_jit_gas_price()
            
            # Calculate cost in MATIC
            gas_cost_matic = self.w3.from_wei(gas_price_wei * gas_limit, 'ether')
            
            # Convert to USD
            gas_cost_usd = float(gas_cost_matic) * self.matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating gas cost: {e}")
            return 2.0  # Safe estimate
    
    async def estimate_flashloan_gas_cost(self) -> float:
        """Estimate gas cost for flashloan transaction"""
        try:
            gas_limit = self.config['gas_settings']['gas_limit_flashloan']
            gas_price_wei = await self.get_jit_gas_price()
            
            gas_cost_matic = self.w3.from_wei(gas_price_wei * gas_limit, 'ether')
            gas_cost_usd = float(gas_cost_matic) * self.matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating flashloan gas: {e}")
            return 3.0
    
    async def estimate_sandwich_gas_cost(self) -> float:
        """Estimate gas cost for sandwich attack (2 transactions)"""
        try:
            gas_limit = self.config['gas_settings']['gas_limit_sandwich']
            gas_price_wei = await self.get_jit_gas_price()
            
            # 2 transactions (front-run + back-run)
            total_gas = gas_limit * 2
            
            gas_cost_matic = self.w3.from_wei(gas_price_wei * total_gas, 'ether')
            gas_cost_usd = float(gas_cost_matic) * self.matic_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating sandwich gas: {e}")
            return 2.5
    
    def get_average_gas_price(self, window_minutes: int = 5) -> float:
        """
        Get average gas price over time window
        
        Args:
            window_minutes: Time window in minutes
            
        Returns:
            Average gas price in gwei
        """
        if not self.gas_history:
            return 50.0  # Default
        
        cutoff_time = time.time() - (window_minutes * 60)
        
        recent_prices = [
            entry['gas_price_gwei']
            for entry in self.gas_history
            if entry['timestamp'] >= cutoff_time
        ]
        
        if not recent_prices:
            return 50.0
        
        return sum(recent_prices) / len(recent_prices)
    
    def get_gas_trend(self) -> str:
        """
        Determine gas price trend
        
        Returns:
            'rising', 'falling', or 'stable'
        """
        if len(self.gas_history) < 10:
            return 'stable'
        
        recent_avg = self.get_average_gas_price(window_minutes=2)
        older_avg = self.get_average_gas_price(window_minutes=10)
        
        diff_pct = ((recent_avg - older_avg) / older_avg) * 100
        
        if diff_pct > 10:
            return 'rising'
        elif diff_pct < -10:
            return 'falling'
        else:
            return 'stable'
    
    def update_matic_price(self, price_usd: float):
        """Update MATIC price for accurate USD calculations"""
        self.matic_price_usd = price_usd
        logger.debug(f"MATIC price updated: ${price_usd:.4f}")
    
    def should_execute_now(self, expected_profit_usd: float) -> bool:
        """
        Determine if transaction should execute now based on gas
        
        Args:
            expected_profit_usd: Expected profit
            
        Returns:
            True if should execute
        """
        trend = self.get_gas_trend()
        current_avg = self.get_average_gas_price()
        
        # If gas is rising and profit is small, wait
        if trend == 'rising' and expected_profit_usd < 20:
            logger.info("Gas rising, profit small - waiting")
            return False
        
        # If gas is very high, only execute if profit is substantial
        if current_avg > 100 and expected_profit_usd < 50:
            logger.info("Gas very high - need higher profit")
            return False
        
        return True