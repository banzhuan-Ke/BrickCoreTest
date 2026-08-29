"""用例标签归一与 quarantine 约定。"""
from __future__ import annotations

from typing import Any, Iterable

QUARANTINE_TAG = "quarantine"


def normalize_tags(raw: Any) -> list[str]:
    """JSON 列表或逗号串 → 去空白、去空项；保留原大小写，去重保序。"""
    parts: list[str] = []
    if raw is None:
        items: Iterable[Any] = []
    elif isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = [raw]
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(text)
    return parts


def has_quarantine(raw: Any) -> bool:
    return any(t.lower() == QUARANTINE_TAG for t in normalize_tags(raw))


def set_quarantine(raw: Any, enabled: bool) -> list[str]:
    tags = [t for t in normalize_tags(raw) if t.lower() != QUARANTINE_TAG]
    if enabled:
        tags.append(QUARANTINE_TAG)
    return tags
