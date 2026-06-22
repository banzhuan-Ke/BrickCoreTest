# BrickCore 自动化测试平台

基于 **FastAPI + Vue3** 的 Web UI / 接口 / 性能 / AI 一体化测试平台。

---

## 在线演示

可直接访问已部署的演示环境体验（接口 / AI / 性能等；**UI 自动化**需安装下方执行器）：

| 项 | 内容 |
|----|------|
| **演示地址** | **http://43.142.83.156/** |
| 登录账号 | `admin` |
| 登录密码 | `BrickCore123456` |

> 演示环境密码公开，请勿存放真实业务数据；自行部署后请修改密码。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| 接口自动化 | 接口管理、用例/套件/计划、数据工厂、定时任务 |
| AI 测试 | 需求生成功能用例、助手、问答评测、失败分析等 |
| 性能测试 | 场景压测；高并发可配合 **执行机** 中的分布式 Worker |
| Web UI 自动化 | 用例编排、录制、计划执行；需安装 **执行器**（Windows 客户端 / Mac 命令行） |

---

## 功能演示

README 内嵌大图会被 Gitee 压缩变糊，高清说明与录屏见演示站静态页（纯 HTML，随仓库 `showcase/` 部署）：

👉 **[产品功能演示](http://43.142.83.156/showcase/)**  可点击查看高清视频演示哦

👉 **[使用说明（文档）](http://43.142.83.156/showcase/docs/)** — 无需登录，与平台「文档中心」同目录

| 亮点 | 说明 |
|------|------|
| AI 需求 → 功能用例 | 上传 PRD，AI 批量生成，支持禅道 / 导出 XLSX |
| UI MCP 录制 | MCP / 平台助手驱动浏览器录制 |
| UI 定位器自愈 | 页面小改后自动尝试修复定位器 |
| 接口用例 AI 生成 | 基于 Swagger 生成接口自动化用例 |

---

## 执行器下载

UI 自动化、录制回放、分布式压测 Worker 需安装 **BrickCoreRunner**。

**推荐网盘下载**（同一百度分享，提取码 `9gbi`）：

| 系统 | 安装包 | 说明 |
|------|--------|------|
| **Windows** | `BrickCoreRunner.zip`（约 800MB） | 桌面客户端，双击 `BrickCoreRunner.exe` |
| **macOS · Apple 芯片** | `BrickCoreRunner-mac-arm64.zip`（约 330MB） | M 系列 Mac，`uname -m` → `arm64` |
| **macOS · Intel** | `BrickCoreRunner-mac-intel.zip`（约 340MB） | Intel Mac，`uname -m` → `x86_64` |

👉 [百度网盘下载](https://pan.baidu.com/s/1pObFpG-Mt7-Pxo58hklOlg?pwd=9gbi) · 提取码 **`9gbi`**

| 方式 | 说明 |
|------|------|
| **演示平台内** | 登录 [http://43.142.83.156/](http://43.142.83.156/) → **UI 自动化 → 设备管理** → **网盘下载**（Windows） |

**Windows 安装：**

1. 下载并解压 `BrickCoreRunner.zip`（路径勿含中文/空格）
2. 运行 `BrickCoreRunner.exe`，服务器地址填 **`http://43.142.83.156`**
3. 使用演示账号登录，点击 **上线**；在 **设备管理** 确认在线

**macOS 安装：**

1. 按芯片下载 **arm64** 或 **intel** 包，在 Mac 上解压（勿在 Windows 解压）
2. 终端执行：`chmod +x connect-mac.sh start-mac.sh` → `./connect-mac.sh` → `./start-mac.sh`
3. 在平台 **设备管理** 确认在线

更多说明：[docs-site/guide/runner-client.md](docs-site/guide/runner-client.md)

> **维护者**：更新网盘分享后，请同步修改本 README，并在演示机 **系统管理 → 执行器发布** 填写相同外链，便于平台内「网盘下载」按钮跳转。

---

## Linux 服务器 Docker 部署（自建）

**第一次部署请直接跟详细文档（按步骤 0～9 执行）：**

👉 **[docs-site/guide/docker-deploy.md](docs-site/guide/docker-deploy.md)**（**腾讯云 CVM + OpenCloudOS 9** 完整示例）

根目录下文仅作速查；环境安装、安全组、排错以部署文档为准。

> **注意**：服务器上**只使用** `docker-compose.yml` 全栈，**不要**再跑 `docker-services.yml`（会端口冲突）。

### 部署前准备

| 项 | 要求 |
|----|------|
| 系统 | **OpenCloudOS 9**（腾讯云常见）或其它 64 位 Linux |
| 规格 | **2GB+** 内存、**50GB+** 磁盘 |
| Git / Node / Docker | 见部署文档步骤 1～2；OpenCloudOS 用 `dnf install nodejs npm`，**不要用** `dnf module nodejs` 和 NodeSource 一键脚本 |
| 腾讯云 | 安全组放行 **TCP 80**（必开） |

### 速查命令（已完成步骤 1～2 后）

```bash
git clone https://gitee.com/BanZhuanKeOrz/BrickCore.git
cd BrickCore
cd frontend && npm install && npm run build && cd ..

# 建议改 docker-compose.yml：MINIO_PUBLIC_ENDPOINT: <公网IP>:9200

docker compose up -d --build
docker compose logs -f backend    # 出现「启动后端服务」后 Ctrl+C

docker exec -i fastapi_mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database.sql
```

访问 **http://你的公网IP/**，登录 **admin / BrickCore123456**。

### 默认账号（演示）

| 用途 | 账号 | 密码 |
|------|------|------|
| 平台 | admin | BrickCore123456 |
| MySQL | admin | BrickCore123456（库 `fastapi`） |

---

## 本机开发（可选）

见 [部署文档 · 附录 B](docs-site/guide/docker-deploy.md#附录-b本机开发不要用-docker-composeyml-全栈)。

---

## 文档

| 文档 | 说明 |
|------|------|
| **[Docker 部署（腾讯云 OpenCloudOS）](docs-site/guide/docker-deploy.md)** | 自建环境跟做 |
| [docs-site/](docs-site/) | 功能使用说明 |

---

## 测试交流群

使用、部署或反馈问题时，欢迎加入 **BrickCoreAI 测试平台交流群**（微信群）：

<p align="center">
  <img src="assets/readme/image-wechat-group-brickcore.png" width="260" alt="BrickCoreAI 测试平台交流群" /><br />
  <sub>微信扫码加入 · 交流安装部署、用例编写与平台使用 · 二维码 7 天内有效，过期请联系下方作者微信</sub>
</p>

---

## 支持与交流

- 觉得有用欢迎 **Star**
- 问题与建议：加入上方 **测试交流群**，或扫下方微信好友二维码私聊

<p align="center">
  <img src="assets/readme/image-20260604162222425.png" width="200" alt="微信好友二维码" /><br />
  <sub>微信好友</sub>
</p>

## License

平台源码遵循 [LICENSE](LICENSE)。执行器见 [LICENSE-RUNNER.md](LICENSE-RUNNER.md)。
