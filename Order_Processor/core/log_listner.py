
import asyncio
from pathlib import Path
from typing import Optional, Set, Any, Dict, Tuple
from datetime import datetime, time, timedelta
import re
from core.order_processor import OrderProcessor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from loguru import logger
from core.models import OrderObj, OrderType, Exchange, ProductType, OptionType
from core.cache_manager import VariableCache

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
        cache_memory : VariableCache,
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
        self.cache_memory = cache_memory
        # self.queue = queue or asyncio.Queue()

    def _format_expiry(self, expiry_str : str, index: str) -> str:
        """
        Parses expiry strings into yyyy-mm-dd format.

        Supports:
        - '7TH OCT'
        - '05 NOV'
        - '16OCT25'
        - 'OCT'
        - 'DEC'
        - 'OCT25' (same as 'OCT')
        """
        expiry_str = expiry_str.strip().upper()
        today = datetime.today()
        current_year = today.year
        current_month = today.month

        # --- 1. Handle compact format: 16OCT25 ---
        try:
            if len(expiry_str) == 7 and expiry_str[:2].isdigit():
                day = int(expiry_str[:2])
                month_str = expiry_str[2:5]
                year = int("20" + expiry_str[5:])
                month = datetime.strptime(month_str, "%b").month
                return datetime(year, month, day).strftime("%Y-%m-%d")
        except Exception:
            pass

        parts = expiry_str.split()

        # --- 2. Handle Day + Month + (optional year): '7TH OCT', '05 NOV' ---
        if len(parts) >= 2:
            try:
                day_str = parts[0].rstrip("STNDRDTH")  # Remove suffix like 7TH → 7
                day = int(day_str)
                month = datetime.strptime(parts[1], "%b").month
                year = current_year
                if len(parts) == 3 and parts[2].isdigit():
                    year = int("20" + parts[2])
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except Exception:
                pass

        # --- 3. Handle Month-only: 'OCT', 'OCT25', 'DEC' ---
        try:
            # Remove year from 'OCT25' to treat like 'OCT'
            if len(expiry_str) > 3 and expiry_str[:3].isalpha():
                month_str = expiry_str[:3]
            else:
                month_str = expiry_str

            # Map input month to current / next / next-to-next
            
            return self.cache_memory.get_monthly_expiry_date(index, month_str)
            
        except Exception:
            raise ValueError(f"Unrecognized expiry format: '{expiry_str}'")

        
    def _parse_symbol_details(self, symbol_str: str) -> tuple[str, str, str, OptionType]:
        """
        Parses option symbol into (index, expiry, strike, option_type).
        
        Supports expiry formats:
        - "7TH OCT"
        - "05 NOV"
        - "16OCT25"
        - "OCT"
        - "OCT25"
        """
        pattern = r"""
            ^\s*
            (?P<index>[A-Z]+)                        # Index
            \s+
            (?:
                (?P<day1>\d{1,2}(?:ST|ND|RD|TH)?)     # Day with suffix (7TH)
                \s+
                (?P<month1>[A-Z]{3})                  # Month (OCT)
                (?:\s*(?P<year1>\d{2}))?              # Optional year
                |
                (?P<compact>\d{1,2}[A-Z]{3}\d{2})     # Compact expiry e.g., 16OCT25
                |
                (?P<month2>[A-Z]{3})(?P<year2>\d{2})? # Month or Month+Year e.g., OCT, OCT25
            )
            \s+
            (?P<strike>\d+)                          # Strike
            \s+
            (?P<option_type>CE|PE|C|P)               # Option Type
            \s*$
        """

        match = re.match(pattern, symbol_str.strip(), re.IGNORECASE | re.VERBOSE)
        if not match:
            logger.error(f"Not able to parse the symbol : {symbol_str}")
            raise ValueError(f"Invalid symbol format: {symbol_str}")

        index = match.group("index").upper()

        # Determine which expiry format matched
        if match.group("compact"):
            expiry = match.group("compact").upper()
        elif match.group("day1") and match.group("month1"):
            expiry = f"{match.group('day1').upper()} {match.group('month1').upper()}"
            if match.group("year1"):
                expiry += match.group("year1")
        elif match.group("month2"):
            expiry = match.group("month2").upper()
            if match.group("year2"):
                expiry += match.group("year2")
        else:
            raise ValueError(f"Invalid expiry format in symbol: {symbol_str}")

        expiry = self._format_expiry(expiry, index)
        strike = match.group("strike")
        opt_raw = match.group("option_type").upper()
        option_type = OptionType.CE if opt_raw in ("CE", "C") else OptionType.PE
        
        if any(not v for v in [index, expiry, strike, option_type]):
            raise ValueError(f"Missing components in symbol: {symbol_str}")

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
            # Split CSV line
            parts = line.strip().split(',')
            if len(parts) < 5 or parts[1] != "TRADING" or "Initiating Order Placement" not in parts[2]:
                return None
       
            timestamp, log_type, order_details, strategy, test_flag, portfolio = parts

            if not self.cache_memory.strategy_is_active(strategy):
                logger.warning(f"Startegy is not active : {strategy} Dropping it's order for {order_details}")
                return None

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
                quantity=int(details['Qty']),
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
            logger.error(f"Error processing log line::{line}   |   {e}")
            return 
            
    def _validate_order(self, order: OrderObj) -> bool:
        """Validate the created order"""
        try:
            logger.debug(f"Validating order: {order}")
            quantity = order.quantity
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
        cache_memory : VariableCache,
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
        self.order_parser = OrderParser(cache_memory)
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

            # Filter out any None orders that might have resulted from inactive strategies or parsing errors
            valid_orders = [order for order in orders if order is not None]

            # If we have valid orders, send them to processor
            if valid_orders:
                self.event_loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self.order_processor.add_order(valid_orders)
                )
                logger.info(f"Queued {len(valid_orders)} orders for processing from {file_path.name}")

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
        cache_memory : VariableCache,
        target_filename: str = "GridLog.csv",
        # Trading hours configuration
        allowed_weekdays: Set[int] = {0, 1, 2, 3, 4, 5},  # Mon-Fri
        trading_start: time = time(1, 15),
        trading_end: time = time(23, 30),
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
        self.cache_memory = cache_memory
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
            cache_memory = self.cache_memory
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

