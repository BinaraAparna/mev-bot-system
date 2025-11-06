"""
Liquidation Arbitrage Strategy
Monitors lending protocols (Aave, Compound) for undercollateralized positions
"""

from typing import Dict, List, Optional
from decimal import Decimal
from web3 import Web3
from loguru import logger


class LiquidationArbitrage:
    """
    Liquidation arbitrage strategy
    Finds and liquidates undercollateralized loans in DeFi protocols
    """
    
    # Aave V3 Polygon addresses
    AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
    AAVE_DATA_PROVIDER = "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654"
    
    # Liquidation incentive (typically 5-10% bonus)
    LIQUIDATION_BONUS_PCT = 5.0
    
    def __init__(self, w3: Web3, config: Dict, multicall):
        """
        Initialize Liquidation Arbitrage strategy
        
        Args:
            w3: Web3 instance
            config: Bot configuration
            multicall: Multicall utility
        """
        self.w3 = w3
        self.config = config
        self.multicall = multicall
        
        # Strategy settings
        self.min_profit_usd = config['strategies']['liquidation_arbitrage']['min_profit_usd']
        self.health_factor_threshold = config['strategies']['liquidation_arbitrage']['health_factor_threshold']
        
        # Initialize Aave contracts
        self._init_aave_contracts()
        
        logger.info("Liquidation Arbitrage strategy initialized")
    
    def _init_aave_contracts(self):
        """Initialize Aave V3 contract instances"""
        # Aave Pool ABI (simplified)
        pool_abi = [
            {
                "inputs": [
                    {"name": "user", "type": "address"}
                ],
                "name": "getUserAccountData",
                "outputs": [
                    {"name": "totalCollateralBase", "type": "uint256"},
                    {"name": "totalDebtBase", "type": "uint256"},
                    {"name": "availableBorrowsBase", "type": "uint256"},
                    {"name": "currentLiquidationThreshold", "type": "uint256"},
                    {"name": "ltv", "type": "uint256"},
                    {"name": "healthFactor", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "collateralAsset", "type": "address"},
                    {"name": "debtAsset", "type": "address"},
                    {"name": "user", "type": "address"},
                    {"name": "debtToCover", "type": "uint256"},
                    {"name": "receiveAToken", "type": "bool"}
                ],
                "name": "liquidationCall",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        self.aave_pool_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.AAVE_POOL),
            abi=pool_abi
        )
        
        # Data Provider ABI (simplified)
        data_provider_abi = [
            {
                "inputs": [
                    {"name": "user", "type": "address"}
                ],
                "name": "getUserReservesData",
                "outputs": [
                    {"name": "reserves", "type": "address[]"},
                    {"name": "currentATokenBalance", "type": "uint256[]"},
                    {"name": "currentStableDebt", "type": "uint256[]"},
                    {"name": "currentVariableDebt", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.aave_data_provider = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.AAVE_DATA_PROVIDER),
            abi=data_provider_abi
        )
    
    async def find_liquidations(self) -> List[Dict]:
        """
        Find liquidatable positions
        
        Process:
        1. Monitor recent borrowers
        2. Check health factors
        3. Find positions with HF < 1.0
        4. Calculate liquidation profit
        
        Returns:
            List of liquidation opportunities
        """
        opportunities = []
        
        try:
            # Get list of users to check
            # In production, this would be from indexed events or subgraph
            users_to_check = await self._get_users_to_monitor()
            
            # Batch check health factors using multicall
            health_checks = []
            for user_address in users_to_check:
                health_checks.append({
                    'user': user_address,
                    'contract': self.aave_pool_contract,
                    'function': 'getUserAccountData',
                    'args': [user_address]
                })
            
            # Execute multicall
            results = await self._multicall_health_checks(health_checks)
            
            # Find undercollateralized positions
            for user_address, account_data in results.items():
                if self._is_liquidatable(account_data):
                    opp = await self._analyze_liquidation_opportunity(
                        user_address,
                        account_data
                    )
                    
                    if opp and opp['expected_profit_usd'] >= self.min_profit_usd:
                        opportunities.append(opp)
            
            # Sort by profit
            opportunities.sort(key=lambda x: x['expected_profit_usd'], reverse=True)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding liquidations: {e}")
            return []
    
    async def _get_users_to_monitor(self) -> List[str]:
        """
        Get list of user addresses to monitor
        
        In production:
        - Use The Graph to query recent borrow events
        - Subscribe to Aave event logs
        - Maintain database of active borrowers
        
        For now: Return sample addresses
        """
        # This is a simplified version
        # In production, query from blockchain events or subgraph
        
        sample_users = [
            # These would be real addresses from event logs
            "0x1234567890123456789012345678901234567890",
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        ]
        
        return sample_users
    
    async def _multicall_health_checks(self, health_checks: List[Dict]) -> Dict:
        """
        Batch check health factors using multicall
        
        Args:
            health_checks: List of check configs
            
        Returns:
            Dict mapping user addresses to account data
        """
        results = {}
        
        try:
            # Use multicall to batch requests
            calls = []
            for check in health_checks:
                calls.append({
                    'target': check['contract'].address,
                    'call_data': check['contract'].encodeABI(
                        fn_name=check['function'],
                        args=check['args']
                    )
                })
            
            # Execute multicall
            multicall_results = await self.multicall.aggregate(calls)
            
            # Decode results
            for i, check in enumerate(health_checks):
                try:
                    decoded = check['contract'].decode_function_result(
                        check['function'],
                        multicall_results[i]
                    )
                    
                    results[check['user']] = {
                        'total_collateral_base': decoded[0],
                        'total_debt_base': decoded[1],
                        'available_borrows_base': decoded[2],
                        'liquidation_threshold': decoded[3],
                        'ltv': decoded[4],
                        'health_factor': decoded[5]
                    }
                except Exception as e:
                    logger.debug(f"Error decoding health check for {check['user']}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in multicall health checks: {e}")
            return {}
    
    def _is_liquidatable(self, account_data: Dict) -> bool:
        """
        Check if a position is liquidatable
        
        Liquidatable if health_factor < 1.0 (< 1e18 in wei)
        
        Args:
            account_data: Account data from Aave
            
        Returns:
            True if liquidatable
        """
        health_factor = account_data.get('health_factor', 0)
        
        # Health factor is in 1e18 format
        # HF < 1.0 means liquidatable
        # HF < 1.05 means close to liquidation (we monitor these)
        
        threshold_wei = int(self.health_factor_threshold * 1e18)
        
        return health_factor < threshold_wei
    
    async def _analyze_liquidation_opportunity(
        self,
        user_address: str,
        account_data: Dict
    ) -> Optional[Dict]:
        """
        Analyze a liquidation opportunity and calculate profit
        
        Args:
            user_address: Address of the borrower
            account_data: Account data from Aave
            
        Returns:
            Opportunity dict or None
        """
        try:
            # Get user's reserve data (what they borrowed/collateral)
            user_reserves = await self._get_user_reserves(user_address)
            
            if not user_reserves:
                return None
            
            # Find best collateral to seize
            best_collateral = self._select_best_collateral(user_reserves)
            
            # Find debt to repay
            debt_to_repay = self._select_debt_to_repay(user_reserves)
            
            if not best_collateral or not debt_to_repay:
                return None
            
            # Calculate liquidation amount (max 50% of debt)
            max_debt_to_cover = debt_to_repay['amount'] * 0.5
            
            # Calculate collateral to receive (with bonus)
            collateral_to_receive = max_debt_to_cover * (1 + self.LIQUIDATION_BONUS_PCT / 100)
            
            # Calculate profit
            # Profit = (collateral_value - debt_repaid) in USD
            collateral_value_usd = collateral_to_receive * best_collateral['price_usd']
            debt_value_usd = max_debt_to_cover * debt_to_repay['price_usd']
            
            gross_profit_usd = collateral_value_usd - debt_value_usd
            
            # Subtract gas costs
            gas_cost_usd = await self._estimate_gas_cost()
            
            net_profit_usd = gross_profit_usd - gas_cost_usd
            
            if net_profit_usd <= 0:
                return None
            
            return {
                'strategy_type': 'liquidation_arbitrage',
                'user_address': user_address,
                'health_factor': account_data['health_factor'] / 1e18,
                'collateral_asset': best_collateral['address'],
                'collateral_symbol': best_collateral['symbol'],
                'debt_asset': debt_to_repay['address'],
                'debt_symbol': debt_to_repay['symbol'],
                'debt_to_cover': max_debt_to_cover,
                'collateral_to_receive': collateral_to_receive,
                'liquidation_bonus_pct': self.LIQUIDATION_BONUS_PCT,
                'gross_profit_usd': gross_profit_usd,
                'gas_cost_usd': gas_cost_usd,
                'expected_profit_usd': net_profit_usd
            }
            
        except Exception as e:
            logger.error(f"Error analyzing liquidation opportunity: {e}")
            return None
    
    async def _get_user_reserves(self, user_address: str) -> Optional[Dict]:
        """
        Get user's reserve data (collateral and debt)
        
        Args:
            user_address: User address
            
        Returns:
            Dict with user's positions
        """
        try:
            # This is simplified
            # In production, parse the full reserve data from data provider
            
            return {
                'collateral': [
                    {
                        'address': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
                        'symbol': 'USDC',
                        'amount': 10000,
                        'price_usd': 1.0
                    }
                ],
                'debt': [
                    {
                        'address': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
                        'symbol': 'WETH',
                        'amount': 2.5,
                        'price_usd': 3000.0
                    }
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting user reserves: {e}")
            return None
    
    def _select_best_collateral(self, user_reserves: Dict) -> Optional[Dict]:
        """Select most liquid collateral to seize"""
        collateral_list = user_reserves.get('collateral', [])
        
        if not collateral_list:
            return None
        
        # Prefer stablecoins or high-liquidity tokens
        priority_order = ['USDC', 'USDT', 'DAI', 'WETH', 'WBTC', 'WMATIC']
        
        for symbol in priority_order:
            for collateral in collateral_list:
                if collateral['symbol'] == symbol:
                    return collateral
        
        # Default to first collateral
        return collateral_list[0]
    
    def _select_debt_to_repay(self, user_reserves: Dict) -> Optional[Dict]:
        """Select debt to repay"""
        debt_list = user_reserves.get('debt', [])
        
        if not debt_list:
            return None
        
        # Repay largest debt
        return max(debt_list, key=lambda x: x['amount'] * x['price_usd'])
    
    async def _estimate_gas_cost(self) -> float:
        """Estimate gas cost for liquidation"""
        # Liquidation call uses ~300k-400k gas
        gas_limit = 350000
        gas_price_gwei = 50
        gas_cost_matic = (gas_limit * gas_price_gwei) / (10 ** 9)
        gas_cost_usd = gas_cost_matic * 0.80
        
        return gas_cost_usd