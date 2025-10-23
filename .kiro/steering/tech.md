# Technology Stack & Build System

## Core Technologies
- **Python 3.11+** - Primary language
- **AsyncIO** - Asynchronous processing framework
- **Pydantic** - Data validation and settings management
- **Loguru** - Structured logging
- **Watchdog** - File system monitoring
- **HTTPX** - Async HTTP client for API calls

## Key Dependencies
```
httpx          # HTTP client for trading platform APIs
pydantic       # Data validation and configuration
loguru         # Logging framework
PyYAML         # YAML configuration parsing
watchdog       # File system monitoring
pandas         # Data processing
structlog      # Structured logging
pytz           # Timezone handling
```

## Build & Development Commands

### Local Development
```bash
# Setup virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r Order_Processor/requirements.txt

# Run application
python Order_Processor/app.py config.json
```

### Docker Operations
```bash
# Build image
docker build -t stoxxo-order-processor Order_Processor/

# Run container
docker run -v /path/to/config:/config stoxxo-order-processor /config/config.json
```

### Testing
```bash
# Run tests from Order_Processor directory
python -m pytest tests/
```

## Configuration Management
- **JSON Config**: Main system configuration (`config.json`)
- **YAML Config**: Trading strategies and mappings (`config.yaml`)
- **Environment Variables**: Runtime overrides via python-dotenv