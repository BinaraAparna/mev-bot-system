"""
Smart Contract Deployment Script
Deploys FlashloanArbitrage contract to Polygon
"""

import os
import json
from web3 import Web3
from eth_account import Account
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def deploy_contract():
    """Deploy FlashloanArbitrage contract"""
    
    logger.info("Starting contract deployment...")
    
    # Load environment
    admin_private_key = os.getenv('ADMIN_PRIVATE_KEY')
    rpc_url = os.getenv('ALCHEMY_RPC_URL')
    
    if not admin_private_key or not rpc_url:
        logger.error("ADMIN_PRIVATE_KEY and ALCHEMY_RPC_URL must be set")
        return
    
    # Connect to network
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        logger.error("Failed to connect to network")
        return
    
    # Load account
    account = Account.from_key(admin_private_key)
    logger.info(f"Deploying from: {account.address}")
    
    # Check balance
    balance = w3.eth.get_balance(account.address)
    balance_matic = w3.from_wei(balance, 'ether')
    
    logger.info(f"Account balance: {balance_matic} MATIC")
    
    if balance_matic < 0.1:
        logger.error("Insufficient balance for deployment (need at least 0.1 MATIC)")
        return
    
    # Load compiled contract
    contract_path = "artifacts/contracts/FlashloanArbitrage.sol/FlashloanArbitrage.json"
    
    if not os.path.exists(contract_path):
        logger.error(f"Contract artifact not found: {contract_path}")
        logger.info("Run 'npx hardhat compile' first")
        return
    
    with open(contract_path, 'r') as f:
        contract_json = json.load(f)
    
    abi = contract_json['abi']
    bytecode = contract_json['bytecode']
    
    # Create contract instance
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Build deployment transaction
    logger.info("Building deployment transaction...")
    
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    
    # Estimate gas
    try:
        gas_estimate = Contract.constructor().estimate_gas({
            'from': account.address
        })
        gas_limit = int(gas_estimate * 1.2)  # 20% buffer
    except Exception as e:
        logger.warning(f"Gas estimation failed: {e}, using default")
        gas_limit = 3000000
    
    logger.info(f"Gas limit: {gas_limit}")
    logger.info(f"Gas price: {w3.from_wei(gas_price, 'gwei')} gwei")
    
    # Build transaction
    transaction = Contract.constructor().build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': gas_limit,
        'gasPrice': gas_price,
        'chainId': 137
    })
    
    # Estimate cost
    deployment_cost = w3.from_wei(gas_limit * gas_price, 'ether')
    logger.info(f"Estimated deployment cost: {deployment_cost} MATIC")
    
    # Confirm deployment
    confirm = input("\nProceed with deployment? (yes/no): ")
    
    if confirm.lower() != 'yes':
        logger.info("Deployment cancelled")
        return
    
    # Sign transaction
    logger.info("Signing transaction...")
    signed_tx = account.sign_transaction(transaction)
    
    # Send transaction
    logger.info("Sending deployment transaction...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    
    logger.info(f"Transaction sent: {tx_hash.hex()}")
    logger.info("Waiting for confirmation...")
    
    # Wait for receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    
    if receipt['status'] == 1:
        contract_address = receipt['contractAddress']
        
        logger.success("✅ Contract deployed successfully!")
        logger.success(f"Contract address: {contract_address}")
        logger.success(f"Transaction hash: {tx_hash.hex()}")
        logger.success(f"Gas used: {receipt['gasUsed']}")
        
        # Update .env file
        update_env_file(contract_address)
        
        # Set executor address
        set_executor(w3, contract_address, account)
        
    else:
        logger.error("❌ Deployment failed")
        logger.error(f"Transaction hash: {tx_hash.hex()}")


def update_env_file(contract_address: str):
    """Update .env file with contract address"""
    try:
        env_path = ".env"
        
        # Read current .env
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Update or add FLASHLOAN_CONTRACT_ADDRESS
        found = False
        for i, line in enumerate(lines):
            if line.startswith('FLASHLOAN_CONTRACT_ADDRESS='):
                lines[i] = f'FLASHLOAN_CONTRACT_ADDRESS={contract_address}\n'
                found = True
                break
        
        if not found:
            lines.append(f'\nFLASHLOAN_CONTRACT_ADDRESS={contract_address}\n')
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)
        
        logger.success("Updated .env file with contract address")
        
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")


def set_executor(w3: Web3, contract_address: str, admin_account):
    """Set executor address on contract"""
    try:
        executor_address = os.getenv('EXECUTOR_ADDRESS')
        
        if not executor_address:
            logger.warning("EXECUTOR_ADDRESS not set, skipping")
            return
        
        logger.info(f"Setting executor address: {executor_address}")
        
        # Load contract ABI
        with open("artifacts/contracts/FlashloanArbitrage.sol/FlashloanArbitrage.json", 'r') as f:
            contract_json = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_json['abi']
        )
        
        # Build setExecutor transaction
        tx = contract.functions.setExecutor(
            Web3.to_checksum_address(executor_address)
        ).build_transaction({
            'from': admin_account.address,
            'nonce': w3.eth.get_transaction_count(admin_account.address),
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 137
        })
        
        # Sign and send
        signed_tx = admin_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        logger.info(f"setExecutor transaction sent: {tx_hash.hex()}")
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt['status'] == 1:
            logger.success("Executor address set successfully")
        else:
            logger.error("setExecutor transaction failed")
        
    except Exception as e:
        logger.error(f"Error setting executor: {e}")


if __name__ == "__main__":
    deploy_contract()