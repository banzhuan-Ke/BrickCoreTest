"""接口测试文件引用扫描（form-data file 字段中的 file_key）"""
from __future__ import annotations

from typing import Any

from app.models.http import ApiDefinition, ApiTestCase


def _field_references_file_key(field: dict[str, Any], file_key: str) -> bool:
    if field.get("field_type") != "file":
        return False
    return bool(field.get("file_key")) and field.get("file_key") == file_key


def _scan_body_fields(fields: list | None, file_key: str) -> bool:
    if not fields:
        return False
    for field in fields:
        if isinstance(field, dict) and _field_references_file_key(field, file_key):
            return True
    return False


def empty_reference_summary() -> dict[str, Any]:
    return {
        "api_count": 0,
        "case_count": 0,
        "total": 0,
        "apis": [],
        "cases": [],
    }


def _finalize_reference_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["api_count"] = len(bucket["apis"])
    bucket["case_count"] = len(bucket["cases"])
    bucket["total"] = bucket["api_count"] + bucket["case_count"]
    return bucket


async def build_file_reference_map(project_id: int) -> dict[str, dict[str, Any]]:
    """一次扫描项目内 form-data 字段，按 file_key 聚合引用。"""
    ref_map: dict[str, dict[str, Any]] = {}

    def bucket_for(file_key: str) -> dict[str, Any]:
        if file_key not in ref_map:
            ref_map[file_key] = {"apis": [], "cases": []}
        return ref_map[file_key]

    async for api in ApiDefinition.filter(project_id=project_id, is_del=False):
        for field in api.body_fields or []:
            if not isinstance(field, dict) or field.get("field_type") != "file":
                continue
            file_key = field.get("file_key")
            if file_key:
                bucket_for(file_key)["apis"].append({"id": api.id, "name": api.name})
                break

    async for case in ApiTestCase.filter(project_id=project_id, is_del=False):
        for field in case.request_body_fields or []:
            if not isinstance(field, dict) or field.get("field_type") != "file":
                continue
            file_key = field.get("file_key")
            if file_key:
                bucket_for(file_key)["cases"].append({"id": case.id, "name": case.name, "api_id": case.api_id})
                break

    for file_key, bucket in ref_map.items():
        ref_map[file_key] = _finalize_reference_bucket(bucket)
    return ref_map


async def collect_file_references(project_id: int, file_key: str) -> dict[str, Any]:
    """统计项目内引用指定 file_key 的接口定义与用例。"""
    apis: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    async for api in ApiDefinition.filter(project_id=project_id, is_del=False):
        if _scan_body_fields(api.body_fields, file_key):
            apis.append({"id": api.id, "name": api.name})

    async for case in ApiTestCase.filter(project_id=project_id, is_del=False):
        if _scan_body_fields(case.request_body_fields, file_key):
            cases.append({"id": case.id, "name": case.name, "api_id": case.api_id})

    return {
        "api_count": len(apis),
        "case_count": len(cases),
        "total": len(apis) + len(cases),
        "apis": apis[:50],
        "cases": cases[:50],
    }
