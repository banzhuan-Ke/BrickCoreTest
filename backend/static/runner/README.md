# Runner 客户端安装包目录

平台 **平台下载** 读取容器内路径：`/app/static/runner/BrickCoreRunner.zip`。

## 获取安装包

| 方式 | 说明 |
|------|------|
| **网盘（推荐）** | 见根目录 README 或 [执行器获取与发布](../../docs-site/guide/runner-packaging.md) |
| **本目录放置 zip** | 将 `BrickCoreRunner.zip` 放到本目录，供容器内 `GET /runner/client-download` 使用 |

维护者无需在本仓库内打包客户端；请使用官方发布的 `BrickCoreRunner.zip`，版本号与 `RUNNER_CLIENT_VERSION_LATEST` 保持一致。

## 上传到自建服务器

若使用本目录分发（非网盘），可将 zip 复制到服务器后挂载或 `docker cp` 进 `fastapi_backend`：

```bash
# 示例：复制到运行中的后端容器
docker cp BrickCoreRunner.zip fastapi_backend:/app/static/runner/BrickCoreRunner.zip
```

## 推荐：网盘分发

**系统管理 → 执行器发布** 填写网盘/OSS 链接，无需占用本目录磁盘。

## 配置

| 方式 | 说明 |
|------|------|
| 平台页面 | **系统管理 → 执行器发布**（DB，推荐） |
| 本目录文件 | 平台下载（需挂载或 docker cp） |
| `RUNNER_CLIENT_DOWNLOAD_URL` | 环境变量外链兜底 |
| `RUNNER_CLIENT_VERSION_LATEST` | 与 zip 内 VERSION.txt 一致（当前 **1.4.0**） |

## 运行库与测试机要求（v1.4.0）

| 项 | 说明 |
|----|------|
| 系统 | Windows 10/11 x64 |
| Python | **打包版无需安装**；zip 内已含嵌入式 Python 3.11 |
| 运行库 | MSVCP140 / VCRUNTIME140 已内置；`greenlet` DLL 报错请重下最新 zip |
| Playwright | Chromium 已内置；勿只复制 exe，须保留 `_internal/` 与 `runner/` |
| 网络 | 平台 80；MQ 25672；Redis 26379；MinIO 9200 |

用户安装与排查见文档站 [执行器使用说明](../../docs-site/guide/runner-client.md)、[Runner 排查指南](../../docs-site/guide/runner-troubleshooting.md)。

## API

- `GET /runner/client-release` — 版本、`runner_notices` 运行提示与安装包是否可用
- `GET /runner/client-download` — 下载 zip（需登录）

## Docker 挂载（建议）

```yaml
volumes:
  - ./backend/static/runner:/app/static/runner
```
