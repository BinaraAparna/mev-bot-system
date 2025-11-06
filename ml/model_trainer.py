"""
Model Trainer
Offline training script for ML models
"""

import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from loguru import logger


class ModelTrainer:
    """
    Trains ML models offline using historical data
    """
    
    @staticmethod
    def train_price_predictor(X: np.ndarray, y: np.ndarray):
        """
        Train price prediction model
        
        Args:
            X: Feature matrix (n_samples, n_features)
            y: Labels (n_samples,)
        """
        try:
            logger.info(f"Training price predictor with {len(X)} samples")
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=15,
                random_state=42,
                n_jobs=-1
            )
            
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            train_score = model.score(X_train_scaled, y_train)
            test_score = model.score(X_test_scaled, y_test)
            
            logger.info(f"Training accuracy: {train_score:.3f}")
            logger.info(f"Test accuracy: {test_score:.3f}")
            
            # Save model
            joblib.dump(model, "ml/models/price_predictor.joblib")
            joblib.dump(scaler, "ml/models/price_scaler.joblib")
            
            logger.success("Price predictor model saved")
            
        except Exception as e:
            logger.error(f"Error training price predictor: {e}")
    
    @staticmethod
    def generate_synthetic_warmup_data(n_samples: int = 1000) -> tuple:
        """
        Generate synthetic training data for model warmup
        
        Args:
            n_samples: Number of samples to generate
            
        Returns:
            (X, y) tuple
        """
        logger.info(f"Generating {n_samples} synthetic samples")
        
        # Features: [profit_usd, strategy_type, gas_price, volatility]
        X = np.zeros((n_samples, 4))
        y = np.zeros(n_samples, dtype=int)
        
        for i in range(n_samples):
            # Profit (USD)
            profit = np.random.exponential(20) + np.random.uniform(-5, 50)
            
            # Strategy type (1-5)
            strategy = np.random.randint(1, 6)
            
            # Gas price (gwei)
            gas_price = np.random.normal(50, 20)
            
            # Volatility
            volatility = np.random.uniform(0.5, 2.0)
            
            X[i] = [profit, strategy, gas_price, volatility]
            
            # Label: profitable if profit > 10 and gas_price < 100
            y[i] = 1 if (profit > 10 and gas_price < 100) else 0
        
        return X, y
    
    @staticmethod
    def save_warmup_data(X: np.ndarray, y: np.ndarray):
        """Save warmup data to file"""
        import os
        os.makedirs("data/historical", exist_ok=True)
        
        np.savez(
            "data/historical/warmup_data.npz",
            X=X,
            y=y
        )
        
        logger.success("Warmup data saved")


if __name__ == "__main__":
    # Generate and save warmup data
    trainer = ModelTrainer()
    X, y = trainer.generate_synthetic_warmup_data(1000)
    trainer.save_warmup_data(X, y)
    
    # Train model
    trainer.train_price_predictor(X, y)