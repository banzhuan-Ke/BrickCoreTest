"""UI 步骤片段管理"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, require_permissions
from app.core.permissions import UI_CASE_EDIT, UI_CASE_VIEW
from app.core.ui_step_expand import FragmentExpandError, expand_fragment_refs
from app.core.ui_fragment_refs import collect_fragment_references
from app.models.sys import Project
from app.models.ui import UiStepFragment
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/fragments", tags=["UI步骤片段"])


def _fragment_to_dict(row: UiStepFragment) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description or "",
        "steps": row.steps or [],
        "tags": row.tags or "",
        "version": row.version,
        "step_count": len(row.steps or []),
        "username": row.username,
        "update_by": row.update_by or row.username,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


async def _get_fragment_or_404(fragment_id: int, project_id: int) -> UiStepFragment:
    row = await UiStepFragment.get_or_none(id=fragment_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="步骤片段不存在")
    return row


async def _ensure_project(project_id: int) -> Project:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


class FragmentCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    tags: Optional[str] = Field(None, max_length=200)


class FragmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    steps: Optional[list[dict[str, Any]]] = None
    tags: Optional[str] = Field(None, max_length=200)


class FragmentExpandRequest(BaseModel):
    project_id: int
    steps: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


@router.get("", summary="步骤片段列表", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def list_fragments(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    await _ensure_project(project_id)
    qs = UiStepFragment.filter(project_id=project_id, is_del=False)
    if keyword:
        qs = qs.filter(name__icontains=keyword.strip())
    if tag:
        qs = qs.filter(tags__icontains=tag.strip())
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    return StandardResponse(
        data={
            "total": total,
            "page": page,
            "size": size,
            "items": [_fragment_to_dict(r) for r in rows],
        }
    )


@router.get("/{fragment_id}", summary="步骤片段详情", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_fragment(
    fragment_id: int,
    project_id: int = Query(..., description="项目ID"),
):
    row = await _get_fragment_or_404(fragment_id, project_id)
    return StandardResponse(data=_fragment_to_dict(row))


@router.post("", summary="创建步骤片段", dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def create_fragment(
    item: FragmentCreate,
    username: str = Depends(get_current_username),
):
    await _ensure_project(item.project_id)
    exists = await UiStepFragment.filter(
        project_id=item.project_id, name=item.name.strip(), is_del=False
    ).exists()
    if exists:
        raise HTTPException(status_code=422, detail="同项目下已存在同名片段")
    row = await UiStepFragment.create(
        project_id=item.project_id,
        name=item.name.strip(),
        description=(item.description or "").strip() or None,
        steps=item.steps or [],
        tags=(item.tags or "").strip() or None,
        version=1,
        username=username,
        update_by=username,
    )
    return StandardResponse(data=_fragment_to_dict(row), message="创建成功")


@router.put("/{fragment_id}", summary="更新步骤片段", dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def update_fragment(
    fragment_id: int,
    item: FragmentUpdate,
    project_id: int = Query(..., description="项目ID"),
    username: str = Depends(get_current_username),
):
    row = await _get_fragment_or_404(fragment_id, project_id)
    if item.name and item.name.strip() != row.name:
        dup = await UiStepFragment.filter(
            project_id=project_id, name=item.name.strip(), is_del=False
        ).exclude(id=fragment_id).exists()
        if dup:
            raise HTTPException(status_code=422, detail="同项目下已存在同名片段")
        row.name = item.name.strip()
    if item.description is not None:
        row.description = item.description.strip() or None
    if item.tags is not None:
        row.tags = item.tags.strip() or None
    if item.steps is not None:
        row.steps = item.steps
        row.version = int(row.version or 1) + 1
    row.update_by = username
    await row.save()
    return StandardResponse(data=_fragment_to_dict(row), message="更新成功")


@router.get("/{fragment_id}/references", summary="片段引用统计", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_fragment_references(
    fragment_id: int,
    project_id: int = Query(..., description="项目ID"),
):
    await _get_fragment_or_404(fragment_id, project_id)
    data = await collect_fragment_references(project_id, fragment_id)
    return StandardResponse(data=data)


@router.delete("/{fragment_id}", summary="删除步骤片段", dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def delete_fragment(
    fragment_id: int,
    project_id: int = Query(..., description="项目ID"),
    force: bool = Query(False, description="存在引用时仍强制删除"),
):
    row = await _get_fragment_or_404(fragment_id, project_id)
    refs = await collect_fragment_references(project_id, fragment_id)
    if refs["total"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"该片段仍被 {refs['case_count']} 条用例、{refs['suite_count']} 个套件引用",
                "references": refs,
            },
        )
    row.is_del = True
    await row.save()
    return StandardResponse(message="删除成功", data={"references_cleared": refs["total"]})


@router.post("/{fragment_id}/expand", summary="预览展开片段", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def preview_expand_fragment(
    fragment_id: int,
    item: FragmentExpandRequest,
):
    row = await _get_fragment_or_404(fragment_id, item.project_id)
    ref_step = {
        "id": "preview_ref",
        "method": "fragment_ref",
        "params": {
            "fragment_id": row.id,
            "fragment_version": row.version,
            "fragment_name": row.name,
            "variables": item.variables,
        },
    }
    steps = item.steps or [ref_step]
    if not any(s.get("method") == "fragment_ref" for s in steps if isinstance(s, dict)):
        steps = [ref_step]
    try:
        expanded = await expand_fragment_refs(steps, item.project_id)
    except FragmentExpandError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StandardResponse(
        data={
            "fragment": _fragment_to_dict(row),
            "expanded_steps": expanded,
            "step_count": len(expanded),
        }
    )
