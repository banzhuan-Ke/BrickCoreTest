"""性能测试业务链路模板 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, require_permissions
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_SCENE_VIEW
from app.models.perf import PerfJourneyTemplate
from app.models.sys import Project
from app.modules.perf.perf_journey import journey_to_scene_items, normalize_journey_config

router = APIRouter(prefix="/journey-templates", tags=["性能测试链路模板"])


class JourneyTemplateCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    journey: dict = Field(default_factory=dict)
    source_scene_id: Optional[int] = None


class JourneyTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    journey: Optional[dict] = None
    source_scene_id: Optional[int] = None


def _validate_journey_payload(raw_journey: dict) -> dict:
    journey = normalize_journey_config({"journey": raw_journey or {}})
    phases = journey.get("phases") or []
    if not phases:
        raise HTTPException(status_code=422, detail="链路至少配置一个阶段")
    if not any((p.get("steps") or []) for p in phases):
        raise HTTPException(status_code=422, detail="链路至少配置一个步骤")
    return journey


def _serialize(tpl: PerfJourneyTemplate) -> dict:
    return {
        "id": tpl.id,
        "project_id": tpl.project_id,
        "name": tpl.name,
        "description": tpl.description,
        "journey": tpl.journey or {},
        "source_scene_id": tpl.source_scene_id,
        "create_by": tpl.create_by,
        "create_time": tpl.create_time.strftime("%Y-%m-%d %H:%M:%S") if tpl.create_time else None,
        "update_time": tpl.update_time.strftime("%Y-%m-%d %H:%M:%S") if tpl.update_time else None,
    }


@router.get("", summary="链路模板列表", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def list_templates(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None),
):
    qs = PerfJourneyTemplate.filter(project_id=project_id, is_del=False)
    if keyword:
        qs = qs.filter(name__icontains=keyword.strip())
    rows = await qs.order_by("-id").all()
    return {"data": [_serialize(r) for r in rows], "total": len(rows)}


@router.post(
    "",
    summary="创建链路模板",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def create_template(
    body: JourneyTemplateCreate,
    username: str = Depends(get_current_username),
):
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    journey = _validate_journey_payload(body.journey)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="模板名称不能为空")
    tpl = await PerfJourneyTemplate.create(
        project_id=body.project_id,
        name=name,
        description=body.description,
        journey=journey,
        source_scene_id=body.source_scene_id,
        create_by=username,
    )
    return _serialize(tpl)


@router.get("/{template_id}", summary="链路模板详情", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def get_template(template_id: int):
    tpl = await PerfJourneyTemplate.get_or_none(id=template_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    data = _serialize(tpl)
    data["scene_items"] = journey_to_scene_items({"journey": tpl.journey or {}})
    return data


@router.put(
    "/{template_id}",
    summary="更新链路模板",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def update_template(template_id: int, body: JourneyTemplateUpdate):
    tpl = await PerfJourneyTemplate.get_or_none(id=template_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="模板名称不能为空")
        tpl.name = name
    if body.description is not None:
        tpl.description = body.description
    if body.source_scene_id is not None:
        tpl.source_scene_id = body.source_scene_id
    if body.journey is not None:
        tpl.journey = _validate_journey_payload(body.journey)
    await tpl.save()
    return _serialize(tpl)


@router.delete(
    "/{template_id}",
    summary="删除链路模板",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_template(template_id: int):
    tpl = await PerfJourneyTemplate.get_or_none(id=template_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl.is_del = True
    await tpl.save()
