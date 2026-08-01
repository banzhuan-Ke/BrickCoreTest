"""资料库 v2 表格 profile 检测与 entities 预解析（聚合结果，不重复 rows）"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from app.modules.knowledge.parsers.zentao_bug import parse_zentao_bug_export

try:
    from app.modules.knowledge.packs.digitech.iteration_plan import parse_iteration_plan
except ImportError:  # CE / 未打包行业扩展时
    def parse_iteration_plan(content: bytes, file_name: str = "") -> dict[str, Any]:  # type: ignore[misc]
        return {
            "requirements": [],
            "schedule": [],
            "meta": {},
            "summary_text": "",
        }


def detect_tabular_profile(file_name: str, doc_type: Optional[str] = None) -> str:
    """根据 doc_type 与文件名启发式识别 tabular profile。"""
    name = (file_name or "").lower()
    dt = (doc_type or "").strip().lower()
    if dt == "bug_export" or "bug" in name or "缺陷" in name:
        return "zentao_bug"
    if dt == "iteration_plan" or "迭代计划" in (file_name or "") or (
        "迭代" in (file_name or "") and "计划" in (file_name or "")
    ):
        return "iteration_plan"
    return "generic_table"


def _build_zentao_bug_entities(content: bytes, file_name: str) -> dict[str, Any]:
    parsed = parse_zentao_bug_export(content, file_name)
    bugs = parsed.get("bugs") or []
    by_bug_owner = dict(Counter(b.get("bug_owner") or "未知" for b in bugs if b.get("bug_owner")))
    by_resolved_by = dict(Counter(b.get("resolved_by") or "未知" for b in bugs if b.get("resolved_by")))
    by_status = parsed.get("by_status") or {}
    by_severity = parsed.get("by_severity") or {}
    return {
        "total": parsed.get("total") or len(bugs),
        "open_count": parsed.get("open_count") or 0,
        "closed_count": parsed.get("closed_count") or 0,
        "by_bug_owner": by_bug_owner,
        "by_resolved_by": by_resolved_by,
        "by_status": by_status,
        "by_severity": by_severity,
        "headers_found": parsed.get("headers_found") or [],
    }


def _build_iteration_plan_entities(content: bytes, file_name: str) -> dict[str, Any]:
    parsed = parse_iteration_plan(content, file_name)
    requirements = parsed.get("requirements") or []
    schedule = parsed.get("schedule") or []
    by_owner = dict(Counter(r.get("owner") or "未知" for r in requirements if r.get("owner")))
    by_member = dict(
        Counter(
            m.strip()
            for row in schedule
            for m in (row.get("members") or "").replace("，", "、").split("、")
            if m.strip()
        )
    )
    return {
        "requirements_count": len(requirements),
        "schedule_count": len(schedule),
        "by_owner": by_owner,
        "by_member": by_member,
        "meta": parsed.get("meta") or {},
        "summary_text": parsed.get("summary_text") or "",
    }


def build_tabular_structured(
    profile: str,
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """构建 tabular structured 块；entities 仅存聚合统计，不重复 sheets.rows。"""
    structured: dict[str, Any] = {
        "kind": "tabular",
        "profile": profile,
        "entities": {},
    }
    if profile == "zentao_bug":
        structured["entities"] = _build_zentao_bug_entities(content, file_name)
    elif profile == "iteration_plan":
        structured["entities"] = _build_iteration_plan_entities(content, file_name)
    return structured
