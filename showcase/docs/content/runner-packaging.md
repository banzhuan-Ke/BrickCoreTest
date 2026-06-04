# 执行器获取与发布

社区版（CE）仓库**不包含** Playwright 执行引擎源码，无法在本地从源码打包 `BrickCoreRunner`。请通过 **网盘** 获取 `BrickCoreRunner.zip` 后使用 UI 自动化与录制能力。

## 网盘获取

| 方式 | 说明 |
|------|------|
| **百度网盘（推荐）** | [BrickCoreRunner.zip](https://pan.baidu.com/s/1Nx2fkPAUi7htJKZAxp1paw?pwd=ye6b) · 提取码 `ye6b` |
| **演示平台** | 登录 [演示环境](http://43.142.83.156/) → **UI 自动化 → 设备管理** → **网盘下载** |
| **自建平台** | 管理员在 **系统管理 → 执行器发布** 配置网盘/OSS 链接；用户从设备管理页 **网盘下载** |

zip 约 **800MB**（含 Chromium）。解压后目录需包含 `BrickCoreRunner.exe`、`_internal/`、`runner/`、`VERSION.txt`，详见 [执行器使用说明](#runner-client)。

## 在自建平台配置网盘入口

1. 将 `BrickCoreRunner.zip` 上传至百度网盘 / 阿里云盘 / OSS（推荐，避免占满服务器磁盘）
2. 打开 **系统管理 → 执行器发布**（需 `device:edit`）
3. 填写 **网盘/OSS 链接** 与按钮文案（如「百度网盘下载」）→ 保存
4. 用户在 **设备管理** 点击对应按钮跳转网盘

可选环境变量（Backend `.env`）：

| 变量 | 说明 |
|------|------|
| `RUNNER_CLIENT_VERSION_LATEST` | 与 zip 内 `VERSION.txt` 一致，供客户端检查更新 |
| `RUNNER_CLIENT_VERSION_MIN` | 低于此版本的客户端将被拒绝上线 |
| `RUNNER_CLIENT_DOWNLOAD_URL` | 未配置「执行器发布」时的网盘外链兜底 |
| `RUNNER_MQ_PUBLIC_HOST` 等 | Windows 客户端连接 MQ/Redis 的对外地址 |

## Linux 无头执行

社区版 Git **不含** `runner/` 源码，无法按源码方式在 Linux 上 `python main.py` 启动引擎。常见做法：

- **Windows 测试机**：从网盘安装 `BrickCoreRunner` 并上线设备（推荐）
- **服务器 CI**：如需 Linux 无头 Runner，请联系项目维护者获取商业版引擎或托管执行节点

## 从源码自行打包（商业版）

若需 Nuitka 加固打包等完整流程，请使用 **商业版 Pro 仓库**（含 `runner/` 与 `scripts/build_runner_client.ps1`），或购买源码授权。

## 相关文档

- [执行器使用说明](#runner-client)
- [UI 自动化](#ui-automation)
- [系统管理 - 执行器发布](#system-admin)
