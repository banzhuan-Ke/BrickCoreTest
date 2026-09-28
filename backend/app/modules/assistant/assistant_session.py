"""平台 AI 助手 — 服务端多会话持久化"""
from __future__ import annotations

import re
from typing import Any

from app.models.ai import AssistantSession

MAX_SESSION_MESSAGES = 40
MAX_SESSIONS_PER_USER_PROJECT = 30
MAX_SESSION_LIST = 50
SUMMARY_TRIGGER = 16  # 超过此数时把更早消息折叠进 summary_text（可被平台配置覆盖）
SUMMARY_KEEP_TAIL = 12
SUMMARY_MAX_CHARS = 4000

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_JSON_BLOB_RE = re.compile(r"\{[^{}]{400,}\}")


def _scrub_for_summary(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    text = _CODE_FENCE_RE.sub("[代码/JSON 已省略]", text)
    text = _JSON_BLOB_RE.sub("{…}", text)
    if len(text) > 240:
        text = text[:240] + "…"
    return text


def _fold_messages_into_summary(
    existing_summary: str | None,
    dropped: list[dict[str, Any]],
) -> str:
    """确定性摘要：不调 LLM，避免额外 Token；长 JSON/代码块先擦除。"""
    lines: list[str] = []
    prev = (existing_summary or "").strip()
    if prev:
        lines.append(prev)
    for item in dropped:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or ""
        content = _scrub_for_summary(item.get("content") or "")
        if role not in ("user", "assistant") or not content:
            continue
        label = "用户" if role == "user" else "助手"
        lines.append(f"[{label}] {content}")
    text = "\n".join(lines).strip()
    if len(text) > SUMMARY_MAX_CHARS:
        text = "…\n" + text[-(SUMMARY_MAX_CHARS - 2) :]
    return text


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
        "pinned_count": _pinned_count(session.pinned_context_json),
        "create_time": session.create_time.strftime("%Y-%m-%d %H:%M:%S") if session.create_time else "",
        "update_time": session.update_time.strftime("%Y-%m-%d %H:%M:%S") if session.update_time else "",
    }


def _pinned_count(raw: Any) -> int:
    if not isinstance(raw, dict):
        return 0
    items = raw.get("items")
    return len(items) if isinstance(items, list) else 0


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


async def assert_session_belongs_to_project(
    user_id: int,
    session_id: int,
    project_id: int | None,
) -> None:
    """会话必须属于当前用户与项目；不匹配立即失败，避免跨项目历史进入 LLM。"""
    session = await get_session_row(user_id, int(session_id))
    if not session:
        raise ValueError("会话不存在")
    pid = _normalize_project_id(project_id)
    if session.project_id != pid:
        raise ValueError("会话不属于当前项目，请新建会话或切换回原项目")


async def load_session_messages(
    user_id: int,
    project_id: int | None = None,
    *,
    session_id: int | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    session: AssistantSession | None = None
    if session_id:
        await assert_session_belongs_to_project(user_id, session_id, project_id)
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


def _is_open_interaction_message(item: dict[str, Any] | None) -> bool:
    """未完成的 AskUser / Confirm 卡不可被摘要折叠掉。"""
    if not isinstance(item, dict) or item.get("role") != "assistant":
        return False
    pending_ask = item.get("pending_ask_user")
    if isinstance(pending_ask, dict) and not item.get("ask_user_done"):
        return True
    pending_confirm = item.get("pending_confirm")
    if (
        isinstance(pending_confirm, dict)
        and pending_confirm.get("confirm_token")
        and not item.get("confirm_done")
    ):
        return True
    return False


def _partition_messages_for_summary(
    messages: list[dict[str, Any]],
    *,
    trigger: int | None = None,
    keep_tail: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """超过阈值时折叠更早消息；强制保留未完成交互卡。"""
    working = list(messages)
    trig = int(trigger) if trigger is not None else SUMMARY_TRIGGER
    keep = int(keep_tail) if keep_tail is not None else SUMMARY_KEEP_TAIL
    trig = max(8, min(40, trig))
    keep = max(6, min(24, keep))
    if len(working) <= trig:
        return [], working
    keep_from = max(0, len(working) - keep)
    for i, item in enumerate(working):
        if i >= keep_from:
            break
        if _is_open_interaction_message(item):
            keep_from = i
            break
    # 若保护后仍过长，至少保住全部 open 卡 + 尾部
    if len(working) - keep_from > MAX_SESSION_MESSAGES:
        open_idxs = [i for i, m in enumerate(working) if _is_open_interaction_message(m)]
        if open_idxs:
            keep_from = min(open_idxs[0], max(0, len(working) - keep))
    dropped = working[:keep_from]
    kept = working[keep_from:]
    return dropped, kept


async def _resolve_summary_trigger() -> int:
    try:
        from app.core.platform.platform_settings_service import (
            get_platform_settings,
            normalize_assist_session_summary_trigger,
        )

        settings = await get_platform_settings()
        return normalize_assist_session_summary_trigger(
            settings.get("assist_session_summary_trigger")
        )
    except Exception:
        return SUMMARY_TRIGGER


async def save_session_messages(
    user_id: int,
    project_id: int | None,
    messages: list[dict[str, Any]],
    *,
    session_id: int | None = None,
    title_hint: str = "",
) -> int:
    pid = _normalize_project_id(project_id)
    session: AssistantSession | None = None

    if session_id:
        session = await get_session_row(user_id, session_id)
        if session and session.project_id != pid:
            # 禁止跨项目静默迁移会话，避免历史上下文串项目
            raise ValueError("会话不属于当前项目，请新建会话或切换回原项目")

    # W6：长会话把溢出消息折叠进 summary_text（不调 LLM）
    summary_text = ((session.summary_text if session else None) or "")
    trigger = await _resolve_summary_trigger()
    dropped, working = _partition_messages_for_summary(
        list(messages),
        trigger=trigger,
        keep_tail=max(6, min(24, trigger - 4)),
    )
    if dropped:
        summary_text = _fold_messages_into_summary(summary_text, dropped)
    trimmed = working[-MAX_SESSION_MESSAGES:]
    # 尾部硬裁时仍尽量保住 open 交互卡
    if any(_is_open_interaction_message(m) for m in working) and not any(
        _is_open_interaction_message(m) for m in trimmed
    ):
        opens = [m for m in working if _is_open_interaction_message(m)]
        trimmed = (opens + trimmed)[-MAX_SESSION_MESSAGES:]

    if not session:
        await _enforce_session_limit(user_id, pid)
        session = await AssistantSession.create(
            user_id=user_id,
            project_id=pid,
            title=_derive_title(title_hint, trimmed),
            messages=trimmed,
            summary_text=summary_text or None,
        )
        return session.id

    session.messages = trimmed
    session.summary_text = summary_text or None
    if _is_default_session_title(session.title or "") or not (session.title or "").strip():
        session.title = _derive_title(title_hint, trimmed)[:200]
    await session.save(update_fields=["messages", "title", "summary_text", "update_time"])
    return session.id


async def get_session_summary(user_id: int, session_id: int) -> str:
    session = await get_session_row(user_id, session_id)
    if not session:
        return ""
    return (session.summary_text or "").strip()


async def update_session_title(user_id: int, session_id: int, title: str) -> dict[str, Any]:
    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    session.title = (title or "新对话").strip()[:200]
    await session.save(update_fields=["title", "update_time"])
    return _session_to_dict(session)


async def clear_session_messages(user_id: int, session_id: int) -> None:
    """清空消息、摘要与钉住上下文（产品语义：清空本会话交互状态）。"""
    session = await get_session_row(user_id, session_id)
    if not session:
        return
    session.messages = []
    session.summary_text = None
    session.pinned_context_json = None
    await session.save(
        update_fields=["messages", "summary_text", "pinned_context_json", "update_time"]
    )
    try:
        from app.modules.assistant.assistant_jobs import detach_session_jobs

        await detach_session_jobs(int(session_id))
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("[assistant_session] detach jobs failed session=%s", session_id)


async def delete_session(user_id: int, session_id: int) -> None:
    session = await get_session_row(user_id, session_id)
    if session:
        await session.delete()


async def clear_session(user_id: int, project_id: int | None) -> None:
    """兼容旧 API：清空该项目下最近一条会话的消息。"""
    sid, _ = await load_session_messages(user_id, project_id)
    if sid:
        await clear_session_messages(user_id, sid)


async def get_pinned_context(user_id: int, session_id: int) -> dict[str, Any]:
    from app.modules.assistant.assistant_pin import normalize_pinned_payload

    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    return normalize_pinned_payload(session.pinned_context_json)


async def set_pinned_context(
    user_id: int,
    session_id: int,
    project_id: int | None,
    pinned: dict[str, Any],
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.modules.assistant.assistant_pin import normalize_pinned_payload

    await assert_session_belongs_to_project(user_id, session_id, project_id)
    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    data = normalize_pinned_payload(pinned)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.pinned_context_json = data
    await session.save(update_fields=["pinned_context_json", "update_time"])
    return data


async def pin_context_item(
    user_id: int,
    session_id: int,
    project_id: int | None,
    *,
    entity_type: str,
    entity_id: Any,
    label: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.modules.assistant.assistant_pin import (
        MAX_PINNED_ITEMS,
        normalize_pinned_payload,
        pin_item_payload,
    )

    await assert_session_belongs_to_project(user_id, session_id, project_id)
    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    current = normalize_pinned_payload(session.pinned_context_json)
    new_item = pin_item_payload(
        entity_type=entity_type,
        entity_id=entity_id,
        label=label,
        meta=meta,
    )
    items = [
        it
        for it in current["items"]
        if not (it.get("type") == new_item["type"] and str(it.get("id")) == str(new_item["id"]))
    ]
    items.insert(0, new_item)
    data = {
        "items": items[:MAX_PINNED_ITEMS],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    session.pinned_context_json = data
    await session.save(update_fields=["pinned_context_json", "update_time"])
    return data


async def unpin_context_item(
    user_id: int,
    session_id: int,
    project_id: int | None,
    *,
    entity_type: str,
    entity_id: Any,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.modules.assistant.assistant_pin import normalize_pinned_payload, pin_item_payload

    await assert_session_belongs_to_project(user_id, session_id, project_id)
    session = await get_session_row(user_id, session_id)
    if not session:
        raise ValueError("会话不存在")
    target = pin_item_payload(entity_type=entity_type, entity_id=entity_id)
    current = normalize_pinned_payload(session.pinned_context_json)
    items = [
        it
        for it in current["items"]
        if not (it.get("type") == target["type"] and str(it.get("id")) == str(target["id"]))
    ]
    data = {
        "items": items,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    session.pinned_context_json = data
    await session.save(update_fields=["pinned_context_json", "update_time"])
    return data
