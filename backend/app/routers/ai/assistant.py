"""平台内 AI 助手（Phase 4：多会话 + 页面上下文 + 写操作 confirm + 执行回传）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.modules.assistant.assistant_agent import build_assistant_ctx, run_assistant_chat, run_assistant_confirm
from app.modules.assistant.assistant_session import (
    clear_session,
    clear_session_messages,
    create_session,
    delete_session,
    list_sessions,
    load_session_messages,
    update_session_title,
)
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_VIEW
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["AI助手"])


class AssistantHistoryItem(BaseModel):
    role: str = Field(description="user 或 assistant")
    content: str = ""


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    project_id: Optional[int] = None
    history: list[AssistantHistoryItem] = Field(default_factory=list)
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


class CreateSessionRequest(BaseModel):
    project_id: Optional[int] = None
    title: str = Field(default="新对话", max_length=200)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


QUICK_PROMPTS = [
    {"key": "overview", "label": "项目概览", "message": "请总结当前项目的完整情况，包括环境、模块、需求和用例库规模。"},
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
]


@router.get(
    "/quick-prompts",
    summary="助手快捷提问",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_quick_prompts():
    return StandardResponse(data={"items": QUICK_PROMPTS})


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
    return StandardResponse(
        data={
            "session_id": sid,
            "messages": messages,
            "project_id": project_id,
        }
    )


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

    history = [{"role": h.role, "content": h.content} for h in req.history]
    try:
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
        return StandardResponse(data=data, message="ok")
    except HTTPException:
        raise
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[assistant] chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"助手处理失败：{exc}",
        ) from exc


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
