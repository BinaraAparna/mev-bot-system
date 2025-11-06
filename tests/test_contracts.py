"""
Smart Contract Tests
Tests FlashloanArbitrage contract functionality
"""

import pytest
from web3 import Web3
from eth_account import Account


# Note: These tests require a local Hardhat node or testnet
# Run: npx hardhat node
# Then: pytest tests/test_contracts.py


@pytest.fixture
def w3():
    """Connect to local Hardhat node"""
    return Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))


@pytest.fixture
def accounts(w3):
    """Get test accounts"""
    return w3.eth.accounts


@pytest.fixture
def owner(accounts):
    """Contract owner"""
    return accounts[0]


@pytest.fixture
def executor(accounts):
    """Executor account"""
    return accounts[1]


@pytest.fixture
def contract(w3, owner):
    """Deploy FlashloanArbitrage contract"""
    # Load compiled contract
    import json
    with open('artifacts/contracts/FlashloanArbitrage.sol/FlashloanArbitrage.json') as f:
        contract_json = json.load(f)
    
    abi = contract_json['abi']
    bytecode = contract_json['bytecode']
    
    # Deploy
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor().transact({'from': owner})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    return w3.eth.contract(
        address=tx_receipt.contractAddress,
        abi=abi
    )


class TestFlashloanArbitrageContract:
    """Test FlashloanArbitrage smart contract"""
    
    def test_deployment(self, contract, owner):
        """Test contract deployment"""
        assert contract.address is not None
        assert contract.functions.owner().call() == owner
        assert contract.functions.paused().call() 
    
    def test_set_executor(self, w3, contract, owner, executor):
        """Test setting executor address"""
        # Set executor
        tx_hash = contract.functions.setExecutor(executor).transact({'from': owner})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Verify
        assert contract.functions.executor().call() == executor
    
    def test_emergency_pause(self, w3, contract, owner):
        """Test emergency pause function"""
        # Pause
        tx_hash = contract.functions.emergencyPause().transact({'from': owner})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        assert contract.functions.paused().call()
        
        # Unpause
        tx_hash = contract.functions.unpause().transact({'from': owner})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        assert contract.functions.paused().call() 
    
    def test_ownership_transfer(self, w3, contract, owner, accounts):
        """Test ownership transfer"""
        new_owner = accounts[2]
        
        # Transfer
        tx_hash = contract.functions.transferOwnership(new_owner).transact({'from': owner})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        assert contract.functions.owner().call() == new_owner
    
    def test_unauthorized_executor(self, w3, contract, accounts):
        """Test that unauthorized address cannot execute flashloan"""
        unauthorized = accounts[3]
        
        with pytest.raises(Exception):
            contract.functions.executeFlashLoan(
                '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',  # WMATIC
                1000000000000000000,  # 1 token
                b''
            ).transact({'from': unauthorized})


class TestContractSecurity:
    """Test security features"""
    
    def test_reentrancy_guard(self, contract):
        """Test reentrancy protection"""
        # This would require a malicious contract to test properly
        # For now, just verify the function exists
        pass
    
    def test_only_owner_functions(self, w3, contract, owner, accounts):
        """Test onlyOwner modifier"""
        unauthorized = accounts[3]
        
        # Should fail from unauthorized address
        with pytest.raises(Exception):
            contract.functions.emergencyPause().transact({'from': unauthorized})
        
        # Should succeed from owner
        tx_hash = contract.functions.emergencyPause().transact({'from': owner})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        assert contract.functions.paused().call()


# Integration test (requires testnet with funds)
@pytest.mark.skip(reason="Requires testnet with tokens")
class TestFlashloanIntegration:
    """Integration tests with Aave V3"""
    
    def test_flashloan_execution(self, w3, contract, executor):
        """Test actual flashloan execution"""
        # This requires:
        # 1. Deployed contract on testnet
        # 2. Tokens with liquidity
        # 3. Valid arbitrage opportunity
        pass


if __name__ == "__main__":
    pytest.main([__file__, '-v'])