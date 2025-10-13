import asyncio
from loguru import logger
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from dotenv import load_dotenv
import httpx
from core.models import (
    OrderObj,
    Providers,
    OrderStatus,
    )
from core.cache_manager import VariableCache
from core.config import AdapterConfig, TradetronConfig, AlgotestConfig
load_dotenv()
    

class BaseAdapter:
    """Base adapter class"""

    def __init__(self, provider: Providers, config: AdapterConfig, cache_memory : VariableCache):
        self.provider : Providers= provider
        self.active = True  # Set to True by default
        self.timeout = config.TIMEOUT
        self.http_client = httpx.AsyncClient(timeout=self.timeout)
        self.variable_cache = cache_memory
        self.provider_method = None
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
            raise e


    async def _process_single_order(self, order: OrderObj) -> None:
        """Process a single order order"""
        try:
            # Map the order to adapter-specific format
            mapped_order , url = self.map_order(order)
            if mapped_order is None:
                logger.error(f"{self.provider.value} - Order mapping failed for order: {order.order_id}")
                order.update_object({'status': OrderStatus.FAILED, 
                                     'sent_time': None,
                                     'error_message': 'Mapping failed',
                                     'adapter_name': self.provider.value,
                                     'mapped_order': None}).dump_data_to_log(self.provider)
                return # Stop processing this order if mapping fails

            result, error = await self._send_mapped_order(mapped_order, order, url)
            order.update_object({'status': result, 
                                 'adapter_name': self.provider.value,
                                 'mapped_order': mapped_order,
                                 'error_message': error}).dump_data_to_log(self.provider)
            return
            
        except Exception as e:
            logger.error(f"{self.provider.value} - Error processing order: {e}")
            order.update_object({'status': OrderStatus.FAILED, 
                                 'sent_time': datetime.now() if not order.sent_time else order.sent_time,  # Changed from utcnow() to now()
                                 'adapter_name': self.provider.value,
                                 'mapped_order': None,
                                 'error_message': str(e)
            }).dump_data_to_log(self.provider)
            raise e
        
    def map_order(self, order: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        Map generic order order to adapter-specific format.
        Override this in your adapter implementation.
        """
        raise NotImplementedError("Subclasses must implement map_order()")
        #implement token mangment also....
       

    async def _send_mapped_order(self, mapped_order: Dict[str, Any], order: OrderObj, url: str) -> Tuple[OrderStatus, Optional[str]]:
        """
        Send the mapped order to the broker/exchange with retry logic.
        
        Args:
            mapped_order: The order data mapped to provider's format
            order: Original order object
            url: The endpoint URL
            
        Returns:
            Tuple of (OrderStatus, Optional[str] error message)
        """
        if order.status != OrderStatus.PENDING:
            logger.warning(f"{self.provider} - Order {order.order_id} is not in PENDING state. Current state: {order.status}")
            return OrderStatus.FAILED, "Order not in PENDING state"

        # Retry configuration
        max_retries = 1  # One immediate retry
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Record attempt time
                attempt_time = datetime.now()
                is_retry = retry_count > 0
                
                if is_retry:
                    logger.info(f"{self.provider} - Retry attempt {retry_count} for order {order.order_id}")
                else:
                    logger.info(f"{self.provider} - Sending order {order.order_id}: {mapped_order}")

                headers = {
                    "Content-Type": "text/plain" if self.provider_method == 'POST' else "application/json",
                }

                # Send request based on method
                order.sent_time = attempt_time
                if self.provider_method == 'POST':
                    response = await self.http_client.post(
                        url,
                        data=mapped_order.get('payload', None),
                        headers=headers,
                        timeout=self.timeout
                    )
                elif self.provider_method == 'GET' :
                    response = await self.http_client.get(
                        url,
                        params=mapped_order,#Not sending headers here for now (Tradetron specific)
                        timeout=self.timeout
                    )
                
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.provider_method}")
                
                # Process response
                if response.status_code == 200:
                    
                    logger.info(f"{self.provider} - Order {order.order_id} sent successfully")
                    return OrderStatus.SENT, None

                # Handle specific error cases
                elif response.status_code == 429:  # Too Many Requests
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"{self.provider} - Rate limit hit. Retry after {retry_after} s")
                    if retry_count < max_retries:
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue
                    return OrderStatus.FAILED, "Rate limit exceeded"

                elif response.status_code >= 500:  # Server errors - retry
                    if retry_count < max_retries:
                        retry_count += 1
                        continue
                    return OrderStatus.FAILED, f"Server error: {response.status_code}"

                else:  # Other errors - don't retry
                    logger.error(f"{self.provider} - Order {order.order_id} failed: {response.status_code} - {response.text}")
                    return OrderStatus.FAILED, f"HTTP {response.status_code}: {response.text}"

            except httpx.TimeoutException:
                last_error = "Request timeout"
                if retry_count < max_retries:
                    retry_count += 1
                    continue
                    
            except httpx.RequestError as exc:
                logger.error(f"{self.provider} - Request error for {exc.request.url!r}: {exc}")
                return OrderStatus.FAILED, str(exc)
                
            except Exception as e:
                logger.error(f"{self.provider} - Unexpected error: {str(e)}")
                return OrderStatus.FAILED, str(e)

            retry_count += 1

        # If we get here, all retries failed
        return OrderStatus.FAILED, last_error or "Max retries exceeded"


class TradetronAdapter(BaseAdapter):
    """Tradetron adapter"""

    def __init__(self, config: TradetronConfig, cache_memory : VariableCache):
        super().__init__(provider=Providers.TRADETRON, config=config, cache_memory = cache_memory)
        self.base_url = config.BASE_URL
        self.provider_method = 'GET'
        # Additional Tradetron-specific initialization

    def map_order(self, order: OrderObj) -> Dict[str, Any]:
        """Map to Tradetron-specific format"""
        # Get cached values with error checking
        url = self.variable_cache.get_strategy_url(order.strategy_tag, self.provider)
        if not url:
            raise ValueError(f"No token found for strategy: {order.strategy_tag}")
        if isinstance(url, list):
            url = url[0]  # Use the first URL if multiple
        
        index_value = self.variable_cache.get_index_mapping(
            order.index,
            order_type=order.order_type
        )
        if not index_value:
            raise ValueError(f"No mapping found for index: {order.index}")
        
        
        return {
            'auth-token': url.split('token=')[-1],  # Extract token from URL
            'key1': 'INDEX',
            'value1': index_value,
            'key2': 'OP_TYPE',
            'value2': order.option_type.value,
            'key3': 'STRIKE',
            'value3': order.strike,
            'key4': 'QUANTITY',
            'value4': order.quantity,
            'key5': 'EXPIRY',
            'value5': order.expiry 
            }, self.base_url
        

    
class AlgotestAdapter(BaseAdapter):
    """AlgoTest adapter"""

    def __init__(self, config: AlgotestConfig, cache_memory : VariableCache):
        super().__init__(provider=Providers.ALGOTEST, config=config, cache_memory = cache_memory)
        self.provider_method = 'POST'
        # Additional AlgoTest-specific initialization

    def map_order(self, order: OrderObj) -> Dict[str, Any]:
        """Map to AlgoTest-specific format"""
        # Get cached values with error checking
        url = self.variable_cache.get_strategy_url(order.strategy_tag, self.provider)
        if not url:
            raise ValueError(f"No token found for strategy: {order.strategy_tag}")
        lot_size = self.variable_cache.get_lot_size(order.index)
        if lot_size is None:    
            raise ValueError(f"No lot size found for index: {order.index}")
        lot = order.quantity//lot_size
        # Convert expiry date from "2025-10-16" format to "251016"
        expiry = order.expiry.replace('-', '')[-6:] 
        instrument = f"{order.index}{expiry}{"C" if order.option_type.value == 1 else "P"}{order.strike}"
        try:
            symbol = f"{instrument} {order.order_type.value} {lot}"
            return {
            'payload': symbol,
           }, url[0] if isinstance(url, list) else url # Handle both single URL and list of URLs
            
        except Exception as e:
            raise ValueError(f"Error calculating lots for index {order.index}: {e}")
        
        
