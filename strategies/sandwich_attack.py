"""
Sandwich Attack Strategy
Front-runs and back-runs large transactions to profit from price impact
"""

from typing import Dict, List, Optional
from decimal import Decimal
from web3 import Web3
from eth_abi import decode
from loguru import logger


class SandwichAttack:
    """
    Sandwich attack strategy
    
    Process:
    1. Monitor mempool for large swaps
    2. Front-run: Buy token before victim
    3. Victim swap executes (pushes price up)
    4. Back-run: Sell token after victim (at higher price)
    """
    
    # Uniswap V2 Router function signatures
    SWAP_EXACT_TOKENS_FOR_TOKENS = "0x38ed1739"
    SWAP_TOKENS_FOR_EXACT_TOKENS = "0x8803dbee"
    SWAP_EXACT_ETH_FOR_TOKENS = "0x7ff36ab5"
    SWAP_TOKENS_FOR_EXACT_ETH = "0x4a25d94a"
    
    def __init__(self, w3: Web3, mempool_monitor, config: Dict, dex_config: Dict):
        """
        Initialize Sandwich Attack strategy
        
        Args:
            w3: Web3 instance
            mempool_monitor: Mempool monitoring service
            config: Bot configuration
            dex_config: DEX configuration
        """
        self.w3 = w3
        self.mempool_monitor = mempool_monitor
        self.config = config
        self.dex_config = dex_config
        
        # Strategy settings
        self.min_victim_size_usd = config['strategies']['sandwich_attack']['min_victim_size_usd']
        self.min_profit_usd = config['strategies']['sandwich_attack']['min_profit_usd']
        
        logger.info("Sandwich Attack strategy initialized")
    
    async def analyze_transaction(self, tx_data: Dict) -> Optional[Dict]:
        """
        Analyze a pending transaction for sandwich potential
        
        Args:
            tx_data: Transaction data from mempool
            
        Returns:
            Analysis dict if profitable, None otherwise
        """
        try:
            # Check if transaction is a swap
            if not self._is_swap_transaction(tx_data):
                return None
            
            # Decode swap parameters
            swap_params = self._decode_swap_transaction(tx_data)
            
            if not swap_params:
                return None
            
            # Check if swap size is large enough
            if swap_params['value_usd'] < self.min_victim_size_usd:
                return None
            
            # Calculate potential profit
            profit_analysis = await self._calculate_sandwich_profit(
                swap_params,
                tx_data
            )
            
            if not profit_analysis:
                return None
            
            # Check if profitable after gas
            if profit_analysis['net_profit_usd'] < self.min_profit_usd:
                return None
            
            return {
                'is_profitable': True,
                'victim_tx_hash': tx_data['hash'],
                'victim_swap_params': swap_params,
                'front_run_params': profit_analysis['front_run'],
                'back_run_params': profit_analysis['back_run'],
                'expected_profit_usd': profit_analysis['net_profit_usd'],
                'gas_price_gwei': tx_data.get('gasPrice', 0) / 1e9,
                'victim_gas_price_gwei': tx_data.get('gasPrice', 0) / 1e9
            }
            
        except Exception as e:
            logger.debug(f"Error analyzing transaction for sandwich: {e}")
            return None
    
    def _is_swap_transaction(self, tx_data: Dict) -> bool:
        """
        Check if transaction is a DEX swap
        
        Args:
            tx_data: Transaction data
            
        Returns:
            True if swap transaction
        """
        input_data = tx_data.get('input', '')
        
        if not input_data or len(input_data) < 10:
            return False
        
        # Check function signature (first 4 bytes)
        function_sig = input_data[:10]
        
        swap_signatures = [
            self.SWAP_EXACT_TOKENS_FOR_TOKENS,
            self.SWAP_TOKENS_FOR_EXACT_TOKENS,
            self.SWAP_EXACT_ETH_FOR_TOKENS,
            self.SWAP_TOKENS_FOR_EXACT_ETH
        ]
        
        return function_sig in swap_signatures
    
    def _decode_swap_transaction(self, tx_data: Dict) -> Optional[Dict]:
        """
        Decode swap transaction parameters
        
        Args:
            tx_data: Transaction data
            
        Returns:
            Decoded swap parameters
        """
        try:
            input_data = tx_data.get('input', '')
            function_sig = input_data[:10]
            
            # Decode based on function signature
            if function_sig == self.SWAP_EXACT_TOKENS_FOR_TOKENS:
                # swapExactTokensForTokens(uint amountIn, uint amountOutMin, address[] path, address to, uint deadline)
                decoded = decode(
                    ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                    bytes.fromhex(input_data[10:])
                )
                
                amount_in = decoded[0]
                amount_out_min = decoded[1]
                path = decoded[2]
                recipient = decoded[3]
                deadline = decoded[4]
                
                # Get token info
                token_in = path[0]
                token_out = path[-1]
                
                # Estimate value in USD (simplified)
                value_usd = self._estimate_swap_value_usd(amount_in, token_in)
                
                return {
                    'function': 'swapExactTokensForTokens',
                    'amount_in': amount_in,
                    'amount_out_min': amount_out_min,
                    'path': path,
                    'token_in': token_in,
                    'token_out': token_out,
                    'recipient': recipient,
                    'deadline': deadline,
                    'value_usd': value_usd,
                    'router': tx_data.get('to')
                }
            
            # Similar decoding for other function signatures
            # ... (omitted for brevity)
            
            return None
            
        except Exception as e:
            logger.debug(f"Error decoding swap transaction: {e}")
            return None
    
    async def _calculate_sandwich_profit(
        self,
        swap_params: Dict,
        victim_tx: Dict
    ) -> Optional[Dict]:
        """
        Calculate expected profit from sandwich attack
        
        Process:
        1. Calculate price impact of victim swap
        2. Calculate front-run amount (buy same token before victim)
        3. Calculate back-run amount (sell after victim)
        4. Estimate profit = (sell_price - buy_price) * amount - gas
        
        Args:
            swap_params: Victim swap parameters
            victim_tx: Victim transaction data
            
        Returns:
            Profit analysis dict
        """
        try:
            token_in = swap_params['token_in']
            token_out = swap_params['token_out']
            amount_in = swap_params['amount_in']
            router = swap_params['router']
            
            # Get current price
            current_price = await self._get_current_price(token_in, token_out, router)
            
            if current_price <= 0:
                return None
            
            # Calculate victim's price impact
            victim_price_impact_pct = await self._calculate_price_impact(
                token_in,
                token_out,
                amount_in,
                router
            )
            
            if victim_price_impact_pct < 0.5:  # Need at least 0.5% impact
                return None
            
            # Calculate optimal front-run size
            # Use 30% of victim's size to minimize detection
            front_run_amount = int(amount_in * 0.3)
            
            # Calculate expected prices
            # Price after front-run
            front_run_impact = await self._calculate_price_impact(
                token_in,
                token_out,
                front_run_amount,
                router
            )
            price_after_front_run = current_price * (1 + front_run_impact / 100)
            
            # Price after victim swap
            combined_impact = front_run_impact + victim_price_impact_pct
            price_after_victim = current_price * (1 + combined_impact / 100)
            
            # Calculate tokens received in front-run
            tokens_bought = front_run_amount / price_after_front_run
            
            # Calculate tokens sold in back-run (at higher price)
            back_run_proceeds = tokens_bought * price_after_victim
            
            # Calculate gross profit
            gross_profit = back_run_proceeds - front_run_amount
            
            # Convert to USD
            token_in_price_usd = self._get_token_price_usd(token_in)
            gross_profit_usd = (gross_profit / (10 ** 18)) * token_in_price_usd
            
            # Calculate gas costs (2 transactions: front-run + back-run)
            front_run_gas = await self._estimate_sandwich_gas_cost('front_run')
            back_run_gas = await self._estimate_sandwich_gas_cost('back_run')
            total_gas_cost_usd = front_run_gas + back_run_gas
            
            # Calculate optimal tip to beat victim
            # Need to pay higher gas to be included first
            victim_gas_price = victim_tx.get('gasPrice', 0)
            optimal_tip = int(victim_gas_price * 1.125)  # 12.5% more
            
            # Net profit
            net_profit_usd = gross_profit_usd - total_gas_cost_usd
            
            if net_profit_usd <= 0:
                return None
            
            return {
                'front_run': {
                    'amount_in': front_run_amount,
                    'token_in': token_in,
                    'token_out': token_out,
                    'expected_tokens_out': tokens_bought,
                    'gas_price': optimal_tip
                },
                'back_run': {
                    'amount_in': tokens_bought,
                    'token_in': token_out,
                    'token_out': token_in,
                    'expected_amount_out': back_run_proceeds,
                    'gas_price': victim_gas_price  # Can use same as victim
                },
                'price_analysis': {
                    'current_price': current_price,
                    'price_after_front_run': price_after_front_run,
                    'price_after_victim': price_after_victim,
                    'victim_impact_pct': victim_price_impact_pct,
                    'front_run_impact_pct': front_run_impact
                },
                'gross_profit_usd': gross_profit_usd,
                'gas_cost_usd': total_gas_cost_usd,
                'net_profit_usd': net_profit_usd
            }
            
        except Exception as e:
            logger.error(f"Error calculating sandwich profit: {e}")
            return None
    
    async def _get_current_price(
        self,
        token_in: str,
        token_out: str,
        router: str
    ) -> float:
        """Get current exchange rate"""
        try:
            router_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router),
                abi=[{
                    "constant": True,
                    "inputs": [
                        {"name": "amountIn", "type": "uint256"},
                        {"name": "path", "type": "address[]"}
                    ],
                    "name": "getAmountsOut",
                    "outputs": [{"name": "amounts", "type": "uint256[]"}],
                    "type": "function"
                }]
            )
            
            amount_in = 10 ** 18  # 1 token
            path = [
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out)
            ]
            
            amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
            price = amounts[1] / (10 ** 18)
            
            return price
            
        except Exception as e:
            logger.debug(f"Error getting price: {e}")
            return 0
    
    async def _calculate_price_impact(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        router: str
    ) -> float:
        """
        Calculate price impact percentage of a swap
        
        Returns:
            Price impact in percentage
        """
        try:
            # Get price before swap (for 1 token)
            price_before = await self._get_current_price(token_in, token_out, router)
            
            # Get price after swap (simulate large swap)
            router_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router),
                abi=[{
                    "constant": True,
                    "inputs": [
                        {"name": "amountIn", "type": "uint256"},
                        {"name": "path", "type": "address[]"}
                    ],
                    "name": "getAmountsOut",
                    "outputs": [{"name": "amounts", "type": "uint256[]"}],
                    "type": "function"
                }]
            )
            
            path = [
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out)
            ]
            
            amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
            effective_price = amounts[1] / amount_in
            
            # Calculate impact
            price_impact_pct = ((effective_price - price_before) / price_before) * 100
            
            return abs(price_impact_pct)
            
        except Exception as e:
            logger.debug(f"Error calculating price impact: {e}")
            return 0
    
    def _estimate_swap_value_usd(self, amount: int, token_address: str) -> float:
        """Estimate swap value in USD (simplified)"""
        # In production, fetch real token prices
        amount_tokens = amount / (10 ** 18)
        
        # Simplified price mapping
        token_prices = {
            '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270': 0.80,  # WMATIC
            '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174': 1.0,   # USDC
            '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619': 3000.0  # WETH
        }
        
        price_usd = token_prices.get(token_address, 1.0)
        return amount_tokens * price_usd
    
    def _get_token_price_usd(self, token_address: str) -> float:
        """Get token price in USD"""
        prices = {
            '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270': 0.80,
            '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174': 1.0,
            '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619': 3000.0
        }
        return prices.get(token_address, 1.0)
    
    async def _estimate_sandwich_gas_cost(self, tx_type: str) -> float:
        """Estimate gas cost for sandwich transaction"""
        # Front-run: ~200k gas
        # Back-run: ~200k gas
        gas_limit = 200000
        gas_price_gwei = 50
        gas_cost_matic = (gas_limit * gas_price_gwei) / (10 ** 9)
        gas_cost_usd = gas_cost_matic * 0.80
        
        return gas_cost_usd