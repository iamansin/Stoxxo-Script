import os
import csv
from typing import Dict, Optional, Union
from datetime import datetime
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from core.models import OrderType, Providers
from loguru import logger
from core.config import TradetronConfig

class VariableCache:
    """
    Fast in-memory cache for strategy tokens and index mappings.
    Loads data from CSV files at startup and provides O(1) access.
    """
    def __init__(self):
        load_dotenv()
        self._strategy_tokens: Dict[tuple, str] = {}  # (strategy, provider) -> token
        self._index_mappings: Dict[str, str] = {}  # (index, provider) -> value
        self.provider_config = TradetronConfig()
        self._load_mappings()


    def _load_mappings(self):
        """Load mappings from CSV files specified in environment variables"""
        try:
            # Load strategy tokens
            strategy_file = self.provider_config.STRATEGY_CSV
            if strategy_file and Path(strategy_file).exists():
                logger.info(f"Loading strategy mappings from: {strategy_file}")
                with open(strategy_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        strategy = row['strategy']
                        provider = Providers.TRADETRON.value  # Default to tradetron
                        token = row['token']
                        self._strategy_tokens[(strategy, provider)] = token
                        logger.info(f"Loaded strategy: {strategy} ({provider}) -> {token}")
                
                logger.info(f"Loaded {len(self._strategy_tokens)} strategy mappings")
            else:
                logger.error(f"Strategy mapping file not found: {strategy_file}")

            # Load index mappings
            index_file = self.provider_config.INDEX_CSV
            if index_file and Path(index_file).exists():
                logger.info(f"Loading index mappings from: {index_file}")
                with open(index_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        index = row['index']
                        value = row['value']
                        self._index_mappings[index] = value
                        logger.info(f"Loaded index: {index}) -> {value}")
                
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

    def get_index_mapping(self, index: str , order_type: OrderType) -> Optional[str]:
        """Get mapped value for an index. O(1) operation."""
        
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
                
            return str(numeric_value)  # Convert back to string as that's what the API expects
            
        except ValueError as e:
            logger.error(f"Error converting mapping value '{value}' to integer for index: {index}")
            return None
            

    def reload(self):
        """Reload mappings from files"""
        self._strategy_tokens.clear()
        self._index_mappings.clear()
        self._load_mappings()