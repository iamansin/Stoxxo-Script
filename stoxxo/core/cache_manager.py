import os
import csv
from typing import Dict, Optional, Union
from datetime import datetime
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from models import OrderType, Providers
import logging
from config import TradetronConfig

logger = logging.getLogger(__name__)

class VariableCache:
    """
    Fast in-memory cache for strategy tokens and index mappings.
    Loads data from CSV files at startup and provides O(1) access.
    """
    def __init__(self):
        load_dotenv()
        self._strategy_tokens: Dict[tuple, str] = {}  # (strategy, provider) -> token
        self._index_mappings: Dict[tuple, str] = {}  # (index, provider) -> value
        self.provider_config = TradetronConfig()
        self._load_mappings()

    def _load_mappings(self):
        """Load mappings from CSV files specified in environment variables"""
        try:
            # Load strategy tokens
            strategy_file = self.provider_config.STRATEGY_CSV
            if strategy_file and Path(strategy_file).exists():
                logger.info(f"Loading strategy mappings from: {strategy_file}")
                df = pd.read_csv(strategy_file)
                # Log column names for debugging
                logger.info(f"Strategy CSV columns: {df.columns.tolist()}")
                
                # Convert provider names to lowercase for case-insensitive matching
                df['provider'] = df['provider'].str.lower() if 'provider' in df.columns else Providers.TRADETRON.value
                self._strategy_tokens = {
                    (row['strategy'], row['provider']): row['token']
                    for _, row in df.iterrows()
                }
                # Print all loaded strategy mappings
                for (strategy, provider), token in self._strategy_tokens.items():
                    logger.debug(f"Loaded strategy mapping: {strategy} ({provider}) -> {token}")
                logger.info(f"Loaded {len(self._strategy_tokens)} strategy mappings")
            else:
                logger.error(f"Strategy mapping file not found: {strategy_file}")

            # Load index mappings
            index_file = self.provider_config.INDEX_CSV
            if index_file and Path(index_file).exists():
                logger.info(f"Loading index mappings from: {index_file}")
                df = pd.read_csv(index_file)
                # Log column names for debugging
                logger.info(f"Index CSV columns: {df.columns.tolist()}")
                
                # Convert provider names to lowercase for case-insensitive matching
                df['provider'] = df['provider'].str.lower() if 'provider' in df.columns else 'tradetron'
                self._index_mappings = {
                    (row['index'], row['provider']): row['value']
                    for _, row in df.iterrows()
                }
                # Print all loaded index mappings
                for (index, provider), value in self._index_mappings.items():
                    logger.debug(f"Loaded index mapping: {index} ({provider}) -> {value}")
                logger.info(f"Loaded {len(self._index_mappings)} index mappings")
            else:
                logger.error(f"Index mapping file not found: {index_file}")

        except Exception as e:
            logger.error(f"Error loading mappings: {e}")
            raise

    def get_strategy_token(self, strategy: str, provider: Providers) -> Optional[str]:
        """Get token for a strategy. O(1) operation."""
        # Try exact match first
        key = (strategy, provider.value)
        token = self._strategy_tokens.get(key)
        
        if token is None:
            # Try fallback to default provider
            fallback_key = (strategy, 'tradetron')
            token = self._strategy_tokens.get(fallback_key)
            
            if token is None:
                logger.error(f"No token found for strategy: {strategy} with provider: {provider.value}")
            else:
                logger.debug(f"Using fallback token for strategy: {strategy}")
                
        return token

    def get_index_mapping(self, index: str, provider: Union[Providers, str], order_type: OrderType) -> Optional[str]:
        """Get mapped value for an index. O(1) operation."""
        
        # Try exact match first
        key = (index, provider)
        value = self._index_mappings.get(key)
        
        if value is None:
            logger.error(f"No mapping found for index: {index} with provider: {provider}")
            return None
        try:
            # Convert to integer for manipulation
            numeric_value = int(value)
            
            # Apply sign based on order type
            if order_type == OrderType.SELL:
                numeric_value *= -1
                
            return str(numeric_value)  # Convert back to string as that's what the API expects
            
        except ValueError as e:
            logger.error(f"Error converting mapping value '{value}' to integer for index: {index}")
            return None
            

    def reload(self):
        """Reload mappings from files"""
        self._strategy_tokens.clear()
        self._index_mappings.clear()
        self._load_mappings()