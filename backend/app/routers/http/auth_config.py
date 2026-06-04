"""API Token 授权管理"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.api_auth_service import (
    DEFAULT_CUSTOM_CODE,
    auth_config_to_dict,
    preview_auth_config,
    refresh_auth_config,
)
from app.routers.http.utils import normalize_extractor
from app.core.auth import get_current_username, is_authenticated, require_permissions
from app.core.permissions import API_AUTH_EDIT, API_AUTH_VIEW
from app.models.http import ApiAuthConfig, ApiDefinition
from app.models.sys import Environment, Project
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/auth-config", tags=["API授权管理"])


def _normalize_auth_extractors(extractors: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """保存时统一为 {name, source, path}，兼容前端 type/expression。"""
    result = []
    for raw in extractors or []:
        ext = normalize_extractor(raw)
        if ext.get("name"):
            result.append(ext)
    return result


class AuthConfigCreate(BaseModel):
    project_id: int
    environment_id: int
    name: str = Field(..., min_length=1, max_length=100)
    auth_type: str = Field(default="api_login", description="api_login | custom_code")
    login_api_id: Optional[int] = None
    extractors: list[dict[str, Any]] = Field(default_factory=list)
    custom_code: Optional[str] = None
    ttl_minutes: int = Field(default=1440, ge=1, le=10080)
    refresh_before_minutes: int = Field(default=5, ge=0, le=120)
    refresh_mode: str = Field(default="on_execute")
    is_enabled: bool = True


class AuthConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    auth_type: Optional[str] = None
    login_api_id: Optional[int] = None
    extractors: Optional[list[dict[str, Any]]] = None
    custom_code: Optional[str] = None
    ttl_minutes: Optional[int] = Field(None, ge=1, le=10080)
    refresh_before_minutes: Optional[int] = Field(None, ge=0, le=120)
    refresh_mode: Optional[str] = None
    is_enabled: Optional[bool] = None


class AuthConfigTestRequest(BaseModel):
    """调试授权（不保存缓存）"""
    project_id: int
    environment_id: int
    auth_type: str = Field(default="api_login", description="api_login | custom_code")
    login_api_id: Optional[int] = None
    extractors: list[dict[str, Any]] = Field(default_factory=list)
    custom_code: Optional[str] = None


async def _enrich_dict(cfg: ApiAuthConfig) -> dict[str, Any]:
    env = await Environment.get_or_none(id=cfg.environment_id)
    api_name = ""
    if cfg.login_api_id:
        api = await ApiDefinition.get_or_none(id=cfg.login_api_id)
        api_name = api.name if api else ""
    return auth_config_to_dict(cfg, env.name if env else "", api_name)


@router.get("", summary="授权配置列表", dependencies=[Depends(require_permissions(API_AUTH_VIEW))])
async def list_auth_configs(
    project_id: int = Query(..., description="项目ID"),
    environment_id: Optional[int] = Query(None),
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    qs = ApiAuthConfig.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = [await _enrich_dict(r) for r in rows]
    return StandardResponse(data={"list": items, "total": total, "page": page, "size": size})


@router.post("", summary="新建授权配置", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def create_auth_config(
    body: AuthConfigCreate,
    username: str = Depends(get_current_username),
):
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    env = await Environment.get_or_none(id=body.environment_id, project_id=body.project_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    if body.auth_type not in ("api_login", "custom_code"):
        raise HTTPException(status_code=400, detail="auth_type 仅支持 api_login / custom_code")
    if body.auth_type == "api_login" and not body.login_api_id:
        raise HTTPException(status_code=400, detail="接口登录方式需选择登录接口")

    exists = await ApiAuthConfig.filter(
        project_id=body.project_id, environment_id=body.environment_id, name=body.name, is_del=False
    ).exists()
    if exists:
        raise HTTPException(status_code=400, detail="同环境下授权名称已存在")

    cfg = await ApiAuthConfig.create(
        project_id=body.project_id,
        environment_id=body.environment_id,
        name=body.name,
        auth_type=body.auth_type,
        login_api_id=body.login_api_id,
        extractors=_normalize_auth_extractors(body.extractors),
        custom_code=body.custom_code or (DEFAULT_CUSTOM_CODE if body.auth_type == "custom_code" else None),
        ttl_minutes=body.ttl_minutes,
        refresh_before_minutes=body.refresh_before_minutes,
        refresh_mode=body.refresh_mode,
        is_enabled=body.is_enabled,
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=await _enrich_dict(cfg), message="创建成功")


@router.get("/template/custom-code", summary="自定义授权代码模板", dependencies=[Depends(require_permissions(API_AUTH_VIEW))])
async def get_custom_code_template():
    return StandardResponse(data={"code": DEFAULT_CUSTOM_CODE})


@router.post("/test-preview", summary="调试授权（不写入缓存）", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def test_auth_preview(body: AuthConfigTestRequest):
    """按当前表单配置试跑登录/自定义代码，返回将注入的变量"""
    if body.auth_type not in ("api_login", "custom_code"):
        raise HTTPException(status_code=400, detail="auth_type 仅支持 api_login / custom_code")
    if body.auth_type == "api_login" and not body.login_api_id:
        raise HTTPException(status_code=400, detail="接口登录方式需选择登录接口")
    env = await Environment.get_or_none(id=body.environment_id, project_id=body.project_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    base_vars = dict(env.global_vars or {})
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if project and project.global_vars:
        base_vars = {**project.global_vars, **base_vars}
    try:
        variables = await preview_auth_config(
            project_id=body.project_id,
            environment_id=body.environment_id,
            auth_type=body.auth_type,
            login_api_id=body.login_api_id,
            extractors=_normalize_auth_extractors(body.extractors),
            custom_code=body.custom_code,
            base_variables=base_vars,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StandardResponse(
        data={
            "variables": variables,
            "usage_hint": "执行用例时在 Header/Body 中使用 ${{变量名}}，例如 ${{token}}",
        },
        message="调试成功",
    )


@router.get("/{config_id}", summary="授权配置详情", dependencies=[Depends(require_permissions(API_AUTH_VIEW))])
async def get_auth_config(config_id: int, project_id: int = Query(...)):
    cfg = await ApiAuthConfig.get_or_none(id=config_id, project_id=project_id, is_del=False)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    return StandardResponse(data=await _enrich_dict(cfg))


@router.put("/{config_id}", summary="更新授权配置", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def update_auth_config(
    config_id: int,
    body: AuthConfigUpdate,
    project_id: int = Query(...),
    username: str = Depends(get_current_username),
):
    cfg = await ApiAuthConfig.get_or_none(id=config_id, project_id=project_id, is_del=False)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")

    data = body.model_dump(exclude_unset=True)
    if "extractors" in data:
        data["extractors"] = _normalize_auth_extractors(data["extractors"])
    if "name" in data and data["name"] != cfg.name:
        dup = await ApiAuthConfig.filter(
            project_id=project_id, environment_id=cfg.environment_id, name=data["name"], is_del=False
        ).exclude(id=config_id).exists()
        if dup:
            raise HTTPException(status_code=400, detail="同环境下授权名称已存在")

    for k, v in data.items():
        setattr(cfg, k, v)
    cfg.update_by = username
    await cfg.save()
    return StandardResponse(data=await _enrich_dict(cfg), message="更新成功")


@router.delete("/{config_id}", summary="删除授权配置", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def delete_auth_config(
    config_id: int,
    project_id: int = Query(...),
    username: str = Depends(get_current_username),
):
    cfg = await ApiAuthConfig.get_or_none(id=config_id, project_id=project_id, is_del=False)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    cfg.is_del = True
    cfg.update_by = username
    await cfg.save(update_fields=["is_del", "update_by", "update_time"])
    return StandardResponse(message="删除成功")


@router.post("/{config_id}/refresh", summary="立即刷新授权", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def refresh_auth(
    config_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    cfg = await ApiAuthConfig.get_or_none(id=config_id, project_id=project_id, is_del=False)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    env = await Environment.get_or_none(id=cfg.environment_id, is_del=False)
    base_vars = dict(env.global_vars or {}) if env else {}
    project = await Project.get_or_none(id=cfg.project_id, is_del=False)
    if project and project.global_vars:
        base_vars = {**project.global_vars, **base_vars}
    try:
        cache = await refresh_auth_config(cfg, base_vars)
    except Exception as e:
        cfg.last_refresh_error = str(e)
        await cfg.save(update_fields=["last_refresh_error", "update_time"])
        raise HTTPException(status_code=400, detail=str(e))
    return StandardResponse(
        data={"cache_data": cache, "config": await _enrich_dict(cfg)},
        message="刷新成功",
    )


@router.post("/{config_id}/clear-cache", summary="清空授权缓存", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def clear_auth_cache(
    config_id: int,
    project_id: int = Query(...),
    username: str = Depends(get_current_username),
):
    cfg = await ApiAuthConfig.get_or_none(id=config_id, project_id=project_id, is_del=False)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    cfg.cache_data = {}
    cfg.cache_expires_at = None
    cfg.last_refresh_error = None
    cfg.update_by = username
    await cfg.save(update_fields=["cache_data", "cache_expires_at", "last_refresh_error", "update_by", "update_time"])
    return StandardResponse(message="缓存已清空")
