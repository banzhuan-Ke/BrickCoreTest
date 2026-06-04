# BrickCore 文档站（可选）

> **推荐**：文档已集成到主平台 **帮助中心 → 文档中心**（`/docs`），**无需单独启动本项目**。

本目录保留为：

- 内置文档的 Markdown 源文件（主平台后端直接读取）
- 可选：独立 VitePress 静态站（对外部署、SEO 等场景）

## 主平台使用（默认）

1. 启动 `frontend/` + `backend/`  as usual
2. 登录后进入 **帮助中心 → 文档中心**
3. 有 `docs:edit` 权限可上传视频、附件并发布团队文档

## 可选：独立 VitePress 站

```bash
cd docs-site
npm install
npm run docs:dev
```

仅在你需要独立文档域名时使用。
