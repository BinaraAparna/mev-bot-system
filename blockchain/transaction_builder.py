"""
Transaction Builder
Constructs transactions for different arbitrage strategies
"""

from typing import Dict, List, Optional
from web3 import Web3
from eth_abi import encode
from loguru import logger


class TransactionBuilder:
    """
    Builds transactions for various MEV strategies
    """
    
    def __init__(self, w3: Web3, wallet_manager):
        """
        Initialize Transaction Builder
        
        Args:
            w3: Web3 instance
            wallet_manager: Wallet manager for addresses
        """
        self.w3 = w3
        self.wallet_manager = wallet_manager
    
    async def build_arbitrage_tx(
        self,
        opportunity: Dict,
        gas_price: int,
        tip: int
    ) -> Dict:
        """
        Build transaction for direct arbitrage
        
        Args:
            opportunity: Arbitrage opportunity data
            gas_price: Gas price in wei
            tip: Priority fee (tip) in wei
            
        Returns:
            Transaction dict
        """
        try:
            # Extract parameters
            data = opportunity['data']
            token_a = data['pair'][0]
            token_b = data['pair'][1]
            buy_dex = data['buy_dex']
            sell_dex = data['sell_dex']
            #trade_size = data['trade_size_usd'] # Not used in encoding
            
            # Encode arbitrage parameters
            # Strategy type: 1 = Direct arbitrage
            params = self._encode_arbitrage_params(
                strategy_type=1,
                path=[token_a, token_b, token_a],
                routers=[buy_dex, sell_dex],
                amounts_out_min=[0, 0]  # Will be calculated
            )
            
            # Build transaction
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': buy_dex,  # First DEX router
                'value': 0,
                'gas': 500000,
                'maxFeePerGas': gas_price + tip,
                'maxPriorityFeePerGas': tip,
                'data': params,
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building arbitrage transaction: {e}")
            return {}
    
    async def build_triangular_tx(
        self,
        opportunity: Dict,
        gas_price: int,
        tip: int
    ) -> Dict:
        """
        Build transaction for triangular arbitrage
        
        Args:
            opportunity: Triangular arbitrage opportunity
            gas_price: Gas price in wei
            tip: Priority fee in wei
            
        Returns:
            Transaction dict
        """
        try:
            data = opportunity['data']
            path = data['path']  # [A, B, C, A]
            dex_config = data['dex_config']
            # trade_size = data['trade_size_usd']  # Not used in encoding
            
            # Encode parameters
            # Strategy type: 2 = Triangular arbitrage
            params = self._encode_arbitrage_params(
                strategy_type=2,
                path=path,
                routers=[dex_config['router']] * 3,  # Same DEX for all swaps
                amounts_out_min=[0, 0, 0]
            )
            
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': dex_config['router'],
                'value': 0,
                'gas': 450000,
                'maxFeePerGas': gas_price + tip,
                'maxPriorityFeePerGas': tip,
                'data': params,
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building triangular transaction: {e}")
            return {}
    
    async def build_liquidation_tx(
        self,
        opportunity: Dict,
        gas_price: int,
        tip: int
    ) -> Dict:
        """
        Build transaction for liquidation
        
        Args:
            opportunity: Liquidation opportunity
            gas_price: Gas price in wei
            tip: Priority fee in wei
            
        Returns:
            Transaction dict
        """
        try:
            data = opportunity['data']
            
            # Encode liquidation parameters
            # Strategy type: 3 = Liquidation
            params = encode(
                ['uint8', 'address', 'address', 'address', 'uint256'],
                [
                    3,  # Strategy type
                    data['collateral_asset'],
                    data['debt_asset'],
                    data['user_address'],
                    int(data['debt_to_cover'] * 10**18)
                ]
            )
            
            # Aave Pool address
            aave_pool = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
            
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': aave_pool,
                'value': 0,
                'gas': 350000,
                'maxFeePerGas': gas_price + tip,
                'maxPriorityFeePerGas': tip,
                'data': params,
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building liquidation transaction: {e}")
            return {}
    
    async def build_sandwich_tx(
        self,
        opportunity: Dict,
        gas_price: int,
        tip: int
    ) -> Dict:
        """
        Build transaction for sandwich attack (front-run)
        
        Args:
            opportunity: Sandwich opportunity
            gas_price: Gas price in wei
            tip: Priority fee in wei
            
        Returns:
            Transaction dict for front-run
        """
        try:
            front_run_params = opportunity['front_run_params']
            
            # Build front-run transaction
            # This buys tokens before the victim
            router_address = opportunity['victim_swap_params']['router']
            
            # Encode swap parameters
            path = [
                Web3.to_checksum_address(front_run_params['token_in']),
                Web3.to_checksum_address(front_run_params['token_out'])
            ]
            
            # Router function: swapExactTokensForTokens
            function_sig = Web3.keccak(text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")[:4]
            
            params = encode(
                ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                [
                    front_run_params['amount_in'],
                    0,  # amountOutMin (accept any)
                    path,
                    self.wallet_manager.executor_address,
                    int(self.w3.eth.get_block('latest')['timestamp']) + 300
                ]
            )
            
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': router_address,
                'value': 0,
                'gas': 200000,
                'maxFeePerGas': gas_price + tip,
                'maxPriorityFeePerGas': tip,
                'data': function_sig.hex() + params.hex(),
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building sandwich transaction: {e}")
            return {}
    
    async def build_backrun_tx(
        self,
        opportunity: Dict,
        gas_price: int,
        tip: int
    ) -> Dict:
        """
        Build back-run transaction for sandwich attack
        
        Args:
            opportunity: Sandwich opportunity
            gas_price: Gas price in wei
            tip: Priority fee in wei
            
        Returns:
            Transaction dict for back-run
        """
        try:
            back_run_params = opportunity['back_run_params']
            router_address = opportunity['victim_swap_params']['router']
            
            # Reverse path (sell tokens)
            path = [
                Web3.to_checksum_address(back_run_params['token_in']),
                Web3.to_checksum_address(back_run_params['token_out'])
            ]
            
            function_sig = Web3.keccak(text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")[:4]
            
            params = encode(
                ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                [
                    int(back_run_params['amount_in']),
                    0,
                    path,
                    self.wallet_manager.executor_address,
                    int(self.w3.eth.get_block('latest')['timestamp']) + 300
                ]
            )
            
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': router_address,
                'value': 0,
                'gas': 200000,
                'maxFeePerGas': gas_price,
                'maxPriorityFeePerGas': int(tip * 0.5),  # Lower tip for back-run
                'data': function_sig.hex() + params.hex(),
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building backrun transaction: {e}")
            return {}
    
    def _encode_arbitrage_params(
        self,
        strategy_type: int,
        path: List[str],
        routers: List[str],
        amounts_out_min: List[int]
    ) -> bytes:
        """
        Encode arbitrage parameters for smart contract
        
        Args:
            strategy_type: 1=Direct, 2=Triangular, 3=Liquidation, 4=Sandwich
            path: Token addresses path
            routers: DEX router addresses
            amounts_out_min: Minimum output amounts
            
        Returns:
            Encoded bytes
        """
        # Convert addresses to checksummed format
        path_checksummed = [Web3.to_checksum_address(addr) for addr in path]
        routers_checksummed = [Web3.to_checksum_address(addr) for addr in routers]
        
        # Encode parameters
        encoded = encode(
            ['uint8', 'address[]', 'address[]', 'uint256[]'],
            [
                strategy_type,
                path_checksummed,
                routers_checksummed,
                amounts_out_min
            ]
        )
        
        return encoded
    
    async def build_approve_tx(
        self,
        token_address: str,
        spender_address: str,
        amount: int,
        gas_price: int
    ) -> Dict:
        """
        Build ERC20 approve transaction
        
        Args:
            token_address: Token to approve
            spender_address: Spender (router/contract)
            amount: Amount to approve
            gas_price: Gas price in wei
            
        Returns:
            Transaction dict
        """
        try:
            # ERC20 approve function signature
            function_sig = Web3.keccak(text="approve(address,uint256)")[:4]
            
            params = encode(
                ['address', 'uint256'],
                [Web3.to_checksum_address(spender_address), amount]
            )
            
            tx = {
                'from': self.wallet_manager.executor_address,
                'to': Web3.to_checksum_address(token_address),
                'value': 0,
                'gas': 50000,
                'gasPrice': gas_price,
                'data': function_sig.hex() + params.hex(),
                'chainId': 137
            }
            
            return tx
            
        except Exception as e:
            logger.error(f"Error building approve transaction: {e}")
            return {}