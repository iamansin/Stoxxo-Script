import os
import asyncio
from core.adapters import BaseAdapter
from typing import List, Dict, Any, Optional
from core.models import OrderObj
from loguru import logger

class OrderProcessor:
    """Processes orders from queue and sends to dispatcher"""

    def __init__(self, max_queue_size: int = 10000):
        self.order_queue = asyncio.Queue(maxsize=max_queue_size)
        self.adapters: List[BaseAdapter] = []
        self.running = False
        self._processing_tasks: set[asyncio.Task] = set()
        
    def register_adapter(self, adapter: BaseAdapter):
        """Register an adapter for order dispatch"""
        self.adapters.append(adapter)
        logger.info(f"Registered adapter: {adapter.provider.value}")

    async def add_order(self, batch: Dict[str, Any]):
        """Add order to async queue"""
        try:
            logger.debug(f"Adding order batch to queue: {len(batch)}")
            await self.order_queue.put(batch)
        except asyncio.QueueFull:
            logger.warning("Order queue is full, dropping order")

        except Exception as e:
            logger.error(f"Error while adding order to queue: {e}")
            self.error_count += 1

    async def start_processing(self):
        """Main processing loop"""
        self.running = True
        
        try:
            while self.running:
                try:
                    # Get order batch from queue with a timeout
                    try:
                        batch = await asyncio.wait_for(self.order_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue  # Allows the loop to check self.running

                    logger.debug(f"Processing batch of {len(batch)} orders")
                    task = asyncio.create_task(self._dispatch_and_log(batch))
                    self._processing_tasks.add(task)
                    task.add_done_callback(self._processing_tasks.discard)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Processing error: {e}")
                    
        except Exception as e:
            logger.error(f"Main processing loop error: {e}")

    async def _dispatch_and_log(self, order_batch: List[Dict[str, Any]]):
        """
        Dispatch orders to all adapters concurrently and log responses.
        This is fire-and-forget to not block the main processing loop.
        """
        try:
            result = await self.dispatch(order_batch)
            return result 
        except Exception as e:
            logger.error(f"Dispatch error: {e}")
    
    async def dispatch(self, trade_batch: List[Dict[str, Any]]):
        """
        Dispatch processed orders to ALL adapters simultaneously.
        This is the fast, non-blocking implementation you requested.
        """
        if not self.adapters:
            logger.warning("No adapters registered")
            return
        
        logger.info(f"Dispatching {len(trade_batch)} orders to {len(self.adapters)} adapters")
        
        # Create tasks for ALL adapters to send orders concurrently
        # This ensures no adapter waits for another
        adapter_tasks = [
            adapter.send_order(trade_batch) 
            for adapter in self.adapters
        ]
        
        # Execute all adapter tasks simultaneously
        # return_exceptions=True ensures one adapter's failure doesn't affect others
        results = await asyncio.gather(*adapter_tasks, return_exceptions=True)

        return results                                              

    async def stop(self):
        """Stop the processing loop and wait for pending tasks"""
        self.running = False
        if self._processing_tasks:
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)
        logger.info(f"Stopped. Processor!!")


