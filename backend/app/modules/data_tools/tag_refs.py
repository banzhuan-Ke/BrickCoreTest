"""数据工厂标签 ${{df:tag}} 引用扫描"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.models.http import ApiDefinition, ApiTestCase, ApiTestSuite, SqlTemplate
from app.models.ui import Case, Suite

# 与 data_factory._TAG_PATTERN 一致
DF_REF_RE = re.compile(r"\$\{\{df:([\w\u4e00-\u9fa5-]{1,64})\}\}")


def extract_df_tags_from_text(text: str) -> set[str]:
    return set(DF_REF_RE.findall(text or ""))


def extract_df_tags_from_value(value: Any) -> set[str]:
    found: set[str] = set()
    if value is None:
        return found
    if isinstance(value, str):
        found.update(extract_df_tags_from_text(value))
    elif isinstance(value, dict):
        for v in value.values():
            found.update(extract_df_tags_from_value(v))
    elif isinstance(value, list):
        for item in value:
            found.update(extract_df_tags_from_value(item))
    return found


def _add_refs(
    index: dict[str, list[dict[str, Any]]],
    tag: str,
    *,
    resource_type: str,
    resource_id: int,
    resource_name: str,
    location: str,
) -> None:
    index[tag].append({
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "location": location,
    })


def _scan_fields(
    index: dict[str, list[dict[str, Any]]],
    obj: Any,
    fields: list[tuple[str, str]],
    *,
    resource_type: str,
    resource_id: int,
    resource_name: str,
) -> None:
    for attr, location in fields:
        value = getattr(obj, attr, None)
        if value is None:
            continue
        for tag in extract_df_tags_from_value(value):
            _add_refs(
                index,
                tag,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                location=location,
            )


async def build_project_df_tag_usage_index(project_id: int) -> dict[str, list[dict[str, Any]]]:
    """扫描项目内可能引用 ${{df:tag}} 的配置，返回 tag -> 引用列表。"""
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)

    api_case_fields = [
        ("request_headers", "请求头"),
        ("request_params", "请求参数"),
        ("request_body", "请求体"),
        ("request_body_fields", "Form 字段"),
        ("ws_steps", "WS 步骤"),
        ("assertions", "断言"),
        ("assertion_groups", "条件断言"),
        ("extractors", "变量提取"),
        ("db_assertions", "库断言"),
        ("data_set", "数据集"),
        ("pre_script", "前置脚本"),
        ("post_script", "后置脚本"),
    ]
    cases = await ApiTestCase.filter(project_id=project_id, is_del=False).all()
    for case in cases:
        _scan_fields(
            index,
            case,
            api_case_fields,
            resource_type="api_case",
            resource_id=case.id,
            resource_name=case.name,
        )

    api_def_fields = [
        ("headers", "请求头"),
        ("params", "查询参数"),
        ("body", "请求体"),
        ("body_fields", "Form 字段"),
        ("ws_config", "WS 配置"),
    ]
    apis = await ApiDefinition.filter(project_id=project_id, is_del=False).all()
    for api in apis:
        _scan_fields(
            index,
            api,
            api_def_fields,
            resource_type="api_definition",
            resource_id=api.id,
            resource_name=api.name,
        )

    ui_cases = await Case.filter(project_id=project_id, is_del=False).all()
    for ui_case in ui_cases:
        _scan_fields(
            index,
            ui_case,
            [("steps", "执行步骤")],
            resource_type="ui_case",
            resource_id=ui_case.id,
            resource_name=ui_case.name,
        )

    ui_suites = await Suite.filter(project_id=project_id, is_del=False).all()
    for suite in ui_suites:
        _scan_fields(
            index,
            suite,
            [("pre_actions", "前置步骤"), ("db_assertions", "库断言")],
            resource_type="ui_suite",
            resource_id=suite.id,
            resource_name=suite.name,
        )

    api_suites = await ApiTestSuite.filter(project_id=project_id, is_del=False).all()
    for suite in api_suites:
        _scan_fields(
            index,
            suite,
            [("db_assertions", "库断言")],
            resource_type="api_suite",
            resource_id=suite.id,
            resource_name=suite.name,
        )

    sql_templates = await SqlTemplate.filter(project_id=project_id, is_del=False).all()
    for tpl in sql_templates:
        _scan_fields(
            index,
            tpl,
            [("sql_text", "SQL"), ("description", "描述")],
            resource_type="sql_template",
            resource_id=tpl.id,
            resource_name=tpl.name,
        )

    return dict(index)


async def get_tags_usages(project_id: int, tags: set[str]) -> list[dict[str, Any]]:
    if not tags:
        return []
    index = await build_project_df_tag_usage_index(project_id)
    seen: set[tuple[str, int, str]] = set()
    result: list[dict[str, Any]] = []
    for tag in tags:
        for ref in index.get(tag, []):
            key = (ref["resource_type"], ref["resource_id"], ref["location"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(ref)
            item["tag"] = tag
            result.append(item)
    return result


RESOURCE_TYPE_LABELS = {
    "api_case": "接口用例",
    "api_definition": "接口定义",
    "ui_case": "Web 用例",
    "ui_suite": "Web 套件",
    "api_suite": "接口套件",
    "sql_template": "SQL 模板",
}
