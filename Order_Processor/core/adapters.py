import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
import httpx
from core.models import (
    OrderObj,
    Providers,
    OrderStatus,
)
from core.cache_manager import VariableCache
from core.config import AdapterConfig, TradetronConfig
load_dotenv()

logger = logging.getLogger(__name__)        

class BaseAdapter:
    """Base adapter class"""

    def __init__(self, provider: Providers, config: AdapterConfig):
        self.provider : Providers= provider
        self.active = True  # Set to True by default
        self.base_url = config.BASE_URL
        self.timeout = config.TIMEOUT
        self.http_client = httpx.AsyncClient(timeout=self.timeout)
        self.variable_cache = VariableCache()
        
        # Validate configuration and activate
        if not self.base_url:
            logger.error(f"Adapter {self.provider.value} has no base URL configured.")
            self.active = False
        else:
            logger.info(f"Adapter {self.provider.value} initialized and active")

    async def send_order(self, order_batch: List[OrderObj]) -> None:
        """
        Send a batch of orders to the adapter.
        Each line in order_batch represents a order to be sent.
        
        Args:
            order_batch: List of orders to process
            
        Returns:
            List of orderResponse objects, one per order
        """

        if not self.base_url:
            logger.error(f"Adapter {self.provider.value} has no base URL configured.")
            return []
        
        if not self.active:
            logger.warning(f"Adapter {self.provider.value} is inactive. Skipping order dispatch.")
            return []

        logger.info(f"Adapter {self.provider.value} - Dispatching {len(order_batch)} orders")
        # Process each order order concurrently
        try:
            tasks = [self._process_single_order(order) for order in order_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Adapter {self.provider.value} - Completed dispatching orders")
            return 
        
        except Exception as e:
            logger.error(f"Adapter {self.provider.value} - Error dispatching orders: {e}")
            return []


    async def _process_single_order(self, order: OrderObj) -> None:
        """Process a single order order"""
        try:
            # Map the order to adapter-specific format
            mapped_order : Dict[str, Any] = self.map_order(order)
            if mapped_order is None:
                logger.error(f"{self.provider.value} - Order mapping failed for order: {order.order_id}")
                order.update_object({'status': OrderStatus.FAILED, 
                                     'sent_time': None,
                                     'error_message': 'Mapping failed',
                                     'adapter_name': self.provider.value,
                                     'mapped_order': None}).dump_data_to_log(self.provider)
                return # Stop processing this order if mapping fails

            result, exc = await self._send_mapped_order(mapped_order, order)
            order.update_object({'status': result, 
                                 'adapter_name': self.provider.value,
                                 'mapped_order': mapped_order,
                                 'error_message': exc}).dump_data_to_log(self.provider)
            return
            
        except Exception as e:
            logger.error(f"{self.provider.value} - Error processing order: {e}")
            order.update_object({'status': OrderStatus.FAILED, 
                                 'sent_time': datetime.now() if not order.sent_time else order.sent_time,  # Changed from utcnow() to now()
                                 'adapter_name': self.provider.value,
                                 'mapped_order': None,
                                 'error_message': str(e)
            }).dump_data_to_log(self.provider)
            return 
    def map_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map generic order order to adapter-specific format.
        Override this in your adapter implementation.
        """
        raise NotImplementedError("Subclasses must implement map_order()")
        #implement token mangment also....
       

    async def _send_mapped_order(self, mapped_order: Dict[str, Any], order: OrderObj) -> OrderStatus:
        """
        Actually send the mapped order to the broker/exchange.
        Override this in your adapter implementation.
        """
        logger.info(f"{self.provider} - Sending order: {mapped_order}")
        try:
            if order.status == OrderStatus.PENDING:
                order.sent_time = datetime.now() 
                response = await self.http_client.get(self.base_url, params=mapped_order)
                response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
                
                if '200' not in str(response.status_code):
                    logger.error(f"{self.provider} - Order {order.order_id} failed with status code {response.status_code}: {response.text}")
                    return (OrderStatus.FAILED, f"HTTP {response.status_code}: {response.text}")
                # updating object for sent time and status after successful sending
                
                logger.info(f"{self.provider} - Order {order.order_id} sent successfully.")
                return (OrderStatus.SENT, None)

            
        except httpx.HTTPStatusError as exc:
            logger.error(f"{self.provider} - HTTP Error: {exc.response.status_code} - {exc.response.text}")
            return (OrderStatus.FAILED, exc.response.text)
        except httpx.RequestError as exc:
            logger.error(f"{self.provider} - An error occurred while requesting {exc.request.url!r}: {exc}")
            return (OrderStatus.FAILED, str(exc))    
        except Exception as e:
            logger.error(f"{self.provider} - Error sending order: {str(e)}")
            return (OrderStatus.FAILED, str(e))


class TradetronAdapter(BaseAdapter):
    """Tradetron adapter"""

    def __init__(self, config: TradetronConfig):
        super().__init__(provider=Providers.TRADETRON, config=config)
        # Additional Tradetron-specific initialization
        try:
            # Verify that we can load strategy tokens and index mappings
            self.variable_cache._load_mappings()
            logger.info(f"Tradetron adapter initialized successfully with mappings")
        except Exception as e:
            logger.error(f"Failed to initialize Tradetron adapter: {e}")
            self.active = False

        
    def _convert_expiry_format(self, expiry_str: str) -> str:
        """
        Convert expiry from '7TH OCT' format to 'YYYY-MM-DD'.
        If year is not provided, use current year.
        """
        try:
            # Remove ordinal indicators (TH, ST, ND, RD)
            expiry_str = expiry_str.upper()
            for suffix in ['TH', 'ST', 'ND', 'RD']:
                expiry_str = expiry_str.replace(suffix, '')
            
            # Parse the date with current year
            current_year = datetime.now().year
            date_str = f"{expiry_str.strip()} {current_year}"
            
            # Parse and format the date
            expiry_date = datetime.strptime(date_str, "%d %b %Y")
            return expiry_date.strftime("%Y-%m-%d")
            
        except Exception as e:
            logger.error(f"Error converting expiry date '{expiry_str}': {e}")
            return expiry_str  # Return original if parsing fails

    def map_order(self, order: OrderObj) -> Dict[str, Any]:
        """Map to Tradetron-specific format"""
        # Convert expiry to YYYY-MM-DD format
        formatted_expiry = self._convert_expiry_format(order.expiry)
        
        # Get cached values with error checking
        token = self.variable_cache.get_strategy_token(order.strategy_tag, provider=self.provider)
        if not token:
            raise ValueError(f"No token found for strategy: {order.strategy_tag}")
            
        index_value = self.variable_cache.get_index_mapping(
            order.index,
            order_type=order.order_type
        )
        if not index_value:
            raise ValueError(f"No mapping found for index: {order.index}")

        mapped_order = {
            'auth-token': token,
            'key1': 'INDEX',
            'value1': index_value,
            'key2': 'OP_TYPE',
            'value2': order.option_type.value,
            'key3': 'STRIKE',
            'value3': order.strike,
            'key4': 'QUANTITY',
            'value4': order.quantity,
            'key5': 'EXPIRY',
            'value5': formatted_expiry
        }
        logger.info(f"Mapped order for Tradetron: {mapped_order}")
        return mapped_order