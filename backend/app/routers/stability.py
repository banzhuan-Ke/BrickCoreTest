"""执行可信度 API（稳定度 / 隔离）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.platform.auth import is_authenticated, require_any_permissions
from app.core.platform.permissions import (
    API_CASE_EDIT,
    API_CASE_VIEW,
    APP_CASE_EDIT,
    APP_CASE_VIEW,
    UI_CASE_EDIT,
    UI_CASE_VIEW,
    get_user_permissions,
)
from app.modules.stability.buckets import bucket_label
from app.modules.stability.metrics import RECENT_SHORT_K
from app.modules.stability.service import (
    DOMAINS,
    list_case_summaries,
    load_case_row,
    resolve_stability_n,
    set_case_quarantine,
    summarize_case,
)
from app.core.shared.start_url import build_apm_trace_url
from app.modules.ai.ai_project_settings import load_ai_project_settings
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/stability", tags=["执行可信度"], dependencies=[Depends(is_authenticated)])


async def _attach_obs_links(project_id: int, items: list[dict]) -> None:
    settings = await load_ai_project_settings(project_id)
    base = str((settings or {}).get("apm_trace_base_url") or "").strip()
    for item in items:
        rid = str(item.get("last_request_id") or "").strip()
        item["apm_url"] = build_apm_trace_url(base, rid) if base and rid else ""


_VIEW_PERMS = {
    "api": API_CASE_VIEW,
    "ui": UI_CASE_VIEW,
    "app": APP_CASE_VIEW,
}
_EDIT_PERMS = {
    "api": API_CASE_EDIT,
    "ui": UI_CASE_EDIT,
    "app": APP_CASE_EDIT,
}


async def _assert_domain_perm(user_info: dict, domain: str, *, edit: bool = False) -> None:
    if user_info.get("is_superuser"):
        return
    uid = user_info.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    needed = (_EDIT_PERMS if edit else _VIEW_PERMS).get(domain)
    if not needed:
        raise HTTPException(status_code=422, detail="domain 须为 api / ui / app")
    allowed = set(await get_user_permissions(int(uid)))
    if needed not in allowed:
        raise HTTPException(status_code=403, detail=f"权限不足: 需要 {needed}")


def _parse_domain(domain: str) -> str:
    value = (domain or "").strip().lower()
    if value not in DOMAINS:
        raise HTTPException(status_code=422, detail="domain 须为 api / ui / app")
    return value


def _parse_ids(raw: Optional[str]) -> list[int] | None:
    if not raw:
        return None
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out or None


class QuarantineBody(BaseModel):
    enabled: bool
    domain: str = Field(..., description="api / ui / app")
    reason: Optional[str] = None


@router.get("/cases", summary="用例稳定度列表")
async def list_stability_cases(
    project_id: int = Query(...),
    domain: str = Query(..., description="api / ui / app"),
    n: Optional[int] = Query(None, ge=5, le=50),
    case_ids: Optional[str] = Query(None, description="逗号分隔用例 ID，仅汇总这些用例"),
    unstable_only: bool = Query(False),
    quarantine_only: bool = Query(False),
    has_runs_only: bool = Query(False, description="仅有执行样本的用例"),
    name: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(
        None,
        description="pass_rate / recent_pass_rate / overall_pass_rate / n / last_run_at / case_name",
    ),
    sort_order: str = Query("desc", description="asc / desc"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_info: dict = Depends(require_any_permissions(API_CASE_VIEW, UI_CASE_VIEW, APP_CASE_VIEW)),
):
    dom = _parse_domain(domain)
    await _assert_domain_perm(user_info, dom, edit=False)
    await assert_user_project_viewer(user_info, project_id)
    window = await resolve_stability_n(project_id, n)
    data = await list_case_summaries(
        project_id=project_id,
        domain=dom,
        n=window,
        case_ids=_parse_ids(case_ids),
        unstable_only=unstable_only,
        quarantine_only=quarantine_only,
        has_runs_only=has_runs_only,
        name=name,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        size=size,
    )
    for item in data.get("items") or []:
        item["last_failure_bucket_label"] = bucket_label(item.get("last_failure_bucket"))
    await _attach_obs_links(project_id, data.get("items") or [])
    data["n"] = window
    data["recent_k"] = data.get("recent_k") or RECENT_SHORT_K
    return StandardResponse(data=data)


@router.get("/cases/{case_id}", summary="用例稳定度详情")
async def get_stability_case(
    case_id: int,
    domain: str = Query(...),
    n: Optional[int] = Query(None, ge=5, le=50),
    user_info: dict = Depends(require_any_permissions(API_CASE_VIEW, UI_CASE_VIEW, APP_CASE_VIEW)),
):
    dom = _parse_domain(domain)
    case = await load_case_row(dom, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    await _assert_domain_perm(user_info, dom, edit=False)
    await assert_user_project_viewer(user_info, case.project_id)
    window = await resolve_stability_n(case.project_id, n)
    item = await summarize_case(dom, case_id, n=window)
    if not item:
        raise HTTPException(status_code=404, detail="用例不存在")
    item["last_failure_bucket_label"] = bucket_label(item.get("last_failure_bucket"))
    await _attach_obs_links(case.project_id, [item])
    return StandardResponse(data=item)


@router.post("/cases/{case_id}/quarantine", summary="隔离 / 解除隔离")
async def update_quarantine(
    case_id: int,
    body: QuarantineBody,
    user_info: dict = Depends(require_any_permissions(API_CASE_EDIT, UI_CASE_EDIT, APP_CASE_EDIT)),
):
    dom = _parse_domain(body.domain)
    case = await load_case_row(dom, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    await _assert_domain_perm(user_info, dom, edit=True)
    await assert_user_project_member(user_info, case.project_id)
    data = await set_case_quarantine(dom, case_id, body.enabled)
    return StandardResponse(data=data)
