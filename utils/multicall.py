"""
Multicall Utility
Batch multiple contract calls into single RPC request
CRITICAL for reducing RPC calls and saving CU (Compute Units)
"""

from typing import List, Dict, Any, Optional
from web3 import Web3
from eth_abi import encode, decode
from loguru import logger


class Multicall:
    """
    Multicall aggregator for batching contract calls
    Reduces RPC calls by 10-100x
    """
    
    # Multicall3 contract (deployed on Polygon)
    MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
    
    def __init__(self, w3: Web3, chunk_size: int = 50):
        """
        Initialize Multicall
        
        Args:
            w3: Web3 instance
            chunk_size: Max calls per multicall (optimize for free tier)
        """
        self.w3 = w3
        self.chunk_size = chunk_size
        
        # Multicall3 contract
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.MULTICALL3_ADDRESS),
            abi=self._get_multicall3_abi()
        )
        
        logger.info(f"Multicall initialized with chunk size: {chunk_size}")
    
    async def aggregate(
        self,
        calls: List[Dict[str, Any]],
        allow_failure: bool = True
    ) -> List[Any]:
        """
        Execute multiple contract calls in a single transaction
        
        Args:
            calls: List of call dicts with 'target' and 'call_data'
            allow_failure: If True, failed calls return None instead of reverting
            
        Returns:
            List of decoded results
        """
        try:
            if not calls:
                return []
            
            # Split into chunks to avoid gas limit
            chunks = [
                calls[i:i + self.chunk_size]
                for i in range(0, len(calls), self.chunk_size)
            ]
            
            all_results = []
            
            for chunk in chunks:
                chunk_results = await self._execute_chunk(chunk, allow_failure)
                all_results.extend(chunk_results)
            
            return all_results
            
        except Exception as e:
            logger.error(f"Error in multicall aggregate: {e}")
            return [None] * len(calls)
    
    async def _execute_chunk(
        self,
        calls: List[Dict[str, Any]],
        allow_failure: bool
    ) -> List[Any]:
        """
        Execute a chunk of calls
        
        Args:
            calls: List of calls
            allow_failure: Allow individual call failures
            
        Returns:
            List of results
        """
        try:
            # Prepare multicall3 format
            multicall_calls = [
                {
                    'target': Web3.to_checksum_address(call['target']),
                    'allowFailure': allow_failure,
                    'callData': call['call_data']
                }
                for call in calls
            ]
            
            # Call multicall3.aggregate3
            results = self.contract.functions.aggregate3(multicall_calls).call()
            
            # Decode results
            decoded_results = []
            for i, result in enumerate(results):
                success = result[0]
                return_data = result[1]
                
                if success and return_data:
                    decoded_results.append(return_data)
                else:
                    decoded_results.append(None)
            
            return decoded_results
            
        except Exception as e:
            logger.error(f"Error executing multicall chunk: {e}")
            return [None] * len(calls)
    
    async def get_eth_balance_batch(
        self,
        addresses: List[str]
    ) -> Dict[str, int]:
        """
        Get ETH/MATIC balances for multiple addresses
        
        Args:
            addresses: List of addresses
            
        Returns:
            Dict mapping address to balance (wei)
        """
        try:
            # Use multicall3's getEthBalance
            calls = [
                {
                    'target': self.MULTICALL3_ADDRESS,
                    'call_data': self.contract.encodeABI(
                        fn_name='getEthBalance',
                        args=[Web3.to_checksum_address(addr)]
                    )
                }
                for addr in addresses
            ]
            
            results = await self.aggregate(calls)
            
            # Decode balances
            balances = {}
            for i, addr in enumerate(addresses):
                if results[i]:
                    balance = int.from_bytes(results[i], byteorder='big')
                    balances[addr] = balance
                else:
                    balances[addr] = 0
            
            return balances
            
        except Exception as e:
            logger.error(f"Error getting batch balances: {e}")
            return {addr: 0 for addr in addresses}
    
    async def get_token_balances_batch(
        self,
        token_addresses: List[str],
        holder_address: str
    ) -> Dict[str, int]:
        """
        Get ERC20 token balances for multiple tokens
        
        Args:
            token_addresses: List of token addresses
            holder_address: Address holding tokens
            
        Returns:
            Dict mapping token address to balance
        """
        try:
            # ERC20 balanceOf function signature
            balance_of_sig = Web3.keccak(text='balanceOf(address)')[:4]
            
            calls = []
            for token_addr in token_addresses:
                # Encode balanceOf call
                call_data = balance_of_sig + encode(
                    ['address'],
                    [Web3.to_checksum_address(holder_address)]
                )
                
                calls.append({
                    'target': token_addr,
                    'call_data': call_data
                })
            
            results = await self.aggregate(calls)
            
            # Decode balances
            balances = {}
            for i, token_addr in enumerate(token_addresses):
                if results[i]:
                    balance = int.from_bytes(results[i], byteorder='big')
                    balances[token_addr] = balance
                else:
                    balances[token_addr] = 0
            
            return balances
            
        except Exception as e:
            logger.error(f"Error getting token balances: {e}")
            return {addr: 0 for addr in token_addresses}
    
    async def get_pair_reserves_batch(
        self,
        pair_addresses: List[str]
    ) -> Dict[str, tuple]:
        """
        Get reserves for multiple Uniswap V2 pairs
        
        Args:
            pair_addresses: List of pair addresses
            
        Returns:
            Dict mapping pair address to (reserve0, reserve1, timestamp)
        """
        try:
            # getReserves() function signature
            get_reserves_sig = Web3.keccak(text='getReserves()')[:4]
            
            calls = [
                {
                    'target': pair_addr,
                    'call_data': get_reserves_sig
                }
                for pair_addr in pair_addresses
            ]
            
            results = await self.aggregate(calls)
            
            # Decode reserves
            reserves = {}
            for i, pair_addr in enumerate(pair_addresses):
                if results[i] and len(results[i]) >= 96:
                    # Decode (uint112, uint112, uint32)
                    reserve0 = int.from_bytes(results[i][:32], byteorder='big')
                    reserve1 = int.from_bytes(results[i][32:64], byteorder='big')
                    timestamp = int.from_bytes(results[i][64:96], byteorder='big')
                    
                    reserves[pair_addr] = (reserve0, reserve1, timestamp)
                else:
                    reserves[pair_addr] = (0, 0, 0)
            
            return reserves
            
        except Exception as e:
            logger.error(f"Error getting pair reserves: {e}")
            return {addr: (0, 0, 0) for addr in pair_addresses}
    
    async def get_amounts_out_batch(
        self,
        router_address: str,
        amount_in: int,
        paths: List[List[str]]
    ) -> List[List[int]]:
        """
        Get amounts out for multiple swap paths
        
        Args:
            router_address: Router address
            amount_in: Input amount
            paths: List of token paths
            
        Returns:
            List of amounts out for each path
        """
        try:
            # getAmountsOut function signature
            get_amounts_sig = Web3.keccak(text='getAmountsOut(uint256,address[])')[:4]
            
            calls = []
            for path in paths:
                # Encode call
                call_data = get_amounts_sig + encode(
                    ['uint256', 'address[]'],
                    [amount_in, [Web3.to_checksum_address(addr) for addr in path]]
                )
                
                calls.append({
                    'target': router_address,
                    'call_data': call_data
                })
            
            results = await self.aggregate(calls)
            
            # Decode amounts
            amounts_list = []
            for result in results:
                if result:
                    # Decode uint256[]
                    amounts = decode(['uint256[]'], result)[0]
                    amounts_list.append(list(amounts))
                else:
                    amounts_list.append([])
            
            return amounts_list
            
        except Exception as e:
            logger.error(f"Error getting amounts out batch: {e}")
            return [[] for _ in paths]
    
    def _get_multicall3_abi(self) -> List[Dict]:
        """Get Multicall3 ABI"""
        return [
            {
                "inputs": [
                    {
                        "components": [
                            {"name": "target", "type": "address"},
                            {"name": "allowFailure", "type": "bool"},
                            {"name": "callData", "type": "bytes"}
                        ],
                        "name": "calls",
                        "type": "tuple[]"
                    }
                ],
                "name": "aggregate3",
                "outputs": [
                    {
                        "components": [
                            {"name": "success", "type": "bool"},
                            {"name": "returnData", "type": "bytes"}
                        ],
                        "name": "returnData",
                        "type": "tuple[]"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"name": "addr", "type": "address"}],
                "name": "getEthBalance",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]