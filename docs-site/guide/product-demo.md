# 产品功能演示

本页用于展示 BrickCore 核心能力的高清截图与说明，避免 Gitee 首页 README 压缩图片导致模糊。

> **维护**：截图放入 `docs-site/public/demo/`，本页引用 `/demo/文件名`；Pro 改完后 sync 到 CE，并重新构建文档站（或 Gitee Pages）。

<style>
.demo-shot {
  max-width: 100%;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  margin: 12px 0 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.demo-caption {
  color: var(--vp-c-text-2);
  font-size: 14px;
  margin-top: -12px;
  margin-bottom: 32px;
}
</style>

## AI 需求 → 功能用例

上传 Word / PDF 需求文档，AI 按批次生成功能测试用例，支持禅道配置、批量生成与导出 XLSX。

<img class="demo-shot" src="/demo/ai-functional-cases.png" alt="AI 需求生成功能用例" />

<p class="demo-caption">路径：<code>docs-site/public/demo/ai-functional-cases.png</code> · 建议宽度 1920px，PNG 原图</p>

## UI MCP 录制

通过 MCP 或平台助手驱动浏览器录制，操作即自动化步骤。

<img class="demo-shot" src="/demo/ui-mcp-record.png" alt="UI MCP 录制" />

<p class="demo-caption">路径：<code>docs-site/public/demo/ui-mcp-record.png</code> · 动图可用 GIF，或放 B 站链接见下文</p>

## UI 定位器自愈

页面元素变更后，执行时自动尝试修复定位器，降低维护成本。

<img class="demo-shot" src="/demo/ui-locator-heal.png" alt="UI 定位器自愈" />

<p class="demo-caption">路径：<code>docs-site/public/demo/ui-locator-heal.png</code></p>

## 接口用例 AI 生成

基于 Swagger / 接口定义，AI 生成接口自动化用例。

<img class="demo-shot" src="/demo/api-ai-generate.png" alt="接口用例 AI 生成" />

<p class="demo-caption">路径：<code>docs-site/public/demo/api-ai-generate.png</code></p>

---

## 在线体验

| 项 | 内容 |
|----|------|
| 演示环境 | http://43.142.83.156/ |
| 账号 | admin / BrickCore123456 |

## 视频演示（可选）

README 与文档站不适合内嵌大体积 mp4。若有完整录屏，可上传 B 站后在下方补充链接：

- （待补充）UI MCP 录制完整演示

---

## 素材规范

| 项 | 建议 |
|----|------|
| 格式 | PNG 截图优先；短动作用 GIF |
| 宽度 | **1920** 或 Retina 2x，文档站会按屏宽缩放，不压糊 |
| 体积 | 单张 PNG &lt; 2MB；GIF &lt; 5MB |
| 命名 | 与上表文件名一致，替换即可 |
