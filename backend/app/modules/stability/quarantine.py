"""quarantine 跳过：拆分用例 ID、写 API skip 记录、UI/App skip 标记。"""
from __future__ import annotations

from typing import Any, Sequence

from app.modules.stability.metrics import SKIP_REASON_MEMBERSHIP, SKIP_REASON_QUARANTINE
from app.modules.stability.tags import has_quarantine


def resolve_case_skip(
    *,
    membership_skip: bool,
    tags: Any,
    include_quarantine: bool = False,
) -> tuple[bool, str | None]:
    """返回 (skip, skip_reason)。隔离优先于套件成员 skip。"""
    if has_quarantine(tags) and not include_quarantine:
        return True, SKIP_REASON_QUARANTINE
    if membership_skip:
        return True, SKIP_REASON_MEMBERSHIP
    return False, None


async def split_quarantined_ids(
    domain: str,
    case_ids: Sequence[int],
    *,
    include_quarantine: bool = False,
) -> tuple[list[int], list[int]]:
    """按原顺序拆成 (runnable, quarantined)。include 时 quarantined 为空。"""
    ids = [int(x) for x in case_ids if x is not None]
    if not ids:
        return [], []
    tag_map = await _load_tag_map(domain, ids)
    runnable: list[int] = []
    quarantined: list[int] = []
    for cid in ids:
        if has_quarantine(tag_map.get(cid)) and not include_quarantine:
            quarantined.append(cid)
        else:
            runnable.append(cid)
    return runnable, quarantined


async def _load_tag_map(domain: str, case_ids: list[int]) -> dict[int, Any]:
    if domain == "api":
        from app.models.http import ApiTestCase

        rows = await ApiTestCase.filter(id__in=case_ids).all()
        return {r.id: r.tags for r in rows}
    if domain == "ui":
        from app.models.ui import Case

        rows = await Case.filter(id__in=case_ids).all()
        return {r.id: getattr(r, "tags", None) for r in rows}
    if domain == "app":
        from app.models.app import AppCase

        rows = await AppCase.filter(id__in=case_ids).all()
        return {r.id: getattr(r, "tags", None) for r in rows}
    return {}


async def write_api_quarantine_skips(
    *,
    case_ids: Sequence[int],
    project_id: int,
    username: str,
    suite_record_id: int | None = None,
) -> list[Any]:
    from app.models.http import ApiRunRecord, ApiTestCase
    from app.schemas.http import ApiRunResult

    results: list[ApiRunResult] = []
    if not case_ids:
        return results
    names = {
        c.id: c.name
        for c in await ApiTestCase.filter(id__in=list(case_ids)).all()
    }
    for cid in case_ids:
        rec = await ApiRunRecord.create(
            case_id=cid,
            project_id=project_id,
            suite_run_record_id=suite_record_id,
            status="skip",
            error_msg="已隔离未跑",
            request_detail={"skip_reason": SKIP_REASON_QUARANTINE},
            run_by=username or "",
        )
        results.append(
            ApiRunResult(
                record_id=rec.id,
                status="skip",
                error="已隔离未跑",
                case_id=cid,
                case_name=names.get(cid),
                request_detail={"skip_reason": SKIP_REASON_QUARANTINE},
            )
        )
    return results
