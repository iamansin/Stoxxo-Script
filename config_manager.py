import streamlit as st
import json
import yaml
import subprocess
import psutil
import os
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
import time
import sys
from datetime import datetime
import copy

class ConfigManager:
    """Manages configuration files and application lifecycle"""
    
    def __init__(self):
        self.config_json_path = "config.json"
        self.config_yaml_path = "config.yaml"
        self.pid_file_path = Path("app.pid")
        
    def load_json_config(self) -> Dict[str, Any]:
        """Load JSON configuration with error handling"""
        try:
            if not Path(self.config_json_path).exists():
                st.error(f"Config file not found: {self.config_json_path}")
                return self._get_default_json_config()
            
            with open(self.config_json_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON format: {e}")
            return self._get_default_json_config()
        except Exception as e:
            st.error(f"Error loading JSON config: {e}")
            return self._get_default_json_config()
    
    def load_yaml_config(self) -> Dict[str, Any]:
        """Load YAML configuration with error handling"""
        try:
            if not Path(self.config_yaml_path).exists():
                st.error(f"Config file not found: {self.config_yaml_path}")
                return self._get_default_yaml_config()
            
            with open(self.config_yaml_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            st.error(f"Invalid YAML format: {e}")
            return self._get_default_yaml_config()
        except Exception as e:
            st.error(f"Error loading YAML config: {e}")
            return self._get_default_yaml_config()
    
    def save_json_config(self, config: Dict[str, Any]) -> bool:
        """Save JSON configuration with validation and backup"""
        try:
            backup_path = Path(f"{self.config_json_path}.backup")
            config_path = Path(self.config_json_path)

            # Create backup by replacing any existing backup file
            if config_path.exists():
                config_path.replace(backup_path)

            # Validate before saving
            if not self._validate_json_config(config):
                # If validation fails, restore the backup
                if backup_path.exists():
                    backup_path.replace(config_path)
                return False

            with open(self.config_json_path, 'w') as f:
                json.dump(config, f, indent=2)

            return True
        except Exception as e:
            st.error(f"Error saving JSON config: {e}")
            # Restore backup if it exists
            backup_path = Path(f"{self.config_json_path}.backup")
            config_path = Path(self.config_json_path)
            if backup_path.exists():
                backup_path.replace(config_path)
            return False
    
    def save_yaml_config(self, config: Dict[str, Any]) -> bool:
        """Save YAML configuration with validation and backup"""
        try:
            backup_path = Path(f"{self.config_yaml_path}.backup")
            config_path = Path(self.config_yaml_path)
            
            # Create backup by replacing any existing backup file
            if config_path.exists():
                config_path.replace(backup_path)

            # Validate before saving
            if not self._validate_yaml_config(config):
                # If validation fails, restore the backup
                if backup_path.exists():
                    backup_path.replace(config_path)
                return False

            with open(self.config_yaml_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2, sort_keys=False)

            return True
        except Exception as e:
            st.error(f"Error saving YAML config: {e}")
            # Restore backup if it exists
            backup_path = Path(f"{self.config_yaml_path}.backup")
            config_path = Path(self.config_yaml_path)
            if backup_path.exists():
                backup_path.replace(config_path)
            return False
    
    def _validate_json_config(self, config: Dict[str, Any]) -> bool:
        """Validate JSON configuration structure"""
        required_fields = ['MAX_WORKERS', 'QUEUE_SIZE', 'BATCH_SIZE', 'LOG_PATH']
        for field in required_fields:
            if field not in config:
                st.error(f"Missing required field: {field}")
                return False
        return True
    
    def _validate_yaml_config(self, config: Dict[str, Any]) -> bool:
        """Validate YAML configuration structure"""
        if 'strategies' not in config or not isinstance(config['strategies'], list):
            st.error("Invalid strategies configuration")
            return False
        return True
    
    def _get_default_json_config(self) -> Dict[str, Any]:
        """Return default JSON configuration"""
        return {
            "MAX_WORKERS": 4,
            "QUEUE_SIZE": 10000,
            "BATCH_SIZE": 50,
            "LOG_PATH": "",
            "LOG_FILE_PATTERN": "*.csv",
            "RETRY_ATTEMPTS": 3,
            "RETRY_DELAY": 1.0,
            "PROCESSING_TIMEOUT": 30,
            "YAML_PATH": "",
            "ENABLE_TRADETRON": True,
            "ENABLE_ALGOTEST": False,
            "ALGOTEST_CONFIG": {},
            "TRADETRON_CONFIG": {},
            "allowed_weekdays": [0, 1, 2, 3, 4],
            "trading_start_time": "09:15",
            "trading_end_time": "15:30"
        }
    
    def _get_default_yaml_config(self) -> Dict[str, Any]:
        """Return default YAML configuration"""
        return {
            "strategies": [],
            "index_mappings": {},
            "lot_sizes": {},
            "monthly_expiry": {}
        }
    
    # --- NEW HELPER METHOD ---
    def _get_pid_from_file(self) -> Optional[int]:
        """Reads the PID from the PID file. Returns None if not found or invalid."""
        try:
            if self.pid_file_path.exists():
                with self.pid_file_path.open('r') as f:
                    pid_str = f.read().strip()
                    if pid_str:
                        return int(pid_str)
        except (IOError, ValueError):
            # If file is unreadable or content is not an integer, we'll treat it as invalid.
            return None
        return None

    # --- NEW HELPER METHOD ---
    def _cleanup_pid_file(self):
        """Removes the PID file safely if it exists."""
        try:
            if self.pid_file_path.exists():
                self.pid_file_path.unlink()
            # Also clear the temporary session state
            st.session_state.app_pid = None
            st.session_state.app_start_time = None
        except OSError:
            pass  # Ignore errors if the file is already gone

    # --- HEAVILY MODIFIED: The core logic now relies on the PID file ---
    def is_app_running(self) -> bool:
        """
        Checks if the application is running by reading the PID file and verifying the process.
        This is the new "source of truth".
        """
        pid = self._get_pid_from_file()
        if not pid:
            return False
        
        try:
            process = psutil.Process(pid)
            # Extra check: Make sure the running process is actually our script.
            # This prevents a stale PID file from matching a new, unrelated process.
            if "app.py" in " ".join(process.cmdline()):
                st.session_state.app_pid = pid  # Keep session_state in sync for the UI
                return process.is_running()
            else:
                # The PID exists, but it's not our app. This is a stale PID file.
                self._cleanup_pid_file()
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # The process with that PID is gone. The PID file is stale.
            self._cleanup_pid_file()
            return False

    # --- MODIFIED: Writes the PID to the file on successful start ---
    def start_application(self, json_config_path: str) -> bool:
        """Starts the main application and creates a PID file to track it."""
        try:
            if self.is_app_running():
                st.warning("Application is already running!")
                return False

            script_dir = Path(__file__).resolve().parent
            app_script_path = script_dir / "Order_Processor" / "app.py"
            abs_json_config_path = script_dir / json_config_path

            if not app_script_path.exists():
                st.error(f"FATAL: Application script not found at: {app_script_path}")
                return False
            
            cmd = [sys.executable, str(app_script_path), str(abs_json_config_path)]

            # Handle process creation for different OS
            popen_kwargs = {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True}
            if os.name == 'nt':
                popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs['start_new_session'] = True

            process = subprocess.Popen(cmd, **popen_kwargs)
            
            time.sleep(2)  # Give the app a moment to start or fail

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                st.error("Application failed to start. See error from subprocess below:")
                st.code(f"STDERR:\n{stderr}\n\nSTDOUT:\n{stdout}", language='bash')
                return False

            # --- CRITICAL CHANGE: Write PID to file on success ---
            with self.pid_file_path.open('w') as f:
                f.write(str(process.pid))

            st.session_state.app_pid = process.pid
            st.session_state.app_start_time = datetime.now()
            return True
            
        except Exception as e:
            st.error(f"An exception occurred while trying to start the application: {e}")
            return False
    
        # --- MODIFIED: Reads the PID from the file and deletes it on successful stop ---
    def stop_application(self) -> bool:
        """Stops the main application using the PID from the PID file."""
        pid = self._get_pid_from_file()

        if not pid or not self.is_app_running():
            st.warning("Application is not running or PID file is missing!")
            self._cleanup_pid_file()  # Clean up just in case the file is stale
            return False
        
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            
            # --- CRITICAL CHANGE: Clean up the PID file after stopping ---
            self._cleanup_pid_file()
            st.success("Process terminated and PID file cleaned up.")
            return True
                
        except (ProcessLookupError, psutil.NoSuchProcess):
            st.warning("Process was already gone. Cleaning up PID file.")
            self._cleanup_pid_file()
            return True
        except Exception as e:
            st.error(f"Error stopping application: {e}")
            return False


def main():
    """Main application entry point"""
    st.set_page_config(
        page_title="Stoxxo Order Processor",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: bold;
            color: #1f77b4;
            text-align: center;
            padding: 1rem 0;
        }
        .status-running {
            color: #28a745;
            font-weight: bold;
        }
        .status-stopped {
            color: #dc3545;
            font-weight: bold;
        }
        .stButton button {
            width: 100%;
        }
        div[data-testid="stExpander"] div[role="button"] p {
            font-size: 1.1rem;
            font-weight: 600;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-header">📊 Stoxxo Order Processor</div>', unsafe_allow_html=True)
    st.markdown("### Configuration Management System")
    
    # Initialize session state
    if 'config_manager' not in st.session_state:
        st.session_state.config_manager = ConfigManager()
    
    if 'app_pid' not in st.session_state:
        st.session_state.app_pid = None
    
    if 'app_start_time' not in st.session_state:
        st.session_state.app_start_time = None
    
    config_manager = st.session_state.config_manager
    
    # Sidebar - Application Control
    with st.sidebar:
        st.header("🎛️ Application Control")
        
        is_running = config_manager.is_app_running()
        
        if is_running:
            st.markdown('<p class="status-running">🟢 Application Running</p>', unsafe_allow_html=True)
            if st.session_state.app_start_time:
                uptime = datetime.now() - st.session_state.app_start_time
                st.info(f"⏱️ Uptime: {str(uptime).split('.')[0]}")
            st.info(f"🔢 PID: {st.session_state.app_pid}")
        else:
            st.markdown('<p class="status-stopped">🔴 Application Stopped</p>', unsafe_allow_html=True)
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Start", type="primary", disabled=is_running, use_container_width=True):
                if config_manager.start_application(config_manager.config_json_path):
                    st.success("✅ Started!")
                    time.sleep(1)
                    st.rerun()
        
        with col2:
            if st.button("🛑 Stop", type="secondary", disabled=not is_running, use_container_width=True):
                if config_manager.stop_application():
                    st.success("✅ Stopped!")
                    time.sleep(1)
                    st.rerun()
        
        st.divider()
        
        st.header("📁 File Paths")
        st.text_input("JSON Config", value=config_manager.config_json_path, disabled=True)
        st.text_input("YAML Config", value=config_manager.config_yaml_path, disabled=True)
        
        if st.button("🔄 Reload Configs", use_container_width=True):
            st.rerun()
    
    # Main content - Configuration tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚙️ Application Config",
        "📈 Strategy Config",
        "🔌 Adapter Config",
        "🗺️ Mappings"
    ])
    
    with tab1:
        render_application_config(config_manager)
    
    with tab2:
        render_strategy_config(config_manager)
    
    with tab3:
        render_adapter_config(config_manager)
    
    with tab4:
        render_mappings_config(config_manager)


def render_application_config(config_manager: ConfigManager):
    """Render application configuration tab"""
    st.header("Application Configuration")
    st.info("⚠️ Changes require application restart to take effect")
    
    config = config_manager.load_json_config()
    
    # Performance Settings
    with st.expander("⚡ Performance Settings", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            config['MAX_WORKERS'] = st.number_input(
                "Max Workers",
                value=config.get('MAX_WORKERS', 4),
                min_value=1,
                max_value=32,
                help="Number of worker threads for processing"
            )
            
            config['QUEUE_SIZE'] = st.number_input(
                "Queue Size",
                value=config.get('QUEUE_SIZE', 10000),
                min_value=100,
                max_value=100000,
                help="Maximum size of the processing queue"
            )
            
            config['BATCH_SIZE'] = st.number_input(
                "Batch Size",
                value=config.get('BATCH_SIZE', 50),
                min_value=1,
                max_value=1000,
                help="Number of orders to process in a batch"
            )
        
        with col2:
            config['PROCESSING_TIMEOUT'] = st.number_input(
                "Processing Timeout (seconds)",
                value=config.get('PROCESSING_TIMEOUT', 30),
                min_value=1,
                max_value=300,
                help="Timeout for processing a single order"
            )
            
            config['RETRY_ATTEMPTS'] = st.number_input(
                "Retry Attempts",
                value=config.get('RETRY_ATTEMPTS', 3),
                min_value=0,
                max_value=10,
                help="Number of retry attempts on failure"
            )
            
            config['RETRY_DELAY'] = st.number_input(
                "Retry Delay (seconds)",
                value=float(config.get('RETRY_DELAY', 1.0)),
                min_value=0.1,
                max_value=10.0,
                step=0.1,
                help="Delay between retry attempts"
            )
    
    # File Path Settings
    with st.expander("📁 File Path Settings", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            config['LOG_PATH'] = st.text_input(
                "Log Path",
                value=config.get('LOG_PATH', ''),
                help="Directory path for log files"
            )
            
            config['LOG_FILE_PATTERN'] = st.text_input(
                "Log File Pattern",
                value=config.get('LOG_FILE_PATTERN', '*.csv'),
                help="File pattern to match log files"
            )
        
        with col2:
            config['YAML_PATH'] = st.text_input(
                "YAML Config Path",
                value=config.get('YAML_PATH', ''),
                help="Path to YAML configuration file"
            )
    
    # Trading Hours Settings
    with st.expander("🕐 Trading Hours Configuration", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Regular Trading Hours")
            config['trading_start_time'] = st.text_input(
                "Start Time (HH:MM)",
                value=config.get('trading_start_time', '09:15'),
                help="Regular trading session start time"
            )
            
            config['trading_end_time'] = st.text_input(
                "End Time (HH:MM)",
                value=config.get('trading_end_time', '15:30'),
                help="Regular trading session end time"
            )
        
        with col2:
            st.subheader("Pre-market Session")
            config['enable_premarket'] = st.checkbox(
                "Enable Pre-market",
                value=config.get('enable_premarket', True)
            )
            
            if config['enable_premarket']:
                config['premarket_start'] = st.text_input(
                    "Pre-market Start (HH:MM)",
                    value=config.get('premarket_start', '09:00'),
                    help="Pre-market session start time"
                )
        
        with col3:
            st.subheader("Post-market Session")
            config['enable_postmarket'] = st.checkbox(
                "Enable Post-market",
                value=config.get('enable_postmarket', True)
            )
            
            if config['enable_postmarket']:
                config['postmarket_end'] = st.text_input(
                    "Post-market End (HH:MM)",
                    value=config.get('postmarket_end', '16:00'),
                    help="Post-market session end time"
                )
        
        st.subheader("Allowed Trading Days")
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        selected_days = st.multiselect(
            "Select Trading Days",
            options=list(range(7)),
            default=config.get('allowed_weekdays', [0, 1, 2, 3, 4]),
            format_func=lambda x: weekdays[x],
            help="Days of the week when trading is allowed"
        )
        config['allowed_weekdays'] = selected_days
    
    # Save Button
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("💾 Save Configuration", type="primary", use_container_width=True):
            if config_manager.save_json_config(config):
                st.success("✅ Configuration saved successfully!")
                time.sleep(1)
                st.rerun()
    
    with col2:
        if st.button("↩️ Reset to Defaults", use_container_width=True):
            st.warning("This will reset all application settings to defaults")
            if st.button("⚠️ Confirm Reset"):
                config_manager.save_json_config(config_manager._get_default_json_config())
                st.rerun()


def render_strategy_config(config_manager: ConfigManager):
    """Render strategy configuration tab"""
    st.header("Strategy Configuration")
    st.info("💡 Manage your trading strategies and their webhooks")
    
    config = config_manager.load_yaml_config()
    
    if 'strategies' not in config:
        config['strategies'] = []
    
    # Add new strategy button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("➕ Add New Strategy", type="primary", use_container_width=True):
            new_strategy = {
                'name': f"Strategy_{len(config['strategies']) + 1}",
                'tradetron_urls': [],
                'algotest_urls': [],
                'active': True
            }
            config['strategies'].append(new_strategy)
            config_manager.save_yaml_config(config)
            st.rerun()
    
    # Display existing strategies
    if not config['strategies']:
        st.warning("📭 No strategies configured. Click 'Add New Strategy' to create one.")
    else:
        for i, strategy in enumerate(config['strategies']):
            status_icon = "✅" if strategy.get('active', True) else "⏸️"
            expander_title = f"{status_icon} {strategy.get('name', f'Strategy_{i+1}')}"
            
            with st.expander(expander_title, expanded=False):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    strategy['name'] = st.text_input(
                        "Strategy Name",
                        value=strategy.get('name', ''),
                        key=f"strat_name_{i}",
                        help="Unique name for this strategy"
                    )
                
                with col2:
                    strategy['active'] = st.checkbox(
                        "Active",
                        value=strategy.get('active', True),
                        key=f"strat_active_{i}",
                        help="Enable/disable this strategy"
                    )
                
                # Tradetron URLs Section
                st.subheader("🔷 Tradetron Webhooks")
                tradetron_urls = strategy.get('tradetron_urls', [])
                
                if not tradetron_urls:
                    st.info("No Tradetron URLs configured")
                
                for j, url_config in enumerate(tradetron_urls):
                    col1, col2, col3 = st.columns([6, 2, 1])
                    
                    with col1:
                        url_config['url'] = st.text_input(
                            f"Tradetron URL #{j+1}",
                            value=url_config.get('url', ''),
                            key=f"tt_url_{i}_{j}",
                            help="Tradetron webhook URL or ID"
                        )
                    
                    with col2:
                        url_config['multiplier'] = st.number_input(
                            f"Multiplier #{j+1}",
                            value=url_config.get('multiplier', 1),
                            min_value=1,
                            max_value=100,
                            key=f"tt_mult_{i}_{j}",
                            help="Order quantity multiplier"
                        )
                    
                    with col3:
                        st.write("")
                        st.write("")
                        if st.button("🗑️", key=f"del_tt_{i}_{j}"):
                            tradetron_urls.pop(j)
                            config_manager.save_yaml_config(config)
                            st.rerun()
                
                if st.button(f"➕ Add Tradetron URL", key=f"add_tt_{i}"):
                    tradetron_urls.append({'url': '', 'multiplier': 1})
                    config_manager.save_yaml_config(config)
                    st.rerun()
                
                st.divider()
                
                # Algotest URLs Section
                st.subheader("🔶 Algotest Webhooks")
                algotest_urls = strategy.get('algotest_urls', [])
                
                if not algotest_urls:
                    st.info("No Algotest URLs configured")
                
                for j, url_config in enumerate(algotest_urls):
                    col1, col2, col3 = st.columns([6, 2, 1])
                    
                    with col1:
                        url_config['url'] = st.text_input(
                            f"Algotest URL #{j+1}",
                            value=url_config.get('url', ''),
                            key=f"at_url_{i}_{j}",
                            help="Algotest webhook URL"
                        )
                    
                    with col2:
                        url_config['multiplier'] = st.number_input(
                            f"Multiplier #{j+1}",
                            value=url_config.get('multiplier', 1),
                            min_value=1,
                            max_value=100,
                            key=f"at_mult_{i}_{j}",
                            help="Order quantity multiplier"
                        )
                    
                    with col3:
                        st.write("")
                        st.write("")
                        if st.button("🗑️", key=f"del_at_{i}_{j}"):
                            algotest_urls.pop(j)
                            config_manager.save_yaml_config(config)
                            st.rerun()
                
                if st.button(f"➕ Add Algotest URL", key=f"add_at_{i}"):
                    algotest_urls.append({'url': '', 'multiplier': 1})
                    config_manager.save_yaml_config(config)
                    st.rerun()
                
                st.divider()
                
                # Delete strategy button
                if st.button(
                    f"🗑️ Delete Strategy: {strategy.get('name', '')}",
                    key=f"del_strat_{i}",
                    type="secondary",
                    use_container_width=True
                ):
                    config['strategies'].pop(i)
                    config_manager.save_yaml_config(config)
                    st.rerun()
    
    # Save button
    st.divider()
    if st.button("💾 Save All Strategies", type="primary", use_container_width=True):
        if config_manager.save_yaml_config(config):
            st.success("✅ Strategies saved successfully!")
            time.sleep(1)
            st.rerun()



def render_adapter_config(config_manager: "ConfigManager"):
    """Render adapter configuration tab"""
    st.header("Adapter Configuration")
    st.info("🔌 Configure integration adapters for different trading platforms")
    
    config = config_manager.load_json_config()
    
    # Tradetron Adapter
    with st.expander("🔷 Tradetron Adapter Settings", expanded=True):
        col1, col2 = st.columns([1, 3])
        
        with col1:
            config['ENABLE_TRADETRON'] = st.checkbox(
                "Enable Tradetron",
                value=config.get('ENABLE_TRADETRON', True),
                help="Enable/disable Tradetron integration"
            )
        
        if config['ENABLE_TRADETRON']:
            if 'TRADETRON_CONFIG' not in config:
                config['TRADETRON_CONFIG'] = {}
            
            tt_config = config['TRADETRON_CONFIG']
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                tt_config['TIMEOUT'] = st.number_input(
                    "Request Timeout (seconds)",
                    value=tt_config.get('TIMEOUT', 10),
                    min_value=1,
                    max_value=60,
                    key="tt_timeout",
                    help="API request timeout"
                )
                
                tt_config['BASE_URL'] = st.text_input(
                    "Base URL",
                    value=tt_config.get('BASE_URL', 'https://api.tradetron.tech/api'),
                    key="tt_base_url",
                    help="Tradetron API base URL"
                )
                
                tt_config['METHOD'] = st.selectbox(
                    "HTTP Method",
                    options=['GET', 'POST'],
                    index=0 if tt_config.get('METHOD', 'GET') == 'GET' else 1,
                    key="tt_method"
                )
            
            with col2:
                tt_config['RATE_LIMITER_ACTIVE'] = st.checkbox(
                    "Enable Rate Limiting",
                    value=tt_config.get('RATE_LIMITER_ACTIVE', True),
                    key="tt_rate_limiter",
                    help="Enable rate limiting for API requests"
                )
                
                tt_config['RATE_LIMIT'] = st.number_input(
                    "Rate Limit (requests)",
                    value=tt_config.get('RATE_LIMIT', 30),
                    min_value=1,
                    max_value=1000,
                    key="tt_rate_limit",
                    help="Maximum requests allowed"
                )
                
                tt_config['RATE_LIMIT_PERIOD'] = st.number_input(
                    "Rate Limit Period (seconds)",
                    value=tt_config.get('RATE_LIMIT_PERIOD', 60),
                    min_value=1,
                    max_value=3600,
                    key="tt_rate_period",
                    help="Time window for rate limit"
                )
            
            with col3:
                tt_config['GROUPING_ENABLED'] = st.checkbox(
                    "Enable Grouping",
                    value=tt_config.get('GROUPING_ENABLED', True),
                    key="tt_grouping",
                    help="Enable order grouping"
                )
                
                tt_config['GROUP_LIMIT'] = st.number_input(
                    "Group Limit",
                    value=tt_config.get('GROUP_LIMIT', 40),
                    min_value=1,
                    max_value=1000,
                    key="tt_group_limit",
                    help="Maximum orders per group"
                )
                
                tt_config['COUNTER_SIZE'] = st.number_input(
                    "Variable Range",
                    value=tt_config.get('COUNTER_SIZE', 10),
                    min_value=1,
                    max_value=100,
                    key="tt_counter_size",
                    help="Size of the request counter"
                )
                
                order_delay_input = st.number_input(
                        "Order Delay (seconds)",
                        value=float(order_delay) if (order_delay := tt_config.get('ORDER_DELAY_SECONDS')) is not None else 0.0,
                        min_value=0.0,
                        max_value=10.0,
                        step=0.1,
                        key="tt_order_delay",
                        help="Delay between orders"
                    )
                tt_config['ORDER_DELAY_SECONDS'] = round(order_delay_input, 2)
                
    # Algotest Adapter
    with st.expander("🔶 Algotest Adapter Settings", expanded=True):
        col1, col2 = st.columns([1, 3])
        
        with col1:
            config['ENABLE_ALGOTEST'] = st.checkbox(
                "Enable Algotest",
                value=config.get('ENABLE_ALGOTEST', False),
                help="Enable/disable Algotest integration"
            )
        
        if config['ENABLE_ALGOTEST']:
            if 'ALGOTEST_CONFIG' not in config:
                config['ALGOTEST_CONFIG'] = {}
            
            at_config = config['ALGOTEST_CONFIG']
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                at_config['TIMEOUT'] = st.number_input(
                    "Request Timeout (seconds)",
                    value=at_config.get('TIMEOUT', 10),
                    min_value=1,
                    max_value=60,
                    key="at_timeout",
                    help="API request timeout"
                )
                
                at_config['BASE_URL'] = st.text_input(
                    "Base URL",
                    value=at_config.get('BASE_URL', 'https://api.algotest.in'),
                    key="at_base_url",
                    help="Algotest API base URL"
                )
                
                at_config['METHOD'] = st.selectbox(
                    "HTTP Method",
                    options=['GET', 'POST'],
                    index=0 if at_config.get('METHOD', 'GET') == 'GET' else 1,
                    key="at_method"
                )
            
            with col2:
                at_config['RATE_LIMITER_ACTIVE'] = st.checkbox(
                    "Enable Rate Limiting",
                    value=at_config.get('RATE_LIMITER_ACTIVE', False),
                    key="at_rate_limiter",
                    help="Enable rate limiting for API requests"
                )
                
                at_config['RATE_LIMIT'] = st.number_input(
                    "Rate Limit (requests)",
                    value=at_config.get('RATE_LIMIT', 0),
                    min_value=0,
                    max_value=1000,
                    key="at_rate_limit",
                    help="Maximum requests allowed"
                )
                
                at_config['RATE_LIMIT_PERIOD'] = st.number_input(
                    "Rate Limit Period (seconds)",
                    value=at_config.get('RATE_LIMIT_PERIOD', 60),
                    min_value=1,
                    max_value=3600,
                    key="at_rate_period",
                    help="Time window for rate limit"
                )
            
            with col3:
                at_config['GROUPING_ENABLED'] = st.checkbox(
                    "Enable Grouping",
                    value=at_config.get('GROUPING_ENABLED', False),
                    key="at_grouping",
                    help="Enable order grouping"
                )
                
                at_config['GROUP_LIMIT'] = st.number_input(
                    "Group Limit",
                    value=at_config.get('GROUP_LIMIT', 0),
                    min_value=0,
                    max_value=1000,
                    key="at_group_limit",
                    help="Maximum orders per group"
                )
                
                at_config['ALGOTEST_COUNTER_SIZE'] = st.number_input(
                    "Variable Range",
                    value=at_config.get('ALGOTEST_COUNTER_SIZE', 6),
                    min_value=1,
                    max_value=100,
                    key="at_counter_size",
                    help="Size of the request counter"
                )
                
                # CORRECTED THIS BLOCK
                order_delay_input = st.number_input(
                        "Order Delay (seconds)",
                        value=float(order_delay) if (order_delay := at_config.get('ORDER_DELAY_SECONDS')) is not None else 0.0,
                        min_value=0.0,
                        max_value=10.0,
                        step=0.1,
                        key="at_order_delay",
                        help="Delay between orders"
                    )
                at_config['ORDER_DELAY_SECONDS'] = round(order_delay_input, 2)
    
    # Save Button
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("💾 Save Adapter Config", type="primary", use_container_width=True):
            if config_manager.save_json_config(config):
                st.success("✅ Adapter configuration saved successfully!")
                time.sleep(1)
                st.rerun()


def render_mappings_config(config_manager: ConfigManager):
    """Render mappings configuration tab"""
    st.header("Mappings Configuration")
    st.info("🗺️ Manage index mappings, lot sizes, and monthly expiry dates")
    
    config = config_manager.load_yaml_config()
    
    # Index Mappings Section
    with st.expander("📊 Index Mappings", expanded=True):
        st.write("Map index names to their numeric identifiers")
        
        if 'index_mappings' not in config:
            config['index_mappings'] = {}
        
        # Add new index mapping
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            new_index_name = st.text_input("New Index Name", key="new_index_name")
        with col2:
            new_index_value = st.text_input("Index ID", key="new_index_value")
        with col3:
            st.write("")
            st.write("")
            if st.button("➕ Add", key="add_index_mapping"):
                if new_index_name and new_index_value:
                    config['index_mappings'][new_index_name] = new_index_value
                    config_manager.save_yaml_config(config)
                    st.rerun()
        
        st.divider()
        
        # Display existing mappings
        if config['index_mappings']:
            for idx, (key, value) in enumerate(list(config['index_mappings'].items())):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    new_key = st.text_input(
                        f"Index Name",
                        value=key,
                        key=f"idx_map_key_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col2:
                    new_value = st.text_input(
                        f"Index ID",
                        value=str(value),
                        key=f"idx_map_val_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col3:
                    if st.button("🗑️", key=f"del_idx_map_{idx}"):
                        del config['index_mappings'][key]
                        config_manager.save_yaml_config(config)
                        st.rerun()
                
                # Update if changed
                if new_key != key or new_value != value:
                    if new_key != key:
                        del config['index_mappings'][key]
                    config['index_mappings'][new_key] = new_value
        else:
            st.info("No index mappings configured")
    
    # Lot Sizes Section
    with st.expander("📦 Lot Sizes", expanded=True):
        st.write("Configure lot sizes for different instruments")
        
        if 'lot_sizes' not in config:
            config['lot_sizes'] = {}
        
        # Add new lot size
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            new_lot_instrument = st.text_input("Instrument Name", key="new_lot_instrument")
        with col2:
            new_lot_size = st.number_input("Lot Size", min_value=1, value=25, key="new_lot_size")
        with col3:
            st.write("")
            st.write("")
            if st.button("➕ Add", key="add_lot_size"):
                if new_lot_instrument:
                    config['lot_sizes'][new_lot_instrument] = new_lot_size
                    config_manager.save_yaml_config(config)
                    st.rerun()
        
        st.divider()
        
        # Display existing lot sizes
        if config['lot_sizes']:
            for idx, (key, value) in enumerate(list(config['lot_sizes'].items())):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    new_key = st.text_input(
                        f"Instrument",
                        value=key,
                        key=f"lot_key_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col2:
                    new_value = st.number_input(
                        f"Lot Size",
                        value=int(value),
                        min_value=1,
                        key=f"lot_val_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col3:
                    if st.button("🗑️", key=f"del_lot_{idx}"):
                        del config['lot_sizes'][key]
                        config_manager.save_yaml_config(config)
                        st.rerun()
                
                # Update if changed
                if new_key != key or new_value != value:
                    if new_key != key:
                        del config['lot_sizes'][key]
                    config['lot_sizes'][new_key] = new_value
        else:
            st.info("No lot sizes configured")
    
    # Monthly Expiry Section
    with st.expander("📅 Monthly Expiry Dates", expanded=True):
        st.write("Configure monthly expiry dates for different instruments")
        
        if 'monthly_expiry' not in config:
            config['monthly_expiry'] = {}
        
        # Add new instrument for expiry
        col1, col2 = st.columns([3, 1])
        with col1:
            new_expiry_instrument = st.text_input("New Instrument", key="new_expiry_instrument")
        with col2:
            st.write("")
            st.write("")
            if st.button("➕ Add Instrument", key="add_expiry_instrument"):
                if new_expiry_instrument and new_expiry_instrument not in config['monthly_expiry']:
                    config['monthly_expiry'][new_expiry_instrument] = {}
                    config_manager.save_yaml_config(config)
                    st.rerun()
        
        st.divider()
        
        # Display and edit existing expiry configurations
        if config['monthly_expiry']:
            for instrument_idx, (instrument, months) in enumerate(list(config['monthly_expiry'].items())):
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"📈 {instrument}")
                    with col2:
                        if st.button("🗑️ Delete", key=f"del_expiry_inst_{instrument_idx}"):
                            del config['monthly_expiry'][instrument]
                            config_manager.save_yaml_config(config)
                            st.rerun()
                    
                    # Add new month for this instrument
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col1:
                        new_month = st.text_input(
                            "Month (e.g., JAN)",
                            key=f"new_month_{instrument_idx}",
                            max_chars=3
                        ).upper()
                    with col2:
                        new_expiry_date = st.text_input(
                            "Expiry Date (YY-MM-DD)",
                            key=f"new_expiry_date_{instrument_idx}",
                            placeholder="25-12-31"
                        )
                    with col3:
                        st.write("")
                        st.write("")
                        if st.button("➕ Add", key=f"add_month_{instrument_idx}"):
                            if new_month and new_expiry_date:
                                if months is None:
                                    config['monthly_expiry'][instrument] = {}
                                config['monthly_expiry'][instrument][new_month] = new_expiry_date
                                config_manager.save_yaml_config(config)
                                st.rerun()
                    
                    # Display existing months
                    if months:
                        for month_idx, (month, date) in enumerate(list(months.items())):
                            col1, col2, col3 = st.columns([1, 2, 1])
                            
                            with col1:
                                new_month_key = st.text_input(
                                    "Month",
                                    value=month,
                                    key=f"month_key_{instrument_idx}_{month_idx}",
                                    label_visibility="collapsed"
                                )
                            
                            with col2:
                                new_date_value = st.text_input(
                                    "Date",
                                    value=date,
                                    key=f"month_date_{instrument_idx}_{month_idx}",
                                    label_visibility="collapsed"
                                )
                            
                            with col3:
                                if st.button("🗑️", key=f"del_month_{instrument_idx}_{month_idx}"):
                                    del config['monthly_expiry'][instrument][month]
                                    config_manager.save_yaml_config(config)
                                    st.rerun()
                            
                            # Update if changed
                            if new_month_key != month or new_date_value != date:
                                if new_month_key != month:
                                    del config['monthly_expiry'][instrument][month]
                                config['monthly_expiry'][instrument][new_month_key] = new_date_value
                    else:
                        st.info(f"No expiry dates configured for {instrument}")
                    
                    st.divider()
        else:
            st.info("No monthly expiry configurations")
    
    # Save Button
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("💾 Save All Mappings", type="primary", use_container_width=True):
            if config_manager.save_yaml_config(config):
                st.success("✅ Mappings saved successfully!")
                time.sleep(1)
                st.rerun()
    
    with col2:
        if st.button("📥 Export Config", use_container_width=True):
            st.download_button(
                label="Download YAML",
                data=yaml.dump(config, default_flow_style=False, indent=2),
                file_name=f"config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml",
                mime="text/yaml",
                use_container_width=True
            )


if __name__ == "__main__":
    main()