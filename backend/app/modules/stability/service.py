"""按域聚合最近 N 次执行的稳定度。"""
from __future__ import annotations

from typing import Any, Sequence

from app.modules.ai.ai_project_settings import load_ai_project_settings, get_stability_policy, normalize_stability_n
from app.modules.stability.metrics import RECENT_SHORT_K, collect_run_samples, summarize_samples
from app.modules.stability.request_id import extract_request_id_from_detail
from app.modules.stability.tags import has_quarantine, set_quarantine

DOMAINS = frozenset({"api", "ui", "app"})
OVERALL_LOOKBACK = 100
METRIC_SORT_FIELDS = frozenset({
    "pass_rate",
    "recent_pass_rate",
    "overall_pass_rate",
    "n",
    "overall_n",
    "retry_salvage_count",
    "last_run_at",
    "case_name",
})


def _fmt_dt(value: Any) -> Any:
    return value.isoformat(sep=" ")[:19] if hasattr(value, "isoformat") else value


def _fallback(domain: str) -> str:
    # API：无重试信息时终态成功计入首跑；UI/App 无 attempt 字段不得用终态冒充（SoT §4.1）
    if domain == "api":
        return "equal"
    return "null"


async def resolve_stability_n(project_id: int | None, override: int | None = None) -> int:
    if override is not None:
        return normalize_stability_n(override)
    if not project_id:
        return normalize_stability_n(None)
    settings = await load_ai_project_settings(project_id)
    return normalize_stability_n(settings.get("stability_n"))


async def resolve_stability_policy(project_id: int | None) -> dict[str, Any]:
    if not project_id:
        return get_stability_policy(None)
    settings = await load_ai_project_settings(project_id)
    return get_stability_policy(settings)


async def load_case_row(domain: str, case_id: int):
    if domain == "api":
        from app.models.http import ApiTestCase

        return await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if domain == "ui":
        from app.models.ui import Case

        return await Case.get_or_none(id=case_id, is_del=False)
    from app.models.app import AppCase

    return await AppCase.get_or_none(id=case_id, is_del=False)


async def list_project_cases(domain: str, project_id: int, *, name: str | None = None):
    if domain == "api":
        from app.models.http import ApiTestCase

        q = ApiTestCase.filter(project_id=project_id, is_del=False)
        if name:
            q = q.filter(name__icontains=name)
        return await q.order_by("-id").all()
    if domain == "ui":
        from app.models.ui import Case

        q = Case.filter(project_id=project_id, is_del=False)
        if name:
            q = q.filter(name__icontains=name)
        return await q.order_by("-id").all()
    from app.models.app import AppCase

    q = AppCase.filter(project_id=project_id, is_del=False)
    if name:
        q = q.filter(name__icontains=name)
    return await q.order_by("-id").all()


async def fetch_recent_runs(domain: str, case_id: int, n: int) -> list[dict[str, Any]]:
    limit = max(OVERALL_LOOKBACK, n * 3, n)
    if domain == "api":
        from app.models.http import ApiRunRecord

        rows = await ApiRunRecord.filter(case_id=case_id).order_by("-id").limit(limit)
        out: list[dict[str, Any]] = []
        for r in rows:
            detail = r.request_detail if isinstance(r.request_detail, dict) else {}
            out.append({
                "id": r.id,
                "status": r.status,
                "request_detail": detail,
                "assertions_result": r.assertions_result if isinstance(r.assertions_result, list) else [],
                "response_status": r.response_status,
                "error_msg": r.error_msg,
                "ended_at": r.end_time or r.start_time,
                "request_id": extract_request_id_from_detail(detail, r.request_headers),
            })
        return out
    if domain == "ui":
        from app.models.ui import UiCaseExecution

        rows = await UiCaseExecution.filter(case_id=case_id, is_del=False).order_by("-id").limit(limit)
        return [
            {
                "id": r.id,
                "status": r.status,
                "result_data": r.result_data if isinstance(r.result_data, dict) else {},
                "ended_at": r.start_time,
            }
            for r in rows
        ]
    from app.models.app import AppCaseExecution

    rows = await AppCaseExecution.filter(case_id=case_id, is_del=False).order_by("-id").limit(limit)
    return [
        {
            "id": r.id,
            "status": r.status,
            "result_data": r.result_data if isinstance(r.result_data, dict) else {},
            "ended_at": r.start_time,
        }
        for r in rows
    ]


def _clip_summary(
    runs: list[dict[str, Any]],
    n: int,
    *,
    tags: Any,
    fallback: str,
    recent_k: int = RECENT_SHORT_K,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    samples = collect_run_samples(runs, first_pass_fallback=fallback)
    window = samples[: max(0, int(n or 0))]
    return summarize_samples(
        window,
        tags=tags,
        first_pass_fallback=fallback,
        recent_k=recent_k,
        overall_samples=samples,
        rules=rules,
    )


def _public_item(case, domain: str, summary: dict[str, Any], *, with_recent: bool = False) -> dict[str, Any]:
    item = {
        "case_id": case.id,
        "case_name": case.name,
        "domain": domain,
        "n": summary["n"],
        "pass_rate": summary["pass_rate"],
        "recent_pass_rate": summary.get("recent_pass_rate"),
        "recent_n": summary.get("recent_n") or 0,
        "overall_pass_rate": summary.get("overall_pass_rate"),
        "overall_n": summary.get("overall_n") or 0,
        "first_pass_rate": summary["first_pass_rate"],
        "retry_salvage_count": summary["retry_salvage_count"],
        "unstable": summary["unstable"],
        "quarantine": summary["quarantine"],
        "last_failure_bucket": summary["last_failure_bucket"],
        "bucket_histogram": summary["bucket_histogram"],
        "last_run_at": _fmt_dt(summary.get("last_run_at")),
        "last_request_id": summary.get("last_request_id") or "",
    }
    if with_recent:
        item["recent"] = [
            {**s, "ended_at": _fmt_dt(s.get("ended_at"))}
            for s in (summary.get("recent") or [])
        ]
    return item


def _sort_items(items: list[dict[str, Any]], sort_by: str | None, sort_order: str) -> list[dict[str, Any]]:
    key = (sort_by or "").strip()
    if key not in METRIC_SORT_FIELDS:
        return items
    reverse = (sort_order or "desc").strip().lower() != "asc"
    numeric = key in {
        "pass_rate", "recent_pass_rate", "overall_pass_rate",
        "n", "overall_n", "retry_salvage_count",
    }
    missing = float("-inf") if reverse else float("inf")

    def _key(item: dict[str, Any]):
        val = item.get(key)
        if val is None or val == "":
            return missing if numeric else ""
        if numeric:
            try:
                return float(val)
            except (TypeError, ValueError):
                return missing
        return str(val)

    return sorted(items, key=_key, reverse=reverse)


def _build_overview(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = list(items or [])
    with_runs = [i for i in rows if int(i.get("n") or 0) > 0]
    unstable = sum(1 for i in with_runs if i.get("unstable"))
    quarantined = sum(1 for i in rows if i.get("quarantine"))
    rates = [float(i["pass_rate"]) for i in with_runs if i.get("pass_rate") is not None]
    avg_pass = round(sum(rates) / len(rates), 4) if rates else None
    bands = {"high": 0, "mid": 0, "low": 0, "none": 0}
    for i in rows:
        if int(i.get("n") or 0) <= 0:
            bands["none"] += 1
            continue
        pr = float(i.get("pass_rate") or 0)
        if pr >= 0.85:
            bands["high"] += 1
        elif pr >= 0.5:
            bands["mid"] += 1
        else:
            bands["low"] += 1
    bucket_hist: dict[str, int] = {}
    for i in with_runs:
        b = i.get("last_failure_bucket")
        if not b:
            continue
        bucket_hist[str(b)] = bucket_hist.get(str(b), 0) + 1
    return {
        "case_count": len(rows),
        "with_runs": len(with_runs),
        "unstable": unstable,
        "quarantined": quarantined,
        "avg_pass_rate": avg_pass,
        "pass_bands": bands,
        "bucket_histogram": bucket_hist,
    }


async def summarize_case(domain: str, case_id: int, *, n: int) -> dict[str, Any] | None:
    case = await load_case_row(domain, case_id)
    if not case:
        return None
    policy = await resolve_stability_policy(getattr(case, "project_id", None))
    runs = await fetch_recent_runs(domain, case_id, n)
    summary = _clip_summary(
        runs,
        n,
        tags=getattr(case, "tags", None),
        fallback=_fallback(domain),
        recent_k=policy["recent_k"],
        rules=policy["rules"],
    )
    return _public_item(case, domain, summary, with_recent=True)


async def list_case_summaries(
    *,
    project_id: int,
    domain: str,
    n: int,
    case_ids: Sequence[int] | None = None,
    unstable_only: bool = False,
    quarantine_only: bool = False,
    has_runs_only: bool = False,
    name: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    if case_ids:
        rows = []
        for cid in case_ids:
            case = await load_case_row(domain, int(cid))
            if case and getattr(case, "project_id", None) == project_id:
                rows.append(case)
    else:
        rows = await list_project_cases(domain, project_id, name=name)

    if quarantine_only:
        rows = [c for c in rows if has_quarantine(getattr(c, "tags", None))]

    page = max(1, int(page or 1))
    size = max(1, min(100, int(size or 20)))
    fallback = _fallback(domain)
    policy = await resolve_stability_policy(project_id)
    recent_k = policy["recent_k"]
    rules = policy["rules"]
    sort_key = (sort_by or "").strip()
    need_full = bool(
        unstable_only
        or has_runs_only
        or (sort_key in METRIC_SORT_FIELDS)
    )

    async def _item_for(case) -> dict[str, Any]:
        runs = await fetch_recent_runs(domain, case.id, n)
        summary = _clip_summary(
            runs,
            n,
            tags=getattr(case, "tags", None),
            fallback=fallback,
            recent_k=recent_k,
            rules=rules,
        )
        return _public_item(case, domain, summary)

    if not need_full:
        total = len(rows)
        start = (page - 1) * size
        page_rows = rows[start: start + size]
        items = [await _item_for(case) for case in page_rows]
        return {
            "total": total,
            "page": page,
            "size": size,
            "items": items,
            "overview": _build_overview(items),
            "overview_scope": "page",
            "recent_k": recent_k,
            "rules": rules,
        }

    items: list[dict[str, Any]] = []
    for case in rows:
        item = await _item_for(case)
        if has_runs_only and int(item.get("n") or 0) <= 0:
            continue
        if unstable_only and not item.get("unstable"):
            continue
        items.append(item)

    items = _sort_items(items, sort_key or None, sort_order)
    total = len(items)
    start = (page - 1) * size
    page_items = items[start: start + size]
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": page_items,
        "overview": _build_overview(items),
        "overview_scope": "filtered",
        "recent_k": recent_k,
        "rules": rules,
    }


async def set_case_quarantine(domain: str, case_id: int, enabled: bool) -> dict[str, Any] | None:
    case = await load_case_row(domain, case_id)
    if not case:
        return None
    case.tags = set_quarantine(getattr(case, "tags", None), enabled)
    await case.save()
    return {
        "case_id": case.id,
        "domain": domain,
        "quarantine": has_quarantine(case.tags),
        "tags": case.tags,
    }
