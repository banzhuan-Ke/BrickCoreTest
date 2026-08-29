# 测试管理扩展包（brickcore_tm）

质量门禁、指派通知 / 站内信、版本智能化、导出版本包等高级能力，由扩展包 **brickcore_tm** 提供。

| 部署方式 | 是否需要单独安装 |
|----------|------------------|
| **官方 Docker 镜像（已内置扩展包）** | 一般**不需要** |
| **从源码自建 · Docker / Linux 服务器** | 需要：下载 **linux** 版 `.bcpack` → 安装 → 重启 backend |
| **Windows 本机跑 backend** | 需要：下载 **win** 版 `.bcpack`（与本机 Python 主次版本一致，当前多为 3.11） |
| **macOS 本机跑 backend** | 需要：下载 **macos-arm64** 或 **macos-amd64**（按芯片）`.bcpack` |
| **Mac 上 Docker 跑 backend** | 装 **linux** 包（容器内是 Linux，不要用 macos 包） |

扩展包与平台版本需对齐；安装步骤见下文。

## 版本对齐

| 平台版本 | 扩展包版本 |
|----------|------------|
| 1.6.x / 1.7.x | 1.7.0 |

安装后可访问：`GET /test-management/premium-status`，应返回 `installed: true` 且 `compatible: true`。

## 获取安装包

1. Gitee Release 附件，或官方网盘（与执行器包同渠道维护）
2. 正式包文件名示例：
   - `brickcore_tm-1.7.0-linux-amd64-cp311.bcpack`（Docker / Linux）
   - `brickcore_tm-1.7.0-win-amd64-cp311.bcpack`（Windows 本机）
   - `brickcore_tm-1.7.0-macos-arm64-cp311.bcpack`（Apple Silicon 本机）
   - `brickcore_tm-1.7.0-macos-amd64-cp311.bcpack`（Intel Mac 本机）
3. 请选择与 backend **Python 主次版本**一致的包（官方镜像为 **3.11** → 选 `cp311`）

## Docker 安装（CE 自建）

```bash
docker cp brickcore_tm-1.7.0-linux-amd64-cp311.bcpack <backend容器名>:/tmp/
docker exec <backend容器名> python tools/install_brickcore_tm.py /tmp/brickcore_tm-1.7.0-linux-amd64-cp311.bcpack
docker compose restart backend
```

## Windows / 本机中间件

在 **backend 使用的同一个 Python 环境** 中执行：

```powershell
cd backend
python tools/install_brickcore_tm.py D:\downloads\brickcore_tm-1.7.0-win-amd64-cp311.bcpack
# 然后重启 uvicorn / 服务
```

## macOS 本机

```bash
cd backend
# Apple Silicon
python3.11 tools/install_brickcore_tm.py ~/Downloads/brickcore_tm-1.7.0-macos-arm64-cp311.bcpack
# Intel Mac 用 macos-amd64 包
# 然后重启 uvicorn / 服务
```

若 site-packages 无写权限，加 `--target` 指向可写目录，并保证该目录在 `PYTHONPATH` 中。

## 未安装时的行为

- 版本、计划、缺陷、评审、追溯等**基础能力可用**
- 质量门禁 / 智能化 / 导出 / 通知保存等返回 `503`，错误码 `tm_premium_required`
- 站内信列表为空，前端设置页显示黄色提示条

## 升级

1. 升级平台代码 / 镜像 + `aerich upgrade`
2. 若扩展包大版本变更：下载新 `.bcpack` 再装一次（覆盖）
3. 官方 Docker 随镜像升级即可，无需手装

调试可临时关闭扩展包探测：`BRICKCORE_TM_DISABLED=1`（仅开发用）。
