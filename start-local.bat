@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo    FastAPI UI Test Platform - Startup
echo ==========================================
echo.

echo Step 0: Checking Docker...
where docker >nul 2>nul
if errorlevel 1 (
    echo ERROR: docker not found. Install Docker Desktop first.
    pause
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo ERROR: Docker is not running. Start Docker Desktop first.
    pause
    exit /b 1
)

echo Step 1/4: Starting Docker services...
docker compose -f docker-services.yml up -d
if errorlevel 1 (
    echo ERROR: docker compose failed
    pause
    exit /b 1
)

for %%C in (fastapi-mysql fastapi-redis fastapi-rabbitmq fastapi-minio) do (
    docker ps --filter "name=%%C" --filter "status=running" --format "{{.Names}}" | findstr /i "%%C" >nul
    if not errorlevel 1 (
        echo OK: %%C
    ) else (
        echo WARN: %%C not running
    )
)

echo.

if not exist "%~dp0backend\venv\Scripts\activate.bat" (
    echo ERROR: backend venv missing. Run: cd backend ^&^& python -m venv venv
    pause
    exit /b 1
)

if not exist "%~dp0frontend\node_modules" (
    echo ERROR: frontend node_modules missing. Run: cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo Step 2/4: Checking backend playwright...
call "%~dp0backend\venv\Scripts\activate.bat"
python -c "import playwright" >nul 2>nul
if errorlevel 1 (
    echo INFO: Installing playwright...
    pip install playwright==1.51.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo ERROR: playwright install failed
        pause
        exit /b 1
    )
    playwright install chromium
)

echo Step 3/4: Starting backend...
start "Backend" cmd /k "%~dp0backend\start-local-env.bat"

timeout /t 3 >nul

echo Step 4/4: Starting frontend...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ==========================================
echo Started:
echo   Frontend:  http://localhost:8080
echo   Backend:   http://localhost:8000
echo   Swagger:   http://localhost:8000/swagger
echo   RabbitMQ:  http://localhost:35672
echo   MinIO UI:  http://localhost:9001
echo.
echo Login: admin / 123456
echo.
echo Runner client:
echo   runner_client\start-client.bat
echo   Server: http://localhost:8000  then Login and Online
echo.
echo Legacy runner: runner\start-local.bat
echo ==========================================
echo.
pause
