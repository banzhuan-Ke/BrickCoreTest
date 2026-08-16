"""API Token 授权管理"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.http.api_auth_service import (
    DEFAULT_CUSTOM_CODE,
    auth_config_to_dict,
    get_enabled_auth_config,
    persist_auth_preview_cache,
    preview_auth_config,
    refresh_auth_config,
)
from app.routers.http.utils import normalize_extractor
from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import API_AUTH_EDIT, API_AUTH_VIEW
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


def _release_auth_config_name(cfg: ApiAuthConfig) -> None:
    """软删时改名，释放 (project_id, environment_id, name) 唯一键，便于同名重建。"""
    suffix = f"__del_{cfg.id}"
    base = (cfg.name or "auth")[: max(1, 100 - len(suffix))]
    cfg.name = f"{base}{suffix}"


async def _purge_soft_deleted_auth_name(project_id: int, environment_id: int, name: str) -> None:
    """清掉同名软删残留（兼容历史未改名数据）。"""
    await ApiAuthConfig.filter(
        project_id=project_id,
        environment_id=environment_id,
        name=name,
        is_del=True,
    ).delete()


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
    """调试授权；传入 config_id 时会把调试结果写入该配置缓存"""
    project_id: int
    environment_id: int
    auth_type: str = Field(default="api_login", description="api_login | custom_code")
    login_api_id: Optional[int] = None
    extractors: list[dict[str, Any]] = Field(default_factory=list)
    custom_code: Optional[str] = None
    config_id: Optional[int] = Field(None, description="已有配置 ID；调试成功后写入缓存")


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

    await _purge_soft_deleted_auth_name(body.project_id, body.environment_id, body.name)

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


@router.post("/test-preview", summary="调试授权（可选写入缓存）", dependencies=[Depends(require_permissions(API_AUTH_EDIT))])
async def test_auth_preview(body: AuthConfigTestRequest):
    """按当前表单配置试跑登录/自定义代码，返回将注入的变量。

    若传入 config_id，调试成功后写入该配置缓存，便于立刻执行用例。
    """
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

    cache_written = False
    if body.config_id:
        cfg = await ApiAuthConfig.get_or_none(
            id=body.config_id, project_id=body.project_id, is_del=False
        )
        if not cfg:
            raise HTTPException(status_code=404, detail="授权配置不存在")
        if cfg.environment_id != body.environment_id:
            raise HTTPException(status_code=400, detail="调试环境与配置绑定环境不一致")
        try:
            await persist_auth_preview_cache(cfg, variables)
            cache_written = True
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"写入缓存失败: {e}")

    hint = "执行用例时在 Header/Body 中使用 ${{变量名}}，例如 ${{token}}"
    if cache_written:
        hint = "已写入授权缓存。" + hint
    else:
        hint = "调试未写入缓存（新建请先保存）。" + hint

    return StandardResponse(
        data={
            "variables": variables,
            "usage_hint": hint,
            "cache_written": cache_written,
        },
        message="调试成功",
    )

@router.get("/variables-preview", summary="变量插入预览：Token 授权变量", dependencies=[Depends(require_permissions(API_AUTH_VIEW))])
async def auth_variables_preview(
    project_id: int = Query(..., description="项目ID"),
    environment_id: int = Query(..., description="环境ID"),
):
    """返回当前环境下 Token 授权可插入的变量名及缓存预览（供插入变量面板）。"""
    env = await Environment.get_or_none(id=environment_id, project_id=project_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    cfg = await get_enabled_auth_config(project_id, environment_id)
    if not cfg:
        cfg = await ApiAuthConfig.filter(
            project_id=project_id, environment_id=environment_id, is_del=False
        ).order_by("-update_time").first()

    if not cfg:
        return StandardResponse(data={"auth_name": None, "is_enabled": False, "items": []})

    cache = cfg.cache_data if isinstance(cfg.cache_data, dict) else {}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for ex in cfg.extractors or []:
        name = str(ex.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({
            "name": name,
            "preview": cache.get(name),
            "description": f"授权「{cfg.name}」",
        })

    if cfg.auth_type == "custom_code":
        for name, value in cache.items():
            if name in seen:
                continue
            seen.add(name)
            items.append({
                "name": name,
                "preview": value,
                "description": f"授权「{cfg.name}」",
            })

    return StandardResponse(data={
        "auth_name": cfg.name,
        "is_enabled": cfg.is_enabled,
        "items": items,
    })


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
        await _purge_soft_deleted_auth_name(project_id, cfg.environment_id, data["name"])

    # 登录/提取规则变更后旧缓存键可能失效（如 token → token1），必须清空
    invalidate_cache = any(
        k in data for k in ("extractors", "login_api_id", "auth_type", "custom_code")
    )
    for k, v in data.items():
        setattr(cfg, k, v)
    if invalidate_cache:
        cfg.cache_data = {}
        cfg.cache_expires_at = None
        cfg.last_refresh_error = None
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
    _release_auth_config_name(cfg)
    cfg.is_del = True
    cfg.update_by = username
    await cfg.save(update_fields=["name", "is_del", "update_by", "update_time"])
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
