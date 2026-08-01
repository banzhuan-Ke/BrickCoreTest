"""TestCatalog 目录树工具"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.models.sys import TestCatalog


async def get_catalog_subtree_ids(project_id: int, catalog_id: int) -> list[int]:
    """返回目录自身及所有子孙节点 ID。"""
    root = await TestCatalog.get_or_none(id=catalog_id, project_id=project_id, is_del=False)
    if not root:
        return []

    rows = await TestCatalog.filter(project_id=project_id, is_del=False).values("id", "parent_id")
    children_map: dict[int | None, list[int]] = {}
    for row in rows:
        parent_id = row["parent_id"]
        children_map.setdefault(parent_id, []).append(row["id"])

    result: list[int] = []
    stack = [catalog_id]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(children_map.get(current, []))
    return result


async def resolve_catalog(project_id: int, catalog_id: int) -> TestCatalog:
    """校验目录存在且属于项目，否则抛出 422。"""
    catalog = await TestCatalog.get_or_none(id=catalog_id, project_id=project_id, is_del=False)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="目录不存在或已被删除",
        )
    return catalog


async def load_active_catalog_names(catalog_ids: list[int]) -> dict[int, str]:
    """批量解析目录名；已软删目录不返回，调用方展示为空即可。"""
    ids = [int(i) for i in catalog_ids if i is not None]
    if not ids:
        return {}
    rows = await TestCatalog.filter(id__in=ids, is_del=False).values("id", "name")
    return {int(row["id"]): row["name"] for row in rows}


def build_catalog_tree(flat_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将扁平目录列表构建为嵌套树（含 children）。"""
    nodes: dict[int, dict[str, Any]] = {}
    for item in flat_list:
        node = {**item, "children": []}
        nodes[item["id"]] = node

    roots: list[dict[str, Any]] = []
    for item in flat_list:
        node = nodes[item["id"]]
        parent_id = item.get("parent_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


async def apply_catalog_filter(
    query,
    project_id: int,
    catalog_id: int | None,
    include_children: bool = True,
    field: str = "catalog_id",
):
    """按目录过滤查询；include_children=True 时包含子树。"""
    if catalog_id is None:
        return query
    if include_children:
        ids = await get_catalog_subtree_ids(project_id, catalog_id)
        if not ids:
            return query.filter(**{f"{field}__in": []})
        return query.filter(**{f"{field}__in": ids})
    return query.filter(**{field: catalog_id})
