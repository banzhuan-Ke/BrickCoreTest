# 执行器说明

本仓库为**平台源码**。在 Windows 上跑 **Web UI 自动化**、**录制回放**，或使用**分布式性能 Worker** 时，请安装执行器。

## 获取与使用

1. **网盘下载（推荐）**：见根目录 [README.md](../README.md#执行器下载windows--约-800mb) 中的百度网盘链接；或登录 [在线演示](http://43.142.83.156/) → **UI 自动化 → 设备管理 → 网盘下载**
2. 解压后运行 `BrickCoreRunner.exe`，**管理服务器环境** 填 **`http://43.142.83.156`** 或自建平台 `http://<公网IP>`（**不要** `:8000`），登录并 **上线** 设备；自建机还需对测试机 IP 放行 **80、25672、26379、9200**
3. 详见 [docs-site 执行器说明](../docs-site/guide/runner-client.md)

## 说明

请从网盘下载 **BrickCoreRunner** 安装包获取 Playwright 执行与 Worker 运行时。如有问题可通过 Gitee Issues 反馈。
