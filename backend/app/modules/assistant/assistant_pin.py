"""会话钉住上下文（W2）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ALLOWED_PIN_TYPES = frozenset(
    {
        "plan",
        "suite",
        "api_suite",
        "case",
        "ui_case",
        "ui_suite",
        "ui_plan",
        "app_case",
        "app_plan",
        "api",
        "requirement",
        "env",
        "device",
        "perf_scene",
        "record",
        "api_run_record",
        "ui_suite_run",
    }
)
MAX_PINNED_ITEMS = 8


def _normalize_pin_type(value: str) -> str:
    t = (value or "").strip().lower()
    aliases = {
        "api_plan": "plan",
        "ui_task": "ui_plan",
        "task": "ui_plan",
        "api_definition": "api",
        "environment": "env",
        "online_device": "device",
    }
    return aliases.get(t, t)


def normalize_pinned_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"items": [], "updated_at": None}
    items_in = raw.get("items") if isinstance(raw.get("items"), list) else []
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for it in items_in:
        if not isinstance(it, dict):
            continue
        etype = _normalize_pin_type(str(it.get("type") or ""))
        if etype not in ALLOWED_PIN_TYPES:
            continue
        eid = it.get("id")
        if eid is None or str(eid).strip() == "":
            continue
        key = (etype, str(eid))
        if key in seen:
            continue
        seen.add(key)
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        clean_meta: dict[str, Any] = {}
        for k in list(meta.keys())[:12]:
            key = str(k)[:40]
            val = meta[k]
            if isinstance(val, (int, float, bool)) or val is None:
                clean_meta[key] = val
            else:
                clean_meta[key] = str(val)[:120]
        items.append(
            {
                "type": etype,
                "id": eid if isinstance(eid, int) else str(eid)[:64],
                "label": str(it.get("label") or f"{etype}#{eid}")[:120],
                "meta": clean_meta,
            }
        )
        if len(items) >= MAX_PINNED_ITEMS:
            break
    return {
        "items": items,
        "updated_at": raw.get("updated_at"),
    }


def pin_item_payload(
    *,
    entity_type: str,
    entity_id: Any,
    label: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    etype = _normalize_pin_type(entity_type)
    if etype not in ALLOWED_PIN_TYPES:
        raise ValueError(f"不支持钉住类型：{entity_type}")
    if entity_id is None or str(entity_id).strip() == "":
        raise ValueError("entity_id 必填")
    return {
        "type": etype,
        "id": int(entity_id) if str(entity_id).isdigit() else str(entity_id)[:64],
        "label": (label or f"{etype}#{entity_id}")[:120],
        "meta": meta if isinstance(meta, dict) else {},
    }
