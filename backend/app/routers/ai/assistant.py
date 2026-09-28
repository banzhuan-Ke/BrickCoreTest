"""平台内 AI 助手（Phase 4：多会话 + 页面上下文 + 写操作 confirm + 执行回传）"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.modules.assistant.assist_gateway import (
    assist_premium_ready,
    get_assist_premium_info,
    require_assist_premium,
    resolve_chat_mode,
)
from app.modules.assistant.assistant_agent import build_assistant_ctx, run_assistant_chat, run_assistant_confirm
from app.modules.assistant.assistant_session import (
    clear_session,
    clear_session_messages,
    create_session,
    delete_session,
    get_pinned_context,
    list_sessions,
    load_session_messages,
    pin_context_item,
    unpin_context_item,
    update_session_title,
)
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_CONFIG_VIEW, AI_TEST_EXECUTE, AI_TEST_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["AI助手"])


async def _assert_member(user_info: dict, project_id: int | None) -> int:
    """Assistant API 统一项目成员校验；返回规范化 project_id。"""
    if not project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id 必填")
    pid = int(project_id)
    await assert_project_access(user_info, pid, min_role=PROJECT_ROLE_VIEWER)
    return pid


class AssistantHistoryItem(BaseModel):
    role: str = Field(description="user 或 assistant")
    content: str = Field(default="", max_length=4000)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    project_id: Optional[int] = None
    history: list[AssistantHistoryItem] = Field(default_factory=list, max_length=40)
    ai_config_id: Optional[int] = None
    session_id: Optional[int] = None
    use_server_history: bool = True
    page_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="当前页面上下文（路由名、实体 ID 等），用于优先选用相关工具",
    )


class AssistantConfirmRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    confirm_token: str = Field(min_length=8, max_length=128)
    confirm_args: dict[str, Any] = Field(default_factory=dict)
    project_id: Optional[int] = None
    session_id: Optional[int] = None


class CancelConfirmRequest(BaseModel):
    session_id: int
    project_id: Optional[int] = None
    action: str = Field(min_length=1, max_length=64)
    confirm_token: str = Field(min_length=8, max_length=128)


class CreateSessionRequest(BaseModel):
    project_id: Optional[int] = None
    title: str = Field(default="新对话", max_length=200)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class PinContextRequest(BaseModel):
    session_id: int = Field(description="会话 ID")
    project_id: Optional[int] = None
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: Any = Field(description="实体 ID")
    label: str = Field(default="", max_length=120)
    meta: dict[str, Any] = Field(default_factory=dict)


class UnpinContextRequest(BaseModel):
    session_id: int
    project_id: Optional[int] = None
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: Any


class AskUserAnswerRequest(BaseModel):
    session_id: int
    project_id: Optional[int] = None
    ask_id: str = Field(min_length=4, max_length=64)
    answers: dict[str, Any] = Field(default_factory=dict)
    continue_chat: bool = Field(default=True, description="是否带着答案继续对话")
    page_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="可选：续聊时恢复的页面上下文（优先用消息内保存的）",
    )

    @field_validator("answers")
    @classmethod
    def _limit_answers(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("answers 须为对象")
        if len(v) > 40:
            raise ValueError("answers 字段过多")
        # 硬上限：超限拒绝（避免静默截断导致错误生成）
        _MAX_BY_KEY = {
            "curl": 12000,
            "response_sample": 8000,
            "content": 200000,
            "raw_element": 20000,
            "query": 4000,
            "description": 4000,
            "prompt": 2000,
            "intent": 500,
        }
        _REJECT_OVER = frozenset({"curl", "content", "raw_element", "response_sample"})
        out: dict[str, Any] = {}
        for k, val in v.items():
            key = str(k)[:64]
            if isinstance(val, str):
                lim = _MAX_BY_KEY.get(key, 2000)
                if key in _REJECT_OVER and len(val) > lim:
                    raise ValueError(f"{key} 过长（最多 {lim} 字符），请缩短后再提交")
                out[key] = val if len(val) <= lim else val[:lim]
            elif isinstance(val, (int, float, bool)) or val is None:
                out[key] = val
            else:
                continue
        return out


class SkillChipPrepareRequest(BaseModel):
    chip_key: str = Field(min_length=1, max_length=64)
    project_id: int = Field(description="当前项目 ID")
    session_id: Optional[int] = None
    chip_label: str = Field(default="", max_length=80)
    chip_message: str = Field(default="", max_length=2000)
    page_context: Optional[dict[str, Any]] = None


class MemoryUpsertRequest(BaseModel):
    project_id: int
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=2000)


class FeedbackRequest(BaseModel):
    session_id: int
    message_id: str = Field(min_length=1, max_length=64)
    score: int = Field(description="1=赞 -1=踩")
    note: str = Field(default="", max_length=500)
    project_id: Optional[int] = None


QUICK_PROMPTS = [
    {"key": "overview", "label": "项目概览", "message": "请总结当前项目的完整情况，包括环境、模块、需求和用例库规模。"},
    {
        "key": "loop_analyze",
        "label": "失败闭环",
        "message": (
            "请做「失败分析闭环」："
            "1）列出当前项目最近失败用例；"
            "2）查看最近接口套件/计划执行记录；"
            "3）在回复中写明可用于分析的 target_type 与 target_id（接口失败记录 ID）；"
            "4）若我已在本句给出 target，再发起 AI 失败分析预览（需我确认）；否则先出清单等我指定。"
            "若当前无失败，直接说明即可。"
        ),
    },
    {
        "key": "loop_run",
        "label": "执行闭环",
        "message": (
            "请做「接口执行闭环」："
            "1）列出当前项目的接口测试计划与测试环境；"
            "2）若页面上下文或本句已有计划 ID 与环境 ID，则预览执行该计划（需我确认）；"
            "否则先推荐一个可执行计划并说明还需哪项 ID。"
            "3）执行完成后我会收到回传；若有失败，我再点快捷「失败闭环」做分析。"
            "不要跳过确认直接执行。"
        ),
    },
    {"key": "failures", "label": "最近失败", "message": "列出当前项目最近的失败用例，并简要说明。"},
    {"key": "requirements", "label": "需求列表", "message": "当前项目有哪些需求文档？各有多少条已生成用例？"},
    {
        "key": "api_overview",
        "label": "接口概览",
        "message": "请汇总当前项目的接口分类、接口定义、接口测试用例和套件情况。",
    },
    {
        "key": "api_cases",
        "label": "接口用例",
        "message": "列出当前项目的接口测试用例，说明各用例关联的接口、方法与路径。",
    },
    {
        "key": "api_runs",
        "label": "接口执行",
        "message": "列出当前项目最近的接口套件与测试计划执行记录，并简要说明成功/失败情况。",
    },
    {
        "key": "ui_runs",
        "label": "UI 执行",
        "message": "列出当前项目最近的 UI 测试计划执行记录，说明通过率与失败数。",
    },
    {
        "key": "app",
        "label": "App 用例",
        "message": "当前项目有哪些 App 用例、套件和测试计划？各有多少步骤或用例？",
    },
    {
        "key": "app_suites",
        "label": "App 套件",
        "message": "列出当前项目的 App 测试套件及各套件包含的用例数。",
    },
    {
        "key": "app_plans",
        "label": "App 计划",
        "message": "列出当前项目的 App 测试计划及最近执行状态。",
    },
    {
        "key": "app_runs",
        "label": "App 执行",
        "message": "列出当前项目最近的 App 套件与计划执行记录，并简要说明成功/失败情况。",
    },
    {
        "key": "perf",
        "label": "压测概览",
        "message": "当前项目有哪些压测场景？最近一次压测的 QPS 和响应时间如何？",
    },
    {"key": "ui", "label": "UI 计划", "message": "当前项目有哪些 UI 测试计划和 Web 用例？"},
    {
        "key": "ui_suites",
        "label": "UI 套件",
        "message": "列出当前项目的 Web UI 测试套件及各套件包含的用例数。",
    },
    {
        "key": "api_plans",
        "label": "接口计划",
        "message": "列出当前项目的接口测试计划及最近执行状态。",
    },
    {
        "key": "cron_all",
        "label": "定时任务",
        "message": "汇总当前项目接口、UI、App、压测四类定时任务及启用状态。",
    },
    {
        "key": "workers",
        "label": "压测 Worker",
        "message": "当前项目有哪些压测 Worker 节点？在线状态如何？",
    },
    {
        "key": "run_api_case",
        "label": "单条用例",
        "message": "列出当前项目的测试环境，并说明如何按用例 ID 或名称执行单条接口用例。",
    },
    {
        "key": "run_ui_case",
        "label": "Web 单条",
        "message": "列出当前项目的 Web UI 用例和在线 Runner 设备，并说明如何执行单条 Web UI 用例。",
    },
    {
        "key": "run_app_case",
        "label": "App 单条",
        "message": "列出当前项目的 App 用例和在线 App Runner 设备（含 adb 设备），并说明如何执行单条 App 用例。",
    },
    {
        "key": "data_factory",
        "label": "数据工厂",
        "message": "列出当前项目的数据工厂数据源和 SQL 模板（setup/teardown），说明各环境配置情况。",
    },
    {
        "key": "mock",
        "label": "Mock 接口",
        "message": "列出当前项目已配置的 Mock 接口及匹配规则。",
    },
    {
        "key": "devices",
        "label": "在线设备",
        "message": "列出当前项目在线的 Web / App Runner 设备，说明 device_id、app_udid 与状态。",
    },
    {
        "key": "browser_lab",
        "label": "智能浏览器",
        "message": (
            "请帮我派发智能浏览器（Browser Lab）探索任务："
            "1）先 list_online_devices 确认有在线 Runner；"
            "2）若缺起始 URL / 任务描述 / device_id，用 ask_user 询问；"
            "3）信息齐后调用 preview_spawn_browser_lab（需我确认），不要直接执行。"
        ),
    },
]


SKILL_CHIPS = [
    {
        "key": "skill_ui_failure",
        "label": "失败分析",
        "kind": "skill",
        "skill_code": "ui_failure_analysis",
        "direct_form": True,
        "message": "请分析近期失败（可指定接口 / Web UI / App / 压测记录），给出原因和下一步建议。",
        "hint": "将直接弹出失败域与记录选择表单",
    },
    {
        "key": "skill_req_test_points",
        "label": "需求→测试点",
        "kind": "skill",
        "skill_code": "requirement_to_test_points",
        "direct_form": True,
        "message": "请根据需求生成测试点草稿，并先给我预览确认卡。可选择已有需求或粘贴正文。",
        "hint": "将直接弹出「选已有 / 粘贴」表单",
    },
    {
        "key": "skill_api_to_cases",
        "label": "接口→用例",
        "kind": "skill",
        "skill_code": "api_definition_to_cases",
        "direct_form": True,
        "message": "请根据接口定义生成测试用例，并先给我预览确认卡。若未钉住或未说明 api_definition_id，请先列出接口并用选择卡让我挑选，不要自行选一个。",
        "hint": "将直接弹出接口选择表单",
    },
    {
        "key": "skill_tp_to_cases",
        "label": "测试点→用例",
        "kind": "skill",
        "skill_code": "test_points_to_functional_cases",
        "direct_form": True,
        "message": "请根据需求测试点生成功能用例草稿，并先给我预览确认卡。若未钉住或未说明 requirement_id，请先列出需求并用选择卡让我挑选，不要自行选一个。",
        "hint": "将直接弹出需求选择表单",
    },
    {
        "key": "skill_mock_gen",
        "label": "生成 Mock",
        "kind": "skill",
        "skill_code": "mock_response_generate",
        "direct_form": True,
        "message": "请根据接口方法与路径生成 Mock 响应，并先给我预览确认卡。需要 method 和 path。",
        "hint": "将直接弹出方法/路径表单",
    },
    {
        "key": "skill_df_nl_sql",
        "label": "NL→SQL模板",
        "kind": "skill",
        "skill_code": "nl_to_sql_template",
        "direct_form": True,
        "message": "请根据自然语言生成数据工厂 SQL 模板与断言草稿，并先给我预览确认卡。需要 datasource_id 与 prompt。",
        "hint": "将直接弹出数据源与需求表单",
    },
    {
        "key": "skill_perf_nl",
        "label": "一句话压测",
        "kind": "skill",
        "skill_code": "perf_scene_from_nl",
        "direct_form": True,
        "message": "请根据我的自然语言描述生成压测场景草稿，并先给我预览确认卡。",
        "hint": "将直接弹出压测描述表单",
    },
    {
        "key": "skill_bl_to_ui",
        "label": "浏览器→用例",
        "kind": "skill",
        "skill_code": "browser_lab_to_ui_case",
        "direct_form": True,
        "message": "请把智能浏览器任务转成 Web UI 用例，并先给我预览确认卡。若未钉住或未说明 task_id，请先列出任务并用选择卡让我挑选。",
        "hint": "将直接弹出浏览器任务选择表单",
    },
    {
        "key": "skill_ui_nl",
        "label": "自然语言 UI",
        "kind": "skill",
        "skill_code": "ui_steps_from_nl",
        "direct_form": True,
        "message": "请根据自然语言生成 Web UI 步骤，并先给我预览确认卡。",
        "hint": "将直接弹出描述/URL/设备表单",
    },
    {
        "key": "skill_report_narr",
        "label": "报告叙事",
        "kind": "skill",
        "skill_code": "report_narrative",
        "direct_form": True,
        "message": "请为这条执行报告生成摘要叙事，并先给我预览确认卡。需要 report_type 和 record_id。",
        "hint": "将直接弹出报告类型与记录 ID 表单",
    },
    {
        "key": "skill_qa_eval",
        "label": "问答评测",
        "kind": "skill",
        "skill_code": "qa_eval_assist",
        "direct_form": True,
        "message": "请预览并准备启动问答评测跑批。若未钉住或未说明 set_id，请先列出评测集并用选择卡让我挑选。",
        "hint": "将直接弹出评测集选择表单",
    },
    {
        "key": "skill_curl_to_cases",
        "label": "curl→用例",
        "kind": "skill",
        "skill_code": "curl_to_cases",
        "direct_form": True,
        "message": "请根据我粘贴的 curl（及可选响应样例）生成接口用例，并先给我预览确认卡。",
        "hint": "将直接弹出 curl / 响应样例表单",
    },
    {
        "key": "skill_knowledge_qa",
        "label": "资料库问答",
        "kind": "skill",
        "skill_code": "knowledge_qa",
        "direct_form": True,
        "message": "请根据我对资料库的提问检索并回答。",
        "hint": "将直接弹出问题表单",
    },
    {
        "key": "skill_platform_howto",
        "label": "平台怎么用",
        "kind": "skill",
        "skill_code": "platform_how_to",
        "direct_form": True,
        "message": "请根据帮助中心与技能清单说明平台功能或技能怎么用，并给出可跳转入口。",
        "hint": "将直接弹出问题表单",
    },
    {
        "key": "skill_locator",
        "label": "元素→定位",
        "kind": "skill",
        "skill_code": "ui_locator_suggest",
        "direct_form": True,
        "message": "请根据我粘贴的页面元素信息给出定位建议。",
        "hint": "将直接弹出元素信息表单",
    },
    {
        "key": "skill_fc_to_ui",
        "label": "功能用例→Web",
        "kind": "skill",
        "skill_code": "functional_case_to_ui_case",
        "direct_form": True,
        "message": "请把功能用例转为 Web UI 用例，并先给我预览确认卡。",
        "hint": "将直接弹出功能用例选择表单",
    },
    {
        "key": "skill_fc_to_app",
        "label": "功能用例→App",
        "kind": "skill",
        "skill_code": "functional_case_to_app_case",
        "direct_form": True,
        "message": "请把功能用例转为 App 用例，并先给我预览确认卡。",
        "hint": "将直接弹出功能用例选择表单",
    },
    {
        "key": "skill_suite_to_perf",
        "label": "套件→压测",
        "kind": "skill",
        "skill_code": "perf_journey_from_suite",
        "direct_form": True,
        "message": "请把接口套件转为压测 journey 场景，并先给我预览确认卡。",
        "hint": "将直接弹出套件选择表单",
    },
    {
        "key": "skill_failure_to_defect",
        "label": "失败→缺陷",
        "kind": "skill",
        "skill_code": "failure_to_defect_draft",
        "direct_form": True,
        "message": "请根据失败记录生成 TM 缺陷草稿，并先给我预览确认卡。",
        "hint": "将直接弹出失败记录选择表单",
    },
]


@router.get(
    "/quick-prompts",
    summary="助手快捷提问",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_quick_prompts():
    from app.core.platform.edition import knowledge_feature_enabled, qa_eval_feature_enabled
    from app.modules.assistant.assist_gateway import assist_premium_ready

    items = QUICK_PROMPTS
    if not qa_eval_feature_enabled():
        items = [p for p in QUICK_PROMPTS if p.get("key") != "qa_eval"]
    chips = SKILL_CHIPS if assist_premium_ready() else []
    if chips and not qa_eval_feature_enabled():
        chips = [c for c in chips if c.get("key") != "skill_qa_eval"]
    if chips and not knowledge_feature_enabled():
        chips = [c for c in chips if c.get("key") != "skill_knowledge_qa"]
    return StandardResponse(data={"items": items, "skill_chips": chips})


@router.post(
    "/skill-chips/prepare",
    summary="技能 Chip 直出补充信息表单（跳过空转模型轮）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def prepare_skill_chip_form(
    body: SkillChipPrepareRequest,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.assistant.assist_gateway import assist_premium_ready
    from app.modules.assistant.assistant_skill_chip_forms import (
        chip_supports_direct_form,
        persist_chip_direct_form,
    )

    if not assist_premium_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="小测标准模式未就绪，无法使用技能快捷表单",
        )
    if not chip_supports_direct_form(body.chip_key):
        raise HTTPException(status_code=400, detail="该 Chip 不支持直出表单")
    if body.chip_key == "skill_qa_eval":
        from app.core.platform.edition import qa_eval_feature_enabled

        if not qa_eval_feature_enabled():
            raise HTTPException(status_code=400, detail="当前版本未启用问答评测")
    if body.chip_key == "skill_knowledge_qa":
        from app.core.platform.edition import knowledge_feature_enabled

        if not knowledge_feature_enabled():
            raise HTTPException(status_code=400, detail="当前版本未启用资料库")
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        from app.core.platform.project_access import PROJECT_ROLE_MEMBER
        from app.modules.assistant.assistant_skill_chip_forms import skill_code_for_chip
        from brickcore_assist.skills.policy import get_skill_policy, skill_required_permission

        # 生成类 / 写 Skill：prepare 即要求成员 + 对应执行权限，避免 VIEWER 填完才失败
        code = skill_code_for_chip(body.chip_key)
        policy = get_skill_policy(code) if code else None
        min_role = policy.min_role if policy else PROJECT_ROLE_MEMBER
        needs_member = min_role == PROJECT_ROLE_MEMBER
        if needs_member:
            req_perm = skill_required_permission(code) if code else AI_TEST_EXECUTE
            if req_perm and not user_info.get("is_superuser"):
                from app.core.platform.auth import _load_user_permission_codes

                uid = user_info.get("id")
                allowed = await _load_user_permission_codes(int(uid)) if uid else set()
                if req_perm not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"权限不足：需要 {req_perm} 才能使用该技能表单",
                    )
            await assert_project_access(user_info, int(body.project_id), min_role=PROJECT_ROLE_MEMBER)
            pid = int(body.project_id)
        else:
            pid = await _assert_member(user_info, body.project_id)
        data = await persist_chip_direct_form(
            user_id=int(user_id),
            project_id=pid,
            session_id=body.session_id,
            chip_key=body.chip_key,
            chip_label=body.chip_label or "",
            chip_message=body.chip_message or "",
            page_context=body.page_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StandardResponse(data=data, message="ok")


@router.get(
    "/capabilities",
    summary="助手能力与扩展包状态（始终 200）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_assistant_capabilities():
    """无包/未 ready 时 mode=lite；不抛 503。"""
    info = get_assist_premium_info()
    return StandardResponse(
        data={
            "mode": info.get("mode") or "lite",
            "installed": bool(info.get("installed")),
            "compatible": bool(info.get("compatible")),
            "ready": bool(info.get("ready")),
            "version": info.get("version"),
            "api_version": info.get("api_version"),
            "reason": info.get("reason"),
            "capabilities": info.get("capabilities") or [],
            "message": info.get("message"),
            "doc": info.get("doc"),
        }
    )


@router.get(
    "/skills",
    summary="列出可用 Skill（无扩展包返回空列表）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_assistant_skills():
    """仅 ready 时返回可执行 Skill 列表，避免前端展示后点击 503。"""
    info = get_assist_premium_info()
    skills: list = []
    if info.get("ready"):
        try:
            from brickcore_assist import api as assist_api

            skills = list(assist_api.list_skills() or [])
        except Exception:
            skills = []
    return StandardResponse(
        data={
            "skills": skills,
            "mode": info.get("mode") or "lite",
            "ready": bool(info.get("ready")),
            "executable": bool(info.get("ready")),
        }
    )


def _assist_agent_intro() -> dict[str, Any]:
    """小测 Agent 基础介绍（只读文案，不含 Prompt）。"""
    return {
        "name": "小测",
        "modes": [
            {
                "code": "lite",
                "label": "精简模式",
                "summary": "单轮工具问答；无扩展包或开关关闭时使用。",
            },
            {
                "code": "standard",
                "label": "标准模式（多轮）",
                "summary": (
                    "多轮编排：可调用平台工具与内置技能；"
                    "写操作需预览确认卡；缺关键参数会出选择卡。"
                ),
            },
        ],
        "notes": [
            "生成类操作（如接口→用例）默认先预览，确认后再写入。",
            "禁止编造环境、设备、接口定义等 ID；以工具结果与钉住上下文为准。",
            "可通过小测快捷入口、对话或 MCP 工具调用技能。",
            "详细 Token 消耗占比见「模型使用情况」；本页按技能汇总执行记录。",
        ],
    }


def _capability_highlights(*, skill_count: int = 0) -> dict[str, Any]:
    """能力亮点：技能 / 小测工具 / MCP 工具数量（只读统计，不含密钥）。"""
    from app.modules.assistant.assistant_tools import PREVIEW_TOOL_NAMES, READONLY_TOOL_NAMES

    assistant_tools = len(READONLY_TOOL_NAMES) + len(PREVIEW_TOOL_NAMES)
    mcp_tool_count = 0
    mcp_group_count = 0
    try:
        from app.mcp.server import MCP_TOOL_GROUPS, get_registered_tool_count

        mcp_tool_count = int(get_registered_tool_count() or 0)
        mcp_group_count = len(MCP_TOOL_GROUPS)
    except Exception:
        logger.debug("capability highlights: mcp tool count unavailable", exc_info=True)

    return {
        "skill_count": int(skill_count or 0),
        "assistant_tool_count": assistant_tools,
        "mcp_tool_count": mcp_tool_count,
        "mcp_group_count": mcp_group_count,
        "blurb": (
            f"当前支持约 {int(skill_count or 0)} 项内置技能、"
            f"{assistant_tools} 个小测可调工具、"
            f"{mcp_tool_count} 个 MCP 工具（{mcp_group_count} 组）；"
            "站内小测与站外 MCP 共用 Skill / 预览确认契约。"
        ),
    }


def _overview_filter_project_id(project_id: Optional[int]) -> Optional[int]:
    """仅正整数参与 project_id 过滤；0 / 负数视为未筛选。"""
    if project_id is None:
        return None
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _serialize_skill_run_row(r: Any) -> dict[str, Any]:
    """执行记录对外字段：截断摘要，不返回 Prompt 正文。"""
    err = (getattr(r, "error_message", None) or "")[:200]
    return {
        "id": getattr(r, "id", None),
        "skill_code": getattr(r, "skill_code", None),
        "skill_version": getattr(r, "skill_version", None),
        "project_id": getattr(r, "project_id", None),
        "entry_source": getattr(r, "entry_source", None),
        "run_mode": getattr(r, "run_mode", None),
        "status": getattr(r, "status", None),
        "input_summary": (getattr(r, "input_summary", None) or "")[:200],
        "output_summary": (getattr(r, "output_summary", None) or "")[:300],
        "error_message": err or None,
        "duration_ms": getattr(r, "duration_ms", None),
        "tokens_used": getattr(r, "tokens_used", None),
        "username": getattr(r, "username", None),
        "create_time": r.create_time.isoformat() if getattr(r, "create_time", None) else None,
    }


def _apply_skill_run_filters(
    qs,
    *,
    skill_code: Optional[str] = None,
    status: Optional[str] = None,
    entry_source: Optional[str] = None,
    run_mode: Optional[str] = None,
):
    code = (skill_code or "").strip()
    if code:
        qs = qs.filter(skill_code=code)
    st = (status or "").strip()
    if st:
        qs = qs.filter(status=st)
    entry = (entry_source or "").strip()
    if entry:
        qs = qs.filter(entry_source=entry)
    mode = (run_mode or "").strip()
    if mode:
        qs = qs.filter(run_mode=mode)
    return qs


@router.get(
    "/skills/overview",
    summary="Skills / Agent 可见面：介绍 + 按 skill 调用统计 + 近期执行",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_skills_overview(
    days: int = Query(30, ge=1, le=90, description="统计近 N 天"),
    project_id: Optional[int] = Query(None, description="可选：按项目过滤执行统计"),
    recent_limit: int = Query(20, ge=1, le=50),
):
    """介绍始终可读；Skill 清单在扩展包已安装时列出（未 ready 也可看简介）。"""
    from datetime import timedelta

    from tortoise.functions import Count, Sum

    from app.core.platform.datetime_utils import now_app
    from app.models.ai import AiSkillRunRecord

    info = get_assist_premium_info()
    manifests: list[dict[str, Any]] = []
    manifests_error: Optional[str] = None
    if info.get("installed"):
        try:
            from brickcore_assist.skills.registry import list_skill_manifests

            manifests = list(list_skill_manifests() or [])
        except Exception:
            logger.exception("skills/overview: list_skill_manifests failed")
            manifests = []
            manifests_error = "skill_manifest_load_failed"

    # 与 usage_logs / assist_run_stale 一致：Asia/Shanghai naive 墙钟
    since = now_app() - timedelta(days=int(days))
    qs = AiSkillRunRecord.filter(create_time__gte=since)
    filter_pid = _overview_filter_project_id(project_id)
    if filter_pid is not None:
        qs = qs.filter(project_id=filter_pid)

    stats_map: dict[str, dict[str, Any]] = {}
    stats_error: Optional[str] = None
    try:
        rows = (
            await qs.group_by("skill_code")
            .annotate(calls=Count("id"), tokens=Sum("tokens_used"))
            .values("skill_code", "calls", "tokens")
        )
        for row in rows or []:
            code = str(row.get("skill_code") or "").strip()
            if not code:
                continue
            stats_map[code] = {
                "calls": int(row.get("calls") or 0),
                "tokens_used": int(row.get("tokens") or 0),
                "failed_calls": 0,
                "success_calls": 0,
            }
        fail_rows = (
            await qs.filter(status="failed")
            .group_by("skill_code")
            .annotate(failed_calls=Count("id"))
            .values("skill_code", "failed_calls")
        )
        for row in fail_rows or []:
            code = str(row.get("skill_code") or "").strip()
            if code in stats_map:
                stats_map[code]["failed_calls"] = int(row.get("failed_calls") or 0)
        ok_rows = (
            await qs.filter(status="success")
            .group_by("skill_code")
            .annotate(success_calls=Count("id"))
            .values("skill_code", "success_calls")
        )
        for row in ok_rows or []:
            code = str(row.get("skill_code") or "").strip()
            if code in stats_map:
                stats_map[code]["success_calls"] = int(row.get("success_calls") or 0)
    except Exception:
        logger.exception("skills/overview: aggregate skill run stats failed")
        stats_map = {}
        stats_error = "skill_stats_query_failed"

    skills_out: list[dict[str, Any]] = []
    try:
        from brickcore_assist.skills.policy import get_skill_policy, skill_required_permission
    except Exception:
        get_skill_policy = None  # type: ignore
        skill_required_permission = None  # type: ignore
    for m in manifests:
        code = str(m.get("code") or "").strip()
        st = stats_map.get(code) or {
            "calls": 0,
            "tokens_used": 0,
            "failed_calls": 0,
            "success_calls": 0,
        }
        policy = get_skill_policy(code) if get_skill_policy and code else None
        min_role = getattr(policy, "min_role", None) or PROJECT_ROLE_VIEWER
        req_perm = (
            skill_required_permission(code)
            if skill_required_permission and code
            else (AI_TEST_EXECUTE if min_role == PROJECT_ROLE_MEMBER else None)
        )
        skills_out.append(
            {
                **{k: v for k, v in m.items() if k != "system"},
                "stats": st,
                "executable": bool(info.get("ready")),
                "source": "current",
                "min_role": min_role,
                "required_permission": req_perm,
                "requires_ai_execute": req_perm == AI_TEST_EXECUTE,
                "can_quick_use": bool(info.get("ready")) and bool(code),
            }
        )

    # 有执行记录但不在当前清单里的 skill（历史/旧版）
    known = {str(s.get("code") or "") for s in skills_out}
    for code, st in stats_map.items():
        if code and code not in known:
            skills_out.append(
                {
                    "code": code,
                    "name": code,
                    "description": "历史执行记录中的 Skill（当前包未登记清单）",
                    "version": None,
                    "entry_modes": [],
                    "params": {},
                    "stats": st,
                    "executable": False,
                    "source": "historical",
                }
            )

    recent: list[dict[str, Any]] = []
    recent_error: Optional[str] = None
    try:
        run_rows = await qs.order_by("-id").limit(int(recent_limit))
        for r in run_rows:
            recent.append(_serialize_skill_run_row(r))
    except Exception:
        logger.exception("skills/overview: list recent skill runs failed")
        recent = []
        recent_error = "recent_runs_query_failed"

    total_calls = sum(int(s["stats"]["calls"]) for s in skills_out)
    total_tokens = sum(int(s["stats"]["tokens_used"]) for s in skills_out)
    total_failed = sum(int(s["stats"]["failed_calls"]) for s in skills_out)

    return StandardResponse(
        data={
            "period_days": int(days),
            "project_id": filter_pid,
            "capabilities": {
                "mode": info.get("mode") or "lite",
                "installed": bool(info.get("installed")),
                "compatible": bool(info.get("compatible")),
                "ready": bool(info.get("ready")),
                "version": info.get("version"),
                "api_version": info.get("api_version"),
                "reason": info.get("reason"),
                "capabilities": info.get("capabilities") or [],
                "message": info.get("message"),
            },
            "agent": _assist_agent_intro(),
            "skills": skills_out,
            "summary": {
                "skill_count": len([s for s in skills_out if s.get("code")]),
                "calls": total_calls,
                "tokens_used": total_tokens,
                "failed_calls": total_failed,
            },
            "highlights": _capability_highlights(
                skill_count=len([s for s in skills_out if s.get("code") and s.get("source") != "historical"])
            ),
            "recent_runs": recent,
            "errors": {
                "manifests": manifests_error,
                "stats": stats_error,
                "recent_runs": recent_error,
            },
        }
    )


@router.get(
    "/skills/runs",
    summary="技能执行记录（分页 + 筛选）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_skill_runs(
    days: int = Query(30, ge=1, le=90, description="近 N 天"),
    project_id: Optional[int] = Query(None, description="可选：按项目过滤"),
    skill_code: Optional[str] = Query(None, max_length=64),
    status: Optional[str] = Query(None, max_length=32, description="success/failed/running/preview…"),
    entry_source: Optional[str] = Query(None, max_length=32, description="assistant/mcp/page/api/job"),
    run_mode: Optional[str] = Query(None, max_length=16, description="preview/confirm/direct"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """执行记录列表；摘要截断，不含 Prompt 正文。"""
    from datetime import timedelta

    from app.core.platform.datetime_utils import now_app
    from app.models.ai import AiSkillRunRecord

    since = now_app() - timedelta(days=int(days))
    qs = AiSkillRunRecord.filter(create_time__gte=since)
    filter_pid = _overview_filter_project_id(project_id)
    if filter_pid is not None:
        qs = qs.filter(project_id=filter_pid)
    qs = _apply_skill_run_filters(
        qs,
        skill_code=skill_code,
        status=status,
        entry_source=entry_source,
        run_mode=run_mode,
    )
    total = await qs.count()
    page_n = int(page)
    size_n = int(size)
    offset = (page_n - 1) * size_n
    rows = await qs.order_by("-id").offset(offset).limit(size_n)
    return StandardResponse(
        data={
            "total": int(total),
            "page": page_n,
            "size": size_n,
            "items": [_serialize_skill_run_row(r) for r in rows],
            "period_days": int(days),
            "project_id": filter_pid,
        }
    )


class SkillRunRequest(BaseModel):
    skill_code: str = Field(min_length=1, max_length=64)
    project_id: int = Field(description="项目 ID")
    query: Optional[str] = Field(None, max_length=2000, description="knowledge_qa 问题")
    mode: Optional[str] = Field(None, description="knowledge_qa: smart|retrieve")
    folder_ids: Optional[list[int]] = Field(None, max_length=20)
    document_ids: Optional[list[int]] = Field(None, max_length=20)
    target_type: Optional[str] = Field(None, description="api|ui|app；与 target_id 一起指定单条")
    target_id: Optional[int] = None
    requirement_id: Optional[int] = Field(None, description="requirement_to_test_points")
    api_definition_id: Optional[int] = Field(None, description="api_definition_to_cases")
    count: Optional[int] = Field(None, ge=1, le=30, description="生成条数")
    catalog_id: Optional[int] = None
    test_point_ids: Optional[list[int]] = None
    method: Optional[str] = None
    path: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = Field(None, max_length=4000)
    response_status: Optional[int] = None
    prompt: Optional[str] = Field(None, max_length=2000)
    suite_id: Optional[int] = None
    case_ids: Optional[list[int]] = None
    task_id: Optional[int] = None
    case_name: Optional[str] = None
    page_url: Optional[str] = None
    device_id: Optional[str] = None
    report_type: Optional[str] = None
    record_id: Optional[int] = None
    set_id: Optional[int] = None
    curl: Optional[str] = Field(None, max_length=12000, description="curl_to_cases")
    response_sample: Optional[str] = Field(None, max_length=8000)
    content: Optional[str] = Field(None, max_length=200000, description="需求粘贴正文")
    requirement_name: Optional[str] = Field(None, max_length=200)
    raw_element: Optional[str] = Field(None, max_length=20000, description="ui_locator_suggest")
    intent: Optional[str] = Field(None, max_length=500)
    limit: int = Field(1, ge=1, le=30)
    force_refresh: bool = False
    ai_config_id: Optional[int] = None
    session_id: Optional[int] = None


@router.post(
    "/skills/run",
    summary="执行 Skill（需扩展包 ready）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def run_assistant_skill(
    body: SkillRunRequest,
    user_info: dict = Depends(is_authenticated),
):
    try:
        require_assist_premium()
        await _assert_member(user_info, body.project_id)
        ctx = await build_assistant_ctx(user_info)
        from brickcore_assist import api as assist_api
        from brickcore_assist.api import AssistBusyError

        code = body.skill_code.strip()
        _PREVIEW_SKILLS = {
            "requirement_to_test_points",
            "api_definition_to_cases",
            "test_points_to_functional_cases",
            "mock_response_generate",
            "perf_scene_from_nl",
            "browser_lab_to_ui_case",
            "ui_steps_from_nl",
            "report_narrative",
            "qa_eval_assist",
            "curl_to_cases",
        }
        run_mode = "preview" if code in _PREVIEW_SKILLS else "direct"
        data = await assist_api.run_skill(
            ctx=ctx,
            skill_code=code,
            project_id=body.project_id,
            query=body.query,
            mode=body.mode,
            folder_ids=body.folder_ids,
            document_ids=body.document_ids,
            target_type=body.target_type,
            target_id=body.target_id,
            requirement_id=body.requirement_id,
            api_definition_id=body.api_definition_id,
            count=body.count,
            catalog_id=body.catalog_id,
            test_point_ids=body.test_point_ids,
            method=body.method,
            path=body.path,
            name=body.name,
            description=body.description,
            response_status=body.response_status,
            prompt=body.prompt,
            suite_id=body.suite_id,
            case_ids=body.case_ids,
            task_id=body.task_id,
            case_name=body.case_name,
            page_url=body.page_url,
            device_id=body.device_id,
            report_type=body.report_type,
            record_id=body.record_id,
            set_id=body.set_id,
            curl=body.curl,
            response_sample=body.response_sample,
            content=body.content,
            requirement_name=body.requirement_name,
            raw_element=body.raw_element,
            intent=body.intent,
            limit=body.limit,
            force_refresh=body.force_refresh,
            entry_source="api",
            run_mode=run_mode,
            ai_config_id=body.ai_config_id,
            session_id=body.session_id,
        )
        return StandardResponse(data=data, message="ok")
    except HTTPException:
        raise
    except ValueError as exc:
        detail = str(exc)
        if detail in ("用户不存在", "未登录") or "用户不存在" in detail:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail) from exc
        if detail.startswith("权限不足"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        from brickcore_assist.api import AssistBusyError

        if isinstance(exc, AssistBusyError):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc
        logger.exception("[assistant] run_skill failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Skill 执行失败，请稍后重试",
        ) from exc


@router.get(
    "/sessions",
    summary="列出助手会话（多会话）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_assistant_sessions(
    project_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="按标题或最近消息预览搜索"),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    items = await list_sessions(user_id, project_id, keyword=keyword)
    return StandardResponse(data={"items": items, "project_id": project_id, "keyword": keyword or ""})


@router.post(
    "/sessions",
    summary="新建助手会话",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def post_assistant_session(
    body: CreateSessionRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    item = await create_session(user_id, body.project_id, title=body.title)
    return StandardResponse(data=item, message="会话已创建")


@router.patch(
    "/sessions/{session_id}",
    summary="重命名助手会话",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def patch_assistant_session(
    session_id: int,
    body: RenameSessionRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        item = await update_session_title(user_id, session_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return StandardResponse(data=item, message="已重命名")


@router.delete(
    "/sessions/{session_id}",
    summary="删除助手会话",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def remove_assistant_session(
    session_id: int,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    await delete_session(user_id, session_id)
    return StandardResponse(message="会话已删除")


@router.get(
    "/session",
    summary="获取助手会话历史（服务端）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_assistant_session(
    project_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    sid, messages = await load_session_messages(user_id, project_id, session_id=session_id)
    pinned = {"items": [], "updated_at": None}
    if sid:
        try:
            pinned = await get_pinned_context(user_id, sid)
        except Exception:
            pinned = {"items": [], "updated_at": None}
        try:
            from app.modules.assistant.assistant_feedback import (
                apply_feedback_scores,
                map_scores_for_session,
            )

            score_map = await map_scores_for_session(user_id=int(user_id), session_id=int(sid))
            messages = apply_feedback_scores(messages, score_map)
        except Exception:
            logger.warning(
                "[assistant] merge feedback scores failed session=%s",
                sid,
                exc_info=True,
            )
    return StandardResponse(
        data={
            "session_id": sid,
            "messages": messages,
            "project_id": project_id,
            "pinned_context": pinned,
        }
    )


@router.post(
    "/context/pin",
    summary="钉住实体到当前助手会话（W2）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def pin_assistant_context(
    body: PinContextRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        data = await pin_context_item(
            user_id,
            body.session_id,
            body.project_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            label=body.label,
            meta=body.meta,
        )
        return StandardResponse(data={"pinned_context": data}, message="已钉住")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/context/unpin",
    summary="取消钉住实体（W2）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def unpin_assistant_context(
    body: UnpinContextRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        data = await unpin_context_item(
            user_id,
            body.session_id,
            body.project_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
        )
        return StandardResponse(data={"pinned_context": data}, message="已取消钉住")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/context",
    summary="获取会话钉住上下文（W2）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_assistant_context(
    session_id: int = Query(...),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        from app.modules.assistant.assistant_session import assert_session_belongs_to_project

        await assert_session_belongs_to_project(user_id, session_id, project_id)
        data = await get_pinned_context(user_id, session_id)
        return StandardResponse(data={"pinned_context": data, "session_id": session_id})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ask-user/answer",
    summary="回答 AskUser 卡片并可选继续对话（W2）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def answer_assistant_ask_user(
    body: AskUserAnswerRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        from app.modules.assistant.assistant_ask_guard import (
            release_ask_answer_claim,
            try_claim_ask_answer,
            validate_ask_user_answers,
        )
        from app.modules.assistant.assistant_session import (
            assert_session_belongs_to_project,
            save_session_messages,
        )
        from app.modules.assistant.assistant_skill_chip_forms import (
            build_run_skill_kwargs_from_chip_answers,
            chip_prefer_direct_run,
            format_chip_answer_user_line,
            normalize_chip_answers_for_continue,
        )

        if body.project_id is not None:
            await _assert_member(user_info, body.project_id)
        await assert_session_belongs_to_project(user_id, body.session_id, body.project_id)
        sid, messages = await load_session_messages(
            user_id, body.project_id, session_id=body.session_id
        )
        if not sid:
            raise ValueError("会话不存在")

        matched_msg: dict[str, Any] | None = None
        matched_pending: dict[str, Any] | None = None
        matched_page_context: dict[str, Any] | None = None
        for msg in reversed(messages):
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            pending = msg.get("pending_ask_user")
            if not isinstance(pending, dict):
                continue
            if str(pending.get("ask_id") or "") != body.ask_id:
                continue
            if msg.get("ask_user_done"):
                raise ValueError("该提问已回答过，请勿重复提交")
            matched_msg = msg
            matched_pending = pending
            matched_page_context = (
                msg.get("page_context") if isinstance(msg.get("page_context"), dict) else None
            )
            break
        if not matched_msg or not matched_pending:
            raise ValueError("未找到对应的提问卡片，可能已过期")

        answers = validate_ask_user_answers(matched_pending, body.answers or {})
        cancelled = str(answers.get("cancelled") or "").lower() in ("1", "true", "yes")
        chip_key = str((matched_pending or {}).get("chip_key") or "").strip()
        skill_code = str((matched_pending or {}).get("skill_code") or "").strip()
        source = str((matched_pending or {}).get("source") or "").strip()

        if cancelled:
            answer_text = "我已取消补充信息。"
        elif source == "skill_chip_direct" and skill_code:
            norm = normalize_chip_answers_for_continue(skill_code, answers)
            if skill_code == "requirement_to_test_points":
                if not norm.get("requirement_id") and not str(norm.get("content") or "").strip():
                    raise ValueError("请选择已有需求，或粘贴需求正文")
            if skill_code == "curl_to_cases" and not str(norm.get("curl") or "").strip():
                raise ValueError("请粘贴 curl 命令")
            if skill_code == "ui_locator_suggest" and not str(norm.get("raw_element") or "").strip():
                raise ValueError("请粘贴元素 outerHTML 或属性文本")
            if skill_code == "knowledge_qa" and not str(norm.get("query") or "").strip():
                raise ValueError("请填写资料库问题")
            answer_text = format_chip_answer_user_line(skill_code, answers)
            if chip_key:
                answer_text = f"{answer_text}（chip={chip_key}）"
        else:
            lines = [f"{k}={v}" for k, v in answers.items() if v is not None and str(v) != ""]
            q = str((matched_pending or {}).get("question") or "").strip()
            reason = str((matched_pending or {}).get("reason") or "").strip()
            prefix = f"针对提问「{q}」" if q else "我已补充"
            extra = f"（原因：{reason}）" if reason else ""
            answer_text = (
                f"{prefix}{extra}，补充："
                + ("；".join(lines) if lines else "（无字段）")
                + "。请继续刚才的请求。"
            )

        claimed = await try_claim_ask_answer(
            session_id=int(sid), ask_id=body.ask_id, user_id=int(user_id)
        )
        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该提问正在处理或已提交，请勿重复点击",
            )

        try:
            matched_msg["ask_user_done"] = True
            matched_msg["ask_user_answers"] = answers
            await save_session_messages(
                user_id,
                body.project_id,
                messages,
                session_id=sid,
            )
        except Exception:
            await release_ask_answer_claim(session_id=int(sid), ask_id=body.ask_id)
            matched_msg["ask_user_done"] = False
            matched_msg.pop("ask_user_answers", None)
            raise

        if not body.continue_chat:
            messages.append({"role": "user", "content": answer_text})
            await save_session_messages(
                user_id,
                body.project_id,
                messages,
                session_id=sid,
                title_hint=answer_text,
            )
            return StandardResponse(
                data={"session_id": sid, "answered": True, "continued": False},
                message="ok",
            )

        async def _rollback_ask_card() -> None:
            matched_msg["ask_user_done"] = False
            matched_msg.pop("ask_user_answers", None)
            if (
                messages
                and isinstance(messages[-1], dict)
                and messages[-1].get("role") == "user"
                and messages[-1].get("content") == answer_text
            ):
                messages.pop()
            await save_session_messages(
                user_id,
                body.project_id,
                messages,
                session_id=sid,
            )
            await release_ask_answer_claim(session_id=int(sid), ask_id=body.ask_id)

        if (
            not cancelled
            and chip_prefer_direct_run(skill_code, source)
            and body.project_id is not None
            and assist_premium_ready()
        ):
            from app.core.platform.datetime_utils import now_app
            from app.modules.assistant.assistant_tools import extract_pending_confirm
            from brickcore_assist import api as assist_api
            from brickcore_assist.orchestrator.cards import build_assistant_cards

            page_ctx = matched_page_context or body.page_context
            try:
                from brickcore_assist.skills.safe import sanitize_page_context

                page_ctx = sanitize_page_context(page_ctx)
            except Exception:
                page_ctx = page_ctx if isinstance(page_ctx, dict) else None

            ctx = await build_assistant_ctx(user_info)
            skill_kwargs = build_run_skill_kwargs_from_chip_answers(skill_code, answers)
            try:
                skill_result = await assist_api.run_skill(
                    ctx=ctx,
                    project_id=int(body.project_id),
                    entry_source="assistant",
                    run_mode="direct",
                    session_id=sid,
                    ai_config_id=None,
                    **{k: v for k, v in skill_kwargs.items() if k != "skill_code"},
                    skill_code=skill_code,
                )
            except Exception as exc:
                err = str(getattr(exc, "detail", None) or exc)
                if isinstance(getattr(exc, "detail", None), dict):
                    err = str(exc.detail.get("message") or exc.detail)
                await _rollback_ask_card()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=err[:500]
                ) from exc

            pending = extract_pending_confirm(
                "run_skill", skill_result if isinstance(skill_result, dict) else {}
            )
            content = ""
            if isinstance(skill_result, dict):
                content = (
                    str(skill_result.get("summary") or "")
                    or str(skill_result.get("answer") or "")
                    or str(skill_result.get("content") or "")
                )
            if not content and pending:
                content = "已生成预览确认卡，请确认后执行。"
            if not content:
                content = "技能已执行。"
            cards = build_assistant_cards(
                pending_confirm=pending,
                pending_ask_user=None,
                skills_used=[
                    {
                        "skill_code": skill_code,
                        "status": (skill_result or {}).get("status")
                        if isinstance(skill_result, dict)
                        else "",
                    }
                ],
            )
            user_msg = {
                "role": "user",
                "content": answer_text,
                "create_time": now_app().isoformat(),
            }
            asst_msg: dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "mode": "standard",
                "skills_used": [{"skill_code": skill_code}],
                "cards": cards,
                "message_id": f"m-{uuid.uuid4().hex[:16]}",
                "create_time": now_app().isoformat(),
            }
            if pending:
                asst_msg["pending_confirm"] = pending
            if page_ctx:
                asst_msg["page_context"] = page_ctx
            messages.append(user_msg)
            messages.append(asst_msg)
            await save_session_messages(
                user_id,
                body.project_id,
                messages,
                session_id=sid,
                title_hint=answer_text,
            )
            data: dict[str, Any] = {
                "session_id": sid,
                "content": content,
                "mode": "standard",
                "skills_used": [{"skill_code": skill_code}],
                "cards": cards,
                "ask_user_answered": True,
                "continued": True,
                "direct_skill": True,
            }
            if pending:
                data["pending_confirm"] = pending
            if isinstance(skill_result, dict) and skill_result.get("tokens_used") is not None:
                data["tokens_used"] = skill_result.get("tokens_used")
            try:
                from app.modules.assistant.assistant_trace import record_turn_trace

                await record_turn_trace(
                    session_id=sid,
                    user_id=user_id,
                    project_id=body.project_id,
                    mode="standard",
                    # rounds 用长度记「1 轮直跑」，供多轮分布统计；不含参数正文
                    trace={"stop_reason": "direct_skill", "rounds": [{"skill": skill_code}]},
                    tools_used=["run_skill"],
                    skills_used=[{"skill_code": skill_code}],
                    tokens_used=(
                        int(skill_result.get("tokens_used") or 0)
                        if isinstance(skill_result, dict)
                        else 0
                    ),
                    duration_ms=None,
                    has_pending_confirm=bool(pending),
                    has_pending_ask_user=False,
                )
            except Exception:
                logger.debug("record_turn_trace after direct skill skipped", exc_info=True)
            return StandardResponse(data=data, message="ok")

        page_ctx = matched_page_context or body.page_context
        try:
            from brickcore_assist.skills.safe import sanitize_page_context

            page_ctx = sanitize_page_context(page_ctx)
        except Exception:
            page_ctx = page_ctx if isinstance(page_ctx, dict) else None

        ctx = await build_assistant_ctx(user_info)
        try:
            if assist_premium_ready():
                from brickcore_assist import api as assist_api

                data = await assist_api.chat_standard(
                    ctx=ctx,
                    user_message=answer_text,
                    history=[],
                    project_id=body.project_id,
                    session_id=sid,
                    use_server_history=True,
                    page_context=page_ctx,
                )
            else:
                data = await run_assistant_chat(
                    ctx=ctx,
                    user_message=answer_text,
                    history=[],
                    project_id=body.project_id,
                    session_id=sid,
                    use_server_history=True,
                    page_context=page_ctx,
                )
                if isinstance(data, dict):
                    data = {**data, "mode": resolve_chat_mode()}
        except Exception:
            await _rollback_ask_card()
            raise
        if isinstance(data, dict):
            data = {**data, "ask_user_answered": True}
        return StandardResponse(data=data, message="ok")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[assistant] ask-user answer failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="回答提问失败，请稍后重试",
        ) from exc


@router.delete(
    "/session",
    summary="清空当前会话消息",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def delete_assistant_session(
    project_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    if session_id:
        await clear_session_messages(user_id, session_id)
    else:
        await clear_session(user_id, project_id)
    return StandardResponse(message="已清空会话消息")


@router.post(
    "/chat",
    summary="助手对话（一次性 JSON 返回）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def assistant_chat(
    req: AssistantChatRequest,
    user_info: dict = Depends(is_authenticated),
):
    try:
        ctx = await build_assistant_ctx(user_info)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # 传入 project_id 时必须是项目成员，避免仅凭全局 AI_TEST_VIEW 读跨项目数据
    if req.project_id is not None:
        await _assert_member(user_info, req.project_id)

    history = [{"role": h.role, "content": h.content} for h in req.history]
    try:
        if assist_premium_ready():
            from brickcore_assist import api as assist_api

            data = await assist_api.chat_standard(
                ctx=ctx,
                user_message=req.message.strip(),
                history=history,
                project_id=req.project_id,
                ai_config_id=req.ai_config_id,
                session_id=req.session_id,
                use_server_history=req.use_server_history,
                page_context=req.page_context,
            )
        else:
            data = await run_assistant_chat(
                ctx=ctx,
                user_message=req.message.strip(),
                history=history,
                project_id=req.project_id,
                ai_config_id=req.ai_config_id,
                session_id=req.session_id,
                use_server_history=req.use_server_history,
                page_context=req.page_context,
            )
            if isinstance(data, dict):
                data = {**data, "mode": resolve_chat_mode()}
        return StandardResponse(data=data, message="ok")
    except HTTPException:
        raise
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        try:
            from brickcore_assist.api import AssistBusyError

            if isinstance(exc, AssistBusyError):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=str(exc),
                ) from exc
        except ImportError:
            pass
        logger.exception("[assistant] chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="助手处理失败，请稍后重试",
        ) from exc


@router.get(
    "/jobs",
    summary="列出会话关联的长任务（W3 Job 桥）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_assistant_jobs(
    session_id: int = Query(..., description="会话 ID"),
    project_id: Optional[int] = Query(None),
    refresh: bool = Query(True, description="是否从外部任务刷新状态"),
    user_info: dict = Depends(is_authenticated),
):
    try:
        ctx = await build_assistant_ctx(user_info)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        from app.modules.assistant.assistant_jobs import list_session_jobs
        from app.modules.assistant.assistant_session import assert_session_belongs_to_project, get_session_row

        session = await get_session_row(ctx.user_id, int(session_id))
        if not session:
            raise ValueError("会话不存在或无权访问")
        if session.project_id:
            await _assert_member(user_info, session.project_id)
        await assert_session_belongs_to_project(ctx.user_id, int(session_id), project_id)

        jobs = await list_session_jobs(
            user_id=ctx.user_id,
            session_id=session_id,
            project_id=project_id if project_id is not None else session.project_id,
            refresh=refresh,
            notify=True,
        )
        return StandardResponse(data={"items": jobs, "total": len(jobs)})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/jobs/{link_id}/cancel",
    summary="取消会话关联的长任务",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def cancel_assistant_job(
    link_id: int,
    user_info: dict = Depends(is_authenticated),
):
    try:
        ctx = await build_assistant_ctx(user_info)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        from app.models.ai import AssistantJobLink
        from app.modules.assistant.assistant_jobs import cancel_session_job
        from app.modules.assistant.assistant_session import get_session_row

        link = await AssistantJobLink.get_or_none(id=int(link_id))
        if not link:
            raise ValueError("任务关联不存在")
        session = await get_session_row(ctx.user_id, int(link.session_id))
        if not session:
            raise ValueError("会话不存在或无权访问")
        if session.project_id:
            await _assert_member(user_info, session.project_id)

        job = await cancel_session_job(
            user_id=ctx.user_id,
            link_id=link_id,
            username=ctx.username or "",
        )
        return StandardResponse(data=job, message="已请求停止")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/memory",
    summary="列出项目记忆（W6）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_assistant_memory(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    await _assert_member(user_info, project_id)
    from app.modules.assistant.assistant_memory import list_memories

    items = await list_memories(user_id=int(user_id), project_id=int(project_id))
    return StandardResponse(data={"items": items, "total": len(items)})


@router.put(
    "/memory",
    summary="写入项目记忆（W6）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def put_assistant_memory(
    body: MemoryUpsertRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    await _assert_member(user_info, body.project_id)
    try:
        from app.modules.assistant.assistant_memory import upsert_memory

        data = await upsert_memory(
            user_id=int(user_id),
            project_id=int(body.project_id),
            key=body.key,
            value=body.value,
        )
        return StandardResponse(data=data, message="已保存")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/memory",
    summary="删除项目记忆（W6）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def delete_assistant_memory(
    project_id: int = Query(...),
    key: str = Query(..., min_length=1, max_length=64),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    await _assert_member(user_info, project_id)
    try:
        from app.modules.assistant.assistant_memory import delete_memory

        await delete_memory(user_id=int(user_id), project_id=int(project_id), key=key)
        return StandardResponse(message="已删除")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/memory/all",
    summary="清空当前项目全部记忆（W6）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def clear_assistant_memory(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    await _assert_member(user_info, project_id)
    from app.modules.assistant.assistant_memory import clear_all_memories

    deleted = await clear_all_memories(user_id=int(user_id), project_id=int(project_id))
    return StandardResponse(data={"deleted": deleted}, message="已清空")


@router.post(
    "/feedback",
    summary="小测回复点赞/点踩（W6）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def post_assistant_feedback(
    body: FeedbackRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        from app.modules.assistant.assistant_feedback import upsert_feedback
        from app.modules.assistant.assistant_session import get_session_row

        session = await get_session_row(int(user_id), int(body.session_id))
        if not session:
            raise ValueError("会话不存在或无权访问")
        if session.project_id:
            await _assert_member(user_info, session.project_id)
        if body.project_id is not None and session.project_id is not None:
            if int(body.project_id) != int(session.project_id):
                raise ValueError("project_id 与会话项目不匹配")

        data = await upsert_feedback(
            user_id=int(user_id),
            session_id=int(body.session_id),
            message_id=body.message_id,
            score=int(body.score),
            note=body.note or "",
            project_id=session.project_id,
        )
        return StandardResponse(data=data, message="已记录")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/feedback/summary",
    summary="小测反馈与 Prompt 效果汇总（AI-2）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_feedback_summary(
    days: int = Query(30, ge=1, le=90),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    # 按项目：成员可读；全局聚合：仅 AI 配置查看（避免普通用户看平台级效果）
    if project_id is not None:
        await _assert_member(user_info, project_id)
    else:
        if not user_info.get("is_superuser"):
            from app.core.platform.auth import _load_user_permission_codes

            uid = user_info.get("id")
            allowed = await _load_user_permission_codes(int(uid)) if uid else set()
            if AI_CONFIG_VIEW not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="查看全局反馈汇总需要 ai_config:view；请传 project_id 限定项目",
                )
    from app.modules.assistant.assistant_feedback import summarize_feedback_effectiveness

    data = await summarize_feedback_effectiveness(days=days, project_id=project_id)
    return StandardResponse(data=data)


@router.get(
    "/traces",
    summary="小测回合脱敏追踪（管理查询，无 Prompt）（W6）",
    dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))],
)
async def list_assistant_traces(
    project_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_info: dict = Depends(is_authenticated),
):
    me = user_info.get("id")
    if not me:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    if project_id is not None:
        await _assert_member(user_info, project_id)
    # 非超管强制只看自己的追踪，避免项目内横向窥视
    if not user_info.get("is_superuser"):
        user_id = int(me)
    from app.modules.assistant.assistant_trace import list_turn_traces

    data = await list_turn_traces(
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return StandardResponse(data=data)


@router.get(
    "/traces/{trace_id}",
    summary="小测回合脱敏追踪详情（无 Prompt）（W6）",
    dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))],
)
async def get_assistant_trace(
    trace_id: int,
    user_info: dict = Depends(is_authenticated),
):
    me = user_info.get("id")
    if not me:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    from app.modules.assistant.assistant_trace import get_turn_trace

    data = await get_turn_trace(trace_id=int(trace_id))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="追踪记录不存在")
    owner = data.get("user_id")
    if not user_info.get("is_superuser"):
        if owner is None or int(owner) != int(me):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该追踪")
    if data.get("project_id") is not None:
        await _assert_member(user_info, int(data["project_id"]))
    return StandardResponse(data=data)


@router.post(
    "/confirm",
    summary="确认执行助手 preview 操作",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def assistant_confirm(
    req: AssistantConfirmRequest,
    user_info: dict = Depends(is_authenticated),
):
    try:
        ctx = await build_assistant_ctx(user_info)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        data = await run_assistant_confirm(
            ctx=ctx,
            action=req.action.strip(),
            confirm_token=req.confirm_token.strip(),
            confirm_args=req.confirm_args or {},
            project_id=req.project_id,
            session_id=req.session_id,
        )
        return StandardResponse(data=data, message="ok")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[assistant] confirm failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"确认执行失败：{exc}",
        ) from exc


@router.post(
    "/confirm/cancel",
    summary="取消确认卡（落库，避免刷新回魂）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def cancel_assistant_confirm(
    body: CancelConfirmRequest,
    user_info: dict = Depends(is_authenticated),
):
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        from app.core.integration.mcp_confirm import consume_confirm_token
        from app.core.platform.auth import resolve_current_username
        from app.modules.assistant.assistant_session import (
            assert_session_belongs_to_project,
            save_session_messages,
        )

        if body.project_id is not None:
            await _assert_member(user_info, body.project_id)
        await assert_session_belongs_to_project(user_id, body.session_id, body.project_id)
        sid, messages = await load_session_messages(
            user_id, body.project_id, session_id=body.session_id
        )
        if not sid:
            raise ValueError("会话不存在")
        token = body.confirm_token.strip()
        action = body.action.strip()
        matched = False
        already_done = False
        for msg in reversed(messages):
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            pc = msg.get("pending_confirm")
            if not isinstance(pc, dict):
                continue
            if str(pc.get("action") or "") != action:
                continue
            if token and str(pc.get("confirm_token") or "") != token:
                continue
            if msg.get("confirm_done"):
                matched = True
                already_done = True
                break
            msg["confirm_done"] = True
            msg["confirm_cancelled"] = True
            matched = True
            break
        if not matched:
            raise ValueError("未找到对应的确认卡片，可能已过期")
        if already_done:
            return StandardResponse(data={"session_id": sid, "cancelled": True}, message="ok")
        try:
            uname = await resolve_current_username(user_info)
            await consume_confirm_token(token, action, uname)
        except Exception:
            pass
        messages.append(
            {
                "role": "assistant",
                "content": "已取消该操作。",
                "message_id": f"m-{uuid.uuid4().hex[:16]}",
            }
        )
        await save_session_messages(user_id, body.project_id, messages, session_id=sid)
        return StandardResponse(data={"session_id": sid, "cancelled": True}, message="ok")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
