"""业务链路压测（Journey）通用编排与聚合。"""
from __future__ import annotations

import asyncio
import copy
from typing import Any, Awaitable, Callable, Optional

import numpy as np

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


class PhaseSyncCoordinator:
    """阶段前屏障：同 phase 的全部虚拟用户到齐后再继续（可跨链路轮次复用）。

    可选 slot_release / slot_acquire：在屏障等待期间释放并发槽位，避免 Ramp-up 或长等待占满信号量。
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._barrier_key: Optional[str] = None
        self._expected = 0
        self._arrived = 0
        self._event: Optional[asyncio.Event] = None

    async def _wait_or_stop(self, event: asyncio.Event, stop_event: Optional[asyncio.Event]) -> None:
        if event.is_set():
            return
        if stop_event and stop_event.is_set():
            return
        tasks = [asyncio.create_task(event.wait())]
        if stop_event:
            tasks.append(asyncio.create_task(stop_event.wait()))
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    async def wait(
        self,
        expected: int,
        barrier_key: str,
        *,
        stop_event: Optional[asyncio.Event] = None,
        slot_release: Optional[Callable[[], Any]] = None,
        slot_acquire: Optional[Callable[[], Awaitable[Any]]] = None,
    ):
        if slot_release:
            slot_release()
        reset_after = False
        try:
            async with self._lock:
                if barrier_key != self._barrier_key or self._event is None:
                    self._barrier_key = barrier_key
                    self._expected = max(1, expected)
                    self._arrived = 0
                    self._event = asyncio.Event()
                self._arrived += 1
                local_event = self._event
                if self._arrived >= self._expected:
                    local_event.set()
                    reset_after = True
            await self._wait_or_stop(local_event, stop_event)
        finally:
            if reset_after:
                async with self._lock:
                    if self._barrier_key == barrier_key:
                        self._barrier_key = None
                        self._arrived = 0
                        self._event = None
            if slot_acquire:
                await slot_acquire()


class JourneyStatsCollector:
    """链路级统计（线程安全）。"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.total_journeys = 0
        self.success_journeys = 0
        self.fail_journeys = 0
        self.journey_durations: list[float] = []
        self.phases: dict[str, dict] = {}

    async def record_journey(self, success: bool, duration_ms: float, phase_summaries: list[dict]):
        async with self._lock:
            self.total_journeys += 1
            if success:
                self.success_journeys += 1
            else:
                self.fail_journeys += 1
            if duration_ms > 0:
                self.journey_durations.append(duration_ms)
            for ps in phase_summaries:
                key = str(ps.get("phase_index", 0))
                if key not in self.phases:
                    self.phases[key] = {
                        "name": ps.get("phase_name", ""),
                        "total": 0,
                        "success": 0,
                        "fail": 0,
                        "durations": [],
                    }
                p = self.phases[key]
                p["total"] += 1
                if ps.get("success"):
                    p["success"] += 1
                else:
                    p["fail"] += 1
                d = ps.get("duration_ms", 0)
                if d > 0:
                    p["durations"].append(d)

    def to_aggregations(self) -> dict:
        durations = list(self.journey_durations)
        phase_out = {}
        for key, p in self.phases.items():
            durs = list(p.get("durations") or [])
            phase_out[key] = {
                "name": p.get("name", ""),
                "total": p.get("total", 0),
                "success": p.get("success", 0),
                "fail": p.get("fail", 0),
                "error_rate": round(p["fail"] / p["total"] * 100, 2) if p.get("total") else 0,
                "avg_duration_ms": round(sum(durs) / len(durs), 2) if durs else 0,
                "p95_duration_ms": round(float(np.percentile(durs, 95)), 2) if len(durs) >= 2 else (round(durs[0], 2) if durs else 0),
            }
        return {
            "total_journeys": self.total_journeys,
            "success_journeys": self.success_journeys,
            "fail_journeys": self.fail_journeys,
            "journey_success_rate": round(self.success_journeys / self.total_journeys * 100, 2) if self.total_journeys else 0,
            "avg_journey_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "p95_journey_duration_ms": round(float(np.percentile(durations, 95)), 2) if len(durations) >= 2 else (round(durations[0], 2) if durations else 0),
            "phases": phase_out,
        }


ExecuteStepFn = Callable[
    [int, int, dict, dict],
    Awaitable[tuple[dict, dict]],
]


async def run_one_journey(
    *,
    journey: dict,
    worker_id: int,
    journey_index: int,
    session_vars: dict,
    sync: PhaseSyncCoordinator,
    active_users: int,
    execute_step: ExecuteStepFn,
    result_queue: list,
    stream_profile_global: Optional[dict] = None,
    slot_release: Optional[Callable[[], Any]] = None,
    slot_acquire: Optional[Callable[[], Awaitable[Any]]] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> tuple[bool, float, list[dict]]:
    """执行一条完整业务链路。"""
    import time

    chain_start = time.time()
    chain_ok = True
    phase_summaries: list[dict] = []
    stop_on_fail = journey.get("stop_on_step_fail", True)

    for phase_idx, phase in enumerate(journey.get("phases") or []):
        if not chain_ok and stop_on_fail:
            break

        if phase.get("sync_before"):
            barrier_key = f"phase_{phase_idx}"
            await sync.wait(
                active_users,
                barrier_key,
                stop_event=stop_event,
                slot_release=slot_release,
                slot_acquire=slot_acquire,
            )

        phase_start = time.time()
        phase_ok = True
        steps = phase.get("steps") or []
        execution = (phase.get("execution") or "serial").strip()

        async def _run_step(step_idx: int, step: dict, vars_for_step: dict) -> tuple[dict, dict]:
            if not chain_ok and stop_on_fail:
                return {"success": False}, {}
            step_stream = step.get("use_stream") and stream_profile_global
            step_cfg = {**step, "_stream_profile": stream_profile_global if step_stream else None}
            result, extracted = await execute_step(phase_idx, step_idx, step_cfg, vars_for_step)
            result["journey_index"] = journey_index
            result["phase_index"] = phase_idx
            result["phase_name"] = phase.get("name", "")
            result["step_index"] = step_idx
            result["worker_id"] = worker_id
            return result, extracted

        if execution == "parallel" and len(steps) > 1:
            max_parallel = phase.get("max_parallel", 6)
            sem = asyncio.Semaphore(max_parallel)

            async def _parallel_step(step_idx: int, step: dict):
                async with sem:
                    result, extracted = await _run_step(step_idx, step, copy.copy(session_vars))
                    delay_ms = step.get("delay_ms", 0)
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000)
                    return result, extracted

            gathered = await asyncio.gather(*[_parallel_step(i, s) for i, s in enumerate(steps)])
            for step_idx, (result, extracted) in enumerate(gathered):
                result_queue.append(result)
                if extracted:
                    session_vars.update(extracted)
                if not result.get("success"):
                    phase_ok = False
                    if stop_on_fail:
                        chain_ok = False
        else:
            for step_idx, step in enumerate(steps):
                if not chain_ok and stop_on_fail:
                    break
                result, extracted = await _run_step(step_idx, step, session_vars)
                result_queue.append(result)
                if extracted:
                    session_vars.update(extracted)
                if not result.get("success"):
                    phase_ok = False
                    if stop_on_fail:
                        chain_ok = False
                delay_ms = step.get("delay_ms", 0)
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

        phase_summaries.append({
            "phase_index": phase_idx,
            "phase_name": phase.get("name", ""),
            "success": phase_ok,
            "duration_ms": round((time.time() - phase_start) * 1000, 2),
        })

    chain_duration = round((time.time() - chain_start) * 1000, 2)
    return chain_ok, chain_duration, phase_summaries
