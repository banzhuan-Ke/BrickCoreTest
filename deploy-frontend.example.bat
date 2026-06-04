@echo off
REM 复制为 deploy-frontend.local.bat 并填写你的服务器（勿提交 .local.bat）
REM Copy to deploy-frontend.local.bat and set your server (do not commit .local.bat)

setlocal
cd /d "%~dp0"

set "DEPLOY_HOST=YOUR_SERVER_IP"
set "DEPLOY_USER=root"
set "DEPLOY_ROOT=/opt/brickcore"

if not exist "frontend\package.json" (
    echo ERROR: run from repo root
    exit /b 1
)

cd frontend
call npm run build
if errorlevel 1 exit /b 1
cd ..

echo Upload dist to %DEPLOY_USER%@%DEPLOY_HOST%:%DEPLOY_ROOT%/frontend/
scp -r "%~dp0frontend\dist" %DEPLOY_USER%@%DEPLOY_HOST%:%DEPLOY_ROOT%/frontend/
ssh %DEPLOY_USER%@%DEPLOY_HOST% "cd %DEPLOY_ROOT% && docker compose restart nginx"
echo Done.
endlocal
