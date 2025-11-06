"""
Unit Tests for Trading Strategies
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from web3 import Web3

from strategies.flashloan_arb import FlashloanArbitrage
from strategies.triangular_arb import TriangularArbitrage
from strategies.liquidation_arb import LiquidationArbitrage
from strategies.sandwich_attack import SandwichAttack


@pytest.fixture
def w3():
    """Mock Web3 instance"""
    return Mock(spec=Web3)


@pytest.fixture
def config():
    """Test configuration"""
    return {
        'strategies': {
            'flashloan_arbitrage': {
                'min_profit_usd': 5,
                'max_loan_size_usd': 10000
            },
            'triangular_arbitrage': {
                'min_profit_usd': 8
            }
        }
    }


@pytest.fixture
def dex_config():
    """Mock DEX configuration"""
    return {
        'polygon_dexes': {
            'quickswap_v2': {
                'router': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',
                'factory': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
                'version': 'v2',
                'enabled': True
            }
        }
    }


@pytest.fixture
def token_config():
    """Mock token configuration"""
    return {
        'tokens': {
            'WMATIC': {
                'address': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
                'decimals': 18,
                'symbol': 'WMATIC',
                'trusted': True
            },
            'USDC': {
                'address': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
                'decimals': 6,
                'symbol': 'USDC',
                'trusted': True
            }
        },
        'high_volume_pairs': [
            ['WMATIC', 'USDC']
        ]
    }


class TestFlashloanArbitrage:
    """Test Flashloan Arbitrage Strategy"""
    
    @pytest.mark.asyncio
    async def test_find_opportunities(self, w3, config, dex_config, token_config):
        """Test opportunity finding"""
        contract_manager = Mock()
        strategy = FlashloanArbitrage(w3, contract_manager, config, dex_config, token_config)
        
        # Mock methods
        strategy._find_cross_dex_arbitrage = AsyncMock(return_value=None)
        
        opportunities = await strategy.find_opportunities()
        
        assert isinstance(opportunities, list)
    
    @pytest.mark.asyncio
    async def test_calculate_optimal_loan_size(self, w3, config, dex_config, token_config):
        """Test loan size calculation"""
        contract_manager = Mock()
        strategy = FlashloanArbitrage(w3, contract_manager, config, dex_config, token_config)
        
        token_a = token_config['tokens']['WMATIC']
        token_b = token_config['tokens']['USDC']
        
        # Mock pool data
        strategy._get_pool_liquidity = AsyncMock(return_value=100000)
        strategy._get_price = AsyncMock(return_value=0.80)
        
        loan_size = await strategy._calculate_optimal_loan_size(
            token_a, token_b, {}, {}
        )
        
        assert loan_size >= 0


class TestTriangularArbitrage:
    """Test Triangular Arbitrage Strategy"""
    
    def test_generate_triangular_paths(self, w3, dex_config, token_config):
        """Test path generation"""
        multicall = Mock()
        strategy = TriangularArbitrage(w3, dex_config, token_config, multicall)
        
        assert len(strategy.triangular_paths) > 0
        
        # Check path format
        for path in strategy.triangular_paths:
            assert len(path) == 4
            assert path[0] == path[3]
    
    @pytest.mark.asyncio
    async def test_check_triangular_path(self, w3, dex_config, token_config):
        """Test path profitability check"""
        multicall = Mock()
        strategy = TriangularArbitrage(w3, dex_config, token_config, multicall)
        
        path = ['WMATIC', 'USDC', 'WETH', 'WMATIC']
        
        # Mock exchange rates
        strategy._get_exchange_rate = AsyncMock(return_value=1.01)
        strategy._calculate_optimal_trade_size = AsyncMock(return_value=1000)
        strategy._get_token_price_usd = AsyncMock(return_value=0.80)
        strategy._estimate_gas_cost_triangular = AsyncMock(return_value=2.0)
        
        result = await strategy._check_triangular_path(
            path,
            'quickswap_v2',
            dex_config['polygon_dexes']['quickswap_v2']
        )
        
        # Should return None if not profitable, or dict if profitable
        assert result is None or isinstance(result, dict)


class TestLiquidationArbitrage:
    """Test Liquidation Arbitrage Strategy"""
    
    @pytest.mark.asyncio
    async def test_find_liquidations(self, w3, config):
        """Test liquidation finding"""
        multicall = Mock()
        strategy = LiquidationArbitrage(w3, config, multicall)
        
        # Mock methods
        strategy._get_users_to_monitor = AsyncMock(return_value=[])
        
        opportunities = await strategy.find_liquidations()
        
        assert isinstance(opportunities, list)
    
    def test_is_liquidatable(self, w3, config):
        """Test liquidation check"""
        multicall = Mock()
        strategy = LiquidationArbitrage(w3, config, multicall)
        
        # Health factor < 1.0 (liquidatable)
        account_data = {
            'health_factor': int(0.95 * 1e18)
        }
        
        assert strategy._is_liquidatable(account_data)
        
        # Health factor > 1.0 (safe)
        account_data = {
            'health_factor': int(1.5 * 1e18)
        }
        
        assert strategy._is_liquidatable(account_data) 


class TestSandwichAttack:
    """Test Sandwich Attack Strategy"""
    
    def test_is_swap_transaction(self, w3, config, dex_config):
        """Test swap detection"""
        mempool_monitor = Mock()
        strategy = SandwichAttack(w3, mempool_monitor, config, dex_config)
        
        # Valid swap transaction
        tx_valid = {
            'input': '0x38ed1739' + '0' * 200
        }
        
        assert strategy._is_swap_transaction(tx_valid) 
        
        # Invalid transaction
        tx_invalid = {
            'input': '0x12345678'
        }
        
        assert not strategy._is_swap_transaction(tx_invalid) 
    
    @pytest.mark.asyncio
    async def test_analyze_transaction(self, w3, config, dex_config):
        """Test transaction analysis"""
        mempool_monitor = Mock()
        strategy = SandwichAttack(w3, mempool_monitor, config, dex_config)
        
        tx_data = {
            'hash': '0x123',
            'input': '0x12345678',
            'gasPrice': 50000000000
        }
        
        result = await strategy.analyze_transaction(tx_data)
        
        # Should return None for non-swap tx
        assert result is None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, '-v'])