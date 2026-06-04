# 方案 B：清空本地 Docker 数据卷并按新密码重建（与云上 docker-compose 一致）
# 用法：在项目根目录 PowerShell 执行  .\scripts\reset-local-docker.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 停止并删除本地基础服务（含数据卷）..." -ForegroundColor Cyan
docker compose -f docker-services.yml down -v

# 若曾用完整 compose 单独起过 MinIO，一并清理
docker rm -f fastapi-minio 2>$null
$minioVol = docker volume ls -q --filter name=minio
if ($minioVol) {
    docker volume rm $minioVol 2>$null
}

Write-Host "==> 启动 MySQL / Redis / RabbitMQ / MinIO ..." -ForegroundColor Cyan
docker compose -f docker-services.yml up -d

Write-Host "==> 等待 MySQL 就绪（约 30 秒）..." -ForegroundColor Cyan
Start-Sleep -Seconds 30

$mysqlOk = $false
for ($i = 0; $i -lt 12; $i++) {
    docker exec fastapi-mysql mysqladmin ping -h localhost -ufastapi -p"F@stAp1_ecure#2026" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $mysqlOk = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $mysqlOk) {
    Write-Host "[WARN] MySQL 可能尚未就绪，请稍后手动检查" -ForegroundColor Yellow
}

Write-Host "==> 执行数据库迁移..." -ForegroundColor Cyan
Push-Location backend
if (Test-Path "venv\Scripts\activate.ps1") {
    & .\venv\Scripts\activate.ps1
}
aerich upgrade
Pop-Location

Write-Host "==> 导入初始数据 database.sql ..." -ForegroundColor Cyan
Get-Content "database.sql" -Raw -Encoding UTF8 | docker exec -i fastapi-mysql mysql -ufastapi -p"F@stAp1_ecure#2026" fastapi

Write-Host ""
Write-Host "完成。请启动：" -ForegroundColor Green
Write-Host "  后端: cd backend && venv\Scripts\activate && python run_new.py"
Write-Host "  前端: cd frontend && npm run dev"
Write-Host "  Runner: cd runner && python main.py  (已配置 runner\.env 连 localhost)"
Write-Host "  登录: http://localhost:8080  admin / 123456"
