import pytest
import os 
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.models import OrderObj, Providers, OrderStatus, OrderType, Exchange, ProductType, OptionType
from core.logging_config import setup_logging
from datetime import datetime
from pathlib import Path
import csv
import json
import shutil
from loguru import logger

# Sample data for testing
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

@pytest.fixture(scope="module")
def log_dir():
    """Create a temporary log directory for tests and clean up afterward."""
    test_log_dir = Path("test_logs")
    # Clean up any previous test runs
    if test_log_dir.exists():
        shutil.rmtree(test_log_dir)
    
    # Setup logging to use this directory
    setup_logging(base_log_dir=str(test_log_dir))
    
    # Yield the directory path to the tests
    yield test_log_dir
    
    # Teardown: clean up the log directory after tests are done
    # logger.remove()
    # if test_log_dir.exists():
    #     shutil.rmtree(test_log_dir)

def test_tradetron_specific_logging(log_dir: Path):
    """
    Tests logging using logger.bind(tradetron=True).info()
    and validates the structure of tradetron.csv.
    """
    order = OrderObj(**SAMPLE_ORDER_DATA)
    order.update_object({
        "sent_time": datetime(2023, 1, 1, 10, 0, 2),
        "pipeline_latency": 1000,
        "end_to_end_latency": 2000,
        "status": OrderStatus.SENT,
        "mapped_order": {"broker_id": "XYZ123"}
    })
    
    # Log the order using the specific provider
    order.dump_data_to_log(Providers.TRADETRON)
    
    # Get the expected daily directory
    daily_log_dir = log_dir / datetime.now().strftime('%Y-%m-%d')
    tradetron_csv_path = daily_log_dir / "tradetron.csv"

    # 1. Check if the CSV file was created
    assert tradetron_csv_path.exists(), "tradetron.csv was not created."

    # 2. Read the CSV and validate its content
    with open(tradetron_csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

        # 2a. Validate headers
        expected_headers = [
            'Log_time', 'Stoxxo_Timestamp', 'Stoxxo_Latency', 'Application_Timestamp', 
            'Sent_Timestamp', 'Application_Latency', 'Pipeline_Latency', 'Strategy',
            'Stoxxo_Order', 'order_summary', 'Mapped_order', 'order_status', 'error_message'
        ]
        assert header == expected_headers

        # 2b. Validate row count
        assert len(rows) == 1, "Expected exactly one data row in tradetron.csv."
        
        # 2c. Validate data in the row
        row = rows[0]
        assert row[1] == order.actual_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        assert row[2] == f"{order.processing_gap}ms"
        assert row[4] == order.sent_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        assert row[5] == f"{order.pipeline_latency}ms"
        assert row[6] == f"{order.end_to_end_latency}ms"
        assert row[8] == order.stoxxo_order
        assert json.loads(row[10]) == order.mapped_order
        assert row[11] == order.status.value

def test_order_log_structure_and_csv(log_dir: Path):
    """
    Tests logging using logger.bind(order=True).info()
    and validates the structure of orders.log and orders.csv.
    """
    order = OrderObj(**SAMPLE_ORDER_DATA)
    order.update_object({
        "status": OrderStatus.FAILED,
        "error_message": "Insufficient funds"
    })
    
    # Use a generic order log
    log_data = order.dump_data_to_log(Providers.TRADETRON) # Assuming TRADETRON is a specific provider
    
    # Get expected paths
    daily_log_dir = log_dir / datetime.now().strftime('%Y-%m-%d')
    orders_csv_path = daily_log_dir / "orders.csv"
    orders_log_path = daily_log_dir / "orders.log"

    # 1. Check if files were created
    assert orders_csv_path.exists(), "orders.csv was not created."
    assert orders_log_path.exists(), "orders.log was not created."

    # 2. Validate orders.csv content
    with open(orders_csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
        
        expected_headers = [
            'Log_time','Stoxxo_Timestamp', 'Stoxxo_Latency', 'Application_Timestamp', 
            'Sent_Timestamp', 'Application_Latency', 'Pipeline_Latency', 'Strategy',
            'Stoxxo_Order', 'order_summary', 'Mapped_order', 'order_status', 'error_message'
        ]
        assert header == expected_headers
        assert len(rows) >= 1, "Expected at least one data row in orders.csv."
        
        # Check the last added row
        last_row = rows[-1]
        assert last_row[11] == OrderStatus.FAILED.value 
        assert last_row[12] == "Insufficient funds"

    # 3. Validate orders.log content
    with open(orders_log_path, 'r') as f:
        log_content = f.read()
        # Ensure the log file contains the JSON representation of our order
        assert order.order_id in log_content
        assert OrderStatus.FAILED.value in log_content
        assert "Insufficient funds" in log_content

