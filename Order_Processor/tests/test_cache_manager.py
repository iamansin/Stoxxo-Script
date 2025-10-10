import pytest
import pandas as pd
from pathlib import Path
import tempfile
from core.cache_manager import VariableCache
from core.models import OrderType, Providers
from core.config import TradetronConfig

@pytest.fixture
def sample_strategy_csv():
    """Create a temporary strategy CSV file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write("strategy,provider,token\n")
        f.write("strategy1,tradetron,token1\n")
        f.write("strategy2,tradetron,token2\n")
        f.write("strategy3,algotrades,token3\n")
    return Path(f.name)

@pytest.fixture
def sample_index_csv():
    """Create a temporary index CSV file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write("index,provider,value\n")
        f.write("NIFTY,tradetron,1\n")
        f.write("BANKNIFTY,tradetron,2\n")
        f.write("FINNIFTY,tradetron,3\n")
    return Path(f.name)

@pytest.fixture
def mock_config(sample_strategy_csv, sample_index_csv, monkeypatch):
    """Mock TradetronConfig to use test CSV files"""
    class MockTradetronConfig(TradetronConfig):
        STRATEGY_CSV = str(sample_strategy_csv)
        INDEX_CSV = str(sample_index_csv)
    
    monkeypatch.setattr("core.cache_manager.TradetronConfig", MockTradetronConfig)
    return MockTradetronConfig()

def test_load_mappings(mock_config):
    """Test that mappings are loaded correctly"""
    cache = VariableCache()
    
    # Check strategy mappings
    assert len(cache._strategy_tokens) == 3
    assert cache.get_strategy_token("strategy1", Providers.TRADETRON) == "token1"
    assert cache.get_strategy_token("strategy2", Providers.TRADETRON) == "token2"
    assert cache.get_strategy_token("strategy3", Providers.ALGOTRADES) == "token3"
    
    # Print all strategy mappings for debugging
    print("\nLoaded strategy mappings:")
    for (strategy, provider), token in cache._strategy_tokens.items():
        print(f"{strategy} ({provider}) -> {token}")
    
    # Check index mappings
    assert len(cache._index_mappings) == 3
    
    # Test BUY orders (positive values)
    assert cache.get_index_mapping("NIFTY", Providers.TRADETRON, OrderType.BUY) == "1"
    assert cache.get_index_mapping("BANKNIFTY", Providers.TRADETRON, OrderType.BUY) == "2"
    
    # Test SELL orders (negative values)
    assert cache.get_index_mapping("NIFTY", Providers.TRADETRON, OrderType.SELL) == "-1"
    assert cache.get_index_mapping("BANKNIFTY", Providers.TRADETRON, OrderType.SELL) == "-2"
    
    # Print all index mappings for debugging
    print("\nLoaded index mappings:")
    for (index, provider), value in cache._index_mappings.items():
        print(f"{index} ({provider}) -> {value}")

def test_missing_strategy(mock_config):
    """Test behavior when strategy is not found"""
    cache = VariableCache()
    result = cache.get_strategy_token("nonexistent", Providers.TRADETRON)
    assert result is None

def test_missing_index(mock_config):
    """Test behavior when index is not found"""
    cache = VariableCache()
    result = cache.get_index_mapping("nonexistent", Providers.TRADETRON, OrderType.BUY)
    assert result is None

def test_invalid_index_value(mock_config, sample_index_csv):
    """Test handling of non-numeric index values"""
    # Create a CSV with invalid numeric value
    with open(sample_index_csv, 'a') as f:
        f.write("INVALID,tradetron,not_a_number\n")
    
    cache = VariableCache()
    result = cache.get_index_mapping("INVALID", Providers.TRADETRON, OrderType.BUY)
    assert result is None

def test_provider_case_insensitivity(mock_config):
    """Test that provider matching is case-insensitive"""
    cache = VariableCache()
    assert cache.get_strategy_token("strategy1", Providers.TRADETRON) == \
           cache.get_strategy_token("strategy1", Providers("TRADETRON"))

def test_reload_mappings(mock_config, sample_strategy_csv):
    """Test that reload updates mappings when files change"""
    cache = VariableCache()
    initial_token = cache.get_strategy_token("strategy1", Providers.TRADETRON)
    
    # Modify the CSV file
    with open(sample_strategy_csv, 'a') as f:
        f.write("strategy1,tradetron,new_token\n")
    
    # Reload and verify
    cache.reload()
    new_token = cache.get_strategy_token("strategy1", Providers.TRADETRON)
    assert new_token == "new_token"
    assert new_token != initial_token

def cleanup_test_files(sample_strategy_csv, sample_index_csv):
    """Clean up temporary test files"""
    try:
        sample_strategy_csv.unlink()
        sample_index_csv.unlink()
    except Exception as e:
        print(f"Error cleaning up test files: {e}")

# Add cleanup to be run after all tests
@pytest.fixture(autouse=True)
def cleanup(sample_strategy_csv, sample_index_csv):
    yield
    cleanup_test_files(sample_strategy_csv, sample_index_csv)