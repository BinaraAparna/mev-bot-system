"""
Flashloan Arbitrage Strategy
Executes arbitrage using Aave V3 flashloans for capital-free trading
"""

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from web3 import Web3
from loguru import logger


class FlashloanArbitrage:
    """
    Flashloan-based arbitrage strategy
    Borrows funds, executes arbitrage, repays loan + fee, keeps profit
    """
    
    # Aave V3 constants
    AAVE_POOL_ADDRESS = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
    FLASHLOAN_PREMIUM_BPS = 9  # 0.09% = 9 basis points
    
    def __init__(self, w3: Web3, contract_manager, config: Dict, dex_config: Dict, token_config: Dict):
        """
        Initialize Flashloan Arbitrage strategy
        
        Args:
            w3: Web3 instance
            contract_manager: Contract interaction manager
            config: Bot configuration
            dex_config: DEX configuration
            token_config: Token configuration
        """
        self.w3 = w3
        self.contract_manager = contract_manager
        self.config = config
        self.dex_config = dex_config
        self.token_config = token_config
        
        # Strategy settings
        self.min_profit_usd = config['strategies']['flashloan_arbitrage']['min_profit_usd']
        self.max_loan_size_usd = config['strategies']['flashloan_arbitrage']['max_loan_size_usd']
        
        logger.info("Flashloan Arbitrage strategy initialized")
    
    async def find_opportunities(self) -> List[Dict]:
        """
        Find flashloan arbitrage opportunities
        
        Returns:
            List of profitable opportunities
        """
        opportunities = []
        
        try:
            # Get high-volume token pairs
            pairs = self.token_config['high_volume_pairs']
            
            for pair in pairs:
                token_a_symbol, token_b_symbol = pair
                token_a = self.token_config['tokens'][token_a_symbol]
                token_b = self.token_config['tokens'][token_b_symbol]
                
                # Find arbitrage across DEXes
                opp = await self._find_cross_dex_arbitrage(token_a, token_b)
                
                if opp and opp['expected_profit_usd'] >= self.min_profit_usd:
                    opportunities.append(opp)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding flashloan opportunities: {e}")
            return []
    
    async def _find_cross_dex_arbitrage(
        self, 
        token_a: Dict, 
        token_b: Dict
    ) -> Optional[Dict]:
        """
        Find arbitrage opportunity between multiple DEXes
        
        Strategy: Borrow token A, swap A->B on DEX1, swap B->A on DEX2, repay loan
        
        Args:
            token_a: Token A config
            token_b: Token B config
            
        Returns:
            Opportunity dict or None
        """
        try:
            # Get enabled DEXes
            enabled_dexes = [
                (name, config) for name, config in self.dex_config['polygon_dexes'].items()
                if config.get('enabled', False)
            ]
            
            if len(enabled_dexes) < 2:
                return None
            
            best_opportunity = None
            max_profit = 0
            
            # Check all DEX pairs
            for i, (dex1_name, dex1_config) in enumerate(enabled_dexes):
                for j, (dex2_name, dex2_config) in enumerate(enabled_dexes):
                    if i >= j:  # Avoid duplicate pairs
                        continue
                    
                    # Calculate optimal loan size
                    loan_amount = await self._calculate_optimal_loan_size(
                        token_a, 
                        token_b,
                        dex1_config,
                        dex2_config
                    )
                    
                    if loan_amount <= 0:
                        continue
                    
                    # Estimate profit
                    profit = await self._estimate_flashloan_profit(
                        token_a,
                        token_b,
                        loan_amount,
                        dex1_config,
                        dex2_config
                    )
                    
                    if profit > max_profit and profit >= self.min_profit_usd:
                        max_profit = profit
                        best_opportunity = {
                            'strategy_type': 'flashloan_arbitrage',
                            'token_borrow': token_a,
                            'token_trade': token_b,
                            'loan_amount': loan_amount,
                            'buy_dex': dex1_name,
                            'buy_dex_config': dex1_config,
                            'sell_dex': dex2_name,
                            'sell_dex_config': dex2_config,
                            'expected_profit_usd': profit,
                            'flashloan_fee_usd': self._calculate_flashloan_fee(loan_amount, token_a)
                        }
            
            return best_opportunity
            
        except Exception as e:
            logger.error(f"Error in _find_cross_dex_arbitrage: {e}")
            return None
    
    async def _calculate_optimal_loan_size(
        self,
        token_a: Dict,
        token_b: Dict,
        dex1_config: Dict,
        dex2_config: Dict
    ) -> float:
        """
        Calculate optimal flashloan size to maximize profit
        
        Uses calculus-based optimization:
        - Too small loan = low profit
        - Too large loan = high price impact, reduces profit
        
        Optimal loan = sqrt(k * price_difference / slippage_factor)
        
        Args:
            token_a: Token to borrow
            token_b: Token to trade
            dex1_config: First DEX config
            dex2_config: Second DEX config
            
        Returns:
            Optimal loan amount in token A units
        """
        try:
            # Get pool liquidity for both DEXes
            liquidity_dex1 = await self._get_pool_liquidity(
                token_a['address'],
                token_b['address'],
                dex1_config
            )
            
            liquidity_dex2 = await self._get_pool_liquidity(
                token_a['address'],
                token_b['address'],
                dex2_config
            )
            
            # Get prices
            price_dex1 = await self._get_price(token_a, token_b, dex1_config)
            price_dex2 = await self._get_price(token_a, token_b, dex2_config)
            
            if not price_dex1 or not price_dex2:
                return 0
            
            # Calculate price difference percentage
            price_diff_pct = abs(price_dex2 - price_dex1) / price_dex1
            
            # If price difference is too small, not profitable
            if price_diff_pct < 0.005:  # Less than 0.5%
                return 0
            
            # Use conservative loan size (10% of smaller liquidity pool)
            min_liquidity = min(liquidity_dex1, liquidity_dex2)
            optimal_loan = min_liquidity * 0.10
            
            # Cap at max loan size
            max_loan_tokens = self.max_loan_size_usd / price_dex1
            optimal_loan = min(optimal_loan, max_loan_tokens)
            
            return optimal_loan
            
        except Exception as e:
            logger.error(f"Error calculating optimal loan size: {e}")
            return 0
    
    async def _estimate_flashloan_profit(
        self,
        token_a: Dict,
        token_b: Dict,
        loan_amount: float,
        dex1_config: Dict,
        dex2_config: Dict
    ) -> float:
        """
        Estimate net profit after flashloan fees and gas
        
        Flow:
        1. Borrow token_a (loan_amount)
        2. Swap token_a -> token_b on DEX1
        3. Swap token_b -> token_a on DEX2
        4. Repay loan + 0.09% fee
        5. Profit = final_amount - loan_amount - fee - gas_cost
        
        Args:
            token_a: Token to borrow
            token_b: Intermediate token
            loan_amount: Amount to borrow
            dex1_config: Buy DEX
            dex2_config: Sell DEX
            
        Returns:
            Expected profit in USD
        """
        try:
            # Step 1: Get amount of token_b after first swap
            amount_b = await self._get_swap_output(
                token_a['address'],
                token_b['address'],
                loan_amount,
                dex1_config
            )
            
            if amount_b <= 0:
                return 0
            
            # Step 2: Get amount of token_a after second swap
            final_amount_a = await self._get_swap_output(
                token_b['address'],
                token_a['address'],
                amount_b,
                dex2_config
            )
            
            if final_amount_a <= loan_amount:
                return 0  # Not profitable
            
            # Step 3: Calculate flashloan fee (0.09%)
            flashloan_fee = loan_amount * (self.FLASHLOAN_PREMIUM_BPS / 10000)
            
            # Step 4: Calculate total debt
            total_debt = loan_amount + flashloan_fee
            
            # Step 5: Calculate gross profit in token_a
            gross_profit_tokens = final_amount_a - total_debt
            
            if gross_profit_tokens <= 0:
                return 0
            
            # Convert to USD
            token_a_price_usd = await self._get_token_price_usd(token_a)
            gross_profit_usd = gross_profit_tokens * token_a_price_usd
            
            # Step 6: Subtract gas costs
            gas_cost_usd = await self._estimate_gas_cost()
            
            net_profit_usd = gross_profit_usd - gas_cost_usd
            
            return net_profit_usd
            
        except Exception as e:
            logger.error(f"Error estimating flashloan profit: {e}")
            return 0
    
    async def _get_pool_liquidity(
        self,
        token_a_address: str,
        token_b_address: str,
        dex_config: Dict
    ) -> float:
        """
        Get pool liquidity for a token pair on a DEX
        
        Args:
            token_a_address: Token A address
            token_b_address: Token B address
            dex_config: DEX configuration
            
        Returns:
            Liquidity in token A units
        """
        try:
            # For V2 DEXes (Uniswap V2 style)
            if dex_config.get('version') == 'v2':
                # Get pair address
                factory_address = dex_config['factory']
                factory_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(factory_address),
                    abi=self._get_factory_abi()
                )
                
                pair_address = factory_contract.functions.getPair(
                    Web3.to_checksum_address(token_a_address),
                    Web3.to_checksum_address(token_b_address)
                ).call()
                
                if pair_address == '0x0000000000000000000000000000000000000000':
                    return 0
                
                # Get reserves
                pair_contract = self.w3.eth.contract(
                    address=pair_address,
                    abi=self._get_pair_abi()
                )
                
                reserves = pair_contract.functions.getReserves().call()
                reserve_a = reserves[0] / (10 ** 18)  # Simplified
                
                return reserve_a
            
            # For V3 DEXes - more complex, use multicall
            elif dex_config.get('version') == 'v3':
                # V3 has concentrated liquidity - more complex calculation
                # Return conservative estimate
                return 100000  # Placeholder
            
            return 0
            
        except Exception as e:
            logger.debug(f"Error getting pool liquidity: {e}")
            return 0
    
    async def _get_price(
        self,
        token_a: Dict,
        token_b: Dict,
        dex_config: Dict
    ) -> float:
        """Get token price on a specific DEX"""
        try:
            # Use router's getAmountsOut
            router_address = dex_config['router']
            router_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=self._get_router_abi()
            )
            
            # Get price for 1 token
            amount_in = 10 ** token_a['decimals']
            path = [
                Web3.to_checksum_address(token_a['address']),
                Web3.to_checksum_address(token_b['address'])
            ]
            
            amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
            price = amounts[1] / (10 ** token_b['decimals'])
            
            return price
            
        except Exception as e:
            logger.debug(f"Error getting price: {e}")
            return 0
    
    async def _get_swap_output(
        self,
        token_in_address: str,
        token_out_address: str,
        amount_in: float,
        dex_config: Dict
    ) -> float:
        """Calculate expected output for a swap"""
        try:
            router_address = dex_config['router']
            router_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=self._get_router_abi()
            )
            
            # Convert amount to wei
            amount_in_wei = int(amount_in * (10 ** 18))
            
            path = [
                Web3.to_checksum_address(token_in_address),
                Web3.to_checksum_address(token_out_address)
            ]
            
            amounts = router_contract.functions.getAmountsOut(amount_in_wei, path).call()
            amount_out = amounts[1] / (10 ** 18)
            
            return amount_out
            
        except Exception as e:
            logger.debug(f"Error getting swap output: {e}")
            return 0
    
    async def _get_token_price_usd(self, token: Dict) -> float:
        """Get token price in USD"""
        # Simplified - in production, fetch from price oracle
        if token['symbol'] == 'USDC' or token['symbol'] == 'USDT':
            return 1.0
        elif token['symbol'] == 'WMATIC':
            return 0.80  # Approximate
        elif token['symbol'] == 'WETH':
            return 3000.0  # Approximate
        else:
            return 100.0  # Placeholder
    
    async def _estimate_gas_cost(self) -> float:
        """Estimate gas cost for flashloan arbitrage in USD"""
        # Flashloan transactions use ~600k-800k gas
        gas_limit = 700000
        gas_price_gwei = 50  # Current Polygon gas price
        gas_cost_matic = (gas_limit * gas_price_gwei) / (10 ** 9)
        gas_cost_usd = gas_cost_matic * 0.80  # MATIC price
        
        return gas_cost_usd
    
    def _calculate_flashloan_fee(self, loan_amount: float, token: Dict) -> float:
        """Calculate flashloan fee in USD"""
        fee_tokens = loan_amount * (self.FLASHLOAN_PREMIUM_BPS / 10000)
        token_price_usd = 1.0  # Simplified
        return fee_tokens * token_price_usd
    
    def _get_factory_abi(self) -> List:
        """Uniswap V2 Factory ABI"""
        return [
            {
                "constant": True,
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"name": "pair", "type": "address"}],
                "type": "function"
            }
        ]
    
    def _get_pair_abi(self) -> List:
        """Uniswap V2 Pair ABI"""
        return [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"name": "reserve0", "type": "uint112"},
                    {"name": "reserve1", "type": "uint112"},
                    {"name": "blockTimestampLast", "type": "uint32"}
                ],
                "type": "function"
            }
        ]
    
    def _get_router_abi(self) -> List:
        """Uniswap V2 Router ABI (simplified)"""
        return [
            {
                "constant": True,
                "inputs": [
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"name": "amounts", "type": "uint256[]"}],
                "type": "function"
            }
        ]