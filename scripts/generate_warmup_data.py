"""
Generate Warmup Data for ML Models
Creates synthetic training data based on realistic Polygon MEV patterns
"""

import os
import numpy as np
from loguru import logger


def generate_synthetic_warmup_data(n_samples: int = 2000):
    """
    Generate synthetic MEV opportunity data
    
    Args:
        n_samples: Number of samples to generate
    """
    logger.info(f"Generating {n_samples} synthetic samples...")
    
    # Features: [profit_usd, strategy_type, gas_price_gwei, volatility, liquidity_score]
    X = np.zeros((n_samples, 5))
    y = np.zeros(n_samples, dtype=int)
    
    for i in range(n_samples):
        # Profit distribution (exponential with some high outliers)
        if np.random.random() < 0.1:
            # 10% high-profit opportunities
            profit = np.random.exponential(50) + 20
        else:
            # 90% normal opportunities
            profit = np.random.exponential(15) + np.random.uniform(-5, 10)
        
        # Strategy type (1-5)
        strategy_weights = [0.3, 0.25, 0.2, 0.15, 0.1]  # Distribution
        strategy = np.random.choice([1, 2, 3, 4, 5], p=strategy_weights)
        
        # Gas price (realistic Polygon range)
        if np.random.random() < 0.8:
            # Normal conditions
            gas_price = np.random.normal(50, 15)
        else:
            # Spike conditions
            gas_price = np.random.normal(200, 50)
        
        gas_price = max(20, min(gas_price, 500))  # Clamp
        
        # Volatility (market condition indicator)
        volatility = np.random.lognormal(0, 0.5)
        
        # Liquidity score (0-10)
        liquidity = np.random.beta(2, 2) * 10
        
        # Store features
        X[i] = [profit, strategy, gas_price, volatility, liquidity]
        
        # Label: Profitable if:
        # 1. Profit > 10 USD
        # 2. Gas price < 150 gwei
        # 3. Liquidity score > 3
        # 4. Random factor (95% accurate)
        
        is_profitable = (
            profit > 10 and
            gas_price < 150 and
            liquidity > 3 and
            np.random.random() < 0.95  # 5% noise
        )
        
        y[i] = 1 if is_profitable else 0
    
    # Calculate statistics
    positive_samples = np.sum(y)
    negative_samples = len(y) - positive_samples
    
    logger.info(f"Generated {n_samples} samples:")
    logger.info(f"  Profitable: {positive_samples} ({positive_samples/n_samples*100:.1f}%)")
    logger.info(f"  Unprofitable: {negative_samples} ({negative_samples/n_samples*100:.1f}%)")
    
    # Feature statistics
    logger.info("\nFeature Statistics:")
    logger.info(f"  Profit: mean=${X[:, 0].mean():.2f}, std=${X[:, 0].std():.2f}")
    logger.info(f"  Gas: mean={X[:, 2].mean():.1f} gwei, std={X[:, 2].std():.1f} gwei")
    logger.info(f"  Volatility: mean={X[:, 3].mean():.2f}")
    logger.info(f"  Liquidity: mean={X[:, 4].mean():.2f}")
    
    return X, y


def save_warmup_data(X: np.ndarray, y: np.ndarray):
    """Save warmup data to file"""
    try:
        # Create directory
        os.makedirs("data/historical", exist_ok=True)
        
        # Save as numpy compressed format
        np.savez_compressed(
            "data/historical/warmup_data.npz",
            X=X,
            y=y
        )
        
        logger.success("Warmup data saved to data/historical/warmup_data.npz")
        
    except Exception as e:
        logger.error(f"Error saving warmup data: {e}")


def generate_tip_optimization_data(n_samples: int = 1000):
    """
    Generate data for tip optimizer
    
    Args:
        n_samples: Number of samples
    """
    logger.info(f"Generating {n_samples} tip optimization samples...")
    
    # Features: [profit_usd, strategy_type]
    X = np.zeros((n_samples, 2))
    # Labels: optimal tip in gwei
    y = np.zeros(n_samples)
    
    for i in range(n_samples):
        profit = np.random.exponential(30) + 5
        strategy = np.random.randint(1, 6)
        
        # Optimal tip calculation (simplified model)
        # Base: 10 gwei
        # Add: profit-based component
        # Add: strategy-based component
        
        base_tip = 10
        profit_component = (profit / 100) * 20  # Max 20 gwei from profit
        strategy_component = strategy * 2  # 2-10 gwei based on strategy
        
        optimal_tip = base_tip + profit_component + strategy_component
        optimal_tip = max(10, min(optimal_tip, 100))  # Clamp to valid range
        
        X[i] = [profit, strategy]
        y[i] = optimal_tip
    
    logger.info(f"Tip data generated: mean={y.mean():.1f} gwei")
    
    # Save
    os.makedirs("data/historical", exist_ok=True)
    np.savez_compressed(
        "data/historical/tip_optimizer_data.npz",
        X=X,
        y=y
    )
    
    logger.success("Tip optimizer data saved")


if __name__ == "__main__":
    # Generate price predictor warmup data
    X, y = generate_synthetic_warmup_data(2000)
    save_warmup_data(X, y)
    
    # Generate tip optimizer data
    generate_tip_optimization_data(1000)
    
    logger.success("All warmup data generated successfully!")
    logger.info("\nNext steps:")
    logger.info("1. Run the bot to let ML models learn from real data")
    logger.info("2. Models will improve over time with actual trading results")