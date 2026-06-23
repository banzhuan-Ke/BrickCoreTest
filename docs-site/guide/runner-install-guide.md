# 执行器安装指南（Windows / macOS）

本文说明如何在 **Windows** 或 **Mac** 上安装 BrickCore 执行器，并连接测试平台。

| 系统 | 安装包 | 适用场景 |
|------|--------|----------|
| **Windows** | `BrickCoreRunner.zip`（约 800MB） | 桌面客户端：登录、上线、UI 自动化、录制、实时画面 |
| **macOS（Apple 芯片）** | `BrickCoreRunner-mac-arm64.zip` |
| **macOS（Intel）** | `BrickCoreRunner-mac-intel.zip`（向管理员索取） |

---

## 获取安装包

| 方式 | 说明 |
|------|------|
| **网盘下载（推荐）** | [百度网盘 BrickCoreRunner.zip](https://pan.baidu.com/s/1Nx2fkPAUi7htJKZAxp1paw?pwd=ye6b)（提取码 `ye6b`）；Mac 包由管理员另行提供 |
| **平台下载** | 登录平台 → **UI 自动化 → 设备管理** → **网盘下载** |
| **自建平台** | 管理员在 **系统管理 → 执行器发布** 配置下载链接 |

> Windows 与 Mac 安装包**不能混用**。

---

## 一、Windows 安装

### 1. 解压

1. 下载 `BrickCoreRunner.zip` 并解压（路径尽量不含中文与空格）
2. 确认目录包含 `BrickCoreRunner.exe`、`_internal/`、`runner/`、`VERSION.txt`

### 2. 连接平台

1. 双击 **`BrickCoreRunner.exe`**
2. **管理服务器环境** 添加平台地址：`http://<公网IP>` 或域名（**勿写 `:8000`**）
3. **登录** → 填写设备名称 → **上线**
4. 在 **设备管理** 确认 **在线**

### 3. 修改平台地址

在客户端切换服务器环境 → **下线** → 重新 **登录 / 上线**。

---

## 二、macOS 安装

### 1. 解压（须在 Mac 上操作）

```bash
# Apple 芯片 (uname -m 为 arm64)
unzip BrickCoreRunner-mac-arm64.zip
cd BrickCoreRunner-mac

# Intel Mac (uname -m 为 x86_64)
# unzip BrickCoreRunner-mac-intel.zip
# cd BrickCoreRunner-mac
```

### 2. 连接平台

```bash
chmod +x connect-mac.sh start-mac.sh
./connect-mac.sh
```

按提示输入平台地址、账号、设备名称。成功后生成 `runner/.env`（包内原本没有，属正常）。

### 3. 启动

```bash
./start-mac.sh
```

在 **设备管理** 确认 **在线**。

### 4. 修改平台地址

删除 `runner/.env` 后重新 `./connect-mac.sh`，或手动编辑 `.env` 中的 `BASE_URL` 等项。

---

## 三、网络要求

| 端口 | 用途 |
|------|------|
| 80 | 平台 API |
| 25672 | RabbitMQ |
| 26379 | Redis |

无法上线请联系平台管理员放行上述端口。

---

## 四、常见问题

- **Windows 闪退**：确认 `_internal/`、`runner/` 完整，重新解压
- **Mac 无 `.env`**：先执行 `./connect-mac.sh`
- **登录失败**：平台地址不要加 `:8000`；检查 `http://<IP>/runner/health`
- **浏览器**：使用包内 Chromium，无需单独安装 Chrome

---

## 相关文档

- [执行器使用说明](runner-client.md)
- [执行器获取与发布](runner-packaging.md)
