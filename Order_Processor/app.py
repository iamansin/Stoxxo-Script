from core.main import OrderProcessingSystem
import asyncio
from loguru import logger
from core.config import Config
import signal
import json
import sys
import platform
from pathlib import Path

#  "LOG_PATH": "C:/Program Files (x86)/Stoxxo/Logs",

def load_config_from_json(config_path: str) -> Config:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Convert paths in config to proper Path objects
        if 'LOG_PATH' in config_data:
            config_data['LOG_PATH'] = Path(config_data['LOG_PATH'])
        if 'YAML_PATH' in config_data:
            config_data['YAML_PATH'] = Path(config_data['YAML_PATH'])
                
        # Create config instance with the loaded data
        return Config(**config_data)
    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")
        raise

async def main():
    """Main entry point for the application"""
    # Check for config file argument
    if len(sys.argv) < 2:
        logger.error("Config file path argument is required! Usage: python app.py /path/to/config.json")
        sys.exit(1)
    
    config_path = sys.argv[1]
    logger.info(f"Loading configuration from: {config_path}")
    
    try:
        config = load_config_from_json(config_path)
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # --- 1. Create the system and a shutdown event ---
    system = OrderProcessingSystem(config)
    shutdown_event = asyncio.Event()

    # Get the current, running event loop
    loop = asyncio.get_running_loop()

    # --- 2. Gracefully handle shutdown signals ---
    # The 'set_event' function will be called when a signal is received
    def set_event():
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        shutdown_event.set()

    # On Windows, loop.add_signal_handler is not supported, so we use the standard signal module.
    # On Linux/macOS, we use the asyncio-native handler.
    if platform.system() == "Windows":
        # The old way is the correct way on Windows
        signal.signal(signal.SIGINT, lambda s, f: set_event())
        signal.signal(signal.SIGTERM, lambda s, f: set_event())
    else:
        # The modern, asyncio-native way for Unix-like systems
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, set_event)

    # --- 3. Use a try/finally block to guarantee cleanup ---
    try:
        logger.info("System starting... Press Ctrl+C to exit.")
        # Start the main application task
        await system.start()

        # This will pause the main function here indefinitely until the event is set
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"An unexpected error occurred in the main task: {e}")
    finally:
        # This block is GUARANTEED to run on exit or error
        logger.info("Cleaning up resources...")
        await system.stop()
        logger.info("Application has been shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user.")
