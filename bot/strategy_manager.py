"""
Strategy Manager
Coordinates multiple strategies and selects the best opportunity
"""

from typing import List, Optional, Dict
from loguru import logger


class StrategyManager:
    """
    Manages multiple trading strategies and selects optimal opportunity
    """
    
    def __init__(self, config: Dict, strategies: List):
        """
        Initialize Strategy Manager
        
        Args:
            config: Bot configuration
            strategies: List of strategy instances
        """
        self.config = config
        self.strategies = strategies
        
        # Strategy priority mapping
        self.priority_map = {
            'sandwich_attack': 5,
            'flashloan_arbitrage': 4,
            'liquidation_arbitrage': 4,
            'triangular_arbitrage': 3,
            'direct_arbitrage': 2
        }
    
    def select_best_opportunity(self, opportunities: List[Optional[Dict]]) -> Optional[Dict]:
        """
        Select the best opportunity from multiple strategies
        
        Selection criteria (in order):
        1. ML Confidence Score >= threshold
        2. Expected profit (highest)
        3. Strategy priority (if profit is similar)
        4. Gas efficiency (profit/gas ratio)
        
        Args:
            opportunities: List of opportunity dicts from different strategies
            
        Returns:
            Best opportunity or None
        """
        # Filter out None values
        valid_opps = [opp for opp in opportunities if opp is not None]
        
        if not valid_opps:
            return None
        
        # Filter by min confidence
        min_confidence = self.config['ml_optimization']['min_confidence_score']
        confident_opps = [
            opp for opp in valid_opps
            if opp.get('confidence', 0) >= min_confidence
        ]
        
        if not confident_opps:
            logger.debug("No opportunities meet minimum confidence threshold")
            return None
        
        # Sort by expected profit (descending)
        confident_opps.sort(key=lambda x: x['expected_profit_usd'], reverse=True)
        
        # Get top candidate
        top_opp = confident_opps[0]
        
        # Check if there are multiple similar profit opportunities
        similar_profit_threshold = 2.0  # $2 difference considered "similar"
        similar_opps = [
            opp for opp in confident_opps
            if abs(opp['expected_profit_usd'] - top_opp['expected_profit_usd']) <= similar_profit_threshold
        ]
        
        if len(similar_opps) > 1:
            # If profits are similar, choose by priority
            similar_opps.sort(key=lambda x: self.priority_map.get(x['strategy'], 0), reverse=True)
            return similar_opps[0]
        
        return top_opp
    
    def get_active_strategies(self) -> List[str]:
        """Get list of enabled strategies"""
        return [
            name for name, config in self.config['strategies'].items()
            if config.get('enabled', False)
        ]
    
    def is_strategy_enabled(self, strategy_name: str) -> bool:
        """Check if a strategy is enabled"""
        return self.config['strategies'].get(strategy_name, {}).get('enabled', False)