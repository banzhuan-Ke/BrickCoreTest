"""NL → TabularQueryPlan（规则解析，第一期保守）"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.modules.knowledge.knowledge_qa_classify import classify_qa_question
from app.modules.knowledge.knowledge_tabular_profiles import (
    PROFILE_GENERIC_TABLE,
    PROFILE_ITERATION_PLAN,
    PROFILE_ZENTAO_BUG,
    resolve_column_header,
    resolve_field_for_profile,
)

_POSSESSIVE_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9_]{1,15})(?:的\s*(?:bug|缺陷|任务|需求|单子|编号|标题))"
)
_ASSIGN_RE = re.compile(
    r"(?:"
    r"(?:bug归属人|归属人|解决者|处理人|指派给|负责人|参与人|测试人员)"
    r"(?:为|是|等于|[:：])"
    r")\s*"
    r"([\u4e00-\u9fffA-Za-z0-9_]{1,10})"
    r"(?=[的\s，,。；;？?！!]|$)"
)
_SKIP_VALUES = frozenset({"列出", "查询", "统计", "显示", "查看"})
_VERB_PREFIX_RE = re.compile(r"^(列出|查询|统计|显示|查看)")
_FIELD_HINT_RE = re.compile(
    r"(bug归属人|归属人|解决者|处理人|指派给|负责人|参与人|测试人员|严重程度|优先级|编号|标题|需求|任务)"
)
_LIST_FIELDS_RE = re.compile(r"(编号和标题|编号、标题|编号及标题|编号\s*[,，、]\s*标题)")


@dataclass
class FilterSpec:
    field: str
    column: str
    op: str
    value: str


@dataclass
class TabularQueryPlan:
    query_kind: str
    profile: str
    sheet_name: Optional[str] = None
    filters: list[FilterSpec] = field(default_factory=list)
    select_fields: list[str] = field(default_factory=list)
    group_by_field: Optional[str] = None
    group_by_column: Optional[str] = None


def _detect_profile(doc: Any) -> str:
    sj = doc.sections_json if isinstance(getattr(doc, "sections_json", None), dict) else {}
    structured = sj.get("structured") if isinstance(sj.get("structured"), dict) else {}
    profile = structured.get("profile")
    if profile:
        return str(profile)
    dt = (getattr(doc, "doc_type", None) or "").lower()
    fname = (getattr(doc, "file_name", None) or "").lower()
    if dt == "bug_export" or "bug" in fname or "缺陷" in fname:
        return PROFILE_ZENTAO_BUG
    if dt == "iteration_plan" or "迭代计划" in (getattr(doc, "file_name", None) or ""):
        return PROFILE_ITERATION_PLAN
    return PROFILE_GENERIC_TABLE


def _pick_sheet(sheets: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    if not sheets:
        return {}
    if profile == PROFILE_ZENTAO_BUG:
        for sh in sheets:
            if (sh.get("name") or "").lower() == "bug":
                return sh
    return sheets[0]


def _extract_value(query: str) -> Optional[str]:
    q = query or ""
    m = _ASSIGN_RE.search(q)
    if m:
        val = (m.group(1) or "").strip()
        if val and val not in _SKIP_VALUES:
            return val[:80]

    candidates: list[tuple[str, int]] = []
    for m in _POSSESSIVE_RE.finditer(q):
        val = (m.group(1) or "").strip()
        val = _VERB_PREFIX_RE.sub("", val).strip()
        if not val or val in _SKIP_VALUES:
            continue
        if any(ch in val for ch in ("为", "是", "等于")):
            continue
        candidates.append((val, m.start()))
    if candidates:
        # 同一问句多个候选时，优先更靠后的（通常更贴近实体名词）
        candidates.sort(key=lambda x: x[1])
        return candidates[-1][0][:80]
    return None


def _extract_field_hint(query: str) -> Optional[str]:
    m = _FIELD_HINT_RE.search(query)
    return m.group(1) if m else None


def parse_tabular_query(query: str, doc: Any) -> Optional[TabularQueryPlan]:
    q = (query or "").strip()
    if not q:
        return None

    classification = classify_qa_question(q)
    qtype = classification.get("question_type")
    if qtype not in ("stat", "coverage", "mixed"):
        return None

    profile = _detect_profile(doc)
    sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    sheets = sj.get("sheets") or []
    sheet = _pick_sheet(sheets, profile)
    headers = [str(h) for h in (sheet.get("headers") or []) if h]
    if not headers and not (sheet.get("rows") or []):
        return None

    kind_hint = classification.get("query_kind_hint")
    if _LIST_FIELDS_RE.search(q) or qtype == "coverage":
        query_kind = "list"
    elif kind_hint == "group_by" or "按" in q:
        query_kind = "group_by"
    else:
        query_kind = "count"

    field_hint = _extract_field_hint(q) or ""
    if query_kind == "list" and _LIST_FIELDS_RE.search(q) and field_hint in ("编号", "标题"):
        field_hint = ""
    if not field_hint:
        if "归属" in q:
            field_hint = "归属人"
        elif "解决" in q or "处理" in q:
            field_hint = "解决者"
        elif "参与" in q or "测试人员" in q:
            field_hint = "参与人"

    std_field = resolve_field_for_profile(profile, field_hint) if field_hint else None
    if not std_field and profile == PROFILE_ZENTAO_BUG:
        if _POSSESSIVE_RE.search(q) and ("bug" in q.lower() or "缺陷" in q or "单子" in q):
            std_field = "bug_owner"
            if not field_hint:
                field_hint = "归属人"
        elif ("bug" in q.lower() or "缺陷" in q) and "归属" in q:
            std_field = "bug_owner"

    value = _extract_value(q)
    if query_kind == "list" and value and profile == PROFILE_ZENTAO_BUG and not field_hint:
        field_hint = "归属人"
        std_field = resolve_field_for_profile(profile, field_hint)
    filters: list[FilterSpec] = []
    if std_field and value:
        column = resolve_column_header(profile, std_field, headers, spoken=field_hint)
        if column and column in headers:
            filters.append(FilterSpec(field=std_field, column=column, op="eq", value=value))

    if query_kind in ("count", "list", "group_by") and not filters and query_kind != "group_by":
        return None

    select_fields: list[str] = []
    if query_kind == "list":
        if profile == PROFILE_ZENTAO_BUG:
            select_fields = ["bug_id", "title"]
        elif _LIST_FIELDS_RE.search(q):
            select_fields = ["bug_id", "title"]

    group_field = None
    group_column = None
    if query_kind == "group_by":
        gm = re.search(r"按(.{1,12}?)(?:统计|分组|分布)", q)
        spoken = (gm.group(1) if gm else field_hint) or ""
        group_field = resolve_field_for_profile(profile, spoken) or std_field
        if group_field:
            group_column = resolve_column_header(profile, group_field, headers, spoken=spoken)
        if not group_column or group_column not in headers:
            return None

    return TabularQueryPlan(
        query_kind=query_kind,
        profile=profile,
        sheet_name=sheet.get("name"),
        filters=filters,
        select_fields=select_fields,
        group_by_field=group_field,
        group_by_column=group_column,
    )
