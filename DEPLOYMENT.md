# 🚀 MEV Bot Deployment Guide

Complete step-by-step deployment guide for production.

## 📋 Pre-Deployment Checklist

### 1. Hardware Requirements
- **VPS/Server**: 2 CPU cores, 4GB RAM minimum
- **Storage**: 20GB free space
- **Network**: Stable internet, low latency to Polygon RPC
- **OS**: Ubuntu 20.04+ or similar Linux

### 2. Software Requirements
```bash
# Python 3.9+
python3 --version

# Node.js 16+
node --version

# Git
git --version
```

---

## 📦 Step 1: Project Setup

### Clone Repository
```bash
git clone <your-repo-url>
cd mev-bot-system
```

### Install Python Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install packages
pip install -r requirements.txt
```

### Install Node Dependencies
```bash
npm install
```

---

## 🔑 Step 2: Create Wallets

### Generate New Wallets (SECURE METHOD)

```python
# generate_wallets.py
from eth_account import Account
import secrets

# Generate Executor Wallet
executor_key = "0x" + secrets.token_hex(32)
executor_account = Account.from_key(executor_key)

print("=" * 70)
print("EXECUTOR WALLET")
print("=" * 70)
print(f"Private Key: {executor_key}")
print(f"Address: {executor_account.address}")
print()

# Generate Admin Wallet
admin_key = "0x" + secrets.token_hex(32)
admin_account = Account.from_key(admin_key)

print("=" * 70)
print("ADMIN WALLET")
print("=" * 70)
print(f"Private Key: {admin_key}")
print(f"Address: {admin_account.address}")
print()
print("⚠️  SAVE THESE KEYS SECURELY - NEVER SHARE!")
print("=" * 70)
```

**Run:**
```bash
python generate_wallets.py
```

**Save keys in password manager (KeePass, 1Password, etc.)**

---

## 🌐 Step 3: Get Free RPC API Keys

### Alchemy (Tier 1 - Primary)
1. Go to https://www.alchemy.com/
2. Sign up for free account
3. Create new app → Polygon Mainnet
4. Copy API Key
5. Free tier: 300M Compute Units/month

### QuickNode (Tier 2 - Secondary)
1. Go to https://www.quicknode.com/
2. Sign up for free account
3. Create endpoint → Polygon Mainnet
4. Copy endpoint URL
5. Free tier: 10M API credits

### Infura (Tier 3 - Buffer)
1. Go to https://infura.io/
2. Sign up for free account
3. Create project → Polygon Mainnet
4. Copy Project ID
5. Free tier: 100k requests/day

---

## 📧 Step 4: Setup Gmail SMTP (Alerts)

### Create App Password
1. Go to Google Account → Security
2. Enable 2-Factor Authentication
3. Go to App Passwords
4. Generate new app password for "Mail"
5. Save the 16-character password

---

## ⚙️ Step 5: Configure .env File

Create `.env` file:

```env
# ============================================
# WALLETS (FROM STEP 2)
# ============================================
EXECUTOR_PRIVATE_KEY=0xYOUR_EXECUTOR_PRIVATE_KEY
ADMIN_PRIVATE_KEY=0xYOUR_ADMIN_PRIVATE_KEY
EXECUTOR_ADDRESS=0xYOUR_EXECUTOR_ADDRESS
ADMIN_ADDRESS=0xYOUR_ADMIN_ADDRESS

# ============================================
# RPC ENDPOINTS (FROM STEP 3)
# ============================================
# Alchemy
ALCHEMY_API_KEY=your_alchemy_api_key_here
ALCHEMY_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}
ALCHEMY_WSS_URL=wss://polygon-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}

# QuickNode
QUICKNODE_API_KEY=your_quicknode_api_key_here
QUICKNODE_RPC_URL=https://your-endpoint.matic.quiknode.pro/${QUICKNODE_API_KEY}/
QUICKNODE_WSS_URL=wss://your-endpoint.matic.quiknode.pro/${QUICKNODE_API_KEY}/

# Infura
INFURA_API_KEY=your_infura_api_key_here
INFURA_RPC_URL=https://polygon-mainnet.infura.io/v3/${INFURA_API_KEY}
INFURA_WSS_URL=wss://polygon-mainnet.infura.io/ws/v3/${INFURA_API_KEY}

# Public (fallback)
POLYGON_PUBLIC_RPC=https://polygon-rpc.com

# ============================================
# ALERTS (FROM STEP 4)
# ============================================
ALERT_EMAIL=your_email@gmail.com
SMTP_USERNAME=your_gmail@gmail.com
SMTP_APP_PASSWORD=your_16_char_app_password

# SMTP Settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# ============================================
# MISC
# ============================================
DATABASE_PATH=./data/cache/mev_bot.db
LOG_LEVEL=INFO
LOG_FILE=./data/logs/bot.log
```

---

## 💰 Step 6: Fund Wallets

### Executor Wallet
Send **$20-30 worth of MATIC** to executor address.

**Where to buy MATIC:**
- Binance
- Coinbase
- Crypto.com

**Transfer to Polygon Network:**
1. Use bridge: https://wallet.polygon.technology/
2. Or withdraw directly to Polygon from exchange

### Admin Wallet
**Optional:** Can fund later. Profits will accumulate in contract first.

---

## 🏗️ Step 7: Deploy Smart Contract

### Compile Contract
```bash
npx hardhat compile
```

### Deploy to Polygon Mainnet
```bash
python scripts/deploy_contract.py
```

**Expected output:**
```
Deploying from: 0xYourAdminAddress
Account balance: 20.5 MATIC
Gas limit: 2500000
Estimated deployment cost: 0.05 MATIC

Proceed with deployment? (yes/no): yes

✅ Contract deployed successfully!
Contract address: 0x1234...5678
Transaction hash: 0xabcd...ef01
```

**Contract address is automatically saved to .env**

---

## 🤖 Step 8: Generate ML Training Data

```bash
python scripts/generate_warmup_data.py
```

Creates synthetic data for ML models to warm up.

---

## ✅ Step 9: System Check

Run pre-flight checks:

```bash
python scripts/check_system.py
```

**Should see:**
```
✓ PASS: Environment Variables
✓ PASS: Configuration Files
✓ PASS: RPC Connections
✓ PASS: Wallet Balances
✓ PASS: Contract Deployment
✓ PASS: ML Models

✅ System ready to run!
```

---

## 🚀 Step 10: Start Bot

### Test Run (Dry Run)
First, test without real trades:

```bash
# Edit config/bot_config.json
{
  "strategies": {
    "direct_arbitrage": {
      "enabled": false  // Disable all strategies first
    }
  }
}

python main.py
```

Check logs for errors.

### Production Run
Enable strategies:

```bash
# Edit config/bot_config.json
{
  "strategies": {
    "direct_arbitrage": {
      "enabled": true,
      "min_profit_usd": 10  // Start conservative
    },
    "triangular_arbitrage": {
      "enabled": true,
      "min_profit_usd": 15
    }
  }
}
```

Start bot:
```bash
python main.py
```

---

## 📊 Step 11: Monitor Bot

### View Live Logs
```bash
tail -f data/logs/bot.log
```

### Check Email Alerts
You should receive:
- System start notification
- Profit alerts
- Daily summaries

### Monitor RPC Usage
Check Alchemy/QuickNode dashboards for CU usage.

---

## 🛡️ Step 12: Security Hardening

### 1. Secure .env File
```bash
chmod 600 .env
```

### 2. Setup Firewall
```bash
sudo ufw allow 22/tcp
sudo ufw enable
```

### 3. Regular Backups
```bash
# Backup .env and keys
tar -czf backup.tar.gz .env data/
```

### 4. Monitor Wallet Balances
Set up alerts in your exchange for low balances.

---

## 🔄 Step 13: Profit Withdrawal

### Manual Withdrawal
```python
# withdraw_profits.py
from web3 import Web3
from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv()

w3 = Web3(Web3.HTTPProvider(os.getenv('ALCHEMY_RPC_URL')))
admin_key = os.getenv('ADMIN_PRIVATE_KEY')
contract_address = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')

# Load contract ABI
import json
with open('artifacts/contracts/FlashloanArbitrage.sol/FlashloanArbitrage.json') as f:
    abi = json.load(f)['abi']

contract = w3.eth.contract(address=contract_address, abi=abi)
admin_account = Account.from_key(admin_key)

# Withdraw USDC
usdc_address = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'

tx = contract.functions.withdrawProfits(
    usdc_address,
    admin_account.address
).build_transaction({
    'from': admin_account.address,
    'nonce': w3.eth.get_transaction_count(admin_account.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})

signed_tx = admin_account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

print(f"Withdrawal transaction: {tx_hash.hex()}")
```

### Automated Withdrawal
Bot automatically withdraws when profit > $100 (configurable).

---

## 📈 Scaling Up

### When Free Tier Runs Out

**Option 1: Upgrade Alchemy ($50/month)**
- Growth plan: 1B CU/month
- Better performance
- Priority support

**Option 2: Add Private Relay**
- Flashbots/MEV-Boost integration
- Higher success rate
- ~$100/month

**Expected ROI after scaling:**
- Free tier: $100-200/day
- Paid RPC: $300-500/day
- Private relay: $500-1000/day

---

## 🆘 Troubleshooting

### Bot Not Finding Opportunities
```bash
# Lower profit threshold temporarily
# Edit bot_config.json
"min_profit_usd": 3
```

### RPC Rate Limits
```bash
# Check tier status
# Bot auto-falls back, but monitor:
grep "RPC" data/logs/bot.log
```

### Transaction Failures
```bash
# Check gas price settings
# Edit bot_config.json
"max_gas_price_gwei": 200  # Increase if needed
```

---

## 📞 Support

**Email Alerts:** Check your configured alert email

**Logs:** `data/logs/bot.log`

**System Check:** `python scripts/check_system.py`

---

**🎉 Congratulations! Your MEV Bot is now running!**