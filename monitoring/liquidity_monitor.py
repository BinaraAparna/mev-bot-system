"""
Liquidity Monitor
Tracks liquidity levels in DEX pools to avoid high slippage
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from loguru import logger


class LiquidityMonitor:
    """
    Monitors liquidity in DEX pools
    Helps avoid trading in low-liquidity pools (high slippage)
    """
    
    def __init__(self, w3: Web3, dex_config: Dict):
        """
        Initialize Liquidity Monitor
        
        Args:
            w3: Web3 instance
            dex_config: DEX configuration
        """
        self.w3 = w3
        self.dex_config = dex_config
        
        # Liquidity cache
        self.liquidity_cache = {}  # (dex, token_a, token_b) -> liquidity_usd
        
        # Running state
        self.running = False
        
        logger.info("Liquidity Monitor initialized")
    
    async def start(self):
        """Start liquidity monitoring"""
        self.running = True
        logger.info("Starting liquidity monitoring...")
        
        # Update loop
        asyncio.create_task(self._update_loop())
    
    async def stop(self):
        """Stop liquidity monitoring"""
        self.running = False
        logger.info("Liquidity monitoring stopped")
    
    async def _update_loop(self):
        """Periodically update liquidity data"""
        while self.running:
            try:
                await self._update_liquidity()
                await asyncio.sleep(60)  # Update every 60 seconds
            except Exception as e:
                logger.error(f"Error in liquidity update loop: {e}")
                await asyncio.sleep(10)
    
    async def _update_liquidity(self):
        """Update liquidity for tracked pools"""
        try:
            # This is a simplified version
            # In production, use multicall to batch all liquidity checks
            logger.debug("Liquidity data updated")
            
        except Exception as e:
            logger.error(f"Error updating liquidity: {e}")
    
    async def get_pool_liquidity(
        self,
        dex_name: str,
        token_a_address: str,
        token_b_address: str
    ) -> float:
        """
        Get liquidity for a specific pool
        
        Args:
            dex_name: DEX name
            token_a_address: First token address
            token_b_address: Second token address
            
        Returns:
            Liquidity in USD
        """
        try:
            # Check cache first
            cache_key = (dex_name, token_a_address, token_b_address)
            
            if cache_key in self.liquidity_cache:
                return self.liquidity_cache[cache_key]
            
            # Fetch from blockchain
            dex_config = self.dex_config['polygon_dexes'].get(dex_name)
            
            if not dex_config or dex_config.get('version') != 'v2':
                return 0
            
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
            reserve_0 = reserves[0]
            # reserve_1 = reserves[1]  # Reserved for future use
            
            # Estimate USD value (simplified)
            # Assume token_a is stablecoin or calculate based on price
            liquidity_usd = (reserve_0 / 10**18) * 2  # Rough estimate
            
            # Cache result
            self.liquidity_cache[cache_key] = liquidity_usd
            
            return liquidity_usd
            
        except Exception as e:
            logger.debug(f"Error getting pool liquidity: {e}")
            return 0
    
    async def get_all_pool_liquidity(
        self,
        token_a_address: str,
        token_b_address: str
    ) -> Dict[str, float]:
        """
        Get liquidity across all DEXes for a token pair
        
        Args:
            token_a_address: First token
            token_b_address: Second token
            
        Returns:
            Dict mapping DEX name to liquidity USD
        """
        results = {}
        
        for dex_name, dex_config in self.dex_config['polygon_dexes'].items():
            if not dex_config.get('enabled', False):
                continue
            
            liquidity = await self.get_pool_liquidity(
                dex_name,
                token_a_address,
                token_b_address
            )
            
            if liquidity > 0:
                results[dex_name] = liquidity
        
        return results
    
    async def get_best_liquidity_dex(
        self,
        token_a_address: str,
        token_b_address: str
    ) -> Optional[Tuple[str, float]]:
        """
        Find DEX with highest liquidity for a pair
        
        Args:
            token_a_address: First token
            token_b_address: Second token
            
        Returns:
            Tuple of (dex_name, liquidity_usd) or None
        """
        all_liquidity = await self.get_all_pool_liquidity(
            token_a_address,
            token_b_address
        )
        
        if not all_liquidity:
            return None
        
        best_dex = max(all_liquidity.items(), key=lambda x: x[1])
        return best_dex
    
    def is_liquidity_sufficient(
        self,
        liquidity_usd: float,
        trade_size_usd: float,
        max_impact_pct: float = 1.0
    ) -> bool:
        """
        Check if liquidity is sufficient for trade
        
        Rule of thumb: trade_size should be < 1% of liquidity
        
        Args:
            liquidity_usd: Pool liquidity in USD
            trade_size_usd: Trade size in USD
            max_impact_pct: Maximum acceptable impact percentage
            
        Returns:
            True if liquidity is sufficient
        """
        if liquidity_usd <= 0:
            return False
        
        impact_pct = (trade_size_usd / liquidity_usd) * 100
        return impact_pct <= max_impact_pct
    
    def _get_factory_abi(self) -> List[Dict]:
        """Minimal factory ABI"""
        return [{
            "constant": True,
            "inputs": [
                {"name": "tokenA", "type": "address"},
                {"name": "tokenB", "type": "address"}
            ],
            "name": "getPair",
            "outputs": [{"name": "pair", "type": "address"}],
            "type": "function"
        }]
    
    def _get_pair_abi(self) -> List[Dict]:
        """Minimal pair ABI"""
        return [{
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