"""
功能用例库：实体转换、从需求工作区复制入库
"""
from typing import Any, Literal, Optional

from app.models.ai import AiFunctionalCase, AiRequirementCase

DuplicateTitleMode = Literal["skip", "overwrite"]


def _normalize_dup_key(text: str) -> str:
    return " ".join((text or "").strip().split())


def _library_dup_key(title: str, module: str) -> tuple[str, str]:
    return (_normalize_dup_key(title), _normalize_dup_key(module))


def format_zentao_case_id_display(case: AiFunctionalCase) -> str:
    """禅道用例编号：有值则显示，无值显示 —"""
    zid = (getattr(case, "zentao_case_id", None) or "").strip()
    if zid:
        return zid
    extra = case.extra if isinstance(case.extra, dict) else {}
    return (extra.get("zentao_case_id") or "").strip() or "—"


def functional_case_to_dict(case: AiFunctionalCase) -> dict[str, Any]:
    extra = case.extra if isinstance(case.extra, dict) else {}
    ui = extra.get("ui_import") if isinstance(extra.get("ui_import"), dict) else {}
    return {
        "id": case.id,
        "project_id": case.project_id,
        "product": case.product or "",
        "module": case.module or "",
        "related_story": case.related_story or "",
        "title": case.title,
        "zentao_case_id": getattr(case, "zentao_case_id", None) or "",
        "zentao_case_id_display": format_zentao_case_id_display(case),
        "precondition": case.precondition or "",
        "steps": case.steps or [],
        "priority": case.priority,
        "type": case.type,
        "stage": case.stage,
        "keywords": case.keywords or "",
        "status": case.status,
        "source_type": case.source_type,
        "source_requirement_id": case.source_requirement_id,
        "source_requirement_case_id": case.source_requirement_case_id,
        "source_import_batch": case.source_import_batch,
        "source_file_name": case.source_file_name,
        "extra": extra,
        "ui_import_status": ui.get("status") or "none",
        "ui_case_id": ui.get("ui_case_id"),
        "naming_template_id": case.naming_template_id,
        "naming_template_version": case.naming_template_version,
        "naming_slots": case.naming_slots or {},
        "create_by": case.create_by,
        "update_by": getattr(case, "update_by", None) or "",
        "create_time": case.create_time.strftime("%Y-%m-%d %H:%M:%S") if case.create_time else "",
        "update_time": case.update_time.strftime("%Y-%m-%d %H:%M:%S") if case.update_time else "",
    }


def _resolve_source_type(req_case: AiRequirementCase) -> str:
    extra = req_case.extra if isinstance(req_case.extra, dict) else {}
    if extra.get("test_point_ids"):
        return "test_analysis_copy"
    return "requirement_copy"


def _build_lib_extra(src: AiRequirementCase, func_module: str) -> dict[str, Any]:
    extra_src = src.extra if isinstance(src.extra, dict) else {}
    lib_extra: dict[str, Any] = {}
    if func_module:
        lib_extra["func_module"] = func_module
    if src.section_ids:
        lib_extra["source_section_ids"] = list(src.section_ids)
    if extra_src.get("test_point_ids"):
        lib_extra["test_point_ids"] = list(extra_src["test_point_ids"])
    return lib_extra


def _apply_req_case_to_library(
    fc: AiFunctionalCase,
    src: AiRequirementCase,
    *,
    requirement_id: int,
    username: str,
    lib_extra: dict[str, Any],
    zentao_mod: str,
) -> None:
    fc.product = getattr(src, "product", None) or ""
    fc.module = zentao_mod
    fc.related_story = getattr(src, "related_story", None) or ""
    fc.title = src.title
    fc.naming_template_id = getattr(src, "naming_template_id", None)
    fc.naming_template_version = getattr(src, "naming_template_version", None)
    fc.naming_slots = dict(getattr(src, "naming_slots", None) or {})
    fc.precondition = src.precondition
    fc.steps = list(src.steps or [])
    fc.priority = src.priority
    fc.type = src.type
    fc.stage = getattr(src, "stage", None) or "系统测试阶段"
    fc.keywords = src.keywords or ""
    fc.status = "confirmed"
    fc.source_type = _resolve_source_type(src)
    fc.source_requirement_id = requirement_id
    fc.source_requirement_case_id = src.id
    fc.extra = lib_extra
    fc.update_by = username


async def _sync_workspace_library_copies(src: AiRequirementCase, library_id: int) -> None:
    extra_src = src.extra if isinstance(src.extra, dict) else {}
    copies = list(extra_src.get("library_copies") or [])
    if library_id not in copies:
        copies.append(library_id)
    extra_src["library_copies"] = copies
    src.extra = extra_src
    await src.save(update_fields=["extra"])


async def copy_requirement_cases_to_library(
    project_id: int,
    req_cases: list[AiRequirementCase],
    username: str,
    requirement_id: int,
    *,
    duplicate_title_mode: DuplicateTitleMode = "skip",
) -> tuple[list[int], int, int, int]:
    """复制工作区用例到库，返回 (library_ids, copied_count, skipped_count, overwritten_count)"""
    library_ids: list[int] = []
    copied = 0
    skipped = 0
    overwritten = 0

    src_ids = [c.id for c in req_cases if c.id]
    by_source_id: dict[int, AiFunctionalCase] = {}
    if src_ids:
        for fc in await AiFunctionalCase.filter(
            project_id=project_id,
            is_del=False,
            source_requirement_case_id__in=src_ids,
        ).all():
            if fc.source_requirement_case_id is not None:
                by_source_id[int(fc.source_requirement_case_id)] = fc

    modules = set()
    for src in req_cases:
        extra_src = src.extra if isinstance(src.extra, dict) else {}
        zentao_mod = (extra_src.get("zentao_module") or "").strip()
        modules.add(zentao_mod)

    title_module_map: dict[tuple[str, str], AiFunctionalCase] = {}
    if modules:
        for fc in await AiFunctionalCase.filter(
            project_id=project_id,
            is_del=False,
            module__in=list(modules),
        ).all():
            key = _library_dup_key(fc.title, fc.module)
            prev = title_module_map.get(key)
            if prev is None or fc.id < prev.id:
                title_module_map[key] = fc

    for src in req_cases:
        extra_src = src.extra if isinstance(src.extra, dict) else {}
        func_module = src.module or ""
        zentao_mod = (extra_src.get("zentao_module") or "").strip()
        lib_extra = _build_lib_extra(src, func_module)
        dup_key = _library_dup_key(src.title, zentao_mod)

        existing = by_source_id.get(src.id)
        if existing is None:
            candidate = title_module_map.get(dup_key)
            if candidate is not None and candidate.source_requirement_case_id != src.id:
                existing = candidate

        if existing is not None:
            if duplicate_title_mode == "overwrite":
                _apply_req_case_to_library(
                    existing,
                    src,
                    requirement_id=requirement_id,
                    username=username,
                    lib_extra=lib_extra,
                    zentao_mod=zentao_mod,
                )
                await existing.save()
                by_source_id[src.id] = existing
                title_module_map[dup_key] = existing
                library_ids.append(existing.id)
                overwritten += 1
                await _sync_workspace_library_copies(src, existing.id)
            else:
                skipped += 1
            continue

        fc = await AiFunctionalCase.create(
            project_id=project_id,
            product=getattr(src, "product", None) or "",
            module=zentao_mod,
            related_story=getattr(src, "related_story", None) or "",
            title=src.title,
            naming_template_id=getattr(src, "naming_template_id", None),
            naming_template_version=getattr(src, "naming_template_version", None),
            naming_slots=dict(getattr(src, "naming_slots", None) or {}),
            precondition=src.precondition,
            steps=list(src.steps or []),
            priority=src.priority,
            type=src.type,
            stage=getattr(src, "stage", None) or "系统测试阶段",
            keywords=src.keywords or "",
            status="confirmed",
            source_type=_resolve_source_type(src),
            source_requirement_id=requirement_id,
            source_requirement_case_id=src.id,
            extra=lib_extra,
            create_by=username,
        )
        library_ids.append(fc.id)
        copied += 1
        by_source_id[src.id] = fc
        title_module_map[dup_key] = fc
        await _sync_workspace_library_copies(src, fc.id)

    return library_ids, copied, skipped, overwritten
