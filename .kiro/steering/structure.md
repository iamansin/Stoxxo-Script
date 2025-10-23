# Project Structure & Organization

## Directory Layout
```
├── Order_Processor/           # Main application package
│   ├── app.py                # Application entry point
│   ├── core/                 # Core business logic
│   │   ├── main.py          # System orchestrator
│   │   ├── config.py        # Configuration models
│   │   ├── models.py        # Data models and enums
│   │   ├── order_processor.py # Order processing logic
│   │   ├── log_listner.py   # File monitoring
│   │   ├── adapters.py      # Trading platform adapters
│   │   ├── cache_manager.py # Caching system
│   │   └── logging_config.py # Logging setup
│   ├── tests/               # Test suite
│   ├── Dockerfile          # Container configuration
│   └── requirements.txt    # Python dependencies
├── logs_folder/             # Runtime logs (gitignored)
├── test_folder/            # Test data (gitignored)
├── config.json             # System configuration
└── config.yaml            # Trading strategies
```

## Architecture Patterns

### Core Principles
- **Async-first**: All I/O operations use asyncio
- **Configuration-driven**: Behavior controlled via JSON/YAML configs
- **Adapter pattern**: Platform integrations through adapters
- **Event-driven**: File system events trigger processing
- **Separation of concerns**: Clear module boundaries

### Module Responsibilities
- `app.py`: Entry point, signal handling, configuration loading
- `main.py`: System orchestration and lifecycle management
- `order_processor.py`: Core order processing logic
- `adapters.py`: External platform integrations
- `log_listner.py`: File system monitoring and parsing
- `models.py`: Data structures and business entities

### Naming Conventions
- **Files**: snake_case (e.g., `order_processor.py`)
- **Classes**: PascalCase (e.g., `OrderProcessingSystem`)
- **Functions/Variables**: snake_case (e.g., `load_config_from_json`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_WORKERS`)
- **Enums**: PascalCase with UPPER values (e.g., `OrderStatus.PENDING`)

### Configuration Structure
- System settings in `config.json` (paths, timeouts, workers)
- Trading strategies in `config.yaml` (URLs, multipliers, mappings)
- Pydantic models for validation and type safety