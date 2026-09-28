"""小测回合脱敏追踪（W6；禁止存 Prompt / 用户正文 / tool arguments）。"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.models.ai import AssistantTurnTrace

logger = logging.getLogger(__name__)

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _safe_code(raw: Any) -> str | None:
    s = str(raw or "").strip()[:64]
    if not s or not _SAFE_CODE_RE.match(s):
        return None
    return s


def _safe_skills(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:20]:
        if isinstance(item, dict):
            code = _safe_code(item.get("code") or item.get("skill_code"))
            status = _safe_code(item.get("status")) or ""
            if code:
                out.append({"code": code, "status": status[:32]})
        elif isinstance(item, str):
            code = _safe_code(item)
            if code:
                out.append({"code": code, "status": ""})
    return out


def _safe_tools(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw[:40]:
        # 拒绝 dict / 带空格长句（可能混入用户输入）
        if isinstance(x, dict):
            name = _safe_code(x.get("name") or x.get("tool"))
        else:
            name = _safe_code(x)
        if name:
            out.append(name)
    return out


def _safe_stop_reason(raw: Any) -> str | None:
    code = _safe_code(raw)
    if not code:
        return None
    # 未知 stop_reason 也允许短 code，但不允许空格/中文长句
    if " " in code or len(code) > 64:
        return None
    return code


async def record_turn_trace(
    *,
    session_id: int | None,
    user_id: int | None,
    project_id: int | None,
    mode: str = "standard",
    trace: dict[str, Any] | None = None,
    tools_used: list[str] | None = None,
    skills_used: list | None = None,
    tokens_used: int | None = None,
    duration_ms: int | None = None,
    has_pending_confirm: bool = False,
    has_pending_ask_user: bool = False,
    error_code: str | None = None,
) -> int | None:
    """落库脱敏 trace；失败静默但可观测（不影响主对话）。

    契约：仅枚举 / ID / 布尔 / 数字 / 短 code；禁止用户 content、arguments、result、error 正文。
    """
    try:
        tr = trace if isinstance(trace, dict) else {}
        # 故意不落库完整 rounds 明细（可能含 args/result）
        rounds_raw = tr.get("rounds")
        rounds_n = len(rounds_raw) if isinstance(rounds_raw, list) else None
        mode_s = _safe_code(mode) or "standard"
        if mode_s not in ("standard", "lite"):
            mode_s = "standard"
        row = await AssistantTurnTrace.create(
            session_id=int(session_id) if session_id else None,
            user_id=int(user_id) if user_id else None,
            project_id=int(project_id) if project_id else None,
            mode=mode_s[:16],
            stop_reason=_safe_stop_reason(tr.get("stop_reason")),
            tools_used=_safe_tools(tools_used),
            skills_used=_safe_skills(skills_used),
            rounds=rounds_n,
            tokens_used=int(tokens_used) if tokens_used is not None else None,
            duration_ms=int(duration_ms) if duration_ms is not None else None,
            has_pending_confirm=bool(has_pending_confirm),
            has_pending_ask_user=bool(has_pending_ask_user),
            error_code=_safe_code(error_code),
        )
        return row.id
    except Exception:
        logger.warning("[assistant_trace] record failed", exc_info=True)
        return None


def _trace_to_dict(r: AssistantTurnTrace) -> dict[str, Any]:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "user_id": r.user_id,
        "project_id": r.project_id,
        "mode": r.mode,
        "stop_reason": r.stop_reason,
        "tools_used": r.tools_used or [],
        "skills_used": r.skills_used or [],
        "rounds": r.rounds,
        "tokens_used": r.tokens_used,
        "duration_ms": r.duration_ms,
        "has_pending_confirm": bool(r.has_pending_confirm),
        "has_pending_ask_user": bool(r.has_pending_ask_user),
        "error_code": r.error_code,
        "create_time": r.create_time.isoformat() if r.create_time else None,
    }


async def _enrich_trace_display(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """补全项目名称、用户昵称展示（保留 id 字段便于排查）。"""
    if not items:
        return items
    from app.models.sys import Project, User
    from app.modules.ai.ai_dashboard_stats import build_user_display_name

    pids = {int(i["project_id"]) for i in items if i.get("project_id")}
    uids = {int(i["user_id"]) for i in items if i.get("user_id")}
    project_map: dict[int, str] = {}
    user_map: dict[int, str] = {}
    if pids:
        rows = await Project.filter(id__in=list(pids), is_del=False).values("id", "name")
        project_map = {int(r["id"]): (r.get("name") or "").strip() for r in rows}
    if uids:
        rows = await User.filter(id__in=list(uids), is_del=False).values(
            "id", "username", "nickname"
        )
        for r in rows:
            user_map[int(r["id"])] = build_user_display_name(
                r.get("username") or "", r.get("nickname")
            )
    for item in items:
        pid = item.get("project_id")
        if pid:
            item["project_name"] = project_map.get(int(pid), "") or f"#{pid}"
        else:
            item["project_name"] = "—"
        uid = item.get("user_id")
        if uid:
            item["user_display"] = user_map.get(int(uid), "") or f"#{uid}"
        else:
            item["user_display"] = "—"
    return items


async def list_turn_traces(
    *,
    project_id: int | None = None,
    user_id: int | None = None,
    session_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    qs = AssistantTurnTrace.all()
    if project_id is not None:
        qs = qs.filter(project_id=int(project_id))
    if user_id is not None:
        qs = qs.filter(user_id=int(user_id))
    if session_id is not None:
        qs = qs.filter(session_id=int(session_id))
    total = await qs.count()
    rows = await qs.order_by("-id").offset(max(0, offset)).limit(min(max(limit, 1), 100))
    items = await _enrich_trace_display([_trace_to_dict(r) for r in rows])
    return {"total": total, "items": items}


async def get_turn_trace(*, trace_id: int) -> dict[str, Any] | None:
    row = await AssistantTurnTrace.get_or_none(id=int(trace_id))
    if not row:
        return None
    items = await _enrich_trace_display([_trace_to_dict(row)])
    return items[0] if items else None
