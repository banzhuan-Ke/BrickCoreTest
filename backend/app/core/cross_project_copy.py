"""跨项目复制资产"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import HTTPException

from app.core.catalog_utils import resolve_catalog
from app.models.http import ApiDefinition, ApiTestCase
from app.models.sys import Project
from app.models.ui import Case


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
        headers=api.headers,
        global_header_policy=api.global_header_policy,
        params=api.params,
        body=api.body,
        body_type=api.body_type,
        body_fields=api.body_fields,
        ws_config=api.ws_config,
        response_schema=api.response_schema,
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
        steps=case.steps,
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

    depends_on = case.depends_on if case.project_id == target_project_id else []

    return await ApiTestCase.create(
        name=new_name or f"{case.name}_副本",
        api_id=target_api_id,
        project_id=target_project_id,
        catalog_id=target_catalog_id,
        request_headers=case.request_headers,
        global_header_policy=case.global_header_policy,
        request_params=case.request_params,
        request_body=case.request_body,
        request_body_type=case.request_body_type,
        request_body_fields=case.request_body_fields,
        ws_steps=case.ws_steps,
        assertions=case.assertions,
        assertion_groups=getattr(case, "assertion_groups", None) or [],
        extractors=case.extractors,
        depends_on=depends_on,
        timeout=case.timeout,
        retry_count=case.retry_count,
        tags=case.tags,
        priority=case.priority,
        pre_script=getattr(case, "pre_script", None),
        post_script=getattr(case, "post_script", None),
        data_set=getattr(case, "data_set", None) or [],
        db_assertions=getattr(case, "db_assertions", None) or [],
        api_version_snapshot=getattr(case, "api_version_snapshot", 1),
        create_by=username,
        update_by=username,
    )
