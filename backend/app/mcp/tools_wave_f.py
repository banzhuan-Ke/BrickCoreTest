"""MCP Wave F：操作日志 / 看板统计 / 资产搜索 / 测试管理（发布·缺陷·评审）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.permissions import (
    AI_CONFIG_VIEW,
    OPERATION_LOG_VIEW,
    TEST_DEFECT_EDIT,
    TEST_DEFECT_VIEW,
    TEST_RELEASE_EDIT,
    TEST_RELEASE_VIEW,
    TEST_REVIEW_MANAGE,
    TEST_REVIEW_SUBMIT,
    TEST_REVIEW_VIEW,
)
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER
from app.mcp.auth import McpAuthContext, ensure_permission


def _clip(text: Any, limit: int = 300) -> str:
    s = ("" if text is None else str(text)).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _http_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _ctx_user_info(ctx: McpAuthContext) -> dict[str, Any]:
    return {
        "id": ctx.user_id,
        "username": ctx.username or "",
        "is_superuser": bool(ctx.is_superuser or ctx.is_api_key),
        "is_api_key": bool(ctx.is_api_key),
    }


async def _ensure_users_exist(user_ids: list[int], *, label: str = "用户") -> None:
    """预检：指定用户须存在（至少存在性，避免写库后才 422）。"""
    ids = sorted({int(x) for x in (user_ids or []) if x is not None})
    if not ids:
        return
    from app.models.sys import User

    found = await User.filter(id__in=ids, is_del=False).values_list("id", flat=True)
    missing = [i for i in ids if i not in set(found)]
    if missing:
        raise ValueError(f"{label}不存在: {missing}")


async def _require_project(ctx: McpAuthContext, project_id: int, *, member: bool = False) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(
        ctx,
        int(project_id),
        min_role=PROJECT_ROLE_MEMBER if member else PROJECT_ROLE_VIEWER,
    )


async def _await_svc(coro):
    from fastapi import HTTPException

    try:
        return await coro
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc


def _unwrap(resp: Any) -> Any:
    data = getattr(resp, "data", None)
    if data is not None:
        return data
    if isinstance(resp, dict) and "data" in resp:
        return resp.get("data")
    return resp


# ---------- 日志 / 统计 / 搜索 ----------


async def tool_list_operation_logs(
    ctx: McpAuthContext,
    page: int = 1,
    size: int = 20,
    username: str = "",
    module: str = "",
    action: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    """列出平台操作日志（不含请求体 params）。"""
    ensure_permission(ctx, OPERATION_LOG_VIEW)
    from app.routers.sys.operation_logs import get_operation_logs

    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    return await get_operation_logs(
        page=page,
        size=size,
        username=(username or "").strip() or None,
        module=(module or "").strip() or None,
        action=(action or "").strip() or None,
        start_date=(start_date or "").strip() or None,
        end_date=(end_date or "").strip() or None,
    )


async def tool_list_assistant_traces(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
    session_id: Optional[int] = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    """列出小测回合追踪（不含 Prompt / 用户正文）。"""
    ensure_permission(ctx, AI_CONFIG_VIEW)
    if project_id:
        await _require_project(ctx, int(project_id))
    from app.modules.assistant.assistant_trace import list_turn_traces

    user_id = None if (ctx.is_superuser or ctx.is_api_key) else ctx.user_id
    return await list_turn_traces(
        project_id=int(project_id) if project_id else None,
        user_id=user_id,
        session_id=int(session_id) if session_id else None,
        limit=min(max(int(limit or 30), 1), 100),
        offset=max(int(offset or 0), 0),
    )


async def tool_get_dashboard_summary(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    """获取首页看板摘要（指定项目须为成员；全平台仅超管/API Key）。"""
    if project_id:
        await _require_project(ctx, int(project_id))
    elif not (ctx.is_superuser or ctx.is_api_key):
        raise ValueError("全平台看板摘要仅管理员可用，请传 project_id")

    from app.routers.sys.dashboard import get_dashboard

    raw = await get_dashboard(
        start_date=(start_date or "").strip() or None,
        end_date=(end_date or "").strip() or None,
        project_id=int(project_id) if project_id else None,
    )
    # 压缩：保留摘要字段，截断大列表
    out = {
        "date_range": raw.get("date_range"),
        "stats": raw.get("stats"),
        "case_proportion": raw.get("case_proportion"),
        "execution_proportion": raw.get("execution_proportion"),
        "ai_summary": raw.get("ai_summary"),
        "token_stats": raw.get("token_stats"),
        "pending_cron_jobs": (raw.get("pending_cron_jobs") or [])[:10],
        "top_failed_cases": (raw.get("top_failed_cases") or [])[:10],
        "perf_top_failed_scenes": (raw.get("perf_top_failed_scenes") or [])[:8],
        "recent_executions": (raw.get("recent_executions") or [])[:10],
        "user_activity_top": (raw.get("user_activity_top") or [])[:5],
        "generate_trend": raw.get("generate_trend"),
    }
    return out


async def tool_search_project_assets(
    ctx: McpAuthContext,
    project_id: int,
    q: str,
    limit: int = 8,
) -> dict[str, Any]:
    """项目内资产关键词搜索（用例/套件/计划/接口等）。"""
    pid = await _require_project(ctx, project_id)
    keyword = (q or "").strip()
    if not keyword:
        raise ValueError("搜索关键词不能为空")
    from app.routers.sys.search import project_search

    resp = await project_search(
        project_id=pid,
        q=keyword[:100],
        limit=min(max(int(limit or 8), 1), 30),
        username=ctx.username or "",
    )
    data = _unwrap(resp)
    return data if isinstance(data, dict) else {"raw": data}


# ---------- 测试管理：发布 ----------


async def tool_list_releases(
    ctx: McpAuthContext,
    project_id: int,
    status: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """列出项目发布版本。"""
    ensure_permission(ctx, TEST_RELEASE_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.service import list_releases, release_to_dict

    rows = await _await_svc(
        list_releases(
            pid,
            status=(status or "").strip() or None,
            keyword=(keyword or "").strip() or None,
        )
    )
    all_items = [release_to_dict(r) for r in rows]
    return {"total": len(all_items), "items": all_items[:50], "truncated": len(all_items) > 50, "project_id": pid}


async def tool_get_release(ctx: McpAuthContext, project_id: int, release_id: int) -> dict[str, Any]:
    """获取发布版本详情。"""
    ensure_permission(ctx, TEST_RELEASE_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.service import get_release_or_404, release_to_dict

    row = await _await_svc(get_release_or_404(int(release_id), pid))
    return release_to_dict(row)


async def tool_preview_create_release(
    ctx: McpAuthContext,
    project_id: int,
    release_key: str,
    name: str,
    description: str = "",
    owner_id: Optional[int] = None,
    external_url: str = "",
) -> dict[str, Any]:
    """预览创建发布版本。"""
    ensure_permission(ctx, TEST_RELEASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    key = (release_key or "").strip()
    title = (name or "").strip()
    if not key or not title:
        raise ValueError("release_key 与 name 必填")
    impact = {
        "project_id": pid,
        "release_key": _clip(key, 80),
        "name": _clip(title, 80),
        "description": _clip(description, 200),
        "owner_id": int(owner_id) if owner_id else None,
        "external_url": _clip(external_url, 200),
        "warning": "将创建 draft 状态的发布版本",
    }
    token = await create_confirm_token(
        "create_release",
        {
            "project_id": pid,
            "release_key": key,
            "name": title,
            "description": (description or "").strip(),
            "owner_id": int(owner_id) if owner_id else None,
            "external_url": (external_url or "").strip() or None,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_release 并传入 confirm_token",
    }


async def tool_confirm_create_release(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    release_key: str,
    name: str,
    description: str = "",
    owner_id: Optional[int] = None,
    external_url: str = "",
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_RELEASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "create_release", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("release_key") or "") != (release_key or "").strip():
        raise ValueError("release_key 与确认 Token 不匹配")
    if (payload.get("name") or "") != (name or "").strip():
        raise ValueError("name 与确认 Token 不匹配")
    if (payload.get("description") or "") != (description or "").strip():
        raise ValueError("description 与确认 Token 不匹配")
    tok_owner = payload.get("owner_id")
    if (int(tok_owner) if tok_owner is not None else None) != (int(owner_id) if owner_id else None):
        raise ValueError("owner_id 与确认 Token 不匹配")
    if (payload.get("external_url") or None) != ((external_url or "").strip() or None):
        raise ValueError("external_url 与确认 Token 不匹配")

    from app.modules.test_management.service import create_release, release_to_dict

    row = await _await_svc(
        create_release(
            project_id=pid,
            release_key=payload["release_key"],
            name=payload["name"],
            username=ctx.username or "",
            description=(payload.get("description") or "").strip() or None,
            owner_id=int(tok_owner) if tok_owner is not None else None,
            external_url=payload.get("external_url") or None,
        )
    )
    return {"ok": True, "release": release_to_dict(row)}


async def tool_preview_transition_release(
    ctx: McpAuthContext,
    project_id: int,
    release_id: int,
    target_status: str,
) -> dict[str, Any]:
    """预览发布版本状态流转。"""
    ensure_permission(ctx, TEST_RELEASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    from app.modules.test_management.service import get_release_or_404, release_to_dict

    row = await _await_svc(get_release_or_404(int(release_id), pid))
    target = (target_status or "").strip()
    if not target:
        raise ValueError("target_status 必填")
    impact = {
        "project_id": pid,
        "release_id": row.id,
        "release_key": row.release_key,
        "name": row.name,
        "from_status": row.status,
        "to_status": target,
        "warning": "将变更发布版本状态，可能影响缺陷/评审范围",
    }
    token = await create_confirm_token(
        "transition_release",
        {"project_id": pid, "release_id": int(row.id), "target_status": target},
        ctx.username,
    )
    return {
        "impact": impact,
        "current": release_to_dict(row),
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_transition_release 并传入 confirm_token",
    }


async def tool_confirm_transition_release(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    release_id: int,
    target_status: str,
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_RELEASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "transition_release", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("release_id") or 0) != int(release_id):
        raise ValueError("release_id 与确认 Token 不匹配")
    if (payload.get("target_status") or "") != (target_status or "").strip():
        raise ValueError("target_status 与确认 Token 不匹配")

    from app.modules.test_management.service import (
        get_release_or_404,
        release_to_dict,
        transition_release,
    )

    row = await _await_svc(get_release_or_404(int(release_id), pid))
    updated, warnings = await _await_svc(
        transition_release(row, (target_status or "").strip(), ctx.username or "")
    )
    return {"ok": True, "release": release_to_dict(updated), "warnings": warnings or []}


# ---------- 测试管理：缺陷 ----------


async def tool_list_defects(
    ctx: McpAuthContext,
    project_id: int,
    release_id: Optional[int] = None,
    status: str = "",
    keyword: str = "",
    severity: str = "",
    assignee_id: Optional[int] = None,
) -> dict[str, Any]:
    """列出项目缺陷。"""
    ensure_permission(ctx, TEST_DEFECT_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.defect_service import list_defects

    items = await _await_svc(
        list_defects(
            pid,
            release_id=int(release_id) if release_id else None,
            status=(status or "").strip() or None,
            keyword=(keyword or "").strip() or None,
            severity=(severity or "").strip() or None,
            assignee_id=int(assignee_id) if assignee_id else None,
            with_links=True,
        )
    )
    all_items = list(items or [])
    return {
        "total": len(all_items),
        "items": all_items[:50],
        "truncated": len(all_items) > 50,
        "project_id": pid,
    }


async def tool_get_defect(ctx: McpAuthContext, project_id: int, defect_id: int) -> dict[str, Any]:
    """获取缺陷详情（含关联与流转记录摘要）。"""
    ensure_permission(ctx, TEST_DEFECT_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.defect_service import get_defect_detail, get_defect_or_404

    row = await _await_svc(get_defect_or_404(int(defect_id), pid))
    detail = await _await_svc(get_defect_detail(row))
    # 截断活动/评论
    if isinstance(detail, dict):
        detail["comments"] = (detail.get("comments") or [])[:20]
        detail["activities"] = (detail.get("activities") or [])[:30]
        if detail.get("description"):
            detail["description"] = _clip(detail.get("description"), 2000)
    return detail


async def tool_preview_create_defect(
    ctx: McpAuthContext,
    project_id: int,
    title: str,
    description: str = "",
    severity: str = "major",
    priority: str = "p2",
    release_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览创建缺陷。"""
    ensure_permission(ctx, TEST_DEFECT_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    t = (title or "").strip()
    if not t:
        raise ValueError("标题必填")
    if assignee_id:
        await _ensure_users_exist([int(assignee_id)], label="经办人")
    impact = {
        "project_id": pid,
        "title": _clip(t, 120),
        "severity": (severity or "major").strip(),
        "priority": (priority or "p2").strip(),
        "release_id": int(release_id) if release_id else None,
        "assignee_id": int(assignee_id) if assignee_id else None,
        "description": _clip(description, 200),
        "warning": "将创建一条缺陷工单",
    }
    token = await create_confirm_token(
        "create_defect",
        {
            "project_id": pid,
            "title": t,
            "description": (description or "").strip(),
            "severity": (severity or "major").strip(),
            "priority": (priority or "p2").strip(),
            "release_id": int(release_id) if release_id else None,
            "assignee_id": int(assignee_id) if assignee_id else None,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_defect 并传入 confirm_token",
    }


async def tool_confirm_create_defect(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    title: str,
    description: str = "",
    severity: str = "major",
    priority: str = "p2",
    release_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_DEFECT_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "create_defect", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("title") or "") != (title or "").strip():
        raise ValueError("title 与确认 Token 不匹配")
    if (payload.get("description") or "") != (description or "").strip():
        raise ValueError("description 与确认 Token 不匹配")
    if (payload.get("severity") or "major") != (severity or "major").strip():
        raise ValueError("severity 与确认 Token 不匹配")
    if (payload.get("priority") or "p2") != (priority or "p2").strip():
        raise ValueError("priority 与确认 Token 不匹配")
    tok_release = payload.get("release_id")
    if (int(tok_release) if tok_release is not None else None) != (int(release_id) if release_id else None):
        raise ValueError("release_id 与确认 Token 不匹配")
    tok_assignee = payload.get("assignee_id")
    if (int(tok_assignee) if tok_assignee is not None else None) != (int(assignee_id) if assignee_id else None):
        raise ValueError("assignee_id 与确认 Token 不匹配")

    from app.modules.test_management.defect_service import create_defect, defect_to_dict

    row = await _await_svc(
        create_defect(
            project_id=pid,
            title=payload["title"],
            username=ctx.username or "",
            release_id=int(tok_release) if tok_release is not None else None,
            description=(payload.get("description") or "").strip() or None,
            severity=(payload.get("severity") or "major").strip(),
            priority=(payload.get("priority") or "p2").strip(),
            assignee_id=int(tok_assignee) if tok_assignee is not None else None,
            reporter_id=ctx.user_id,
            actor_user_id=ctx.user_id,
        )
    )
    return {"ok": True, "defect": defect_to_dict(row)}


async def tool_preview_transition_defect(
    ctx: McpAuthContext,
    project_id: int,
    defect_id: int,
    to_status: str,
    comment: str = "",
    assignee_id: Optional[int] = None,
    force: bool = False,
) -> dict[str, Any]:
    """预览缺陷状态流转。"""
    ensure_permission(ctx, TEST_DEFECT_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    from app.modules.test_management.defect_service import defect_to_dict, get_defect_or_404

    row = await _await_svc(get_defect_or_404(int(defect_id), pid))
    target = (to_status or "").strip()
    if not target:
        raise ValueError("to_status 必填")
    # 与 Web 一致：仅超管 / MCP API Key 可 force，普通用户传 force 无效
    can_force = bool(ctx.is_superuser or ctx.is_api_key)
    effective_force = bool(force) and can_force
    if force and not can_force:
        raise ValueError("仅超级管理员可强制流转非本人负责的缺陷（force）")
    if assignee_id:
        await _ensure_users_exist([int(assignee_id)], label="经办人")
    impact = {
        "project_id": pid,
        "defect_id": row.id,
        "defect_key": row.defect_key,
        "title": _clip(row.title, 120),
        "from_status": row.status,
        "to_status": target,
        "assignee_id": int(assignee_id) if assignee_id else None,
        "force": effective_force,
        "warning": (
            "将强制变更缺陷状态（管理员）"
            if effective_force
            else "将变更缺陷状态；非负责人可能被拒绝"
        ),
    }
    token = await create_confirm_token(
        "transition_defect",
        {
            "project_id": pid,
            "defect_id": int(row.id),
            "to_status": target,
            "comment": (comment or "").strip(),
            "assignee_id": int(assignee_id) if assignee_id else None,
            "force": effective_force,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "current": defect_to_dict(row),
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_transition_defect 并传入 confirm_token",
    }


async def tool_confirm_transition_defect(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    defect_id: int,
    to_status: str,
    comment: str = "",
    assignee_id: Optional[int] = None,
    force: bool = False,
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_DEFECT_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "transition_defect", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("defect_id") or 0) != int(defect_id):
        raise ValueError("defect_id 与确认 Token 不匹配")
    if (payload.get("to_status") or "") != (to_status or "").strip():
        raise ValueError("to_status 与确认 Token 不匹配")
    if (payload.get("comment") or "") != (comment or "").strip():
        raise ValueError("comment 与确认 Token 不匹配")
    tok_assignee = payload.get("assignee_id")
    if (int(tok_assignee) if tok_assignee is not None else None) != (int(assignee_id) if assignee_id else None):
        raise ValueError("assignee_id 与确认 Token 不匹配")
    if bool(payload.get("force")) != bool(force):
        raise ValueError("force 与确认 Token 不匹配")
    # 与 Web 路由一致：仅超管/API Key 可 force；忽略客户端自行抬权
    use_force = bool(payload.get("force")) and bool(ctx.is_superuser or ctx.is_api_key)

    from app.modules.test_management.defect_service import (
        defect_to_dict,
        get_defect_or_404,
        transition_defect,
    )

    row = await _await_svc(get_defect_or_404(int(payload["defect_id"]), pid))
    updated = await _await_svc(
        transition_defect(
            row,
            to_status=(payload.get("to_status") or "").strip(),
            username=ctx.username or "",
            actor_user_id=ctx.user_id,
            comment=(payload.get("comment") or "").strip() or None,
            assignee_id=int(tok_assignee) if tok_assignee is not None else None,
            force=use_force,
        )
    )
    return {"ok": True, "defect": defect_to_dict(updated)}


# ---------- 测试管理：用例评审 ----------


async def tool_list_reviews(
    ctx: McpAuthContext,
    project_id: int,
    release_id: Optional[int] = None,
    status: str = "",
) -> dict[str, Any]:
    """列出用例评审批次。"""
    ensure_permission(ctx, TEST_REVIEW_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.review_service import list_reviews, review_to_dict

    rows = await _await_svc(
        list_reviews(
            pid,
            release_id=int(release_id) if release_id else None,
            status=(status or "").strip() or None,
        )
    )
    all_items = [review_to_dict(r) for r in rows]
    return {
        "total": len(all_items),
        "items": all_items[:50],
        "truncated": len(all_items) > 50,
        "project_id": pid,
    }


async def tool_get_review(ctx: McpAuthContext, project_id: int, review_id: int) -> dict[str, Any]:
    """获取用例评审详情与条目统计。"""
    ensure_permission(ctx, TEST_REVIEW_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.review_service import (
        build_review_stats,
        get_review_or_404,
        list_review_items,
        review_to_dict,
    )

    review = await _await_svc(get_review_or_404(int(review_id), pid))
    items = await _await_svc(list_review_items(review))
    stats = build_review_stats(review, items)
    item_total = len(items or [])
    # 条目摘要截断
    slim = []
    for it in (items or [])[:40]:
        slim.append(
            {
                "id": it.get("id"),
                "functional_case_id": it.get("functional_case_id"),
                "case_title": _clip(it.get("case_title"), 120),
                "decision": it.get("decision"),
                "owner_decision": it.get("owner_decision"),
            }
        )
    return {
        "review": review_to_dict(review),
        "stats": stats,
        "items": slim,
        "item_total": item_total,
        "returned_count": len(slim),
        "truncated": item_total > len(slim),
    }


async def tool_preview_create_review(
    ctx: McpAuthContext,
    project_id: int,
    title: str,
    functional_case_ids: list[int],
    reviewer_ids: list[int],
    release_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览创建用例评审批次。"""
    ensure_permission(ctx, TEST_REVIEW_MANAGE)
    pid = await _require_project(ctx, project_id, member=True)
    name = (title or "").strip()
    if not name:
        raise ValueError("评审标题必填")
    case_ids = [int(x) for x in (functional_case_ids or [])]
    rev_ids = [int(x) for x in (reviewer_ids or [])]
    if not case_ids:
        raise ValueError("请选择功能用例")
    if not rev_ids:
        raise ValueError("请选择评审人")
    if len(case_ids) > 100:
        raise ValueError("单次最多 100 条用例")
    await _ensure_users_exist(rev_ids, label="评审人")
    impact = {
        "project_id": pid,
        "title": _clip(name, 120),
        "case_count": len(case_ids),
        "reviewer_count": len(rev_ids),
        "release_id": int(release_id) if release_id else None,
        "warning": "将创建用例评审批次并通知评审人",
    }
    token = await create_confirm_token(
        "create_review",
        {
            "project_id": pid,
            "title": name,
            "functional_case_ids": case_ids,
            "reviewer_ids": rev_ids,
            "release_id": int(release_id) if release_id else None,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_review 并传入 confirm_token",
    }


async def tool_confirm_create_review(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    title: str,
    functional_case_ids: list[int],
    reviewer_ids: list[int],
    release_id: Optional[int] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_REVIEW_MANAGE)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "create_review", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("title") or "") != (title or "").strip():
        raise ValueError("title 与确认 Token 不匹配")
    tok_cases = [int(x) for x in (payload.get("functional_case_ids") or [])]
    tok_reviewers = [int(x) for x in (payload.get("reviewer_ids") or [])]
    if tok_cases != [int(x) for x in (functional_case_ids or [])]:
        raise ValueError("functional_case_ids 与确认 Token 不匹配")
    if tok_reviewers != [int(x) for x in (reviewer_ids or [])]:
        raise ValueError("reviewer_ids 与确认 Token 不匹配")
    tok_release = payload.get("release_id")
    if (int(tok_release) if tok_release is not None else None) != (int(release_id) if release_id else None):
        raise ValueError("release_id 与确认 Token 不匹配")

    from app.modules.test_management.review_service import create_review, review_to_dict

    row = await _await_svc(
        create_review(
            project_id=pid,
            title=payload["title"],
            functional_case_ids=tok_cases,
            reviewer_ids=tok_reviewers,
            username=ctx.username or "",
            release_id=int(tok_release) if tok_release is not None else None,
        )
    )
    from app.modules.test_management.review_service import notify_review_created

    notified = True
    try:
        await notify_review_created(row, actor_user_id=ctx.user_id)
    except Exception:
        # 通知失败不回滚创建；与 Web 侧 soft 通知一致
        notified = False
    return {"ok": True, "review": review_to_dict(row), "notified": notified}


async def tool_preview_submit_review_decision(
    ctx: McpAuthContext,
    project_id: int,
    review_id: int,
    item_id: int,
    decision: str,
    comment: str = "",
    checklist_result: Optional[dict] = None,
    reviewer_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览提交评审条目结论。"""
    ensure_permission(ctx, TEST_REVIEW_SUBMIT)
    pid = await _require_project(ctx, project_id, member=True)
    from app.modules.test_management.review_service import get_review_or_404, review_to_dict

    review = await _await_svc(get_review_or_404(int(review_id), pid))
    dec = (decision or "").strip()
    if not dec:
        raise ValueError("decision 必填")
    if not ctx.user_id:
        raise ValueError("MCP API Key 无法提交评审结论，请使用登录 JWT")
    effective_reviewer = int(ctx.user_id)
    if reviewer_id is not None and int(reviewer_id) != int(ctx.user_id):
        if not ctx.is_superuser:
            raise ValueError("仅超级管理员可代他人提交评审结论")
        effective_reviewer = int(reviewer_id)
    impact = {
        "project_id": pid,
        "review_id": review.id,
        "item_id": int(item_id),
        "decision": dec,
        "comment": _clip(comment, 200),
        "reviewer_id": effective_reviewer,
        "has_checklist_result": bool(checklist_result),
        "warning": "将以指定评审人身份提交该评审条目结论",
    }
    token = await create_confirm_token(
        "submit_review_decision",
        {
            "project_id": pid,
            "review_id": int(review.id),
            "item_id": int(item_id),
            "decision": dec,
            "comment": (comment or "").strip(),
            "reviewer_id": effective_reviewer,
            "checklist_result": checklist_result if isinstance(checklist_result, dict) else None,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "review": review_to_dict(review),
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_submit_review_decision 并传入 confirm_token",
    }


async def tool_confirm_submit_review_decision(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    review_id: int,
    item_id: int,
    decision: str,
    comment: str = "",
    checklist_result: Optional[dict] = None,
    reviewer_id: Optional[int] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_REVIEW_SUBMIT)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "submit_review_decision", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("review_id") or 0) != int(review_id):
        raise ValueError("review_id 与确认 Token 不匹配")
    if int(payload.get("item_id") or 0) != int(item_id):
        raise ValueError("item_id 与确认 Token 不匹配")
    if (payload.get("decision") or "") != (decision or "").strip():
        raise ValueError("decision 与确认 Token 不匹配")
    if (payload.get("comment") or "") != (comment or "").strip():
        raise ValueError("comment 与确认 Token 不匹配")
    tok_reviewer = int(payload.get("reviewer_id") or 0)
    if reviewer_id is not None and int(reviewer_id) != tok_reviewer:
        raise ValueError("reviewer_id 与确认 Token 不匹配")
    tok_checklist = payload.get("checklist_result")
    if checklist_result is not None and checklist_result != tok_checklist:
        raise ValueError("checklist_result 与确认 Token 不匹配")
    if not ctx.user_id:
        raise ValueError("MCP API Key 无法提交评审结论，请使用登录 JWT")
    allow_delegate = bool(ctx.is_superuser) and tok_reviewer != int(ctx.user_id)

    from app.modules.test_management.review_service import get_review_or_404, submit_item_decision

    review = await _await_svc(get_review_or_404(int(payload["review_id"]), pid))
    item = await _await_svc(
        submit_item_decision(
            review=review,
            item_id=int(payload["item_id"]),
            reviewer_id=tok_reviewer,
            decision=(payload.get("decision") or "").strip(),
            comment=(payload.get("comment") or "").strip() or None,
            checklist_result=tok_checklist if isinstance(tok_checklist, dict) else None,
            username=ctx.username or "",
            auth_user_id=ctx.user_id,
            allow_delegate=allow_delegate,
        )
    )
    return {
        "ok": True,
        "item_id": getattr(item, "id", int(payload["item_id"])),
        "decision": getattr(item, "decision", payload.get("decision")),
    }


async def tool_preview_finalize_review(
    ctx: McpAuthContext,
    project_id: int,
    review_id: int,
    decision: str,
    comment: str = "",
) -> dict[str, Any]:
    """预览用例评审批次最终定版。"""
    ensure_permission(ctx, TEST_REVIEW_MANAGE)
    pid = await _require_project(ctx, project_id, member=True)
    from app.modules.test_management.review_service import get_review_or_404, review_to_dict

    review = await _await_svc(get_review_or_404(int(review_id), pid))
    dec = (decision or "").strip()
    if dec not in ("approved", "changes_requested", "rejected"):
        raise ValueError("decision 须为 approved / changes_requested / rejected")
    impact = {
        "project_id": pid,
        "review_id": review.id,
        "title": _clip(review.title, 120),
        "decision": dec,
        "comment": _clip(comment, 200),
        "warning": "将最终裁定该评审批次，不可重复操作",
    }
    token = await create_confirm_token(
        "finalize_review",
        {
            "project_id": pid,
            "review_id": int(review.id),
            "decision": dec,
            "comment": (comment or "").strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "review": review_to_dict(review),
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_finalize_review 并传入 confirm_token",
    }


async def tool_confirm_finalize_review(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    review_id: int,
    decision: str,
    comment: str = "",
) -> dict[str, Any]:
    ensure_permission(ctx, TEST_REVIEW_MANAGE)
    pid = await _require_project(ctx, project_id, member=True)
    payload = await consume_confirm_token(confirm_token, "finalize_review", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("review_id") or 0) != int(review_id):
        raise ValueError("review_id 与确认 Token 不匹配")
    if (payload.get("decision") or "") != (decision or "").strip():
        raise ValueError("decision 与确认 Token 不匹配")
    if (payload.get("comment") or "") != (comment or "").strip():
        raise ValueError("comment 与确认 Token 不匹配")

    from app.modules.test_management.review_service import (
        finalize_review,
        get_review_or_404,
        review_to_dict,
    )

    review = await _await_svc(get_review_or_404(int(payload["review_id"]), pid))
    updated = await _await_svc(
        finalize_review(
            review,
            decision=(payload.get("decision") or "").strip(),
            comment=(payload.get("comment") or "").strip() or None,
            username=ctx.username or "",
            actor_user_id=ctx.user_id,
            is_manager=True,
        )
    )
    return {"ok": True, "review": review_to_dict(updated)}
