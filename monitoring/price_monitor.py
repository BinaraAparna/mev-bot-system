"""
Price Monitor
Fetches real-time token prices from free APIs (DexScreener, GeckoTerminal)
"""

import asyncio
import aiohttp
from typing import Dict, Optional
from loguru import logger


class PriceMonitor:
    """
    Monitors token prices using free public APIs
    Implements caching to reduce API calls
    """
    
    # Free API endpoints
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
    GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2"
    
    def __init__(self, config: Dict, token_config: Dict):
        """
        Initialize Price Monitor
        
        Args:
            config: Bot configuration
            token_config: Token configuration
        """
        self.config = config
        self.token_config = token_config
        
        # Price cache
        self.price_cache = {}  # token_symbol -> price_usd
        self.cache_timestamps = {}
        
        # Update interval
        self.update_interval = config['monitoring']['price_update_interval_ms'] / 1000
        
        # Running state
        self.running = False
        
        logger.info("Price Monitor initialized")
    
    async def start(self):
        """Start price monitoring"""
        self.running = True
        logger.info("Starting price monitoring...")
        
        # Initial price fetch
        await self._update_all_prices()
        
        # Start update loop
        asyncio.create_task(self._price_update_loop())
    
    async def stop(self):
        """Stop price monitoring"""
        self.running = False
        logger.info("Price monitoring stopped")
    
    async def _price_update_loop(self):
        """Continuously update prices"""
        while self.running:
            try:
                await self._update_all_prices()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in price update loop: {e}")
                await asyncio.sleep(5)
    
    async def _update_all_prices(self):
        """Update prices for all tracked tokens"""
        try:
            # Get list of tokens to track
            tokens = self.token_config['tokens']
            
            # Fetch prices in batches
            async with aiohttp.ClientSession() as session:
                tasks = []
                
                for symbol, token_data in tokens.items():
                    if token_data.get('trusted', False):
                        task = self._fetch_token_price(session, symbol, token_data)
                        tasks.append(task)
                
                # Execute all fetches concurrently
                await asyncio.gather(*tasks, return_exceptions=True)
            
            logger.debug(f"Updated prices for {len(self.price_cache)} tokens")
            
        except Exception as e:
            logger.error(f"Error updating prices: {e}")
    
    async def _fetch_token_price(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        token_data: Dict
    ):
        """
        Fetch price for a single token
        
        Args:
            session: aiohttp session
            symbol: Token symbol
            token_data: Token configuration
        """
        try:
            # Try DexScreener first (primary)
            price = await self._fetch_from_dexscreener(
                session,
                token_data['address']
            )
            
            if price is None:
                # Fallback to GeckoTerminal
                price = await self._fetch_from_geckoterminal(
                    session,
                    token_data['address']
                )
            
            if price is not None:
                self.price_cache[symbol] = price
                self.cache_timestamps[symbol] = asyncio.get_event_loop().time()
            
        except Exception as e:
            logger.debug(f"Error fetching price for {symbol}: {e}")
    
    async def _fetch_from_dexscreener(
        self,
        session: aiohttp.ClientSession,
        token_address: str
    ) -> Optional[float]:
        """
        Fetch price from DexScreener API (free)
        
        Args:
            session: aiohttp session
            token_address: Token address
            
        Returns:
            Price in USD or None
        """
        try:
            url = f"{self.DEXSCREENER_API}/tokens/{token_address}"
            
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract price from first pair
                    if 'pairs' in data and len(data['pairs']) > 0:
                        pair = data['pairs'][0]
                        price_usd = float(pair.get('priceUsd', 0))
                        
                        if price_usd > 0:
                            return price_usd
            
            return None
            
        except Exception as e:
            logger.debug(f"DexScreener fetch error: {e}")
            return None
    
    async def _fetch_from_geckoterminal(
        self,
        session: aiohttp.ClientSession,
        token_address: str
    ) -> Optional[float]:
        """
        Fetch price from GeckoTerminal API (free)
        
        Args:
            session: aiohttp session
            token_address: Token address
            
        Returns:
            Price in USD or None
        """
        try:
            # GeckoTerminal network ID for Polygon
            network_id = "polygon_pos"
            url = f"{self.GECKOTERMINAL_API}/networks/{network_id}/tokens/{token_address}"
            
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'data' in data and 'attributes' in data['data']:
                        price_usd = float(
                            data['data']['attributes'].get('price_usd', 0)
                        )
                        
                        if price_usd > 0:
                            return price_usd
            
            return None
            
        except Exception as e:
            logger.debug(f"GeckoTerminal fetch error: {e}")
            return None
    
    def get_price(self, token_symbol: str) -> Optional[float]:
        """
        Get cached token price
        
        Args:
            token_symbol: Token symbol (e.g., 'WMATIC')
            
        Returns:
            Price in USD or None
        """
        return self.price_cache.get(token_symbol)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices"""
        return self.price_cache.copy()
    
    def is_price_stale(self, token_symbol: str, max_age_seconds: int = 60) -> bool:
        """
        Check if cached price is stale
        
        Args:
            token_symbol: Token symbol
            max_age_seconds: Maximum age before considered stale
            
        Returns:
            True if price is stale or missing
        """
        if token_symbol not in self.cache_timestamps:
            return True
        
        age = asyncio.get_event_loop().time() - self.cache_timestamps[token_symbol]
        return age > max_age_seconds
    
    async def force_update(self, token_symbol: str):
        """
        Force immediate price update for a token
        
        Args:
            token_symbol: Token symbol to update
        """
        try:
            token_data = self.token_config['tokens'].get(token_symbol)
            
            if not token_data:
                return
            
            async with aiohttp.ClientSession() as session:
                await self._fetch_token_price(session, token_symbol, token_data)
            
        except Exception as e:
            logger.error(f"Error in force update: {e}")