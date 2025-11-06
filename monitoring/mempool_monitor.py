"""
Mempool Monitor
Monitors pending transactions for sandwich attack opportunities
"""

import asyncio
import json
from typing import Dict, Set, Optional
from collections import deque
from web3 import Web3
from loguru import logger


class MempoolMonitor:
    """
    Monitors Polygon mempool for large pending swaps
    Uses WebSocket connection for real-time monitoring
    """
    
    def __init__(self, rpc_manager, config: Dict):
        """
        Initialize Mempool Monitor
        
        Args:
            rpc_manager: RPC manager for WebSocket connection
            config: Bot configuration
        """
        self.rpc_manager = rpc_manager
        self.config = config
        
        # Pending transactions cache
        self.pending_txs = {}  # tx_hash -> tx_data
        self.max_cache_size = 1000
        
        # WebSocket connection
        self.ws = None
        self.ws_connected = False
        self.subscription_id = None
        
        # Filtering
        self.min_value_usd = config['monitoring']['mempool_filter_min_value_usd']
        
        # Running state
        self.running = False
        
        logger.info("Mempool Monitor initialized")
    
    async def start(self):
        """Start mempool monitoring"""
        self.running = True
        logger.info("Starting mempool monitoring...")
        
        # Start WebSocket connection
        await self._connect_websocket()
        
        # Start monitoring loop
        asyncio.create_task(self._monitor_loop())
    
    async def stop(self):
        """Stop mempool monitoring"""
        self.running = False
        
        if self.ws:
            await self._unsubscribe()
            await self.ws.close()
        
        logger.info("Mempool monitoring stopped")
    
    async def _connect_websocket(self):
        """Connect to WebSocket endpoint"""
        try:
            # Get WebSocket URL from RPC manager
            ws_url = self.rpc_manager.get_websocket_url()
            
            if not ws_url:
                logger.error("No WebSocket URL available")
                return
            
            # Create WebSocket connection
            import websockets
            self.ws = await websockets.connect(ws_url)
            self.ws_connected = True
            
            # Subscribe to pending transactions
            await self._subscribe_pending_txs()
            
            logger.success(f"Connected to mempool WebSocket: {ws_url[:50]}...")
            
        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {e}")
            self.ws_connected = False
    
    async def _subscribe_pending_txs(self):
        """Subscribe to pending transaction events"""
        try:
            # Ethereum JSON-RPC subscription
            subscribe_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newPendingTransactions"]
            })
            
            await self.ws.send(subscribe_msg)
            
            # Receive subscription ID
            response = await self.ws.recv()
            response_data = json.loads(response)
            
            if 'result' in response_data:
                self.subscription_id = response_data['result']
                logger.success(f"Subscribed to pending txs: {self.subscription_id}")
            else:
                logger.error(f"Subscription failed: {response_data}")
                
        except Exception as e:
            logger.error(f"Error subscribing to pending transactions: {e}")
    
    async def _unsubscribe(self):
        """Unsubscribe from pending transactions"""
        try:
            if self.subscription_id:
                unsubscribe_msg = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_unsubscribe",
                    "params": [self.subscription_id]
                })
                
                await self.ws.send(unsubscribe_msg)
                logger.info("Unsubscribed from pending transactions")
                
        except Exception as e:
            logger.error(f"Error unsubscribing: {e}")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Mempool monitor loop started")
        
        while self.running:
            try:
                if not self.ws_connected:
                    # Try to reconnect
                    await asyncio.sleep(5)
                    await self._connect_websocket()
                    continue
                
                # Receive transaction hash
                message = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                data = json.loads(message)
                
                # Extract transaction hash
                if 'params' in data and 'result' in data['params']:
                    tx_hash = data['params']['result']
                    
                    # Fetch full transaction data
                    asyncio.create_task(self._process_pending_tx(tx_hash))
                
            except asyncio.TimeoutError:
                # No new transactions - continue
                continue
            except Exception as e:
                logger.debug(f"Error in monitor loop: {e}")
                self.ws_connected = False
                await asyncio.sleep(1)
    
    async def _process_pending_tx(self, tx_hash: str):
        """
        Process a pending transaction
        
        Args:
            tx_hash: Transaction hash
        """
        try:
            # Get full transaction data
            w3 = self.rpc_manager.get_web3()
            tx = w3.eth.get_transaction(tx_hash)
            
            if not tx:
                return
            
            # Filter by value
            value_eth = w3.from_wei(tx.get('value', 0), 'ether')
            value_usd = float(value_eth) * 0.80  # Approximate MATIC price
            
            # Skip small transactions
            if value_usd < self.min_value_usd:
                return
            
            # Check if it's a swap transaction
            if self._is_swap_transaction(tx):
                # Add to cache
                self.pending_txs[tx_hash] = {
                    'hash': tx_hash,
                    'from': tx['from'],
                    'to': tx['to'],
                    'value': tx['value'],
                    'input': tx['input'],
                    'gasPrice': tx.get('gasPrice', 0),
                    'timestamp': asyncio.get_event_loop().time()
                }
                
                # Maintain cache size
                if len(self.pending_txs) > self.max_cache_size:
                    # Remove oldest
                    oldest_hash = min(
                        self.pending_txs.keys(),
                        key=lambda k: self.pending_txs[k]['timestamp']
                    )
                    del self.pending_txs[oldest_hash]
                
                logger.debug(f"Found potential sandwich target: {tx_hash[:10]}...")
            
        except Exception as e:
            logger.debug(f"Error processing pending tx {tx_hash[:10]}: {e}")
    
    def _is_swap_transaction(self, tx: Dict) -> bool:
        """
        Check if transaction is a DEX swap
        
        Args:
            tx: Transaction data
            
        Returns:
            True if swap transaction
        """
        input_data = tx.get('input', '')
        
        if not input_data or len(input_data) < 10:
            return False
        
        # Common swap function signatures
        swap_signatures = [
            '0x38ed1739',  # swapExactTokensForTokens
            '0x8803dbee',  # swapTokensForExactTokens
            '0x7ff36ab5',  # swapExactETHForTokens
            '0x4a25d94a',  # swapTokensForExactETH
            '0x18cbafe5',  # swapExactTokensForETH
            '0xfb3bdb41',  # swapETHForExactTokens
        ]
        
        function_sig = input_data[:10]
        return function_sig in swap_signatures
    
    def get_pending_transactions(self) -> Dict[str, Dict]:
        """
        Get current pending transactions
        
        Returns:
            Dict mapping tx_hash to tx_data
        """
        # Clean up old transactions (>60 seconds)
        current_time = asyncio.get_event_loop().time()
        to_remove = [
            tx_hash for tx_hash, tx_data in self.pending_txs.items()
            if current_time - tx_data['timestamp'] > 60
        ]
        
        for tx_hash in to_remove:
            del self.pending_txs[tx_hash]
        
        return self.pending_txs.copy()
    
    def get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """
        Get specific transaction data
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction data or None
        """
        return self.pending_txs.get(tx_hash)
    
    async def check_connection(self) -> bool:
        """Check if WebSocket is connected"""
        return self.ws_connected
    
    async def reconnect(self):
        """Force reconnection to WebSocket"""
        if self.ws:
            await self.ws.close()
        
        self.ws_connected = False
        await self._connect_websocket()