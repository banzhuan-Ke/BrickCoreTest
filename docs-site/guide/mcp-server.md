# MCP 外部接入（AI 助手操控平台）

## 适用场景

团队使用 **Kimi Code、Cursor** 等支持 MCP 的 AI 客户端时，可通过本功能让 AI **直接查询项目、需求、用例，触发测试执行与失败分析**，无需反复切换浏览器手工点选。

这与平台内部的「UI Agent（MCP 思路）」不同：后者用于**平台内**生成 UI 步骤；本文说的是 **BrickCore MCP Server**，供**外部 AI 客户端**远程调用。

## 在平台哪里配置、哪里查看接入信息？

### 管理员：设置 API Key 与对外地址

1. 登录 BrickCore  
2. 左侧菜单 **系统管理** → **MCP配置**  
3. 开启 **启用 MCP Server**，填写 **平台对外地址**（如 `http://localhost:8000`）和 **MCP API Key**  
4. 点击 **保存 MCP 配置**

### 所有人：查看接入地址、复制客户端 JSON

1. 左侧菜单 **数据看板** → **首页看板**  
2. 页面向下滚动，找到 **BrickCore MCP Server** 卡片（标题旁有「已启用 / 未启用」状态）  
3. 可复制 **接入地址**，或点击 **一键复制 JSON**，粘贴到 AI 客户端配置中  

> 接入路径默认 `/brickcore/agent-hub`，由部署环境变量控制；修改需同步 Nginx，一般使用者无需改动。

## Kimi Code 配置（国内常用）

### 步骤 1：确认平台已保存 API Key

在 **系统管理 → MCP配置** 中保存密钥（请使用足够长的随机字符串，勿用弱口令）。

### 步骤 2：配置客户端

**重要**：HTTP 模式必须用 **`headers` 传认证**，不能写在 **Environment Variables（环境变量）** 里——`env` 仅用于 `stdio` 子进程。

**方式 A：命令行**

```bash
kimi mcp add --transport http brickcore http://localhost:8000/brickcore/agent-hub/ \
  --header "Authorization: Bearer 你的MCP_API_KEY"
```

**方式 B：编辑配置文件** `~/.kimi/mcp.json`（Windows：`C:\Users\你的用户名\.kimi\mcp.json`）

```json
{
  "mcpServers": {
    "brickcore": {
      "url": "http://localhost:8000/brickcore/agent-hub/",
      "headers": {
        "Authorization": "Bearer 你的MCP_API_KEY"
      }
    }
  }
}
```

### 步骤 3：检查项

| 项 | 正确示例 |
|----|----------|
| Transport | `http` |
| URL | `http://localhost:8000/brickcore/agent-hub/`（建议末尾带 `/`） |
| Requires OAuth | **不要勾选**（使用 Bearer API Key） |
| Authorization | `Bearer` 与平台 **MCP API Key 完全一致** |

保存后重启 Kimi Code，在对话中用自然语言验证，例如：

> 用 BrickCore 查看 MCP 是否已连接成功  

或：

> 用 BrickCore 列出所有项目  

若返回项目列表或连接状态为已认证，即配置成功。

## 其他客户端（Cursor / Claude Desktop）

1. 打开 **数据看板 → 首页看板**，在 **BrickCore MCP Server** 卡片点击 **一键复制 JSON**  
2. 粘贴到客户端 MCP 配置（`mcpServers` 下的 `url` 与 `headers`）  
3. 重启客户端  

Claude Desktop 配置文件（Windows）：`%APPDATA%\Claude\claude_desktop_config.json`

## 能做什么？

连上后，在 AI 对话里用**自然语言**描述即可，**不必记忆英文工具名**。例如：

| 你想做的事 | 可以这样说 |
|------------|------------|
| **项目全貌总结（推荐）** | 「用 BrickCore 总结项目 3 的完整情况」或「调用 get_project_overview 查项目 3」 |
| 查项目 | 「BrickCore 有哪些项目？」 |
| 查环境 | 「项目 3 有哪些测试环境？」 |
| 查需求 | 「项目 1 有哪些需求文档？」 |
| **查已生成用例** | 「项目 3 需求 9 生成了哪些用例？按优先级统计一下」 |
| 查失败 | 「列出项目 1 最近失败的用例」 |
| **检索迭代资料** | 「检索资料库里支付模块相关的 Bug」 |
| 分析失败 | 「对最近一条失败做 AI 分析」 |
| 查接口计划/记录 | 「项目 3 有哪些接口测试计划？最近执行结果如何？」 |
| 查 UI/压测 | 「列出 UI 套件和定时任务」「压测 Worker 在线情况」 |
| 执行测试 | 「先预览执行接口套件 3，确认后再真正执行」 |
| 执行接口计划 | 「先 preview 接口测试计划 5，确认后执行」 |

危险操作（跑测试、批量生成用例）会自动走 **先预览、再确认** 两步，避免误触发。

## 平台内助手（无需 MCP 配置）

登录平台后，右下角 **小测 · 平台助手** 可直接问答（**Phase 3**）：项目概览、需求/用例、接口/UI/压测全域查询、最近失败等；执行/生成/分析类操作会弹出 **确认卡片**；支持 **多会话**、**消息全文搜索**、回答内 **可点击跳转**（suite_id / plan_id 等）；**可拖动放大浮窗**，表格 Markdown 正常渲染。
<!-- mcp-tools:auto:assistant-stats:start -->
与对外 MCP 共用同一套后端工具（MCP 共 **58** 个，助手只读白名单 **38** 个 + **10** 个 preview）；外部 Kimi/Cursor 仍走 MCP 接入。
<!-- mcp-tools:auto:assistant-stats:end -->

**AI 模型配置 → 场景绑定**：为各 AI 场景指定默认模型，支持推荐配置与「一键套用」。

设计说明见文档中心 **设计文档 → platform-assistant**。

部署使用 Docker 时，助手走 `POST /ai/assistant/chat` 与 `POST /ai/assistant/confirm`（一次性 JSON，非 SSE）；历史存 `assistant_session` 表。

## 常见问题

**Q：Kimi Code 显示 Connection failed，但后端日志是 200？**  
Windows 上可能是客户端显示编码问题；若对话里能正常返回项目或连接信息，可忽略红字。

**Q：`authenticated: false` 或未提供认证？**  
检查是否把 `Authorization` 误填在 **环境变量** 里；HTTP 模式应写在 `headers` 或 `--header`。

**Q：问「环境变量」查不到？**  
当前 MCP 首版主要覆盖项目、需求、用例、执行与失败分析；环境的**全局变量**等细节能力将按实际使用逐步补充，届时可直接用自然语言查询。

**Q：生产环境要注意什么？**  
API Key 设长随机串；尽量内网或 VPN；公网暴露时可在 Nginx 对 MCP 路径做 IP 白名单。

**Q：确认执行 UI 用例时报 `'Depends' object has no attribute 'get'`？**  
旧版确认阶段直调路由未注入身份，预览成功但任务未入队。请升级至 **v1.5.0+** backend 并重启；修复后应正常入队，或返回可读业务错误（如设备正忙）。
