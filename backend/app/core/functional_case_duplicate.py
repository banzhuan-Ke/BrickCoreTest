"""
功能用例库重复检验
"""
from collections import defaultdict
from typing import Any, Optional

from app.core.case_steps import align_steps_expects
from app.core.functional_case_service import functional_case_to_dict
from app.models.ai import AiFunctionalCase


def _normalize_key(text: str) -> str:
    return " ".join((text or "").strip().split())


def _steps_summary(steps) -> str:
    """步骤摘要：对齐后的 step|expect 拼接，供严格模式去重"""
    aligned = align_steps_expects(steps or [])
    parts: list[str] = []
    for st in aligned:
        step = _normalize_key(st.get("step", ""))
        expect = _normalize_key(st.get("expect", ""))
        if step or expect:
            parts.append(f"{step}|{expect}")
    return "|".join(parts)


async def find_duplicate_groups(
    project_id: int,
    *,
    module: Optional[str] = None,
    source_type: Optional[str] = None,
    import_batch: Optional[str] = None,
    strict_mode: bool = False,
) -> dict[str, Any]:
    """按 标题 + 所属模块（+ 可选步骤摘要）分组，返回含 2 条及以上的组"""
    q = AiFunctionalCase.filter(project_id=project_id, is_del=False)
    if module:
        q = q.filter(module=module)
    if source_type:
        q = q.filter(source_type=source_type)
    if import_batch:
        q = q.filter(source_import_batch=import_batch)

    cases = await q.order_by("id").all()
    buckets: dict[tuple, list[AiFunctionalCase]] = defaultdict(list)
    for case in cases:
        title = _normalize_key(case.title)
        mod = _normalize_key(case.module)
        if strict_mode:
            key = (title, mod, _steps_summary(case.steps))
        else:
            key = (title, mod)
        buckets[key].append(case)

    groups = []
    duplicate_case_count = 0
    for key, items in buckets.items():
        if len(items) < 2:
            continue
        duplicate_case_count += len(items)
        title, mod = key[0], key[1]
        group_key: dict[str, Any] = {"title": title, "module": mod}
        if strict_mode:
            group_key["steps_summary"] = key[2]
        groups.append({
            "key": group_key,
            "cases": [functional_case_to_dict(c) for c in items],
        })

    groups.sort(key=lambda g: (-len(g["cases"]), g["key"]["title"]))
    return {
        "strict_mode": strict_mode,
        "group_count": len(groups),
        "duplicate_case_count": duplicate_case_count,
        "groups": groups,
    }
