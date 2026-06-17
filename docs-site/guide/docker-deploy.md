# Docker 部署（腾讯云 · OpenCloudOS 示例）

> 根目录 **[README.md](../../README.md)** 有精简版命令；**本文按腾讯云 CVM + OpenCloudOS 9 从零跟做即可**（你当前的 `VM-xx-opencloudos` 即此类环境）。

使用仓库根目录 **`docker-compose.yml`** 一次性部署全栈：MySQL、Redis、RabbitMQ、MinIO、后端、Nginx 前端。

> **不要** 在同一台机器上再执行 `docker-services.yml`（会重复起 MySQL，端口冲突）。该文件仅用于本机开发，见文末附录。

---

## 环境要求

| 项 | 建议 |
|----|------|
| 云厂商 | **腾讯云 CVM**（其它云步骤类似，安全组名称不同） |
| 系统 | **OpenCloudOS 9** / TencentOS Server 4（64 位） |
| 规格 | 2 核+，**8GB+** 内存，**50GB+** 系统盘（首次 `docker compose build` 较久） |
| Docker | 20.10.9+（OpenCloudOS 官方要求），推荐 24+ 且带 **Compose V2** |
| Node.js | **18+**（OpenCloudOS 源里一般为 18 LTS，用于 `npm run build`） |
| 网络 | 能访问 Gitee、Docker Hub（慢可配镜像加速） |

---

## 部署前：腾讯云安全组（必做）

在 **腾讯云控制台 → 云服务器 → 安全组 → 入站规则** 中放行：

| 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|
| TCP | **80** | 0.0.0.0/0（或办公网） | **平台页面 + API 反代（必开）** |
| TCP | **25672** | Runner 测试机公网 IP | RabbitMQ，执行器上线后收任务 |
| TCP | **26379** | Runner 测试机公网 IP | Redis，日志/实时画面 |
| TCP | **9200** | Runner 测试机公网 IP | MinIO，UI 截图/视频上传 |
| TCP | 8000 | 可选 | 直连 API / Swagger 调试（生产可不开放） |
| TCP | 22 | 你的 IP | SSH（一般已有） |

> `25672`、`26379`、`9200` 不要对 `0.0.0.0/0` 全网开放，仅放行信任的 Runner 机器 IP。

记下实例 **公网 IP**（后文用 `<公网IP>` 表示），例如 `123.45.67.89`。

---

## 标准部署流程（逐步执行）

以下均在 SSH 登录服务器后执行（`root` 或 `sudo`）。**建议整段复制到终端，每步确认无报错再继续。**

### 步骤 0：确认系统

```bash
cat /etc/os-release | head -5
# 应看到 OpenCloudOS 或 TencentOS

uname -m
# x86_64 或 aarch64，后文 Docker 源按此架构自动识别
```

### 步骤 1：安装 Git 与 Node.js

OpenCloudOS **没有** `dnf module nodejs`，也**不要**用 NodeSource 的 `curl setup_20.x | bash`（会报 RPM 识别错误）。

```bash
sudo dnf makecache
sudo dnf install -y git

# 若提示找不到 nodejs，先装 EPOL 源（拼写是 epol，不是 epel）
sudo dnf install -y epol-release
sudo dnf makecache

sudo dnf install -y nodejs npm

node -v    # 期望 v18.x 或更高
npm -v
```

若 `node -v` 低于 18 或 `npm run build` 失败，改用 NVM 装 Node 20：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
node -v
```

### 步骤 2：安装 Docker 与 Compose

OpenCloudOS 与 CentOS 兼容，使用 Docker 官方 **centos** 源即可：

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo systemctl enable --now docker

docker compose version
# 能输出版本号即可
```

国内拉镜像慢时，可配置加速（示例，按你账号替换地址）：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]
}
EOF
sudo systemctl restart docker
```

### 步骤 3：克隆代码

```bash
cd /opt
git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
cd BrickCore
```

### 步骤 4：构建前端

```bash
cd frontend
npm install
npm run build
cd ..

ls frontend/dist/index.html
# 必须存在，否则 Nginx 页面会空白
```

> 若 `npm install` 很慢或内存不足，可在 Windows 本机构建后上传：  
> `scp -r frontend/dist root@<公网IP>:/opt/BrickCore/frontend/`

### 步骤 5：配置 MinIO 公网地址（建议）

用浏览器访问平台时，报告/附件链接需指向公网，编辑 `docker-compose.yml` 中 **backend** 的环境变量：

```yaml
MINIO_PUBLIC_ENDPOINT: <公网IP>:9200
```

例如公网 IP 为 `123.45.67.89` 则写 `123.45.67.89:9200`。

Backend 启动时会自动创建 MinIO 默认 bucket（`test-results`、`api-test-files`、`ui-test-files`、`ai-requirements`，名称随环境变量 `MINIO_BUCKET` 等）；Runner 首次上传截图时若目标 bucket 不存在也会自动创建，**无需**再手工建桶。  
可稍后再改；改完执行 `docker compose up -d --build backend`。

### 步骤 6：启动全栈

在 `/opt/BrickCore`（仓库根目录）执行：

```bash
docker compose up -d --build
```

首次约 **10～30 分钟**（拉镜像 + 构建后端 Playwright 镜像）。另开 SSH 窗口查看日志：

```bash
cd /opt/BrickCore
docker compose ps
docker compose logs -f backend
```

看到 **「启动后端服务」** 且 `backend` 状态为 `running` 后，按 `Ctrl+C` 退出日志。

### 步骤 7：导入演示数据（首次必做）

**须在后端日志出现「启动后端服务」之后**再导入（表由 `aerich upgrade` 创建；旧版 SQL 里的 `module` 表已废弃）。

```bash
cd /opt/BrickCore
docker exec -i fastapi_mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database.sql
```

无报错即已写入管理员 `admin` 与示例项目（演示名称均为 **BrickCore**）。

若页面显示中文乱码，或已从旧库导入，可执行名称修正：

```bash
docker exec -i fastapi_mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database-demo-fix-labels.sql
```

若报错 **`Table 'fastapi.module' doesn't exist`**：说明 `database.sql` 过旧。先尝试登录（部分数据可能已写入）；再执行补导入：

```bash
cd /opt/BrickCore
git pull   # 拉取含 database-demo-patch.sql 的最新仓库
docker exec -i fastapi_mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database-demo-patch.sql
```

或重新 `git pull` 后只导入更新后的 `database.sql`（全新库请先 `docker compose down -v` 再 up，慎用会清空数据）。

### 步骤 8：系统防火墙（firewalld）

```bash
sudo systemctl status firewalld
# 若为 active，执行：
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

再次确认 **腾讯云安全组** 已放行 **80**（步骤见上文）。

本机自测：

```bash
curl -I http://127.0.0.1/
# 期望 HTTP/1.1 200 或 304
```

### 步骤 9：浏览器访问

| 地址 | 说明 |
|------|------|
| **http://你的公网IP/** | 平台首页（推荐） |
| http://你的公网IP:8000 | API / Swagger |
| http://你的公网IP:35672 | RabbitMQ 管理台（演示环境勿长期对公网开放） |
| http://你的公网IP:9001 | MinIO 控制台 |

登录：**admin** / **BrickCore123456**

---

## BrickCore Runner 桌面客户端（Windows 测试机）

在同事 Windows 电脑安装 `BrickCoreRunner.zip` 后：

| 步骤 | 配置 |
|------|------|
| 服务器地址 | **管理服务器环境** → 添加 `http://<公网IP>`（**勿写 `:8000`**） |
| 登录 | 使用平台账号；探活 `GET /runner/health` 走 **80** 端口 |
| 上线 | 需安全组对该机 IP 放行 **25672**（MQ）、**26379**（Redis） |
| 跑 UI 用例 | 截图/录屏上传还需 **9200**（MinIO 预签名 PUT） |

**误配提示**：填 `http://<IP>:8000` 会「无法访问服务器」——Docker 生产环境 API 经 Nginx **80** 反代，8000 通常未对公网开放。

**测试机自检**：

```powershell
curl.exe http://<公网IP>/runner/health
Test-NetConnection <公网IP> -Port 25672
Test-NetConnection <公网IP> -Port 26379
Test-NetConnection <公网IP> -Port 9200
```

详见 [执行器使用说明](runner-client.md)、[执行器打包](runner-packaging.md)（Pro 仓 `docs/其他文档/CE同步与发布手册.md` 有 Pro→CE 发布流程）。

---

## 部署完成后：常用操作

```bash
cd /opt/BrickCore

# 查看所有容器
docker compose ps

# 看后端日志
docker compose logs -f backend

# 停止
docker compose down

# 更新代码后
git pull
cd frontend && npm install && npm run build && cd ..
docker compose up -d --build
```

## 容器与端口

| 容器名 | 服务 | 宿主机端口 |
|--------|------|------------|
| fastapi_mysql | MySQL 8 | 3306 |
| fastapi_redis | Redis 7 | 26379 |
| fastapi_rabbitmq | RabbitMQ | 25672 / 35672 |
| fastapi-minio | MinIO | 9200 / 9001 |
| fastapi_backend | 后端 | 8000 |
| fastapi_nginx | 前端 + 反代 | **80** |

## 执行器（UI / 分布式压测）

Docker 只部署**平台**。UI 自动化、分布式 Worker 需在 **Windows** 安装 **BrickCoreRunner.zip**（约 800MB）：

1. **网盘下载**：见仓库 [README](../../README.md#执行器下载windows--约-800mb)；或登录演示环境 **设备管理 → 网盘下载**
2. 解压运行 `BrickCoreRunner.exe`，服务器填 **`http://43.142.83.156`**（自建填你的地址），演示账号 `admin` 登录并 **上线**
3. **设备管理** 中确认在线  

详见 [执行器说明](runner-client.md)。

## 生产环境注意

公网演示后请修改默认密码，并在 `docker-compose.yml` 的 `backend.environment` 中设置 `SECRET_KEY`、`INTERNAL_API_KEY` 等；安全组尽量只开放 80/443。

## 常见问题（OpenCloudOS / 腾讯云）

**Q：`dnf module` 报 `missing groups or modules: nodejs`？**  
正常。OpenCloudOS 用 **`dnf install nodejs npm`**，不要用 `dnf module`。

**Q：NodeSource 报 `intended for RPM-based systems`？**  
不要用 `curl setup_20.x | bash`，用步骤 1 的 `dnf install` 或 NVM。

**Q：外网打不开，本机 `curl 127.0.0.1` 正常？**  
查 **腾讯云安全组** 是否放行 80，以及 firewalld 是否放行 http。

**Q：页面空白？**  
是否执行步骤 4，是否存在 `frontend/dist/index.html`。

**Q：无法登录？**  
是否在后端启动后执行步骤 7 导入 `database.sql`。

**Q：附件链接是 localhost？**  
完成步骤 5 修改 `MINIO_PUBLIC_ENDPOINT` 为 `<公网IP>:9200` 并重建 backend。

**Q：80 端口被占用？**  
`sudo ss -tlnp | grep ':80 '`；如有 `httpd`：`sudo systemctl stop httpd && sudo systemctl disable httpd`。

---

## 附录 A：CentOS / Rocky / AlmaLinux

与 OpenCloudOS 步骤相同；Node 可尝试 `dnf module install nodejs:20`，或直接 `dnf install nodejs npm`。Docker 仍用 `linux/centos/docker-ce.repo`。

## 附录 B：本机开发（不要用 docker-compose.yml 全栈）

```bash
docker compose -f docker-services.yml up -d
docker exec -i fastapi-mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database.sql

cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && aerich upgrade && python run_new.py

cd ../frontend && npm install && npm run dev
```

访问 http://localhost:8080
