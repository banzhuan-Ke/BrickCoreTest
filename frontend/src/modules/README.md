# 前端业务模块目录

与后端 `backend/app/modules/` 对应，按产品线收纳页面与 API。

## 当前已迁移

| 模块 | 路径 | 说明 |
|------|------|------|
| qa-eval | `modules/qa-eval/views/` | 问答准确性评测页；API 仍在 `api/modules/ai.js` 的 `qaEvalApi` |

## 规划映射（逐步迁移，不拆单文件内容）

| 模块 | 现有位置 | 目标 |
|------|----------|------|
| ai | `views/AI/` | `modules/ai/views/` |
| http | `views/ApiModule/` | `modules/http/views/` |
| app | `views/App/` | `modules/app/views/` |
| ui | `views/Case/`、`Suite/`、`Task/` | `modules/ui/views/` |
| perf | `views/Perf/` | `modules/perf/views/` |
| sys | `views/System/` | `modules/sys/views/` |

迁移时仅调整目录与 `router/index.js` 中的 import 路径，**不拆分 Vue 单文件内部**。
