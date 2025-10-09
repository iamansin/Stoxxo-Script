
import asyncio
import threading
from pathlib import Path
from typing import Optional, Set, Any, Dict, Tuple
from datetime import datetime, time, timedelta
import re
from order_processor import OrderProcessor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from loguru import logger
from models import OrderObj, OrderType, Exchange, ProductType, OptionType


class TradingHoursValidator:
    """Validates if current time is within allowed trading hours"""
    
    def __init__(
        self,
        allowed_weekdays: Set[int] = {0, 1, 2, 3, 4},  # Mon-Fri
        trading_start: time = time(1, 15),  # 9:15 AM
        trading_end: time = time(15, 30),   # 3:30 PM
        enable_premarket: bool = False,
        premarket_start: time = time(9, 0),  # 9:00 AM
        enable_postmarket: bool = False,
        postmarket_end: time = time(16, 0),  # 4:00 PM  
    ):
        """
        Initialize trading hours validator
        
        Args:
            allowed_weekdays: Set of allowed weekdays (0=Monday, 6=Sunday)
            trading_start: Market start time
            trading_end: Market end time
            enable_premarket: Allow pre-market orders
            premarket_start: Pre-market start time
            enable_postmarket: Allow post-market orders
            postmarket_end: Post-market end time
        """
        self.allowed_weekdays = allowed_weekdays
        self.trading_start = trading_start
        self.trading_end = trading_end
        self.enable_premarket = enable_premarket
        self.premarket_start = premarket_start
        self.enable_postmarket = enable_postmarket
        self.postmarket_end = postmarket_end
    
    def is_trading_allowed(self, dt: Optional[datetime] = None) -> tuple[bool, str]:
        """
        Check if trading is allowed at given datetime
        
        Returns:
            tuple: (is_allowed, reason)
        """
        logger.debug(f"Validating trading hours for: {dt}")
        if dt is None:  
            dt = datetime.now()
        
        # Check weekday
        if dt.weekday() not in self.allowed_weekdays:
            return False, f"Non-trading day: {dt.strftime('%A')}"
        
        current_time = dt.time()
        
        # Check if within trading hours
        if self.enable_premarket and self.premarket_start <= current_time < self.trading_start:
            return True, "Pre-market hours"
        
        if self.trading_start <= current_time <= self.trading_end:
            return True, "Regular trading hours"
        
        if self.enable_postmarket and self.trading_end < current_time <= self.postmarket_end:
            return True, "Post-market hours"
        
        return False, f"Outside trading hours: {current_time.strftime('%H:%M:%S')}"


class OrderParser:
    """Parses and validates trading orders from log lines"""
    
    def __init__(
        self,
        min_quantity: int = 1,
        max_quantity: int = 10000,
    ):
        """
        Initialize order parser
        
        Args:
            min_quantity: Minimum allowed quantity
            max_quantity: Maximum allowed quantity
            queue: Async queue for processed orders
        """
        self.min_quantity = min_quantity
        self.max_quantity = max_quantity
        # self.queue = queue or asyncio.Queue()
        
    def _parse_symbol_details(self, symbol_str: str) -> tuple[str, str, str, OptionType]:
        """Parse symbol string into components"""
        # Example: "NIFTY 7TH OCT 25900 CE"
        parts = symbol_str.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid symbol format: {symbol_str}")
            
        index = parts[0]
        expiry = f"{parts[1]} {parts[2]}"  # "7TH OCT"
        strike = parts[3]
        option_type = OptionType.CE if parts[4] == "CE" else OptionType.PE
        
        return index, expiry, strike, option_type

    def _parse_datetime(self, time_str: str) -> datetime:
        """
        Parse time string into datetime with millisecond precision
        Args:
            time_str: Time string in format "HH:MM:SS:mmm"
        Returns:
            datetime object with millisecond precision
        """
        try:
            # Split the time string into components
            hour, minute, second, ms = map(int, time_str.split(':'))
            
            # Get current date components
            now = datetime.now()
            
            # First create datetime with current date
            dt = datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=minute,
                second=second,
                microsecond=ms * 1000  # Convert milliseconds to microseconds
            )
            
            # If the time is in the future compared to now, it's probably from yesterday
            if dt > now:
                dt = dt - timedelta(days=1)
            # If the time difference is more than 12 hours in the past, it's probably from today
            elif (now - dt).total_seconds() > 43200:  # More than 12 hours
                dt = dt + timedelta(days=1)
            
            logger.debug(f"Parsed time {time_str} to {dt} (current time: {now})")
            return dt
            
        except Exception as e:
            logger.error(f"Error parsing datetime {time_str}: {e}")
            return datetime.now()

    def process_log_line(self, line: str) -> Optional[OrderObj]:
        """Process a single log line and create OrderObj if valid"""
        try:
            logger.debug(f"Processing log line: {line.strip()}")
            # Split CSV line
            parts = line.strip().split(',')
            if len(parts) < 5 or parts[1] != "TRADING" or "Initiating Order Placement" not in parts[2]:
                return None

            timestamp, log_type, order_details, strategy, test_flag, portfolio = parts

            # Extract order details from the message
            details = {}
            for item in order_details.split(';'):
                item = item.strip()
                if ': ' in item:
                    key, value = item.split(': ', 1)
                    details[key] = value.strip(' ;')
            
            # Parse symbol details
            index, expiry, strike, option_type = self._parse_symbol_details(details['Symbol'])
            
            # Parse timestamps with millisecond precision
            actual_time = self._parse_datetime(timestamp)
            parse_time = datetime.now()
            
            # Create OrderObj
            order = OrderObj(
                order_id=details.get('Leg ID'),
                strategy_tag=strategy,
                index=index,
                strike=strike,
                quantity=details['Qty'],
                expiry=expiry,
                order_type=OrderType.BUY if details['Txn'] == 'BUY' else OrderType.SELL,
                exchange=Exchange.NFO,  # Assuming NFO for now
                product=ProductType.NRML,  # Default to NRML
                option_type=option_type,
                actual_time=actual_time,
                parse_time=parse_time,
                stoxxo_order=line,  # Store original log line
                processing_gap=int((parse_time - actual_time).total_seconds() * 1000)
            )
            
            # Validate the order
            if not self._validate_order(order):
                return None
                
            return order
            
        except Exception as e:
            logger.error(f"Error processing log line: {e}")
            return None
            
    def _validate_order(self, order: OrderObj) -> bool:
        """Validate the created order"""
        try:
            logger.debug(f"Validating order: {order}")
            quantity = int(order.quantity)
            if not (self.min_quantity <= quantity <= self.max_quantity):
                logger.error(f"Invalid quantity: {quantity}")
                return False
                
            if not order.strategy_tag:
                logger.error("Missing required fields")
                return False
                
            return True
            
        except ValueError:
            logger.error(f"Invalid quantity format: {order.quantity}")
            return False
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False


class GridLogEventHandler(FileSystemEventHandler):
    """
    Handles file system events for GridLog.csv files.
    Optimized for recursive watching with pattern matching 
    """
    
    def __init__(
        self,
        event_loop: asyncio.AbstractEventLoop,
        hours_validator: TradingHoursValidator,
        order_processor: OrderProcessor,
        target_filename: str = "GridLog.csv",
    ):
        """
        Initialize event handler
        
        Args:
            order_processor: OrderProcessor instance to send signals to
            event_loop: Async event loop for thread-safe async operations
            hours_validator: Trading hours validator
            target_filename: Target log filename to monitor
        """
        super().__init__()
        self.event_loop = event_loop
        self.hours_validator = hours_validator
        self.target_filename = target_filename
        self.order_parser = OrderParser()
        self.order_processor = order_processor
        self.file_handle = None
        self.last_position = 0
        
        logger.info(f"GridLogEventHandler initialized | Target: {target_filename}")
    
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
        
        # Check if this is our target file
        file_path = Path(event.src_path)
        if file_path.name != self.target_filename:
            return
        
        logger.debug(f"GridLog modified | Path: {file_path}")
        
        # Process new lines in the file
        self._process_file_changes(file_path)
    
    def on_created(self, event):
        """Handle file creation events (new day's log file)"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if file_path.name != self.target_filename:
            return
        
        logger.info(f"New GridLog detected | Path: {file_path}")
        
        # Close existing handle if any
        self.close()
        
        # Reset position for new file
        self.last_position = 0
        
        # Process the file
        self._process_file_changes(file_path)
    
    def _get_file_handle(self, file_path: Path) -> tuple[Any, int]:
        """Get or create file handle and last position"""
        if self.file_handle is None:
            try:
                self.file_handle = open(file_path, 'r', encoding='utf-8', errors='ignore')
                self.file_handle.seek(0, 2)  # Seek to end
                self.last_position = self.file_handle.tell()
                logger.info(f"Opened new file handle: {file_path}")
            except Exception as e:
                logger.error(f"Error opening file {file_path}: {e}")
                return None, 0
                
        return self.file_handle, self.last_position

    def _process_file_changes(self, file_path: Path):
        """Process new lines added to the file using efficient batch processing"""
        try:
            handle, last_position = self._get_file_handle(file_path)
            if not handle:
                return

            # Read new content
            handle.seek(last_position)
            new_lines = handle.readlines()
            self.last_position = handle.tell()

            if not new_lines:
                return

            logger.debug(f"Processing {len(new_lines)} new lines | File: {file_path.name}")

            # Check if trading is allowed before processing batch
            is_allowed, hours_reason = self.hours_validator.is_trading_allowed()
            if not is_allowed:
                logger.warning(f"Trading not allowed: {hours_reason}")
                return

            # Batch process all lines
            orders = []
            for line in new_lines:
                try:
                    if order := self.order_parser.process_log_line(line):
                        orders.append(order)
                except Exception as e:
                    logger.error(f"Error processing line in {file_path.name}: {e}")
                    continue

            # If we have orders, send them to processor
            if orders:
                self.event_loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self.order_processor.add_order(orders)
                )
                logger.info(f"Queued {len(orders)} orders for processing from {file_path.name}")

        except Exception as e:
            logger.error(f"Error in file processing: {file_path.name} - {e}")

    def close(self):
        """Clean up file handle"""
        if self.file_handle:
            try:
                self.file_handle.close()
                self.file_handle = None
                self.last_position = 0
                logger.info("Closed file handle")
            except Exception as e:
                logger.error(f"Error closing file handle: {e}")
                pass



class LogMonitor:
    """
    Monitors log directories recursively for GridLog.csv files
    Production-ready with automatic daily rotation handling
    """
    
    def __init__(
        self,
        log_path: str,
        order_processor,
        target_filename: str = "GridLog.csv",
        # Trading hours configuration
        allowed_weekdays: Set[int] = {0, 1, 2, 3, 4},  # Mon-Fri
        trading_start: time = time(1, 15),
        trading_end: time = time(15, 30),
        enable_premarket: bool = False,
        enable_postmarket: bool = False,
        # Order validation configuration
        min_quantity: int = 1,
        max_quantity: int = 10000,
    ):
        """
        Initialize log monitor with recursive watching
        
        Args:
            log_path: Root path to monitor (will watch all subdirectories)
            order_processor: OrderProcessor instance
            target_filename: Filename to watch for (e.g., "GridLog.csv")
            allowed_weekdays: Allowed trading weekdays
            trading_start: Market start time
            trading_end: Market end time
            enable_premarket: Allow pre-market trading
            enable_postmarket: Allow post-market trading
            min_quantity: Minimum order quantity
            max_quantity: Maximum order quantity
            allowed_symbols: Whitelist of symbols (None = all allowed)
            blocked_symbols: Blacklist of symbols
        """
        self.log_path = Path(log_path)
        self.order_processor = order_processor
        self.target_filename = target_filename
        
        # Validators
        self.hours_validator = TradingHoursValidator(
            allowed_weekdays=allowed_weekdays,
            trading_start=trading_start,
            trading_end=trading_end,
            enable_premarket=enable_premarket,
            enable_postmarket=enable_postmarket,
        )

        self.observer = None
        self.event_handler: Optional[GridLogEventHandler] = None
        
        # Verify log path exists
        if not self.log_path.exists():
            raise ValueError(f"Log path does not exist: {self.log_path}")
        
        if not self.log_path.is_dir():
            raise ValueError(f"Log path is not a directory: {self.log_path}")
        
        logger.info(
            f"LogMonitor initialized | "
            f"Path: {self.log_path} | "
            f"Target: {target_filename} | "
            f"Recursive: True"
        )
    
    def start(self, event_loop: asyncio.AbstractEventLoop):
        """
        Start monitoring log directory recursively
        
        Args:
            event_loop: Async event loop for thread-safe operations
            
        Returns:
            Observer instance
        """
        # Create event handler
        self.event_handler = GridLogEventHandler(
            order_processor=self.order_processor,
            event_loop=event_loop,
            hours_validator=self.hours_validator,
            target_filename=self.target_filename,
        )
        
        # Create observer
        self.observer = Observer()
        
        # Schedule recursive watching
        # recursive=True will monitor all subdirectories automatically
        self.observer.schedule(
            self.event_handler,
            str(self.log_path),
            recursive=True  # KEY: This handles daily folder changes automatically
        )
        
        self.observer.start()
        
        logger.info(
            f"LogMonitor started | "
            f"Watching: {self.log_path} | "
            f"Recursive: True | "
            f"Target file: {self.target_filename}"
        )
        
        return self.observer
    
    def stop(self):
        """Stop monitoring and cleanup resources"""
        logger.info("Stopping LogMonitor...")
        if self.event_handler:
            self.event_handler.close()  # Close file handles
            
        if self.observer:
            self.observer.stop()
            logger.info("LogMonitor stopped")

