# 🤖 Advanced MEV Bot - Polygon Network

**Ultra-optimized Multi-Strategy MEV Bot** for Polygon with $0 initial cost (free tier optimization).

## ✨ Features

### 🎯 Trading Strategies
- ✅ **Direct Arbitrage** - Cross-DEX price differences
- ✅ **Triangular Arbitrage** - 3-token cycles (A→B→C→A)
- ✅ **Flashloan Arbitrage** - Capital-free trading with Aave V3
- ✅ **Liquidation Arbitrage** - Profit from undercollateralized loans
- ✅ **Sandwich Attacks** - Front-run + back-run large swaps

### 🛡️ Safety Features
- ✅ **Kill Switch** - Auto-pause on daily loss limit
- ✅ **Dual Wallet System** - Executor + Admin separation
- ✅ **Real-time Alerts** - Email notifications (Gmail SMTP)
- ✅ **Transaction Simulation** - Pre-execution validation
- ✅ **Reentrancy Guards** - Smart contract protection

### ⚡ Performance Optimizations
- ✅ **Multicall Batching** - 10-100x fewer RPC calls
- ✅ **4-Tier RPC Fallback** - Alchemy → QuickNode → Infura → Public
- ✅ **JIT Gas Pricing** - Just-in-time optimal gas calculation
- ✅ **Local Caching** - SQLite cache for price/liquidity data
- ✅ **Yul/Assembly Gas Optimization** - 20-30% gas savings

### 🤖 Machine Learning
- ✅ **Profit Predictor** - ML-based opportunity scoring
- ✅ **Dynamic Tip Optimizer** - Smart MEV tip calculation
- ✅ **Online Learning** - Models improve with real trades

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js 16+ (for Hardhat)
- Polygon wallet with ~$20 MATIC for gas

### 1. Clone & Install

```bash
git clone <your-repo>
cd mev-bot-system

# Install Python dependencies
pip install -r requirements.txt

# Install Hardhat
npm install
```

### 2. Configure Environment

Create `.env` file:

```env
# Wallets (CRITICAL - KEEP SECRET)
EXECUTOR_PRIVATE_KEY=your_executor_key_here
ADMIN_PRIVATE_KEY=your_admin_key_here
EXECUTOR_ADDRESS=your_executor_address
ADMIN_ADDRESS=your_admin_address

# RPC Endpoints (Free Tier)
ALCHEMY_API_KEY=your_alchemy_key
QUICKNODE_API_KEY=your_quicknode_key
INFURA_API_KEY=your_infura_key

# Construct URLs
ALCHEMY_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}
ALCHEMY_WSS_URL=wss://polygon-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}
QUICKNODE_RPC_URL=https://your-endpoint.matic.quiknode.pro/${QUICKNODE_API_KEY}/
INFURA_RPC_URL=https://polygon-mainnet.infura.io/v3/${INFURA_API_KEY}

# Alerts
ALERT_EMAIL=your_email@gmail.com
SMTP_USERNAME=your_gmail@gmail.com
SMTP_APP_PASSWORD=your_gmail_app_password
```

### 3. Deploy Smart Contract

```bash
# Compile contracts
npx hardhat compile

# Deploy to Polygon
python scripts/deploy_contract.py
```

This will:
- Deploy `FlashloanArbitrage.sol`
- Update `.env` with contract address
- Set executor address

### 4. Generate ML Warmup Data

```bash
python scripts/generate_warmup_data.py
```

Creates synthetic training data for ML models.

### 5. Run Bot

```bash
python main.py
```

## 📊 Configuration

### Bot Settings (`config/bot_config.json`)

```json
{
  "profit_thresholds": {
    "min_profit_usd": 5,
    "min_profit_multiplier": 2.0
  },
  "risk_management": {
    "max_daily_loss_usd": 50,
    "max_failed_tx_before_pause": 1
  }
}
```

### Supported DEXes (`config/dex_config.json`)

- QuickSwap V2/V3
- SushiSwap
- Uniswap V3
- Balancer V2
- Curve Finance

### Tokens (`config/token_config.json`)

High-priority: WMATIC, USDC, USDT, WETH, DAI, WBTC

## 🎯 Strategy Selection Logic

Bot automatically selects best opportunity:

```
WHILE (running):
  1. Check sandwich attacks (Priority 5)
  2. Check liquidations (Priority 4)
  3. Check direct arbitrage (Priority 2)
  4. Check triangular arbitrage (Priority 3)
  
  IF (opportunity.confidence >= 90% AND profit >= min):
    EXECUTE
```

## 💰 Free Tier Optimization

### RPC Usage Strategy

| Tier | Provider | Limit | Usage |
|------|----------|-------|-------|
| 1 | Alchemy | 300M CU/month | Primary data reading |
| 2 | QuickNode | 10M credits | Fallback + WebSocket |
| 3 | Infura | 100k/day | Buffer fallback |
| 4 | Public | Unstable | Last resort only |

### Cost Breakdown

**Initial Costs:**
- Smart Contract Deployment: ~$0.50 (one-time)
- Initial Gas Buffer: $20 (executor wallet)
- VPS (optional): $5-10/month

**Ongoing Costs:**
- Gas per trade: $0.50-$2.00
- RPC: $0 (free tiers)
- ML compute: $0 (local sklearn)

**Target ROI:**
- Daily profit goal: $100+
- Break-even: ~2-3 days
- Monthly profit: $2,000-$3,000

## 🔒 Security

### Dual Wallet System

1. **Executor Wallet**
   - Only holds gas buffer ($20-50)
   - Signs daily transactions
   - Private key in `.env`

2. **Admin Wallet**
   - Holds accumulated profits
   - Withdraws profits weekly
   - Controls kill switch
   - Separate private key

### Auto-Withdrawal

Profits automatically withdraw to admin wallet when:
- Accumulated profit > $100
- Executor buffer maintained at $50

### Kill Switch Triggers

- Daily loss exceeds $50
- 1+ failed transactions
- Manual activation
- RPC exhaustion

## 📈 Monitoring

### Real-time Alerts (Email)

- ✅ Profit notifications
- ⚠️ Loss warnings
- 🚨 Kill switch activation
- 📊 Daily summaries
- 🔄 RPC failover alerts

### Logs

```bash
# View live logs
tail -f data/logs/bot.log

# Check errors only
grep ERROR data/logs/bot.log
```

## 🧪 Testing

### Local Testing (Hardhat)

```bash
npx hardhat test
```

### Mumbai Testnet

```bash
# Update .env with testnet RPC
TESTNET_RPC=https://rpc-mumbai.maticvigil.com

# Deploy to testnet
npx hardhat run scripts/deploy.js --network mumbai
```

## 🛠️ Troubleshooting

### Bot Not Finding Opportunities

1. Check RPC connection: `bot.rpc_manager.is_healthy()`
2. Verify DEX liquidity > $10k
3. Lower `min_profit_usd` temporarily
4. Check gas prices (should be < 150 gwei)

### RPC Rate Limits

Bot auto-falls back to next tier. If Tier 4 reached:
- Wait 1 hour for Tier 1 reset
- Or upgrade to paid RPC plan

### Failed Transactions

Check:
- Gas price too low
- Slippage too tight
- Front-run by competitors
- Insufficient liquidity

### Contract Reverts

Enable simulation:
```json
"free_tier_optimization": {
  "skip_simulation_below_profit": 0
}
```

## 📚 Architecture

```
mev-bot-system/
├── contracts/          # Solidity contracts
├── bot/               # Core bot logic
├── strategies/        # Trading strategies
├── blockchain/        # Contract interactions
├── monitoring/        # Mempool, prices
├── ml/               # ML models
├── utils/            # Utilities
└── config/           # Configuration
```

## 🔄 Upgrade Path

### Phase 1: Free Tier (Current)
- $0 initial cost
- Free RPC tiers
- Target: $100+/day

### Phase 2: Paid RPC ($50/month)
- Alchemy Growth plan
- Private relay access
- Target: $300+/day

### Phase 3: MEV-Boost ($100/month)
- Flashbots integration
- Builder network access
- Target: $500+/day

## 📞 Support

**Email Alerts:** binaraedu20@gmail.com

**Logs:** `data/logs/bot.log`

## ⚠️ Disclaimer

This bot is for educational purposes. Cryptocurrency trading involves significant risk. Always:
- Test on testnet first
- Start with small amounts
- Monitor constantly
- Understand the code
- Never invest more than you can lose

## 📄 License

MIT License - See LICENSE file

---

**Built with ❤️ for MEV research and education**