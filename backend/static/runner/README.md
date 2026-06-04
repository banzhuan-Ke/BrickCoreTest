# Runner 客户端安装包目录

平台 **平台下载** 读取容器内路径：`/app/static/runner/BrickCoreRunner.zip`。

## 制作 zip

```powershell
cd E:\project2026\fastapi_ui_new
.\scripts\build_runner_client.ps1
# 产出 runner_client\dist\BrickCoreRunner.zip
```

## 上传到服务器

```bat
cd E:\project2026\fastapi_ui_new\runner_client
upload-to-server.bat
```

（scp 到宿主机 + docker cp 进 `fastapi_backend`）

## 推荐：网盘分发

**系统管理 → 执行器发布** 填写网盘/OSS 链接，无需占用本目录磁盘。

## 配置

| 方式 | 说明 |
|------|------|
| 平台页面 | **系统管理 → 执行器发布**（DB，推荐） |
| 本目录文件 | 平台下载（需挂载或 docker cp） |
| `RUNNER_CLIENT_DOWNLOAD_URL` | 环境变量外链兜底 |
| `RUNNER_CLIENT_VERSION_LATEST` | 与 zip 内 VERSION.txt 一致（当前推荐 **1.1.1**，含 UI 执行中断加固；**1.1.0** 含数据工厂回调） |

## API

- `GET /runner/client-release` — 版本与安装包是否可用
- `GET /runner/client-download` — 下载 zip（需登录）

## Docker 挂载（建议）

```yaml
volumes:
  - ./backend/static/runner:/app/static/runner
```

详见 [Runner客户端与执行器后续计划.md](../../docs/Runner客户端与执行器后续计划.md) 中 R-1。
