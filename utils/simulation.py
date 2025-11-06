"""
Transaction Simulator
Simulates transactions before sending to avoid gas waste
"""

from typing import Dict, Optional
from web3 import Web3
from loguru import logger


class TransactionSimulator:
    """
    Simulates transactions to predict success/failure
    Uses eth_call for free simulation
    """
    
    def __init__(self, w3: Web3):
        """
        Initialize Transaction Simulator
        
        Args:
            w3: Web3 instance
        """
        self.w3 = w3
        
        logger.info("Transaction Simulator initialized")
    
    async def simulate_transaction(self, tx: Dict) -> bool:
        """
        Simulate transaction execution
        
        Args:
            tx: Transaction dict
            
        Returns:
            True if simulation succeeds
        """
        try:
            # Use eth_call to simulate
            result = self.w3.eth.call(tx)
            
            # If no exception, simulation succeeded
            logger.debug(f"Simulation successful: {result.hex()[:20]}...")
            return True
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check for common revert reasons
            if 'revert' in error_str:
                logger.warning(f"Simulation reverted: {e}")
                return False
            elif 'insufficient' in error_str:
                logger.warning(f"Insufficient balance/allowance: {e}")
                return False
            elif 'execution reverted' in error_str:
                logger.warning(f"Execution reverted: {e}")
                return False
            else:
                # Unknown error - log but allow execution
                logger.warning(f"Simulation error (allowing execution): {e}")
                return True
    
    async def simulate_with_state_override(
        self,
        tx: Dict,
        state_override: Dict
    ) -> bool:
        """
        Simulate with state override (requires archive node)
        
        Args:
            tx: Transaction dict
            state_override: State modifications
            
        Returns:
            True if simulation succeeds
        """
        try:
            # This requires special RPC support
            # Most free tiers don't support this
            logger.debug("State override simulation not available on free tier")
            return True  # Allow execution
            
        except Exception as e:
            logger.error(f"State override simulation error: {e}")
            return True
    
    async def estimate_gas_accurate(self, tx: Dict) -> Optional[int]:
        """
        Estimate gas more accurately
        
        Args:
            tx: Transaction dict
            
        Returns:
            Gas estimate or None
        """
        try:
            gas_estimate = self.w3.eth.estimate_gas(tx)
            
            # Add 10% buffer
            buffered_gas = int(gas_estimate * 1.10)
            
            logger.debug(f"Gas estimate: {gas_estimate} -> {buffered_gas} (buffered)")
            
            return buffered_gas
            
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            return None
    
    async def check_profitability_after_simulation(
        self,
        tx: Dict,
        expected_profit_usd: float
    ) -> bool:
        """
        Check if transaction is still profitable after gas estimation
        
        Args:
            tx: Transaction dict
            expected_profit_usd: Expected profit
            
        Returns:
            True if still profitable
        """
        try:
            # Estimate actual gas
            gas_estimate = await self.estimate_gas_accurate(tx)
            
            if gas_estimate is None:
                # Can't estimate - assume original is correct
                return True
            
            # Get gas price from tx
            gas_price = tx.get('gasPrice', tx.get('maxFeePerGas', 0))
            
            if gas_price == 0:
                return True
            
            # Calculate gas cost
            gas_cost_wei = gas_estimate * gas_price
            gas_cost_matic = self.w3.from_wei(gas_cost_wei, 'ether')
            gas_cost_usd = float(gas_cost_matic) * 0.80  # MATIC price
            
            # Check profitability
            net_profit = expected_profit_usd - gas_cost_usd
            
            if net_profit <= 0:
                logger.warning(
                    f"Transaction no longer profitable: "
                    f"profit ${expected_profit_usd:.2f}, gas ${gas_cost_usd:.2f}"
                )
                return False
            
            logger.debug(f"Transaction profitable: net ${net_profit:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking profitability: {e}")
            return True  # Allow execution on error
    
    async def simulate_flashloan(
        self,
        contract_address: str,
        asset: str,
        amount: int,
        params: bytes
    ) -> bool:
        """
        Simulate flashloan execution
        
        Args:
            contract_address: Flashloan contract
            asset: Asset to borrow
            amount: Amount to borrow
            params: Encoded parameters
            
        Returns:
            True if simulation succeeds
        """
        try:
            # Build call transaction
            tx = {
                'to': Web3.to_checksum_address(contract_address),
                'data': self._encode_flashloan_call(asset, amount, params)
            }
            
            return await self.simulate_transaction(tx)
            
        except Exception as e:
            logger.error(f"Flashloan simulation error: {e}")
            return False
    
    def _encode_flashloan_call(self, asset: str, amount: int, params: bytes) -> str:
        """Encode flashloan function call"""
        # executeFlashLoan(address asset, uint256 amount, bytes params)
        function_sig = Web3.keccak(text='executeFlashLoan(address,uint256,bytes)')[:4]
        
        from eth_abi import encode
        encoded_params = encode(
            ['address', 'uint256', 'bytes'],
            [Web3.to_checksum_address(asset), amount, params]
        )
        
        return function_sig.hex() + encoded_params.hex()