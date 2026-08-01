"""跨项目复制资产"""
from __future__ import annotations

import copy
import time
from typing import Any, Optional

from fastapi import HTTPException

from app.core.shared.catalog_utils import resolve_catalog
from app.models.http import ApiDefinition, ApiTestCase
from app.models.sys import Project
from app.models.ui import Case


def _json_clone(value: Any, default: Any):
    """深拷贝 JSON 字段，避免副本与原用例共用同一可变对象。"""
    if value is None:
        return copy.deepcopy(default)
    return copy.deepcopy(value)


async def ensure_target_project(target_project_id: int) -> Project:
    project = await Project.get_or_none(id=target_project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="目标项目不存在")
    return project


async def resolve_target_catalog(project_id: int, catalog_id: Optional[int]) -> Optional[int]:
    if catalog_id is None:
        return None
    await resolve_catalog(project_id, catalog_id)
    return catalog_id


async def copy_api_definition_to_project(
    api: ApiDefinition,
    target_project_id: int,
    target_catalog_id: Optional[int],
    username: str,
    new_name: Optional[str] = None,
) -> ApiDefinition:
    """复制接口定义到目标项目；若 method+path 已存在则复用。"""
    existing = await ApiDefinition.get_or_none(
        project_id=target_project_id,
        method=api.method,
        path=api.path,
        is_del=False,
    )
    if existing:
        return existing

    return await ApiDefinition.create(
        name=new_name or api.name,
        project_id=target_project_id,
        catalog_id=target_catalog_id,
        protocol=api.protocol,
        method=api.method,
        path=api.path,
        description=api.description,
        base_url=api.base_url,
        headers=_json_clone(api.headers, {}),
        global_header_policy=_json_clone(api.global_header_policy, {}),
        params=_json_clone(api.params, []),
        body=_json_clone(api.body, {}),
        body_type=api.body_type,
        body_fields=_json_clone(api.body_fields, []),
        ws_config=_json_clone(api.ws_config, {}),
        grpc_config=_json_clone(getattr(api, "grpc_config", None), {}),
        response_schema=_json_clone(api.response_schema, {}),
        source=api.source,
        source_id=api.source_id,
        create_by=username,
        update_by=username,
        version=1,
        version_history=[{"version": 1, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "desc": "跨项目复制"}],
    )


async def copy_ui_case_to_project(
    case: Case,
    target_project_id: int,
    target_catalog_id: Optional[int],
    username: str,
    new_name: Optional[str] = None,
) -> Case:
    return await Case.create(
        name=new_name or f"{case.name}_副本",
        project_id=target_project_id,
        steps=_json_clone(case.steps, []),
        level=case.level,
        catalog_id=target_catalog_id,
        description=case.description,
        username=username,
        update_by=username,
    )


async def copy_api_case_to_project(
    case: ApiTestCase,
    target_project_id: int,
    target_catalog_id: Optional[int],
    username: str,
    new_name: Optional[str] = None,
    copy_api_if_missing: bool = True,
) -> ApiTestCase:
    api = await case.api
    if not api:
        raise HTTPException(status_code=422, detail="用例关联的接口不存在")

    target_api_id = case.api_id
    if case.project_id != target_project_id:
        if copy_api_if_missing:
            target_api = await copy_api_definition_to_project(
                api, target_project_id, None, username
            )
            target_api_id = target_api.id
        else:
            match = await ApiDefinition.get_or_none(
                project_id=target_project_id,
                method=api.method,
                path=api.path,
                is_del=False,
            )
            if not match:
                raise HTTPException(
                    status_code=422,
                    detail="目标项目不存在同名接口，请先复制接口或开启自动复制接口",
                )
            target_api_id = match.id

    depends_on = (
        _json_clone(case.depends_on, [])
        if case.project_id == target_project_id
        else []
    )

    return await ApiTestCase.create(
        name=new_name or f"{case.name}_副本",
        api_id=target_api_id,
        project_id=target_project_id,
        catalog_id=target_catalog_id,
        request_headers=_json_clone(case.request_headers, {}),
        global_header_policy=_json_clone(case.global_header_policy, {}),
        request_params=_json_clone(case.request_params, []),
        request_body=_json_clone(case.request_body, {}),
        request_body_type=case.request_body_type or "json",
        request_body_fields=_json_clone(case.request_body_fields, []),
        ws_steps=_json_clone(case.ws_steps, []),
        assertions=_json_clone(case.assertions, []),
        assertion_groups=_json_clone(getattr(case, "assertion_groups", None), []),
        extractors=_json_clone(case.extractors, []),
        depends_on=depends_on,
        timeout=case.timeout,
        retry_count=case.retry_count,
        tags=_json_clone(case.tags, []),
        priority=case.priority,
        pre_script=getattr(case, "pre_script", None),
        post_script=getattr(case, "post_script", None),
        data_set=_json_clone(getattr(case, "data_set", None), []),
        db_assertions=_json_clone(getattr(case, "db_assertions", None), []),
        api_version_snapshot=getattr(case, "api_version_snapshot", 1),
        create_by=username,
        update_by=username,
    )
