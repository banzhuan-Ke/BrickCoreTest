"""平台内 AI 助手 — 一次性 JSON 回答（无 SSE）"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from fastapi import HTTPException

from app.modules.ai.ai_scene_config import resolve_config_for_scene
from app.core.llm.ai_usage_log import record_ai_usage
from app.modules.assistant.assistant_execution_watch import schedule_execution_watch
from app.modules.assistant.assistant_session import load_session_messages, save_session_messages
from app.modules.assistant.assistant_tools import (
    get_tool_selection_schemas,
    compact_tools_payload,
    extract_pending_confirm,
    invoke_assistant_tool,
    invoke_confirm_tool,
    truncate_tool_result,
)
from app.core.platform.encryption import decrypt_value
from app.core.llm.llm_client import LLMClientFactory
from app.mcp.auth import McpAuthContext
from app.models.ai import AiConfig
from app.models.sys import Project

logger = logging.getLogger(__name__)

ASSISTANT_MAX_SECONDS = 300
LLM_CALL_TIMEOUT = 240
TOOL_SELECT_TIMEOUT = 45

_OVERVIEW_HINTS = ("总结", "概览", "完整情况", "项目情况", "全貌", "介绍一下")
_FAILURE_HINTS = ("失败", "报错", "错误", "不通过", "failed")
_REQUIREMENT_HINTS = ("需求", "需求文档", "需求列表")
_CASE_HINTS = ("用例", "case", "工作区")
_LIBRARY_HINTS = ("功能用例库", "用例库", "functional")
_API_HINTS = ("接口", "api", "API", "endpoint", "路径", "请求")
_UI_HINTS = ("ui", "UI", "界面", "web", "计划")
_APP_HINTS = ("app", "App", "APP", "移动端", "安卓", "Android", "真机", "模拟器", "元素探查", "元素库")
_EXECUTE_HINTS = ("执行", "运行", "触发", "跑", "启动")
_EXECUTE_CAPABILITY_PHRASES = (
    "可以吗",
    "能否",
    "能不能",
    "可不可以",
    "是否可以",
    "能不能直接",
    "能否直接",
    "可以执行",
    "能执行",
    "可以跑",
    "能跑",
    "可以运行",
    "能运行",
    "帮我执行",
    "帮我跑",
    "帮我运行",
    "直接帮",
    "我是说",
    "会执行",
)
_QA_EVAL_HINTS = ("问答评测", "问答准确性", "qa eval", "qa_eval", "评测集", "问答准确")
_PERF_HINTS = ("压测", "性能", "perf", "Perf", "TPS", "QPS", "并发")
_RECORD_HINTS = ("执行记录", "跑测", "运行记录", "最近执行", "测试记录", "报告")
_API_PLAN_HINTS = ("测试计划", "接口计划", "编排计划", "api计划")
_MOCK_HINTS = ("mock", "Mock", "模拟接口")
_CRON_HINTS = ("定时", "cron", "调度", "Cron")
_DATA_FACTORY_HINTS = ("数据工厂", "数据源", "SQL模板", "SQL 模板", "sql模板", "造数", "数据准备")

SYSTEM_PROMPT = """你是 BrickCore 测试平台助手。根据用户问题与附带的平台查询 JSON 数据，用简体中文回答。
可综合多个工具的结果作答。不要编造数据中不存在的内容；若某类数据未出现在 JSON 中，请明确说明「平台未返回该数据」，不要从失败记录等无关数据猜测。
若 JSON 中包含 list_api_categories、list_api_definitions、list_api_test_cases，必须优先用这些字段回答接口管理与接口用例问题。
若某工具返回 permission_denied 或 user_hint，请原样转告用户权限不足原因及 user_hint，不要尝试绕过权限。
若 JSON 含 _truncated 或 _truncated_note，说明列表被截断，回答时注明「仅展示部分数据」。
回答使用 Markdown；段落之间最多空一行，列表项之间不要插入空行。
提及平台实体时请使用可识别格式便于跳转，例如：api_id=5、suite_id=12、plan_id=4、case_id=6（接口用例）、ui_case_id=8（Web UI 用例）、app_case_id=3、app_suite_id=2、app_plan_id=1、task_id=8、requirement_id=3、perf_scene_id=2、template_id=7、set_id=2；列表项可写 id=数字（须放在对应 App/Web/接口 小节下）。
你具备发起测试执行的能力：单条接口/Web UI/App 用例，接口/UI/App 套件与计划，压测场景，问答评测等；流程为先 preview 再展示 pending_confirm 确认卡片，用户点击「确认执行」后才真正跑测。
若用户询问「能否/可不可以执行用例」，应明确回答「可以」，说明需指定用例/套件/计划 ID 与环境 ID（Web/App UI 还需 Runner device_id），并给出示例说法；可结合 list_environments、list_online_devices 等数据辅助说明。
禁止因本次 JSON 未含 preview 结果、或无执行按钮字段，就声称「无法执行任何用例」——未调用 preview 仅表示尚未发起执行，不等于平台无执行能力。
危险操作（执行测试、批量生成、失败分析）需用户在前端点击确认后才会真正执行；若返回了 pending_confirm，请简要说明影响并提示用户确认。"""

TOOL_SELECT_PROMPT = """你是 BrickCore 平台工具规划器。根据用户问题，从可用工具中选择 1～4 个最相关的工具及参数。
规则：
- 项目总结/概览优先 get_project_overview，可叠加 list_recent_failures、list_requirements
- **接口管理概览/汇总**（未要求逐条列举）：优先 list_api_categories + list_api_suites，**不要**同时拉全量 list_api_definitions + list_api_test_cases
- **接口管理/接口用例详情**：用 list_api_categories + list_api_definitions + list_api_test_cases（可选 list_api_suites），**禁止**用 list_requirements
- 查单个接口详情用 get_api_definition
- 查 UI 计划/用例用 list_ui_tasks / list_ui_cases；UI 执行记录用 list_ui_run_records
- App 移动端用 list_app_cases / list_app_suites / list_app_plans；App 执行记录用 list_app_run_records；App 定时用 list_app_cron_jobs
- 接口测试计划用 list_api_plans；接口执行记录用 list_api_run_records
- 压测场景/记录/定时/Worker 用 list_perf_scenes / list_perf_records / list_perf_cron_jobs / list_perf_workers
- UI 套件/定时用 list_ui_suites / list_ui_cron_jobs
- Mock 接口用 list_mock_apis；数据工厂数据源/SQL 模板用 list_data_factory_datasources / list_sql_templates / get_sql_template
- 执行接口套件/计划用 preview_run_api_suite / preview_run_api_plan（需用户 confirm，执行记录触发方式为「小测」）
- 执行单条接口用例用 preview_run_api_case（case_id 或 case_name + env_id，确认后同步返回结果）
- 执行单条 Web UI 用例用 preview_run_ui_case（case_id 或 case_name + env_id + device_id）
- 执行单条 App 用例用 preview_run_app_case（需在线 App Runner + adb 设备）
- 执行 App 套件用 preview_run_app_suite；App 测试计划用 preview_run_app_plan（均需 env_id、device_id）
- 问答准确性评测：支持「跑评测集 2 第 1-10 题」自动解析 range；需 target_id
- Web UI 执行前可先 list_online_devices 获取在线 Runner 的 device_id；App 执行需 App Runner 及 app_udid
- 执行 UI 测试计划用 preview_run_ui_task；Web UI 套件用 preview_run_ui_suite（均需 env_id、device_id）
- 启动压测场景用 preview_run_perf_scene（需 env_id；施压必须有在线 Worker，不再支持本机直跑）
- 查单条执行详情用 get_execution_record（record_type: api_suite/api_plan/ui_plan/ui_case/app_plan/app_suite/app_case/perf）
- 用户明确要求执行/生成/分析时，调用对应的 preview_* 工具（不要直接 confirm）
- **执行能力咨询**（如「你能执行用例吗」「可以直接帮我跑吗」，且未给用例/套件 ID）：调用 list_environments，涉及 UI/App 时加 list_online_devices；涉及接口时加 list_api_test_cases；涉及 Web UI 时加 list_ui_cases；**不要**仅查执行记录 list_*_run_records / get_execution_record
- 只选择与问题相关的工具；当前项目 ID 已给定，project_id 请使用该值
- 若仅需闲聊或无法查询，可不调用任何工具"""


async def build_assistant_ctx(user_info: dict) -> McpAuthContext:
    from app.core.platform.permissions import get_user_permissions
    from app.models.sys import User

    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise ValueError("用户不存在")
    perms = set(await get_user_permissions(user))
    return McpAuthContext(
        username=user.username,
        user_id=user.id,
        is_superuser=bool(user.is_superuser),
        permissions=perms,
    )


async def resolve_project_context(project_id: int | None) -> tuple[int | None, str]:
    if not project_id:
        return None, "未选择项目"
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return project_id, f"ID={project_id}（不存在）"
    return project_id, f"{project.name} (id={project.id})"


def _extract_requirement_id(message: str) -> int | None:
    m = re.search(r"需求\s*[：:#]?\s*(\d+)", message or "")
    if m:
        return int(m.group(1))
    m = re.search(r"requirement[_\s-]*id\s*[=:]?\s*(\d+)", message or "", re.I)
    return int(m.group(1)) if m else None


def _extract_id(message: str, labels: tuple[str, ...]) -> int | None:
    for label in labels:
        m = re.search(rf"{label}\s*[：:#]?\s*(\d+)", message or "", re.I)
        if m:
            return int(m.group(1))
    return None


def _is_execution_capability_inquiry(message: str) -> bool:
    """用户询问「能否执行用例」等能力问题（非具体执行指令）。"""
    text = (message or "").strip()
    if not text:
        return False
    if any(h in text for h in _RECORD_HINTS):
        return False
    if _extract_id(
        text,
        ("用例", "case", "套件", "suite", "计划", "plan", "task", "任务", "场景", "scene"),
    ):
        return False
    if not any(h in text for h in _EXECUTE_HINTS):
        return False
    if any(p in text for p in _EXECUTE_CAPABILITY_PHRASES):
        return True
    return text.endswith(("吗", "?", "？"))


def _plan_tools_for_execution_capability(
    message: str, project_id: int
) -> list[tuple[str, dict[str, Any]]]:
    """执行能力咨询：拉环境/设备/用例摘要，供回答时举例。"""
    pid = project_id
    planned: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    def add(name: str, args: dict[str, Any]) -> None:
        if name not in seen:
            seen.add(name)
            planned.append((name, args))

    text = message or ""
    tl = text.lower()
    mentions_api = _is_api_automation_context(text) or "接口" in text
    mentions_ui = any(h in text for h in _UI_HINTS) or "ui" in tl or "界面" in text
    mentions_app = any(h in text for h in _APP_HINTS) or "app" in tl

    add("list_environments", {"project_id": pid})

    if mentions_ui or mentions_app or not mentions_api:
        add("list_online_devices", {"project_id": pid})
    if mentions_ui or (not mentions_api and not mentions_app):
        add("list_ui_cases", {"project_id": pid, "page": 1, "size": 10})
    if mentions_api or "接口" in text:
        add("list_api_test_cases", {"project_id": pid, "page": 1, "size": 10})
    if mentions_app:
        add("list_app_cases", {"project_id": pid, "page": 1, "size": 10})

    return planned[:4]


def _execution_capability_answer_hint() -> str:
    return (
        "\n\n【执行能力说明】用户是在询问能否由助手代为发起测试执行，而非查询某条执行记录。"
        "请明确回答：可以；流程为 preview → 聊天内确认卡片 → 确认后执行。"
        "分别说明接口用例（case_id + env_id）、Web UI 用例（case_id + env_id + device_id）的示例说法；"
        "若 JSON 中有环境与设备/用例列表，可举 1～2 个真实 ID 作为示例。"
        "不要回答「无法执行」或「必须由您在前端页面完成全部操作」。"
    )


def _is_api_automation_context(text: str) -> bool:
    """接口自动化领域（区别于需求/功能用例工作区）。"""
    t = (text or "").strip()
    tl = t.lower()
    api_phrases = (
        "接口用例",
        "接口测试",
        "接口管理",
        "接口定义",
        "接口列表",
        "接口套件",
        "接口自动化",
        "api用例",
        "api case",
        "api test",
        "api suite",
        "api definition",
    )
    if any(p in t or p in tl for p in api_phrases):
        return True
    if ("接口" in t or "api" in tl) and "用例" in t:
        return True
    return any(h in t for h in _API_HINTS)


def _add_api_tool_bundle(
    add,
    pid: int,
    *,
    keyword: str = "",
    api_id: int | None = None,
    include_suites: bool = True,
    detail_level: str = "full",
) -> None:
    """detail_level: overview=分类+套件；cases=分类+用例；full=完整四工具包。"""
    level = (detail_level or "full").lower()
    add("list_api_categories", {"project_id": pid})
    if level == "overview":
        add("list_api_suites", {"project_id": pid, "keyword": keyword, "page": 1, "size": 15})
        return
    if level == "cases":
        case_args: dict[str, Any] = {"project_id": pid, "page": 1, "size": 20}
        if api_id:
            case_args["api_id"] = api_id
        if keyword:
            case_args["keyword"] = keyword
        add("list_api_test_cases", case_args)
        return
    add("list_api_definitions", {"project_id": pid, "keyword": keyword, "page": 1, "size": 20})
    case_args = {"project_id": pid, "page": 1, "size": 20}
    if api_id:
        case_args["api_id"] = api_id
    if keyword:
        case_args["keyword"] = keyword
    add("list_api_test_cases", case_args)
    if include_suites:
        add("list_api_suites", {"project_id": pid, "keyword": keyword, "page": 1, "size": 15})


def _api_overview_intent(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    overview_words = ("概览", "汇总", "统计", "有多少", "概况", "整体", "分类")
    detail_words = ("列出", "明细", "逐条", "全部", "详情", "哪些用例", "用例列表")
    if any(w in t for w in detail_words):
        return False
    if any(w in t for w in overview_words):
        return True
    if "接口" in t and any(w in t for w in ("情况", "总结", "介绍")):
        return True
    return False


def _safe_int(value: Any) -> int | None:
    try:
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_qa_eval_range(text: str) -> tuple[int, int] | None:
    """从自然语言解析评测序号区间，如「第 1-10 题」「序号 1 到 10」。"""
    patterns = (
        r"第?\s*(\d+)\s*[～~\-—至到]\s*(\d+)\s*[题号]?",
        r"序号\s*(\d+)\s*[～~\-—至到]\s*(\d+)",
        r"(\d+)\s*到\s*(\d+)\s*题",
    )
    for pat in patterns:
        m = re.search(pat, text or "")
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start <= end:
                return start, end
    return None


def _format_page_context_hint(page_context: dict[str, Any] | None) -> str:
    if not page_context:
        return ""
    label = page_context.get("page_label") or page_context.get("page") or ""
    parts = [f"页面：{label}"] if label else []
    for key, label_name in (
        ("api_id", "接口 ID"),
        ("suite_id", "套件 ID"),
        ("requirement_id", "需求 ID"),
        ("task_id", "UI 计划 ID"),
        ("ui_case_id", "UI 用例 ID"),
        ("api_run_record_id", "接口执行记录 ID"),
        ("plan_id", "测试计划 ID"),
        ("perf_scene_id", "压测场景 ID"),
        ("perf_record_id", "压测记录 ID"),
        ("ui_task_run_id", "UI 执行记录 ID"),
        ("ui_suite_run_id", "UI 套件执行记录 ID"),
        ("template_id", "SQL 模板 ID"),
        ("datasource_id", "数据源 ID"),
        ("set_id", "问答评测集 ID"),
    ):
        val = page_context.get(key)
        if val:
            parts.append(f"{label_name}={val}")
    hint = page_context.get("page_hint")
    if hint:
        parts.append(f"页面类型={hint}")
    if not parts:
        return ""
    return (
        "\n当前页面上下文：" + "；".join(parts)
        + "。用户可能针对当前页面提问，优先调用与上述 ID/页面类型相关的工具。\n"
    )


def _plan_tools_from_page_context(
    page_context: dict[str, Any] | None,
    project_id: int,
) -> list[tuple[str, dict[str, Any]]]:
    """根据前端 page_context 预规划 1～4 个高相关工具。"""
    if not page_context or not project_id:
        return []
    pid = project_id
    planned: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    def add(name: str, args: dict[str, Any]) -> None:
        if name not in seen:
            seen.add(name)
            planned.append((name, args))

    api_id = _safe_int(page_context.get("api_id"))
    suite_id = _safe_int(page_context.get("suite_id"))
    req_id = _safe_int(page_context.get("requirement_id"))
    task_id = _safe_int(page_context.get("task_id"))
    ui_case_id = _safe_int(page_context.get("ui_case_id"))
    api_run_id = _safe_int(page_context.get("api_run_record_id"))
    plan_id = _safe_int(page_context.get("plan_id"))
    perf_scene_id = _safe_int(page_context.get("perf_scene_id"))
    perf_record_id = _safe_int(page_context.get("perf_record_id"))
    ui_task_run_id = _safe_int(page_context.get("ui_task_run_id"))
    ui_suite_run_id = _safe_int(page_context.get("ui_suite_run_id"))
    app_case_id = _safe_int(page_context.get("app_case_id"))
    app_plan_id = _safe_int(page_context.get("app_plan_id"))
    app_suite_run_id = _safe_int(page_context.get("app_suite_run_id"))
    app_plan_run_id = _safe_int(page_context.get("app_plan_run_id"))
    template_id = _safe_int(page_context.get("template_id"))
    page_hint = (page_context.get("page_hint") or "").strip()

    if api_id:
        add("get_api_definition", {"api_id": api_id, "project_id": pid})
        add("list_api_test_cases", {"project_id": pid, "api_id": api_id, "page": 1, "size": 30})
    elif suite_id:
        add("list_api_suites", {"project_id": pid, "keyword": "", "page": 1, "size": 20})
        add("list_api_definitions", {"project_id": pid, "keyword": "", "page": 1, "size": 20})
    elif req_id:
        add("get_requirement", {"requirement_id": req_id, "project_id": pid})
        add("list_requirement_cases", {"requirement_id": req_id, "project_id": pid, "page": 1, "size": 30})
    elif task_id:
        add("list_ui_tasks", {"project_id": pid, "keyword": "", "page": 1, "size": 20})
        add("list_ui_cases", {"project_id": pid, "page": 1, "size": 20})
    elif ui_case_id:
        add("list_ui_cases", {"project_id": pid, "page": 1, "size": 30})
    elif api_run_id:
        add("get_execution_record", {"record_type": "api_suite", "record_id": api_run_id})
        add("list_recent_failures", {"project_id": pid, "limit": 8})
    elif plan_id:
        add("list_api_plans", {"project_id": pid, "keyword": "", "page": 1, "size": 15})
        add("list_api_run_records", {"project_id": pid, "record_type": "plan", "page": 1, "size": 10})
    elif perf_scene_id:
        add("list_perf_scenes", {"project_id": pid, "page": 1, "size": 15})
        add("list_perf_records", {"project_id": pid, "scene_id": perf_scene_id, "page": 1, "size": 10})
    elif perf_record_id:
        add("get_execution_record", {"record_type": "perf", "record_id": perf_record_id})
        add("list_perf_records", {"project_id": pid, "page": 1, "size": 10})
    elif ui_task_run_id:
        add("list_ui_run_records", {"project_id": pid, "page": 1, "size": 10})
        add("get_execution_record", {"record_type": "ui_plan", "record_id": ui_task_run_id})
    elif ui_suite_run_id:
        add("get_execution_record", {"record_type": "ui_suite", "record_id": ui_suite_run_id})
        add("list_ui_run_records", {"project_id": pid, "page": 1, "size": 10})
    elif app_case_id:
        add("list_app_cases", {"project_id": pid, "page": 1, "size": 30})
    elif app_plan_id:
        add("list_app_plans", {"project_id": pid, "page": 1, "size": 15})
        add("list_app_run_records", {"project_id": pid, "record_type": "plan", "page": 1, "size": 10})
    elif app_plan_run_id:
        add("get_execution_record", {"record_type": "app_plan", "record_id": app_plan_run_id})
        add("list_app_run_records", {"project_id": pid, "page": 1, "size": 10})
    elif app_suite_run_id:
        add("get_execution_record", {"record_type": "app_suite", "record_id": app_suite_run_id})
        add("list_app_run_records", {"project_id": pid, "page": 1, "size": 10})
    elif template_id:
        add("get_sql_template", {"template_id": template_id})
        add("list_sql_templates", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "data_factory":
        add("list_data_factory_datasources", {"project_id": pid, "page": 1, "size": 20})
        add("list_sql_templates", {"project_id": pid, "page": 1, "size": 20})
    elif page_hint == "mock_apis":
        add("list_mock_apis", {"project_id": pid, "page": 1, "size": 20})
    elif page_hint == "qa_eval":
        add("list_qa_eval_sets", {"project_id": pid})
    elif page_hint == "online_devices":
        add("list_online_devices", {"project_id": pid})
    elif page_hint == "api_plans":
        add("list_api_plans", {"project_id": pid, "keyword": "", "page": 1, "size": 15})
        add("list_api_run_records", {"project_id": pid, "record_type": "plan", "page": 1, "size": 10})
    elif page_hint == "ui_suites":
        add("list_ui_suites", {"project_id": pid, "page": 1, "size": 20})
        add("list_ui_cases", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "cron_jobs":
        add("list_api_cron_jobs", {"project_id": pid, "page": 1, "size": 10})
        add("list_ui_cron_jobs", {"project_id": pid, "page": 1, "size": 10})
        add("list_app_cron_jobs", {"project_id": pid, "page": 1, "size": 10})
        add("list_perf_cron_jobs", {"project_id": pid, "page": 1, "size": 10})
    elif page_hint == "perf_scenes":
        add("list_perf_scenes", {"project_id": pid, "page": 1, "size": 15})
        add("list_perf_records", {"project_id": pid, "page": 1, "size": 10})
    elif page_hint == "perf_workers":
        add("list_perf_workers", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "api_definitions":
        _add_api_tool_bundle(add, pid, detail_level="overview")
    elif page_hint == "api_test_cases":
        add("list_api_categories", {"project_id": pid})
        add("list_api_test_cases", {"project_id": pid, "page": 1, "size": 20})
    elif page_hint == "api_suites":
        add("list_api_suites", {"project_id": pid, "keyword": "", "page": 1, "size": 20})
        add("list_api_categories", {"project_id": pid})
    elif page_hint in ("requirements", "functional_cases"):
        add("list_requirements", {"project_id": pid, "page": 1, "size": 20})
    elif page_hint == "ui_cases":
        add("list_ui_cases", {"project_id": pid, "page": 1, "size": 20})
        add("list_ui_tasks", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "app_cases":
        add("list_app_cases", {"project_id": pid, "page": 1, "size": 20})
        add("list_app_plans", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "app_suites":
        add("list_app_suites", {"project_id": pid, "page": 1, "size": 20})
        add("list_app_cases", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "app_plans":
        add("list_app_plans", {"project_id": pid, "page": 1, "size": 15})
        add("list_app_run_records", {"project_id": pid, "record_type": "plan", "page": 1, "size": 10})
    elif page_hint == "app_run_records":
        add("list_app_run_records", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint == "app_inspector":
        add("list_online_devices", {"project_id": pid})
        add("list_app_cases", {"project_id": pid, "page": 1, "size": 15})
    elif page_hint in ("api_run_records", "ui_run_records"):
        add("list_api_run_records", {"project_id": pid, "page": 1, "size": 15})
        add("list_ui_run_records", {"project_id": pid, "page": 1, "size": 15})

    return planned[:4]


def _merge_planned_tools(
    *groups: list[tuple[str, dict[str, Any]]],
    max_tools: int = 4,
) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    merged: list[tuple[str, dict[str, Any]]] = []
    for group in groups:
        for name, args in group:
            if name in seen:
                continue
            seen.add(name)
            merged.append((name, args))
            if len(merged) >= max_tools:
                return merged
    return merged


def _plan_tools(message: str, project_id: int | None) -> list[tuple[str, dict[str, Any]]]:
    """关键词规划工具（LLM 选工具失败时的兜底）。"""
    if not project_id:
        return []
    text = (message or "").strip()
    pid = project_id
    planned: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    def add(name: str, args: dict[str, Any]) -> None:
        if name not in seen:
            seen.add(name)
            planned.append((name, args))

    req_id = _extract_requirement_id(text)
    is_summary = any(h in text for h in ("总结", "概览", "完整情况", "全貌", "介绍一下"))
    is_api_ctx = _is_api_automation_context(text)

    if is_summary:
        add("get_project_overview", {"project_id": pid})
        add("list_recent_failures", {"project_id": pid, "limit": 15})
        if not is_api_ctx:
            add("list_requirements", {"project_id": pid, "page": 1, "size": 20})
        add("list_api_definitions", {"project_id": pid, "keyword": "", "page": 1, "size": 30})
    elif any(h in text for h in _OVERVIEW_HINTS) or "项目" in text:
        add("get_project_overview", {"project_id": pid})

    if not is_summary and any(h in text for h in _FAILURE_HINTS):
        add("list_recent_failures", {"project_id": pid, "limit": 10})

    if not is_summary and not is_api_ctx and (
        any(h in text for h in _REQUIREMENT_HINTS)
        or (any(h in text for h in _CASE_HINTS) and "功能" not in text)
    ):
        add("list_requirements", {"project_id": pid, "page": 1, "size": 20})
        if req_id:
            add(
                "list_requirement_cases",
                {"requirement_id": req_id, "project_id": pid, "page": 1, "size": 30},
            )

    if any(h in text for h in _LIBRARY_HINTS):
        kw = ""
        m = re.search(r"搜索[：:]?\s*(.+)", text)
        if m:
            kw = m.group(1).strip()[:50]
        add("search_functional_cases", {"project_id": pid, "keyword": kw, "page": 1, "size": 15})

    if is_api_ctx:
        kw = ""
        m = re.search(r"(?:接口|API)\s*[：:#]?\s*(.+)", text, re.I)
        if m:
            kw = m.group(1).strip()[:50]
        api_id = _extract_id(text, ("接口", "api", "API"))
        if api_id and ("详情" in text or "detail" in text.lower()):
            add("get_api_definition", {"api_id": api_id, "project_id": pid})
        elif "用例" in text and api_id:
            _add_api_tool_bundle(add, pid, keyword=kw, api_id=api_id, detail_level="cases")
        elif _api_overview_intent(text):
            _add_api_tool_bundle(add, pid, keyword=kw, detail_level="overview")
        else:
            _add_api_tool_bundle(add, pid, keyword=kw, api_id=api_id if api_id and "用例" in text else None)
    elif any(h in text for h in _API_HINTS):
        kw = ""
        m = re.search(r"(?:接口|API)\s*[：:#]?\s*(.+)", text, re.I)
        if m:
            kw = m.group(1).strip()[:50]
        api_id = _extract_id(text, ("接口", "api", "API"))
        if api_id and ("详情" in text or "detail" in text.lower()):
            add("get_api_definition", {"api_id": api_id, "project_id": pid})
        else:
            add("list_api_definitions", {"project_id": pid, "keyword": kw, "page": 1, "size": 30})

    if any(h in text for h in _PERF_HINTS):
        scene_id = _extract_id(text, ("场景", "scene"))
        add("list_perf_scenes", {"project_id": pid, "page": 1, "size": 15})
        add(
            "list_perf_records",
            {"project_id": pid, "scene_id": scene_id, "page": 1, "size": 15},
        )

    is_ui_record = any(h in text for h in ("UI执行", "界面执行", "Web执行")) or (
        any(h in text for h in _RECORD_HINTS) and any(h in text for h in _UI_HINTS)
    )
    is_app_ctx = any(h in text for h in _APP_HINTS)
    is_app_record = any(h in text for h in ("App执行", "APP执行", "移动端执行")) or (
        any(h in text for h in _RECORD_HINTS) and is_app_ctx
    )
    is_api_record = any(h in text for h in ("接口执行", "套件执行", "API执行")) or (
        any(h in text for h in _RECORD_HINTS) and is_api_ctx
    )
    if is_api_record or (
        any(h in text for h in _RECORD_HINTS)
        and not is_ui_record
        and not is_app_record
        and not any(h in text for h in _PERF_HINTS)
    ):
        if "计划" in text and "UI" not in text.upper() and "界面" not in text and not is_app_ctx:
            add("list_api_run_records", {"project_id": pid, "record_type": "plan", "page": 1, "size": 15})
        else:
            add("list_api_run_records", {"project_id": pid, "page": 1, "size": 15})
    elif is_app_record:
        rt = ""
        if "计划" in text:
            rt = "plan"
        elif "套件" in text:
            rt = "suite"
        args: dict[str, Any] = {"project_id": pid, "page": 1, "size": 15}
        if rt:
            args["record_type"] = rt
        add("list_app_run_records", args)
    elif is_ui_record:
        task_id = _extract_id(text, ("计划", "task", "任务"))
        args: dict[str, Any] = {"project_id": pid, "page": 1, "size": 15}
        if task_id:
            args["task_id"] = task_id
        add("list_ui_run_records", args)

    if any(h in text for h in _API_PLAN_HINTS) and "UI" not in text and "界面" not in text:
        add("list_api_plans", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in _MOCK_HINTS):
        add("list_mock_apis", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in _DATA_FACTORY_HINTS):
        template_id = _extract_id(text, ("模板", "template"))
        if template_id and ("详情" in text or "detail" in text.lower()):
            add("get_sql_template", {"template_id": template_id})
        else:
            add("list_data_factory_datasources", {"project_id": pid, "page": 1, "size": 15})
            add("list_sql_templates", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in _UI_HINTS) and not is_api_ctx and not is_app_ctx:
        if "计划" in text or "task" in text.lower():
            add("list_ui_tasks", {"project_id": pid, "page": 1, "size": 20})
        else:
            add("list_ui_cases", {"project_id": pid, "page": 1, "size": 20})

    if is_app_ctx and not is_api_ctx:
        if "计划" in text or "plan" in text.lower():
            add("list_app_plans", {"project_id": pid, "page": 1, "size": 20})
        elif "套件" in text:
            add("list_app_suites", {"project_id": pid, "page": 1, "size": 20})
        elif "用例" in text or "case" in text.lower():
            add("list_app_cases", {"project_id": pid, "page": 1, "size": 20})

    if any(h in text for h in _EXECUTE_HINTS):
        suite_id = _extract_id(text, ("套件", "suite"))
        plan_id = _extract_id(text, ("测试计划", "计划", "plan"))
        task_id = _extract_id(text, ("计划", "task", "任务"))
        scene_id = _extract_id(text, ("场景", "scene", "压测"))
        env_id = _extract_id(text, ("环境", "env"))
        case_id = _extract_id(text, ("用例", "case"))
        set_id = _extract_id(text, ("评测集", "set"))
        is_ui_exec = any(h in text for h in _UI_HINTS) and not is_api_ctx and not is_app_ctx
        is_app_exec = is_app_ctx and not is_api_ctx
        is_perf_exec = any(h in text for h in _PERF_HINTS)
        is_qa_eval = any(h in text for h in _QA_EVAL_HINTS)
        if is_qa_eval and set_id and any(h in text for h in _EXECUTE_HINTS):
            target_id = _extract_id(text, ("被测", "target", "api"))
            qa_args: dict[str, Any] = {"project_id": pid, "set_id": set_id}
            if target_id:
                qa_args["target_id"] = target_id
            qa_range = _parse_qa_eval_range(text)
            if qa_range:
                qa_args["case_scope"] = "range"
                qa_args["range_start"], qa_args["range_end"] = qa_range
            add("preview_run_qa_eval", qa_args)
        elif case_id and is_app_exec and not is_qa_eval and "套件" not in text:
            add(
                "preview_run_app_case",
                {
                    "project_id": pid,
                    "case_id": case_id,
                    "env_id": env_id or 0,
                    "device_id": "",
                },
            )
        elif case_id and is_ui_exec and not is_qa_eval and "套件" not in text:
            add(
                "preview_run_ui_case",
                {
                    "project_id": pid,
                    "case_id": case_id,
                    "env_id": env_id or 0,
                    "device_id": "",
                },
            )
        elif case_id and is_api_ctx and not is_qa_eval and "套件" not in text:
            add(
                "preview_run_api_case",
                {"project_id": pid, "case_id": case_id, "env_id": env_id or 0},
            )
        elif scene_id and is_perf_exec:
            add("preview_run_perf_scene", {"scene_id": scene_id, "env_id": env_id or 0})
        elif suite_id and is_ui_exec and "接口" not in text:
            add(
                "preview_run_ui_suite",
                {"suite_id": suite_id, "env_id": env_id or 0, "device_id": ""},
            )
        elif suite_id and is_app_exec and "接口" not in text:
            add(
                "preview_run_app_suite",
                {"suite_id": suite_id, "env_id": env_id or 0, "device_id": ""},
            )
        elif suite_id and (is_api_ctx or ("接口" in text and not is_ui_exec)):
            add("preview_run_api_suite", {"suite_id": suite_id, "env_id": env_id})
        elif plan_id and not is_ui_exec and "UI" not in text.upper() and not is_perf_exec:
            if is_app_exec:
                add(
                    "preview_run_app_plan",
                    {"plan_id": plan_id, "env_id": env_id or 0, "device_id": ""},
                )
            else:
                add("preview_run_api_plan", {"plan_id": plan_id, "env_id": env_id})
        elif task_id and is_ui_exec:
            add(
                "preview_run_ui_task",
                {"task_id": task_id, "env_id": env_id or 0, "device_id": ""},
            )

    if any(h in text for h in _CRON_HINTS):
        cron_all = any(k in text for k in ("四类", "三类", "汇总", "全部", "所有"))
        if cron_all or (
            not is_api_ctx
            and not any(h in text for h in _UI_HINTS)
            and not is_app_ctx
            and not any(h in text for h in _PERF_HINTS)
        ):
            add("list_api_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
            add("list_ui_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
            add("list_app_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
            add("list_perf_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
        elif any(h in text for h in _PERF_HINTS):
            add("list_perf_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
        elif is_app_ctx:
            add("list_app_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
        elif any(h in text for h in _UI_HINTS):
            add("list_ui_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
        elif is_api_ctx:
            add("list_api_cron_jobs", {"project_id": pid, "page": 1, "size": 15})
        else:
            add("list_api_cron_jobs", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in _QA_EVAL_HINTS) and not any(h in text for h in _EXECUTE_HINTS):
        add("list_qa_eval_sets", {"project_id": pid})

    if any(k in text for k in ("runner", "device_id", "执行设备", "执行器", "在线设备")) and (
        any(h in text for h in _UI_HINTS) or is_app_ctx
    ):
        add("list_online_devices", {"project_id": pid})

    if any(h in text for h in ("App套件", "移动端套件")) or (
        "套件" in text and is_app_ctx and not is_api_ctx
    ):
        add("list_app_suites", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in ("UI套件", "Web套件", "界面套件")) or (
        "套件" in text and any(h in text for h in _UI_HINTS) and not is_api_ctx
    ):
        add("list_ui_suites", {"project_id": pid, "page": 1, "size": 15})

    if any(h in text for h in ("Worker", "worker", "压测节点", "性能节点")):
        add("list_perf_workers", {"project_id": pid, "page": 1, "size": 15})

    if req_id and "list_requirement_cases" not in seen and not is_api_ctx:
        add(
            "list_requirement_cases",
            {"requirement_id": req_id, "project_id": pid, "page": 1, "size": 30},
        )

    if not planned:
        add("get_project_overview", {"project_id": pid})

    return planned


async def _select_tools_with_llm(
    client,
    config: AiConfig,
    *,
    user_message: str,
    project_id: int,
    project_label: str,
    history: list[dict[str, str]],
    page_context: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]] | None:
    history_lines = ""
    for item in (history or [])[-2:]:
        if isinstance(item, dict):
            history_lines += f"\n[{item.get('role', 'user')}] {item.get('content', '')}"

    page_hint = _format_page_context_hint(page_context)
    user_content = (
        f"当前项目：{project_label}（project_id={project_id}）\n"
        f"{page_hint}"
        f"{history_lines}\n\n用户问题：{user_message}\n"
        "请选择需要调用的工具。"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": TOOL_SELECT_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=get_tool_selection_schemas(),
                tool_choice="auto",
                temperature=0.1,
                max_tokens=800,
                stream=False,
            ),
            timeout=TOOL_SELECT_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("[assistant] LLM tool select failed: %s", exc)
        return None

    msg = resp.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []
    if not tool_calls:
        return None

    planned: list[tuple[str, dict[str, Any]]] = []
    for call in tool_calls[:4]:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if isinstance(args, dict):
            planned.append((name, args))
    return planned or None


async def _fetch_tools(
    ctx: McpAuthContext,
    planned: list[tuple[str, dict[str, Any]]],
    default_project_id: int | None,
) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    async def _one(name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        data = await invoke_assistant_tool(ctx, name, args, default_project_id=default_project_id)
        return name, data

    pairs = await asyncio.gather(*[_one(n, a) for n, a in planned])
    payload: dict[str, Any] = {}
    used: list[str] = []
    pending_confirm: dict[str, Any] | None = None
    for name, data in pairs:
        used.append(name)
        payload[name] = data
        if not pending_confirm and isinstance(data, dict) and not data.get("error"):
            pending_confirm = extract_pending_confirm(name, data)
    return payload, used, pending_confirm


def _summarize_tool_errors(tools_payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    hints: list[str] = []
    for name, data in tools_payload.items():
        if not isinstance(data, dict) or not data.get("error"):
            continue
        if data.get("permission_denied"):
            hint = data.get("user_hint") or data.get("error")
            if hint and hint not in hints:
                hints.append(str(hint))
            labels = data.get("permission_labels") or data.get("required_permissions") or []
            if labels:
                lines.append(f"{name}：权限不足（{'、'.join(str(x) for x in labels)}）")
            else:
                lines.append(f"{name}：{data.get('error')}")
        else:
            lines.append(f"{name}：{data.get('error')}")
    if hints:
        lines.append("")
        lines.extend(hints)
    return lines


def _build_all_tools_failed_content(tools_payload: dict[str, Any]) -> str:
    lines = _summarize_tool_errors(tools_payload)
    if not lines:
        return "查询失败，请稍后重试。"
    permission_only = all(
        isinstance(v, dict) and v.get("permission_denied")
        for v in tools_payload.values()
        if isinstance(v, dict) and v.get("error")
    )
    prefix = "无法查询平台数据（权限不足）：" if permission_only else "查询失败："
    return prefix + "\n".join(lines)


async def _llm_answer(
    client,
    config: AiConfig,
    *,
    username: str,
    project_label: str,
    user_message: str,
    history: list[dict[str, str]],
    tools_payload: dict[str, Any],
    start: float,
    pending_confirm: dict[str, Any] | None = None,
    page_context: dict[str, Any] | None = None,
    execution_capability_inquiry: bool = False,
) -> tuple[str, int]:
    if time.monotonic() - start > ASSISTANT_MAX_SECONDS:
        raise TimeoutError(f"助手响应超时（超过 {ASSISTANT_MAX_SECONDS} 秒）")

    history_lines = ""
    for item in (history or [])[-4:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        history_lines += f"\n[{role}] {item.get('content', '')}"

    confirm_hint = ""
    if pending_confirm:
        confirm_hint = (
            f"\n\n待用户确认的操作（pending_confirm）：\n"
            f"{json.dumps(pending_confirm.get('impact') or {}, ensure_ascii=False, default=str)}"
        )

    capability_hint = _execution_capability_answer_hint() if execution_capability_inquiry else ""

    user_content = (
        f"用户：{username}\n当前项目：{project_label}\n"
        f"{_format_page_context_hint(page_context)}"
        f"平台查询结果（JSON，按工具名分组）：\n"
        f"{truncate_tool_result(compact_tools_payload(tools_payload))}\n"
        f"{history_lines}\n\n用户问题：{user_message}\n"
        f"{confirm_hint}{capability_hint}\n请综合以上数据用中文回答。"
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    temperature = min(config.temperature, 0.5)
    max_tokens = min(config.max_tokens, 4096)

    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        ),
        timeout=LLM_CALL_TIMEOUT,
    )
    tokens = resp.usage.total_tokens if resp.usage else 0
    content = (resp.choices[0].message.content or "").strip()
    return content or "（模型未返回内容）", tokens


def _message_to_session(role: str, content: str, **extra: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": role, "content": content}
    msg.update(extra)
    return msg


async def run_assistant_chat(
    *,
    ctx: McpAuthContext,
    user_message: str,
    history: list[dict[str, str]],
    project_id: int | None,
    ai_config_id: int | None = None,
    session_id: int | None = None,
    use_server_history: bool = True,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """一次性返回完整回答：LLM/关键词选工具 → 并行调用 → 单次 LLM 整理。"""
    start = time.monotonic()
    user_message = (user_message or "").strip()
    if not user_message:
        raise ValueError("消息不能为空")

    try:
        config = await resolve_config_for_scene("platform_assistant", ai_config_id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        content = detail
        sid = await save_session_messages(
            ctx.user_id,
            project_id,
            [_message_to_session("user", user_message), _message_to_session("assistant", content)],
            session_id=session_id,
            title_hint=user_message,
        )
        return {
            "content": content,
            "tools_used": [],
            "tokens_used": 0,
            "model": "",
            "session_id": sid,
        }
    except Exception as exc:
        raise ValueError(f"无法加载 LLM 配置：{exc}") from exc

    resolved_pid, project_label = await resolve_project_context(project_id)
    project_name = project_label.split(" (id=")[0] if resolved_pid else ""

    chat_history = history
    active_session_id = session_id
    if use_server_history and ctx.user_id:
        stored_sid, stored_msgs = await load_session_messages(
            ctx.user_id, resolved_pid, session_id=active_session_id
        )
        if stored_msgs:
            chat_history = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in stored_msgs
                if isinstance(m, dict)
            ]
        if stored_sid:
            active_session_id = stored_sid

    if not resolved_pid:
        content = "请先在页面顶部选择一个项目，或在问题中说明 project_id。"
        sid = await save_session_messages(
            ctx.user_id,
            resolved_pid,
            [_message_to_session("user", user_message), _message_to_session("assistant", content)],
            session_id=active_session_id,
            title_hint=user_message,
        )
        return {
            "content": content,
            "tools_used": [],
            "tokens_used": 0,
            "model": config.model,
            "session_id": sid,
        }

    api_key = decrypt_value(config.api_key)
    llm = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=max(config.timeout, LLM_CALL_TIMEOUT),
    )

    is_exec_capability = _is_execution_capability_inquiry(user_message)

    if is_exec_capability:
        planned = _plan_tools_for_execution_capability(user_message, resolved_pid)
    else:
        context_planned = _plan_tools_from_page_context(page_context, resolved_pid) if resolved_pid else []

        planned = await _select_tools_with_llm(
            llm.client,
            config,
            user_message=user_message,
            project_id=resolved_pid,
            project_label=project_label,
            history=chat_history,
            page_context=page_context,
        )
        if not planned:
            planned = _plan_tools(user_message, resolved_pid)
        planned = _merge_planned_tools(context_planned, planned)

    logger.info(
        "[assistant] planned_tools=%s project_id=%s page=%s",
        [p[0] for p in planned],
        resolved_pid,
        (page_context or {}).get("page"),
    )

    tools_payload, tools_used, pending_confirm = await _fetch_tools(ctx, planned, resolved_pid)
    errors = [k for k, v in tools_payload.items() if isinstance(v, dict) and v.get("error")]
    if errors and len(errors) == len(tools_used):
        content = _build_all_tools_failed_content(tools_payload)
        sid = await save_session_messages(
            ctx.user_id,
            resolved_pid,
            chat_history
            + [_message_to_session("user", user_message), _message_to_session("assistant", content, tools=tools_used)],
            session_id=active_session_id,
            title_hint=user_message,
        )
        return {
            "content": content,
            "tools_used": tools_used,
            "tokens_used": 0,
            "model": config.model,
            "session_id": sid,
        }

    try:
        content, tokens = await _llm_answer(
            llm.client,
            config,
            username=ctx.username,
            project_label=project_label,
            user_message=user_message,
            history=chat_history,
            tools_payload=tools_payload,
            start=start,
            pending_confirm=pending_confirm,
            page_context=page_context,
            execution_capability_inquiry=is_exec_capability,
        )
    except asyncio.TimeoutError as exc:
        await record_ai_usage(
            scene="platform_assistant",
            user_id=ctx.user_id,
            username=ctx.username,
            project_id=resolved_pid,
            project_name=project_name,
            ai_config_id=config.id,
            model=config.model,
            provider=config.provider,
            tokens_used=0,
            duration_ms=int((time.monotonic() - start) * 1000),
            status="failed",
            input_summary=user_message,
            output_summary="LLM 调用超时",
            extra={"tools_used": tools_used},
        )
        raise TimeoutError("LLM 调用超时，请稍后重试") from exc

    duration_ms = int((time.monotonic() - start) * 1000)
    await record_ai_usage(
        scene="platform_assistant",
        user_id=ctx.user_id,
        username=ctx.username,
        project_id=resolved_pid,
        project_name=project_name,
        ai_config_id=config.id,
        model=config.model,
        provider=config.provider,
        tokens_used=tokens,
        duration_ms=duration_ms,
        status="success",
        input_summary=user_message,
        output_summary=content,
        extra={"tools_used": tools_used, "has_pending_confirm": bool(pending_confirm), "page": (page_context or {}).get("page")},
    )

    assistant_msg = _message_to_session("assistant", content, tools=tools_used)
    if pending_confirm:
        assistant_msg["pending_confirm"] = pending_confirm

    sid = await save_session_messages(
        ctx.user_id,
        resolved_pid,
        chat_history + [_message_to_session("user", user_message), assistant_msg],
        session_id=active_session_id,
        title_hint=user_message,
    )

    result: dict[str, Any] = {
        "content": content,
        "tools_used": tools_used,
        "tokens_used": tokens,
        "model": config.model,
        "duration_ms": duration_ms,
        "session_id": sid,
    }
    if pending_confirm:
        result["pending_confirm"] = pending_confirm
    return result


async def run_assistant_confirm(
    *,
    ctx: McpAuthContext,
    action: str,
    confirm_token: str,
    confirm_args: dict[str, Any],
    project_id: int | None,
    session_id: int | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    resolved_pid, project_label = await resolve_project_context(project_id)
    project_name = project_label.split(" (id=")[0] if resolved_pid else ""

    try:
        result = await invoke_confirm_tool(ctx, action, confirm_token, confirm_args or {})
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    content = f"操作已执行。\n\n```json\n{truncate_tool_result(result)}\n```"
    duration_ms = int((time.monotonic() - start) * 1000)

    await record_ai_usage(
        scene="platform_assistant",
        user_id=ctx.user_id,
        username=ctx.username,
        project_id=resolved_pid,
        project_name=project_name,
        ai_config_id=None,
        model="",
        provider="",
        tokens_used=0,
        duration_ms=duration_ms,
        status="success",
        input_summary=f"confirm:{action}",
        output_summary=truncate_tool_result(result)[:500],
        extra={"action": action, "confirm_args": confirm_args},
    )

    _, stored_msgs = await load_session_messages(ctx.user_id, resolved_pid, session_id=session_id)
    confirm_msg = _message_to_session(
        "assistant",
        content,
        tools=[f"confirm:{action}"],
        confirm_result={"action": action, "result": result},
    )
    sid = await save_session_messages(
        ctx.user_id,
        resolved_pid,
        stored_msgs + [confirm_msg],
        session_id=session_id,
    )

    execution_watch = schedule_execution_watch(
        user_id=ctx.user_id,
        project_id=resolved_pid,
        session_id=sid,
        action=action,
        result=result if isinstance(result, dict) else {},
    )

    return {
        "content": content,
        "result": result,
        "action": action,
        "duration_ms": duration_ms,
        "session_id": sid,
        "execution_watch": execution_watch,
    }
