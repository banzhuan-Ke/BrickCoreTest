"""被测应用 CRUD + 环境绑定（JWT + 项目权限）。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from tortoise.exceptions import IntegrityError

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_SCENE_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.models.perf import SutAppEnvBinding, SutApplication, SutServer
from app.models.sys import Environment, Project
from app.modules.perf.sut_resolve import resolve_servers, validate_bindings_payload

router = APIRouter(
    prefix="/sut-applications",
    tags=["被测应用"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_VIEW))],
)


def _normalize_roles_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for r in raw:
        s = str(r or "").strip()
        if s and s not in out:
            out.append(s[:64])
        if len(out) >= 50:
            break
    return out


def _serialize_app(row: SutApplication, *, binding_count: Optional[int] = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "roles": _normalize_roles_list(row.roles_json),
        "remark": row.remark or "",
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
        "create_by": row.create_by or "",
    }
    if binding_count is not None:
        data["binding_count"] = binding_count
    return data


class AppCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    roles: Optional[list[str]] = None
    remark: Optional[str] = Field(None, max_length=500)


class AppUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    roles: Optional[list[str]] = None
    remark: Optional[str] = Field(None, max_length=500)


class EnvBindingPut(BaseModel):
    environment_id: int
    bindings: list[dict[str, Any]] = Field(default_factory=list)


async def _get_app_or_404(app_id: int) -> SutApplication:
    row = await SutApplication.get_or_none(id=app_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="被测应用不存在")
    return row


@router.get("", summary="被测应用列表")
async def list_applications(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    rows = await SutApplication.filter(project_id=project_id, is_del=False).order_by("-id")
    app_ids = [r.id for r in rows]
    count_map: dict[int, int] = {}
    if app_ids:
        bindings = await SutAppEnvBinding.filter(application_id__in=app_ids)
        for b in bindings:
            count_map[b.application_id] = count_map.get(b.application_id, 0) + 1
    out = [_serialize_app(r, binding_count=count_map.get(r.id, 0)) for r in rows]
    return {"data": out, "total": len(out)}


@router.post(
    "",
    summary="创建被测应用",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def create_application(
    body: AppCreate,
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="名称不能为空")
    row = await SutApplication.create(
        project_id=body.project_id,
        name=name,
        roles_json=_normalize_roles_list(body.roles),
        remark=(body.remark or "").strip()[:500],
        create_by=username or "",
    )
    return _serialize_app(row, binding_count=0)


@router.get("/{app_id}", summary="被测应用详情")
async def get_application(
    app_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)
    cnt = await SutAppEnvBinding.filter(application_id=row.id).count()
    return _serialize_app(row, binding_count=cnt)


@router.patch(
    "/{app_id}",
    summary="更新被测应用",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def update_application(
    app_id: int,
    body: AppUpdate,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="名称不能为空")
        row.name = name
    if body.roles is not None:
        row.roles_json = _normalize_roles_list(body.roles)
    if body.remark is not None:
        row.remark = body.remark.strip()[:500]
    await row.save()
    cnt = await SutAppEnvBinding.filter(application_id=row.id).count()
    return _serialize_app(row, binding_count=cnt)


@router.delete(
    "/{app_id}",
    summary="删除被测应用",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_application(
    app_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    await SutAppEnvBinding.filter(application_id=row.id).delete()
    row.is_del = True
    await row.save()
    return {"ok": True}


@router.get("/{app_id}/env-bindings", summary="列出应用的全部环境绑定")
async def list_env_bindings(
    app_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)
    bindings = await SutAppEnvBinding.filter(application_id=app_id).order_by("environment_id")
    env_ids = [b.environment_id for b in bindings]
    envs = await Environment.filter(id__in=env_ids) if env_ids else []
    env_map = {e.id: e for e in envs}
    data = []
    for b in bindings:
        env = env_map.get(b.environment_id)
        data.append(
            {
                "environment_id": b.environment_id,
                "environment_name": getattr(env, "name", None) or "",
                "bindings": b.bindings_json or [],
                "update_time": b.update_time.isoformat() if b.update_time else None,
            }
        )
    return {"application_id": app_id, "data": data}


@router.put(
    "/{app_id}/env-bindings",
    summary="写入某一环境的角色→采集器绑定",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def put_env_binding(
    app_id: int,
    body: EnvBindingPut,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    env = await Environment.get_or_none(id=body.environment_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    if env.project_id != row.project_id:
        raise HTTPException(status_code=403, detail="环境不属于该应用所在项目")

    servers = await SutServer.filter(project_id=row.project_id, is_del=False)
    allowed = {s.id for s in servers}
    app_roles = set(_normalize_roles_list(row.roles_json))
    # 空数组 = 清除本环境绑定（与 DELETE 同语义）
    if isinstance(body.bindings, list) and len(body.bindings) == 0:
        deleted = await SutAppEnvBinding.filter(
            application_id=app_id,
            environment_id=body.environment_id,
        ).delete()
        return {
            "application_id": app_id,
            "environment_id": body.environment_id,
            "environment_name": env.name or "",
            "bindings": [],
            "deleted": int(deleted or 0),
        }
    try:
        cleaned, rejected, invalid_roles = validate_bindings_payload(
            body.bindings,
            allowed_server_ids=allowed,
            allowed_roles=app_roles if app_roles else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if invalid_roles:
        raise HTTPException(
            status_code=422,
            detail=f"绑定角色不在应用角色清单内: {invalid_roles}",
        )
    if rejected:
        raise HTTPException(
            status_code=422,
            detail=f"存在无效或不属于本项目的 server_id: {rejected}",
        )
    if not cleaned:
        raise HTTPException(status_code=422, detail="至少需要一条有效角色绑定；清空请用 DELETE 或传空数组")

    existing = await SutAppEnvBinding.get_or_none(
        application_id=app_id,
        environment_id=body.environment_id,
    )
    if existing:
        existing.bindings_json = cleaned
        await existing.save(update_fields=["bindings_json"])
        binding = existing
    else:
        try:
            binding = await SutAppEnvBinding.create(
                application_id=app_id,
                environment_id=body.environment_id,
                bindings_json=cleaned,
            )
        except IntegrityError:
            existing = await SutAppEnvBinding.get_or_none(
                application_id=app_id,
                environment_id=body.environment_id,
            )
            if not existing:
                raise
            existing.bindings_json = cleaned
            await existing.save(update_fields=["bindings_json"])
            binding = existing
    return {
        "application_id": app_id,
        "environment_id": body.environment_id,
        "environment_name": env.name or "",
        "bindings": binding.bindings_json,
    }


@router.delete(
    "/{app_id}/env-bindings/{environment_id}",
    summary="删除某一环境的绑定",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_env_binding(
    app_id: int,
    environment_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    deleted = await SutAppEnvBinding.filter(
        application_id=app_id,
        environment_id=environment_id,
    ).delete()
    return {"ok": True, "deleted": int(deleted or 0)}


@router.get("/{app_id}/resolve", summary="解析应用×环境→采集器（M3 预览）")
async def resolve_application_servers(
    app_id: int,
    environment_id: int = Query(...),
    roles: Optional[str] = Query(None, description="逗号分隔角色；空=全部"),
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_app_or_404(app_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)
    role_list = None
    if roles and roles.strip():
        role_list = [x.strip() for x in roles.split(",") if x.strip()]
    result = await resolve_servers(
        application_id=app_id,
        environment_id=environment_id,
        roles=role_list,
    )
    return result
