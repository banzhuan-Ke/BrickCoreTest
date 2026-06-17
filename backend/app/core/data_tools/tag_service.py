"""数据工厂标签变量：供 API/UI 执行时 ${{df:tag}} 引用"""
from __future__ import annotations

import json
from typing import Any

from app.models.http import DataToolRecord


def format_record_output(output_data: Any, output_text: str | None = None) -> str:
    if output_text is not None and str(output_text).strip():
        return str(output_text)
    if output_data is None:
        return ""
    if isinstance(output_data, (dict, list)):
        return json.dumps(output_data, ensure_ascii=False)
    return str(output_data)


def normalize_output_data_for_storage(
    output_data: Any,
    output_text: str | None = None,
) -> tuple[dict | list, str | None]:
    """
    Tortoise JSONField 仅接受 dict/list；标量（UUID、数字、哈希等）只写入 output_text。
    """
    if isinstance(output_data, (dict, list)):
        text = output_text
        if text is None:
            text = format_record_output(output_data)
        return output_data, text
    text = output_text
    if text is None and output_data is not None:
        text = format_record_output(output_data)
    return {}, text


async def merge_df_tag_variables(project_id: int, environment_id: int | None) -> dict[str, str]:
    """
    加载项目下已保存的数据工厂标签，注入变量池。
    键名格式 df:{tag}，用法 ${{df:tag}}。
    指定环境时：先加载「项目通用」，再由「当前环境」同名标签覆盖。
    """
    if not project_id:
        return {}

    base_qs = DataToolRecord.filter(project_id=project_id, is_del=False)

    def _apply_row(result: dict[str, str], row: DataToolRecord) -> None:
        value = format_record_output(row.output_data, row.output_text)
        if row.tag:
            result[f"df:{row.tag}"] = value
        for alias in row.tags or []:
            alias = str(alias).strip()
            if alias:
                result[f"df:{alias}"] = value

    result: dict[str, str] = {}
    if environment_id:
        rows_global = await base_qs.filter(environment_id__isnull=True).order_by("update_time").all()
        rows_env = await base_qs.filter(environment_id=environment_id).order_by("update_time").all()
        for row in rows_global:
            _apply_row(result, row)
        for row in rows_env:
            _apply_row(result, row)
    else:
        rows = await base_qs.order_by("-update_time").all()
        for row in rows:
            _apply_row(result, row)
    return result


async def merge_execution_variables(
    project_id: int | None = None,
    environment_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    合并执行变量池：项目全局 < 环境全局 < 数据工厂标签 < extra。
    供 API / UI / 性能测试执行与 SQL 数据工厂 hooks 共用。
    """
    from app.models.sys import Environment, Project

    from app.core.global_vars_validate import flatten_global_vars

    merged: dict[str, Any] = {}
    if project_id:
        project = await Project.get_or_none(id=project_id, is_del=False)
        if project and project.global_vars:
            merged.update(flatten_global_vars(project.global_vars))
    if environment_id:
        env = await Environment.get_or_none(id=environment_id, is_del=False)
        if env:
            if env.global_vars:
                merged.update(flatten_global_vars(env.global_vars))
            if not project_id:
                project_id = env.project_id
    df_vars = await merge_df_tag_variables(project_id, environment_id)
    merged.update(df_vars)
    if extra:
        merged.update(extra)
    return merged
