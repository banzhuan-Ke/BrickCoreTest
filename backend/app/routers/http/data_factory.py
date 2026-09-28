"""数据工厂：环境数据源 + SQL 模板 + 调试执行"""
import re
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from tortoise.expressions import Q

from app.core.platform.auth import get_current_username, require_permissions, verify_internal_token
from app.core.db.db_factory_service import (
    datasource_to_dict,
    encrypt_datasource_password,
    evaluate_db_assertions,
    execute_console_on_datasource,
    execute_sql_on_datasource,
    get_datasource_by_id,
    resolve_datasource,
    run_sql_templates_by_ids,
    sql_template_to_dict,
    substitute_sql,
    test_datasource_connection,
)
from app.modules.data_tools.executor import ToolExecutionError, execute_tool
from app.modules.data_tools.registry import TOOL_CATEGORIES, get_tool_definition, list_tools
from app.modules.data_tools.tag_refs import (
    RESOURCE_TYPE_LABELS,
    build_project_df_tag_usage_index,
    get_tags_usages,
)
from app.modules.data_tools.tag_service import format_record_output, normalize_output_data_for_storage
from app.core.platform.permissions import DATA_FACTORY_EDIT, DATA_FACTORY_VIEW
from app.models.http import DataToolFavorite, DataToolRecord, EnvDatasource, SqlTemplate
from app.models.sys import User
from app.models.sys import Environment, Project
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/data-factory", tags=["数据工厂"])


class DatasourceCreate(BaseModel):
    project_id: int
    environment_id: int
    name: str = Field(..., min_length=1, max_length=100)
    db_type: str = Field(default="mysql")
    host: str
    port: int = Field(default=3306, ge=1, le=65535)
    database_name: str
    username: Optional[str] = ""
    password: Optional[str] = None
    allow_write: bool = False
    max_rows: int = Field(default=100, ge=1, le=1000)
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    is_default: bool = False
    is_enabled: bool = True
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机测连/查询")


class DatasourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    allow_write: Optional[bool] = None
    max_rows: Optional[int] = Field(None, ge=1, le=1000)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=120)
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None


class DatasourceTestBody(BaseModel):
    password: Optional[str] = None
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机测连")


def _datasource_for_test(
    *,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
    db_type: str = "mysql",
    timeout_seconds: int = 10,
) -> EnvDatasource:
    return EnvDatasource(
        db_type=db_type or "mysql",
        host=host,
        port=port,
        database_name=database_name,
        username=username or "",
        password_encrypted=encrypt_datasource_password(password or ""),
        timeout_seconds=timeout_seconds,
    )


class SqlTemplateCreate(BaseModel):
    project_id: int
    datasource_id: int
    name: str = Field(..., min_length=1, max_length=100)
    template_type: str = Field(default="setup", description="setup/teardown/query")
    sql_text: str
    description: Optional[str] = None
    environment_id: Optional[int] = None
    is_enabled: bool = True


class SqlTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    datasource_id: Optional[int] = None
    template_type: Optional[str] = None
    sql_text: Optional[str] = None
    description: Optional[str] = None
    environment_id: Optional[int] = None
    is_enabled: Optional[bool] = None


class SqlExecuteRequest(BaseModel):
    project_id: int
    environment_id: int
    datasource_id: int
    sql: str
    variables: dict[str, Any] = Field(default_factory=dict)
    for_assertion: bool = False
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机执行")


class ConsoleExecuteRequest(BaseModel):
    """查询控制台执行（人工工作台）。"""

    project_id: int
    environment_id: int
    datasource_id: int
    sql: str = Field(..., min_length=1, max_length=200_000, description="SQL 或 Redis 命令")
    variables: dict[str, Any] = Field(default_factory=dict)
    max_rows: Optional[int] = Field(None, ge=1, le=1000, description="可选行数上限，默认 ≤200 且不超过数据源配置")
    confirm_write: bool = Field(False, description="写操作二次确认标记")
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机执行")


class ConsoleCatalogRequest(BaseModel):
    """查询控制台对象目录（只读）。"""

    project_id: int
    environment_id: int
    datasource_id: int
    scope: str = Field(
        "objects",
        description="objects|columns|indexes|ddl|sample；Redis 时 object_name 为 SCAN 前缀",
    )
    object_name: Optional[str] = Field(
        None, description="表/索引/key 名；Redis objects 时为 SCAN 前缀"
    )
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机读取")


class SqlTemplateExecuteRequest(BaseModel):
    project_id: int
    environment_id: int
    template_id: int
    variables: dict[str, Any] = Field(default_factory=dict)
    worker_id: Optional[int] = Field(None, description="可选：经空闲 PerfWorker 本机执行")


class DbAssertionTestRequest(BaseModel):
    project_id: int
    environment_id: int
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class UiSuiteDbHooksRequest(BaseModel):
    suite_id: int
    environment_id: int
    suite_execution_id: int
    variables: dict[str, Any] = Field(default_factory=dict)
    phase: str = Field(default="post", description="post=teardown+db_assert")


class EvaluateAssertionRequest(BaseModel):
    project_id: int
    environment_id: int
    assertion: dict[str, Any]
    variables: dict[str, Any] = Field(default_factory=dict)


class FavoriteItem(BaseModel):
    item_type: str = Field(..., description="tool|tag")
    item_key: str = Field(..., min_length=1, max_length=64)


class FavoriteReorderRequest(BaseModel):
    items: list[FavoriteItem] = Field(default_factory=list)


async def _enrich_datasource(ds: EnvDatasource) -> dict[str, Any]:
    env = await Environment.get_or_none(id=ds.environment_id)
    return datasource_to_dict(ds, env.name if env else "")


async def _enrich_template(tpl: SqlTemplate) -> dict[str, Any]:
    ds = await EnvDatasource.get_or_none(id=tpl.datasource_id)
    env_name = ""
    if tpl.environment_id:
        env = await Environment.get_or_none(id=tpl.environment_id)
        env_name = env.name if env else ""
    return sql_template_to_dict(tpl, ds.name if ds else "", env_name)


async def _clear_other_defaults(project_id: int, environment_id: int, exclude_id: Optional[int] = None):
    qs = EnvDatasource.filter(
        project_id=project_id,
        environment_id=environment_id,
        is_del=False,
        is_default=True,
    )
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    await qs.update(is_default=False)


@router.get("/datasources", summary="数据源列表", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def list_datasources(
    project_id: int = Query(...),
    environment_id: Optional[int] = Query(None),
    keyword: Optional[str] = None,
    enabled_only: bool = Query(False, description="仅返回已启用数据源（查询控制台用）"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    qs = EnvDatasource.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    if enabled_only:
        qs = qs.filter(is_enabled=True)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = [await _enrich_datasource(r) for r in rows]
    return StandardResponse(data={"list": items, "total": total, "page": page, "size": size})


@router.post("/datasources", summary="新建数据源", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def create_datasource(body: DatasourceCreate, username: str = Depends(get_current_username)):
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    env = await Environment.get_or_none(id=body.environment_id, is_del=False, project_id=body.project_id)
    if not project or not env:
        raise HTTPException(status_code=422, detail="项目或环境不存在")

    exists = await EnvDatasource.filter(
        project_id=body.project_id, environment_id=body.environment_id, name=body.name, is_del=False
    ).exists()
    if exists:
        raise HTTPException(status_code=422, detail="同环境下数据源名称已存在")

    db_type = (body.db_type or "mysql").lower()
    if db_type not in ("mysql", "postgresql", "redis", "elasticsearch"):
        raise HTTPException(status_code=422, detail="db_type 须为 mysql、postgresql、redis 或 elasticsearch")

    password_text = (body.password or "").strip()
    username = (body.username or "").strip()
    auth_optional = db_type in ("redis", "elasticsearch")
    if not auth_optional and not password_text:
        raise HTTPException(status_code=422, detail="请填写数据库密码")
    if not auth_optional and not username:
        raise HTTPException(status_code=422, detail="请填写数据库用户名")

    if body.is_default:
        await _clear_other_defaults(body.project_id, body.environment_id)

    ds = await EnvDatasource.create(
        project_id=body.project_id,
        environment_id=body.environment_id,
        name=body.name,
        db_type=db_type,
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=username,
        password_encrypted=encrypt_datasource_password(password_text),
        allow_write=body.allow_write,
        max_rows=body.max_rows,
        timeout_seconds=body.timeout_seconds,
        is_default=body.is_default,
        is_enabled=body.is_enabled,
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=await _enrich_datasource(ds))


@router.put("/datasources/{ds_id}", summary="更新数据源", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def update_datasource(ds_id: int, body: DatasourceUpdate, username: str = Depends(get_current_username)):
    ds = await EnvDatasource.get_or_none(id=ds_id, is_del=False)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")

    if body.name and body.name != ds.name:
        exists = await EnvDatasource.filter(
            project_id=ds.project_id,
            environment_id=ds.environment_id,
            name=body.name,
            is_del=False,
        ).exclude(id=ds_id).exists()
        if exists:
            raise HTTPException(status_code=422, detail="同环境下数据源名称已存在")
        ds.name = body.name

    if body.db_type is not None:
        db_type = (body.db_type or "mysql").lower()
        if db_type not in ("mysql", "postgresql", "redis", "elasticsearch"):
            raise HTTPException(status_code=422, detail="db_type 须为 mysql、postgresql、redis 或 elasticsearch")
        ds.db_type = db_type

    for field in ("host", "port", "database_name", "username", "allow_write", "max_rows", "timeout_seconds", "is_enabled"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(ds, field, val)

    if body.password is not None:
        password_text = body.password.strip()
        if password_text:
            ds.password_encrypted = encrypt_datasource_password(password_text)

    if body.is_default is not None:
        if body.is_default:
            await _clear_other_defaults(ds.project_id, ds.environment_id, exclude_id=ds.id)
        ds.is_default = body.is_default

    ds.update_by = username
    await ds.save()
    return StandardResponse(data=await _enrich_datasource(ds))


@router.delete("/datasources/{ds_id}", summary="删除数据源", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def delete_datasource(ds_id: int):
    ds = await EnvDatasource.get_or_none(id=ds_id, is_del=False)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    ds.is_del = True
    await ds.save()
    return StandardResponse(message="已删除")


@router.post("/datasources/test-connection", summary="测试连接（不落库）", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def test_connection_preview(body: DatasourceCreate):
    db_type = (body.db_type or "mysql").lower()
    password_text = (body.password or "").strip()
    username = (body.username or "").strip()
    auth_optional = db_type in ("redis", "elasticsearch")
    if not auth_optional and not password_text:
        raise HTTPException(status_code=422, detail="请填写数据库密码")
    if not auth_optional and not username:
        raise HTTPException(status_code=422, detail="请填写数据库用户名")
    temp = _datasource_for_test(
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=username,
        password=password_text,
        db_type=db_type,
        timeout_seconds=body.timeout_seconds,
    )
    if body.worker_id:
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            map_proxy_error_to_result,
            require_df_proxy_worker,
            send_df_probe_via_worker,
        )

        try:
            worker = await require_df_proxy_worker(body.project_id, int(body.worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=temp,
                mode="ping",
                password_override=password_text,
            )
        except WorkerProxyError as exc:
            result = map_proxy_error_to_result(exc)
        return StandardResponse(data=result)
    result = await test_datasource_connection(temp)
    return StandardResponse(data=result)


@router.post("/datasources/{ds_id}/test", summary="测试数据源连接", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def test_datasource(
    ds_id: int,
    body: Optional[DatasourceTestBody] = Body(default=None),
):
    ds = await EnvDatasource.get_or_none(id=ds_id, is_del=False)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    password_override = (body.password if body else None) or None
    if password_override is not None:
        password_override = password_override.strip() or None
    worker_id = getattr(body, "worker_id", None) if body else None
    if worker_id:
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            map_proxy_error_to_result,
            require_df_proxy_worker,
            send_df_probe_via_worker,
        )

        try:
            worker = await require_df_proxy_worker(int(ds.project_id), int(worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="ping",
                password_override=password_override,
            )
        except WorkerProxyError as exc:
            result = map_proxy_error_to_result(exc)
        return StandardResponse(data=result)
    if password_override:
        temp = _datasource_for_test(
            host=ds.host,
            port=int(ds.port or 3306),
            database_name=ds.database_name,
            username=ds.username,
            password=password_override,
            db_type=ds.db_type or "mysql",
            timeout_seconds=int(ds.timeout_seconds or 10),
        )
        result = await test_datasource_connection(temp)
    else:
        result = await test_datasource_connection(ds)
    return StandardResponse(data=result)


@router.get("/sql-templates", summary="SQL 模板列表", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def list_sql_templates(
    project_id: int = Query(...),
    environment_id: Optional[int] = Query(None),
    template_type: Optional[str] = Query(None),
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    qs = SqlTemplate.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    if template_type:
        qs = qs.filter(template_type=template_type)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = [await _enrich_template(r) for r in rows]
    return StandardResponse(data={"list": items, "total": total, "page": page, "size": size})


@router.post("/sql-templates", summary="新建 SQL 模板", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def create_sql_template(body: SqlTemplateCreate, username: str = Depends(get_current_username)):
    ds = await get_datasource_by_id(body.datasource_id, body.project_id)
    if not ds:
        raise HTTPException(status_code=422, detail="数据源不存在")
    if body.template_type not in ("setup", "teardown", "query"):
        raise HTTPException(status_code=422, detail="template_type 必须为 setup/teardown/query")

    exists = await SqlTemplate.filter(project_id=body.project_id, name=body.name, is_del=False).exists()
    if exists:
        raise HTTPException(status_code=422, detail="模板名称已存在")

    tpl = await SqlTemplate.create(
        project_id=body.project_id,
        environment_id=body.environment_id or ds.environment_id,
        datasource_id=body.datasource_id,
        name=body.name,
        template_type=body.template_type,
        sql_text=body.sql_text,
        description=body.description,
        is_enabled=body.is_enabled,
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=await _enrich_template(tpl))


@router.put("/sql-templates/{tpl_id}", summary="更新 SQL 模板", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def update_sql_template(tpl_id: int, body: SqlTemplateUpdate, username: str = Depends(get_current_username)):
    tpl = await SqlTemplate.get_or_none(id=tpl_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=404, detail="SQL 模板不存在")

    if body.name and body.name != tpl.name:
        exists = await SqlTemplate.filter(project_id=tpl.project_id, name=body.name, is_del=False).exclude(id=tpl_id).exists()
        if exists:
            raise HTTPException(status_code=422, detail="模板名称已存在")
        tpl.name = body.name

    if body.datasource_id is not None:
        ds = await get_datasource_by_id(body.datasource_id, tpl.project_id)
        if not ds:
            raise HTTPException(status_code=422, detail="数据源不存在")
        tpl.datasource_id = body.datasource_id

    if body.template_type is not None:
        if body.template_type not in ("setup", "teardown", "query"):
            raise HTTPException(status_code=422, detail="template_type 必须为 setup/teardown/query")
        tpl.template_type = body.template_type

    if body.sql_text is not None:
        tpl.sql_text = body.sql_text
    if body.description is not None:
        tpl.description = body.description
    if body.environment_id is not None:
        tpl.environment_id = body.environment_id
    if body.is_enabled is not None:
        tpl.is_enabled = body.is_enabled

    tpl.update_by = username
    await tpl.save()
    return StandardResponse(data=await _enrich_template(tpl))


@router.delete("/sql-templates/{tpl_id}", summary="删除 SQL 模板", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def delete_sql_template(tpl_id: int):
    tpl = await SqlTemplate.get_or_none(id=tpl_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=404, detail="SQL 模板不存在")
    tpl.is_del = True
    await tpl.save()
    return StandardResponse(message="已删除")


@router.post("/sql/execute", summary="调试执行 SQL", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def execute_sql_debug(body: SqlExecuteRequest):
    ds, ds_err = await resolve_datasource(body.environment_id, body.project_id, body.datasource_id)
    if ds_err or not ds:
        raise HTTPException(status_code=422, detail=ds_err or "数据源不可用")
    if body.worker_id:
        from app.core.db.db_factory_service import substitute_sql
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            require_df_proxy_worker_http,
            send_df_probe_via_worker,
        )
        from app.modules.http.worker_http_proxy import to_http_exception

        final_sql, replacements = substitute_sql(body.sql, body.variables or {})
        try:
            worker = await require_df_proxy_worker_http(body.project_id, int(body.worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="execute",
                statement=final_sql,
                allow_write=bool(ds.allow_write) and not body.for_assertion,
                for_assertion=bool(body.for_assertion),
                max_rows=int(ds.max_rows or 100),
            )
        except WorkerProxyError as exc:
            raise to_http_exception(exc) from exc
        result["sql"] = final_sql
        result["replacements"] = replacements
        return StandardResponse(data=result)
    result = await execute_sql_on_datasource(
        ds, body.sql, body.variables, for_assertion=body.for_assertion
    )
    return StandardResponse(data=result)


@router.post(
    "/console/execute",
    summary="查询控制台执行",
    dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))],
)
async def execute_console(body: ConsoleExecuteRequest):
    """选环境/数据源后手写 SQL 或 Redis 命令；写操作需 confirm_write=true。"""
    ds, ds_err = await resolve_datasource(body.environment_id, body.project_id, body.datasource_id)
    if ds_err or not ds:
        raise HTTPException(status_code=422, detail=ds_err or "数据源不可用")
    if body.worker_id:
        from app.core.db.db_drivers import enrich_execute_result, is_write_command
        from app.core.db.db_factory_service import resolve_console_max_rows, substitute_sql
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            require_df_proxy_worker_http,
            send_df_probe_via_worker,
        )
        from app.modules.http.worker_http_proxy import to_http_exception

        statement = (body.sql or "").strip()
        db_type = (ds.db_type or "mysql").lower()
        needs_write = is_write_command(statement, db_type=db_type)
        if needs_write and not bool(ds.allow_write):
            raise HTTPException(
                status_code=422,
                detail="当前数据源为只读，不允许执行写操作；请在数据源配置中开启「允许写操作」",
            )
        if needs_write and not body.confirm_write:
            return StandardResponse(
                data=enrich_execute_result(
                    {
                        "success": False,
                        "error": "写操作需二次确认后重试",
                        "rows": [],
                        "row_count": 0,
                        "affected_rows": 0,
                        "elapsed_ms": 0,
                        "requires_confirm": True,
                        "is_write": True,
                    }
                )
            )
        final_sql, replacements = substitute_sql(statement, body.variables or {})
        limit = resolve_console_max_rows(ds.max_rows, body.max_rows)
        try:
            worker = await require_df_proxy_worker_http(body.project_id, int(body.worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="execute",
                statement=final_sql,
                allow_write=bool(ds.allow_write),
                for_assertion=False,
                max_rows=limit,
            )
        except WorkerProxyError as exc:
            raise to_http_exception(exc) from exc
        result["sql"] = final_sql
        result["replacements"] = replacements
        result["is_write"] = needs_write
        result["requires_confirm"] = False
        result["max_rows_applied"] = limit
        return StandardResponse(data=result)
    result = await execute_console_on_datasource(
        ds,
        body.sql,
        body.variables,
        max_rows=body.max_rows,
        confirm_write=bool(body.confirm_write),
    )
    # 只读源写操作：明确 422；需确认：200 + requires_confirm 由前端弹框后重试
    if result.get("is_write") and not result.get("success") and not result.get("requires_confirm"):
        err = str(result.get("error") or "不允许写操作")
        if "只读" in err:
            raise HTTPException(status_code=422, detail=err)
    return StandardResponse(data=result)


@router.post(
    "/console/catalog",
    summary="查询控制台对象目录",
    dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))],
)
async def console_catalog(body: ConsoleCatalogRequest):
    """只读列出表/索引/列/DDL/Redis SCAN；可选经执行机（与控制台执行同一台）。"""
    from app.core.db.db_factory_service import (
        _catalog_sql_statements,
        fetch_catalog_on_datasource,
        reshape_catalog_execute_result,
    )

    ds, ds_err = await resolve_datasource(body.environment_id, body.project_id, body.datasource_id)
    if ds_err or not ds:
        raise HTTPException(status_code=422, detail=ds_err or "数据源不可用")
    scope = (body.scope or "objects").strip().lower()
    if scope not in ("objects", "columns", "fields", "indexes", "ddl", "sample"):
        raise HTTPException(
            status_code=422,
            detail="scope 须为 objects、columns、fields、indexes、ddl 或 sample",
        )

    if body.worker_id:
        from app.core.db.db_drivers import CATALOG_OBJECT_LIMIT, CATALOG_REDIS_LIMIT
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            require_df_proxy_worker_http,
            send_df_probe_via_worker,
        )
        from app.modules.http.worker_http_proxy import to_http_exception

        try:
            statement = _catalog_sql_statements(ds, scope=scope, object_name=body.object_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        max_rows = (
            CATALOG_REDIS_LIMIT
            if (ds.db_type or "").lower() == "redis"
            else CATALOG_OBJECT_LIMIT
        )
        try:
            worker = await require_df_proxy_worker_http(body.project_id, int(body.worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="execute",
                statement=statement,
                allow_write=False,
                for_assertion=True,
                max_rows=max_rows,
            )
        except WorkerProxyError as exc:
            raise to_http_exception(exc) from exc
        return StandardResponse(
            data=reshape_catalog_execute_result(
                ds,
                scope=scope,
                execute_result=result,
                object_name=body.object_name,
            )
        )

    # 非法参数与经执行机路径一致：422；连接/查询失败仍 200 + success=false
    if scope in ("columns", "fields", "indexes", "ddl", "sample") or (
        ds.db_type or ""
    ).lower() in ("redis", "elasticsearch"):
        try:
            _catalog_sql_statements(ds, scope=scope, object_name=body.object_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = await fetch_catalog_on_datasource(
        ds, scope=scope, object_name=body.object_name
    )
    return StandardResponse(data=data)


@router.post("/sql-templates/execute", summary="调试执行 SQL 模板", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def execute_template_debug(body: SqlTemplateExecuteRequest):
    tpl = await SqlTemplate.get_or_none(id=body.template_id, project_id=body.project_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=422, detail="SQL 模板不存在")
    ds = await get_datasource_by_id(tpl.datasource_id, body.project_id)
    if not ds:
        raise HTTPException(status_code=422, detail="关联数据源不存在")
    if body.worker_id:
        from app.core.db.db_factory_service import substitute_sql
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            require_df_proxy_worker_http,
            send_df_probe_via_worker,
        )
        from app.modules.http.worker_http_proxy import to_http_exception

        final_sql, replacements = substitute_sql(tpl.sql_text, body.variables or {})
        try:
            worker = await require_df_proxy_worker_http(body.project_id, int(body.worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="execute",
                statement=final_sql,
                allow_write=bool(ds.allow_write),
                for_assertion=False,
                max_rows=int(ds.max_rows or 100),
            )
        except WorkerProxyError as exc:
            raise to_http_exception(exc) from exc
        result["sql"] = final_sql
        result["replacements"] = replacements
        result["template_id"] = tpl.id
        result["template_name"] = tpl.name
        return StandardResponse(data=result)
    result = await execute_sql_on_datasource(ds, tpl.sql_text, body.variables, for_assertion=False)
    result["template_id"] = tpl.id
    result["template_name"] = tpl.name
    return StandardResponse(data=result)


@router.post("/db-assertions/test", summary="调试数据库断言", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def test_db_assertions(body: DbAssertionTestRequest):
    result = await evaluate_db_assertions(
        body.assertions, body.variables, body.environment_id, body.project_id, use_env_default=True
    )
    return StandardResponse(data=result)


@router.post(
    "/internal/evaluate-assertion",
    summary="单条库断言（Runner UI 步骤内部调用）",
    dependencies=[Depends(verify_internal_token)],
)
async def internal_evaluate_assertion(body: EvaluateAssertionRequest):
    result = await evaluate_db_assertions(
        [body.assertion],
        body.variables,
        body.environment_id,
        body.project_id,
        use_env_default=True,
    )
    item = (result.get("results") or [{}])[0]
    return StandardResponse(
        data={
            "passed": item.get("passed", False),
            "result": item,
            "all_passed": result.get("all_passed", False),
        }
    )


@router.post(
    "/internal/ui-suite-hooks",
    summary="UI 套件执行后 SQL/库断言（Runner 内部调用）",
    dependencies=[Depends(verify_internal_token)],
)
async def run_ui_suite_db_hooks(body: UiSuiteDbHooksRequest):
    from app.modules.ui.ui_suite_hooks import run_ui_suite_post_hooks
    from app.models.ui import Suite, UiSuiteExecution

    suite = await Suite.get_or_none(id=body.suite_id, is_del=False)
    record = await UiSuiteExecution.get_or_none(id=body.suite_execution_id, is_del=False)
    if not suite or not record:
        raise HTTPException(status_code=404, detail="套件或执行记录不存在")

    hooks_result = await run_ui_suite_post_hooks(
        suite=suite,
        record=record,
        environment_id=body.environment_id,
        variables=body.variables,
    )
    return StandardResponse(
        data={
            "hooks_result": hooks_result,
            "all_passed": hooks_result.get("all_passed", True),
        }
    )


# ============ 通用数据工厂工具箱 ============

_TAG_PATTERN = re.compile(r"^[\w\u4e00-\u9fa5-]{1,64}$")


class ToolExecuteRequest(BaseModel):
    tool_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class ToolRecordCreate(BaseModel):
    project_id: int
    environment_id: Optional[int] = None
    tool_id: str
    tool_name: str
    tool_category: str
    tag: str = Field(..., min_length=1, max_length=64)
    tags: list[str] = Field(default_factory=list)
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: Any = None
    output_text: Optional[str] = None
    remark: Optional[str] = None


class ToolRecordUpdate(BaseModel):
    """使用记录仅允许修改备注与生效环境。"""
    remark: Optional[str] = None
    environment_id: Optional[int] = None


def _validate_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag or not _TAG_PATTERN.match(tag):
        raise HTTPException(status_code=422, detail="标签仅支持字母数字下划线中文连字符，1～64 字符")
    return tag


async def _check_tag_unique(project_id: int, environment_id: Optional[int], tag: str, exclude_id: Optional[int] = None):
    qs = DataToolRecord.filter(project_id=project_id, tag=tag, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    else:
        qs = qs.filter(environment_id__isnull=True)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    if await qs.exists():
        raise HTTPException(status_code=422, detail=f"标签「{tag}」在当前项目/环境下已存在")


def _record_to_dict(row: DataToolRecord, env_name: str = "") -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "environment_id": row.environment_id,
        "environment_name": env_name,
        "tool_id": row.tool_id,
        "tool_name": row.tool_name,
        "tool_category": row.tool_category,
        "tag": row.tag,
        "tags": row.tags or [],
        "input_data": row.input_data or {},
        "output_data": row.output_data,
        "output_text": row.output_text or format_record_output(row.output_data, row.output_text),
        "remark": row.remark,
        "create_by": row.create_by,
        "create_time": row.create_time,
        "update_time": row.update_time,
    }


@router.get("/tools/catalog", summary="通用工具目录", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def get_tools_catalog(category: Optional[str] = Query(None)):
    return StandardResponse(data={
        "categories": TOOL_CATEGORIES,
        "tools": list_tools(category),
    })


@router.get(
    "/tools/inline-catalog",
    summary="可内联插入的工具目录（用例 ${{dt:...}}）",
    dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))],
)
async def get_inline_tools_catalog():
    from app.modules.data_tools.inline_tools import list_inline_insertable_tools

    tools = list_inline_insertable_tools()
    cat_ids = {t["category"] for t in tools}
    categories = [c for c in TOOL_CATEGORIES if c["id"] in cat_ids]
    return StandardResponse(data={"categories": categories, "tools": tools})


@router.post("/tools/execute", summary="执行通用工具", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def execute_data_tool(body: ToolExecuteRequest):
    try:
        result = execute_tool(body.tool_id, body.inputs)
    except ToolExecutionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    definition = get_tool_definition(body.tool_id)
    return StandardResponse(data={
        **result,
        "tool_id": body.tool_id,
        "tool_name": definition["name"] if definition else body.tool_id,
        "tool_category": definition["category"] if definition else "",
    })


def _attach_usage_to_record(item: dict[str, Any], usages: list[dict[str, Any]]) -> None:
    item["usage_count"] = len(usages)
    item["usages"] = [
        {
            **u,
            "resource_type_label": RESOURCE_TYPE_LABELS.get(u["resource_type"], u["resource_type"]),
        }
        for u in usages
    ]


@router.get("/tool-records", summary="工具使用记录列表", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def list_tool_records(
    project_id: int = Query(...),
    environment_id: Optional[int] = Query(None),
    tool_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    include_usages: bool = Query(True, description="是否附带引用位置（同项目扫描）"),
):
    qs = DataToolRecord.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    if tool_id:
        qs = qs.filter(tool_id=tool_id)
    if tag:
        qs = qs.filter(tag__icontains=tag)
    if keyword:
        qs = qs.filter(Q(tag__icontains=keyword) | Q(tool_name__icontains=keyword))
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    usage_index: dict[str, list] = {}
    if include_usages and rows:
        usage_index = await build_project_df_tag_usage_index(project_id)

    items = []
    for row in rows:
        env_name = ""
        if row.environment_id:
            env = await Environment.get_or_none(id=row.environment_id)
            env_name = env.name if env else ""
        item = _record_to_dict(row, env_name)
        if include_usages:
            tags_on_record = {row.tag, *(row.tags or [])}
            merged_usages: list[dict] = []
            seen: set[tuple] = set()
            for t in tags_on_record:
                for u in usage_index.get(t, []):
                    key = (u["resource_type"], u["resource_id"], u["location"])
                    if key not in seen:
                        seen.add(key)
                        merged_usages.append({**u, "tag": t})
            _attach_usage_to_record(item, merged_usages)
        items.append(item)
    return StandardResponse(data={"list": items, "total": total, "page": page, "size": size})


@router.get(
    "/tool-records/{record_id}/usages",
    summary="标签引用位置",
    dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))],
)
async def get_tool_record_usages(record_id: int):
    row = await DataToolRecord.get_or_none(id=record_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    tags = {row.tag, *(row.tags or [])}
    usages = await get_tags_usages(row.project_id, tags)
    for u in usages:
        u["resource_type_label"] = RESOURCE_TYPE_LABELS.get(u["resource_type"], u["resource_type"])
    return StandardResponse(data=usages)


@router.get("/tool-records/tags", summary="标签列表（供引用选择）", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def list_tool_tags(
    project_id: int = Query(...),
    environment_id: Optional[int] = Query(None),
):
    from app.models.sys import Environment

    qs = DataToolRecord.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(Q(environment_id=environment_id) | Q(environment_id__isnull=True))
    rows = await qs.order_by("-update_time").all()
    env_ids = {r.environment_id for r in rows if r.environment_id}
    env_map: dict[int, str] = {}
    if env_ids:
        env_rows = await Environment.filter(id__in=list(env_ids), is_del=False).all()
        env_map = {e.id: e.name for e in env_rows}
    tags = []
    seen = set()
    for row in rows:
        scope_label = "项目通用" if row.environment_id is None else env_map.get(row.environment_id, f"环境#{row.environment_id}")
        for t in [row.tag, *(row.tags or [])]:
            t = str(t).strip()
            if t and t not in seen:
                seen.add(t)
                tags.append({
                    "tag": t,
                    "ref": "${{df:" + t + "}}",
                    "tool_name": row.tool_name,
                    "output_preview": (row.output_text or format_record_output(row.output_data))[:120],
                    "environment_id": row.environment_id,
                    "scope_label": scope_label,
                })
    return StandardResponse(data=tags)


@router.post("/tool-records", summary="保存工具记录（带标签）", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def create_tool_record(body: ToolRecordCreate, username: str = Depends(get_current_username)):
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    if body.environment_id:
        env = await Environment.get_or_none(id=body.environment_id, is_del=False, project_id=body.project_id)
        if not env:
            raise HTTPException(status_code=422, detail="环境不存在")

    tag = _validate_tag(body.tag)
    await _check_tag_unique(body.project_id, body.environment_id, tag)

    extra_tags = [_validate_tag(t) for t in (body.tags or []) if str(t).strip()]
    stored_output, output_text = normalize_output_data_for_storage(
        body.output_data, body.output_text
    )

    row = await DataToolRecord.create(
        project_id=body.project_id,
        environment_id=body.environment_id,
        tool_id=body.tool_id,
        tool_name=body.tool_name,
        tool_category=body.tool_category,
        tag=tag,
        tags=extra_tags,
        input_data=body.input_data or {},
        output_data=stored_output,
        output_text=output_text,
        remark=body.remark,
        create_by=username,
        update_by=username,
    )
    env_name = ""
    if row.environment_id:
        env = await Environment.get_or_none(id=row.environment_id)
        env_name = env.name if env else ""
    return StandardResponse(data=_record_to_dict(row, env_name))


@router.put("/tool-records/{record_id}", summary="更新工具记录（备注/环境）", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def update_tool_record(record_id: int, body: ToolRecordUpdate, username: str = Depends(get_current_username)):
    row = await DataToolRecord.get_or_none(id=record_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")

    fields_set = body.model_fields_set
    if "environment_id" in fields_set:
        new_env_id = body.environment_id
        if new_env_id:
            env = await Environment.get_or_none(id=new_env_id, is_del=False, project_id=row.project_id)
            if not env:
                raise HTTPException(status_code=422, detail="环境不存在或不属于当前项目")
        await _check_tag_unique(row.project_id, new_env_id, row.tag, exclude_id=record_id)
        row.environment_id = new_env_id
    if "remark" in fields_set:
        row.remark = body.remark
    row.update_by = username
    await row.save()

    env_name = ""
    if row.environment_id:
        env = await Environment.get_or_none(id=row.environment_id)
        env_name = env.name if env else ""
    return StandardResponse(data=_record_to_dict(row, env_name))


@router.delete("/tool-records/{record_id}", summary="删除工具记录", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def delete_tool_record(record_id: int, force: bool = Query(False, description="强制删除（忽略引用检查，不推荐）")):
    row = await DataToolRecord.get_or_none(id=record_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not force:
        tags = {row.tag, *(row.tags or [])}
        usages = await get_tags_usages(row.project_id, tags)
        if usages:
            for u in usages:
                u["resource_type_label"] = RESOURCE_TYPE_LABELS.get(
                    u["resource_type"], u["resource_type"]
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"标签「{row.tag}」仍被 {len(usages)} 处引用，请先移除引用后再删除",
                    "usages": usages,
                },
            )
    row.is_del = True
    await row.save()
    return StandardResponse(message="已删除")


# ============ 工具/标签收藏 ============


async def _user_id_from_username(username: str) -> int:
    user = await User.get_or_none(username=username, is_del=False)
    if not user:
        raise HTTPException(status_code=422, detail="用户不存在")
    return user.id


@router.get("/favorites", summary="收藏列表", dependencies=[Depends(require_permissions(DATA_FACTORY_VIEW))])
async def list_favorites(project_id: int = Query(...), username: str = Depends(get_current_username)):
    user_id = await _user_id_from_username(username)
    rows = await DataToolFavorite.filter(user_id=user_id, project_id=project_id).order_by("sort_order", "id")
    return StandardResponse(
        data=[{"item_type": r.item_type, "item_key": r.item_key, "sort_order": r.sort_order} for r in rows]
    )


@router.post("/favorites", summary="添加收藏", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def add_favorite(
    project_id: int = Query(...),
    body: FavoriteItem = Body(...),
    username: str = Depends(get_current_username),
):
    user_id = await _user_id_from_username(username)
    item_type = (body.item_type or "").strip().lower()
    if item_type not in ("tool", "tag"):
        raise HTTPException(status_code=422, detail="item_type 须为 tool 或 tag")
    item_key = (body.item_key or "").strip()
    if not item_key:
        raise HTTPException(status_code=422, detail="item_key 不能为空")

    exists = await DataToolFavorite.filter(
        user_id=user_id, project_id=project_id, item_type=item_type, item_key=item_key
    ).exists()
    if not exists:
        max_order = await DataToolFavorite.filter(user_id=user_id, project_id=project_id).count()
        await DataToolFavorite.create(
            user_id=user_id,
            project_id=project_id,
            item_type=item_type,
            item_key=item_key,
            sort_order=max_order,
        )
    return StandardResponse(message="已收藏")


@router.delete("/favorites", summary="取消收藏", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def remove_favorite(
    project_id: int = Query(...),
    item_type: str = Query(...),
    item_key: str = Query(...),
    username: str = Depends(get_current_username),
):
    user_id = await _user_id_from_username(username)
    await DataToolFavorite.filter(
        user_id=user_id,
        project_id=project_id,
        item_type=item_type.strip().lower(),
        item_key=item_key.strip(),
    ).delete()
    return StandardResponse(message="已取消收藏")
