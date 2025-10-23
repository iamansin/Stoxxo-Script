# /stock-signal-monitor/config.py

from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing_extensions import Optional, Set
from datetime import time
import json
from typing import Dict, Any

class AdapterConfig(BaseModel):
    """Configuration for adapters"""
    TIMEOUT: Optional[int] = None # seconds
    BASE_URL: Optional[str] = None
    GROUP_LIMIT: Optional[int] = 10
    METHOD: str = "GET"
    RATE_LIMITER_ACTIVE: bool = False
    ORDER_DELAY_SECONDS: Optional[float] = None
    GROUPING_ENABLED: bool = False
    RATE_LIMIT: Optional[int]= None
    RATE_LIMIT_PERIOD: Optional[int] = None
    COUNTER_SIZE: Optional[int] = None
    
    @validator('ORDER_DELAY_SECONDS', pre=True)
    def validate_order_delay(cls, v):
        # Normalize None
        if v is None:
            return None

        # If value is a string, try to parse to float (handles '0', '0.0')
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
            try:
                v = float(v)
            except ValueError:
                raise ValueError(f"ORDER_DELAY_SECONDS must be a number or null, got: {v}")

        # At this point, v should be numeric
        if isinstance(v, (int, float)):
            # Treat explicit zero (0 or 0.0) as None per requirement
            if float(v) == 0.0:
                return None
            if v >= 0.0:
                return float(v)

        # Fallback: invalid type
        raise ValueError(f"ORDER_DELAY_SECONDS must be a non-negative number or null, got: {v}")
        

class TradetronConfig(AdapterConfig): 
    """Tradetron-specific configuration"""
    BASE_URL: str = "https://api.tradetron.tech/api"
    METHOD: str = "GET"
    GROUPING_ENABLED: bool = True
    GROUP_LIMIT: int = 40
    RATE_LIMITER_ACTIVE: bool = True
    ORDER_DELAY_SECONDS: Optional[float] = 1.0
    COUNTER_SIZE: int = None
    RATE_LIMIT: int = None
    RATE_LIMIT_PERIOD: int = None
    
    
class AlgotestConfig(AdapterConfig): 
    """Algotest-specific configuration"""
    METHOD: str = "POST"
    GROUP_LIMIT: Optional[int] = None
    RATE_LIMITER_ACTIVE: bool = False
    ORDER_DELAY_SECONDS: Optional[float] = None
    GROUPING_ENABLED: bool = False
    RATE_LIMIT: Optional[int]= None
    RATE_LIMIT_PERIOD: Optional[int] = None
    COUNTER_SIZE: Optional[int] = None

class Config(BaseModel):
    """Central configuration for the system"""
    
    # System settings
    MAX_WORKERS: int = Field(default=4, description="Number of worker threads")
    QUEUE_SIZE: int = Field(default=10000, description="Maximum size of the order queue")
    BATCH_SIZE: int = Field(default=50, description="Number of orders to process in one batch")

    # Log monitoring
    LOG_PATH: Path = Field(default=Path("logs"), description="Path to store log files")
    LOG_FILE_PATTERN: str = Field(default="*.csv", description="Pattern to match log files")

    # Processing settings
    RETRY_ATTEMPTS: int = Field(default=3, description="Number of retry attempts for failed operations")
    RETRY_DELAY: float = Field(default=1.0, description="Delay between retry attempts in seconds")
    PROCESSING_TIMEOUT: int = Field(default=30, description="Timeout for processing operations in seconds")

    # Platform configurations
    ENABLE_TRADETRON: bool = Field(default=True, description="Enable/disable Tradetron integration")
    ENABLE_ALGOTEST: bool = Field(default=False, description="Enable/disable Algobulls integration")
    

    TRADETRON_CONFIG: TradetronConfig = Field(default_factory=TradetronConfig, description="Tradetron specific configuration")
    ALGOTEST_CONFIG: AlgotestConfig = Field(default_factory=AlgotestConfig, description="Algotest specific configuration")

    YAML_PATH: Path = Field(default=Path('config.yaml'), description="Path to YAML configuration file")
    # Trading hours (IST timezone)
    allowed_weekdays: Set[int] = Field(
        default_factory=lambda: {0, 1, 2, 3, 4},
        description="Trading days (0=Monday, 1=Tuesday, ..., 4=Friday)"
    )
    trading_start_time: time = Field(
        default=time(9, 15),
        description="Trading start time (HH:MM)"
    )
    trading_end_time: time = Field(
        default=time(15, 30),
        description="Trading end time (HH:MM)"
    )
    enable_premarket: bool = Field(
        default=False,
        description="Enable pre-market trading"
    )
    premarket_start: time = Field(
        default=time(9, 0),
        description="Pre-market start time (HH:MM)"
    )
    enable_postmarket: bool = Field(
        default=False,
        description="Enable post-market trading"
    )
    postmarket_end: time = Field(
        default=time(16, 0),
        description="Post-market end time (HH:MM)"
    )

    class Config:
        json_encoders = {
            Path: str,
            time: lambda t: f"{t.hour:02d}:{t.minute:02d}"
        }

    @validator('trading_start_time', 'trading_end_time', 'premarket_start', 'postmarket_end', pre=True)
    def validate_time(cls, v):
        if isinstance(v, str):
            try:
                hour, minute = map(int, v.split(':'))
                return time(hour, minute)
            except ValueError as e:
                raise ValueError(f"Invalid time format. Use HH:MM format: {e}")
        return v

    def to_json(self) -> str:
        """Convert config to JSON string"""
        return json.dumps(self.dict(), indent=2, default=str)


