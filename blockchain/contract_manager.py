"""
Contract Manager
Handles all smart contract interactions
"""

import os
import json
from typing import Dict, List, Optional
from web3 import Web3
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class ContractManager:
    """
    Manages smart contract instances and interactions
    """
    
    def __init__(self, w3: Web3):
        """
        Initialize Contract Manager
        
        Args:
            w3: Web3 instance
        """
        self.w3 = w3
        
        # Load contract address from environment
        self.flashloan_contract_address = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')
        
        if not self.flashloan_contract_address:
            logger.warning("FLASHLOAN_CONTRACT_ADDRESS not set - contract interactions disabled")
            self.flashloan_contract = None
        else:
            # Load contract ABI and create instance
            self.flashloan_contract = self._load_flashloan_contract()
        
        logger.info("Contract Manager initialized")
    
    def _load_flashloan_contract(self):
        """Load FlashloanArbitrage contract instance"""
        try:
            # Load ABI from compiled artifacts
            abi_path = "artifacts/contracts/FlashloanArbitrage.sol/FlashloanArbitrage.json"
            
            if os.path.exists(abi_path):
                with open(abi_path, 'r') as f:
                    contract_json = json.load(f)
                    abi = contract_json['abi']
            else:
                # Use minimal ABI if artifacts not available
                abi = self._get_minimal_flashloan_abi()
            
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.flashloan_contract_address),
                abi=abi
            )
            
            logger.success(f"FlashloanArbitrage contract loaded at {self.flashloan_contract_address}")
            return contract
            
        except Exception as e:
            logger.error(f"Error loading FlashloanArbitrage contract: {e}")
            return None
    
    async def execute_flashloan(
        self,
        asset: str,
        amount: int,
        params: bytes,
        wallet_manager
    ) -> Optional[bytes]:
        """
        Execute flashloan arbitrage
        
        Args:
            asset: Token address to borrow
            amount: Amount to borrow (in wei)
            params: Encoded arbitrage parameters
            wallet_manager: Wallet manager for signing
            
        Returns:
            Transaction hash or None
        """
        try:
            if not self.flashloan_contract:
                logger.error("Flashloan contract not initialized")
                return None
            
            # Build transaction
            tx = self.flashloan_contract.functions.executeFlashLoan(
                Web3.to_checksum_address(asset),
                amount,
                params
            ).build_transaction({
                'from': wallet_manager.executor_address,
                'nonce': self.w3.eth.get_transaction_count(wallet_manager.executor_address),
                'gas': 800000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign and send
            signed_tx = wallet_manager.sign_transaction(tx, wallet='executor')
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Flashloan executed: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error executing flashloan: {e}")
            return None
    
    async def withdraw_profits(
        self,
        token_address: str,
        to_address: str,
        wallet_manager
    ) -> Optional[bytes]:
        """
        Withdraw accumulated profits from contract
        
        Args:
            token_address: Token to withdraw
            to_address: Recipient address (admin wallet)
            wallet_manager: Wallet manager for signing
            
        Returns:
            Transaction hash or None
        """
        try:
            if not self.flashloan_contract:
                logger.error("Flashloan contract not initialized")
                return None
            
            # Build transaction
            tx = self.flashloan_contract.functions.withdrawProfits(
                Web3.to_checksum_address(token_address),
                Web3.to_checksum_address(to_address)
            ).build_transaction({
                'from': wallet_manager.admin_address,
                'nonce': self.w3.eth.get_transaction_count(wallet_manager.admin_address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign with admin key
            signed_tx = wallet_manager.sign_transaction(tx, wallet='admin')
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.success(f"Profits withdrawn: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error withdrawing profits: {e}")
            return None
    
    async def emergency_pause(self, wallet_manager) -> Optional[bytes]:
        """
        Trigger emergency pause (kill switch)
        
        Args:
            wallet_manager: Wallet manager for signing
            
        Returns:
            Transaction hash or None
        """
        try:
            if not self.flashloan_contract:
                logger.error("Flashloan contract not initialized")
                return None
            
            tx = self.flashloan_contract.functions.emergencyPause().build_transaction({
                'from': wallet_manager.admin_address,
                'nonce': self.w3.eth.get_transaction_count(wallet_manager.admin_address),
                'gas': 50000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = wallet_manager.sign_transaction(tx, wallet='admin')
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.critical(f"Emergency pause activated: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error triggering emergency pause: {e}")
            return None
    
    async def set_executor(self, executor_address: str, wallet_manager) -> Optional[bytes]:
        """
        Set authorized executor address
        
        Args:
            executor_address: New executor address
            wallet_manager: Wallet manager for signing
            
        Returns:
            Transaction hash or None
        """
        try:
            if not self.flashloan_contract:
                return None
            
            tx = self.flashloan_contract.functions.setExecutor(
                Web3.to_checksum_address(executor_address)
            ).build_transaction({
                'from': wallet_manager.admin_address,
                'nonce': self.w3.eth.get_transaction_count(wallet_manager.admin_address),
                'gas': 50000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = wallet_manager.sign_transaction(tx, wallet='admin')
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Executor set: {tx_hash.hex()}")
            return tx_hash
            
        except Exception as e:
            logger.error(f"Error setting executor: {e}")
            return None
    
    def get_contract_balance(self, token_address: str) -> int:
        """
        Get contract's token balance
        
        Args:
            token_address: Token address
            
        Returns:
            Balance in wei
        """
        try:
            if not self.flashloan_contract:
                return 0
            
            # ERC20 balanceOf call
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=[{
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }]
            )
            
            balance = token_contract.functions.balanceOf(
                self.flashloan_contract.address
            ).call()
            
            return balance
            
        except Exception as e:
            logger.error(f"Error getting contract balance: {e}")
            return 0
    
    def is_contract_paused(self) -> bool:
        """Check if contract is paused"""
        try:
            if not self.flashloan_contract:
                return True
            
            return self.flashloan_contract.functions.paused().call()
            
        except Exception as e:
            logger.error(f"Error checking pause status: {e}")
            return True
    
    def _get_minimal_flashloan_abi(self) -> List[Dict]:
        """
        Get minimal ABI for FlashloanArbitrage contract
        Used when compiled artifacts are not available
        """
        return [
            {
                "inputs": [
                    {"name": "asset", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "params", "type": "bytes"}
                ],
                "name": "executeFlashLoan",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "token", "type": "address"},
                    {"name": "to", "type": "address"}
                ],
                "name": "withdrawProfits",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "emergencyPause",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "unpause",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [{"name": "executor", "type": "address"}],
                "name": "setExecutor",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "paused",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]