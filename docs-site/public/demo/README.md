# 功能演示截图目录

本目录文件在 VitePress 构建后可通过 **`/demo/文件名`** 访问。

## 文件清单

| 文件 | 说明 |
|------|------|
| `ai-functional-cases.png` | AI 需求生成功能用例 |
| `ui-mcp-record.png` | UI MCP 录制（或 `.gif`） |
| `ui-locator-heal.png` | UI 定位器自愈 |
| `api-ai-generate.png` | 接口用例 AI 生成 |

页面：`docs-site/guide/product-demo.md`

## Gitee Pages 发布（CE 仓库）

```bash
cd docs-site
npm install
npm run docs:build
# 将 .vitepress/dist 内容推送到 Gitee Pages 分支，或在 Gitee 仓库设置 → Pages 选择该目录
```

CE 仓库若启用 Pages，README 可链接：

`https://banzhuankeorz.gitee.io/brickcore/guide/product-demo.html`

（仓库名大小写以 Gitee 实际为准；若 404 需在 `.vitepress/config.mts` 设置 `base: '/brickcore/'`）
