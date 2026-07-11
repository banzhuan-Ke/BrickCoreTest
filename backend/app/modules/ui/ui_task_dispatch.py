"""UI 测试计划并行分发：按执行器权重分配套件（不拆分套件内用例）。"""
from __future__ import annotations

from typing import Any

DeviceAssignment = tuple[str, int, int]  # (device_id, weight, concurrency)


def normalize_device_assignments(
    device_id: str | None,
    devices: list[dict[str, Any]] | None,
    *,
    default_concurrency: int = 1,
) -> list[DeviceAssignment]:
    """合并单设备与多设备入参，返回 [(device_id, weight, concurrency), ...]。"""
    out: list[DeviceAssignment] = []
    seen: set[str] = set()
    for item in devices or []:
        if not isinstance(item, dict):
            continue
        dev = str(item.get("device_id") or "").strip()
        if not dev or dev in seen:
            continue
        weight = item.get("weight", 1)
        try:
            w = int(weight)
        except (TypeError, ValueError):
            w = 1
        concurrency = item.get("concurrency", default_concurrency)
        try:
            c = int(concurrency)
        except (TypeError, ValueError):
            c = default_concurrency
        out.append((dev, max(1, min(w, 100)), max(1, min(c, 20))))
        seen.add(dev)
    if not out and device_id:
        dev = str(device_id).strip()
        if dev:
            try:
                c = int(default_concurrency)
            except (TypeError, ValueError):
                c = 1
            out.append((dev, 1, max(1, min(c, 20))))
    return out


def device_weight_pairs(device_assignments: list[DeviceAssignment]) -> list[tuple[str, int]]:
    return [(dev_id, weight) for dev_id, weight, _ in device_assignments]


def max_device_concurrency(device_assignments: list[DeviceAssignment]) -> int:
    if not device_assignments:
        return 1
    return max(c for _, _, c in device_assignments)


def distribute_suite_indices_by_weight(
    suite_case_counts: list[int],
    device_weights: list[tuple[str, int]],
) -> list[int]:
    """
    按权重将套件索引分配到设备（0-based device index）。
    以用例数为负载，整套件分配，保持套件内串行与 pre_actions 语义。
    """
    n_suites = len(suite_case_counts)
    n_devices = len(device_weights)
    if n_suites == 0 or n_devices == 0:
        return []
    if n_devices == 1:
        return [0] * n_suites

    weights = [max(1, w) for _, w in device_weights]
    total_weight = sum(weights)
    total_cases = sum(max(c, 1) for c in suite_case_counts) or n_suites
    targets = [total_cases * w / total_weight for w in weights]
    loads = [0.0] * n_devices
    assignments: list[int] = []

    for case_count in suite_case_counts:
        load_unit = max(case_count, 1)
        best_idx = min(
            range(n_devices),
            key=lambda i: loads[i] / targets[i] if targets[i] > 0 else float("inf"),
        )
        assignments.append(best_idx)
        loads[best_idx] += load_unit

    return assignments


def group_suites_by_device_index(
    suite_entries: list[Any],
    suite_case_counts: list[int],
    device_weights: list[tuple[str, int]],
) -> dict[str, list[Any]]:
    """返回 {device_id: [suite_entry, ...]}，顺序与计划内套件顺序一致。"""
    indices = distribute_suite_indices_by_weight(suite_case_counts, device_weights)
    grouped: dict[str, list[Any]] = {dev_id: [] for dev_id, _ in device_weights}
    for entry, dev_idx in zip(suite_entries, indices):
        dev_id = device_weights[dev_idx][0]
        grouped[dev_id].append(entry)
    return grouped
