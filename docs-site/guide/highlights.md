# 亮点功能

BrickCore 将 **Web 自动化、App 自动化、接口自动化、性能测试、AI 测试** 整合在同一套平台中，覆盖从需求理解、用例设计、自动执行到 **可读报告与对比闭环** 的完整流程。

> **首次进入文档中心时建议先阅读本章**；登录、项目切换等基础操作见 [使用说明](#home)。

## 快速跳转

| 分类 | 文档 |
|------|------|
| **快速开始** | [使用说明](#home) · [平台概览](#quick-start) · [亮点功能](#highlights) · [版本更新记录](#release-notes) · [项目与环境](#project-setup) · [测试目录](#test-catalog) |
| **Web 自动化** | [Web 自动化](#ui-automation) · [录制与稳定回放](#web-recording-playback) · [失败排障](#web-troubleshooting) · [执行器使用说明](#runner-client) |
| **App 自动化** | [App 自动化](#app-automation) · [执行器安装指南](#runner-install-guide) · [执行器使用说明](#runner-client) |
| **接口与数据** | [接口自动化](#api-automation) · [数据工厂](#data-factory) · [Token 授权](#api-auth) |
| **性能测试** | [性能测试](#perf-testing) · [压测 Worker 协议](#perf-worker-protocol) |
| **AI 测试** | [AI 测试](#ai-testing) · [迭代资料库](#knowledge-base) · [**智能浏览器**](#browser-lab) · [平台内 AI 助手](#platform-assistant) · [MCP 外部接入](#mcp-server) |
| **系统管理** | [系统管理](#system-admin) |

## 平台定位

- **统一入口**：项目、环境、权限、看板共用一套体系
- **降低门槛**：录制回放、Swagger 导入、AI 辅助生成
- **提升效率**：定时回归、失败智能分析、执行完自动推送
- **报告可读可对比**：Web/App/接口/压测沉淀 HTML 与明细；压测支持真分位、验收目标、基线与多轮对照
- **资产沉淀**：功能用例库、迭代资料库、用例导入导出

## 核心能力一览

| 模块 | 主要能力 |
|------|----------|
| [**Web 自动化**](#ui-automation) | 可视化编排、步骤片段、测试文件库、录制回放、套件与执行计划、定时任务、截图/视频报告 |
| [**App 自动化**](#app-automation) | 用例/套件/计划编排、元素库、**元素探查**、步骤片段、定时任务；真机执行需 Runner 勾选 **App 自动化** |
| [**接口自动化**](#api-automation) | Swagger / Postman / cURL 导入、测试计划、Mock、数据驱动、Token 授权、数据工厂与库断言 |
| [**性能测试**](#perf-testing) | 固定/循环/梯度压测、流式 SSE、业务链路、CSV 参数化、分布式 Worker（Runner / Perf）、验收目标与基线、**增强报告（真分位 / 对照 / HTML）** |
| [**AI 测试**](#ai-testing) | 需求生成功能用例、[**迭代资料库**](#knowledge-base)、[**智能浏览器**](#browser-lab)、录制优化、失败分析 |
| **平台能力** | 数据看板、邮件/钉钉/企微通知、[MCP 外部接入](#mcp-server)、[平台助手「小测」](#platform-assistant)、RBAC、文档中心 |

> **Web / App 执行** 依赖网盘或设备管理下载的 **BrickCoreRunner**（见 [执行器使用说明](#runner-client)）。App 真机调度须使用勾选 **App 自动化** 的整包。**压测**须上线压测 Worker（Runner 压测角色或精简 **BrickCorePerf**），平台不本机代压。

## App 自动化（摘要）

| 能力 | 说明 |
|------|------|
| 平台编排 | 用例、元素库、元素探查、套件、计划、定时任务、步骤片段 |
| 真机执行 | Runner 勾选 App + `adb devices`；详见 [App 自动化](#app-automation) |
| 技术栈 | u2 原生 + WebView/Chrome H5 + 图像模板 |

## 性能测试

**路径**：**性能测试**（场景管理 / 执行机 / 执行记录 / 报告对比 / 定时压测）

面向 HTTP 接口与流式问答压测：平台负责编排、派发与报告聚合，**施压一律由在线 Worker 执行**。

| 能力 | 说明 |
|------|------|
| 压测模式 | **固定并发**、**循环**（总量可控）、**梯度**（分阶段加压找拐点）；另有 **流式阶段**（每用户 1 次 SSE） |
| 流式 / SSE | 场景可开 **流式问答**；报告展示首字/阶段耗时等 SSE 摘要，并与 QPS/RT 对照阅读 |
| 业务链路 | 多步骤 journey；步骤可混用普通 HTTP 与流式 |
| 数据与间隔 | CSV 参数化、数据工厂变量、固定/随机请求间隔、Ramp-up / Warmup |
| 执行机 | **BrickCoreRunner**（压测角色）或精简包 **BrickCorePerf**，二选一上线；支持多节点叠加；契约见 [压测 Worker 协议](#perf-worker-protocol) |
| **增强报告** | **真分位**（多机合并，非近似估算）、有效 QPS、SSE/HTTP 明细与秒级趋势；**多轮对照** / **梯度对照**；HTML/Excel 导出，便于版本对比与对外汇报 |
| 护栏 | **性能验收目标**、**历史基线**、**错误率熔断**三者独立；报告解释是否达目标，不编造未配置的基准 |
| AI | 一句话生成场景草稿；报告 AI 分析解释目标判定 |
| 通知 | 执行结束可走邮件等渠道推送摘要（见 [系统管理](#system-admin)） |

> **勿对生产误压**。压测前先用低并发或单接口用例验证 Host / Token；定时压测触发时也须有在线 Worker。

详细配置与常见问题见 [性能测试](#perf-testing)。

## AI 能力（摘要）

| 能力 | 说明 |
|------|------|
| 需求 → 功能用例 | 上传 PRD，AI 批量生成 → [AI 测试](#ai-testing) |
| 迭代资料库 | 文件夹、检索/问答、通用报告向导；定制页签需联系管理员开通 → [迭代资料库](#knowledge-base) |
| 录制 + AI 优化 | Playwright 录制步骤 → [Web 自动化](#ui-automation) |
| 失败根因 / 报告摘要 | 执行后一键分析 → [AI 测试](#ai-testing) |
| 平台助手 / MCP | 自然语言查数 → [平台内 AI 助手](#platform-assistant) · [MCP 外部接入](#mcp-server) |
| 智能浏览器 | 自然语言探索页面 → [智能浏览器](#browser-lab) |

## 建议上手路径

1. **本章（亮点功能）** — 了解平台定位与核心能力
2. [**使用说明**](#home) — 登录、选项目、安装执行器
3. [**平台概览**](#quick-start) — 熟悉菜单与流程
4. [**项目与环境**](#project-setup) — 完成基础配置
5. [**Web 自动化**](#ui-automation) 或 [**接口自动化**](#api-automation)（Web 需先安装 [执行器](#runner-client)）
6. [**App 自动化**](#app-automation) — 体验编排与元素探查（真机执行需 App Runner）
7. [**性能测试**](#perf-testing) — 上线 Worker → 配置场景 → 看增强报告（真分位 / 基线 / 多轮对照）
8. [**迭代资料库**](#knowledge-base) — 建文件夹、检索与通用报告向导
9. [**系统管理**](#system-admin) — 管理员配置通知与权限

各模块逐步操作见上方 **快速跳转** 或左侧目录。
