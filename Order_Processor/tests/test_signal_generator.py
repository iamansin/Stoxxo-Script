import os
import time
from datetime import datetime
import random
from pathlib import Path
from loguru import logger

    

def generate_order_signal():
    """Generate a random order signal with realistic parameters"""
    indexes = ["NIFTY", "BANKNIFTY", "SENSEX"]
    index = random.choice(indexes)
    leg_id = random.randint(1000, 2000)
    strikes = [24000, 24500, 25000, 25500, 26000]
    strike = random.choice(strikes)
    qty = 525
    txn = random.choice(['BUY', 'SELL'])
    option_type = random.choice(['CE', 'PE'])
    expiries = ["14TH OCT", "OCT", "14OCT25"]
    expiry = random.choice(expiries)
    # Format: timestamp,TRADING,order_details,strategy,test_flag,portfolio
    signal = (
        f"TRADING,"
        f"Initiating Order Placement for User: SIMULATED1 (SIM1 - APITest); "
        f"Leg ID: {leg_id}; Symbol: {index} {expiry} {strike} {option_type}; "
        f"Qty: {qty}; Txn: {txn}; Portfolio: FRI-NIFTY-14.45; IsExit: False; "
        f"ExitSL: False; OrderType: MARKET; AtBroker: None,"
        f"SIM1,TEST,FRI-NIFTY-14.45"  # Add strategy, test flag, and portfolio
    )
    return signal

def write_signal_to_file(base_path: str):
    """Write a signal to the GridLogs.csv file"""
    # Create current date folder
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_folder = Path(base_path) / current_date
    log_folder.mkdir(parents=True, exist_ok=True)
    
    # GridLog.csv path (note: removed 's' to match expected filename)
    grid_logs_path = log_folder / "GridLog.csv"
    
    # Generate signal
    signal = generate_order_signal()
    current_time = datetime.now().strftime("%H:%M:%S:%f")[:12]  # Format as HH:MM:SS:fff
    
    # Write to file
    try:
        # Create file if it doesn't exist (no header needed)
        if not grid_logs_path.exists():
            grid_logs_path.touch()
            logger.debug(f"Created new file: {grid_logs_path}")
            
        # Format the timestamp as HH:MM:SS:fff
        timestamp = datetime.now()
        log_time = timestamp.strftime("%H:%M:%S:%f")[:12]
        
        # Append signal with correct format
        with open(grid_logs_path, 'a', newline='', encoding='utf-8') as f:
            f.write(f"{log_time},{signal}\n")
            f.flush()  # Force write to disk
            os.fsync(f.fileno())  # Ensure it's written to disk
            
        # Let the log watcher know a change occurred by updating the file's modified time
        os.utime(grid_logs_path, None)
            
        print(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] Signal written successfully")
    except Exception as e:
        print(f"Error writing signal: {e}")

def main():
    # Base path for logs - using current directory
    base_path = Path.cwd() / "test_folder"  # This will create a test_logs folder in your current directory
    
    print("Starting signal generator...")
    print(f"Writing to: {base_path}")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            write_signal_to_file(base_path)
            time.sleep(10)  # Wait for 10 seconds
            
    except KeyboardInterrupt:
        print("\nSignal generator stopped by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()