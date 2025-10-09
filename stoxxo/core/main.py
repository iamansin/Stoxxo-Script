import os 
# main.py
import asyncio
import signal
import sys
sys.path
import platform
from pathlib import Path
from typing import Optional
import threading
from log_listner import LogMonitor
from order_processor import OrderProcessor
from adapters import TradetronAdapter
from config import Config, TradetronConfig
from loguru import logger
from logging_config import setup_logging

# Setup logging
setup_logging()

# Configure event loop based on platform
if platform.system() != 'Windows':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop event loop")
    except ImportError:
        logger.warning("uvloop not available, using default event loop")
else:
    # Use WindowsProactorEventLoop for better performance on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    logger.info("Using Windows Proactor event loop for optimal performance")



class OrderProcessingSystem:
    """Main orchestrator for the order processing system"""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.observer: Optional[threading.Thread] = None
        # Initialize components
        self.order_processor = OrderProcessor(
            max_queue_size=config.QUEUE_SIZE,
        )

        self.log_monitor = LogMonitor(
            log_path=config.LOG_PATH,
            order_processor=self.order_processor
        )
        
        # Register adapters
        self._register_adapters()

    def _register_adapters(self):
        """Register trading platform adapters"""
        if self.config.ENABLE_TRADETRON:
            self.order_processor.register_adapter(
                TradetronAdapter(TradetronConfig())
            )
        
        # if self.config.ENABLE_ALGOBULLS:
        #     self.order_processor.register_adapter(
        #         AlgobullsAdapter(self.config.ALGOBULLS_CONFIG, self)
        #     )
    
    async def start(self):
        """Start all components of the system"""
        self.running = True
        logger.info("Starting order Processing System...")
        
        # Start watchdog observer (it handles its own threading)
        logger.info("Starting log monitor...")
        self.observer = self.log_monitor.start(asyncio.get_running_loop())
        logger.info("Log monitor started.")

        # Start async tasks
        logger.info("Starting processing tasks...")
        await self.order_processor.start_processing()

    async def stop(self):
        """Stop all components gracefully"""
        if not self.running:
            return
            
        self.running = False
        logger.info("Stopping Order Processing System...")

        # Stop the log monitor thread
        self.log_monitor.stop()

        # Stop the order processor
        await self.order_processor.stop()
        
        logger.info("System stopped successfully")

async def main():
    """Main entry point"""
    config = Config()
    system = OrderProcessingSystem(config)
    
    stop_event = asyncio.Event()

    def signal_handler(signum, frame):
        # Use call_soon_threadsafe to safely set the event from a signal handler
        asyncio.get_event_loop().call_soon_threadsafe(stop_event.set)

    # Register signal handlers the traditional way
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("System starting... Press Ctrl+C to exit.")
    
    system_task = asyncio.create_task(system.start())
    
    try:
        # Wait for either the system to crash or a shutdown signal
        await asyncio.wait([
            system_task,
            asyncio.create_task(stop_event.wait()) 
        ], return_when=asyncio.FIRST_COMPLETED)
    except Exception as e:
        logger.error(f"Error during execution: {e}")
    finally:
        logger.info("Shutdown signal received. Cleaning up...")
        
        # Graceful shutdown
        await system.stop()
        
        # Cancel the main task to ensure it exits
        if not system_task.done():
            system_task.cancel()
            try:
                await system_task
            except asyncio.CancelledError:
                logger.info("System task cancelled successfully.")

if __name__ == "__main__":
    asyncio.run(main())



