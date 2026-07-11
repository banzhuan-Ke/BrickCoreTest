# 功能演示静态页

纯 HTML，改完 `showcase/` 后 commit；演示服务器 Nginx 挂载本目录即可访问。

## 在线地址（演示机）

**http://43.142.83.156/showcase/**

**使用说明（无需登录）：** [http://43.142.83.156/showcase/docs/](http://43.142.83.156/showcase/docs/) — 与平台「文档中心」同目录

（Gitee Pages 已下线，改用演示站 Nginx 托管，见根目录 `nginx-docker.conf` 中 `/showcase/`）

## 目录

```text
showcase/
├── index.html
├── demo-ui.html
├── docs/                 # 静态使用说明（见下方「生成文档」）
│   ├── index.html
│   ├── manifest.json
│   └── content/*.md
└── demo/
    ├── ai-functional-cases.mp4          # AI 需求 → 功能用例
    ├── ai-functional-cases.png          # 封面（可选）
    ├── UI录制AI优化加速版.mp4           # UI 录制 + AI 优化
    ├── ui通过mcp生成用例加速版.mp4      # UI Agent（MCP）生成步骤
    ├── ui执行ai治愈加速版.mp4           # UI 定位器自愈
    └── 接口用例ai生成快速版.mp4         # 接口用例 AI 生成
```

## UI 录制演示页

| 项 | 内容 |
|----|------|
| 地址 | http://43.142.83.156/showcase/demo-ui.html |
| 账号 | demo / demo123 |
| 用途 | UI 录制、回放（固定 id，非动态 SPA） |

推荐录制：登录 → 用户管理 → 查询 → 新增用户 → 保存

## 本地预览

浏览器打开 `index.html`（需与 `demo/` 同目录，视频才能播放）。

## 演示服务器更新

```bash
cd /opt/BrickCore
git pull
docker compose up -d nginx
```

## 文档内容

`showcase/docs/content/` 已与 `docs-site/` 内置文档同步打包进仓库，克隆后即可使用，无需额外生成步骤。
