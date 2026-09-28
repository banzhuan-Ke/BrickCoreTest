"""MCP Wave D / M3：目录详情与显式创建（常用字段子集，写操作须确认）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.permissions import (
    API_CASE_EDIT,
    API_MANAGE_EDIT,
    API_PLAN_EDIT,
    API_SUITE_EDIT,
    APP_CASE_EDIT,
    APP_PLAN_EDIT,
    APP_SUITE_EDIT,
    MODULE_EDIT,
    MODULE_VIEW,
    PERF_SCENE_EDIT,
    UI_CASE_EDIT,
    UI_SUITE_EDIT,
    UI_TASK_EDIT,
)
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER
from app.mcp.auth import McpAuthContext, ensure_permission
from app.models.sys import TestCatalog

_ASSET_SPECS: dict[str, tuple[str, str]] = {
    "api_def": ("app.models.http.ApiDefinition", API_MANAGE_EDIT),
    "api_definition": ("app.models.http.ApiDefinition", API_MANAGE_EDIT),
    "api_case": ("app.models.http.ApiTestCase", API_CASE_EDIT),
    "api_suite": ("app.models.http.ApiTestSuite", API_SUITE_EDIT),
    "api_plan": ("app.models.http.ApiTestPlan", API_PLAN_EDIT),
    "ui_case": ("app.models.ui.Case", UI_CASE_EDIT),
    "ui_suite": ("app.models.ui.Suite", UI_SUITE_EDIT),
    "ui_task": ("app.models.ui.Task", UI_TASK_EDIT),
    "app_case": ("app.models.app.AppCase", APP_CASE_EDIT),
    "app_suite": ("app.models.app.AppSuite", APP_SUITE_EDIT),
    "app_plan": ("app.models.app.AppPlan", APP_PLAN_EDIT),
    "perf_scene": ("app.models.perf.PerfScene", PERF_SCENE_EDIT),
}


def _clip(text: Any, limit: int = 200) -> str:
    s = ("" if text is None else str(text)).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else _clip(value, 40)


def _http_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _obj_id(obj: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get("id")
    return getattr(obj, "id", None)


async def _require_project(ctx: McpAuthContext, project_id: int, *, member: bool = False) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(
        ctx,
        int(project_id),
        min_role=PROJECT_ROLE_MEMBER if member else PROJECT_ROLE_VIEWER,
    )


def _norm_ids(asset_ids: list[int] | None) -> list[int]:
    ids = []
    for raw in asset_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError) as exc:
            raise ValueError("asset_ids 必须是整数列表") from exc
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ValueError("请提供要移动的资产 ID")
    if len(ids) > 50:
        raise ValueError("单次最多移动 50 条资产")
    return ids


def _resolve_asset_spec(asset_type: str) -> tuple[str, str, str]:
    key = (asset_type or "").strip().lower()
    spec = _ASSET_SPECS.get(key)
    if not spec:
        allowed = "api_def / api_case / api_suite / api_plan / ui_case / ui_suite / ui_task / app_case / app_suite / app_plan / perf_scene"
        raise ValueError(f"不支持的 asset_type，可选：{allowed}")
    kind = "api_def" if key == "api_definition" else key
    return kind, spec[0], spec[1]


def _load_model(path: str):
    module_name, cls_name = path.rsplit(".", 1)
    import importlib

    return getattr(importlib.import_module(module_name), cls_name)


async def _owned_rows(model, ids: list[int], pid: int) -> tuple[list[Any], list[int]]:
    rows = []
    missing = []
    for asset_id in ids:
        row = await model.get_or_none(id=asset_id, is_del=False)
        if not row:
            missing.append(asset_id)
            continue
        if int(getattr(row, "project_id", 0) or 0) != pid:
            raise ValueError(f"资产 {asset_id} 不属于当前项目")
        rows.append(row)
    return rows, missing


def _catalog_brief(catalog: TestCatalog, counts: dict | None = None) -> dict[str, Any]:
    data = {
        "id": catalog.id,
        "name": catalog.name,
        "project_id": catalog.project_id,
        "parent_id": catalog.parent_id,
        "sort": catalog.sort,
        "description": _clip(catalog.description, 200),
        "username": catalog.username,
    }
    if counts:
        data["counts"] = {
            "api_defs": counts.get("api_defs", 0),
            "api_cases": counts.get("api_cases", 0),
            "ui_cases": counts.get("ui_cases", 0),
            "app_cases": counts.get("app_cases", 0),
            "ui_suites": counts.get("ui_suites", 0),
            "api_suites": counts.get("api_suites", 0),
            "perf_scenes": counts.get("perf_scenes", 0),
        }
    return data


async def tool_get_catalog_detail(
    ctx: McpAuthContext,
    project_id: int,
    catalog_id: int,
) -> dict[str, Any]:
    """获取目录详情与各类型资产数量。"""
    ensure_permission(ctx, MODULE_VIEW)
    pid = await _require_project(ctx, project_id)
    catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
    if not catalog:
        raise ValueError("目录不存在或不属于当前项目")
    from app.routers.sys.catalogs import _get_asset_counts

    return _catalog_brief(catalog, await _get_asset_counts(catalog.id))


async def tool_list_catalog_assets(
    ctx: McpAuthContext,
    project_id: int,
    catalog_id: int,
    include_children: bool = False,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出目录下的资产（名称摘要，不含步骤全文）。"""
    ensure_permission(ctx, MODULE_VIEW)
    pid = await _require_project(ctx, project_id)
    catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
    if not catalog:
        raise ValueError("目录不存在或不属于当前项目")
    from app.routers.sys.catalogs import _list_catalog_assets

    rows = await _list_catalog_assets(catalog.id, pid, bool(include_children))
    page_no = max(1, int(page or 1))
    page_size = min(50, max(1, int(size or 20)))
    start = (page_no - 1) * page_size
    items = []
    for row in rows[start : start + page_size]:
        items.append(
            {
                "id": row.get("id"),
                "name": _clip(row.get("name"), 120),
                "asset_type": row.get("asset_type"),
                "username": row.get("username") or "",
                "api_id": row.get("api_id"),
                "create_time": _iso(row.get("create_time")),
            }
        )
    return {
        "catalog_id": catalog.id,
        "project_id": pid,
        "total": len(rows),
        "page": page_no,
        "size": page_size,
        "items": items,
    }


async def tool_preview_create_catalog(
    ctx: McpAuthContext,
    project_id: int,
    name: str,
    parent_id: Optional[int] = None,
    description: str = "",
) -> dict[str, Any]:
    """预览创建测试目录。"""
    ensure_permission(ctx, MODULE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    catalog_name = (name or "").strip()
    if not catalog_name:
        raise ValueError("目录名称不能为空")
    if parent_id:
        parent = await TestCatalog.get_or_none(id=int(parent_id), project_id=pid, is_del=False)
        if not parent:
            raise ValueError("父目录不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "name": _clip(catalog_name, 80),
        "parent_id": int(parent_id) if parent_id else None,
        "description": _clip(description, 200),
        "warning": "将在当前项目新建一个测试目录",
    }
    token = await create_confirm_token(
        "create_catalog",
        {
            "project_id": pid,
            "name": catalog_name,
            "parent_id": int(parent_id) if parent_id else None,
            "description": (description or "").strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_catalog 并传入 confirm_token",
    }


async def tool_confirm_create_catalog(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    name: str,
    parent_id: Optional[int] = None,
    description: str = "",
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.sys.catalogs import create_catalog
    from app.schemas.sys import TestCatalogCreate

    ensure_permission(ctx, MODULE_EDIT)
    payload = await consume_confirm_token(confirm_token, "create_catalog", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("name") or "") != (name or "").strip():
        raise ValueError("name 与确认 Token 不匹配")
    if (payload.get("parent_id") or None) != (int(parent_id) if parent_id else None):
        raise ValueError("parent_id 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    try:
        catalog = await create_catalog(
            TestCatalogCreate(
                name=payload["name"],
                project_id=pid,
                parent_id=payload.get("parent_id"),
                description=payload.get("description") or None,
            ),
            username=ctx.username or "",
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    return {
        "catalog_id": catalog.id,
        "name": catalog.name,
        "project_id": pid,
        "parent_id": catalog.parent_id,
        "message": "目录已创建",
    }


async def tool_preview_move_assets_to_catalog(
    ctx: McpAuthContext,
    project_id: int,
    catalog_id: int,
    asset_type: str,
    asset_ids: list[int],
) -> dict[str, Any]:
    """预览把同一类资产移入目标目录。"""
    ensure_permission(ctx, MODULE_EDIT)
    kind, model_path, edit_perm = _resolve_asset_spec(asset_type)
    ensure_permission(ctx, edit_perm)
    pid = await _require_project(ctx, project_id, member=True)
    ids = _norm_ids(asset_ids)
    catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
    if not catalog:
        raise ValueError("目标目录不存在或不属于当前项目")
    rows, missing = await _owned_rows(_load_model(model_path), ids, pid)
    impact = {
        "project_id": pid,
        "catalog_id": catalog.id,
        "catalog_name": catalog.name,
        "asset_type": kind,
        "asset_ids": [row.id for row in rows],
        "missing_ids": missing,
        "warning": f"将把 {len(rows)} 条{kind}移到目录「{catalog.name}」",
    }
    token = await create_confirm_token(
        "move_assets_to_catalog",
        {"project_id": pid, "catalog_id": catalog.id, "asset_type": kind, "asset_ids": ids},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_move_assets_to_catalog 并传入 confirm_token",
    }


async def tool_confirm_move_assets_to_catalog(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    catalog_id: int,
    asset_type: str,
    asset_ids: list[int],
) -> dict[str, Any]:
    ensure_permission(ctx, MODULE_EDIT)
    kind, model_path, edit_perm = _resolve_asset_spec(asset_type)
    ensure_permission(ctx, edit_perm)
    payload = await consume_confirm_token(confirm_token, "move_assets_to_catalog", ctx.username)
    ids = _norm_ids(asset_ids)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("catalog_id") or 0) != int(catalog_id):
        raise ValueError("catalog_id 与确认 Token 不匹配")
    if (payload.get("asset_type") or "") != kind:
        raise ValueError("asset_type 与确认 Token 不匹配")
    if list(payload.get("asset_ids") or []) != ids:
        raise ValueError("asset_ids 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    catalog = await TestCatalog.get_or_none(id=int(payload["catalog_id"]), project_id=pid, is_del=False)
    if not catalog:
        raise ValueError("目标目录不存在或不属于当前项目")
    rows, missing = await _owned_rows(_load_model(model_path), ids, pid)
    for row in rows:
        row.catalog_id = catalog.id
        fields = ["catalog_id"]
        if hasattr(row, "update_by"):
            row.update_by = ctx.username or getattr(row, "update_by", None)
            fields.append("update_by")
        await row.save(update_fields=fields)
    return {
        "catalog_id": catalog.id,
        "asset_type": kind,
        "updated": len(rows),
        "missing_ids": missing,
        "message": f"已移动 {len(rows)} 条",
    }


async def tool_preview_create_api_definition(
    ctx: McpAuthContext,
    project_id: int,
    name: str,
    method: str,
    path: str,
    catalog_id: Optional[int] = None,
    description: str = "",
) -> dict[str, Any]:
    """预览创建接口定义（仅常用字段）。"""
    ensure_permission(ctx, API_MANAGE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    api_name = (name or "").strip()
    api_path = (path or "").strip()
    api_method = (method or "GET").strip().upper()
    if not api_name or not api_path:
        raise ValueError("接口名称和路径不能为空")
    if catalog_id:
        catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
        if not catalog:
            raise ValueError("目录不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "name": _clip(api_name, 80),
        "method": api_method,
        "path": _clip(api_path, 200),
        "catalog_id": int(catalog_id) if catalog_id else None,
        "warning": "将新建一条接口定义；请求头、Body 等请到编辑页补充",
    }
    token = await create_confirm_token(
        "create_api_definition",
        {
            "project_id": pid,
            "name": api_name,
            "method": api_method,
            "path": api_path,
            "catalog_id": int(catalog_id) if catalog_id else None,
            "description": (description or "").strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_api_definition 并传入 confirm_token",
    }


async def tool_confirm_create_api_definition(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    name: str,
    method: str,
    path: str,
    catalog_id: Optional[int] = None,
    description: str = "",
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.http.apis import create_api
    from app.schemas.http import ApiDefinitionCreate

    ensure_permission(ctx, API_MANAGE_EDIT)
    payload = await consume_confirm_token(confirm_token, "create_api_definition", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("name") or "") != (name or "").strip():
        raise ValueError("name 与确认 Token 不匹配")
    if (payload.get("method") or "").upper() != (method or "").strip().upper():
        raise ValueError("method 与确认 Token 不匹配")
    if (payload.get("path") or "") != (path or "").strip():
        raise ValueError("path 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    try:
        created = await create_api(
            ApiDefinitionCreate(
                name=payload["name"],
                method=payload["method"],
                path=payload["path"],
                project_id=pid,
                catalog_id=payload.get("catalog_id"),
                description=payload.get("description") or None,
            ),
            username=ctx.username or "",
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    api_id = _obj_id(created)
    return {
        "api_id": api_id,
        "name": payload["name"],
        "method": payload["method"],
        "path": payload["path"],
        "navigate": f"/api-module?api_id={api_id}",
        "message": "接口已创建，复杂字段请打开编辑页",
    }


async def tool_preview_create_api_test_case(
    ctx: McpAuthContext,
    project_id: int,
    api_id: int,
    name: str,
    catalog_id: Optional[int] = None,
    priority: str = "P2",
) -> dict[str, Any]:
    """预览创建接口用例（挂到已有接口，断言留空）。"""
    from app.models.http import ApiDefinition

    ensure_permission(ctx, API_CASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    case_name = (name or "").strip()
    if not case_name:
        raise ValueError("用例名称不能为空")
    api = await ApiDefinition.get_or_none(id=int(api_id), is_del=False)
    if not api or int(getattr(api, "project_id", 0) or 0) != pid:
        raise ValueError("接口不存在或不属于当前项目")
    if catalog_id:
        catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
        if not catalog:
            raise ValueError("目录不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "api_id": api.id,
        "api_name": api.name,
        "name": _clip(case_name, 80),
        "catalog_id": int(catalog_id) if catalog_id else api.catalog_id,
        "priority": (priority or "P2").strip() or "P2",
        "warning": "将新建一条空断言接口用例，请到编辑页补断言",
    }
    token = await create_confirm_token(
        "create_api_test_case",
        {
            "project_id": pid,
            "api_id": api.id,
            "name": case_name,
            "catalog_id": int(catalog_id) if catalog_id else None,
            "priority": impact["priority"],
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_api_test_case 并传入 confirm_token",
    }


async def tool_confirm_create_api_test_case(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    api_id: int,
    name: str,
    catalog_id: Optional[int] = None,
    priority: str = "P2",
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.http.cases import create_test_case
    from app.schemas.http import ApiTestCaseCreate

    ensure_permission(ctx, API_CASE_EDIT)
    payload = await consume_confirm_token(confirm_token, "create_api_test_case", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("api_id") or 0) != int(api_id):
        raise ValueError("api_id 与确认 Token 不匹配")
    if (payload.get("name") or "") != (name or "").strip():
        raise ValueError("name 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    try:
        created = await create_test_case(
            ApiTestCaseCreate(
                name=payload["name"],
                api_id=int(payload["api_id"]),
                project_id=pid,
                catalog_id=payload.get("catalog_id"),
                priority=payload.get("priority") or "P2",
            ),
            username=ctx.username or "",
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    case_id = _obj_id(created)
    return {
        "case_id": case_id,
        "api_id": int(payload["api_id"]),
        "name": payload["name"],
        "navigate": f"/api-case?edit_case_id={case_id}",
        "message": "接口用例已创建，请打开编辑页补充断言",
    }


async def tool_preview_create_ui_case(
    ctx: McpAuthContext,
    project_id: int,
    name: str,
    catalog_id: Optional[int] = None,
    level: str = "P2",
    description: str = "",
) -> dict[str, Any]:
    """预览创建 Web UI 用例（步骤留空，到编辑页补）。"""
    ensure_permission(ctx, UI_CASE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    case_name = (name or "").strip()
    if not case_name:
        raise ValueError("用例名称不能为空")
    if catalog_id:
        catalog = await TestCatalog.get_or_none(id=int(catalog_id), project_id=pid, is_del=False)
        if not catalog:
            raise ValueError("目录不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "name": _clip(case_name, 80),
        "catalog_id": int(catalog_id) if catalog_id else None,
        "level": (level or "P2").strip() or "P2",
        "warning": "将新建一条空步骤 Web 用例，步骤请到编辑页录制或粘贴",
    }
    token = await create_confirm_token(
        "create_ui_case",
        {
            "project_id": pid,
            "name": case_name,
            "catalog_id": int(catalog_id) if catalog_id else None,
            "level": impact["level"],
            "description": (description or "").strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_create_ui_case 并传入 confirm_token",
    }


async def tool_confirm_create_ui_case(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    name: str,
    catalog_id: Optional[int] = None,
    level: str = "P2",
    description: str = "",
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.ui.cases import create_case
    from app.schemas.ui import AddCaseForm

    ensure_permission(ctx, UI_CASE_EDIT)
    payload = await consume_confirm_token(confirm_token, "create_ui_case", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("name") or "") != (name or "").strip():
        raise ValueError("name 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    try:
        created = await create_case(
            AddCaseForm(
                name=payload["name"],
                project_id=pid,
                steps=[],
                username=ctx.username or "",
                catalog_id=payload.get("catalog_id"),
                level=payload.get("level") or "P2",
                description=payload.get("description") or None,
            )
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    case_id = _obj_id(created)
    return {
        "case_id": case_id,
        "name": payload["name"],
        "navigate": f"/case/edit/{case_id}",
        "message": "Web 用例已创建，请打开编辑页补充步骤",
    }
