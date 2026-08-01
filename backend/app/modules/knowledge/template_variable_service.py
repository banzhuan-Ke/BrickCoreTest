"""项目级自定义模板变量 CRUD"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.knowledge import AiKnowledgeTemplateVariable
from app.modules.knowledge.template_registry import (
    BUILTIN_TEMPLATE_VARIABLES,
    is_valid_variable_name,
)
from app.modules.knowledge.template_variable_types import CUSTOM_VALUE_TYPES, normalize_value_type


def _row_to_dict(row: AiKnowledgeTemplateVariable) -> dict[str, Any]:
    from app.modules.knowledge.template_variable_types import variable_to_dict

    return variable_to_dict(
        row.name,
        {
            "category": row.category or "custom",
            "label": row.label,
            "description": row.description or "",
            "value_type": getattr(row, "value_type", None) or "text",
            "value_schema": getattr(row, "value_schema", None),
            "default_value": row.default_value or "",
        },
        builtin=False,
        id=row.id,
        sort=row.sort,
        created_by=row.created_by,
        create_time=row.create_time.isoformat() if row.create_time else None,
    )


async def list_custom_variables(project_id: int) -> list[dict[str, Any]]:
    rows = await AiKnowledgeTemplateVariable.filter(project_id=project_id, is_del=False).order_by(
        "sort", "id"
    )
    return [_row_to_dict(r) for r in rows]


async def create_custom_variable(
    project_id: int,
    username: str,
    *,
    name: str,
    label: str,
    category: str = "custom",
    value_type: str = "text",
    value_schema: Optional[dict[str, Any]] = None,
    description: Optional[str] = None,
    default_value: Optional[str] = None,
    sort: int = 0,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not is_valid_variable_name(name):
        raise HTTPException(status_code=400, detail="变量名须为小写字母开头的 snake_case，如 my_field")
    if name in BUILTIN_TEMPLATE_VARIABLES:
        raise HTTPException(status_code=400, detail=f"变量名 {name} 与内置变量冲突")
    vt = normalize_value_type(value_type, custom=True)
    if vt not in CUSTOM_VALUE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效变量类型，可选: {', '.join(sorted(CUSTOM_VALUE_TYPES))}")
    exists = await AiKnowledgeTemplateVariable.filter(
        project_id=project_id, name=name, is_del=False
    ).exists()
    if exists:
        raise HTTPException(status_code=400, detail=f"变量 {name} 已存在")
    row = await AiKnowledgeTemplateVariable.create(
        project_id=project_id,
        name=name,
        label=label.strip() or name,
        category=(category or "custom").strip()[:32],
        value_type=vt,
        value_schema=value_schema if vt == "table" else None,
        description=description,
        default_value=default_value,
        sort=sort,
        created_by=username,
    )
    return _row_to_dict(row)


async def update_custom_variable(
    var_id: int,
    project_id: int,
    *,
    label: Optional[str] = None,
    category: Optional[str] = None,
    value_type: Optional[str] = None,
    value_schema: Optional[dict[str, Any]] = None,
    description: Optional[str] = None,
    default_value: Optional[str] = None,
    sort: Optional[int] = None,
) -> dict[str, Any]:
    row = await AiKnowledgeTemplateVariable.get_or_none(
        id=var_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="自定义变量不存在")
    if label is not None:
        row.label = label.strip() or row.label
    if category is not None:
        row.category = category.strip()[:32] or row.category
    if value_type is not None:
        vt = normalize_value_type(value_type, custom=True)
        if vt not in CUSTOM_VALUE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效变量类型，可选: {', '.join(sorted(CUSTOM_VALUE_TYPES))}")
        row.value_type = vt
        if vt != "table":
            row.value_schema = None
    if value_schema is not None and (row.value_type == "table" or value_type == "table"):
        row.value_schema = value_schema
    if description is not None:
        row.description = description
    if default_value is not None:
        row.default_value = default_value
    if sort is not None:
        row.sort = sort
    await row.save()
    return _row_to_dict(row)


async def delete_custom_variable(var_id: int, project_id: int) -> None:
    row = await AiKnowledgeTemplateVariable.get_or_none(
        id=var_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="自定义变量不存在")
    row.is_del = True
    await row.save()
