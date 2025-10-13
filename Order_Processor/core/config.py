# /stock-signal-monitor/config.py

from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing_extensions import Optional, Set
from datetime import time
import json
from typing import Dict, Any

class AdapterConfig(BaseModel):
    """Configuration for adapters"""
    TIMEOUT: Optional[int] = 10  # seconds

class TradetronConfig(AdapterConfig): 
    TIMEOUT: Optional[int] = 10
    BASE_URL: Optional[str] = "https://api.tradetron.tech/api"
    
class AlgotestConfig(AdapterConfig): 
    TIMEOUT: Optional[int] = 10

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


