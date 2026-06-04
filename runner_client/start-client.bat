@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Step 1/2: Creating venv...
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
  call venv\Scripts\activate.bat
)
cd /d "%~dp0\.."
python -m runner_client.main
pause
