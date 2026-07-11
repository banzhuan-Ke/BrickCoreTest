"""平台 AI 助手 — 服务端多会话持久化"""
from __future__ import annotations

from typing import Any

from app.models.ai import AssistantSession

MAX_SESSION_MESSAGES = 40
MAX_SESSIONS_PER_USER_PROJECT = 30
MAX_SESSION_LIST = 50


def _normalize_project_id(project_id: int | None) -> int | None:
    if project_id is None or project_id <= 0:
        return None
    return project_id


def _is_default_session_title(title: str) -> bool:
    t = (title or "").strip()
    if not t or t == "新对话":
        return True
    return t.startswith("会话 #")


def _derive_title(title_hint: str, messages: list[dict[str, Any]]) -> str:
    hint = (title_hint or "").strip()
    if hint:
        return hint[:80] + ("…" if len(hint) > 80 else "")
    for item in messages:
        if item.get("role") == "user":
            content = (item.get("content") or "").strip()
            if content:
                return content[:80] + ("…" if len(content) > 80 else "")
    return "新对话"


def _session_to_dict(session: AssistantSession) -> dict[str, Any]:
    msgs = session.messages if isinstance(session.messages, list) else []
    title = (session.title or "").strip()
    if _is_default_session_title(title) and msgs:
        title = _derive_title("", msgs)
    elif not title:
        title = f"会话 #{session.id}"
    return {
        "id": session.id,
        "project_id": session.project_id,
        "title": title,
        "message_count": len(msgs),
        "preview": _preview_from_messages(msgs),
        "create_time": session.create_time.strftime("%Y-%m-%d %H:%M:%S") if session.create_time else "",
        "update_time": session.update_time.strftime("%Y-%m-%d %H:%M:%S") if session.update_time else "",
    }


def _preview_from_messages(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            text = (item.get("content") or "").strip()
            if text:
                return text[:60] + ("…" if len(text) > 60 else "")
    return ""


async def _enforce_session_limit(user_id: int, project_id: int | None) -> None:
    pid = _normalize_project_id(project_id)
    qs = AssistantSession.filter(user_id=user_id, project_id=pid)
    count = await qs.count()
    if count < MAX_SESSIONS_PER_USER_PROJECT:
        return
    overflow = count - MAX_SESSIONS_PER_USER_PROJECT + 1
    old_rows = await qs.order_by("update_time").limit(overflow)
    for row in old_rows:
        await row.delete()


async def list_sessions(
    user_id: int,
    project_id: int | None,
    *,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    pid = _normalize_project_id(project_id)
    qs = AssistantSession.filter(user_id=user_id, project_id=pid)
    rows = await qs.order_by("-update_time").limit(MAX_SESSION_LIST)
    items = [_session_to_dict(row) for row in rows]
    kw = (keyword or "").strip().lower()
    if not kw:
        return items
    return [_session_to_dict(row) for row in rows if _session_matches_keyword(row, kw)]


def _session_matches_keyword(session: AssistantSession, kw: str) -> bool:
    item = _session_to_dict(session)
    if kw in (item.get("title") or "").lower() or kw in (item.get("preview") or "").lower():
        return True
    msgs = session.messages if isinstance(session.messages, list) else []
    for msg in msgs:
        if kw in (msg.get("content") or "").lower():
            return True
    return False


async def create_session(
    user_id: int,
    project_id: int | None,
    *,
    title: str = "新对话",
) -> dict[str, Any]:
    pid = _normalize_project_id(project_id)
    await _enforce_session_limit(user_id, pid)
    session = await AssistantSession.create(
        user_id=user_id,
        project_id=pid,
        title=(title or "新对话")[:200],
        messages=[],
    )
    return _session_to_dict(session)


async def get_session_row(user_id: int, session_id: int) -> AssistantSession | None:
    return await AssistantSession.get_or_none(id=session_id, user_id=user_id)


async def load_session_messages(
    user_id: int,
    project_id: int | None = None,
    *,
    session_id: int | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    session: AssistantSession | None = None
    if session_id:
        session = await get_session_row(user_id, session_id)
    else:
        pid = _normalize_project_id(project_id)
        session = (
            await AssistantSession.filter(user_id=user_id, project_id=pid)
            .order_by("-update_time")
            .first()
        )
    if not session:
        return None, []
    msgs = session.messages if isinstance(session.messages, list) else []
    return session.id, msgs


async def save_session_messages(
    user_id: int,
    project_id: int | None,
    messages: list[dict[str, Any]],
    *,
    session_id: int | None = None,
    title_hint: str = "",
) -> int:
    pid = _normalize_project_id(project_id)
    trimmed = messages[-MAX_SESSION_MESSAGES:]
    session: AssistantSession | None = None

    if session_id:
        session = await get_session_row(user_id, session_id)

    if not session:
        await _enforce_session_limit(user_id, pid)
        session = await AssistantSession.create(
            user_id=user_id,
            project_id=pid,
            title=_derive_title(title_hint, trimmed),
            messages=trimmed,
        )
        return session.id

    session.messages = trimmed
    if session.project_id != pid:
        session.project_id = pid
    if _is_default_session_title(session.title or "") or not (session.title or "").strip():
        session.title = _derive_title(title_hint, trimmed)[:200]
    await session.save(update_fields=["messages", "project_id", "title", "update_time"])
    return session.id


async def update_session_title(user_id: int, session_id: int, title: str) -> dict[str, Any]:
    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    session.title = (title or "新对话").strip()[:200]
    await session.save(update_fields=["title", "update_time"])
    return _session_to_dict(session)


async def clear_session_messages(user_id: int, session_id: int) -> None:
    session = await get_session_row(user_id, session_id)
    if not session:
        return
    session.messages = []
    await session.save(update_fields=["messages", "update_time"])


async def delete_session(user_id: int, session_id: int) -> None:
    session = await get_session_row(user_id, session_id)
    if session:
        await session.delete()


async def clear_session(user_id: int, project_id: int | None) -> None:
    """兼容旧 API：清空该项目下最近一条会话的消息。"""
    sid, _ = await load_session_messages(user_id, project_id)
    if sid:
        await clear_session_messages(user_id, sid)
