@echo off
echo Starting Stoxxo Configuration Manager...
streamlit run config_manager.py --server.port 8501 --server.headless true
pause