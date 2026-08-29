"""Browser Lab 导入策略评估：快速转换 vs Agent 固化。"""
from __future__ import annotations

from typing import Any

from app.modules.browser_dispatch.run_mode import analyze_import_steps

_ELEMENT_METHODS = frozenset({"click_ele", "fill_value", "select_option", "hover_ele"})


def _cache_strength_stats(actions: list | None) -> dict[str, int]:
    strong = heuristic = weak = 0
    for act in actions or []:
        if not isinstance(act, dict):
            continue
        op = (act.get("op") or "").lower()
        if op not in ("click", "fill", "select"):
            continue
        strength = (act.get("strength") or "").strip().lower()
        if strength == "strong":
            strong += 1
        elif strength == "weak":
            weak += 1
        else:
            heuristic += 1
    return {"strong": strong, "heuristic": heuristic, "weak": weak}


def build_browser_lab_import_plan(
    *,
    task_status: str,
    steps: list[dict] | None,
    cache_actions: list | None = None,
    cache_hit: bool = False,
    engine: str = "",
) -> dict[str, Any]:
    """产出推荐导入模式与说明文案。"""
    step_meta = analyze_import_steps(steps)
    total = len(steps or [])
    element_steps = [
        s for s in (steps or []) if isinstance(s, dict) and (s.get("method") in _ELEMENT_METHODS)
    ]
    with_candidates = sum(
        1
        for s in element_steps
        if isinstance(s.get("meta"), dict) and (s.get("meta") or {}).get("candidates")
    )
    harvested = sum(
        1
        for s in element_steps
        if isinstance(s.get("meta"), dict) and (s.get("meta") or {}).get("element_harvest")
    )

    cache_stats = _cache_strength_stats(cache_actions)
    has_cache = bool(cache_actions)
    weak = int(step_meta.get("weak_locator_count") or 0)
    element_count = max(1, len(element_steps))
    weak_ratio = weak / element_count

    modes: list[dict[str, Any]] = []

    if has_cache:
        modes.append(
            {
                "id": "quick_cache",
                "label": "快速转换（动作缓存）",
                "description": "使用 BL-1 动作缓存中的 selector，适合二次执行或缓存命中任务。",
                "quality": "high" if cache_stats["strong"] >= 2 else "medium",
            }
        )

    modes.append(
        {
            "id": "quick_steps",
            "label": "快速转换（执行记录）",
            "description": "由 step_log + Runner 采集的多定位候选生成；可在导入前切换备选定位。",
            "quality": "high" if weak == 0 and with_candidates else ("medium" if weak <= 2 else "low"),
        }
    )

    modes.append(
        {
            "id": "solidify",
            "label": "Agent 重新固化",
            "description": "重新跑 Playwright UI Agent，产出可回归定位器；页面复杂或弱定位多时使用。",
            "quality": "high",
        }
    )

    recommended = "quick_steps"
    reason = "可根据执行记录快速生成草稿，导入后核对定位。"

    if task_status not in ("done", "failed", "stopped"):
        recommended = "none"
        reason = "任务尚未结束，请等待执行完成后再导入。"
    elif has_cache and (cache_hit or engine == "action_cache") and cache_stats["strong"] >= 1:
        recommended = "quick_cache"
        reason = (
            f"任务已写入动作缓存（强定位 {cache_stats['strong']} 步），"
            "优先使用缓存步骤，无需再跑 Agent。"
        )
    elif weak == 0 and (with_candidates >= 2 or harvested >= 2):
        recommended = "quick_steps"
        reason = (
            f"执行记录含 {with_candidates or harvested} 步多定位候选，"
            "可直接快速导入并在表格中切换备选定位。"
        )
    elif weak >= 3 or weak_ratio >= 0.6:
        recommended = "solidify"
        reason = f"有 {weak} 步为启发式/索引定位，建议 Agent 固化后再导入正式用例。"
    elif weak >= 1:
        recommended = "quick_steps"
        reason = f"仅 {weak} 步需核对定位；可先快速导入，不满意再 Agent 固化。"

    return {
        **step_meta,
        "import_plan": {
            "recommended_mode": recommended,
            "reason": reason,
            "modes": modes,
            "cache_available": has_cache,
            "cache_stats": cache_stats,
            "steps_with_candidates": with_candidates,
            "harvested_step_count": harvested,
            "element_step_count": len(element_steps),
            "total_step_count": total,
            "weak_ratio": round(weak_ratio, 2),
        },
    }
