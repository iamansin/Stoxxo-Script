import asyncio
from datetime import datetime
import os 
import sys
from loguru import logger
import unittest
from unittest.mock import AsyncMock, patch
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.order_processor import OrderProcessor
from core.models import OrderObj, OrderType, Exchange, ProductType, OptionType
 # Assuming OrderObj is in core.models
SAMPLE_ORDER_DATA = {
    "strategy_tag": "TestStrategy",
    "index": "NIFTY",
    "strike": "18000",
    "quantity": "50",
    "expiry": "2023-12-28",
    "order_type": OrderType.BUY,
    "exchange": Exchange.NFO,
    "product": ProductType.NRML,
    "option_type": OptionType.CE,
    "actual_time": datetime(2023, 1, 1, 10, 0, 0),
    "parse_time": datetime(2023, 1, 1, 10, 0, 1),
    "stoxxo_order": "some_stoxxo_order_string",
    "processing_gap": 1000
}
class TestOrderProcessor(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up the test environment before each test."""
        self.processor = OrderProcessor()

        # Create sample order objects for testing
        self.sample_orders_1 = [
            OrderObj(**SAMPLE_ORDER_DATA, order_id="test001"),
            OrderObj(**SAMPLE_ORDER_DATA, order_id="test002"),
        ]
        self.sample_orders_2 = [
            OrderObj(**SAMPLE_ORDER_DATA, order_id="test003"),
        ]

    async def test_add_order(self):
        """Test that orders can be added to the queue."""
        self.assertEqual(self.processor.order_queue.qsize(), 0)
        
        # Add a batch of orders
        await self.processor.add_order(self.sample_orders_1)
        
        # Check that the queue size has increased
        self.assertEqual(self.processor.order_queue.qsize(), 1)
        
        # Verify the content of the queue
        queued_batch = await self.processor.order_queue.get()
        self.assertEqual(queued_batch, self.sample_orders_1)

    @patch('core.order_processor.OrderProcessor._dispatch_and_log', new_callable=AsyncMock)
    async def test_start_and_stop_processing(self, mock_dispatch_and_log):
        """Test the main processing loop's start and stop functionality."""
        
        # Add some batches to the queue
        await self.processor.add_order(self.sample_orders_1)
        await self.processor.add_order(self.sample_orders_2)
        self.assertEqual(self.processor.order_queue.qsize(), 2)
        print(f"Queue size before processing: {self.processor.order_queue.qsize()}")

        print(f"Starting processor!!")
        # Start the processing loop as a background task
        processing_task = asyncio.create_task(self.processor.start_processing())
        print(f"Processor started!!")
        # Allow the processor to run for a moment to process items
        await asyncio.sleep(0.1)

        print(f"Stopping processor!!")
        # Stop the processor
        await self.processor.stop()
        
        print(f"Processor stopped!!")
        # Wait for the processing task to finish
        if not processing_task.done():
            print(f"Waiting for processing task to finish!!")
            await processing_task
        print("Checking assertions now!!")
        # Assert that _dispatch_and_log was called for each batch
        self.assertEqual(mock_dispatch_and_log.call_count, 2)
        mock_dispatch_and_log.assert_any_call(self.sample_orders_1)
        mock_dispatch_and_log.assert_any_call(self.sample_orders_2)
        
        # Assert that the queue is now empty
        self.assertTrue(self.processor.order_queue.empty())
        
        # Assert that the processor is no longer running
        self.assertFalse(self.processor.running)

if __name__ == "__main__":
    unittest.main()
