# /stock-signal-monitor/config.py

from pathlib import Path
from pydantic import BaseModel
from typing_extensions import Optional
from dotenv import load_dotenv
import os

load_dotenv()
# --- Webhook Configuration ---
# Replace with your actual authentication token
AUTH_TOKEN = "f18326bc-7b06-4593-ae5b-e7d0789e5318"
BASE_URL = "https://api.tradetron.tech/api"

# --- Log File Monitoring Configuration ---
# Define the base path to the log directory
LOGS_BASE_PATH = Path("C:/Program Files (x86)/Stoxxo/Logs")
# The name of the log file to monitor. 
# This example assumes the file is named 'trading_signals.log'. 
# Please CHANGE this to your actual log file name.
LOG_FILE_NAME = "trading_signals.log"
LOG_FILE_PATH = LOGS_BASE_PATH / LOG_FILE_NAME

# --- Log Parsing Configuration ---
# The specific text in a log message that identifies a relevant signal.
# This ensures that only order placement logs are processed.
RELEVANT_LOG_KEYWORD = "Initiating Order Placement"


class Config(BaseModel):
    """Central configuration for the system"""
    
    # System settings
    MAX_WORKERS : int = 4
    QUEUE_SIZE : int = 10000
    BATCH_SIZE : int = 50

    # Log monitoring
    LOG_PATH : Path = Path("C:/Program Files (x86)/Stoxxo/Logs")
    LOG_FILE_PATTERN : str = "*.csv"

    # Processing settings
    RETRY_ATTEMPTS : int = 3
    RETRY_DELAY : float = 1.0   # seconds
    PROCESSING_TIMEOUT : int = 30  # seconds

    # Platform configurations
    ENABLE_TRADETRON : bool = True
    ENABLE_ALGOBULLS : bool = False

class AdapterConfig(BaseModel):
    """Configuration for adapters"""
    BASE_URL: Optional[str] = None
    TIMEOUT: Optional[int] = 10  # seconds

class TradetronConfig(AdapterConfig): 
    BASE_URL: Optional[str] = 'https://api.tradetron.tech/api'
    TIMEOUT: Optional[int] = 10
    INDEX_CSV : str =  Path('C:/Users/cawdev/Downloads/tradetron_index_mapping - Sheet1.csv')
    STRATEGY_CSV : str = Path('C:/Users/cawdev/Downloads/tradetron_strategy_mapping - Sheet1.csv')



# # ============================================================================
# # File: core/config.py
# # Production-ready configuration with environment variable support
# # ============================================================================

# import os
# from pathlib import Path
# from datetime import time
# from typing import Set, Optional, Dict, Any
# from dataclasses import dataclass, field
# from loguru import logger


# @dataclass
# class LoggingConfig:
#     """Logging configuration"""
#     log_dir: str = "logs"
#     rotation: str = "500 MB"
#     retention: str = "10 days"
#     compression: str = "zip"
#     level: str = "INFO"
#     enable_console: bool = True
    
#     def __post_init__(self):
#         # Create log directory if it doesn't exist
#         Path(self.log_dir).mkdir(parents=True, exist_ok=True)


# @dataclass
# class MonitoringConfig:
#     """Log monitoring configuration"""
#     log_path: str = "/path/to/your/log/root/folder"
#     target_log_filename: str = "GridLog.csv"
    
#     # Trading hours (IST timezone)
#     allowed_weekdays: Set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})  # Mon-Fri
#     trading_start_time: time = time(9, 15)  # 9:15 AM
#     trading_end_time: time = time(15, 30)   # 3:30 PM
#     enable_premarket: bool = False
#     premarket_start: time = time(9, 0)
#     enable_postmarket: bool = False
#     postmarket_end: time = time(16, 0)
    
#     # Signal validation
#     min_quantity: int = 1
#     max_quantity: int = 10000
#     require_signal_id: bool = True
    
#     # Symbol filtering (None = all allowed)
#     allowed_symbols: Optional[Set[str]] = None
#     blocked_symbols: Set[str] = field(default_factory=set)
    
#     def __post_init__(self):
#         log_path = Path(self.log_path)
#         if not log_path.exists():
#             raise ValueError(f"Log path does not exist: {log_path}")
#         if not log_path.is_dir():
#             raise ValueError(f"Log path is not a directory: {log_path}")


# @dataclass
# class ProcessorConfig:
#     """Order processor configuration"""
#     queue_size: int = 10000
    
#     # Deduplication
#     enable_deduplication: bool = True
#     dedup_window_seconds: int = 60
    
#     # Rate limiting
#     enable_rate_limiting: bool = True
#     max_orders_per_second: int = 10
#     max_orders_per_minute: int = 100
#     max_orders_per_symbol_per_minute: int = 20
    
#     # Health monitoring
#     health_check_interval: int = 60  # seconds


# @dataclass
# class AdapterConfig:
#     """Base adapter configuration"""
#     enabled: bool = True
#     api_key: str = ""
#     api_secret: str = ""
#     timeout: float = 5.0
    
#     def validate(self, adapter_name: str):
#         """Validate adapter configuration"""
#         if self.enabled:
#             if not self.api_key:
#                 raise ValueError(f"{adapter_name}: API key is required")
#             if not self.api_secret:
#                 raise ValueError(f"{adapter_name}: API secret is required")


# @dataclass
# class TradetronConfig(AdapterConfig):
#     """Tradetron adapter configuration"""
#     base_url: str = "https://api.tradetron.tech"
#     strategy_id: Optional[str] = None
#     paper_trading: bool = False


# @dataclass
# class AlgobullsConfig(AdapterConfig):
#     """AlgoBulls adapter configuration"""
#     base_url: str = "https://api.algobulls.com"
#     strategy_code: Optional[str] = None
#     broker: str = "zerodha"


# @dataclass
# class ZerodhaConfig(AdapterConfig):
#     """Zerodha adapter configuration"""
#     access_token: str = ""
    
#     def validate(self, adapter_name: str):
#         """Validate Zerodha configuration"""
#         super().validate(adapter_name)
#         if self.enabled and not self.access_token:
#             raise ValueError(f"{adapter_name}: Access token is required")


# @dataclass
# class BinanceConfig(AdapterConfig):
#     """Binance adapter configuration"""
#     testnet: bool = False


# class Config:
#     """
#     Main application configuration
#     Supports environment variables and configuration files
#     """
    
#     def __init__(self, env_file: Optional[str] = None):
#         """
#         Initialize configuration
        
#         Args:
#             env_file: Path to .env file (optional)
#         """
#         # Load environment variables from .env file if provided
#         if env_file and Path(env_file).exists():
#             self._load_env_file(env_file)
        
#         # Initialize sub-configurations
#         self.logging = self._init_logging_config()
#         self.monitoring = self._init_monitoring_config()
#         self.processor = self._init_processor_config()
        
#         # Initialize adapter configurations
#         self.adapters = self._init_adapter_configs()
        
#         # Validate configuration
#         self._validate()
        
#         logger.info("Configuration initialized")
    
#     def _load_env_file(self, env_file: str):
#         """Load environment variables from .env file"""
#         try:
#             with open(env_file, 'r') as f:
#                 for line in f:
#                     line = line.strip()
#                     if line and not line.startswith('#'):
#                         key, value = line.split('=', 1)
#                         os.environ[key.strip()] = value.strip()
#             logger.info(f"Environment variables loaded from {env_file}")
#         except Exception as e:
#             logger.warning(f"Failed to load .env file: {e}")
    
#     def _init_logging_config(self) -> LoggingConfig:
#         """Initialize logging configuration from environment"""
#         return LoggingConfig(
#             log_dir=os.getenv('LOG_DIR', 'logs'),
#             rotation=os.getenv('LOG_ROTATION', '500 MB'),
#             retention=os.getenv('LOG_RETENTION', '10 days'),
#             level=os.getenv('LOG_LEVEL', 'INFO'),
#             enable_console=os.getenv('LOG_ENABLE_CONSOLE', 'true').lower() == 'true',
#         )
    
#     def _init_monitoring_config(self) -> MonitoringConfig:
#         """Initialize monitoring configuration from environment"""
#         # Parse allowed weekdays
#         weekdays_str = os.getenv('ALLOWED_WEEKDAYS', '0,1,2,3,4')
#         allowed_weekdays = {int(d) for d in weekdays_str.split(',')}
        
#         # Parse allowed symbols
#         allowed_symbols_str = os.getenv('ALLOWED_SYMBOLS', '')
#         allowed_symbols = None
#         if allowed_symbols_str:
#             allowed_symbols = {s.strip().upper() for s in allowed_symbols_str.split(',')}
        
#         # Parse blocked symbols
#         blocked_symbols_str = os.getenv('BLOCKED_SYMBOLS', '')
#         blocked_symbols = set()
#         if blocked_symbols_str:
#             blocked_symbols = {s.strip().upper() for s in blocked_symbols_str.split(',')}
        
#         return MonitoringConfig(
#             log_path=os.getenv('MONITOR_LOG_PATH', '/path/to/your/log/root/folder'),
#             target_log_filename=os.getenv('MONITOR_TARGET_FILENAME', 'GridLog.csv'),
#             allowed_weekdays=allowed_weekdays,
#             trading_start_time=self._parse_time(os.getenv('TRADING_START_TIME', '09:15')),
#             trading_end_time=self._parse_time(os.getenv('TRADING_END_TIME', '15:30')),
#             enable_premarket=os.getenv('ENABLE_PREMARKET', 'false').lower() == 'true',
#             premarket_start=self._parse_time(os.getenv('PREMARKET_START', '09:00')),
#             enable_postmarket=os.getenv('ENABLE_POSTMARKET', 'false').lower() == 'true',
#             postmarket_end=self._parse_time(os.getenv('POSTMARKET_END', '16:00')),
#             min_quantity=int(os.getenv('MIN_QUANTITY', '1')),
#             max_quantity=int(os.getenv('MAX_QUANTITY', '10000')),
#             require_signal_id=os.getenv('REQUIRE_SIGNAL_ID', 'true').lower() == 'true',
#             allowed_symbols=allowed_symbols,
#             blocked_symbols=blocked_symbols,
#         )
    
#     def _init_processor_config(self) -> ProcessorConfig:
#         """Initialize processor configuration from environment"""
#         return ProcessorConfig(
#             queue_size=int(os.getenv('QUEUE_SIZE', '10000')),
#             enable_deduplication=os.getenv('ENABLE_DEDUPLICATION', 'true').lower() == 'true',
#             dedup_window_seconds=int(os.getenv('DEDUP_WINDOW_SECONDS', '60')),
#             enable_rate_limiting=os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true',
#             max_orders_per_second=int(os.getenv('MAX_ORDERS_PER_SECOND', '10')),
#             max_orders_per_minute=int(os.getenv('MAX_ORDERS_PER_MINUTE', '100')),
#             max_orders_per_symbol_per_minute=int(os.getenv('MAX_ORDERS_PER_SYMBOL_PER_MINUTE', '20')),
#             health_check_interval=int(os.getenv('HEALTH_CHECK_INTERVAL', '60')),
#         )
    
#     def _init_adapter_configs(self) -> Dict[str, AdapterConfig]:
#         """Initialize adapter configurations from environment"""
#         adapters = {}
        
#         # Tradetron
#         adapters['tradetron'] = TradetronConfig(
#             enabled=os.getenv('TRADETRON_ENABLED', 'false').lower() == 'true',
#             api_key=os.getenv('TRADETRON_API_KEY', ''),
#             api_secret=os.getenv('TRADETRON_API_SECRET', ''),
#             base_url=os.getenv('TRADETRON_BASE_URL', 'https://api.tradetron.tech'),
#             strategy_id=os.getenv('TRADETRON_STRATEGY_ID'),
#             paper_trading=os.getenv('TRADETRON_PAPER_TRADING', 'false').lower() == 'true',
#             timeout=float(os.getenv('TRADETRON_TIMEOUT', '5.0')),
#         )
        
#         # AlgoBulls
#         adapters['algobulls'] = AlgobullsConfig(
#             enabled=os.getenv('ALGOBULLS_ENABLED', 'false').lower() == 'true',
#             api_key=os.getenv('ALGOBULLS_API_KEY', ''),
#             api_secret=os.getenv('ALGOBULLS_API_SECRET', ''),
#             base_url=os.getenv('ALGOBULLS_BASE_URL', 'https://api.algobulls.com'),
#             strategy_code=os.getenv('ALGOBULLS_STRATEGY_CODE'),
#             broker=os.getenv('ALGOBULLS_BROKER', 'zerodha'),
#             timeout=float(os.getenv('ALGOBULLS_TIMEOUT', '5.0')),
#         )
        
#         # Zerodha
#         adapters['zerodha'] = ZerodhaConfig(
#             enabled=os.getenv('ZERODHA_ENABLED', 'false').lower() == 'true',
#             api_key=os.getenv('ZERODHA_API_KEY', ''),
#             api_secret=os.getenv('ZERODHA_API_SECRET', ''),
#             access_token=os.getenv('ZERODHA_ACCESS_TOKEN', ''),
#             timeout=float(os.getenv('ZERODHA_TIMEOUT', '5.0')),
#         )
        
#         # Binance
#         adapters['binance'] = BinanceConfig(
#             enabled=os.getenv('BINANCE_ENABLED', 'false').lower() == 'true',
#             api_key=os.getenv('BINANCE_API_KEY', ''),
#             api_secret=os.getenv('BINANCE_API_SECRET', ''),
#             testnet=os.getenv('BINANCE_TESTNET', 'false').lower() == 'true',
#             timeout=float(os.getenv('BINANCE_TIMEOUT', '5.0')),
#         )
        
#         return adapters
    
#     def _parse_time(self, time_str: str) -> time:
#         """Parse time string in HH:MM format"""
#         try:
#             hour, minute = map(int, time_str.split(':'))
#             return time(hour, minute)
#         except Exception as e:
#             logger.warning(f"Failed to parse time '{time_str}': {e}. Using default.")
#             return time(9, 15)
    
#     def _validate(self):
#         """Validate configuration"""
#         # Validate enabled adapters
#         for name, adapter in self.adapters.items():
#             if adapter.enabled:
#                 try:
#                     adapter.validate(name.title())
#                 except ValueError as e:
#                     logger.error(f"Configuration validation failed: {e}")
#                     raise
    
#     def get_enabled_adapters(self) -> Dict[str, AdapterConfig]:
#         """Get all enabled adapters"""
#         return {
#             name: config 
#             for name, config in self.adapters.items() 
#             if config.enabled
#         }
    
#     def to_dict(self) -> Dict[str, Any]:
#         """Convert configuration to dictionary"""
#         return {
#             'logging': self.logging.__dict__,
#             'monitoring': {
#                 **self.monitoring.__dict__,
#                 'allowed_weekdays': list(self.monitoring.allowed_weekdays),
#                 'allowed_symbols': list(self.monitoring.allowed_symbols) if self.monitoring.allowed_symbols else None,
#                 'blocked_symbols': list(self.monitoring.blocked_symbols),
#             },
#             'processor': self.processor.__dict__,
#             'adapters': {
#                 name: config.__dict__ 
#                 for name, config in self.adapters.items()
#             }
#         }
    
#     def print_config(self):
#         """Print configuration summary (without sensitive data)"""
#         logger.info("=" * 70)
#         logger.info("Configuration Summary")
#         logger.info("=" * 70)
        
#         logger.info(f"Logging:")
#         logger.info(f"  - Directory: {self.logging.log_dir}")
#         logger.info(f"  - Level: {self.logging.level}")
#         logger.info(f"  - Rotation: {self.logging.rotation}")
        
#         logger.info(f"Monitoring:")
#         logger.info(f"  - Log path: {self.monitoring.log_path}")
#         logger.info(f"  - Target file: {self.monitoring.target_log_filename}")
#         logger.info(f"  - Trading hours: {self.monitoring.trading_start_time} - {self.monitoring.trading_end_time}")
#         logger.info(f"  - Allowed weekdays: {self.monitoring.allowed_weekdays}")
        
#         logger.info(f"Processor:")
#         logger.info(f"  - Queue size: {self.processor.queue_size}")
#         logger.info(f"  - Deduplication: {self.processor.enable_deduplication}")
#         logger.info(f"  - Rate limiting: {self.processor.enable_rate_limiting}")
        
#         logger.info(f"Adapters:")
#         enabled_adapters = self.get_enabled_adapters()
#         if enabled_adapters:
#             for name in enabled_adapters:
#                 logger.info(f"  - {name.title()}: Enabled")
#         else:
#             logger.warning("  - No adapters enabled!")
        
#         logger.info("=" * 70)


# # ============================================================================
# # Example .env file
# # ============================================================================

# ENV_FILE_EXAMPLE = """
# # ============================================================================
# # Trading Signal Processor Configuration
# # Save this as .env in your project root
# # ============================================================================

# # Logging Configuration
# LOG_DIR=logs
# LOG_LEVEL=INFO
# LOG_ROTATION=500 MB
# LOG_RETENTION=10 days
# LOG_ENABLE_CONSOLE=true

# # Monitoring Configuration
# MONITOR_LOG_PATH=/path/to/your/log/root/folder
# MONITOR_TARGET_FILENAME=GridLog.csv

# # Trading Hours (IST)
# ALLOWED_WEEKDAYS=0,1,2,3,4
# TRADING_START_TIME=09:15
# TRADING_END_TIME=15:30
# ENABLE_PREMARKET=false
# PREMARKET_START=09:00
# ENABLE_POSTMARKET=false
# POSTMARKET_END=16:00

# # Signal Validation
# MIN_QUANTITY=1
# MAX_QUANTITY=10000
# REQUIRE_SIGNAL_ID=true

# # Symbol Filtering (comma-separated, leave empty for all)
# ALLOWED_SYMBOLS=
# BLOCKED_SYMBOLS=

# # Processor Configuration
# QUEUE_SIZE=10000
# ENABLE_DEDUPLICATION=true
# DEDUP_WINDOW_SECONDS=60
# ENABLE_RATE_LIMITING=true
# MAX_ORDERS_PER_SECOND=10
# MAX_ORDERS_PER_MINUTE=100
# MAX_ORDERS_PER_SYMBOL_PER_MINUTE=20
# HEALTH_CHECK_INTERVAL=60

# # Tradetron Adapter
# TRADETRON_ENABLED=true
# TRADETRON_API_KEY=your_api_key_here
# TRADETRON_API_SECRET=your_api_secret_here
# TRADETRON_BASE_URL=https://api.tradetron.tech
# TRADETRON_STRATEGY_ID=your_strategy_id
# TRADETRON_PAPER_TRADING=false
# TRADETRON_TIMEOUT=5.0

# # AlgoBulls Adapter
# ALGOBULLS_ENABLED=false
# ALGOBULLS_API_KEY=your_api_key_here
# ALGOBULLS_API_SECRET=your_api_secret_here
# ALGOBULLS_BASE_URL=https://api.algobulls.com
# ALGOBULLS_STRATEGY_CODE=your_strategy_code
# ALGOBULLS_BROKER=zerodha
# ALGOBULLS_TIMEOUT=5.0

# # Zerodha Adapter
# ZERODHA_ENABLED=false
# ZERODHA_API_KEY=your_api_key_here
# ZERODHA_API_SECRET=your_api_secret_here
# ZERODHA_ACCESS_TOKEN=your_access_token_here
# ZERODHA_TIMEOUT=5.0

# # Binance Adapter
# BINANCE_ENABLED=false
# BINANCE_API_KEY=your_api_key_here
# BINANCE_API_SECRET=your_api_secret_here
# BINANCE_TESTNET=true
# BINANCE_TIMEOUT=5.0
# """

