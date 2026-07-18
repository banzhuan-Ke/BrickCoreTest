"""业务链路压测（Journey）配置规范化与构建辅助。

链路施压执行体在闭源 Runner Worker；本模块只保留配置归一化与场景构建，
不得再写入可独立复现的施压循环。
"""
from __future__ import annotations

from typing import Optional

JOURNEY_FIXED_MODE = "journey_fixed"
JOURNEY_LOOP_MODE = "journey_loop"
JOURNEY_MODES = (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE)


def is_journey_mode(mode: Optional[str]) -> bool:
    return (mode or "").strip() in JOURNEY_MODES


def _safe_case_id(raw) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def normalize_journey_config(config: dict) -> dict:
    """从场景 config 提取并规范化 journey 配置。"""
    raw = config.get("journey") or {}
    phases = []
    for i, phase in enumerate(raw.get("phases") or []):
        steps = []
        for j, step in enumerate(phase.get("steps") or []):
            case_id = _safe_case_id(step.get("case_id"))
            if case_id is None:
                continue
            steps.append({
                "case_id": case_id,
                "delay_ms": int(step.get("delay_ms") or 0),
                "use_stream": bool(step.get("use_stream")),
                "order": int(step.get("order", j)),
            })
        steps.sort(key=lambda s: s["order"])
        phases.append({
            "name": (phase.get("name") or f"阶段{i + 1}").strip(),
            "execution": (phase.get("execution") or "serial").strip(),
            "sync_before": bool(phase.get("sync_before")),
            "max_parallel": max(1, min(int(phase.get("max_parallel") or 6), 50)),
            "steps": steps,
        })
    return {
        "stop_on_step_fail": bool(raw.get("stop_on_step_fail", True)),
        "delay_between_journeys_ms": int(raw.get("delay_between_journeys_ms") or 0),
        "phases": phases,
    }


def journey_has_sync_barrier(config: dict) -> bool:
    journey = normalize_journey_config(config)
    return any(p.get("sync_before") for p in journey.get("phases") or [])


def collect_journey_case_ids(config: dict) -> list[int]:
    journey = normalize_journey_config(config)
    ids: list[int] = []
    seen: set[int] = set()
    for phase in journey["phases"]:
        for step in phase["steps"]:
            cid = step["case_id"]
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
    return ids


def journey_to_scene_items(config: dict) -> list[dict]:
    """将 journey 步骤扁平化为 scene_items（兼容快照与 Worker）。"""
    journey = normalize_journey_config(config)
    items: list[dict] = []
    seen: set[int] = set()
    for phase in journey["phases"]:
        for step in phase["steps"]:
            cid = step["case_id"]
            if cid in seen:
                continue
            seen.add(cid)
            items.append({
                "case_id": cid,
                "weight": 1,
                "delay_ms": step.get("delay_ms", 0),
            })
    return items


async def run_one_journey(*_args, **_kwargs):
    """占位：施压体仅在 Runner；Backend 调用必失败，防止误用。"""
    raise RuntimeError(
        "Journey 施压已迁至 Runner Worker，Backend 不再本机执行链路压测。"
    )
