import os 
# main.py
import asyncio
import sys
sys.path
import platform
from pathlib import Path
from typing import Optional
import threading
from core.log_listner import LogMonitor
from core.order_processor import OrderProcessor
from core.adapters import TradetronAdapter
from core.config import Config, TradetronConfig
from loguru import logger
from core.logging_config import setup_logging

# Setup logging
setup_logging()



# Configure event loop based on platform
if platform.system() != 'Windows':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop event loop")
    except ImportError:
        logger.warning("uvloop not available, trying to install...")
        try:
            os.system(f"{sys.executable} -m pip install uvloop")
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except Exception as e:
            logger.error(f"Failed to install uvloop: {e}")
            logger.info("Falling back to default asyncio event loop")
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
            order_processor=self.order_processor,
            trading_start=config.trading_start_time,
            trading_end=config.trading_end_time,    
            allowed_weekdays=config.allowed_weekdays,
            enable_premarket=config.enable_premarket,   
            enable_postmarket=config.enable_postmarket,
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




