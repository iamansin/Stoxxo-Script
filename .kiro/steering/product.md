---
inclusion: always
---

# Stoxxo Order Processing System

## Product Overview
High-performance, asynchronous financial trading order processor that monitors CSV log files for trading signals and routes orders to multiple platforms (Tradetron/Algotest) with real-time processing and risk management.

## Core Business Logic
- **Signal Processing**: Parse CSV log files for BUY/SELL signals with timestamps
- **Order Routing**: Route orders to appropriate trading platforms based on configuration
- **Risk Management**: Apply multipliers, validate trading hours, enforce position limits
- **State Management**: Track order status, handle retries, maintain audit trails

## System Behavior
- **File Monitoring**: Continuously watch `logs_folder/` for new CSV entries
- **Trading Hours**: Only process orders during configured market sessions
- **Error Handling**: Retry failed orders with exponential backoff, log all failures
- **Configuration Hot-reload**: Support runtime config updates without restart

## Platform Integration
- **Tradetron**: Primary trading platform with webhook-based order submission
- **Algotest**: Secondary platform for strategy validation and backtesting
- **Dual Routing**: Orders can be sent to both platforms simultaneously based on strategy config

## Data Flow Constraints
- CSV format: `timestamp,symbol,action,quantity,price,strategy`
- Order validation: Symbol mapping, quantity limits, price bounds
- Async processing: All I/O operations must be non-blocking
- Idempotency: Duplicate signal detection and prevention

## Configuration-Driven Behavior
- `config.json`: System settings (paths, timeouts, workers, trading hours)
- `config.yaml`: Strategy mappings (symbols, multipliers, platform routing)
- Environment overrides: Support for runtime configuration via env vars

## Operational Requirements
- **Logging**: Structured logs with correlation IDs for order tracking
- **Monitoring**: Health checks, performance metrics, error rates
- **Deployment**: Docker containerization with volume mounts for configs
- **Scalability**: Multi-worker processing with shared state management