"""
RPC Manager
Manages multi-tier RPC fallback system (Tier 1-4)
CRITICAL for free tier optimization and avoiding rate limits
"""

import os
import json
import time
from typing import Optional, Dict
from web3 import Web3
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class RPCManager:
    """
    Multi-tier RPC management system
    
    Tier 1: Alchemy Free (300M CU/month) - Primary
    Tier 2: QuickNode Free (10M credits) - Secondary
    Tier 3: Infura Free (100k/day) - Buffer
    Tier 4: Public RPC - Last resort only
    """
    
    def __init__(self):
        """Initialize RPC Manager with tier system"""
        # Load RPC configuration
        with open('config/rpc_config.json', 'r') as f:
            self.config = json.load(f)
        
        # Initialize tiers
        self.tiers = self._init_tiers()
        self.current_tier = 'tier_1'
        
        # Usage tracking
        self.usage_stats = {
            tier_name: {
                'requests': 0,
                'failures': 0,
                'last_failure_time': 0
            }
            for tier_name in self.tiers.keys()
        }
        
        # Web3 instances
        self.w3_instances = {}
        self._create_web3_instances()
        
        # WebSocket URL cache
        self.ws_url_cache = None
        
        logger.info(f"RPC Manager initialized with {len(self.tiers)} tiers")
        logger.info(f"Current tier: {self.current_tier}")
    
    def _init_tiers(self) -> Dict:
        """Initialize RPC tier configuration"""
        tiers = {}
        
        for tier_name, tier_config in self.config['rpc_tiers'].items():
            if tier_name == 'archive_tier':
                continue  # Handle separately
            
            http_url = os.getenv(tier_config['http_url_env'])
            wss_url = os.getenv(tier_config.get('wss_url_env', ''))
            
            if http_url:
                tiers[tier_name] = {
                    'name': tier_config['name'],
                    'http_url': http_url,
                    'wss_url': wss_url if wss_url else None,
                    'priority': tier_config['priority'],
                    'limits': tier_config['limits'],
                    'capabilities': tier_config['capabilities']
                }
        
        return tiers
    
    def _create_web3_instances(self):
        """Create Web3 instances for each tier"""
        for tier_name, tier_data in self.tiers.items():
            try:
                w3 = Web3(Web3.HTTPProvider(tier_data['http_url']))
                
                # Test connection
                if w3.is_connected():
                    self.w3_instances[tier_name] = w3
                    logger.success(f"Connected to {tier_data['name']}")
                else:
                    logger.warning(f"Failed to connect to {tier_data['name']}")
                    
            except Exception as e:
                logger.error(f"Error creating Web3 for {tier_name}: {e}")
    
    def get_web3(self, tier: Optional[str] = None) -> Web3:
        """
        Get Web3 instance for current or specified tier
        
        Args:
            tier: Specific tier name (None = current tier)
            
        Returns:
            Web3 instance
        """
        tier_name = tier if tier else self.current_tier
        
        if tier_name not in self.w3_instances:
            logger.error(f"Tier {tier_name} not available, using tier_1")
            tier_name = 'tier_1'
        
        return self.w3_instances[tier_name]
    
    def get_websocket_url(self) -> Optional[str]:
        """Get WebSocket URL for current tier"""
        if self.ws_url_cache:
            return self.ws_url_cache
        
        tier_data = self.tiers.get(self.current_tier)
        
        if tier_data and tier_data['wss_url']:
            self.ws_url_cache = tier_data['wss_url']
            return tier_data['wss_url']
        
        # Try tier_2 if tier_1 doesn't have WSS
        tier_2_data = self.tiers.get('tier_2')
        if tier_2_data and tier_2_data['wss_url']:
            self.ws_url_cache = tier_2_data['wss_url']
            return tier_2_data['wss_url']
        
        return None
    
    async def make_call(self, method: str, params: list, tier: Optional[str] = None):
        """
        Make RPC call with automatic fallback
        
        Args:
            method: RPC method
            params: Method parameters
            tier: Specific tier to use (None = auto)
            
        Returns:
            RPC result
        """
        tier_name = tier if tier else self.current_tier
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                w3 = self.get_web3(tier_name)
                
                # Make call
                result = w3.provider.make_request(method, params)
                
                # Track success
                self.usage_stats[tier_name]['requests'] += 1
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check for rate limit errors
                if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
                    logger.warning(f"Rate limit on {tier_name}: {e}")
                    
                    # Record failure
                    self.usage_stats[tier_name]['failures'] += 1
                    self.usage_stats[tier_name]['last_failure_time'] = time.time()
                    
                    # Fallback to next tier
                    next_tier = self._get_next_tier(tier_name)
                    
                    if next_tier:
                        logger.info(f"Falling back to {next_tier}")
                        tier_name = next_tier
                        self.current_tier = next_tier
                    else:
                        logger.critical("All RPC tiers exhausted!")
                        raise
                else:
                    # Other error - retry
                    if attempt < max_retries - 1:
                        logger.debug(f"RPC error, retrying: {e}")
                        time.sleep(1)
                    else:
                        raise
        
        return None
    
    def _get_next_tier(self, current_tier: str) -> Optional[str]:
        """
        Get next tier in fallback sequence
        
        Args:
            current_tier: Current tier name
            
        Returns:
            Next tier name or None
        """
        fallback_sequence = self.config['failover_strategy']['fallback_sequence']
        
        try:
            current_index = fallback_sequence.index(current_tier)
            
            # Return next tier if available
            if current_index + 1 < len(fallback_sequence):
                return fallback_sequence[current_index + 1]
            else:
                return None
                
        except ValueError:
            return 'tier_1'  # Default to tier_1
    
    def force_tier(self, tier_name: str):
        """
        Force switch to specific tier
        
        Args:
            tier_name: Tier to switch to
        """
        if tier_name in self.tiers:
            self.current_tier = tier_name
            logger.info(f"Forced switch to {tier_name}")
        else:
            logger.error(f"Invalid tier: {tier_name}")
    
    def is_healthy(self) -> bool:
        """
        Check if current RPC tier is healthy
        
        Returns:
            True if healthy
        """
        try:
            w3 = self.get_web3()
            return w3.is_connected()
        except Exception:
            return False
    
    def get_tier_status(self) -> Dict:
        """Get status of all tiers"""
        status = {}
        
        for tier_name, tier_data in self.tiers.items():
            stats = self.usage_stats[tier_name]
            
            # Calculate success rate
            total = stats['requests']
            failures = stats['failures']
            success_rate = ((total - failures) / total * 100) if total > 0 else 100
            
            status[tier_name] = {
                'name': tier_data['name'],
                'total_requests': total,
                'failures': failures,
                'success_rate': f"{success_rate:.1f}%",
                'last_failure': stats['last_failure_time'],
                'connected': tier_name in self.w3_instances
            }
        
        return status
    
    def get_usage_stats(self) -> Dict:
        """Get detailed usage statistics"""
        return {
            'current_tier': self.current_tier,
            'tier_stats': self.usage_stats.copy(),
            'tier_status': self.get_tier_status()
        }
    
    async def check_cu_usage(self) -> Dict:
        """
        Check Compute Unit usage (Alchemy-specific)
        
        Returns:
            Usage stats
        """
        # This would require Alchemy API key to check dashboard
        # For now, return estimated usage based on request count
        
        tier_1_requests = self.usage_stats['tier_1']['requests']
        
        # Estimate CU (1 request ≈ 100 CU on average)
        estimated_cu = tier_1_requests * 100
        
        return {
            'tier': 'tier_1',
            'requests': tier_1_requests,
            'estimated_cu': estimated_cu,
            'limit_cu': 300_000_000,  # Alchemy free tier
            'usage_pct': (estimated_cu / 300_000_000) * 100
        }
    
    def reset_tier_to_primary(self):
        """Reset to primary tier (Tier 1)"""
        self.current_tier = 'tier_1'
        logger.info("Reset to primary tier (Tier 1)")