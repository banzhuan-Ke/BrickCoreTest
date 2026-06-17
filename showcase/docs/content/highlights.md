# 亮点功能

BrickCore 将 **UI 自动化、接口自动化、性能测试、AI 测试** 整合在同一套平台中，覆盖从需求理解、用例设计、自动执行到报告推送的完整流程。

> **首次进入文档中心时建议先阅读本章**；登录、项目切换等基础操作见 [使用说明](#home)。

## 快速跳转

| 分类 | 文档 |
|------|------|
| **快速开始** | [使用说明](#home) · [平台概览](#quick-start) · [项目与环境](#project-setup) · [测试目录](#test-catalog) |
| **UI 自动化** | [UI 自动化](#ui-automation) · [执行器使用说明](#runner-client) · [执行器获取与发布](#runner-packaging) |
| **接口与数据** | [接口自动化](#api-automation) · [数据工厂](#data-factory) · [Token 授权](#api-auth) |
| **性能测试** | [性能测试](#perf-testing) |
| **AI 测试** | [AI 测试](#ai-testing) · [平台内 AI 助手](#platform-assistant) · [MCP 外部接入](#mcp-server) |
| **系统管理** | [系统管理](#system-admin) |

## 平台定位

- **统一入口**：项目、环境、权限、看板共用一套体系
- **降低门槛**：录制回放、Swagger 导入、AI 辅助生成
- **提升效率**：定时回归、自动报告推送、失败智能分析
- **资产沉淀**：功能用例库、用例导入导出

## 核心能力一览

| 模块 | 主要能力 |
|------|----------|
| [**UI 自动化**](#ui-automation) | 可视化编排、录制回放、套件与执行计划、定时任务、截图/视频报告 |
| [**接口自动化**](#api-automation) | Swagger / Postman / cURL 导入、测试计划、Mock、数据驱动、Token 授权、数据工厂与库断言 |
| [**性能测试**](#perf-testing) | 场景压测、梯度加压、分布式 Worker、报告对比 |
| [**AI 测试**](#ai-testing) | 需求生成功能用例、问答准确性评测、录制优化、失败分析 |
| **平台能力** | 数据看板、[MCP 外部接入](#mcp-server)、[平台助手「小测」](#platform-assistant)、通知、RBAC、文档中心 |

> **UI / 录制 / 分布式压测 Worker** 依赖网盘分发的 **BrickCoreRunner**（见 [执行器使用说明](#runner-client)）。

## AI 能力（摘要）

| 能力 | 说明 |
|------|------|
| 需求 → 功能用例 | 上传 PRD，AI 批量生成 → [AI 测试](#ai-testing) |
| 录制 + AI 优化 | Playwright 录制步骤 → [UI 自动化](#ui-automation) |
| 失败根因 / 报告摘要 | 执行后一键分析 |
| 问答准确性评测 | 标准题集 + SSE 被测 API + 统计报告 → [AI 测试](#ai-testing) |
| 平台助手 / MCP | 自然语言查数 → [平台内 AI 助手](#platform-assistant) · [MCP 外部接入](#mcp-server) |

## 建议上手路径

1. **本章（亮点功能）** — 了解平台定位与核心能力
2. [**使用说明**](#home) — 登录、选项目、权限说明
3. [**平台概览**](#quick-start) — 熟悉菜单与流程
4. [**项目与环境**](#project-setup) — 完成基础配置
5. [**接口自动化**](#api-automation) 或 [**UI 自动化**](#ui-automation)（需先安装 [执行器](#runner-client)）
6. [**系统管理**](#system-admin) — 管理员配置通知与权限

各模块逐步操作见上方 **快速跳转** 或左侧目录。
