# BrickCore 执行器（桌面客户端）

## 适用场景

在 **Windows 测试机** 上安装 BrickCore 执行器，用于：

- Web UI 用例执行、AI 录制、实时画面
- **分布式压测 Worker**（v1.3.14+，与 UI 共用同一客户端）
- 与平台 MQ/Redis 通信，接收任务并回传结果

安装包内已包含：**桌面 GUI**（`BrickCoreRunner.exe` + `_internal`）、**Runner 引擎**（`runner\` 子目录，含嵌入式 Python 与 Playwright Chromium）。**无需在本机单独安装 Python**。

## 网盘获取

| 方式 | 说明 |
|------|------|
| **网盘下载（推荐）** | [百度网盘](https://pan.baidu.com/s/1pObFpG-Mt7-Pxo58hklOlg?pwd=9gbi)（提取码 `9gbi`）；或见 [README 执行器章节](../../README.md#执行器下载windows--约-800mb) |
| **平台下载** | 登录平台 → **Web 自动化 → 设备管理** → **网盘下载**（需管理员已配置下载源） |
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
4. **管理服务器环境** 添加线上地址：`http://<公网IP>` 或域名（**不要** `:8000`；生产 API 走 Nginx **80**）
5. 使用 **平台账号** 登录 → 填写 **设备名称** → 点击 **上线**
6. 在 **Web 自动化 → 设备管理** 确认状态为 **在线**

## 界面说明

| 区域 | 说明 |
|------|------|
| 连接状态 | 平台 API / 消息队列 / Redis / UI 引擎 / 压测节点 指示灯 |
| 执行角色 | **仅 UI**（默认）/ **仅压测** / **UI+压测双开**（v1.3.14+） |
| 登录 / 上线 / 下线 | 登录平台账号；上线启动对应子进程；下线自动注销设备/压测节点 |
| 检查更新 | 对比 `/runner/version`；可下载安装包（需已登录） |
| 管理… | 增删改服务器环境列表 |
| 设置 | 记住密码、开机自启（仅打包 exe 有效） |
| 系统托盘 | 关闭窗口最小化到托盘；托盘可上线/下线 |

## 与平台配合使用

### Web 自动化

1. **执行用例**：用例列表 → 运行 → 选择 **在线设备**
2. **AI 录制**：用例编辑 → AI 录制 → 选择本机设备
3. **实时画面**：设备管理 → 实时画面（设备须在线）
4. **定时任务**：计划触发时 MQ 下发到已上线设备

### 性能压测（v1.3.14+，推荐）

1. 登录 → 执行角色选 **仅压测执行机**（或 UI+压测）
2. **压测项目** 选择与平台顶部一致的项目 → **上线**
3. 在 **性能测试 → 执行机** 确认节点在线
4. 场景执行时勾选 **使用分布式 Worker 执行**
5. 压测进行中在客户端 **当前会话日志** 查看秒级 QPS/RT；完整日志：`runner\logs\perf_worker.log`

> 客户端启动的压测引擎与命令行 `perf_worker.py` **完全相同**，平台报告指标一致。区别仅在于 GUI 选项目、自动 Token、下线即时注销、日志汇聚到客户端窗口。

仍支持命令行脚本方式，见 [性能测试 · 执行机](./perf-testing.md#执行机worker)。

### App 自动化（Windows，Pro）

1. 上线时勾选 **App 自动化**；本机 `adb devices` 须为 `device`
2. 设备连接三选一：**USB**、**WiFi 无线调试**（`adb pair` / `adb connect`）、**Android 模拟器**（`adb connect 127.0.0.1:端口`）
3. 每台 serial 首次执行 `runner\venv\Scripts\python.exe -m uiautomator2 init`
4. 平台 **设备管理** 查看 `app_udid`（WiFi 为 `IP:端口`，连接方式 **wifi**）
5. **App 自动化** 中用例/计划/元素探查选择在线 App Runner

详细步骤与故障排查：[执行器安装指南 → App 自动化](runner-install-guide.md#二app-自动化仅-windows)、[App 自动化](app-automation.md)。

## 设备管理（平台侧）

**路径**：**Web 自动化 → 设备管理**

| 能力 | 说明 |
|------|------|
| 下载区 | 网盘下载 / 平台下载 / 跳转使用说明 |
| **运行要求与注意事项** | 折叠面板：运行库、开发模式、录制提示、常见问题 FAQ（v1.3.6+） |
| 客户端版本 | 展示各设备 `runner_client_version`；低于推荐版本时标「需升级」 |
| 变量 / 内联工具 | Runner 含 `tools/data_tools`（与 Backend 同步），步骤支持 `${{dt:md5\|text=@a}}` 等 |
| 最后心跳 | 展示 `runner_last_heartbeat` |
| 复制设备编号 | 执行计划、小测助手填 `device_id` 时使用 |

## 版本与更新

- 版本号：窗口旁 **vX.Y.Z** 与 `VERSION.txt`
- **GUI / exe 变更**：关闭客户端后，用新 zip **整目录覆盖**（最稳妥）
- **1.1.0+**：支持 UI 套件执行完成后自动触发后置 SQL / 库断言（需 Backend 配置 `INTERNAL_API_KEY`）
- **当前主线**：另含 UI 用例步骤关键字 **「数据库断言」**（`kw_db_assert`），执行到该步时回调 `/internal/evaluate-assertion`
- **1.1.1**：UI 执行中断 MQ 加固（计划/套件/单用例停止、状态「已停止」、精准 device 投递）
- **1.3.15**（当前推荐）：修复 hover 步骤将 `timeout` 误当作悬停后等待导致每次多 sleep 的问题；`timeout` 仅作 Playwright 定位超时，悬停后停留用 `wait_time`（默认 500ms）
- **1.3.14**：打开客户端默认「仅 UI 执行器」；压测引擎同步流式持续/梯度压测与 CSV 问题参数化；操作日志识别压测 Worker 节点
- **1.3.12**：一体化压测——执行角色可选 UI/压测/双开；压测秒级日志；下线自动注销 Worker；`httpx`/`numpy` 内置
- **1.3.6**：UI 录制四层增强——浮层高亮、多候选/区域链式 `>>`、步骤质量评估、录制后 3 秒撤销
- 平台可设 `RUNNER_CLIENT_VERSION_MIN`，过低版本 connect 会拒绝上线

## 探活与日志

- **仅「上线」之后**，客户端每 **10 秒** 请求一次 `GET /runner/health` 刷新「平台 API」状态灯
- 未上线 / 已下线 / 关闭客户端：**不会**持续轮询
- 服务端已对 `/runner/health`、`/runner/heartbeat` **过滤 access 日志**，避免 Docker 日志膨胀

## 常见问题

| 现象 | 处理 |
|------|------|
| 双击 exe 闪退 | 确认 `_internal` 与 `runner` 目录完整；重新下载最新安装包解压 |
| 无法连接平台 / 登录报「无法访问服务器」 | 地址应为 `http://<IP>` **不带 :8000**；确认安全组 **80** 已开；`curl http://<IP>/runner/health` 应 200 |
| MQ / Redis 连接失败 | 安全组对测试机 IP 放行 **25672**（MQ）、**26379**（Redis）；Backend 需配置 `RUNNER_MQ_PUBLIC_*` / `RUNNER_REDIS_PUBLIC_*` 或 `MINIO_PUBLIC_ENDPOINT` 推导公网 IP |
| 截图/视频上传失败 | 放行 **9200**（MinIO）；确认 `MINIO_PUBLIC_ENDPOINT: <公网IP>:9200` |
| 设备一直离线 | 确认已点击「上线」且对应引擎指示灯为绿；查看客户端日志 |
| 压测无日志 | 确认执行角色含压测且已上线；平台触发压测后看会话日志或 `runner/logs/perf_worker.log` |
| 压测下线后平台仍在线 | 升级客户端 **≥1.3.14** 与 Backend（含 `/perf/workers/unregister`）；旧版需等约 2 分钟心跳超时 |
| 平台下载 404 | 未上传 zip 或未 `docker cp` 进 backend 容器；或改用网盘链接 |
| Playwright 浏览器缺失 | 打包版启动时会提示补装；或重新下载完整安装包 |
| UI 套件 DB 断言未执行 | 需 Runner **≥1.1.0** 且 Backend/Runner `INTERNAL_API_KEY` 一致；接口自动化不依赖 Runner |
| UI 步骤「数据库断言」失败 | 确认 Runner 含 `kw_db_assert`；`INTERNAL_API_KEY` 与 Backend 一致；数据工厂已配置对应环境数据源 |
| 客户端未响应 | Backend 慢或未启动；请用含后台探活的最新客户端；确认 `curl http://<IP>/runner/health` |
| `No module named 'jsonpath_ng'` | `runner/venv` 依赖不全，或 **多个 Runner 进程** 中有一个用了错误 Python；`pip install -r runner/requirements.txt` 后 **下线再上线** |
| 同环境同 Runner，套件一成功一失败 | 几乎总是 **重复 `main.py` 进程** 抢 MQ；PowerShell 自查见 [排查指南](../../docs/其他文档/RUNNER_TROUBLESHOOTING.md) |
| 套件报告里有 `kai-api-key` 等 | 正常：报告展示 **env_payload.variables**（项目/环境共享变量），不是接口套件混用 |
| 计划并行只开 2 个浏览器 | 部分套件可能在打开浏览器前失败（依赖/进程问题）；并发本身可能已生效 |
| 点停止后仍在跑 / 单用例停不下来 | 需升级 Runner **1.1.1** 并整包覆盖安装；Backend 也需部署最新停止 API |

完整排查：[Runner 排查指南](runner-troubleshooting.md)（平台文档站）或 [仓库详细版](../../docs/其他文档/RUNNER_TROUBLESHOOTING.md)

## UI 录制（v1.3.6+）

1. 用例编辑 → **AI 录制** → 选择已上线本机设备
2. 浏览器中移动鼠标：**蓝框**标出即将录制的元素；点击后顶部 toast 显示「已录制」，**3 秒内可撤销**
3. 导入平台后：步骤列表有**截图缩略图**与**质量**列（正常/注意/风险）；可下拉切换备选定位
4. **AI 优化**会精简步骤并优化描述；**可从候选列表智能重选默认定位**（如顶栏「设置」优先区域链式），不会自造不在列表里的表达式

## 相关文档

- [执行器安装指南](runner-install-guide.md)（App：USB / WiFi / 模拟器）
- [App 自动化](app-automation.md)
- [执行器获取与发布](runner-packaging.md)
- [排查指南](runner-troubleshooting.md)
- [Web 自动化](ui-automation.md)
- [系统管理 - 执行器发布](system-admin.md#执行器发布)
