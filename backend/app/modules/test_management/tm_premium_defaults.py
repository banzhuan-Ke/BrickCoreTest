"""扩展包未安装时的开源默认值（与 brickcore_tm 内默认对齐，供设置页只读展示）。"""
from __future__ import annotations

from typing import Any

DEFAULT_TM_NOTIFY_SETTINGS: dict[str, Any] = {
    "inbox_enabled": True,
    "external_enabled": True,
    "external_channels": ["email", "dingtalk"],
    "on_scope_owner_assigned": False,
    "on_defect_assigned": True,
    "on_review_invited": True,
    "on_plan_run_item_assigned": True,
    "on_review_item_pending": True,
    "on_quality_gate_failed": True,
    "default_scope_owner_id": None,
    "digest_minutes": 5,
}

DEFAULT_QUALITY_RULES: dict[str, Any] = {
    "required_completion_min": 1.0,
    "required_pass_rate_min": 0.95,
    "blocker_open_max": 0,
    "critical_open_max": 0,
    "high_risk_without_result_max": 0,
}

DEFAULT_USER_NOTIFY_PREFS: dict[str, Any] = {
    "inbox_enabled": True,
    "external_enabled": True,
    "im_at_enabled": True,
    "muted_events": [],
    "dnd_enabled": False,
    "dnd_start": "22:00",
    "dnd_end": "08:00",
    "dnd_mute_inbox": False,
    "dnd_timezone": "Asia/Shanghai",
}
