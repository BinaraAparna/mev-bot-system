"""
System Check Script
Verifies all configurations and connections before running bot
"""

import os
import sys
import json
from web3 import Web3
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def check_environment_variables():
    """Check if all required environment variables are set"""
    logger.info("Checking environment variables...")
    
    required_vars = [
        'EXECUTOR_PRIVATE_KEY',
        'ADMIN_PRIVATE_KEY',
        'EXECUTOR_ADDRESS',
        'ADMIN_ADDRESS',
        'ALCHEMY_API_KEY',
        'ALERT_EMAIL'
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        return False
    
    logger.success("✓ All environment variables set")
    return True


def check_rpc_connections():
    """Check RPC endpoint connections"""
    logger.info("Checking RPC connections...")
    
    rpcs = {
        'Alchemy': os.getenv('ALCHEMY_RPC_URL'),
        'QuickNode': os.getenv('QUICKNODE_RPC_URL'),
        'Infura': os.getenv('INFURA_RPC_URL')
    }
    
    connected = 0
    for name, url in rpcs.items():
        if not url:
            logger.warning(f"  {name}: Not configured")
            continue
        
        try:
            w3 = Web3(Web3.HTTPProvider(url))
            if w3.is_connected():
                block = w3.eth.block_number
                logger.success(f"  ✓ {name}: Connected (Block: {block})")
                connected += 1
            else:
                logger.error(f"  ✗ {name}: Connection failed")
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")
    
    if connected == 0:
        logger.error("No RPC connections available!")
        return False
    
    logger.success(f"✓ {connected}/{len(rpcs)} RPC endpoints connected")
    return True


def check_wallet_balances():
    """Check wallet balances"""
    logger.info("Checking wallet balances...")
    
    rpc_url = os.getenv('ALCHEMY_RPC_URL')
    if not rpc_url:
        logger.warning("No RPC URL - skipping balance check")
        return True
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    executor_addr = os.getenv('EXECUTOR_ADDRESS')
    admin_addr = os.getenv('ADMIN_ADDRESS')
    
    if executor_addr:
        try:
            balance = w3.eth.get_balance(executor_addr)
            balance_matic = w3.from_wei(balance, 'ether')
            
            logger.info(f"  Executor: {balance_matic:.4f} MATIC")
            
            if balance_matic < 0.1:
                logger.warning("  ⚠ Executor balance low (need at least 0.1 MATIC)")
            else:
                logger.success("  ✓ Executor balance sufficient")
        except Exception as e:
            logger.error(f"  Error checking executor balance: {e}")
    
    if admin_addr:
        try:
            balance = w3.eth.get_balance(admin_addr)
            balance_matic = w3.from_wei(balance, 'ether')
            
            logger.info(f"  Admin: {balance_matic:.4f} MATIC")
        except Exception as e:
            logger.error(f"  Error checking admin balance: {e}")
    
    return True


def check_contract_deployment():
    """Check if smart contract is deployed"""
    logger.info("Checking smart contract deployment...")
    
    contract_address = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')
    
    if not contract_address:
        logger.warning("  Contract not deployed yet")
        logger.info("  Run: python scripts/deploy_contract.py")
        return False
    
    rpc_url = os.getenv('ALCHEMY_RPC_URL')
    if not rpc_url:
        return True
    
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        code = w3.eth.get_code(contract_address)
        
        if code == b'' or code == '0x':
            logger.error(f"  ✗ No contract at {contract_address}")
            return False
        
        logger.success(f"  ✓ Contract deployed at {contract_address}")
        return True
    except Exception as e:
        logger.error(f"  Error checking contract: {e}")
        return False


def check_configuration_files():
    """Check if all configuration files exist"""
    logger.info("Checking configuration files...")
    
    required_files = [
        'config/bot_config.json',
        'config/dex_config.json',
        'config/token_config.json',
        'config/rpc_config.json'
    ]
    
    missing = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing.append(file_path)
        else:
            # Try to load JSON
            try:
                with open(file_path, 'r') as f:
                    json.load(f)
                logger.success(f"  ✓ {file_path}")
            except Exception as e:
                logger.error(f"  ✗ {file_path}: {e}")
                missing.append(file_path)
    
    if missing:
        logger.error(f"Missing/invalid config files: {', '.join(missing)}")
        return False
    
    logger.success("✓ All configuration files valid")
    return True


def check_directories():
    """Check if required directories exist"""
    logger.info("Checking directories...")
    
    required_dirs = [
        'data/cache',
        'data/logs',
        'data/historical',
        'ml/models'
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"  Created: {dir_path}")
        else:
            logger.success(f"  ✓ {dir_path}")
    
    return True


def check_ml_models():
    """Check ML model files"""
    logger.info("Checking ML models...")
    
    model_files = [
        'data/historical/warmup_data.npz',
        'ml/models/price_predictor.joblib',
        'ml/models/price_scaler.joblib'
    ]
    
    missing = []
    for file_path in model_files:
        if not os.path.exists(file_path):
            missing.append(file_path)
    
    if 'warmup_data.npz' in str(missing):
        logger.warning("  ML warmup data not found")
        logger.info("  Run: python scripts/generate_warmup_data.py")
    
    if len(missing) > 1:
        logger.warning("  ML models not trained yet (will train on first run)")
    else:
        logger.success("  ✓ ML models ready")
    
    return True


def check_smtp_configuration():
    """Check SMTP configuration for alerts"""
    logger.info("Checking SMTP configuration...")
    
    smtp_user = os.getenv('SMTP_USERNAME')
    smtp_pass = os.getenv('SMTP_APP_PASSWORD')
    
    if not smtp_user or not smtp_pass:
        logger.warning("  SMTP not configured - alerts disabled")
        logger.info("  To enable: Set SMTP_USERNAME and SMTP_APP_PASSWORD in .env")
        return True
    
    logger.success("  ✓ SMTP configured")
    return True


def main():
    """Run all system checks"""
    logger.info("=" * 70)
    logger.info("MEV Bot System Check")
    logger.info("=" * 70)
    
    checks = [
        ("Environment Variables", check_environment_variables),
        ("Configuration Files", check_configuration_files),
        ("Directories", check_directories),
        ("RPC Connections", check_rpc_connections),
        ("Wallet Balances", check_wallet_balances),
        ("Contract Deployment", check_contract_deployment),
        ("ML Models", check_ml_models),
        ("SMTP Configuration", check_smtp_configuration)
    ]
    
    results = []
    
    for name, check_func in checks:
        logger.info("")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Error in {name}: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("Summary")
    logger.info("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"  {status}: {name}")
    
    logger.info("")
    logger.info(f"Total: {passed}/{total} checks passed")
    
    if passed == total:
        logger.success("=" * 70)
        logger.success("✅ System ready to run!")
        logger.success("=" * 70)
        logger.info("Start bot: python main.py")
        return 0
    else:
        logger.error("=" * 70)
        logger.error("❌ System not ready - fix issues above")
        logger.error("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())