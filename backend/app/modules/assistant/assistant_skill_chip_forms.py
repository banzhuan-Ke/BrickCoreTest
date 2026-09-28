"""小测 Skill Chip 直出 AskUser 表单（跳过空转模型轮）。

生成类 Chip 点击后由本模块构造 pending_ask_user（含 select 选项），
写入会话后再由现有 /ask-user/answer 继续对话。
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.platform.datetime_utils import now_app

# 与 brickcore_assist.orchestrator.cards.ASK_USER_OPTION_LIMIT 对齐
_OPTION_LIMIT = 100

# chip_key → 表单规格（字段在运行时填充 options）
CHIP_DIRECT_FORM_KEYS = frozenset(
    {
        "skill_ui_nl",
        "skill_req_test_points",
        "skill_api_to_cases",
        "skill_tp_to_cases",
        "skill_mock_gen",
        "skill_perf_nl",
        "skill_bl_to_ui",
        "skill_ui_failure",
        "skill_report_narr",
        "skill_qa_eval",
        "skill_curl_to_cases",
        "skill_knowledge_qa",
        "skill_platform_howto",
        "skill_locator",
        "skill_fc_to_ui",
        "skill_fc_to_app",
        "skill_suite_to_perf",
        "skill_failure_to_defect",
        "skill_df_nl_sql",
    }
)

# 与 SKILL_CHIPS.skill_code / registry 对齐；answer 后服务端直跑 Skill，避免长文截断/再 ask
CHIP_KEY_TO_SKILL_CODE: dict[str, str] = {
    "skill_ui_nl": "ui_steps_from_nl",
    "skill_req_test_points": "requirement_to_test_points",
    "skill_api_to_cases": "api_definition_to_cases",
    "skill_tp_to_cases": "test_points_to_functional_cases",
    "skill_mock_gen": "mock_response_generate",
    "skill_perf_nl": "perf_scene_from_nl",
    "skill_bl_to_ui": "browser_lab_to_ui_case",
    "skill_ui_failure": "ui_failure_analysis",
    "skill_report_narr": "report_narrative",
    "skill_qa_eval": "qa_eval_assist",
    "skill_curl_to_cases": "curl_to_cases",
    "skill_knowledge_qa": "knowledge_qa",
    "skill_platform_howto": "platform_how_to",
    "skill_locator": "ui_locator_suggest",
    "skill_fc_to_ui": "functional_case_to_ui_case",
    "skill_fc_to_app": "functional_case_to_app_case",
    "skill_suite_to_perf": "perf_journey_from_suite",
    "skill_failure_to_defect": "failure_to_defect_draft",
    "skill_df_nl_sql": "nl_to_sql_template",
}

# Chip 提交后一律服务端 run_skill（不经 LLM 转述参数）
CHIP_DIRECT_RUN_SKILL_CODES = frozenset(CHIP_KEY_TO_SKILL_CODE.values())


def chip_supports_direct_form(chip_key: str | None) -> bool:
    return (chip_key or "").strip() in CHIP_DIRECT_FORM_KEYS


def skill_code_for_chip(chip_key: str | None) -> str:
    return CHIP_KEY_TO_SKILL_CODE.get((chip_key or "").strip(), "")


def _ask_id() -> str:
    from uuid import uuid4

    return f"ask_{uuid4().hex[:16]}"


async def _web_device_options() -> list[dict[str, Any]]:
    from app.models.sys import Device

    rows = await Device.filter(status="在线", is_del=False).order_by("-update_time")
    opts: list[dict[str, Any]] = []
    for d in rows:
        engines = d.runner_engine_types or []
        if isinstance(engines, str):
            engines = [engines]
        eng = [str(x).lower() for x in engines]
        # 未声明能力视为通用；仅 App/Perf 等非 Web 能力的跳过
        if eng and not any(x in ("web", "all", "ui") for x in eng):
            continue
        name = (d.name or d.hostname or str(d.id)).strip()
        ip = (d.ip or "").strip()
        label = f"{name}" + (f" ({ip})" if ip else "") + f" · {d.id}"
        opts.append({"value": d.id, "label": label[:220]})
        if len(opts) >= _OPTION_LIMIT:
            break
    return opts


async def _requirement_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.ai import AiRequirement

    rows = await AiRequirement.filter(project_id=int(project_id), is_del=False).order_by("-id").limit(
        _OPTION_LIMIT
    )
    opts = []
    for r in rows:
        name = (r.name or f"需求{r.id}").strip()
        opts.append({"value": int(r.id), "label": f"{r.id} - {name}"[:220]})
    return opts


async def _api_definition_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.http import ApiDefinition

    rows = (
        await ApiDefinition.filter(project_id=int(project_id), is_del=False)
        .order_by("-id")
        .limit(_OPTION_LIMIT)
    )
    opts = []
    for r in rows:
        name = (r.name or "").strip() or f"接口{r.id}"
        method = (r.method or "").strip()
        path = (r.path or "").strip()
        route = f"{method} {path}".strip()
        suffix = f" · {route}" if route else ""
        opts.append({"value": int(r.id), "label": f"{r.id} - {name}{suffix}"[:220]})
    return opts


async def _datasource_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.http import EnvDatasource
    from app.models.sys import Environment

    rows = (
        await EnvDatasource.filter(project_id=int(project_id), is_del=False, is_enabled=True)
        .order_by("-id")
        .limit(_OPTION_LIMIT)
    )
    opts = []
    for r in rows:
        env = await Environment.get_or_none(id=r.environment_id)
        env_name = env.name if env else ""
        db_type = (r.db_type or "mysql").lower()
        label = f"{r.id} - {r.name} [{db_type}]"
        if env_name:
            label += f" · {env_name}"
        opts.append({"value": int(r.id), "label": label[:220]})
    return opts


async def _browser_lab_task_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.ai import BrowserLabTask

    rows = (
        await BrowserLabTask.filter(project_id=int(project_id)).order_by("-id").limit(_OPTION_LIMIT)
    )
    opts = []
    for r in rows:
        title = (r.case_name or (r.task_text or "")[:40] or f"任务{r.id}").strip()
        status = str(r.status or "").strip()
        suffix = f" · {status}" if status else ""
        opts.append({"value": int(r.id), "label": f"{r.id} - {title}{suffix}"[:220]})
    return opts


async def _qa_eval_set_options(project_id: int) -> list[dict[str, Any]]:
    # 开源发行版已移除问答评测模型
    _ = project_id
    return []


async def _functional_case_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.ai import AiFunctionalCase

    rows = (
        await AiFunctionalCase.filter(project_id=int(project_id), is_del=False)
        .order_by("-id")
        .limit(_OPTION_LIMIT)
    )
    opts = []
    for r in rows:
        title = (r.title or f"功能用例{r.id}").strip()
        opts.append({"value": int(r.id), "label": f"{r.id} - {title}"[:220]})
    return opts


async def _api_suite_options(project_id: int) -> list[dict[str, Any]]:
    from app.models.http import ApiTestSuite

    rows = (
        await ApiTestSuite.filter(project_id=int(project_id), is_del=False)
        .order_by("-id")
        .limit(_OPTION_LIMIT)
    )
    opts = []
    for r in rows:
        name = (r.name or f"套件{r.id}").strip()
        opts.append({"value": int(r.id), "label": f"{r.id} - {name}"[:220]})
    return opts


_FAILURE_TYPE_LABEL = {
    "api": "接口",
    "ui": "Web UI",
    "app": "App",
    "perf": "压测",
}

_TIME_RANGE_HOURS = {"1d": 24, "7d": 168, "30d": 720}


async def _failure_record_options(project_id: int) -> list[dict[str, Any]]:
    """近 30 天失败记录下拉；前端按失败域/时间窗再过滤。"""
    import time as _time

    from app.core.shared.report_summary_context import fetch_recent_failures

    items = await fetch_recent_failures(
        int(project_id),
        limit=min(_OPTION_LIMIT, 40),
        since_hours=720,
    )
    now = _time.time()
    opts: list[dict[str, Any]] = []
    for it in items:
        tt = str(it.get("target_type") or "").lower()
        tid = it.get("target_id")
        if not tt or tid is None:
            continue
        label_type = _FAILURE_TYPE_LABEL.get(tt, tt)
        name = str(it.get("case_name") or "").strip() or f"记录#{tid}"
        run_at = str(it.get("run_at") or "").strip()
        hours_ago = None
        if run_at:
            try:
                from datetime import datetime

                dt = datetime.strptime(run_at, "%Y-%m-%d %H:%M:%S")
                hours_ago = max(0.0, (now - dt.timestamp()) / 3600.0)
            except Exception:
                hours_ago = None
        suffix = f" · {run_at}" if run_at else ""
        opts.append(
            {
                "value": f"{tt}:{int(tid)}",
                "label": f"[{label_type}] {name} · #{tid}{suffix}"[:220],
                "meta": {
                    "target_type": tt,
                    "hours_ago": hours_ago,
                    "run_at": run_at,
                },
            }
        )
    return opts


async def _report_record_options(project_id: int) -> list[dict[str, Any]]:
    """报告叙事用：各类型近期执行记录（前端按 report_type 过滤）。"""
    from app.models.app import AppPlanExecution, AppSuiteExecution
    from app.models.http import ApiPlanRunRecord, ApiSuiteRunRecord
    from app.models.perf import PerfRecord
    from app.models.ui import UiPlanExecution, UiSuiteExecution

    opts: list[dict[str, Any]] = []
    per = min(30, max(8, _OPTION_LIMIT // 7))
    pid = int(project_id)

    def _ts(dt) -> str:
        return dt.strftime("%m-%d %H:%M") if dt else ""

    def _push(rtype: str, prefix: str, rid: int, name: str, ts: str = ""):
        opts.append(
            {
                "value": f"{rtype}:{rid}",
                "label": f"[{prefix}] #{rid} {(name or '').strip()}{(' · ' + ts) if ts else ''}"[:220],
                "meta": {"report_type": rtype, "record_id": rid},
            }
        )

    for r in await ApiSuiteRunRecord.filter(project_id=pid).prefetch_related("suite").order_by("-id").limit(per):
        suite = r.suite
        _push("api_suite", "接口套件", int(r.id), getattr(suite, "name", None) or "", _ts(r.start_time))

    for r in await ApiPlanRunRecord.filter(project_id=pid).prefetch_related("plan").order_by("-id").limit(per):
        plan = r.plan
        _push("api_plan", "接口计划", int(r.id), getattr(plan, "name", None) or "", _ts(r.start_time))

    for r in await UiPlanExecution.filter(project_id=pid, is_del=False).prefetch_related("task").order_by("-id").limit(per):
        task = r.task
        _push("ui_task", "Web计划", int(r.id), getattr(task, "name", None) or "", _ts(r.start_time))

    ui_suite_n = 0
    for r in (
        await UiSuiteExecution.filter(is_del=False)
        .prefetch_related("suite")
        .order_by("-id")
        .limit(per * 4)
    ):
        suite = r.suite
        if not suite or int(getattr(suite, "project_id", 0) or 0) != pid:
            continue
        _push("ui_suite", "Web套件", int(r.id), getattr(suite, "name", None) or "", _ts(r.start_time))
        ui_suite_n += 1
        if ui_suite_n >= per:
            break

    for r in await AppPlanExecution.filter(project_id=pid, is_del=False).prefetch_related("plan").order_by("-id").limit(per):
        plan = r.plan
        _push("app_plan", "App计划", int(r.id), getattr(plan, "name", None) or "", _ts(r.start_time))

    app_suite_n = 0
    for r in (
        await AppSuiteExecution.filter(is_del=False)
        .prefetch_related("suite")
        .order_by("-id")
        .limit(per * 4)
    ):
        suite = r.suite
        if not suite or int(getattr(suite, "project_id", 0) or 0) != pid:
            continue
        _push("app_suite", "App套件", int(r.id), getattr(suite, "name", None) or "", _ts(r.start_time))
        app_suite_n += 1
        if app_suite_n >= per:
            break

    for pr in await PerfRecord.filter(project_id=pid).prefetch_related("scene").order_by("-id").limit(per):
        scene = pr.scene
        _push(
            "perf",
            "压测",
            int(pr.id),
            getattr(scene, "name", None) or "",
            _ts(pr.started_at),
        )

    return opts[:_OPTION_LIMIT]


async def build_direct_ask_card(chip_key: str, *, project_id: int) -> dict[str, Any]:
    """构造 AskUser 卡片 dict（含 type/ask_id/fields）。"""
    key = (chip_key or "").strip()
    if key not in CHIP_DIRECT_FORM_KEYS:
        raise ValueError(f"Chip 不支持直出表单: {key}")

    ask_id = _ask_id()
    fields: list[dict[str, Any]] = []
    question = "请补充必要信息"
    reason = "点击技能快捷入口后直接收集参数，避免空转调用模型。"

    if key == "skill_ui_nl":
        question = "请填写自然语言描述、起始 URL 与在线 Web Runner"
        reason = "用于生成 Web UI 步骤并预览确认卡"
        device_opts = await _web_device_options()
        fields = [
            {
                "name": "description",
                "label": "自然语言步骤描述",
                "field_type": "textarea",
                "required": True,
                "placeholder": "例如：打开登录页，输入账号密码并点击登录",
            },
            {
                "name": "page_url",
                "label": "起始页面 URL",
                "field_type": "text",
                "required": True,
                "placeholder": "https://example.com/login",
            },
            {
                "name": "device_id",
                "label": "在线 Web UI Runner",
                "field_type": "select",
                "required": True,
                "options": device_opts,
                "placeholder": "请选择在线设备" if device_opts else "暂无在线 Web Runner",
            },
        ]
    elif key == "skill_req_test_points":
        question = "选择已有需求，或粘贴需求正文生成测试点"
        reason = "粘贴模式确认后才创建需求文档；大文件上传请走需求工作台"
        opts = await _requirement_options(project_id)
        fields = [
            {
                "name": "input_mode",
                "label": "输入方式",
                "field_type": "select",
                "required": True,
                "default": "existing",
                "options": [
                    {"value": "existing", "label": "选择已有需求"},
                    {"value": "paste", "label": "粘贴需求正文"},
                ],
            },
            {
                "name": "requirement_id",
                "label": "需求文档（选已有时必填）",
                "field_type": "select",
                "required": False,
                "options": opts,
                "placeholder": "请选择需求" if opts else "当前项目暂无需求文档",
            },
            {
                "name": "requirement_name",
                "label": "需求名称（粘贴时可选）",
                "field_type": "text",
                "required": False,
                "placeholder": "默认取正文首行作标题",
            },
            {
                "name": "content",
                "label": "需求正文（粘贴时必填）",
                "field_type": "textarea",
                "required": False,
                "placeholder": "粘贴 PRD / 用户故事 / 变更说明…",
                "max_length": 200000,
            },
        ]
    elif key == "skill_tp_to_cases":
        question = "请选择需求文档（将基于其测试点生成功能用例）"
        opts = await _requirement_options(project_id)
        fields = [
            {
                "name": "requirement_id",
                "label": "需求文档",
                "field_type": "select",
                "required": True,
                "options": opts,
                "placeholder": "请选择需求" if opts else "当前项目暂无需求文档",
            },
        ]
    elif key == "skill_api_to_cases":
        question = "请选择接口定义以生成测试用例"
        opts = await _api_definition_options(project_id)
        fields = [
            {
                "name": "api_definition_id",
                "label": "接口定义",
                "field_type": "select",
                "required": True,
                "options": opts,
                "placeholder": "请选择接口" if opts else "当前项目暂无接口定义",
            },
        ]
    elif key == "skill_mock_gen":
        question = "请填写要生成 Mock 的方法与路径"
        fields = [
            {
                "name": "method",
                "label": "HTTP 方法",
                "field_type": "select",
                "required": True,
                "default": "GET",
                "options": [
                    {"value": m, "label": m}
                    for m in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
                ],
            },
            {
                "name": "path",
                "label": "接口路径",
                "field_type": "text",
                "required": True,
                "placeholder": "/api/login",
            },
        ]
    elif key == "skill_df_nl_sql":
        question = "请选择数据源并描述要生成的 SQL/命令"
        reason = "将生成模板与断言草稿，确认后写入数据工厂并可打开控制台试跑"
        opts = await _datasource_options(project_id)
        fields = [
            {
                "name": "datasource_id",
                "label": "数据源",
                "field_type": "select",
                "required": True,
                "options": opts,
                "placeholder": "请选择数据源" if opts else "当前项目暂无数据源，请先到数据工厂配置",
            },
            {
                "name": "prompt",
                "label": "自然语言需求",
                "field_type": "textarea",
                "required": True,
                "placeholder": "例如：查 orders 表近 7 天失败订单，按 status 分组",
            },
            {
                "name": "schema_hint",
                "label": "表结构/补充（可选）",
                "field_type": "textarea",
                "required": False,
                "placeholder": "可选：粘贴 CREATE TABLE 或字段说明",
            },
            {
                "name": "template_type",
                "label": "模板类型",
                "field_type": "select",
                "required": False,
                "default": "query",
                "options": [
                    {"value": "query", "label": "query 查询"},
                    {"value": "setup", "label": "setup 造数"},
                    {"value": "teardown", "label": "teardown 清数"},
                ],
            },
        ]
    elif key == "skill_perf_nl":
        question = "请用一句话描述压测场景"
        reason = "将生成压测场景草稿并预览确认"
        fields = [
            {
                "name": "prompt",
                "label": "压测描述",
                "field_type": "textarea",
                "required": True,
                "placeholder": "例如：对登录接口压 50 并发 3 分钟，关注 P95",
            },
        ]
    elif key == "skill_bl_to_ui":
        question = "请选择智能浏览器任务以转为 UI 用例"
        opts = await _browser_lab_task_options(project_id)
        fields = [
            {
                "name": "task_id",
                "label": "智能浏览器任务",
                "field_type": "select",
                "required": True,
                "options": opts,
                "placeholder": "请选择任务" if opts else "暂无浏览器任务，可先派发探索",
            },
        ]
    elif key == "skill_ui_failure":
        question = "可选失败域与具体记录；都不选则分析近期失败"
        reason = "支持接口 / Web UI / App / 压测；可用时间范围筛选下拉列表"
        fail_opts = await _failure_record_options(project_id)
        fields = [
            {
                "name": "time_range",
                "label": "时间范围",
                "field_type": "select",
                "required": False,
                "default": "7d",
                "options": [
                    {"value": "1d", "label": "近 24 小时"},
                    {"value": "7d", "label": "近 7 天"},
                    {"value": "30d", "label": "近 30 天"},
                ],
            },
            {
                "name": "target_type",
                "label": "失败域（可选）",
                "field_type": "select",
                "required": False,
                "options": [
                    {"value": "ui", "label": "Web UI"},
                    {"value": "api", "label": "接口"},
                    {"value": "app", "label": "App"},
                    {"value": "perf", "label": "性能测试"},
                ],
                "placeholder": "不选则包含全部域",
            },
            {
                "name": "failure_ref",
                "label": "失败记录（可选）",
                "field_type": "select",
                "required": False,
                "options": fail_opts,
                "filter_by": ["target_type", "time_range"],
                "placeholder": "不选则分析该范围近期失败"
                if fail_opts
                else "暂无失败记录，可留空分析（若仍无数据将提示）",
            },
        ]
    elif key == "skill_report_narr":
        question = "请选择报告类型与执行记录"
        report_opts = await _report_record_options(project_id)
        fields = [
            {
                "name": "report_type",
                "label": "报告类型",
                "field_type": "select",
                "required": True,
                "options": [
                    {"value": "api_plan", "label": "接口计划"},
                    {"value": "api_suite", "label": "接口套件"},
                    {"value": "ui_task", "label": "Web UI 计划"},
                    {"value": "ui_suite", "label": "Web UI 套件"},
                    {"value": "app_plan", "label": "App 计划"},
                    {"value": "app_suite", "label": "App 套件"},
                    {"value": "perf", "label": "压测"},
                ],
            },
            {
                "name": "report_ref",
                "label": "执行记录",
                "field_type": "select",
                "required": True,
                "options": report_opts,
                "filter_by": ["report_type"],
                "placeholder": "请先选报告类型，再选记录"
                if report_opts
                else "暂无执行记录",
            },
        ]
    elif key == "skill_qa_eval":
        question = "请选择评测集"
        opts = await _qa_eval_set_options(project_id)
        fields = [
            {
                "name": "set_id",
                "label": "评测集",
                "field_type": "select",
                "required": True,
                "options": opts,
                "placeholder": "请选择评测集" if opts else "当前项目暂无评测集",
            },
        ]
    elif key == "skill_curl_to_cases":
        question = "请粘贴 curl（可选附带响应样例）以生成接口用例"
        reason = "确认后将创建接口定义并导入用例"
        fields = [
            {
                "name": "curl",
                "label": "curl 命令",
                "field_type": "textarea",
                "required": True,
                "placeholder": "curl -X POST 'https://...' -H '...' -d '{...}'",
                "max_length": 12000,
            },
            {
                "name": "response_sample",
                "label": "响应样例（可选）",
                "field_type": "textarea",
                "required": False,
                "placeholder": "可选：粘贴 JSON/文本响应，便于生成更准的断言",
                "max_length": 8000,
            },
        ]
    elif key == "skill_knowledge_qa":
        question = "请输入要对资料库提出的问题"
        reason = "将检索项目迭代测试资料库并生成答案"
        fields = [
            {
                "name": "query",
                "label": "问题",
                "field_type": "textarea",
                "required": True,
                "placeholder": "例如：登录失败常见原因有哪些？",
                "max_length": 4000,
            },
            {
                "name": "mode",
                "label": "模式",
                "field_type": "select",
                "required": False,
                "default": "smart",
                "options": [
                    {"value": "smart", "label": "智能生成答案"},
                    {"value": "retrieve", "label": "仅检索片段"},
                ],
            },
        ]
    elif key == "skill_platform_howto":
        question = "想了解平台哪块功能或哪个技能怎么用？"
        reason = "将检索帮助中心与 Skill 清单，给出菜单路径与跳转"
        fields = [
            {
                "name": "query",
                "label": "问题",
                "field_type": "textarea",
                "required": True,
                "placeholder": "例如：失败分析怎么用？数据工厂在哪？有哪些技能？",
                "max_length": 2000,
            },
        ]
    elif key == "skill_locator":
        question = "请粘贴页面元素信息以获取定位建议"
        reason = "只读建议，不直接改用例；可将候选填入 Web 步骤"
        fields = [
            {
                "name": "raw_element",
                "label": "元素 outerHTML / 属性",
                "field_type": "textarea",
                "required": True,
                "placeholder": "<button data-testid=\"login\">登录</button>",
                "max_length": 20000,
            },
            {
                "name": "intent",
                "label": "操作意图（可选）",
                "field_type": "text",
                "required": False,
                "placeholder": "例如：点击登录",
            },
        ]
    elif key in ("skill_fc_to_ui", "skill_fc_to_app"):
        to_app = key == "skill_fc_to_app"
        question = (
            "请选择功能用例以转为 App 自动化用例"
            if to_app
            else "请选择功能用例以转为 Web UI 用例"
        )
        reason = "确认后将导入用例库并打开编辑页"
        fc_opts = await _functional_case_options(project_id)
        fields = [
            {
                "name": "functional_case_id",
                "label": "功能用例",
                "field_type": "select",
                "required": True,
                "options": fc_opts,
                "placeholder": "请选择功能用例" if fc_opts else "当前项目暂无功能用例",
            },
        ]
        if to_app:
            fields.append(
                {
                    "name": "driver_mode",
                    "label": "驱动模式",
                    "field_type": "select",
                    "required": False,
                    "default": "hybrid",
                    "options": [
                        {"value": "hybrid", "label": "混合（推荐）"},
                        {"value": "native", "label": "原生控件"},
                        {"value": "vision", "label": "视觉"},
                    ],
                }
            )
    elif key == "skill_suite_to_perf":
        question = "请选择接口套件以生成压测 journey 场景"
        reason = "确认后将创建压测场景并打开编辑页"
        suite_opts = await _api_suite_options(project_id)
        fields = [
            {
                "name": "suite_id",
                "label": "接口套件",
                "field_type": "select",
                "required": True,
                "options": suite_opts,
                "placeholder": "请选择套件" if suite_opts else "当前项目暂无接口套件",
            },
            {
                "name": "layout",
                "label": "阶段布局",
                "field_type": "select",
                "required": False,
                "default": "single_phase",
                "options": [
                    {"value": "single_phase", "label": "单阶段（整链）"},
                    {"value": "per_case_phase", "label": "按用例分阶段"},
                ],
            },
        ]
    elif key == "skill_failure_to_defect":
        question = "请选择失败记录以生成 TM 缺陷草稿"
        reason = "将可选地先做失败分析，预览缺陷字段后确认创建"
        fail_opts = [
            o
            for o in await _failure_record_options(project_id)
            if str((o.get("meta") or {}).get("target_type") or "").lower() in ("api", "ui", "app")
        ]
        fields = [
            {
                "name": "time_range",
                "label": "时间范围",
                "field_type": "select",
                "required": False,
                "default": "7d",
                "options": [
                    {"value": "1d", "label": "近 24 小时"},
                    {"value": "7d", "label": "近 7 天"},
                    {"value": "30d", "label": "近 30 天"},
                ],
            },
            {
                "name": "target_type",
                "label": "失败域",
                "field_type": "select",
                "required": False,
                "options": [
                    {"value": "api", "label": "接口"},
                    {"value": "ui", "label": "Web UI"},
                    {"value": "app", "label": "App"},
                ],
                "placeholder": "可选，用于筛选下拉",
            },
            {
                "name": "failure_ref",
                "label": "失败记录",
                "field_type": "select",
                "required": True,
                "options": fail_opts,
                "filter_by": ["target_type", "time_range"],
                "placeholder": "请选择失败记录" if fail_opts else "暂无可用失败记录（不含压测）",
            },
            {
                "name": "severity",
                "label": "严重度",
                "field_type": "select",
                "required": False,
                "default": "major",
                "options": [
                    {"value": "blocker", "label": "阻塞"},
                    {"value": "critical", "label": "严重"},
                    {"value": "major", "label": "一般"},
                    {"value": "minor", "label": "轻微"},
                ],
            },
            {
                "name": "priority",
                "label": "优先级",
                "field_type": "select",
                "required": False,
                "default": "p2",
                "options": [
                    {"value": "p0", "label": "P0"},
                    {"value": "p1", "label": "P1"},
                    {"value": "p2", "label": "P2"},
                    {"value": "p3", "label": "P3"},
                ],
            },
        ]
    else:
        raise ValueError(f"未实现的 Chip 表单: {key}")

    # 规范化（与 build_ask_user_card 兼容；textarea 前端单独支持）
    clean_fields: list[dict[str, Any]] = []
    for raw in fields:
        ft = str(raw.get("field_type") or "text").lower()
        if ft not in ("text", "number", "select", "textarea"):
            ft = "text"
        item: dict[str, Any] = {
            "name": str(raw["name"])[:64],
            "label": str(raw.get("label") or raw["name"])[:80],
            "field_type": ft,
            "required": bool(raw.get("required", True)),
        }
        ph = str(raw.get("placeholder") or "").strip()
        if ph:
            item["placeholder"] = ph[:120]
        if "default" in raw and raw.get("default") is not None:
            item["default"] = raw.get("default")
        if raw.get("max_length") is not None:
            try:
                item["max_length"] = max(1, min(int(raw.get("max_length")), 500_000))
            except (TypeError, ValueError):
                pass
        # 级联筛选：失败记录 / 报告记录下拉依赖上游字段
        fb = raw.get("filter_by")
        if isinstance(fb, list) and fb:
            item["filter_by"] = [str(x)[:64] for x in fb if x][:8]
        elif isinstance(fb, str) and fb.strip():
            item["filter_by"] = [fb.strip()[:64]]
        opts = raw.get("options")
        if isinstance(opts, list) and ft == "select":
            cleaned_opts: list[dict[str, Any]] = []
            for o in opts:
                if not isinstance(o, dict) or o.get("value") is None:
                    continue
                opt_item: dict[str, Any] = {
                    "value": o.get("value"),
                    "label": str(o.get("label") or o.get("value"))[:220],
                }
                meta = o.get("meta")
                if isinstance(meta, dict) and meta:
                    # 仅保留前端过滤需要的短字段
                    safe_meta: dict[str, Any] = {}
                    for mk in (
                        "target_type",
                        "report_type",
                        "record_id",
                        "hours_ago",
                        "run_at",
                    ):
                        if mk in meta and meta[mk] is not None:
                            safe_meta[mk] = meta[mk]
                    if safe_meta:
                        opt_item["meta"] = safe_meta
                cleaned_opts.append(opt_item)
                if len(cleaned_opts) >= _OPTION_LIMIT:
                    break
            item["options"] = cleaned_opts
        clean_fields.append(item)

    return {
        "type": "ask_user",
        "ask_id": ask_id,
        "question": question[:500],
        "reason": reason[:300],
        "fields": clean_fields,
        "chip_key": key,
        "skill_code": skill_code_for_chip(key),
        "source": "skill_chip_direct",
    }


def chip_user_prompt_line(chip_key: str, chip_label: str | None = None) -> str:
    label = (chip_label or chip_key or "技能").strip()
    return f"【技能快捷入口】{label}（请根据我稍后补充的参数生成预览确认卡，不要再向我重复索要已提供的字段）"


_INT_ANSWER_KEYS = frozenset(
    {
        "requirement_id",
        "api_definition_id",
        "task_id",
        "record_id",
        "target_id",
        "set_id",
        "catalog_id",
        "count",
        "since_hours",
        "functional_case_id",
        "suite_id",
    }
)


def normalize_chip_answers_for_continue(
    skill_code: str, answers: dict[str, Any] | None
) -> dict[str, Any]:
    """续聊前规范化 Chip 答案：整型字段、失败分析成对参数、需求贴文模式。"""
    raw = answers if isinstance(answers, dict) else {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None or str(k) == "cancelled":
            continue
        if isinstance(v, str) and not v.strip():
            continue
        key = str(k)
        if key in _INT_ANSWER_KEYS:
            try:
                out[key] = int(str(v).strip())
            except (TypeError, ValueError):
                continue
        else:
            out[key] = v

    if skill_code == "ui_failure_analysis":
        # failure_ref=ui:123 → target_type + target_id；仅失败域也可（分析该域近期）
        ref = str(out.pop("failure_ref", "") or "").strip()
        if ref and ":" in ref:
            tt, tid_s = ref.split(":", 1)
            tt = tt.strip().lower()
            try:
                tid = int(tid_s.strip())
            except (TypeError, ValueError):
                tid = None
            if tt in ("api", "ui", "app", "perf") and tid is not None:
                out["target_type"] = tt
                out["target_id"] = tid
        tr = str(out.pop("time_range", "") or "7d").strip().lower()
        out["since_hours"] = int(_TIME_RANGE_HOURS.get(tr, 168))
        # 仅有 target_id 无 type → 丢弃半填；仅有 type → 保留
        has_type = bool(out.get("target_type"))
        has_id = out.get("target_id") is not None
        if has_id and not has_type:
            out.pop("target_id", None)

    if skill_code == "report_narrative":
        ref = str(out.pop("report_ref", "") or "").strip()
        if ref and ":" in ref:
            rtype, rid_s = ref.split(":", 1)
            rtype = rtype.strip()
            try:
                rid = int(rid_s.strip())
            except (TypeError, ValueError):
                rid = None
            if rtype and rid is not None:
                out["report_type"] = rtype
                out["record_id"] = rid
        # 兼容旧字段 record_id 数字
        if out.get("record_id") is not None and not out.get("report_type"):
            out.pop("record_id", None)

    if skill_code == "mock_response_generate":
        method = str(out.get("method") or "GET").strip().upper() or "GET"
        out["method"] = method
        path = str(out.get("path") or "").strip()
        if path and not path.startswith("/"):
            path = "/" + path
        if path:
            out["path"] = path

    if skill_code == "nl_to_sql_template":
        ds = out.get("datasource_id")
        try:
            out["datasource_id"] = int(ds) if ds is not None and str(ds).strip() != "" else None
        except (TypeError, ValueError):
            out["datasource_id"] = None
        prompt = str(out.get("prompt") or out.get("query") or "").strip()
        if prompt:
            out["prompt"] = prompt
        hint = str(out.get("schema_hint") or "").strip()
        if hint:
            out["schema_hint"] = hint
        else:
            out.pop("schema_hint", None)
        ttype = str(out.get("template_type") or "query").strip().lower()
        out["template_type"] = ttype if ttype in ("query", "setup", "teardown") else "query"

    if skill_code == "requirement_to_test_points":
        mode = str(out.get("input_mode") or "").strip().lower()
        content = str(out.get("content") or "").strip()
        if mode == "paste" or (content and not out.get("requirement_id")):
            out["content"] = content
            if not content:
                out.pop("content", None)
            out.pop("requirement_id", None)
            out.pop("input_mode", None)
        else:
            out.pop("content", None)
            out.pop("requirement_name", None)
            out.pop("input_mode", None)

    if skill_code == "curl_to_cases":
        curl = str(out.get("curl") or "").strip()
        if curl:
            out["curl"] = curl
        resp = str(out.get("response_sample") or "").strip()
        if resp:
            out["response_sample"] = resp
        else:
            out.pop("response_sample", None)

    if skill_code == "ui_locator_suggest":
        raw_el = str(out.get("raw_element") or out.get("query") or "").strip()
        if raw_el:
            out["raw_element"] = raw_el
        out.pop("query", None)
        intent = str(out.get("intent") or "").strip()
        if intent:
            out["intent"] = intent
        else:
            out.pop("intent", None)

    if skill_code == "knowledge_qa":
        q = str(out.get("query") or "").strip()
        if q:
            out["query"] = q
        mode = str(out.get("mode") or "smart").strip().lower()
        out["mode"] = mode if mode in ("smart", "retrieve") else "smart"

    if skill_code == "failure_to_defect_draft":
        ref = str(out.pop("failure_ref", "") or "").strip()
        if ref and ":" in ref:
            tt, tid_s = ref.split(":", 1)
            tt = tt.strip().lower()
            try:
                tid = int(tid_s.strip())
            except (TypeError, ValueError):
                tid = None
            if tt in ("api", "ui", "app") and tid is not None:
                out["target_type"] = tt
                out["target_id"] = tid
        out.pop("time_range", None)
        has_type = bool(out.get("target_type"))
        has_id = out.get("target_id") is not None
        if has_id and not has_type:
            out.pop("target_id", None)
        sev = str(out.get("severity") or "major").strip() or "major"
        if sev not in ("blocker", "critical", "major", "minor"):
            sev = "major"
        out["severity"] = sev
        pri = str(out.get("priority") or "p2").strip() or "p2"
        if pri not in ("p0", "p1", "p2", "p3"):
            pri = "p2"
        out["priority"] = pri

    if skill_code == "perf_journey_from_suite":
        layout = str(out.get("layout") or "single_phase").strip().lower()
        out["layout"] = layout if layout in ("single_phase", "per_case_phase") else "single_phase"

    if skill_code == "functional_case_to_app_case":
        dm = str(out.get("driver_mode") or "hybrid").strip().lower() or "hybrid"
        out["driver_mode"] = dm

    return out


def chip_prefer_direct_run(skill_code: str | None, source: str | None = None) -> bool:
    """Chip 直出表单提交后是否跳过 LLM、服务端直接 run_skill。"""
    if (source or "").strip() != "skill_chip_direct":
        return False
    return (skill_code or "").strip() in CHIP_DIRECT_RUN_SKILL_CODES


def build_run_skill_kwargs_from_chip_answers(
    skill_code: str, answers: dict[str, Any] | None
) -> dict[str, Any]:
    """将规范化后的 Chip 答案映射为 run_skill kwargs（不含 ctx/project_id）。"""
    norm = normalize_chip_answers_for_continue(skill_code, answers)
    # 透传 skill 认识的字段；忽略 UI 专用键
    skip = {"cancelled", "input_mode"}
    out: dict[str, Any] = {"skill_code": skill_code}
    for k, v in norm.items():
        if k in skip or v is None:
            continue
        out[k] = v
    return out


def format_chip_answer_user_line(skill_code: str, answers: dict[str, Any] | None) -> str:
    """写入会话的用户侧摘要（长文截断，完整参数已由 direct run 传递）。"""
    norm = normalize_chip_answers_for_continue(skill_code, answers)
    parts: list[str] = []
    for k, v in norm.items():
        if v is None or str(k) == "cancelled":
            continue
        s = str(v)
        if k in ("curl", "content", "raw_element", "response_sample", "query", "description", "prompt"):
            preview = s[:200] + ("…" if len(s) > 200 else "")
            parts.append(f"{k}={preview}")
        else:
            parts.append(f"{k}={s}")
    joined = ", ".join(parts) if parts else "（已提交表单）"
    return f"【技能快捷入口】已提交参数并执行 skill_code={skill_code}：{joined}"


async def persist_chip_direct_form(
    *,
    user_id: int,
    project_id: int,
    session_id: int | None,
    chip_key: str,
    chip_label: str | None = None,
    chip_message: str | None = None,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写入会话：用户意图 + 助手 AskUser，返回供前端展示的结构。"""
    from app.modules.assistant.assistant_session import (
        assert_session_belongs_to_project,
        load_session_messages,
        save_session_messages,
        create_session,
    )

    if session_id:
        await assert_session_belongs_to_project(user_id, int(session_id), int(project_id))
        sid, messages = await load_session_messages(
            user_id, int(project_id), session_id=int(session_id)
        )
        if not sid:
            raise ValueError("会话不存在")
    else:
        sess = await create_session(user_id, int(project_id), title=chip_label or "新对话")
        sid = int(sess["id"] if isinstance(sess, dict) else sess.id)
        messages = []

    ask = await build_direct_ask_card(chip_key, project_id=int(project_id))
    user_line = chip_user_prompt_line(chip_key, chip_label)
    if chip_message:
        user_line = f"{user_line}\n原技能说明：{chip_message[:400]}"

    safe_page: dict[str, Any] | None = None
    if isinstance(page_context, dict) and page_context:
        try:
            from brickcore_assist.skills.safe import sanitize_page_context

            safe_page = sanitize_page_context(page_context)
        except Exception:
            safe_page = None

    user_msg = {"role": "user", "content": user_line, "create_time": now_app().isoformat()}
    asst_msg: dict[str, Any] = {
        "role": "assistant",
        "content": "请先在下方补充信息，提交后我将继续生成预览确认卡。",
        "pending_ask_user": ask,
        "ask_user_done": False,
        "mode": "standard",
        "message_id": f"m-{uuid.uuid4().hex[:16]}",
        "create_time": now_app().isoformat(),
    }
    if safe_page:
        asst_msg["page_context"] = safe_page

    messages.append(user_msg)
    messages.append(asst_msg)
    await save_session_messages(
        user_id,
        int(project_id),
        messages,
        session_id=sid,
        title_hint=chip_label or chip_key,
    )
    return {
        "session_id": sid,
        "pending_ask_user": ask,
        "user_message": user_msg,
        "assistant_message": asst_msg,
    }
