# BrickCore Runner 客户端（GUI）

Windows 桌面程序：登录 BrickCore 平台、选择环境、**上线**执行设备、检查更新。  
**执行引擎**（Playwright、MQ 消费等）已包含在网盘分发的 `BrickCoreRunner.zip` 内；社区版仓库**不含** `runner/` 引擎源码。

## 网盘获取（社区版）

| 方式 | 说明 |
|------|------|
| **百度网盘（推荐）** | [BrickCoreRunner.zip](https://pan.baidu.com/s/1Nx2fkPAUi7htJKZAxp1paw?pwd=ye6b) · 提取码 `ye6b` |
| **演示平台** | http://43.142.83.156/ → **UI 自动化 → 设备管理** → **网盘下载** |
| **自建平台** | **系统管理 → 执行器发布** 配置网盘/OSS 链接 → 设备管理页下载 |

详细步骤见 [docs-site/guide/runner-client.md](../docs-site/guide/runner-client.md)、[执行器获取与发布](../docs-site/guide/runner-packaging.md)。

## 使用流程

1. 从网盘下载并解压 `BrickCoreRunner.zip`（保留 `exe`、`_internal`、`runner` 目录）
2. 运行 `BrickCoreRunner.exe`，填写平台地址
3. 使用平台账号 **登录** → 填写设备名称 → **上线**
4. 在平台 **设备管理** 确认状态为 **在线**

切换环境：先 **下线**，再更换地址后重新登录/上线。

## 本目录源码说明

| 项 | 说明 |
|----|------|
| 技术栈 | PySide6 桌面壳 + 调用平台 API |
| 社区版 | 可阅读、集成参考；**不提供** 引擎打包脚本与 `runner/` 源码 |
| 商业版 | 含完整 `runner/` 与打包脚本，可自行构建 zip 分发 |

从源码运行（仅调试 GUI，**仍需**单独准备 `runner/` 引擎目录，社区版默认没有）：

```powershell
cd runner_client
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..
python -m runner_client.main
```

一般用户请从 **网盘** 下载 `BrickCoreRunner.zip`，无需编译本目录。

## 探活说明

- 仅 **上线后** 每 10 秒请求 `/runner/health` 刷新状态灯
- 下线后停止轮询

## 平台 API（摘要）

- `POST /sys/users/login`
- `POST /runner/connect`（需 `device:edit`）
- `GET /runner/version`、`GET /runner/client-release`
- `POST /runner/disconnect`、心跳与结果上报

## 相关文档

- [执行器使用说明](../docs-site/guide/runner-client.md)
- [执行器获取与发布](../docs-site/guide/runner-packaging.md)
