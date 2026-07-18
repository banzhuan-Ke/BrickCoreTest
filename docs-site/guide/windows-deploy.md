# Windows 部署与本机开发

> 面向在 **Windows 10/11** 上自建 BrickCore（本仓库适用）。  
> **云服务器 Linux Docker** 请看 [Docker 部署](docker-deploy.md)。  
> **执行器**请用网盘安装包，见 [执行器安装指南](runner-install-guide.md)；本公开仓不含执行器引擎源码。

| 方式 | 是否需要 Docker | 适用场景 |
|------|-----------------|----------|
| **方式一：全本机安装（推荐）** | **不需要** | Docker Desktop 不好装 / 公司电脑限制虚拟化时 |
| **方式二：本机开发 + Docker 中间件** | 只要中间件 | 已装 Docker，只想省事起 MySQL 等 |
| **方式三：Docker 全栈** | 需要 | 不想本机装 Python / MySQL，整站容器化 |

---

## 默认账号（种子数据）

| 用途 | 用户名 | 密码 |
|------|--------|------|
| 平台登录 | `admin` | `BrickCore123456` |

中间件账号密码下文按方式分别说明。演示约定常用同一密码：`BrickCore123456`。

---

## 方式一：全本机安装（不用 Docker）

适合：不想装 Docker Desktop。本机分别安装 **MySQL、Redis、RabbitMQ、MinIO**，再跑 Backend + Frontend。

### 0. 必备软件

| 软件 | 版本 | 下载 |
|------|------|------|
| Git | 任意 | https://git-scm.com/download/win |
| Python | 3.10+ | https://www.python.org/downloads/（勾选 **Add to PATH**） |
| Node.js | 18+ | https://nodejs.org/ |
| MySQL | 8.0+ | https://dev.mysql.com/downloads/installer/ |
| Redis（Windows 移植版） | 5.x / 7.x | https://github.com/tporadowski/redis/releases |
| Erlang + RabbitMQ | 现行稳定版 | Erlang：https://www.erlang.org/downloads ；RabbitMQ：https://www.rabbitmq.com/docs/install-windows |
| MinIO（可选但推荐） | 最新 Windows | https://dl.min.io/server/minio/release/windows-amd64/minio.exe |

克隆代码：

```powershell
git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
cd BrickCore
```

### 1. 安装 MySQL

1. 安装时选 **Server only**，设置 root 密码（自行记住；下文示例用 `BrickCore123456`）
2. 用 MySQL Workbench / 命令行执行：

```sql
CREATE DATABASE fastapi DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'admin'@'%' IDENTIFIED BY 'BrickCore123456';
CREATE USER 'admin'@'localhost' IDENTIFIED BY 'BrickCore123456';
GRANT ALL PRIVILEGES ON fastapi.* TO 'admin'@'%';
GRANT ALL PRIVILEGES ON fastapi.* TO 'admin'@'localhost';
FLUSH PRIVILEGES;
```

3. 导入种子数据（在仓库根目录，需已把 `mysql` 加入 PATH）：

```powershell
mysql -h 127.0.0.1 -P 3306 -uadmin -pBrickCore123456 --default-character-set=utf8mb4 fastapi < database.sql
```

若本机没有 `mysql` 命令，可用 Workbench **Data Import** 导入根目录 `database.sql`。

### 2. 安装 Redis（便携版即可）

1. 从 [tporadowski/redis Releases](https://github.com/tporadowski/redis/releases) 下载 Windows zip，解压到例如 `C:\tools\Redis`
2. 编辑目录内 `redis.windows.conf`，增加或修改：

```conf
port 6379
requirepass BrickCore123456
```

3. 启动（可新建 `start-redis.bat`）：

```bat
@echo off
cd /d C:\tools\Redis
redis-server.exe redis.windows.conf
```

保持该窗口运行。验证：

```powershell
C:\tools\Redis\redis-cli.exe -a BrickCore123456 ping
# 应返回 PONG
```

> 默认用标准端口 **6379**（与 Docker 映射的 26379 不同）。只需在 `backend/.env` 里写 `REDIS_PORT=6379`。

### 3. 安装 RabbitMQ

1. 先装 **Erlang**，再装 **RabbitMQ Server**
2. 以管理员打开「RabbitMQ Command Prompt」或进入安装目录的 `sbin`，执行：

```bat
rabbitmq-plugins enable rabbitmq_management
rabbitmqctl add_user admin BrickCore123456
rabbitmqctl set_user_tags admin administrator
rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
```

3. 确认服务已启动（服务名一般为 `RabbitMQ`）

本机默认端口：

| 用途 | 端口 |
|------|------|
| AMQP（执行器 / Backend） | **5672** |
| 管理台 | **15672** → http://localhost:15672 |

> Docker 开发环境用的是 25672/35672；无 Docker 时用标准 **5672/15672**，并在 `.env` 中对应填写。

### 4. 启动 MinIO（文件 / 截图存储）

1. 下载 [`minio.exe`](https://dl.min.io/server/minio/release/windows-amd64/minio.exe) 到例如 `C:\tools\minio`
2. 新建数据目录 `C:\tools\minio-data`
3. `start-minio.bat`：

```bat
@echo off
set MINIO_ROOT_USER=admin
set MINIO_ROOT_PASSWORD=BrickCore123456
cd /d C:\tools\minio
minio.exe server C:\tools\minio-data --address ":9200" --console-address ":9001"
```

- S3 API：http://127.0.0.1:9200  
- 控制台：http://127.0.0.1:9001（账号 `admin` / `BrickCore123456`）

Backend 首次上传时一般会自动建 bucket；也可在控制台手动建 `test-results`、`ai-requirements`。

若暂时不跑 UI 截图，仍建议启动 MinIO，以免附件相关接口报错。

### 5. 配置并启动 Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

copy .env.example .env
notepad .env
```

将 `backend\.env` 调成与上面中间件一致（示例）：

```env
BASE_URL=http://localhost:8000
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_USER=admin
DATABASE_PASSWORD=BrickCore123456
DATABASE_NAME=fastapi

MQ_HOST=127.0.0.1
MQ_PORT=5672
MQ_USERNAME=admin
MQ_PASSWORD=BrickCore123456

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=BrickCore123456
REDIS_DB=15
SCHEDULER_REDIS_DB=7

STORAGE_TYPE=minio
MINIO_ENDPOINT=127.0.0.1:9200
MINIO_PUBLIC_ENDPOINT=127.0.0.1:9200
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=BrickCore123456
MINIO_SECURE=false
MINIO_BUCKET=test-results
AI_REQUIREMENT_BUCKET=ai-requirements

DOC_USERNAME=admin
DOC_PASSWORD=BrickCore123456
INTERNAL_API_KEY=brickcore-internal-demo
PLATFORM_VERSION=1.3.0
RUNNER_CLIENT_VERSION_LATEST=1.4.0
RUNNER_CLIENT_VERSION_MIN=1.3.8
RUNNER_ENGINE_VERSION=1.0.2
```

初始化表结构并启动：

```powershell
aerich upgrade
python run_new.py
```

Backend：http://localhost:8000  

依赖异常时可试：

```powershell
pip install bcrypt==4.2.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install --only-binary :all: greenlet
```

### 6. 启动 Frontend

新开 PowerShell：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：**http://localhost:8080**（端口以 `frontend/.env.development` 的 `VITE_PORT` 为准）。  
登录：**admin / BrickCore123456**

### 7. 日常启动顺序（无 Docker）

1. MySQL 服务（安装后一般开机自启）  
2. `start-redis.bat`  
3. RabbitMQ 服务  
4. `start-minio.bat`  
5. Backend：`cd backend && venv\Scripts\activate && python run_new.py`  
6. Frontend：`cd frontend && npm run dev`  

可自行写一个 `start-dev-nodocker.bat` 串联第 2～6 步。

### 8. 执行器注意（无 Docker 端口）

本机 Runner 上线时：

- 平台地址：`http://127.0.0.1:8000` 或前端反代地址  
- MQ / Redis 端口必须与 `backend/.env` 一致（本方式为 **5672**、**6379**），不要填 Docker 映射用的 25672 / 26379  

---

## 方式二：本机开发 + Docker 中间件

适合：已装好 Docker Desktop，不想手工装 MySQL/Redis。

**不要**再同时运行根目录全栈 `docker-compose.yml`。

### 1. 只启动中间件

```powershell
docker compose -f docker-services.yml up -d
docker compose -f docker-services.yml ps
```

| 服务 | 主机端口 | 账号 / 密码 |
|------|----------|-------------|
| MySQL | 3306 | `admin` / `BrickCore123456` |
| Redis | **26379** | 密码 `BrickCore123456` |
| RabbitMQ | **25672**（管理台 35672） | `admin` / `BrickCore123456` |
| MinIO | **9200**（控制台 9001） | `admin` / `BrickCore123456` |

### 2. 导入初始数据（首次）

```powershell
Get-Content .\database.sql -Raw | docker exec -i fastapi-mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi
```

### 3. Backend / Frontend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env
# 保持 REDIS_PORT=26379、MQ_PORT=25672（与 docker-services.yml 一致）
aerich upgrade
python run_new.py
```

另开窗口：

```powershell
cd frontend
npm install
npm run dev
```

访问 http://localhost:8080 。可选根目录 `start-local.bat`（需已建好 venv 且 `.env` 与中间件一致）。

---

## 方式三：Docker 全栈

适合：本机只装 Docker + Node（构建前端），不装 Python / MySQL。

### 1. 克隆并准备 `.env`

```powershell
git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
cd BrickCore
copy .env.example .env
notepad .env
```

示例：

```env
MYSQL_ROOT_PASSWORD=BrickCore123456
MYSQL_PASSWORD=BrickCore123456
REDIS_PASSWORD=BrickCore123456
RABBITMQ_PASSWORD=BrickCore123456
MINIO_ROOT_USER=admin
MINIO_PASSWORD=BrickCore123456
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=BrickCore123456
```

### 2. 调整 MinIO 对外地址

编辑 `docker-compose.yml` 中 backend 的：

```yaml
MINIO_PUBLIC_ENDPOINT: host.docker.internal:9200
```

### 3. 构建前端并启动

```powershell
cd frontend
npm install
npm run build
cd ..
docker compose up -d --build
docker compose logs -f backend
```

访问 http://localhost/ ，登录 **admin / BrickCore123456**。  
必要时：`docker exec -it fastapi_backend aerich upgrade`。

---

## 安装执行器（跑 Web 自动化）

1. 百度网盘：[链接](https://pan.baidu.com/s/1pObFpG-Mt7-Pxo58hklOlg?pwd=9gbi)（提取码 `9gbi`）下载 `BrickCoreRunner.zip`
2. 解压后运行 `BrickCoreRunner.exe`
3. 服务器地址：无 Docker 开发填 `http://127.0.0.1:8000`；Docker 全栈填 `http://localhost`
4. 登录并 **上线** → 设备管理确认在线  

端口须与当前 Backend 配置一致（方式一多为 5672/6379/9200；方式二/三多为 25672/26379/9200）。详见 [执行器安装指南](runner-install-guide.md)。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 不想装 Docker | 用 **方式一** |
| Redis / MQ 连不上 | 核对 `.env` 端口：无 Docker 用 6379/5672；Docker 中间件用 26379/25672 |
| 导入 SQL 失败 | 先建好库和 `admin` 用户；确认字符集 utf8mb4 |
| 登录失败 | 确认已导入 `database.sql`；账号 **admin / BrickCore123456** |
| 附件/截图打不开 | MinIO 已启动，且 `MINIO_PUBLIC_ENDPOINT` 为本机可访问地址 |
| Docker 装不上 / 无 Hyper-V | 不要用方式二/三，改方式一 |
| 页面空白（全栈） | 先 `npm run build`，确认有 `frontend/dist/index.html` |

---

## 相关文档

- [Docker 部署（Linux 云服务器）](docker-deploy.md)
- [执行器使用说明](runner-client.md)
- [执行器安装指南](runner-install-guide.md)
- [版本更新记录](release-notes.md)
- 仓库根目录 [README.md](../../README.md)
