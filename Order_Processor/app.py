from core.main import OrderProcessingSystem
import asyncio
from loguru import logger
from core.config import Config
import signal
import json
import sys
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
    """Main entry point"""
    # Check for config file argument
    if len(sys.argv) < 2:
        logger.error("Config file path argument is required!")
        logger.info("Usage: python app.py /path/to/config.json")
        sys.exit(1)
    
    config_path = sys.argv[1]
    logger.info(f"Loading configuration from: {config_path}")
    
    try:
        config = load_config_from_json(config_path)
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
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
