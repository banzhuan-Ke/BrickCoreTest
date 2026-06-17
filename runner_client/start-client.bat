@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "CLIENT_DIR=%CD%"
cd /d "%~dp0.."
set "ROOT=%CD%"
set "RUNNER_DIR=%ROOT%\runner"
set "PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

if not exist "%CLIENT_DIR%\venv\Scripts\python.exe" (
  echo [1/3] Creating client venv...
  python -m venv "%CLIENT_DIR%\venv"
  if errorlevel 1 goto :fail
)

echo [1/3] Installing client dependencies...
"%CLIENT_DIR%\venv\Scripts\python.exe" -m pip install -r "%CLIENT_DIR%\requirements.txt" -i "%PIP_MIRROR%"
if errorlevel 1 goto :fail

if not exist "%RUNNER_DIR%\venv\Scripts\python.exe" (
  echo [2/3] Creating runner venv...
  python -m venv "%RUNNER_DIR%\venv"
  if errorlevel 1 goto :fail
)

echo [3/3] Installing runner dependencies...
"%RUNNER_DIR%\venv\Scripts\python.exe" -m pip install -r "%RUNNER_DIR%\requirements.txt" -i "%PIP_MIRROR%"
if errorlevel 1 goto :fail
"%RUNNER_DIR%\venv\Scripts\python.exe" -c "import jsonpath_ng, pika, playwright"
if errorlevel 1 goto :fail

cd /d "%ROOT%"
"%CLIENT_DIR%\venv\Scripts\python.exe" -m runner_client.main
goto :end

:fail
echo.
echo [ERROR] Setup failed. Check Python is on PATH and network is available.
pause
exit /b 1

:end
pause
