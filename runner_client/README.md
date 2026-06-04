# BrickCore Runner 客户端

登录 BrickCore 平台后，可视化选择环境并 **上线 Runner**，无需手工维护 `runner/.env` 中的 MQ/Redis 密码。

## 安装包模式（推荐，测试人员）

```powershell
# 开发机打包（仓库根目录）
cd E:\project2026\fastapi_ui_new
.\scripts\build_runner_client.ps1
```

产出：

- `runner_client\dist\BrickCoreRunner\` — 解压即用目录（含 exe、`_internal`、`runner`）
- `runner_client\dist\BrickCoreRunner.zip` — 分发/上传用

**上传服务器**（输入 SSH 密码，与 deploy-frontend.bat 相同）：

```bat
cd runner_client
upload-to-server.bat
```

**网盘分发（推荐，约 800MB）**：平台 **系统管理 → 执行器发布** 配置链接。

用户文档：[docs-site/guide/runner-client.md](../docs-site/guide/runner-client.md)

## 开发模式

```powershell
cd runner_client
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
cd ..
python -m runner_client.main
```

或双击 `start-client.bat`。Runner 引擎需单独在 `runner/` 配置（`RUNNER_LEGACY=1`）。

## 使用流程

1. 选择环境（默认线上）→ **登录** 平台账号  
2. 填写设备名称 → **上线**  
3. 平台 **设备管理** 确认 **在线**  
4. 切换环境：先 **下线**，再换地址重新登录/上线  

## 打包参数

| 参数 | 说明 |
|------|------|
| `-SkipPyInstaller` | 只更新 `runner\` 子目录 |
| `-SkipRunnerCopy` | 只重建 exe |
| `-SkipRuntimeSetup` | 跳过 venv/浏览器 |
| `-SkipSourceStrip` | 保留 runner 明文 .py（**仅开发**；网盘发布勿用） |
| `-UseBytecodeStrip` | 跳过 Nuitka，改用 `.pyc` 加固（无 C 编译器时的备选） |

**发布包默认 Nuitka 三级加固**：`WebEngine/`、`tools/` 等编译为 `.pyd`，删除源码。首次编译需 **VS 2022 Build Tools（C++）** 或 Nuitka 自动下载 MinGW（约 10～30 分钟）。

## 探活说明

- 仅 **上线后** 每 10 秒请求 `/runner/health` 刷新状态灯  
- 下线后停止轮询；服务端已过滤 health/heartbeat access 日志  

## API 依赖

- `POST /sys/users/login`
- `POST /runner/connect`（`device:edit`）
- `GET /runner/version`、`GET /runner/client-release`
- `POST /runner/disconnect`、`heartbeat`、`results`、`upload/presign`

## 相关文档

- [打包说明](../docs-site/guide/runner-packaging.md)
- [设计文档](../docs/设计文档/runner-client.md)
- [后续计划](../docs/Runner客户端与执行器后续计划.md)
