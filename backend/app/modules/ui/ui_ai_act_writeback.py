"""AI Act 成功后将规划出的定位参数写回 UI 用例步骤。"""
from __future__ import annotations

from typing import Any

# 允许从 AI Act 写回用例的步骤参数字段（不含 value 等业务变量）
AI_ACT_WRITEBACK_PARAM_KEYS = frozenset({
    "locator",
    "selector",
    "start_selector",
    "end_selector",
    "first_locator",
    "second_locator",
    "source_position_x",
    "source_position_y",
    "target_position_x",
    "target_position_y",
    "first_index",
    "second_index",
    "index",
    "frame",
})


def extract_ai_act_writeback_patch(act_params: dict | None) -> dict[str, Any]:
    """从 AI Act 步骤 params 中提取可写回字段。"""
    if not isinstance(act_params, dict):
        return {}
    patch: dict[str, Any] = {}
    for key in AI_ACT_WRITEBACK_PARAM_KEYS:
        if key not in act_params:
            continue
        val = act_params[key]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        patch[key] = val
    return patch


def apply_ai_act_patch_to_step(step: dict, patch: dict[str, Any]) -> dict[str, str]:
    """将 patch 合并进步骤 params，返回变更摘要。"""
    if not patch:
        return {}
    params = step.get("params")
    if not isinstance(params, dict):
        params = {}
        step["params"] = params

    changes: dict[str, str] = {}
    for key, new_val in patch.items():
        old_val = params.get(key)
        if old_val == new_val:
            continue
        params[key] = new_val
        changes[key] = f"{old_val or '—'} → {new_val}"

    # locator / selector 二选一，与自愈写回一致
    if "locator" in patch:
        params.pop("selector", None)
    elif "selector" in patch:
        params.pop("locator", None)

    return changes
