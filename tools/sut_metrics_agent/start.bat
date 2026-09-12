@echo off
REM 启动被测监控采集器（交互配置）
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  python -m venv .venv
  .venv\Scripts\pip install -U pip
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python.exe agent_ctl.py start %*
