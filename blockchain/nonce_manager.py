"""
Nonce Manager
Handles transaction nonce sequencing to avoid stuck transactions
"""

import asyncio
from typing import Dict, Optional
from web3 import Web3
from loguru import logger


class NonceManager:
    """
    Manages transaction nonces for executor wallet
    Ensures sequential nonce allocation to prevent stuck transactions
    """
    
    def __init__(self, w3: Web3, executor_address: str):
        """
        Initialize Nonce Manager
        
        Args:
            w3: Web3 instance
            executor_address: Executor wallet address
        """
        self.w3 = w3
        self.executor_address = Web3.to_checksum_address(executor_address)
        
        # Internal nonce tracking
        self.current_nonce = None
        self.pending_nonces = set()
        self.lock = asyncio.Lock()
        
        # Initialize nonce from blockchain
        self._sync_nonce()
        
        logger.info(f"Nonce Manager initialized with nonce: {self.current_nonce}")
    
    def _sync_nonce(self):
        """Sync nonce with blockchain"""
        try:
            # Get transaction count (confirmed + pending)
            nonce = self.w3.eth.get_transaction_count(
                self.executor_address,
                'pending'  # Include pending transactions
            )
            self.current_nonce = nonce
            logger.debug(f"Nonce synced: {nonce}")
        except Exception as e:
            logger.error(f"Error syncing nonce: {e}")
            self.current_nonce = 0
    
    async def get_nonce(self) -> int:
        """
        Get next available nonce
        
        Returns:
            Next nonce to use
        """
        async with self.lock:
            if self.current_nonce is None:
                self._sync_nonce()
            
            nonce = self.current_nonce
            self.current_nonce += 1
            self.pending_nonces.add(nonce)
            
            logger.debug(f"Allocated nonce: {nonce}")
            return nonce
    
    async def confirm_nonce(self, nonce: int):
        """
        Mark a nonce as confirmed
        
        Args:
            nonce: Nonce that was confirmed
        """
        async with self.lock:
            if nonce in self.pending_nonces:
                self.pending_nonces.discard(nonce)
                logger.debug(f"Confirmed nonce: {nonce}")
    
    async def reset_nonce(self):
        """Reset nonce from blockchain (used after stuck transaction)"""
        async with self.lock:
            self._sync_nonce()
            self.pending_nonces.clear()
            logger.warning(f"Nonce reset to: {self.current_nonce}")
    
    async def get_pending_count(self) -> int:
        """Get count of pending transactions"""
        return len(self.pending_nonces)
    
    async def cancel_transaction(self, nonce: int, gas_price: int) -> Dict:
        """
        Cancel a stuck transaction by sending 0-value tx with higher gas
        
        Args:
            nonce: Nonce of stuck transaction
            gas_price: New gas price (should be 12.5% higher than original)
            
        Returns:
            Cancellation transaction dict
        """
        try:
            # Create 0-value transaction with same nonce
            cancel_tx = {
                'from': self.executor_address,
                'to': self.executor_address,  # Send to self
                'value': 0,
                'gas': 21000,  # Minimum gas
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': 137
            }
            
            logger.warning(f"Created cancel transaction for nonce {nonce}")
            return cancel_tx
            
        except Exception as e:
            logger.error(f"Error creating cancel transaction: {e}")
            return {}
    
    async def speed_up_transaction(
        self,
        original_tx: Dict,
        gas_price_multiplier: float = 1.125
    ) -> Dict:
        """
        Speed up a pending transaction by resubmitting with higher gas
        
        Args:
            original_tx: Original transaction dict
            gas_price_multiplier: Gas price multiplier (default 12.5% increase)
            
        Returns:
            New transaction with higher gas
        """
        try:
            # Copy original transaction
            new_tx = original_tx.copy()
            
            # Increase gas price
            if 'gasPrice' in new_tx:
                new_tx['gasPrice'] = int(new_tx['gasPrice'] * gas_price_multiplier)
            
            if 'maxFeePerGas' in new_tx:
                new_tx['maxFeePerGas'] = int(new_tx['maxFeePerGas'] * gas_price_multiplier)
            
            if 'maxPriorityFeePerGas' in new_tx:
                new_tx['maxPriorityFeePerGas'] = int(new_tx['maxPriorityFeePerGas'] * gas_price_multiplier)
            
            logger.info(f"Speed-up transaction for nonce {new_tx.get('nonce')}")
            return new_tx
            
        except Exception as e:
            logger.error(f"Error speeding up transaction: {e}")
            return {}
    
    async def check_stuck_transactions(self, max_pending_blocks: int = 10) -> list:
        """
        Check for stuck transactions
        
        Args:
            max_pending_blocks: Maximum blocks a tx can be pending
            
        Returns:
            List of stuck transaction nonces
        """
        stuck_nonces = []
        
        try:
            current_block = self.w3.eth.block_number
            
            for nonce in self.pending_nonces:
                # Check if transaction exists in mempool
                try:
                    tx = self.w3.eth.get_transaction_by_block(nonce)
                    if tx and (current_block - tx['blockNumber']) > max_pending_blocks:
                        stuck_nonces.append(nonce)
                except Exception:
                    # Transaction not found - likely stuck
                    stuck_nonces.append(nonce)
            
            if stuck_nonces:
                logger.warning(f"Found {len(stuck_nonces)} stuck transactions")
            
            return stuck_nonces
            
        except Exception as e:
            logger.error(f"Error checking stuck transactions: {e}")
            return []
    
    def get_current_nonce(self) -> int:
        """Get current nonce (without incrementing)"""
        if self.current_nonce is None:
            self._sync_nonce()
        return self.current_nonce
    
    async def force_sync(self):
        """Force sync nonce with blockchain (use sparingly)"""
        async with self.lock:
            self._sync_nonce()
            logger.info(f"Force synced nonce: {self.current_nonce}")