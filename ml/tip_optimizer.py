"""
Tip Optimizer
ML-based dynamic MEV tip calculation to maximize inclusion probability
"""

import os
import joblib
import numpy as np
from typing import Dict
from sklearn.linear_model import LinearRegression
from loguru import logger


class TipOptimizer:
    """
    Optimizes MEV tips based on:
    - Current network congestion
    - Competitor tip analysis
    - Expected profit
    """
    
    def __init__(self, config: Dict):
        """
        Initialize Tip Optimizer
        
        Args:
            config: Bot configuration
        """
        self.config = config
        self.model = None
        
        # Tip constraints
        self.min_tip_gwei = config['mev_boost']['min_tip_gwei']
        self.max_tip_gwei = config['mev_boost']['max_tip_gwei']
        
        # Historical tip data
        self.tip_history = []  # (tip_gwei, success) tuples
        self.max_history = 100
        
        # Load or create model
        self._load_or_create_model()
        
        logger.info("Tip Optimizer initialized")
    
    def _load_or_create_model(self):
        """Load or create tip optimization model"""
        try:
            model_path = "ml/models/tip_optimizer.joblib"
            
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                logger.success("Loaded tip optimizer model")
            else:
                # Simple linear regression model
                self.model = LinearRegression()
                logger.info("Created new tip optimizer model")
                
        except Exception as e:
            logger.error(f"Error loading tip model: {e}")
            self.model = LinearRegression()
    
    async def calculate_optimal_tip(self, opportunity: Dict) -> int:
        """
        Calculate optimal MEV tip for an opportunity
        
        Strategy:
        1. Base tip = min_tip
        2. If high profit, increase tip proportionally
        3. If sandwich attack, beat victim's gas by 12.5%
        4. Cap at max_tip
        
        Args:
            opportunity: Opportunity data
            
        Returns:
            Optimal tip in wei
        """
        try:
            expected_profit_usd = opportunity['expected_profit_usd']
            strategy = opportunity['strategy']
            
            # Base tip
            base_tip_gwei = self.min_tip_gwei
            
            # Adjust based on profit
            # Rule: Tip up to 10% of expected profit
            max_acceptable_tip_gwei = (expected_profit_usd * 0.10) / 0.0000008  # Convert USD to gwei
            
            # Start with base
            optimal_tip_gwei = base_tip_gwei
            
            # For sandwich attacks, beat victim's gas
            if strategy == 'sandwich_attack':
                victim_gas_gwei = opportunity['data'].get('victim_gas_price_gwei', 50)
                optimal_tip_gwei = max(optimal_tip_gwei, victim_gas_gwei * 1.125)  # 12.5% higher
            
            # For high-profit opportunities, increase tip
            if expected_profit_usd > 50:
                optimal_tip_gwei *= 1.5
            elif expected_profit_usd > 100:
                optimal_tip_gwei *= 2.0
            
            # Apply ML prediction if model is trained
            if self.model is not None and len(self.tip_history) > 10:
                ml_tip_gwei = self._ml_predict_tip(expected_profit_usd, strategy)
                
                if ml_tip_gwei > 0:
                    # Blend ML prediction with rule-based
                    optimal_tip_gwei = (optimal_tip_gwei * 0.6) + (ml_tip_gwei * 0.4)
            
            # Enforce constraints
            optimal_tip_gwei = max(self.min_tip_gwei, min(optimal_tip_gwei, self.max_tip_gwei))
            optimal_tip_gwei = min(optimal_tip_gwei, max_acceptable_tip_gwei)
            
            # Convert to wei
            optimal_tip_wei = int(optimal_tip_gwei * 1e9)
            
            logger.debug(f"Calculated optimal tip: {optimal_tip_gwei:.2f} gwei")
            return optimal_tip_wei
            
        except Exception as e:
            logger.error(f"Error calculating tip: {e}")
            # Return safe default
            return int(self.min_tip_gwei * 1e9)
    
    def _ml_predict_tip(self, expected_profit_usd: float, strategy: str) -> float:
        """
        Use ML model to predict optimal tip
        
        Args:
            expected_profit_usd: Expected profit
            strategy: Strategy type
            
        Returns:
            Predicted tip in gwei
        """
        try:
            # Encode strategy
            strategy_map = {
                'direct_arbitrage': 1,
                'triangular_arbitrage': 2,
                'flashloan_arbitrage': 3,
                'liquidation_arbitrage': 4,
                'sandwich_attack': 5
            }
            
            strategy_encoded = strategy_map.get(strategy, 0)
            
            # Features
            features = np.array([[expected_profit_usd, strategy_encoded]])
            
            # Predict
            predicted_tip = self.model.predict(features)[0]
            
            return max(0, predicted_tip)
            
        except Exception as e:
            logger.debug(f"Error in ML tip prediction: {e}")
            return 0
    
    async def record_tip_outcome(self, tip_gwei: float, success: bool):
        """
        Record tip and outcome for model training
        
        Args:
            tip_gwei: Tip that was used
            success: Whether transaction was successful
        """
        try:
            self.tip_history.append((tip_gwei, 1 if success else 0))
            
            # Limit history size
            if len(self.tip_history) > self.max_history:
                self.tip_history.pop(0)
            
            # Retrain model periodically
            if len(self.tip_history) >= 50 and len(self.tip_history) % 20 == 0:
                await self._retrain_model()
                
        except Exception as e:
            logger.error(f"Error recording tip outcome: {e}")
    
    async def _retrain_model(self):
        """Retrain model with historical data"""
        try:
            if len(self.tip_history) < 10:
                return
            
            # Prepare training data
            X = np.array([[tip] for tip, _ in self.tip_history])
            y = np.array([outcome for _, outcome in self.tip_history])
            
            # Retrain
            self.model.fit(X, y)
            
            # Save model
            os.makedirs("ml/models", exist_ok=True)
            joblib.dump(self.model, "ml/models/tip_optimizer.joblib")
            
            logger.info("Tip optimizer model retrained")
            
        except Exception as e:
            logger.error(f"Error retraining model: {e}")
    
    def get_tip_stats(self) -> Dict:
        """Get tip statistics"""
        if not self.tip_history:
            return {'avg_tip': 0, 'success_rate': 0}
        
        avg_tip = np.mean([tip for tip, _ in self.tip_history])
        success_rate = np.mean([outcome for _, outcome in self.tip_history])
        
        return {
            'avg_tip_gwei': avg_tip,
            'success_rate': success_rate * 100,
            'total_samples': len(self.tip_history)
        }