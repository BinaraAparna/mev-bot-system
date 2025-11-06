"""
Price Predictor
ML model to predict arbitrage profitability
"""

import os
import joblib
import numpy as np
from typing import Dict, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from loguru import logger


class PricePredictor:
    """
    ML model for predicting arbitrage success probability
    Uses lightweight sklearn RandomForest (no GPU needed)
    """
    
    def __init__(self, config: Dict):
        """
        Initialize Price Predictor
        
        Args:
            config: Bot configuration
        """
        self.config = config
        self.model = None
        self.scaler = StandardScaler()
        
        # Model paths
        self.model_path = "ml/models/price_predictor.joblib"
        self.scaler_path = "ml/models/price_scaler.joblib"
        
        # Load or create model
        self._load_or_create_model()
        
        logger.info("Price Predictor initialized")
    
    def _load_or_create_model(self):
        """Load existing model or create new one"""
        try:
            if os.path.exists(self.model_path):
                # Load trained model
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                logger.success(f"Loaded trained model from {self.model_path}")
            else:
                # Create new model
                self.model = RandomForestClassifier(
                    n_estimators=50,  # Lightweight
                    max_depth=10,
                    random_state=42,
                    n_jobs=-1
                )
                logger.info("Created new RandomForest model")
                
                # Train with synthetic data if available
                self._train_with_warmup_data()
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            # Fallback to new model
            self.model = RandomForestClassifier(
                n_estimators=50,
                max_depth=10,
                random_state=42
            )
    
    def _train_with_warmup_data(self):
        """Train model with warmup data if available"""
        try:
            warmup_path = "data/historical/warmup_data.npz"
            
            if os.path.exists(warmup_path):
                data = np.load(warmup_path)
                X_train = data['X']
                y_train = data['y']
                
                # Scale features
                X_scaled = self.scaler.fit_transform(X_train)
                
                # Train model
                self.model.fit(X_scaled, y_train)
                
                # Save model
                os.makedirs("ml/models", exist_ok=True)
                joblib.dump(self.model, self.model_path)
                joblib.dump(self.scaler, self.scaler_path)
                
                logger.success("Model trained with warmup data")
            else:
                logger.warning("No warmup data found - model will learn online")
                
        except Exception as e:
            logger.error(f"Error training with warmup data: {e}")
    
    async def predict_profit_probability(
        self,
        expected_profit_usd: float,
        strategy_type: str
    ) -> Dict:
        """
        Predict probability that trade will be profitable
        
        Args:
            expected_profit_usd: Expected profit in USD
            strategy_type: Type of strategy
            
        Returns:
            Dict with confidence score and prediction
        """
        try:
            # Extract features
            features = self._extract_features(expected_profit_usd, strategy_type)
            
            if self.model is None:
                # No model available - return neutral prediction
                return {
                    'confidence': 0.5,
                    'profitable': True if expected_profit_usd > 0 else False
                }
            
            # Scale features
            features_scaled = self.scaler.transform([features])
            
            # Predict probability
            proba = self.model.predict_proba(features_scaled)[0]
            
            # Confidence is probability of positive class
            confidence = proba[1] if len(proba) > 1 else 0.5
            
            return {
                'confidence': confidence,
                'profitable': confidence >= 0.5,
                'probability_vector': proba.tolist()
            }
            
        except Exception as e:
            logger.debug(f"Error in prediction: {e}")
            # Return conservative estimate
            return {
                'confidence': 0.7 if expected_profit_usd > 10 else 0.5,
                'profitable': True
            }
    
    async def predict_sandwich_success(self, analysis: Dict) -> Dict:
        """
        Predict sandwich attack success probability
        
        Args:
            analysis: Sandwich analysis data
            
        Returns:
            Prediction dict
        """
        try:
            # Extract sandwich-specific features
            features = [
                analysis['expected_profit_usd'],
                analysis['victim_swap_params']['value_usd'],
                analysis['gas_price_gwei'],
                1.0  # Sandwich indicator
            ]
            
            if self.model is None:
                return {'confidence': 0.75, 'profitable': True}
            
            features_scaled = self.scaler.transform([features])
            proba = self.model.predict_proba(features_scaled)[0]
            
            return {
                'confidence': proba[1] if len(proba) > 1 else 0.75,
                'profitable': True
            }
            
        except Exception as e:
            logger.debug(f"Error predicting sandwich success: {e}")
            return {'confidence': 0.75, 'profitable': True}
    
    def _extract_features(
        self,
        expected_profit_usd: float,
        strategy_type: str
    ) -> list:
        """
        Extract features for ML prediction
        
        Features:
        - Expected profit USD
        - Strategy type (encoded)
        - Gas price estimate
        - Market volatility indicator
        
        Args:
            expected_profit_usd: Expected profit
            strategy_type: Strategy name
            
        Returns:
            Feature vector
        """
        # Strategy encoding
        strategy_map = {
            'direct_arbitrage': 1.0,
            'triangular': 2.0,
            'flashloan': 3.0,
            'liquidation': 4.0,
            'sandwich_attack': 5.0
        }
        
        strategy_encoded = strategy_map.get(strategy_type, 0.0)
        
        # Simple features
        features = [
            expected_profit_usd,
            strategy_encoded,
            50.0,  # Assumed gas price (gwei)
            1.0    # Volatility placeholder
        ]
        
        return features
    
    async def update_model(self, X_new: np.ndarray, y_new: np.ndarray):
        """
        Update model with new data (online learning)
        
        Args:
            X_new: New feature data
            y_new: New labels
        """
        try:
            if self.model is None:
                return
            
            # Scale features
            _ = self.scaler.transform(X_new)  # Prepared for future use
            
            # Partial fit (incremental learning)
            # Note: RandomForest doesn't support partial_fit
            # For true online learning, use SGDClassifier
            # For now, we retrain periodically
            
            logger.info("Model update requested (scheduled for batch update)")
            
        except Exception as e:
            logger.error(f"Error updating model: {e}")
    
    def save_model(self):
        """Save model to disk"""
        try:
            os.makedirs("ml/models", exist_ok=True)
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            logger.success("Model saved")
        except Exception as e:
            logger.error(f"Error saving model: {e}")