# Runner 执行器排查指南

> 适用：Windows 桌面客户端 `BrickCoreRunner.exe` / 开发模式 `start-client.bat`  
> 当前推荐客户端版本：**1.3.6**

## 一、运行环境与运行库

| 场景 | 要求 |
|------|------|
| **安装包（测试机）** | Windows 10/11 x64；完整解压 zip（exe + `_internal` + `runner`）；**无需本机 Python** |
| **开发模式（研发）** | Python 3.11；执行 `runner_client\start-client.bat` 自动创建双 venv |
| **运行库** | 打包版已内置 MSVCP140 / VCRUNTIME140；`greenlet` DLL 报错请重下最新 zip |
| **Playwright** | 打包版内置 Chromium；开发模式在 `runner\venv` 内执行 `playwright install chromium` |
| **网络** | 平台 80；MQ 25672；Redis 26379；MinIO 9200（按环境放行） |

## 二、同一 Runner 套件一成功一失败

几乎总是 **多个 `runner/main.py` 进程** 同时连同一 `device_id`，MQ 轮流投递到不同 Python 环境。

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*runner*main.py*' } |
  Select-Object ProcessId, CommandLine
```

**处理**：客户端下线 → 结束多余进程 → 仅用 `start-client.bat` 或 `BrickCoreRunner.exe` 上线。

## 三、`No module named 'jsonpath_ng'`

引擎必须使用 **`runner\venv`**，不是系统 Python 或 `runner_client\venv`。

```powershell
cd E:\project2026\fastapi_ui_new\runner
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

或重跑 `runner_client\start-client.bat`，然后 **下线 → 再上线**。

## 四、开发模式 `pyvenv.cfg` / venv 损坏

现象：`No Python at ...\runner\venv\python.exe`，或依赖明明装了仍报错。

**处理**：删除 `runner\venv` 目录，重新运行 `start-client.bat`（勿混用旧打包版解压的 `runner\venv`）。

## 五、UI 录制定位不准

**v1.3.6+** 已增强：

- 录制时蓝框高亮 + 顶部「撤销」
- 多候选定位、`header >> get_by_text=设置` 区域链式
- 步骤质量评估（风险/注意）
- AI 优化 **不会修改 locator**

仍不准时：录前看蓝框文案；导入前改「质量」为风险的步骤；关键按钮加 `data-testid`。

## 六、客户端版本过低

平台 `.env` 可设 `RUNNER_CLIENT_VERSION_MIN`。设备管理列表会标「需升级」。请下载与 `RUNNER_CLIENT_VERSION_LATEST` 一致的 zip（当前 **1.3.15**）。

## 六、App adb（WiFi / 模拟器）

| 现象 | 处理 |
|------|------|
| `adb pair` → `protocol fault` | PC 与手机不通（常见 **AP 隔离**）；改 **手机热点** 或 USB；`ping` 手机 IP |
| WiFi 已 connect 但 Runner 无 App 能力 | `adb devices` 须为 `device` → 客户端 **下线再上线** |
| 模拟器连不上 | MuMu 等：**设置 → ADB** 查端口 → `adb connect 127.0.0.1:端口` → `uiautomator2 init` |
| 多台设备跑错机 | 只保留一台 `device`，或定时/执行时 **指定 Runner** |

完整步骤见 [执行器安装指南 → App 自动化](runner-install-guide.md#二app-自动化仅-windows)。

## 七、相关文档

- [执行器使用说明](runner-client.md)
- [打包与版本](runner-packaging.md)
- 仓库内 `docs/其他文档/RUNNER_TROUBLESHOOTING.md`（详细版）
