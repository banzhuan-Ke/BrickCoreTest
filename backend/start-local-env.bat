@echo off
cd /d "%~dp0"

rem Local Docker ports/passwords - match docker-services.yml
set MQ_HOST=127.0.0.1
set MQ_PORT=25672
set MQ_USERNAME=admin
set "MQ_PASSWORD=R4bb1t_MQ#2026"
set MQ_MANAGEMENT_HOST=127.0.0.1
set MQ_MANAGEMENT_PORT=35672

set REDIS_HOST=127.0.0.1
set REDIS_PORT=26379
set "REDIS_PASSWORD=R3d1s_S3cur3#2026"
set REDIS_DB=15

set DATABASE_HOST=127.0.0.1
set DATABASE_PORT=3306
set DATABASE_USER=fastapi
set "DATABASE_PASSWORD=F@stAp1_ecure#2026"
set DATABASE_NAME=fastapi

set MINIO_ENDPOINT=127.0.0.1:9200
set MINIO_PUBLIC_ENDPOINT=127.0.0.1:9200
set MINIO_ACCESS_KEY=admin
set "MINIO_SECRET_KEY=M1n10_S3cur3#2026"
set STORAGE_TYPE=minio

set RUNNER_MIDDLEWARE_ISOLATION=1

call "%~dp0venv\Scripts\activate.bat"
python "%~dp0run_new.py"
