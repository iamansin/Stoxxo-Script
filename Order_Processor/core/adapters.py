import asyncio
from loguru import logger
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import time
import httpx
from core.models import (
    OrderObj,
    Providers,
    OrderStatus,
    OrderType,
    OptionType
    )
from core.cache_manager import VariableCache
from core.config import AdapterConfig, TradetronConfig, AlgotestConfig
from collections import deque
import random 

class AsyncFixedWindowRateLimiter:
    """
    Fixed window async rate limiter with proper window management.
    
    Example:
        rate_limiter = AsyncFixedWindowRateLimiter(limit=30, period=60)
        await rate_limiter.acquire()  # Acquire a slot
    """

    def __init__(self, limit: int, period: float):
        """
        Args:
            limit: Maximum number of operations allowed per window.
            period: Duration of each window in seconds.
        """
        if not limit or not period:
            return logger.warning("Rate limiter not configured properly; disabled.")
        if limit <= 0 or period <= 0:
            raise ValueError("Rate limit and period must be positive values.")
            
        self.limit = limit
        self.period = period
        self.current_count = 0
        self.window_start = None  # Will be set on first acquire
        self._lock = asyncio.Lock()
        self._waiters = 0  # Track number of waiting tasks

        

    async def acquire(self, tokens: int = 1):
        """
        Acquire tokens from the rate limiter.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        if tokens > self.limit:
            raise ValueError(f"Cannot acquire {tokens} tokens; limit is {self.limit}")
        
        self._waiters += 1
        try:
            while True:
                async with self._lock:
                    now = asyncio.get_event_loop().time()
                    
                    # Initialize window on first use
                    if self.window_start is None:
                        self.window_start = now
                    
                    elapsed = now - self.window_start

                    # Reset window if period has elapsed
                    if elapsed >= self.period:
                        self.window_start = now
                        self.current_count = 0
                        elapsed = 0

                    # Check if we can acquire tokens
                    if self.current_count + tokens <= self.limit:
                        self.current_count += tokens
                        logger.info(f"Tokens acquired: {tokens}. Current: {self.current_count}/{self.limit}")
                        return

                    # Calculate wait time until next window
                    wait_time = self.period - elapsed
                    
                # Release lock before sleeping
                logger.warning(
                    f"Rate limit reached ({self.current_count}/{self.limit}). "
                    f"Waiting {wait_time:.2f}s for window reset. "
                    f"Waiters: {self._waiters}"
                )
                await asyncio.sleep(wait_time)
                # Loop will retry acquisition after sleep
        finally:
            self._waiters -= 1


class OrderGroupingQueue:
    """
    Queue for grouping orders into batches with configurable group limit.
    Thread-safe and async-compatible.
    """
    
    def __init__(self, group_limit: int, provider_name: str):
        """
        Args:
            group_limit: Maximum number of orders per group
            provider_name: Name of the provider (for logging)
        """
        if group_limit <= 0:
            raise ValueError("Group limit must be positive")
        
        self.group_limit = group_limit
        self.provider_name = provider_name
        self._queue: deque = deque()
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        self._closed = False
        
        logger.info(f"{provider_name} - Grouping queue initialized with limit: {group_limit}")
    
    async def enqueue(self, orders: List[Any]) -> None:
        """Add orders to the queue."""
        if not orders:
            return
        
        async with self._lock:
            if self._closed:
                raise RuntimeError("Queue is closed")
            
            self._queue.extend(orders)
            queue_size = len(self._queue)
            
        # Signal that queue has items (outside lock)
        self._not_empty.set()
        
        logger.debug(
            f"{self.provider_name} - Enqueued {len(orders)} orders. "
            f"Queue size: {queue_size}"
        )
    
    async def dequeue_batch(self) -> List[Any]:
        """
        Dequeue up to group_limit orders as a batch.
        Blocks if queue is empty until orders are available or queue is closed.
        
        Returns:
            List of orders (up to group_limit), or empty list if closed
        """
        while True:
            async with self._lock:
                if self._queue:
                    # Extract up to group_limit orders
                    batch_size = min(self.group_limit, len(self._queue))
                    batch = [self._queue.popleft() for _ in range(batch_size)]
                    remaining = len(self._queue)
                    
                    # Clear event if queue is now empty
                    if not self._queue:
                        self._not_empty.clear()
                    
                    logger.info(
                        f"{self.provider_name} - Dequeued batch of {len(batch)} orders. "
                        f"Remaining in queue: {remaining}"
                    )
                    return batch
                
                if self._closed:
                    logger.info(f"{self.provider_name} - Queue closed, returning empty batch")
                    return []
            
            # Wait for orders (outside lock)
            await self._not_empty.wait()
    
    def get_queue_size(self) -> int:
        """Get current queue size (non-blocking, best-effort)."""
        return len(self._queue)
    
    async def close(self) -> None:
        """Close the queue and wake up any waiting consumers."""
        async with self._lock:
            self._closed = True
            self._not_empty.set()
        logger.info(f"{self.provider_name} - Grouping queue closed")


class BaseAdapter:
    """
    Base adapter with configurable fixed-window rate limiter and optional
    order grouping for batch-based providers.
    """

    def __init__(self, provider: Providers, config: AdapterConfig, cache_memory: VariableCache):
        self.provider: Providers = provider
        self.active = True
        self.timeout = config.TIMEOUT
        self.http_client = httpx.AsyncClient(timeout=self.timeout)
        self.variable_cache = cache_memory
        self.provider_method = config.METHOD
        
        # Rate limiting configuration
        self.rate_limiter_active = config.RATE_LIMITER_ACTIVE
        self.rate_limit = config.RATE_LIMIT
        self.period = config.RATE_LIMIT_PERIOD  # seconds
        self.rate_limiter: Optional[AsyncFixedWindowRateLimiter] = AsyncFixedWindowRateLimiter(
            limit=self.rate_limit,
            period=self.period
        )
        
        # Per-order delay (for sequential processing)
        self.order_delay_seconds: float = config.ORDER_DELAY_SECONDS
        
        # Grouping configuration (disabled by default)
        self.grouping_enabled = config.GROUPING_ENABLED
        self.group_limit = config.GROUP_LIMIT
        self._grouping_queue: Optional[OrderGroupingQueue] = None
        self._processor_task: Optional[asyncio.Task] = None
        self.base_url = config.BASE_URL
        
        if self.grouping_enabled:
            self.enable_grouping(group_limit=self.group_limit)
        
        # Format the delay string appropriately
        rate_limit_str = f"{self.rate_limit} orders / {self.period}s" if self.rate_limiter_active else "Disabled"
        delay_str = "Disabled" if self.order_delay_seconds is None else f"{self.order_delay_seconds * 1000:.0f} ms"
        group_info_Str = f"Enabled with : {self.group_limit}" if self.grouping_enabled else "Disabled"
        logger.info(
            f"Adapter '{self.provider.value}' initialized. | "
            f"Rate Limit: [{rate_limit_str}]. | "
            f"Per-Order Delay: [{delay_str}]. | "
            f"Grouping: [{group_info_Str}]."
        )
    
    def enable_grouping(self, group_limit: int):
        """
        Enable order grouping with specified limit.
        Must be called before processing any orders.
        
        Args:
            group_limit: Maximum orders per group
        """
        if self._processor_task is not None:
            raise RuntimeError("Cannot enable grouping after processing has started")
        
        self.grouping_enabled = True
        self.group_limit = group_limit
        self._grouping_queue = OrderGroupingQueue(group_limit, self.provider.value)
        
    async def _start_grouping_processor(self):
        """Start the background processor for grouped orders."""
        if not self.grouping_enabled or self._processor_task is not None:
            return
        
        logger.debug(f"{self.provider.value} - Starting grouping processor")
        self._processor_task = asyncio.create_task(self._process_grouped_orders())
    
    async def _process_grouped_orders(self):
        """
        Background task that continuously processes batches from the grouping queue.
        """
        logger.debug(f"{self.provider.value} - Grouping processor started")

        try:
            while self.active:
                # Dequeue a batch (blocks until available)
                batch = await self._grouping_queue.dequeue_batch()
                
                if not batch:
                    # Queue closed or empty
                    break
                
                # logger.info(
                #     f"{self.provider.value} - Processing grouped batch of {len(batch)} orders"
                # )
                
                try:
                    # Acquire rate limit token before sending
                    if self.rate_limiter_active:
                        await self.rate_limiter.acquire(tokens=1)
                    
                    # Map the batch to a single request
                    mapped_orders, url = self.map_order_batch(batch)
                    
                    if not mapped_orders:
                        logger.error(
                            f"{self.provider.value} - Batch mapping failed for {len(batch)} orders"
                        )
                        self._mark_batch_failed(batch, "Batch mapping failed")
                        continue
                    
                    logger.info(
                        f"{self.provider.value} - Sending grouped batch: "
                        f"{len(batch)} orders -> 1 request"
                    )

                    tasks = []
                    for _mapped_order in mapped_orders:
                        tasks.append(self._send_batch_mapped_order(_mapped_order, url))
                        
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Apply order_delay_seconds as inter-batch delay (except for first batch)
                    if self.order_delay_seconds is not None:
                        logger.info(
                            f"{self.provider.value} - Applying inter-batch delay: "
                            f"{self.order_delay_seconds * 1000:.0f}ms"
                        )
                        await asyncio.sleep(self.order_delay_seconds)
                    
                    # Process results and handle exceptions
                    success = True
                    error_message = None
                
                    
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            success = False
                            error_message = f"Exception in batch: {str(result)}"
                            logger.error(f"{self.provider.value} - Task {i} failed with exception: {result}")
                        elif isinstance(result, tuple) and len(result) == 2:
                            status, err = result
                            if status == OrderStatus.FAILED:
                                success = False
                                error_message = err
                                logger.error(f"{self.provider.value} - Task {i} failed: {err}")
                        else:
                            success = False
                            error_message = f"Unexpected result format: {result}"
                            logger.error(f"{self.provider.value} - Task {i} returned unexpected format: {result}")
                    
                    # Update batch status based on overall success
                    if success:
                        logger.success(
                            f"{self.provider.value} - Grouped batch sent successfully "
                            f"({len(batch)} orders)"
                        )
                        self._mark_batch_success(batch, mapped_orders[0])
                    else:
                        logger.error(
                            f"{self.provider.value} - Grouped batch failed: {error_message}"
                        )
                        self._mark_batch_failed(batch, error_message, mapped_orders[0])
                    
                except Exception as e:
                    logger.error(
                        f"{self.provider.value} - Error processing grouped batch: {e}",
                        exc_info=True
                    )
                    self._mark_batch_failed(batch, str(e))
                    
        except Exception as e:
            logger.critical(
                f"{self.provider.value} - Grouping processor crashed: {e}",
                exc_info=True
            )
        finally:
            logger.info(f"{self.provider.value} - Grouping processor stopped")
    
    def _mark_batch_success(self, batch: List[OrderObj], mapped_order: Dict[str, Any]= None):
        """Mark all orders in batch as successfully sent."""
        sent_time = datetime.now()
        batch[0].update_object({
                'status': OrderStatus.SENT,
                'adapter_name': self.provider.value,
                'sent_time': sent_time,
                'mapped_order': mapped_order,
                'error_message': None
            }).dump_data_to_log(self.provider)
    
    def _mark_batch_failed(self, batch: List[OrderObj], error: str, mapped_order: Dict[str, Any] = None):
        """Mark all orders in batch as failed."""
        batch[0].update_object({
                'status': OrderStatus.FAILED,
                'adapter_name': self.provider.value,
                'sent_time': None,
                'mapped_order': mapped_order,
                'error_message': error
            }).dump_data_to_log(self.provider)

    async def send_order(self, order_batch: List[OrderObj]) -> List[OrderStatus]:
        """
        Sends a batch of orders with optimal performance.
        
        If grouping is enabled, orders are queued and processed by background task.
        Otherwise, uses existing concurrent/sequential processing.
        
        Args:
            order_batch: A list of order objects to be processed.
            
        Returns:
            A list of final statuses for each order in the batch.
        """
        if not self.active:
            logger.warning(
                f"Adapter '{self.provider.value}' is inactive. "
                f"Skipping {len(order_batch)} orders."
            )
            return [OrderStatus.FAILED] * len(order_batch)

        batch_size = len(order_batch)
        logger.info(
            f"'{self.provider.value}' - Processing batch of {batch_size} orders."
        )
        
        # GROUPING MODE: Queue orders for background processing
        if self.grouping_enabled:
            logger.debug(
                f"'{self.provider.value}' - Using grouping mode "
                f"(limit: {self.group_limit})"
            )
            
            # Start processor if not already running
            await self._start_grouping_processor()
            
            # Enqueue orders
            await self._grouping_queue.enqueue(order_batch)
            
            # Return pending status (actual status will be updated by processor)
            # Note: In grouping mode, caller doesn't wait for completion
            return [OrderStatus.PENDING] * batch_size
        
        # NON-GROUPING MODE: Use existing logic
        start_time = asyncio.get_event_loop().time()
        results = []

        try:
            # Strategy 1: No rate limit, no delay = FULL CONCURRENCY (fastest)
            if not self.rate_limiter_active and self.order_delay_seconds is None:
                logger.info(f"'{self.provider.value}' - Using full concurrency mode")
                tasks = [self._process_single_order(order) for order in order_batch]
                await asyncio.gather(*tasks, return_exceptions=False)
                
            # Strategy 2: Rate limit but no delay = CONTROLLED CONCURRENCY
            elif self.rate_limiter_active and self.order_delay_seconds is None:
                # logger.info(
                #     f"'{self.provider.value}' - Using rate-limited concurrency mode"
                # )
                
                async def rate_limited_process(order):
                    await self.rate_limiter.acquire()
                    return await self._process_single_order(order)
                
                tasks = [rate_limited_process(order) for order in order_batch]
                await asyncio.gather(*tasks, return_exceptions=False)
                
            # Strategy 3: Delay configured = SEQUENTIAL with delays
            else:
                logger.info(f"'{self.provider.value}' - Using sequential mode with delays")
                for idx, order in enumerate(order_batch, 1):
                    if self.rate_limiter_active:
                        await self.rate_limiter.acquire()
                    
                    await self._process_single_order(order)
                    
                    if self.order_delay_seconds is not None and idx < batch_size:
                        await asyncio.sleep(self.order_delay_seconds)
                    
                    # if idx % 10 == 0 or idx == batch_size:
                    #     elapsed = asyncio.get_event_loop().time() - start_time
                    #     rate = idx / elapsed if elapsed > 0 else float('inf')
                    #     logger.info(
                    #         f"'{self.provider.value}' - Progress: {idx}/{batch_size} "
                    #         f"({(idx/batch_size)*100:.0f}%) | Rate: {rate:.1f} orders/sec"
                    #     )
            
            # Collect results from order objects
            results = [order.status for order in order_batch]
                        
            total_time = asyncio.get_event_loop().time() - start_time
            actual_rate = batch_size / total_time if total_time > 0 else float('inf')
            logger.success(
                f"'{self.provider.value}' - Batch complete. "
                f"Processed {batch_size} orders in {total_time:.2f}s "
                f"(Average Rate: {actual_rate:.1f} orders/sec)."
            )
            
        except Exception as e:
            logger.critical(
                f"'{self.provider.value}' - Fatal error during batch processing: {e}",
                exc_info=True
            )
            results = [OrderStatus.FAILED] * batch_size
       
        return results
    
    async def _process_single_order(self, order: OrderObj) -> None:
        """Process a single order for all configured URLs"""
        try:
            # Map the order to adapter-specific format
            mapped_orders = self.map_order(order)
            if not mapped_orders:
                logger.error(
                    f"{self.provider.value} - Order mapping failed for "
                    f"order: {order.order_id}"
                )
                order.update_object({
                    'status': OrderStatus.FAILED,
                    'sent_time': None,
                    'error_message': 'Mapping failed',
                    'adapter_name': self.provider.value,
                    'mapped_order': None
                }).dump_data_to_log(self.provider)
                return

            # Send to all URLs concurrently
            tasks = []
            for mapped_order, url in mapped_orders:
                tasks.append(self._send_mapped_order(mapped_order, order.copy(), url))
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful_sends = 0
            errors = []
            
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                else:
                    status, error = result
                    if status == OrderStatus.SENT:
                        successful_sends += 1
                    elif error:
                        errors.append(error)
            
            # Update order status
            if successful_sends == len(tasks):
                final_status = OrderStatus.SENT
                final_error = None
                sent_time = datetime.now()
            elif successful_sends > 0:
                final_status = OrderStatus.FAILED
                final_error = (
                    f"Sent to {successful_sends}/{len(tasks)} URLs. "
                    f"Errors: {'; '.join(errors)}"
                )
                sent_time = None
            else:
                final_status = OrderStatus.FAILED
                final_error = f"Failed to send to all URLs. Errors: {'; '.join(errors)}"
                sent_time = None
            
            order.update_object({
                'status': final_status,
                'adapter_name': self.provider.value,
                'mapped_order': [mo for mo, _ in mapped_orders],
                'error_message': final_error,
                'sent_time': sent_time
            }).dump_data_to_log(self.provider)
            
        except Exception as e:
            logger.error(f"{self.provider.value} - Error processing order: {e}")
            order.update_object({
                'status': OrderStatus.FAILED,
                'sent_time': None,
                'adapter_name': self.provider.value,
                'mapped_order': None,
                'error_message': str(e)
            }).dump_data_to_log(self.provider)
            raise
    
    def map_order(self, order: OrderObj) -> List[Tuple[Dict[str, Any], str]]:
        """
        Map a single order to adapter-specific format.
        Override this in subclasses for non-grouping adapters.
        
        Returns:
            List of (mapped_order, url) tuples
        """
        raise NotImplementedError("Subclasses must implement map_order()")
    
    def map_order_batch(self, orders: List[OrderObj]) -> List[Tuple[Dict[str, Any], str]]:
        """
        Map a batch of orders to adapter-specific format.
        Override this in subclasses that use grouping.
        
        Args:
            orders: List of orders to group and map
            
        Returns:
            List of (mapped_order, url) tuples (typically single element for grouped)
        """
        # Default: map each order individually (no grouping)
        results = []
        for order in orders:
            results.extend(self.map_order(order))
        return results
    
    async def _send_batch_mapped_order(
            self, 
            mapped_orders: Dict[str, Any], 
            url: str
        ) -> Tuple[OrderStatus, Optional[str]]:
            """
            Send a batch of mapped orders to their respective URLs with retry logic.
            
            Args:
                mapped_orders: Dictionary containing the mapped order data.
                url: The endpoint URL to send the order to.
                
            Returns:
                Tuple of (OrderStatus, Optional[str] error message).
            """
            logger.debug(f"Sending batch order to {url}")
            
            max_retries = 1
            retry_count = 0
            last_error = None

            while retry_count <= max_retries:
                try:
                    if retry_count > 0:
                        logger.warning(
                            f"{self.provider} - Retry attempt {retry_count} for batch order"
                        )

                    headers = {
                        "Content-Type": (
                            "text/plain" if self.provider_method == 'POST' 
                            else "application/json"
                        ),
                    }
                    
                    if self.provider_method == 'POST':
                        response = await self.http_client.post(
                            url,
                            json=mapped_orders,
                            headers=headers,
                            timeout=self.timeout
                        )
                    elif self.provider_method == 'GET':
                        response = await self.http_client.get(
                            url,
                            params=mapped_orders,
                            timeout=self.timeout
                        )
                    else:
                        raise ValueError(f"Unsupported HTTP method: {self.provider_method}")

                    if response.status_code == 200:
                        # logger.info(f"{self.provider} - Batch sent successfully")
                        return OrderStatus.SENT, None

                    elif response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', 1))
                        logger.warning(
                            f"{self.provider} - Rate limit hit for batch. "
                            f"Retrying after {retry_after}s"
                        )
                        last_error = "Rate limit exceeded"
                        if retry_count < max_retries:
                            await asyncio.sleep(retry_after)
                            retry_count += 1
                            continue

                    elif response.status_code >= 500:
                        logger.error(
                            f"{self.provider} - Batch server error: "
                            f"{response.status_code} - {response.text}"
                        )
                        last_error = f"Server error: {response.status_code}"
                        if retry_count < max_retries:
                            retry_count += 1
                            continue
                    
                    else:
                        logger.error(
                            f"{self.provider} - Batch failed with non-retriable error: "
                            f"{response.status_code} - {response.text}"
                        )
                        return (
                            OrderStatus.FAILED,
                            f"HTTP {response.status_code}: {response.text}"
                        )

                except httpx.TimeoutException:
                    last_error = "Request timeout"
                    logger.warning(f"{self.provider} - Request timeout for batch order.")
                    if retry_count < max_retries:
                        retry_count += 1
                        continue
                        
                except httpx.RequestError as exc:
                    logger.error(
                        f"{self.provider} - Request error for batch to "
                        f"{exc.request.url!r}: {exc}"
                    )
                    return OrderStatus.FAILED, str(exc)
                    
                except Exception as e:
                    logger.error(
                        f"{self.provider} - Unexpected error sending batch. "
                        f"Exception Type: {type(e).__name__}, "
                        f"Exception Repr: {repr(e)}"
                    )
                    return OrderStatus.FAILED, str(e)

                # Break the loop if we are not continuing to the next retry
                break

            return OrderStatus.FAILED, last_error or "Max retries exceeded"

    async def _send_mapped_order(
        self, 
        mapped_order: Dict[str, Any], 
        order: OrderObj, 
        url: str
    ) -> Tuple[OrderStatus, Optional[str]]:
        """
        Send the mapped order to the provider with retry logic.
        
        Args:
            mapped_order: The order data mapped to provider's format
            order: Original order object
            url: The endpoint URL
            
        Returns:
            Tuple of (OrderStatus, Optional[str] error message)
        """
        if order.status not in [OrderStatus.PENDING, OrderStatus.SENT]:
            logger.warning(
                f"{self.provider} - Order {order.order_id} is not in valid state. "
                f"Current state: {order.status}"
            )

        max_retries = 1
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                is_retry = retry_count > 0
                
                if is_retry:
                    logger.warning(
                        f"{self.provider} - Retry attempt {retry_count} "
                        f"for order {order.order_id}"
                    )
                # else:
                #     logger.info(
                #         f"{self.provider} - Sending order {order.order_id}: "
                #         f"{mapped_order}"
                #     )

                headers = {
                    "Content-Type": (
                        "text/plain" if self.provider_method == 'POST'
                        else "application/json"
                    ),
                }
                
                if self.provider_method == 'POST':
                    response = await self.http_client.post(
                        url,
                        data=mapped_order.get('payload', None),
                        headers=headers,
                        timeout=self.timeout
                    )
                elif self.provider_method == 'GET':
                    response = await self.http_client.get(
                        url,
                        params=mapped_order,
                        timeout=self.timeout
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.provider_method}")
                
                if response.status_code == 200:
                    # logger.info(
                    #     f"{self.provider} - Order {order.order_id} sent successfully"
                    # )
                    return OrderStatus.SENT, None

                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(
                        f"{self.provider} - Rate limit hit. Retry after {retry_after}s | "
                        f"Symbol: {order.index} {order.strike} {order.option_type} | "
                        f"Order ID: {order.order_id}"
                    )
                    if retry_count < max_retries:
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue
                    return OrderStatus.FAILED, "Rate limit exceeded"

                elif response.status_code >= 500:
                    if retry_count < max_retries:
                        retry_count += 1
                        continue
                    return OrderStatus.FAILED, f"Server error: {response.status_code}"

                else:
                    logger.error(
                        f"{self.provider} - Order {order.order_id} failed: "
                        f"{response.status_code} - {response.text}"
                    )
                    return (
                        OrderStatus.FAILED,
                        f"HTTP {response.status_code}: {response.text}"
                    )

            except httpx.TimeoutException:
                last_error = "Request timeout"
                if retry_count < max_retries:
                    retry_count += 1
                    continue
                    
            except httpx.RequestError as exc:
                logger.error(
                    f"{self.provider} - Request error for {exc.request.url!r}: {exc}"
                )
                return OrderStatus.FAILED, str(exc)
                
            except Exception as e:
                logger.error(f"{self.provider} - Unexpected error: {str(e)}")
                return OrderStatus.FAILED, str(e)

            retry_count += 1

        return OrderStatus.FAILED, last_error or "Max retries exceeded"
    
    async def shutdown(self):
        """Gracefully shutdown the adapter."""
        logger.info(f"{self.provider.value} - Shutting down adapter")
        
        self.active = False
        
        # Close grouping queue if active
        if self._grouping_queue:
            await self._grouping_queue.close()
        
        # Wait for processor to finish
        if self._processor_task:
            try:
                await asyncio.wait_for(self._processor_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(
                    f"{self.provider.value} - Processor task did not finish in time"
                )
                self._processor_task.cancel()
        
        # Close HTTP client
        await self.http_client.aclose()
        
        logger.info(f"{self.provider.value} - Adapter shutdown complete")


class TradetronAdapter(BaseAdapter):
    """Tradetron adapter with grouping support"""

    def __init__(self, config: TradetronConfig, cache_memory: VariableCache):
        super().__init__(
            provider=Providers.TRADETRON,
            config=config,
            cache_memory=cache_memory
        ) 
        self.global_conditions_map = {}

        self.counter_size = config.COUNTER_SIZE
        
    def map_order(self, order):
        return order

    def get_global_count(self, condition : str):
        try:
            counter = self.global_conditions_map.get(condition, 0)
            if counter >= self.counter_size:
                #resetting to 1 again
                self.global_conditions_map[condition] = 1
                return 1

            counter += 1
            #updating the new count value in map
            self.global_conditions_map[condition] = counter
            return counter        
        
        except Exception as e:
            logger.error(f"Error while getting counter for signal variable increamentation from global counter : {e}")

    def map_order_batch(self, orders: List[OrderObj]) -> List[Tuple[Dict[str, Any], str]]:
        """
        Map a batch of orders to Tradetron requests.
        
        Groups all orders into payloads with multiple key-value pairs,
        one payload per webhook configuration.
        """
        if not orders:
            logger.warning(f"{self.provider.value} - No orders to map")
            return []
            
        logger.debug(
            f"{self.provider.value} - Starting batch mapping for {len(orders)} orders"
        )
        
        try:
            # Use the first order's strategy tag to get webhook configs
            webhook_configs = self.variable_cache.get_strategy_url(
                orders[0].strategy_tag,
                self.provider
            )
            if not webhook_configs:
                raise ValueError(
                    f"No token found for strategy: {orders[0].strategy_tag}"
                )
            
            if not isinstance(webhook_configs, list):
                webhook_configs = [webhook_configs]
            
            
            # # Build grouped payload
            random_index_val = random.randint(1,10000) 
            mapped_order ={"auth-token" : None}  # Placeholder, will be set per token later
            key_idx = 1
            
            for order in orders:      
                option_type = 'CE' if order.option_type.value == 1 else 'PE'
                # Create condition key for tracking duplicates
                condition = f"{order.index}_{order.order_type.value}_{option_type}"
                condition_num = self.get_global_count(condition)
                
                # Determine buy/sell string for variable names (capitalized)
                buy_sell_cap = 'Buy' if order.order_type == OrderType.BUY else 'Sell'

                mapped_order[f'key{key_idx}'] = condition + str(condition_num)
                mapped_order[f'value{key_idx}'] = random_index_val
                key_idx += 1
                
                # Add Quantity: key{idx}: INDEX_Quantity_CE_Buy1, value{idx}: 75
                mapped_order[f'key{key_idx}'] = f"{order.index}_Quantity_{option_type}_{buy_sell_cap}{condition_num}"
                mapped_order[f'value{key_idx}'] = order.quantity
                key_idx += 1
                
                # Add Strike: key{idx}: INDEX_Strike_CE_Buy1, value{idx}: 25000
                mapped_order[f'key{key_idx}'] = f"{order.index}_Strike_{option_type}_{buy_sell_cap}{condition_num}"
                mapped_order[f'value{key_idx}'] = order.strike
                key_idx += 1
                
                # Add Expiry: key{idx}: INDEX_Expiry_CE_Buy1, value{idx}: 2025-10-20
                mapped_order[f'key{key_idx}'] = f"{order.index}_Expiry_{option_type}_{buy_sell_cap}{condition_num}"
                mapped_order[f'value{key_idx}'] = order.expiry
                key_idx += 1
                
           
            # Create separate mapped orders for each webhook config
            mapped_orders = []
            for wc in webhook_configs:
                # Create a new copy of the mapped order for this token
                current_mapped = mapped_order.copy()
                current_mapped['auth-token'] = wc.url
                
                # Apply the multiplier to quantities for this specific webhook
                for key, value in current_mapped.items():

                    if key.startswith('key') and '_Quantity_' in str(value):
                        # Find the corresponding value key (e.g., if key is 'key2', we want 'value2')
                        value_key = key.replace('key', 'value')
                        if value_key in current_mapped:
                            # Multiply the quantity by the webhook's multiplier
                            current_mapped[value_key] = int(current_mapped[value_key] * wc.multiplier)
                
                mapped_orders.append(current_mapped)
            
            logger.debug(
                f"{self.provider.value} - Prepared grouped payload for {len(mapped_orders)} webhooks. "
                f"Sample mapped data: {mapped_orders[0] if mapped_orders else 'No mappings created'}"
            )
            return mapped_orders, self.base_url
            
        except Exception as e:
            logger.error(f"Error mapping order batch for Tradetron: {e}")
            raise


class AlgotestAdapter(BaseAdapter):
    """AlgoTest adapter (no changes needed)"""

    def __init__(self, config: AlgotestConfig, cache_memory: VariableCache):
        super().__init__(
            provider=Providers.ALGOTEST,
            config=config,
            cache_memory=cache_memory
        )
        # Grouping disabled (default behavior)

    def map_order(self, order: OrderObj) -> List[Tuple[Dict[str, Any], str]]:
        """Map to AlgoTest-specific format for all configured URLs"""
        webhook_configs = self.variable_cache.get_strategy_url(
            order.strategy_tag,
            self.provider
        )
        if not webhook_configs:
            raise ValueError(f"No token found for strategy: {order.strategy_tag}")
        
        if not isinstance(webhook_configs, list):
            webhook_configs = [webhook_configs]
            
        lot_size = self.variable_cache.get_lot_size(order.index)
        if lot_size is None:
            raise ValueError(f"No lot size found for index: {order.index}")
            
        # Convert expiry date from "2025-10-16" format to "251016"
        expiry = order.expiry.replace('-', '')[-6:]
        instrument = (
            f"{order.index}{expiry}"
            f"{'C' if order.option_type.value == 1 else 'P'}"
            f"{order.strike}"
            
        )
        
        mapped_orders = []
        try:
            for webhook_config in webhook_configs:
                quantity = int(order.quantity * webhook_config.multiplier)
                lot = quantity // lot_size
                
                symbol = f"{instrument} {order.order_type.value} {lot}"
                mapped_orders.append((
                    {'payload': symbol},
                    webhook_config.url
                ))
                
            return mapped_orders
            
        except Exception as e:
            raise ValueError(f"Error calculating lots for index {order.index}: {e}")