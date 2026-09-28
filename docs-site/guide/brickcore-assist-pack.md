# 小测扩展包（brickcore_assist）

平台内 AI 助手「小测」的 **standard 多轮、Skill、任务进度桥** 等增强能力，由扩展包 **brickcore_assist** 提供。

未安装时仍可使用助手的 **基础模式**（查询与确认执行等）；安装扩展包并开启开关后，可使用完整小测能力。

| 部署方式 | 是否需要单独安装 |
|----------|------------------|
| **已内置扩展包的官方镜像** | 一般**不需要** |
| **从源码自建 · Docker / Linux 服务器** | 需要：下载 **linux** 版 `.bcpack` → 安装 → 重启 backend |
| **Windows 本机跑 backend** | 需要：下载 **win** 版 `.bcpack`（与本机 Python 主次版本一致，当前多为 **3.11**） |
| **macOS 本机跑 backend** | 如有对应 macos 包再安装；**Mac 上 Docker 跑 backend** 请装 **linux** 包 |

扩展包与平台版本、**Python 主次版本**均需对齐；安装步骤见下文。

## 版本对齐

| 平台版本 | 扩展包说明 |
|----------|------------|
| 1.9.x | 使用声明兼容 **1.8 / 1.9** 的 brickcore_assist 包（文件名中的版本号以 Release 为准） |
| 1.8.x | 同上（兼容前缀含 1.8） |

安装并重启后，可在 backend 中确认：

```bash
docker compose exec -T backend python -c "import brickcore_assist; print(brickcore_assist.package_info())"
```

期望能打印包名与版本；再确认环境变量 **`ASSIST_STANDARD_ENABLED=1`**（改完须重启 backend）。

> **Python 版本**：Nuitka 加固包与 CPython **主次版本绑定**。官方镜像为 **3.11** → 请选文件名含 **`cp311`** 的包。`cp311` 包无法在 3.10 / 3.12 上加载。

## 获取安装包

1. Gitee Release 附件，或官方网盘（与执行器 / 测试管理扩展包同渠道维护）
2. 正式包文件名示例：
   - `brickcore_assist-*-linux-amd64-cp311.bcpack`（Docker / Linux）
   - `brickcore_assist-*-win-amd64-cp311.bcpack`（Windows 本机）
3. 请选择与 backend **Python 主次版本**及操作系统一致的包

## Docker 安装（源码自建）

```bash
# 推荐装到持久目录（compose 已挂载 ./backend/ext_packages → /app/ext_packages）
docker cp brickcore_assist-*-linux-amd64-cp311.bcpack <backend容器名>:/tmp/
docker exec <backend容器名> python tools/install_brickcore_assist.py /tmp/brickcore_assist-....bcpack
# 确认 ASSIST_STANDARD_ENABLED=1 后：
docker compose restart backend
```

## Windows / 本机中间件

在 **backend 使用的同一个 Python 环境**（建议 3.11）中执行：

```powershell
cd backend
python tools/install_brickcore_assist.py D:\downloads\brickcore_assist-*-win-amd64-cp311.bcpack
# 设置 ASSIST_STANDARD_ENABLED=1 后重启 uvicorn / 服务
```

若需指定目录：

```powershell
python tools/install_brickcore_assist.py D:\path\xxx.bcpack --target D:\path\to\ext_packages
```

并保证该目录在进程的 `PYTHONPATH` 中（Docker compose 已挂载时一般不必改）。

## 未安装时的行为

- 小测 **基础模式**仍可用（查询、确认后触发执行等）
- standard 多轮 / Skill 清单增强 / 部分任务桥能力不可用或降级提示
- 前端与网关会提示未检测到小测扩展包（中性文案，不阻断登录与主流程）

## 开关说明

| 变量 | 含义 |
|------|------|
| `ASSIST_STANDARD_ENABLED=1` | 有包时走完整小测（standard） |
| `ASSIST_STANDARD_ENABLED=0` | 强制基础模式（即使已装包） |
| `BRICKCORE_ASSIST_DISABLED=1` | 模拟未安装扩展包 |

改环境变量后须 **重启 backend** 生效。

## 相关文档

- [平台内 AI 助手](./platform-assistant.md)
- [测试管理扩展包](./brickcore-tm-pack.md)（另一类可选扩展包，安装方式类似）
