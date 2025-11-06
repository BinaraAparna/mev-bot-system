"""
Wallet Manager
Handles dual wallet system (Executor + Admin) for security
"""

import os
from typing import Dict
from decimal import Decimal
from web3 import Web3
from eth_account import Account
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class WalletManager:
    """
    Manages two separate wallets for enhanced security:
    - Executor wallet: Daily operations (flashloans, gas)
    - Admin wallet: Profit withdrawal and critical functions
    """
    
    def __init__(self):
        """Initialize wallet manager"""
        # Load private keys from environment
        self.executor_private_key = os.getenv('EXECUTOR_PRIVATE_KEY')
        self.admin_private_key = os.getenv('ADMIN_PRIVATE_KEY')
        
        if not self.executor_private_key or not self.admin_private_key:
            raise ValueError("EXECUTOR_PRIVATE_KEY and ADMIN_PRIVATE_KEY must be set in .env")
        
        # Create account objects
        self.executor_account = Account.from_key(self.executor_private_key)
        self.admin_account = Account.from_key(self.admin_private_key)
        
        # Addresses
        self.executor_address = self.executor_account.address
        self.admin_address = self.admin_account.address
        
        # Buffer management
        self.target_buffer_usd = 50  # Keep $50 in executor wallet
        self.min_withdrawal_threshold_usd = 100  # Withdraw when profit > $100
        
        logger.info(f"Executor wallet: {self.executor_address}")
        logger.info(f"Admin wallet: {self.admin_address}")
    
    def sign_transaction(self, transaction: Dict, wallet: str = 'executor'):
        """
        Sign a transaction with the appropriate wallet
        
        Args:
            transaction: Transaction dict
            wallet: 'executor' or 'admin'
            
        Returns:
            Signed transaction
        """
        if wallet == 'executor':
            account = self.executor_account
        elif wallet == 'admin':
            account = self.admin_account
        else:
            raise ValueError(f"Invalid wallet type: {wallet}")
        
        try:
            signed_tx = account.sign_transaction(transaction)
            return signed_tx
        except Exception as e:
            logger.error(f"Error signing transaction: {e}")
            raise
    
    def get_executor_balance(self, w3: Web3, token_address: str = None) -> Decimal:
        """
        Get executor wallet balance
        
        Args:
            w3: Web3 instance
            token_address: ERC20 token address (None for native MATIC)
            
        Returns:
            Balance in token units
        """
        if token_address is None:
            # Get native MATIC balance
            balance_wei = w3.eth.get_balance(self.executor_address)
            balance = w3.from_wei(balance_wei, 'ether')
        else:
            # Get ERC20 token balance
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=[
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function"
                    }
                ]
            )
            balance = token_contract.functions.balanceOf(self.executor_address).call()
        
        return Decimal(str(balance))
    
    def get_admin_balance(self, w3: Web3, token_address: str = None) -> Decimal:
        """Get admin wallet balance"""
        if token_address is None:
            balance_wei = w3.eth.get_balance(self.admin_address)
            balance = w3.from_wei(balance_wei, 'ether')
        else:
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=[
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function"
                    }
                ]
            )
            balance = token_contract.functions.balanceOf(self.admin_address).call()
        
        return Decimal(str(balance))
    
    async def auto_withdraw_profits(
        self, 
        w3: Web3, 
        contract_manager, 
        token_addresses: list
    ) -> bool:
        """
        Automatically withdraw accumulated profits from contract to admin wallet
        
        Args:
            w3: Web3 instance
            contract_manager: ContractManager instance
            token_addresses: List of token addresses to withdraw
            
        Returns:
            True if successful
        """
        try:
            for token_address in token_addresses:
                # Get contract balance
                contract_balance = await self._get_contract_balance(
                    w3, 
                    contract_manager, 
                    token_address
                )
                
                if contract_balance <= 0:
                    continue
                
                # Estimate USD value (simplified)
                balance_usd = float(contract_balance)  # Placeholder
                
                if balance_usd >= self.min_withdrawal_threshold_usd:
                    logger.info(f"Withdrawing {contract_balance} tokens to admin wallet")
                    
                    # Call withdrawProfits on smart contract
                    tx_hash = await contract_manager.withdraw_profits(
                        token_address,
                        self.admin_address,
                        wallet='admin'  # Sign with admin key
                    )
                    
                    if tx_hash:
                        logger.success(f"Withdrawal successful: {tx_hash.hex()}")
                    else:
                        logger.error("Withdrawal failed")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error in auto_withdraw_profits: {e}")
            return False
    
    async def _get_contract_balance(self, w3, contract_manager, token_address):
        """Get token balance held in the arbitrage contract"""
        # This would query the FlashloanArbitrage contract's balance
        # Implementation in contract_manager
        return 0
    
    def ensure_executor_buffer(self, w3: Web3, current_balance_usd: float) -> bool:
        """
        Ensure executor wallet maintains minimum buffer for gas
        
        Args:
            w3: Web3 instance
            current_balance_usd: Current executor balance in USD
            
        Returns:
            True if buffer is sufficient
        """
        if current_balance_usd < self.target_buffer_usd * 0.5:
            logger.warning(
                f"Executor buffer low: ${current_balance_usd:.2f} "
                f"(target: ${self.target_buffer_usd})"
            )
            return False
        
        return True