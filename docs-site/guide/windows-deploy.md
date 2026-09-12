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

**库表与种子顺序（重要）**：只手工建空库 `fastapi` 即可，**不要**手工建表，也**不要**跑 `aerich init` / `aerich init-db`（仓库已带 migrations）。正确顺序是：配好 `backend/.env` → 在 `backend` 目录执行 **`aerich upgrade`** 生表 → 再导入根目录 **`database.sql`**（仅演示 INSERT）。

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
git clone https://github.com/banzhuan-Ke/BrickCoreTest.git
# 镜像：git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
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

> `database.sql` 只有演示 **INSERT**，不含建表。请先完成下文 **`aerich upgrade`**，再导入种子数据；空库直接导入会报 `Table 'fastapi.user' doesn't exist`。

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

# 可选：定位器自愈等仍可能在 Backend 本机起 Playwright（AI 浏览器任务已迁 Runner）
# python -m playwright install chromium

copy .env.example .env
notepad .env
```

> **易漏点**：智能浏览器与 AI 生成用例的浏览器操作建议在 **在线 Web 执行机** 上跑（减轻平台压力、支持有头调试），请配置 **平台对外地址** 并保持 Runner 在线。仅在使用 **定位器自愈** 等 Backend 本机 Playwright 能力且报  
> `Executable doesn't exist ... ms-playwright\chromium_...` 时，再在 **Backend 的 venv** 内执行 `python -m playwright install chromium` 并重启 Backend。

将 `backend\.env` 调成与上面中间件一致（**必须保存**；无 Docker 方式一端口见下）。至少确认这几行：

- `DATABASE_USER=admin`（不要留成示例默认的 `fastapi`）
- `DATABASE_PASSWORD=BrickCore123456`（与建库时一致）
- `DATABASE_HOST=127.0.0.1`、`DATABASE_PORT=3306`、`DATABASE_NAME=fastapi`

完整示例：

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
PLATFORM_VERSION=1.8.0
RUNNER_CLIENT_VERSION_LATEST=1.8.0
RUNNER_CLIENT_VERSION_MIN=1.3.8
RUNNER_ENGINE_VERSION=1.8.0
RUNNER_ENGINE_VERSION_MIN=1.0.0
```

> 若你本地平台是 **v1.4.0**，把 `PLATFORM_VERSION=1.4.0`、`RUNNER_CLIENT_VERSION_LATEST=1.4.5` 即可；连库账号仍用 **`admin`**。

先确认 **MySQL 服务已启动**，再初始化表结构（只需 **`aerich upgrade`**，勿执行 `aerich init` / `init-db`）。  
`aerich` 会通过配置读取 `backend/.env`；若仍报连库用户为 `fastapi`，说明 `.env` 未保存或未放在 `backend` 目录。

可先自检（应打印 `admin`）：

```powershell
python -c "from dotenv import load_dotenv; load_dotenv('.env'); import os; print(os.getenv('DATABASE_USER'), os.getenv('DATABASE_PASSWORD'))"
```

然后：

```powershell
aerich upgrade
```

表建好后（仓库根目录，需已把 `mysql` 加入 PATH）导入种子数据：

```powershell
cd ..
mysql -h 127.0.0.1 -P 3306 -uadmin -pBrickCore123456 --default-character-set=utf8mb4 fastapi < database.sql
cd backend
```

若本机没有 `mysql` 命令，可用 Workbench **Data Import** 导入根目录 `database.sql`。然后启动：

```powershell
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

> **仅本机访问**：`npm run dev` 会读 `frontend/.env.development`，其中 `VITE_BASE_API` 默认是 `http://localhost:8000`。  
> 服务器本机登录正常、**局域网其他电脑打开页面却「网络错误」** 是预期现象——浏览器在对方电脑上请求了对方自己的 `localhost`。  
> 需要给同事用时，见下文 **「局域网内其他电脑访问」**。

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

### 9. 局域网内其他电脑访问（方式一 / 方式二）

前提：已在服务器上按上文跑通 Backend + Frontend，本机用 `http://localhost:8080` 能登录。  
先查服务器局域网 IP（示例用 `192.168.1.233`，请换成你的）：

```powershell
ipconfig
# 看「以太网」或「WLAN」的 IPv4 地址
```

Windows 防火墙放行 **8080**（前端）和 **8000**（后端；临时方案需要）。

#### 方案 A：继续 `npm run dev`（临时 / 演示）

适合：IP 基本固定、先让同事能登录。**前端与后端端口不同，必须同时改 API 地址并放行 CORS。**

1. 编辑 `frontend/.env.development`：

```env
VITE_BASE_API="http://192.168.1.233:8000"
VITE_BASE_WS="ws://192.168.1.233:8000"
```

2. 编辑 `backend/.env`，追加（或改成你的前端来源；多个用来源逗号分隔）：

```env
CORS_ALLOWED_ORIGINS=http://192.168.1.233:8080
```

> 只改前端、不改 CORS 时，浏览器会报：  
> `blocked by CORS policy: No 'Access-Control-Allow-Origin' header`  
> （页面在 `:8080`，接口在 `:8000`，属于跨域。）

3. **重启 Backend**（`python run_new.py`）与 **Frontend**（先停再 `npm run dev`）。改 `.env` 不重启不生效。

4. 其他电脑浏览器访问：`http://192.168.1.233:8080`（不要写 `localhost`）。

5. 自检（在出问题的电脑按 F12 → Network）：
   - 错误：`http://localhost:8000/...` → 前端仍是旧配置，未改或未重启  
   - 错误：CORS / `Access-Control-Allow-Origin` → 未配 `CORS_ALLOWED_ORIGINS` 或未重启 Backend  
   - 正常：请求为 `http://192.168.1.233:8000/sys/...` 且状态 200

IP 变更后需同步改两处 `.env` 并重启。长期给多人用请用方案 B。

#### 方案 B：生产构建 + Nginx 同域（推荐）

适合：局域网长期访问。接口与页面同端口，**不必**配置 CORS，也**不要**把 `localhost:8000` 打进前端包。

**思路**：浏览器只访问 `http://服务器IP:8080` → Nginx 把页面文件直接返回，把 `/sys`、`/ai` 等 API **转发**到本机已启动的 Backend `127.0.0.1:8000`。对浏览器来说仍是同一域名端口，故无跨域。

1. 确认 `frontend/.env.production` 中为（仓库默认即如此）：

```env
VITE_BASE_API=""
VITE_BASE_WS=""
```

2. **停掉** `npm run dev`（否则会占 8080）。构建：

```powershell
cd frontend
npm install
npm run build
# 确认存在 frontend\dist\index.html
```

3. 安装 Nginx for Windows：打开 [nginx.org/en/download.html](https://nginx.org/en/download.html)，下载 **Stable** 的 zip，解压到例如 `C:\tools\nginx`。目录里应有 `nginx.exe`、`conf\`、`html\`。

4. 用仓库根目录 `nginx.conf` 改一版给 Windows（不要直接覆盖成 Linux 路径）。复制为 `C:\tools\nginx\conf\nginx.conf`，至少改这几处：

```nginx
# 原：include /etc/nginx/mime.types;
include       mime.types;

# 原：listen 80;
listen 8080;

# 所有 root /usr/share/nginx/html; 改成你的 dist 绝对路径（正斜杠）
# 例如代码在 D:\ework\BrickCore：
root D:/ework/BrickCore/frontend/dist;
```

`location /` 与静态资源缓存那两处的 `root` 都要改。`proxy_pass http://127.0.0.1:8000;` **不用改**（Nginx 与 Backend 在同一台机）。其余 `location`（`/sys`、`/mock/`、`/ws/` 等）保持仓库配置即可。

5. Backend 照常运行（`python run_new.py`，监听 8000）。启动 Nginx：

```powershell
cd C:\tools\nginx
.\nginx.exe
# 改配置后重载：
.\nginx.exe -s reload
# 停止：
.\nginx.exe -s stop
```

若提示端口被占用：先结束仍在跑的 `npm run dev`，或把 `listen` 改成别的端口。  
防火墙放行 Nginx 监听端口（如 **8080**）；此时别人**不必**直连 8000。

6. 其他电脑只访问：`http://192.168.1.233:8080`。  
   F12 → Network：接口应为 `http://192.168.1.233:8080/sys/...`，**不应**再出现 `localhost:8000`。

7. 前端有更新时：再执行 `npm run build`，然后 `nginx.exe -s reload`（或重启 Nginx）。一般不用改 conf。

8. 也可改用上文 **方式三：Docker 全栈**（镜像内已含 Nginx + 构建流程），访问入口以 compose / 文档为准。

> **Python 位数**：请使用 **64 位** Python 3.10–3.12 建 venv。若 `python -c "import sys; print(sys.version)"` 出现 `32 bit`，`matplotlib` / `numpy` 等常无 Windows wheel，会误走源码编译并报找不到 `cl`/`gcc`。请改装 64 位后重建 venv。

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

### 2. Backend / Frontend（先建表，再导种子）

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env
# 保持 REDIS_PORT=26379、MQ_PORT=25672（与 docker-services.yml 一致）
aerich upgrade
```

表建好后导入演示数据（仓库根目录）：

```powershell
cd ..
Get-Content .\database.sql -Raw | docker exec -i fastapi-mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi
cd backend
python run_new.py
```

另开窗口：

```powershell
cd frontend
npm install
npm run dev
```

访问 http://localhost:8080 。可选根目录 `start-local.bat`（需已建好 venv 且 `.env` 与中间件一致）。

> 局域网其他电脑访问：同样适用方式一 **§9**（改 `VITE_BASE_API` + `CORS_ALLOWED_ORIGINS`，或 `npm run build` + Nginx）。

---

## 方式三：Docker 全栈

适合：本机只装 Docker + Node（构建前端），不装 Python / MySQL。

### 1. 克隆并准备 `.env`

```powershell
git clone https://github.com/banzhuan-Ke/BrickCoreTest.git
# 镜像：git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
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
| 导入 SQL 失败 / `Table 'fastapi.user' doesn't exist` | 先 `aerich upgrade` 建表，再导 `database.sql`；并确认已建库、`admin` 用户与 utf8mb4 |
| `aerich` 报 Access denied / 用户 `fastapi` | 确认 `backend/.env` 已保存且 `DATABASE_USER=admin`；在 `backend` 目录执行；先跑上面的自检打印；并确认 MySQL 服务已启动 |
| 登录失败 | 确认已 `aerich upgrade` 且导入 `database.sql`；账号 **admin / BrickCore123456** |
| 附件/截图打不开 | MinIO 已启动，且 `MINIO_PUBLIC_ENDPOINT` 为本机可访问地址 |
| Docker 装不上 / 无 Hyper-V | 不要用方式二/三，改方式一 |
| 页面空白（全栈） | 先 `npm run build`，确认有 `frontend/dist/index.html` |
| AI 生成 Agent（MCP）/ 探索失败：`Executable doesn't exist` / `ms-playwright` | 在 **Backend** 目录激活 `venv` 后执行 `python -m playwright install chromium`，重启 Backend（与 Runner 浏览器无关） |
| 服务器本机能登录，局域网其他电脑「网络错误」 | `npm run dev` 默认请求 `localhost:8000`；按 **§9** 改 API 为服务器 IP 并配置 CORS，或改用 build + Nginx |
| 已改成服务器 IP，仍报 CORS / `Access-Control-Allow-Origin` | 在 `backend/.env` 增加 `CORS_ALLOWED_ORIGINS=http://<服务器IP>:8080` 并**重启 Backend** |
| `pip install` 编译 matplotlib 失败 / 找不到 `cl` | 多为 **32 位** Python；改用 64 位并重建 venv（见 §9 末） |

---

## 相关文档

- [Docker 部署（Linux 云服务器）](docker-deploy.md)
- [执行器使用说明](runner-client.md)
- [执行器安装指南](runner-install-guide.md)
- [版本更新记录](release-notes.md)
- 仓库根目录 [README.md](../../README.md)
