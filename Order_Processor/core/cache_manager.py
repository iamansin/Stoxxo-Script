import os
import yaml
import atexit
import signal
from typing import Dict, Optional, Union, List
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from core.models import OrderType, Providers
from loguru import logger
from core.config import Config
from dataclasses import dataclass
import threading

@dataclass
class WebhookConfig:
    url: str
    multiplier: int = 1

class VariableCache:
    """
    Fast in-memory cache for strategy configurations with proper lifecycle management.
    """
    _instance = None
    _lock = threading.Lock()
    _is_shutdown = False

    def __new__(cls, config: Config):
        """Singleton pattern to prevent multiple instances"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Config):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
            
        load_dotenv()
        self._strategy_urls: Dict[tuple, List[WebhookConfig]] = {}
        self._index_mappings: Dict[str, str] = {}
        self.active_strategy_map: Dict[str, bool] = {}
        self.lot_size_mappings: Dict[str, int] = {}
        self.monthly_expiry_mappings: Dict[str, Dict[str, str]] = {}
        self.provider_config = config
        self._pid = os.getpid()
        self._is_shutdown = False
        
        # Log startup
        logger.critical(f"VariableCache STARTING - PID: {self._pid}, Timestamp: {datetime.now()}")
        
        # Register shutdown handlers
        atexit.register(self.shutdown)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self._load_mappings()
        self._initialized = True
        
        logger.info(f" VariableCache initialized successfully for PID {self._pid}")

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        logger.critical(f" Received signal {signum} - Shutting down PID {self._pid}")
        self.shutdown()
        
    def shutdown(self):
        """Clean shutdown of the cache"""
        if self._is_shutdown:
            return
            
        self._is_shutdown = True
        logger.critical(f" SHUTDOWN - VariableCache PID {self._pid} at {datetime.now()}")
        
        # Clear all data
        self._strategy_urls.clear()
        self._index_mappings.clear()
        self.active_strategy_map.clear()
        self.lot_size_mappings.clear()
        self.monthly_expiry_mappings.clear()
        
        logger.critical("Cache cleared and shutdown complete")

    def _load_mappings(self):
        """Load all mappings from YAML configuration file"""
        if self._is_shutdown:
            logger.error("Cannot load mappings - cache is shutdown")
            return
            
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
                
                tradetron_configs = [
                    WebhookConfig(
                        url=url_config['url'],
                        multiplier=url_config.get('multiplier', 1)
                    ) for url_config in strategy.get('tradetron_urls', [])
                ]
                self._strategy_urls[(name, Providers.TRADETRON)] = tradetron_configs
                
                algotest_configs = [
                    WebhookConfig(
                        url=url_config['url'],
                        multiplier=url_config.get('multiplier', 1)
                    ) for url_config in strategy.get('algotest_urls', [])
                ]
                self._strategy_urls[(name, Providers.ALGOTEST)] = algotest_configs
                
                self.active_strategy_map[name] = strategy.get('active', False)
                logger.info(f"Loaded strategy: {name} - "
                          f"Tradetron: {len(tradetron_configs)} URLs, "
                          f"AlgoTest: {len(algotest_configs)} URLs")

            # Load other mappings
            self._index_mappings = config.get('index_mappings', {})
            self.lot_size_mappings = config.get('lot_sizes', {})
            self.monthly_expiry_mappings = config.get('monthly_expiry', {})

            logger.info(f"Active Strategies: {[k for k, v in self.active_strategy_map.items() if v]}")
            logger.critical(f" LOADED CONFIG - PID {self._pid}: {len(self.active_strategy_map)} strategies, "
                          f"{sum(1 for v in self.active_strategy_map.values() if v)} active")

        except Exception as e:
            logger.error(f"Error loading mappings: {str(e)}")
            raise

    def get_strategy_url(self, strategy: str, provider: Providers) -> Optional[Union[WebhookConfig, List[WebhookConfig]]]:
        """Get webhook configurations for a strategy and provider"""
        if self._is_shutdown:
            logger.error("Cannot get strategy URL - cache is shutdown")
            return None
            
        key = (strategy, provider)
        configs = self._strategy_urls.get(key, [])
        
        if not configs:
            logger.error(f"No URLs found for strategy: {strategy} with provider: {provider.value}")
            return None
            
        # Log every URL access for debugging
        logger.debug(f"Accessing URL for strategy: {strategy}, provider: {provider.value}, PID: {self._pid}")
        
        return configs[0] if len(configs) == 1 else configs
    
    def get_lot_size(self, index: str) -> Union[int, None]:
        if self._is_shutdown:
            return None
            
        lot_size = self.lot_size_mappings.get(index)
        if lot_size is None:
            logger.error(f"No lot size found for index: {index}")
            return None
        return int(lot_size) if not isinstance(lot_size, int) else lot_size
    
    def get_monthly_expiry_date(self, index: str, month: str) -> Optional[str]:
        if self._is_shutdown:
            return None
            
        index_data = self.monthly_expiry_mappings.get(index)
        if index_data is None:
            logger.error(f"No expiry mappings found for index: {index}")
            return None
            
        expiry_date = index_data.get(month.upper())
        if expiry_date is None:
            logger.error(f"No expiry date found for index {index} and month {month}")
            return None
            
        return expiry_date

    def get_index_mapping(self, index: str, order_type: OrderType) -> Optional[int]:
        if self._is_shutdown:
            return None
            
        value = self._index_mappings.get(index)
        if value is None:
            logger.error(f"No mapping found for index: {index}")
            return None
            
        try:
            numeric_value = int(value)
            if order_type == OrderType.SELL:
                numeric_value *= -1
            return numeric_value
        except ValueError:
            logger.error(f"Error converting mapping value '{value}' to integer for index: {index}")
            return None
        
    def strategy_is_active(self, strategy_key: str) -> bool:
        if self._is_shutdown:
            return False
            
        is_active = self.active_strategy_map.get(strategy_key, False)
        logger.debug(f"Strategy {strategy_key} active status: {is_active} (PID: {self._pid})")
        return bool(is_active) if isinstance(is_active, bool) else str(is_active).lower() == 'true'
    
    def active_strategies(self):
        return self.active_strategy_map.keys()

    def reload(self):
        """Reload mappings from files"""
        if self._is_shutdown:
            logger.error("Cannot reload - cache is shutdown")
            return
            
        logger.warning(f" RELOADING CONFIG for PID {self._pid}")
        self._index_mappings.clear()
        self._load_mappings()