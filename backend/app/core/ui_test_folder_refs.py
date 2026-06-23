"""UI 测试文件夹资源引用扫描"""
from __future__ import annotations

from typing import Any

from app.core.ui_test_file_refs import iter_steps
from app.models.ui import Case, Suite, UiStepFragment

UPLOAD_FILE_METHOD = "upload_file"


def _step_params(step: dict[str, Any]) -> dict[str, Any]:
    params = step.get("params")
    return params if isinstance(params, dict) else {}


def step_references_folder_key(step: dict[str, Any], folder_key: str) -> bool:
    if step.get("method") != UPLOAD_FILE_METHOD:
        return False
    params = _step_params(step)
    mode = (params.get("upload_mode") or "single").strip().lower()
    return mode == "folder" and bool(params.get("folder_key")) and params.get("folder_key") == folder_key


def empty_folder_reference_summary() -> dict[str, Any]:
    return {
        "case_count": 0,
        "suite_count": 0,
        "fragment_count": 0,
        "total": 0,
        "cases": [],
        "suites": [],
        "fragments": [],
    }


def _finalize_reference_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["case_count"] = len(bucket["cases"])
    bucket["suite_count"] = len(bucket["suites"])
    bucket["fragment_count"] = len(bucket["fragments"])
    bucket["total"] = bucket["case_count"] + bucket["suite_count"] + bucket["fragment_count"]
    return bucket


async def build_folder_reference_map(project_id: int) -> dict[str, dict[str, Any]]:
    ref_map: dict[str, dict[str, Any]] = {}

    def bucket_for(folder_key: str) -> dict[str, Any]:
        if folder_key not in ref_map:
            ref_map[folder_key] = {"cases": [], "suites": [], "fragments": []}
        return ref_map[folder_key]

    async for case in Case.filter(project_id=project_id, is_del=False):
        for step in iter_steps(case.steps):
            params = _step_params(step)
            folder_key = params.get("folder_key")
            mode = (params.get("upload_mode") or "single").strip().lower()
            if step.get("method") == UPLOAD_FILE_METHOD and mode == "folder" and folder_key:
                bucket_for(folder_key)["cases"].append({
                    "id": case.id,
                    "name": case.name,
                    "step_id": step.get("id"),
                })
                break

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        for step in iter_steps(suite.pre_actions):
            params = _step_params(step)
            folder_key = params.get("folder_key")
            mode = (params.get("upload_mode") or "single").strip().lower()
            if step.get("method") == UPLOAD_FILE_METHOD and mode == "folder" and folder_key:
                bucket_for(folder_key)["suites"].append({
                    "id": suite.id,
                    "name": suite.name,
                    "location": "pre_actions",
                })
                break

    async for fragment in UiStepFragment.filter(project_id=project_id, is_del=False):
        for step in iter_steps(fragment.steps):
            params = _step_params(step)
            folder_key = params.get("folder_key")
            mode = (params.get("upload_mode") or "single").strip().lower()
            if step.get("method") == UPLOAD_FILE_METHOD and mode == "folder" and folder_key:
                bucket_for(folder_key)["fragments"].append({
                    "id": fragment.id,
                    "name": fragment.name,
                    "step_id": step.get("id"),
                })
                break

    for folder_key, bucket in ref_map.items():
        ref_map[folder_key] = _finalize_reference_bucket(bucket)
    return ref_map


async def collect_folder_references(project_id: int, folder_key: str) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    suites: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []

    async for case in Case.filter(project_id=project_id, is_del=False):
        for step in iter_steps(case.steps):
            if step_references_folder_key(step, folder_key):
                cases.append({"id": case.id, "name": case.name, "step_id": step.get("id")})
                break

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        for step in iter_steps(suite.pre_actions):
            if step_references_folder_key(step, folder_key):
                suites.append({"id": suite.id, "name": suite.name, "location": "pre_actions"})
                break

    async for fragment in UiStepFragment.filter(project_id=project_id, is_del=False):
        for step in iter_steps(fragment.steps):
            if step_references_folder_key(step, folder_key):
                fragments.append({"id": fragment.id, "name": fragment.name, "step_id": step.get("id")})
                break

    return {
        "case_count": len(cases),
        "suite_count": len(suites),
        "fragment_count": len(fragments),
        "total": len(cases) + len(suites) + len(fragments),
        "cases": cases[:50],
        "suites": suites[:50],
        "fragments": fragments[:50],
    }
