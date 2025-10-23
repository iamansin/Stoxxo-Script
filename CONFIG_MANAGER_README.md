# Stoxxo Configuration Manager

A Streamlit-based web interface for managing your Stoxxo Order Processing System configurations and controlling the application lifecycle.

## Features

- **Web-based Configuration**: Easy-to-use interface for editing JSON and YAML configs
- **Process Management**: Start/stop the main application with one click
- **Real-time Status**: Monitor application status in real-time
- **Organized Tabs**: Separate sections for different configuration types
- **Safe Process Handling**: Runs main application in isolated process

## Installation

1. Install the required dependencies:
```bash
pip install -r streamlit_requirements.txt
```

2. Run the configuration manager:
```bash
streamlit run config_manager.py
```

Or use the batch file on Windows:
```bash
run_config_manager.bat
```

## Usage

### Starting the Configuration Manager

The web interface will be available at `http://localhost:8501`

### Configuration Tabs

1. **Application Config**: 
   - Performance settings (workers, queue size, batch size)
   - File paths and patterns
   - Trading hours and market sessions
   - Retry mechanisms

2. **Adapter Config**:
   - Enable/disable Tradetron and Algotest
   - Timeout settings for each adapter

3. **Strategies**:
   - Manage trading strategies
   - Configure URLs and multipliers
   - Index mappings and lot sizes
   - Monthly expiry configurations

### Process Management

- **Start Application**: Launches the main order processor in a separate process
- **Stop Application**: Safely terminates the running application
- **Status Indicator**: Shows real-time application status

## Process Management Approach

The configuration manager runs the main application in a **separate process** for these benefits:

- **Non-blocking UI**: Streamlit interface remains responsive
- **Process Isolation**: Main app crashes don't affect the config manager
- **Clean Termination**: Proper process cleanup when stopping
- **Resource Management**: Better memory and CPU isolation

## Configuration Storage

- Configurations are stored in the existing `config.json` and `config.yaml` files
- No database required - keeps the system lightweight
- Maintains compatibility with your existing application
- Changes take effect when the application is restarted

## Security Notes

- The configuration manager should only be run in trusted environments
- Process management requires appropriate system permissions
- Consider firewall rules if accessing remotely

## Troubleshooting

- **Application won't start**: Check file paths in configuration
- **Process not stopping**: May require manual termination via Task Manager
- **Config not saving**: Verify file permissions in the directory