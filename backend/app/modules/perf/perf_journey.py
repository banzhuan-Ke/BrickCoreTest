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
            delay_mode = str(step.get("delay_mode") or "fixed").strip().lower()
            if delay_mode not in ("fixed", "random"):
                delay_mode = "fixed"
            steps.append({
                "case_id": case_id,
                "delay_ms": int(step.get("delay_ms") or 0),
                "delay_mode": delay_mode,
                "delay_ms_min": int(step.get("delay_ms_min") or 0),
                "delay_ms_max": int(step.get("delay_ms_max") or 0),
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
                "delay_mode": step.get("delay_mode", "fixed"),
                "delay_ms_min": step.get("delay_ms_min", 0),
                "delay_ms_max": step.get("delay_ms_max", 0),
            })
    return items


LAYOUT_SINGLE_PHASE = "single_phase"
LAYOUT_PER_CASE_PHASE = "per_case_phase"


def suite_cases_to_journey(
    cases: list[dict],
    *,
    layout: str = LAYOUT_SINGLE_PHASE,
    suite_name: str = "",
) -> dict:
    """将套件用例列表转为 journey 配置。

    cases 项至少含 ``case_id``；可选 ``case_name`` / ``name`` 用于阶段命名。
    layout:
      - single_phase: 单阶段，步骤按序
      - per_case_phase: 每用例一个阶段
    """
    layout = (layout or LAYOUT_SINGLE_PHASE).strip()
    if layout not in (LAYOUT_SINGLE_PHASE, LAYOUT_PER_CASE_PHASE):
        layout = LAYOUT_SINGLE_PHASE

    ordered: list[dict] = []
    for raw in cases or []:
        cid = _safe_case_id(raw.get("case_id") if isinstance(raw, dict) else raw)
        if cid is None:
            continue
        name = ""
        if isinstance(raw, dict):
            name = (raw.get("case_name") or raw.get("name") or "").strip()
        ordered.append({"case_id": cid, "name": name})

    if layout == LAYOUT_PER_CASE_PHASE:
        phases = []
        for i, item in enumerate(ordered):
            phases.append({
                "name": item["name"] or f"阶段{i + 1}",
                "execution": "serial",
                "sync_before": False,
                "max_parallel": 6,
                "steps": [{
                    "case_id": item["case_id"],
                    "delay_ms": 0,
                    "use_stream": False,
                    "order": 0,
                }],
            })
    else:
        phase_name = (suite_name or "业务链路").strip() or "业务链路"
        steps = [
            {
                "case_id": item["case_id"],
                "delay_ms": 0,
                "use_stream": False,
                "order": i,
            }
            for i, item in enumerate(ordered)
        ]
        phases = [{
            "name": phase_name,
            "execution": "serial",
            "sync_before": False,
            "max_parallel": 6,
            "steps": steps,
        }] if steps else []

    return normalize_journey_config({
        "journey": {
            "stop_on_step_fail": True,
            "delay_between_journeys_ms": 0,
            "phases": phases,
        }
    })



async def run_one_journey(*_args, **_kwargs):
    """占位：施压体仅在 Runner；Backend 调用必失败，防止误用。"""
    raise RuntimeError(
        "Journey 施压已迁至 Runner Worker，Backend 不再本机执行链路压测。"
    )
