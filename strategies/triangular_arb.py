"""
Triangular Arbitrage Strategy
Exploits price inefficiencies across 3 tokens: A -> B -> C -> A
"""

import itertools
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from web3 import Web3
from loguru import logger


class TriangularArbitrage:
    """
    Triangular arbitrage: Find profitable cycles through 3 tokens
    Example: WMATIC -> USDC -> WETH -> WMATIC
    """
    
    def __init__(self, w3: Web3, dex_config: Dict, token_config: Dict, multicall):
        """
        Initialize Triangular Arbitrage strategy
        
        Args:
            w3: Web3 instance
            dex_config: DEX configuration
            token_config: Token configuration
            multicall: Multicall utility for batched calls
        """
        self.w3 = w3
        self.dex_config = dex_config
        self.token_config = token_config
        self.multicall = multicall
        
        # Pre-computed triangular paths
        self.triangular_paths = self._generate_triangular_paths()
        
        logger.info(f"Triangular Arbitrage initialized with {len(self.triangular_paths)} paths")
    
    def _generate_triangular_paths(self) -> List[List[str]]:
        """
        Generate all possible triangular arbitrage paths
        
        Strategy:
        1. Start with base tokens (high liquidity)
        2. Generate all 3-token combinations
        3. Filter by liquidity and trusted tokens
        
        Returns:
            List of paths, each path is [token_a, token_b, token_c, token_a]
        """
        paths = []
        
        # Get high-priority tokens
        base_tokens = [
            symbol for symbol, token_data in self.token_config['tokens'].items()
            if token_data.get('priority', 10) <= 2 and token_data.get('trusted', False)
        ]
        
        # Pre-defined high-liquidity triangular paths
        predefined_paths = self.dex_config.get('triangular_pairs', {}).get('high_liquidity', [])
        
        for path in predefined_paths:
            if len(path) == 3:
                # Complete the cycle
                paths.append(path + [path[0]])
        
        # Generate additional paths from base tokens
        for combo in itertools.combinations(base_tokens, 3):
            path = list(combo) + [combo[0]]
            if path not in paths:
                paths.append(path)
        
        logger.info(f"Generated {len(paths)} triangular paths")
        return paths
    
    async def find_opportunities(self) -> List[Dict]:
        """
        Find profitable triangular arbitrage opportunities
        
        Returns:
            List of profitable opportunities
        """
        opportunities = []
        
        try:
            # Get enabled DEXes
            enabled_dexes = [
                (name, config) for name, config in self.dex_config['polygon_dexes'].items()
                if config.get('enabled', False) and config.get('version') == 'v2'
            ]
            
            # Check each path on each DEX
            for path in self.triangular_paths:
                for dex_name, dex_config in enabled_dexes:
                    opp = await self._check_triangular_path(path, dex_name, dex_config)
                    
                    if opp and opp['expected_profit_usd'] > 0:
                        opportunities.append(opp)
            
            # Sort by profit
            opportunities.sort(key=lambda x: x['expected_profit_usd'], reverse=True)
            
            return opportunities[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error finding triangular opportunities: {e}")
            return []
    
    async def _check_triangular_path(
        self,
        path: List[str],
        dex_name: str,
        dex_config: Dict
    ) -> Optional[Dict]:
        """
        Check if a triangular path is profitable
        
        Path format: [token_a, token_b, token_c, token_a]
        
        Args:
            path: List of 4 token symbols (last = first)
            dex_name: DEX name
            dex_config: DEX configuration
            
        Returns:
            Opportunity dict or None
        """
        try:
            if len(path) != 4 or path[0] != path[3]:
                return None
            
            # Get token configs
            tokens = [self.token_config['tokens'].get(symbol) for symbol in path[:3]]
            
            if not all(tokens):
                return None
            
            # Calculate exchange rates for all 3 swaps
            # Swap 1: A -> B
            rate_ab = await self._get_exchange_rate(
                tokens[0],
                tokens[1],
                dex_config
            )
            
            # Swap 2: B -> C
            rate_bc = await self._get_exchange_rate(
                tokens[1],
                tokens[2],
                dex_config
            )
            
            # Swap 3: C -> A
            rate_ca = await self._get_exchange_rate(
                tokens[2],
                tokens[0],
                dex_config
            )
            
            if not all([rate_ab, rate_bc, rate_ca]):
                return None
            
            # Calculate final exchange rate (compound rate)
            final_rate = rate_ab * rate_bc * rate_ca
            
            # Profit = (final_rate - 1) * initial_amount
            # If final_rate > 1.0, we have profit
            if final_rate <= 1.005:  # Need at least 0.5% to cover fees/gas
                return None
            
            # Calculate optimal trade size
            trade_size = await self._calculate_optimal_trade_size(
                tokens[0],
                tokens[1],
                tokens[2],
                dex_config
            )
            
            if trade_size <= 0:
                return None
            
            # Estimate profit
            profit_pct = (final_rate - 1.0) * 100
            
            # Get token A price in USD
            token_a_price_usd = await self._get_token_price_usd(tokens[0])
            
            # Gross profit
            gross_profit_usd = (trade_size * token_a_price_usd) * (profit_pct / 100)
            
            # Subtract gas costs (3 swaps)
            gas_cost_usd = await self._estimate_gas_cost_triangular()
            
            net_profit_usd = gross_profit_usd - gas_cost_usd
            
            if net_profit_usd <= 0:
                return None
            
            return {
                'strategy_type': 'triangular_arbitrage',
                'path': path,
                'tokens': tokens,
                'dex': dex_name,
                'dex_config': dex_config,
                'trade_size': trade_size,
                'trade_size_usd': trade_size * token_a_price_usd,
                'exchange_rates': {
                    'A->B': rate_ab,
                    'B->C': rate_bc,
                    'C->A': rate_ca,
                    'final': final_rate
                },
                'profit_percentage': profit_pct,
                'gross_profit_usd': gross_profit_usd,
                'gas_cost_usd': gas_cost_usd,
                'expected_profit_usd': net_profit_usd
            }
            
        except Exception as e:
            logger.debug(f"Error checking triangular path {path}: {e}")
            return None
    
    async def _get_exchange_rate(
        self,
        token_in: Dict,
        token_out: Dict,
        dex_config: Dict
    ) -> float:
        """
        Get exchange rate between two tokens on a DEX
        
        Rate = output_amount / input_amount (for 1 unit of token_in)
        
        Args:
            token_in: Input token config
            token_out: Output token config
            dex_config: DEX configuration
            
        Returns:
            Exchange rate (float)
        """
        try:
            router_address = dex_config['router']
            router_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=self._get_router_abi()
            )
            
            # Use 1 token as input
            amount_in = 10 ** token_in['decimals']
            
            path = [
                Web3.to_checksum_address(token_in['address']),
                Web3.to_checksum_address(token_out['address'])
            ]
            
            # Get amounts out
            amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
            
            # Calculate rate
            amount_out = amounts[1]
            rate = amount_out / (10 ** token_out['decimals'])
            
            return rate
            
        except Exception as e:
            logger.debug(f"Error getting exchange rate: {e}")
            return 0
    
    async def _calculate_optimal_trade_size(
        self,
        token_a: Dict,
        token_b: Dict,
        token_c: Dict,
        dex_config: Dict
    ) -> float:
        """
        Calculate optimal trade size for triangular arbitrage
        
        Optimal size = min(pool_liquidity) * safety_factor
        
        Args:
            token_a: First token
            token_b: Second token
            token_c: Third token
            dex_config: DEX configuration
            
        Returns:
            Optimal trade size in token A units
        """
        try:
            # Get liquidity for all 3 pairs
            liquidity_ab = await self._get_pair_liquidity(token_a, token_b, dex_config)
            liquidity_bc = await self._get_pair_liquidity(token_b, token_c, dex_config)
            liquidity_ca = await self._get_pair_liquidity(token_c, token_a, dex_config)
            
            if min(liquidity_ab, liquidity_bc, liquidity_ca) <= 0:
                return 0
            
            # Use 5% of smallest liquidity to minimize slippage
            min_liquidity = min(liquidity_ab, liquidity_bc, liquidity_ca)
            optimal_size = min_liquidity * 0.05
            
            # Cap at reasonable maximum
            max_size = 10000  # Max 10k tokens
            optimal_size = min(optimal_size, max_size)
            
            return optimal_size
            
        except Exception as e:
            logger.debug(f"Error calculating optimal trade size: {e}")
            return 0
    
    async def _get_pair_liquidity(
        self,
        token_a: Dict,
        token_b: Dict,
        dex_config: Dict
    ) -> float:
        """Get liquidity for a token pair"""
        try:
            factory_address = dex_config['factory']
            factory_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_address),
                abi=[{
                    "constant": True,
                    "inputs": [
                        {"name": "tokenA", "type": "address"},
                        {"name": "tokenB", "type": "address"}
                    ],
                    "name": "getPair",
                    "outputs": [{"name": "pair", "type": "address"}],
                    "type": "function"
                }]
            )
            
            pair_address = factory_contract.functions.getPair(
                Web3.to_checksum_address(token_a['address']),
                Web3.to_checksum_address(token_b['address'])
            ).call()
            
            if pair_address == '0x0000000000000000000000000000000000000000':
                return 0
            
            # Get reserves
            pair_contract = self.w3.eth.contract(
                address=pair_address,
                abi=[{
                    "constant": True,
                    "inputs": [],
                    "name": "getReserves",
                    "outputs": [
                        {"name": "reserve0", "type": "uint112"},
                        {"name": "reserve1", "type": "uint112"},
                        {"name": "blockTimestampLast", "type": "uint32"}
                    ],
                    "type": "function"
                }]
            )
            
            reserves = pair_contract.functions.getReserves().call()
            reserve_a = reserves[0] / (10 ** token_a['decimals'])
            
            return reserve_a
            
        except Exception as e:
            logger.debug(f"Error getting pair liquidity: {e}")
            return 0
    
    async def _get_token_price_usd(self, token: Dict) -> float:
        """Get token price in USD (simplified)"""
        if token['symbol'] in ['USDC', 'USDT', 'DAI']:
            return 1.0
        elif token['symbol'] == 'WMATIC':
            return 0.80
        elif token['symbol'] == 'WETH':
            return 3000.0
        elif token['symbol'] == 'WBTC':
            return 60000.0
        else:
            return 10.0  # Default
    
    async def _estimate_gas_cost_triangular(self) -> float:
        """
        Estimate gas cost for triangular arbitrage
        
        3 swaps + overhead = ~400k-500k gas
        """
        gas_limit = 450000
        gas_price_gwei = 50
        gas_cost_matic = (gas_limit * gas_price_gwei) / (10 ** 9)
        gas_cost_usd = gas_cost_matic * 0.80
        
        return gas_cost_usd
    
    def _get_router_abi(self) -> List:
        """Minimal Router ABI"""
        return [{
            "constant": True,
            "inputs": [
                {"name": "amountIn", "type": "uint256"},
                {"name": "path", "type": "address[]"}
            ],
            "name": "getAmountsOut",
            "outputs": [{"name": "amounts", "type": "uint256[]"}],
            "type": "function"
        }]