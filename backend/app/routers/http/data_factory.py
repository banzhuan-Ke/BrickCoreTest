"""数据工厂：环境数据源 + SQL 模板 + 调试执行"""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, require_permissions, verify_internal_token
from app.core.db_factory_service import (
    datasource_to_dict,
    encrypt_datasource_password,
    evaluate_db_assertions,
    execute_sql_on_datasource,
    get_datasource_by_id,
    run_sql_templates_by_ids,
    sql_template_to_dict,
    substitute_sql,
    test_datasource_connection,
)
from app.core.permissions import DATA_FACTORY_EDIT, DATA_FACTORY_VIEW
from app.models.http import EnvDatasource, SqlTemplate
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
    username: str
    password: Optional[str] = None
    allow_write: bool = False
    max_rows: int = Field(default=100, ge=1, le=1000)
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    is_default: bool = False
    is_enabled: bool = True


class DatasourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
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


def _datasource_for_test(
    *,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
    timeout_seconds: int = 10,
) -> EnvDatasource:
    return EnvDatasource(
        host=host,
        port=port,
        database_name=database_name,
        username=username,
        password_encrypted=encrypt_datasource_password(password),
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


class SqlTemplateExecuteRequest(BaseModel):
    project_id: int
    environment_id: int
    template_id: int
    variables: dict[str, Any] = Field(default_factory=dict)


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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    qs = EnvDatasource.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
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

    password_text = (body.password or "").strip()
    if not password_text:
        raise HTTPException(status_code=422, detail="请填写数据库密码")

    if body.is_default:
        await _clear_other_defaults(body.project_id, body.environment_id)

    ds = await EnvDatasource.create(
        project_id=body.project_id,
        environment_id=body.environment_id,
        name=body.name,
        db_type=body.db_type or "mysql",
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=body.username,
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
    password_text = (body.password or "").strip()
    if not password_text:
        raise HTTPException(status_code=422, detail="请填写数据库密码")
    temp = _datasource_for_test(
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=body.username,
        password=password_text,
        timeout_seconds=body.timeout_seconds,
    )
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
    if password_override:
        temp = _datasource_for_test(
            host=ds.host,
            port=int(ds.port or 3306),
            database_name=ds.database_name,
            username=ds.username,
            password=password_override,
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
    ds = await get_datasource_by_id(body.datasource_id, body.project_id)
    if not ds or ds.environment_id != body.environment_id:
        raise HTTPException(status_code=422, detail="数据源不存在或未绑定当前环境")
    result = await execute_sql_on_datasource(
        ds, body.sql, body.variables, for_assertion=body.for_assertion
    )
    return StandardResponse(data=result)


@router.post("/sql-templates/execute", summary="调试执行 SQL 模板", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def execute_template_debug(body: SqlTemplateExecuteRequest):
    tpl = await SqlTemplate.get_or_none(id=body.template_id, project_id=body.project_id, is_del=False)
    if not tpl:
        raise HTTPException(status_code=422, detail="SQL 模板不存在")
    ds = await get_datasource_by_id(tpl.datasource_id, body.project_id)
    if not ds:
        raise HTTPException(status_code=422, detail="关联数据源不存在")
    result = await execute_sql_on_datasource(ds, tpl.sql_text, body.variables, for_assertion=False)
    result["template_id"] = tpl.id
    result["template_name"] = tpl.name
    return StandardResponse(data=result)


@router.post("/db-assertions/test", summary="调试数据库断言", dependencies=[Depends(require_permissions(DATA_FACTORY_EDIT))])
async def test_db_assertions(body: DbAssertionTestRequest):
    result = await evaluate_db_assertions(
        body.assertions, body.variables, body.environment_id, body.project_id
    )
    return StandardResponse(data=result)


@router.post(
    "/internal/ui-suite-hooks",
    summary="UI 套件执行后 SQL/库断言（Runner 内部调用）",
    dependencies=[Depends(verify_internal_token)],
)
async def run_ui_suite_db_hooks(body: UiSuiteDbHooksRequest):
    from app.models.ui import Suite, UiSuiteExecution

    suite = await Suite.get_or_none(id=body.suite_id, is_del=False)
    record = await UiSuiteExecution.get_or_none(id=body.suite_execution_id, is_del=False)
    if not suite or not record:
        raise HTTPException(status_code=404, detail="套件或执行记录不存在")

    variables = dict(body.variables or {})
    hooks_result: dict[str, Any] = {"teardown": [], "db_assertions": []}

    teardown = await run_sql_templates_by_ids(
        suite.teardown_sql_ids or [],
        variables,
        body.environment_id,
        suite.project_id,
        phase="teardown",
    )
    hooks_result["teardown"] = teardown.get("logs", [])

    db_result = await evaluate_db_assertions(
        suite.db_assertions or [],
        variables,
        body.environment_id,
        suite.project_id,
    )
    hooks_result["db_assertions"] = db_result.get("results", [])

    if not teardown.get("success") or not db_result.get("all_passed"):
        record.status = "执行完成"
        if not db_result.get("all_passed") or not teardown.get("success"):
            fail = (record.fail or 0) + 1
            record.fail = fail
        log = record.execution_log or []
        if isinstance(log, str):
            import json
            try:
                log = json.loads(log)
            except Exception:
                log = []
        log.append({"type": "db_hooks", "hooks_result": hooks_result})
        record.execution_log = log
        await record.save()

    return StandardResponse(data={"hooks_result": hooks_result, "all_passed": teardown.get("success") and db_result.get("all_passed")})
