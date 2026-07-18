# Runner 客户端安装包目录

平台 **平台下载** 读取容器内路径：

| 文件 | 用途 |
|------|------|
| `/app/static/runner/BrickCoreRunner.zip` | 完整执行器（UI + 可选压测） |
| `/app/static/runner/BrickCorePerf.zip` | 精简压测包 Windows |
| `/app/static/runner/BrickCorePerf-mac.zip` | 精简压测包 macOS |

## 推荐：网盘分发

本公开仓**不含**执行器引擎源码与打包脚本。请使用百度网盘 / 平台 **执行器发布** 外链分发安装包，无需占用本目录磁盘。

1. 管理员在 **系统管理 → 执行器发布** 填写网盘/OSS 链接与按钮文案
2. 用户在 **Web 自动化 → 设备管理** 点击 **网盘下载**

也可将已下载的 zip 放到本目录，供「平台下载」读取（需挂载进 backend 容器）。

## 配置

| 方式 | 说明 |
|------|------|
| 平台页面 | **系统管理 → 执行器发布**（DB，推荐） |
| 本目录文件 | 平台下载（需挂载或 docker cp） |
| `RUNNER_CLIENT_DOWNLOAD_URL` | 环境变量外链兜底 |
