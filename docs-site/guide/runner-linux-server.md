# Linux 服务器无头 Runner

## 适用场景

在 **Linux 服务器**（无图形界面）上长期运行 Runner 引擎，用于：

- CI / 定时任务无人值守执行
- 多台服务器横向扩展执行能力

此方式运行的是 **`runner/main.py` 引擎**，不是 Windows 桌面 `BrickCoreRunner.exe`。设备仍须在平台 **设备管理** 中显示为在线。

## 环境要求

| 项 | 说明 |
|----|------|
| 系统 | Ubuntu 20.04+ / CentOS 7+ 等 |
| Python | 3.10+（建议 3.12） |
| 依赖 | `runner/requirements.txt`、Playwright Chromium |
| 网络 | 可访问平台 API、MQ、Redis（使用平台下发的对外地址） |

## 快速启动

```bash
cd <部署目录>/runner   # 含 main.py 的引擎目录（商业版源码部署）
cp env.example .env       # 若有示例
# 编辑 .env：PLATFORM_URL、用户名密码或 RUNNER_TOKEN 等

chmod +x start-headless-linux.sh
./start-headless-linux.sh
```

脚本会：创建/激活 venv → 安装依赖 → `playwright install chromium` → 后台启动 `python main.py`。

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| `PLATFORM_URL` / `BASE_URL` | 平台 Backend 根地址，如 `https://your-platform.example.com:8000` |
| `RUNNER_TOKEN` | 若已通过桌面客户端 connect 获取，可直填（可选） |
| `DEVICE_NAME` | 设备显示名称 |
| `HEADLESS` | 建议 `true` |

具体键名以 `runner/settings.py` 为准；首次部署可用桌面客户端上线一次，从日志或平台查看 device_id 与 token 配置方式。

## 使用 systemd（推荐生产）

```ini
# /etc/systemd/system/brickcore-runner.service
[Unit]
Description=BrickCore Runner Engine
After=network.target

[Service]
Type=simple
User=autotest
WorkingDirectory=<部署目录>/runner
EnvironmentFile=<部署目录>/runner/.env
ExecStart=<部署目录>/runner/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable brickcore-runner
sudo systemctl start brickcore-runner
sudo systemctl status brickcore-runner
```

## 与 Windows 客户端的区别

| 对比 | Windows 桌面客户端 | Linux 无头 |
|------|-------------------|------------|
| 程序 | BrickCoreRunner.exe | python main.py |
| 登录界面 | 有 | 无（配置/env） |
| 实时画面 | 支持 | 一般不用 |
| 适用 | 测试人员本机 | 服务器 CI |

## 平台侧检查

1. **设备管理** 中应出现对应设备，状态 **在线**
2. 执行 UI 用例时选择该 **device_id**
3. 定时任务 / 计划执行前确认设备未被占用

## 常见问题

| 现象 | 处理 |
|------|------|
| 注册失败 | 检查 `PLATFORM_URL`、账号权限 `device:edit` |
| Chromium 启动失败 | `playwright install-deps chromium`（Linux 系统库） |
| MQ 连不上 | 与 Windows 相同，需平台配置 MQ 公网/宿主机地址 |

## 相关文档

- [执行器使用说明](runner-client.md)
- [执行器打包说明](runner-packaging.md)
- [UI 自动化](ui-automation.md)
