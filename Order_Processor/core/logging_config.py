
from loguru import logger
import sys
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import pytz

def get_ist_time():
    """Get current time in IST"""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def get_daily_log_dir(base_dir: str = "logs_folder") -> Path:
    """Get daily log directory path in IST"""
    ist_now = get_ist_time()
    daily_dir = Path(base_dir) / ist_now.strftime('%Y-%m-%d')
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    # Create .gitkeep to preserve empty directories
    gitkeep = daily_dir / '.gitkeep'
    if not gitkeep.exists():
        gitkeep.touch()
        
    return daily_dir

class OrderLogProcessor:
    """Process order logs and convert to CSV"""
    def __init__(self, base_dir: str, provider: str = None):
        self.base_dir = Path(base_dir)
        self.provider = provider

    def _get_csv_file_for_record(self, record_time: datetime) -> Path:
        """Determine the correct daily CSV file based on the log record's timestamp."""
        daily_dir = self.base_dir / record_time.strftime('%Y-%m-%d')
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        # Create .gitkeep to preserve empty directories
        gitkeep = daily_dir / '.gitkeep'
        if not gitkeep.exists():
            gitkeep.touch()
            
        return daily_dir / f"{self.provider or 'orders'}.csv"

    def _setup_csv(self, csv_file: Path):
        """Setup CSV file with headers if it doesn't exist."""
        if not csv_file.exists() or csv_file.stat().st_size == 0:
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Log_time','Stoxxo_Timestamp', 'Stoxxo_Latency', 'Recieve_Timestamp', 
                    'Sent_Timestamp', 'Application_Latency', 'Pipeline_Latency', 'Strategy',
                    'Stoxxo_Order', 'order_summary', 'Mapped_order', 'order_status', 'error_message'  
                ])
    
    def process_log(self, record: Dict[str, Any]) -> str:
        """Process log record and write to the correct daily CSV."""
        try:
            # Determine the correct CSV file for this log's timestamp
            csv_file = self._get_csv_file_for_record(record['time'])
            self._setup_csv(csv_file)

            # Extract order details from record
            message = record['message']
            extra = record['extra']
            
            # Convert order data to CSV row
            if isinstance(message, str):
                try:
                    # Try parsing if message is JSON string
                    data = json.loads(message)
                except json.JSONDecodeError:
                    data = {'message': message}
            else:
                data = message
            
            # Ensure data is a dictionary
            if not isinstance(data, dict):
                data = {'message': str(data)}
            
            # Extract values for each column with defaults
            row_data = [
                record['time'].strftime('%Y-%m-%d %H:%M:%S.%f'),  # Log timestamp,                                # Log level
                data.get('stoxxo_timestamp', 'None'),                 # Stoxxo_Timestamp
                data.get('stoxxo_latency', 'None'),                   # Stoxxo_Latency
                data.get('application_timestamp', 
                    record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')), # Application_Timestamp
                data.get('sent_timestamp', 'None'),                    # Sent_Timestamp
                data.get('application_latency', 'None'),              # Application_Latency
                data.get('pipeline_latency', 'None'),                  # Pipeline_Latency
                data.get('strategy', 'None'),                            # Strategy
                data.get('stoxxo_order', 'None'),        # Stoxxo_Order as JSON string
                data.get('order_summary', 'None'),                    # order_summary
                json.dumps(data.get('mapped_order', {})),         # Mapped_order as JSON string
                data.get('order_status', 'None'),                     # order_status
                data.get('error_message', 'None')                     # error_message
            ]
            
            # Write to CSV
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(row_data)
            
            # Return formatted message for log file
            return f"{json.dumps(data, indent=None)}"
        except Exception as e:
            return f"Error processing order log: {e} | Raw: {message}"


def setup_logging(
    log_level: str = "INFO",
    base_log_dir: str = "logs_folder",
    rotation: str = "00:00",  # Rotate at midnight
    retention: str = "30 days",
    enable_console: bool = True
):
    """
    Configure logging for the entire application.
    Call this ONCE at application startup.
    
    The logger will automatically:
    - Create daily folders in format YYYY-MM-DD under logs_folder/
    - Rotate logs at midnight IST
    - Compress old logs
    - Maintain separate logs for errors, orders, etc.
    - Clean up logs older than retention period
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        base_log_dir: Base directory for logs (daily folders will be created here)
        rotation: When to rotate logs (default: midnight IST)
        retention: How long to keep old logs
        enable_console: Whether to output to console
    """
    
    # Remove default handler
    logger.remove()
    
    # Get daily log directory (in IST)
    # The {time} placeholder ensures logs are written to the correct daily folder
    log_dir_format = Path(base_log_dir) / "{time:YYYY-MM-DD}"
    
    # Initialize processors
    order_processor = OrderLogProcessor(base_log_dir, provider=None)  # Generic orders
    provider_processors = {
        'tradetron': OrderLogProcessor(base_log_dir, 'tradetron'),
        'algotrade': OrderLogProcessor(base_log_dir, 'algotrade')
    }
    
    # ========================================================================
    # SINK FUNCTIONS - These intercept log messages and process them
    # ========================================================================
    
    def create_provider_sink(processor, provider_name):
        """
        Creates a custom sink function for provider-specific logging.
        
        How it works:
        1. Loguru calls this sink when a log matches the filter
        2. The 'message' parameter is a loguru Message object
        3. We extract the record (contains time, level, message, extra fields)
        4. Pass the record to our processor to write to CSV
        5. No return value needed - this is a "side effect" function
        
        Args:
            processor: OrderLogProcessor instance for this provider
            provider_name: Name of the provider (for debugging)
        """
        def sink(message):
            try:
                # message.record contains all log information
                record = message.record
                # Process and write to CSV
                processor.process_log(record)
            except Exception as e:
                print(f"Error in {provider_name} sink: {e}", file=sys.stderr)
        
        return sink
    
    def order_sink(message):
        """
        Custom sink for generic order logging.
        
        How it works:
        1. Receives the log message from loguru
        2. Extracts the record containing all log data
        3. Passes it to the order processor to write to orders.csv
        
        This runs BEFORE the message goes to orders.log file,
        so we get both CSV and log file output.
        """
        try:
            record = message.record
            order_processor.process_log(record)
        except Exception as e:
            print(f"Error in order sink: {e}", file=sys.stderr)
    
    # ========================================================================
    # 1. ALL LOGS (main log file)
    # ========================================================================
    logger.add(
        log_dir_format / "all.log",
        rotation=rotation,
        retention=retention,
        compression="zip",
        enqueue=True,        
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        backtrace=True,
        diagnose=True,
    )
    
    # ========================================================================
    # 2. ERROR LOGS ONLY (separate file for quick error checking)
    # ========================================================================
    logger.add(
        log_dir_format / "errors.log",
        rotation=rotation,
        retention=retention,
        compression="zip",
        enqueue=True,
        level="ERROR",         # Only ERROR and CRITICAL
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        backtrace=True,
        diagnose=True,
    )
    
    # ========================================================================
    # 3. PROVIDER-SPECIFIC LOGGERS (CSV only, no log file)
    # ========================================================================
    # These intercept logs like: logger.bind(tradetron=True).info(order_data)
    # and ONLY write to tradetron.csv (not to any .log file)
    
    for provider_name, processor in provider_processors.items():
        logger.add(
            create_provider_sink(processor, provider_name),
            level="INFO",
            # Filter: only process if the provider name is in extra fields
            # e.g., logger.bind(tradetron=True) adds {'tradetron': True} to extra
            filter=lambda record, p=provider_name: p in record["extra"]
        )
    
    # ========================================================================
    # 4. TRADING ORDERS LOGS (both .log file AND .csv file)
    # ========================================================================
    # First sink: writes to orders.csv
    logger.add(
        order_sink,
        level="INFO",
        filter=lambda record: "order" in record["extra"]  # Triggered by logger.bind(order=True)
    )
    
    # Second sink: writes to orders.log file
    logger.add(
        log_dir_format / "orders.log",
        rotation=rotation,
        retention=retention,
        compression="zip",
        enqueue=True,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        filter=lambda record: "order" in record["extra"]
    )
    
    # ========================================================================
    # 5. CONSOLE OUTPUT (optional, for development)
    # ========================================================================
    if enable_console:
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
            level=log_level,
            enqueue=True,
            colorize=True,
        )
    
    logger.info(f"Logging initialized | Level: {log_level} | Base Directory: {base_log_dir} (IST)")



