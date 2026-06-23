"""UI 测试文件引用扫描与 legacy files_path 迁移扫描"""
from __future__ import annotations

import os
import re
from typing import Any, Iterator

from app.models.ui import Case, Suite, UiStepFragment

UPLOAD_FILE_METHOD = "upload_file"
_LEGACY_FILES_PATH_RE = re.compile(r"\$\{\{?\s*files_path\s*\}?\}|files_path", re.IGNORECASE)


def iter_steps(steps: list | None) -> Iterator[dict[str, Any]]:
    """递归遍历步骤树（含条件分支子步骤）。"""
    if not steps:
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        if step.get("method") == "condition_branch":
            for branch in step.get("branches") or []:
                if isinstance(branch, dict):
                    yield from iter_steps(branch.get("steps"))


def _step_params(step: dict[str, Any]) -> dict[str, Any]:
    params = step.get("params")
    return params if isinstance(params, dict) else {}


def step_references_file_key(step: dict[str, Any], file_key: str) -> bool:
    if step.get("method") != UPLOAD_FILE_METHOD:
        return False
    params = _step_params(step)
    mode = (params.get("upload_mode") or "single").strip().lower()
    if mode == "folder":
        return False
    if mode == "multiple":
        for item in params.get("file_items") or []:
            if isinstance(item, dict) and item.get("file_key") == file_key:
                return True
        return False
    return bool(params.get("file_key")) and params.get("file_key") == file_key


def step_is_legacy_files_path(step: dict[str, Any]) -> bool:
    """upload_file 步骤使用 files_path 本地路径且未绑定 MinIO file_key。"""
    if step.get("method") != UPLOAD_FILE_METHOD:
        return False
    params = _step_params(step)
    mode = (params.get("upload_mode") or "single").strip().lower()
    if mode in ("folder", "multiple"):
        return False
    if params.get("file_key"):
        return False
    file_path = (params.get("file_path") or params.get("path") or params.get("file") or "").strip()
    if not file_path:
        return False
    return bool(_LEGACY_FILES_PATH_RE.search(file_path))


def extract_filename_from_legacy_path(file_path: str) -> str:
    normalized = file_path.replace("\\", "/")
    if "${" in normalized:
        parts = normalized.split("/")
        name = parts[-1] if parts else normalized
        return name.strip() or normalized
    return os.path.basename(normalized) or file_path


def empty_reference_summary() -> dict[str, Any]:
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


async def build_file_reference_map(project_id: int) -> dict[str, dict[str, Any]]:
    """一次扫描项目内步骤，按 file_key 聚合引用（供列表页批量展示）。"""
    ref_map: dict[str, dict[str, Any]] = {}

    def bucket_for(file_key: str) -> dict[str, Any]:
        if file_key not in ref_map:
            ref_map[file_key] = {
                "cases": [],
                "suites": [],
                "fragments": [],
            }
        return ref_map[file_key]

    def register_step_refs(step: dict[str, Any], *, target: str, meta: dict[str, Any]) -> bool:
        """若步骤引用了 MinIO 文件则写入 ref_map，返回是否已处理。"""
        params = _step_params(step)
        mode = (params.get("upload_mode") or "single").strip().lower()
        if step.get("method") != UPLOAD_FILE_METHOD or mode == "folder":
            return False
        keys: list[str] = []
        if mode == "multiple":
            for item in params.get("file_items") or []:
                if isinstance(item, dict) and item.get("file_key"):
                    keys.append(item["file_key"])
        elif params.get("file_key"):
            keys.append(params["file_key"])
        if not keys:
            return False
        for fk in keys:
            bucket_for(fk)[target].append(meta)
        return True

    async for case in Case.filter(project_id=project_id, is_del=False):
        for step in iter_steps(case.steps):
            if register_step_refs(
                step,
                target="cases",
                meta={"id": case.id, "name": case.name, "step_id": step.get("id")},
            ):
                break

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        for step in iter_steps(suite.pre_actions):
            if register_step_refs(
                step,
                target="suites",
                meta={"id": suite.id, "name": suite.name, "location": "pre_actions"},
            ):
                break

    async for fragment in UiStepFragment.filter(project_id=project_id, is_del=False):
        for step in iter_steps(fragment.steps):
            if register_step_refs(
                step,
                target="fragments",
                meta={"id": fragment.id, "name": fragment.name, "step_id": step.get("id")},
            ):
                break

    for file_key, bucket in ref_map.items():
        ref_map[file_key] = _finalize_reference_bucket(bucket)
    return ref_map


async def collect_file_references(project_id: int, file_key: str) -> dict[str, Any]:
    """统计项目内引用指定 file_key 的用例、套件、片段。"""
    cases: list[dict[str, Any]] = []
    suites: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []

    async for case in Case.filter(project_id=project_id, is_del=False):
        for step in iter_steps(case.steps):
            if step_references_file_key(step, file_key):
                cases.append({"id": case.id, "name": case.name, "step_id": step.get("id")})
                break

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        for step in iter_steps(suite.pre_actions):
            if step_references_file_key(step, file_key):
                suites.append({"id": suite.id, "name": suite.name, "location": "pre_actions"})
                break

    async for fragment in UiStepFragment.filter(project_id=project_id, is_del=False):
        for step in iter_steps(fragment.steps):
            if step_references_file_key(step, file_key):
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


async def scan_legacy_upload_steps(project_id: int) -> dict[str, Any]:
    """扫描仍使用 Runner 本地 files_path 的 upload_file 步骤。"""
    items: list[dict[str, Any]] = []

    async def _scan_steps(steps: list | None, *, source_type: str, source_id: int, source_name: str, location: str = "steps"):
        for step in iter_steps(steps):
            if not step_is_legacy_files_path(step):
                continue
            params = _step_params(step)
            file_path = (params.get("file_path") or params.get("path") or "").strip()
            items.append({
                "source_type": source_type,
                "source_id": source_id,
                "source_name": source_name,
                "location": location,
                "step_id": step.get("id"),
                "step_desc": step.get("desc") or "",
                "file_path": file_path,
                "suggested_filename": extract_filename_from_legacy_path(file_path),
            })

    async for case in Case.filter(project_id=project_id, is_del=False):
        await _scan_steps(case.steps, source_type="case", source_id=case.id, source_name=case.name)

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        await _scan_steps(
            suite.pre_actions,
            source_type="suite",
            source_id=suite.id,
            source_name=suite.name,
            location="pre_actions",
        )

    async for fragment in UiStepFragment.filter(project_id=project_id, is_del=False):
        await _scan_steps(
            fragment.steps,
            source_type="fragment",
            source_id=fragment.id,
            source_name=fragment.name,
        )

    filenames = sorted({item["suggested_filename"] for item in items if item.get("suggested_filename")})
    return {
        "total": len(items),
        "unique_filenames": filenames,
        "items": items,
    }
