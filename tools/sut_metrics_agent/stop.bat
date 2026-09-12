@echo off
REM 停止被测监控采集器
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe agent_ctl.py stop
) else (
  python agent_ctl.py stop
)
