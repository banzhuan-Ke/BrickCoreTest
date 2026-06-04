"""
功能用例库：实体转换、从需求工作区复制入库
"""
from typing import Any, Optional

from app.models.ai import AiFunctionalCase, AiRequirementCase


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


async def copy_requirement_cases_to_library(
    project_id: int,
    req_cases: list[AiRequirementCase],
    username: str,
    requirement_id: int,
) -> tuple[list[int], int]:
    """复制工作区用例到库，返回 (library_ids, copied_count)"""
    library_ids: list[int] = []
    for src in req_cases:
        extra_src = src.extra if isinstance(src.extra, dict) else {}
        func_module = src.module or ""
        zentao_mod = (extra_src.get("zentao_module") or "").strip()
        lib_extra: dict[str, Any] = {}
        if func_module:
            lib_extra["func_module"] = func_module
        if src.section_ids:
            lib_extra["source_section_ids"] = list(src.section_ids)
        if extra_src.get("test_point_ids"):
            lib_extra["test_point_ids"] = list(extra_src["test_point_ids"])

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

        copies = list(extra_src.get("library_copies") or [])
        copies.append(fc.id)
        extra_src["library_copies"] = copies
        src.extra = extra_src
        await src.save(update_fields=["extra"])

    return library_ids, len(library_ids)
