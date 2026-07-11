"""Header 模板管理（接口自动化模块）"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, require_permissions
from app.core.shared.header_template_validate import normalize_template_headers
from app.core.platform.permissions import API_MANAGE_EDIT, API_MANAGE_VIEW
from app.models.http import HeaderTemplate
from app.models.sys import Project
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/header-templates", tags=["Header模板"])


def _template_to_dict(row: HeaderTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description or "",
        "headers": row.headers or [],
        "is_default": row.is_default,
        "sort_order": row.sort_order,
        "create_by": row.create_by,
        "update_by": row.update_by,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


async def _get_template_or_404(template_id: int, project_id: int) -> HeaderTemplate:
    row = await HeaderTemplate.get_or_none(id=template_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Header 模板不存在")
    return row


async def _ensure_project(project_id: int) -> Project:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _clear_default(project_id: int, exclude_id: Optional[int] = None) -> None:
    qs = HeaderTemplate.filter(project_id=project_id, is_del=False, is_default=True)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    await qs.update(is_default=False)


class HeaderTemplateCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    headers: list[dict[str, Any]] = Field(default_factory=list)
    is_default: bool = False
    sort_order: int = 0


class HeaderTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    headers: Optional[list[dict[str, Any]]] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None


class HeaderTemplateImportPreviewRequest(BaseModel):
    template_id: int
    project_id: int
    local_keys: list[str] = Field(default_factory=list)


@router.get("", summary="Header 模板列表", dependencies=[Depends(require_permissions(API_MANAGE_VIEW))])
async def list_header_templates(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    await _ensure_project(project_id)
    qs = HeaderTemplate.filter(project_id=project_id, is_del=False)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    total = await qs.count()
    rows = await qs.order_by("-is_default", "sort_order", "-update_time").offset((page - 1) * size).limit(size)
    items = [_template_to_dict(r) for r in rows]
    return StandardResponse(data={"list": items, "total": total, "page": page, "size": size})


@router.get("/options", summary="Header 模板选项", dependencies=[Depends(require_permissions(API_MANAGE_VIEW))])
async def list_header_template_options(project_id: int = Query(..., description="项目ID")):
    """供编辑页下拉使用，返回全部模板（不分页）。"""
    await _ensure_project(project_id)
    rows = await HeaderTemplate.filter(project_id=project_id, is_del=False).order_by(
        "-is_default", "sort_order", "-update_time"
    )
    return StandardResponse(
        data={
            "list": [
                {
                    "id": r.id,
                    "name": r.name,
                    "is_default": r.is_default,
                    "header_count": len(r.headers or []),
                }
                for r in rows
            ]
        }
    )


@router.get("/{template_id}", summary="Header 模板详情", dependencies=[Depends(require_permissions(API_MANAGE_VIEW))])
async def get_header_template(template_id: int, project_id: int = Query(..., description="项目ID")):
    row = await _get_template_or_404(template_id, project_id)
    return StandardResponse(data=_template_to_dict(row))


@router.post("", summary="新建 Header 模板", dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def create_header_template(
    body: HeaderTemplateCreate,
    username: str = Depends(get_current_username),
):
    await _ensure_project(body.project_id)
    exists = await HeaderTemplate.filter(
        project_id=body.project_id, name=body.name, is_del=False
    ).exists()
    if exists:
        raise HTTPException(status_code=400, detail="同项目下模板名称已存在")
    try:
        headers = normalize_template_headers(body.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if body.is_default:
        await _clear_default(body.project_id)

    row = await HeaderTemplate.create(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        headers=headers,
        is_default=body.is_default,
        sort_order=body.sort_order,
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=_template_to_dict(row))


@router.put("/{template_id}", summary="更新 Header 模板", dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def update_header_template(
    template_id: int,
    body: HeaderTemplateUpdate,
    project_id: int = Query(..., description="项目ID"),
    username: str = Depends(get_current_username),
):
    row = await _get_template_or_404(template_id, project_id)
    if body.name and body.name != row.name:
        exists = await HeaderTemplate.filter(
            project_id=project_id, name=body.name, is_del=False
        ).exclude(id=template_id).exists()
        if exists:
            raise HTTPException(status_code=400, detail="同项目下模板名称已存在")
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.headers is not None:
        try:
            row.headers = normalize_template_headers(body.headers)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    if body.is_default is True:
        await _clear_default(project_id, exclude_id=template_id)
        row.is_default = True
    elif body.is_default is False and row.is_default:
        row.is_default = False
    row.update_by = username
    await row.save()
    return StandardResponse(data=_template_to_dict(row))


@router.delete("/{template_id}", summary="删除 Header 模板", dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def delete_header_template(
    template_id: int,
    project_id: int = Query(..., description="项目ID"),
    username: str = Depends(get_current_username),
):
    row = await _get_template_or_404(template_id, project_id)
    row.is_del = True
    row.update_by = username
    await row.save()
    return StandardResponse(data={"id": template_id})


@router.post(
    "/{template_id}/set-default",
    summary="设为默认模板",
    dependencies=[Depends(require_permissions(API_MANAGE_EDIT))],
)
async def set_default_header_template(
    template_id: int,
    project_id: int = Query(..., description="项目ID"),
    username: str = Depends(get_current_username),
):
    row = await _get_template_or_404(template_id, project_id)
    await _clear_default(project_id, exclude_id=template_id)
    row.is_default = True
    row.update_by = username
    await row.save()
    return StandardResponse(data=_template_to_dict(row))


@router.post(
    "/preview-import",
    summary="预览模板导入",
    dependencies=[Depends(require_permissions(API_MANAGE_VIEW))],
)
async def preview_template_import(body: HeaderTemplateImportPreviewRequest):
    row = await _get_template_or_404(body.template_id, body.project_id)
    local_keys = {k.strip() for k in body.local_keys if k and k.strip()}
    to_import = []
    skipped = []
    for item in row.headers or []:
        key = (item.get("key") or "").strip()
        if not key:
            continue
        if key in local_keys:
            skipped.append(key)
        else:
            to_import.append(item)
    return StandardResponse(
        data={
            "template": _template_to_dict(row),
            "to_import": to_import,
            "skipped_keys": skipped,
            "import_count": len(to_import),
            "skip_count": len(skipped),
        }
    )
