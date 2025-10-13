import os
import yaml
from typing import Dict, Optional, Union, List
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from core.models import OrderType, Providers
from loguru import logger
from core.config import Config
class VariableCache:
    """
    Fast in-memory cache for strategy configurations and mappings.
    Loads data from YAML config file at startup and provides O(1) access.
    """

    def __init__(self, config : Config):
        load_dotenv()
        self._strategy_urls: Dict[tuple, List[str]] = {}  # (strategy, provider) -> urls list
        self._index_mappings: Dict[str, str] = {}  # index -> value
        self.active_strategy_map: Dict[str, bool] = {}  # strategy -> active status
        self.lot_size_mappings: Dict[str, int] = {}  # index -> lot size
        self.monthly_expiry_mappings: Dict[str, Dict[str, str]] = {}  # index -> {month -> expiry_date}
        self.provider_config = config
        self._load_mappings()

    def _load_mappings(self):
        """Load all mappings from YAML configuration file"""
        try:
            config_file = self.provider_config.YAML_PATH
            if not Path(config_file).exists():
                raise FileNotFoundError(f"Configuration file not found: {config_file}")

            logger.info(f"Loading configurations from: {config_file}")
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if config is None:
                raise ValueError("Failed to parse YAML file - file may be empty or malformed")

            # Load strategy configurations
            for strategy in config.get('strategies', []):
                name = strategy['name']
                self._strategy_urls[(name,Providers.TRADETRON)] = strategy.get('tradetron_urls', [])
                self._strategy_urls[(name,Providers.ALGOTEST)] = strategy.get('algotest_urls', [])
                self.active_strategy_map[name] = strategy.get('active', False)
                logger.info(f"Loaded strategy: {name} with URLs - "
                          f"Tradetron: {len(self._strategy_urls.get((name, Providers.TRADETRON), []))} "
                          f"AlgoTest: {len(self._strategy_urls.get((name, Providers.ALGOTEST), []))}")
            # Load index mappings
            self._index_mappings = config.get('index_mappings', {})
            logger.info(f"Loaded {len(self._index_mappings)} index mappings")

            # Load lot sizes
            self.lot_size_mappings = config.get('lot_sizes', {})
            logger.info(f"Loaded {len(self.lot_size_mappings)} lot size mappings")

            # Load monthly expiry configurations
            self.monthly_expiry_mappings = config.get('monthly_expiry', {})
            logger.info(f"Loaded expiry mappings for {len(self.monthly_expiry_mappings)} months")

            logger.info(f"Active Strategies: {[k for k, v in self.active_strategy_map.items() if v]}")

        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error loading mappings: {str(e)}")
            raise

    def get_strategy_url(self, strategy: str, provider: Providers) -> Optional[Union[str, List[str]]]:
        """
        Get URLs for a strategy and provider. Returns either a single URL or list of URLs.
        
        Args:
            strategy: Strategy name
            provider: Provider enum (TRADETRON or ALGOTEST)
            
        Returns:
            - List of URLs if multiple URLs are configured
            - Single URL string if only one URL is configured
            - None if no URLs are found
        """
        key = (strategy, provider)
        urls = self._strategy_urls.get(key, [])
        
        if not urls:
            logger.error(f"No URLs found for strategy: {strategy} with provider: {provider.value}")
            return None
            
        return urls[0] if len(urls) == 1 else urls
    
    def get_lot_size(self, index: str) -> Union[int, None]:
        
        lot_size = self.lot_size_mappings.get(index)
        if lot_size is None:
            logger.error(f"No lot size found for strategy: {index}")
            return None
        if not isinstance(lot_size, int):
            return int(lot_size)
        
        return lot_size
    
    def get_monthly_expiry_date(self, index: str, month: str) -> Optional[str]:
        """
        Get expiry date for a specific index and month.
        
        Args:
            index: Index name (e.g., 'NIFTY', 'BANKNIFTY')
            month: Three letter month code in uppercase (e.g., 'OCT', 'NOV')
            
        Returns:
            Expiry date string (e.g., "25-10-14") or None if not found
        """
        index_data = self.monthly_expiry_mappings.get(index, None)
        if index_data is None:
            logger.error(f"No expiry mappings found for index: {index}")
            return None
            
        expiry_date = index_data.get(month.upper())
        if expiry_date is None:
            logger.error(f"No expiry date found for index {index} and month {month}")
            return None
            
        return expiry_date

    def get_index_mapping(self, index: str, order_type: OrderType) -> Optional[str]:
        """
        Get mapped value for an index. O(1) operation.
        Applies sign based on order type (negative for SELL orders)
        """
        value = self._index_mappings.get(index)
        if value is None:
            logger.error(f"No mapping found for index: {index}")
            return None
            
        try:
            # Convert to integer for manipulation
            numeric_value = int(value)
            
            # Apply sign based on order type
            if order_type == OrderType.SELL:
                numeric_value *= -1
                
            return numeric_value  # Convert back to string as that's what the API expects
            
        except ValueError as e:
            logger.error(f"Error converting mapping value '{value}' to integer for index: {index}")
            return None

    def strategy_is_active(self, strategy_key : str) -> bool:
        is_active = self.active_strategy_map.get(strategy_key, False)
        logger.info(f"Strategy {strategy_key} active status: {is_active} (type: {type(is_active)})")
        if isinstance(is_active, bool):
            return is_active
        return True if str(is_active).lower() == 'true' else False
    
    def active_strategies(self):
        return self.active_strategy_map.keys()

    def reload(self):
        """Reload mappings from files"""
        self._index_mappings.clear()
        self._load_mappings()