# BrickCore 执行器（桌面客户端）

## 适用场景

在 **Windows 测试机** 上安装 BrickCore 执行器，用于：

- Web UI 用例执行、AI 录制、实时画面
- 与平台 MQ/Redis 通信，接收任务并回传结果

安装包内已包含：**桌面 GUI**（`BrickCoreRunner.exe` + `_internal`）、**Runner 引擎**（`runner\` 子目录，含嵌入式 Python 与 Playwright Chromium）。**无需在本机单独安装 Python**。

## 网盘获取

| 方式 | 说明 |
|------|------|
| **网盘下载（推荐）** | [百度网盘](https://pan.baidu.com/s/1Nx2fkPAUi7htJKZAxp1paw?pwd=ye6b)（提取码 `ye6b`）；或见 [README 执行器章节](https://gitee.com/BanZhuanKeOrz/BrickCore#执行器下载windows--约-800mb)；登录 [演示平台](http://43.142.83.156/) → **设备管理** → **网盘下载** |
| **平台下载** | 管理员将 zip 上传到服务器后，设备管理页「平台下载 zip」（需登录，占服务器带宽） |
| **客户端检查更新** | 已登录客户端可对比版本；优先使用网盘/外链，支持下载 zip 到「下载」文件夹 |

> 安装包约 **800MB**（含 Chromium），网盘分发可减轻服务器压力。

## 安装步骤（Windows）

1. 下载 `BrickCoreRunner.zip` 并解压到任意目录（路径尽量不含中文与空格）
2. 确认目录结构完整（**不可只复制 exe**）：
   ```
   BrickCoreRunner/
   ├── BrickCoreRunner.exe    # 启动入口
   ├── _internal/             # PyInstaller 依赖（Qt、Python 等），必须与 exe 同目录
   ├── runner/                # 执行引擎
   └── VERSION.txt
   ```
3. 双击 **`BrickCoreRunner.exe`**
4. 服务器地址默认选中线上环境；可在「管理…」维护多套地址
5. 使用 **平台账号** 登录 → 填写 **设备名称** → 点击 **上线**
6. 在 **UI 自动化 → 设备管理** 确认状态为 **在线**

## 界面说明

| 区域 | 说明 |
|------|------|
| 连接状态 | 平台 API / 消息队列 / Redis / Runner 引擎 四色指示灯 |
| 登录 / 上线 / 下线 | 登录平台账号；上线启动 `runner\main.py` 子进程并注册设备 |
| 检查更新 | 对比 `/runner/version`；可下载安装包（需已登录） |
| 管理… | 增删改服务器环境列表 |
| 设置 | 记住密码、开机自启（仅打包 exe 有效） |
| 系统托盘 | 关闭窗口最小化到托盘；托盘可上线/下线 |

## 与平台配合使用

1. **执行用例**：用例列表 → 运行 → 选择 **在线设备**
2. **AI 录制**：用例编辑 → AI 录制 → 选择本机设备
3. **实时画面**：设备管理 → 实时画面（设备须在线）
4. **定时任务**：计划触发时 MQ 下发到已上线设备

## 设备管理（平台侧）

**路径**：**UI 自动化 → 设备管理**

| 能力 | 说明 |
|------|------|
| 下载区 | 网盘下载 / 平台下载 / 跳转使用说明 |
| 客户端版本 | 展示各设备 `runner_client_version` |
| 最后心跳 | 展示 `runner_last_heartbeat` |
| 复制设备编号 | 执行计划、小测助手填 `device_id` 时使用 |

## 版本与更新

- 版本号：窗口旁 **vX.Y.Z** 与 `VERSION.txt`
- **GUI / exe 变更**：关闭客户端后，用新 zip **整目录覆盖**（最稳妥）
- **1.1.0+**：支持 UI 套件执行完成后自动触发后置 SQL / 库断言（需 Backend 配置 `INTERNAL_API_KEY`）
- **1.1.1**（当前推荐）：UI 执行中断 MQ 加固（计划/套件/单用例停止、状态「已停止」、精准 device 投递）
- 平台可设 `RUNNER_CLIENT_VERSION_MIN`，过低版本 connect 会拒绝上线

## 探活与日志

- **仅「上线」之后**，客户端每 **10 秒** 请求一次 `GET /runner/health` 刷新「平台 API」状态灯
- 未上线 / 已下线 / 关闭客户端：**不会**持续轮询
- 服务端已对 `/runner/health`、`/runner/heartbeat` **过滤 access 日志**，避免 Docker 日志膨胀

## 常见问题

| 现象 | 处理 |
|------|------|
| 双击 exe 闪退 | 确认 `_internal` 与 `runner` 目录完整；用最新打包脚本重建 |
| 无法连接平台 | 检查服务器地址、防火墙、Backend 是否启动 |
| MQ / Redis 连接失败 | 平台需配置 MQ/Redis **对外地址**（Windows 不能解析 Docker 内网名 `rabbitmq`） |
| 设备一直离线 | 确认已点击「上线」且 Runner 引擎为绿点；查看客户端日志 |
| 平台下载 404 | 未上传 zip 或未 `docker cp` 进 backend 容器；或改用网盘链接 |
| Playwright 浏览器缺失 | 打包版启动时会提示补装；或重新执行完整打包脚本 |
| UI 套件 DB 断言未执行 | 需 Runner **≥1.1.0** 且 Backend/Runner `INTERNAL_API_KEY` 一致；接口自动化不依赖 Runner |
| 点停止后仍在跑 / 单用例停不下来 | 需升级 Runner **1.1.1** 并整包覆盖安装；Backend 也需部署最新停止 API |

## 相关文档

- [执行器打包 / 获取说明](#runner-packaging)
- [Linux 无头 Runner](#runner-linux-server)
- [UI 自动化](#ui-automation)
- [系统管理 - 执行器发布](#system-admin)
