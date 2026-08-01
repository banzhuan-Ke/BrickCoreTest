"""执行 TabularQueryPlan（程序算数，不让 LLM 猜）"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from app.modules.knowledge.knowledge_qa_tabular_parse import FilterSpec, TabularQueryPlan
from app.modules.knowledge.knowledge_tabular_profiles import (
    PROFILE_ZENTAO_BUG,
    field_display_label,
    resolve_column_header,
)


def _match_row(row: dict[str, str], flt: FilterSpec) -> bool:
    val = str(row.get(flt.column) or "").strip()
    target = str(flt.value or "").strip()
    if flt.op == "eq":
        return val == target
    if flt.op == "contains":
        return target in val
    return val == target


def _filter_rows(rows: list[dict[str, Any]], filters: list[FilterSpec]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if all(_match_row(row, flt) for flt in filters):
            out.append({k: str(v) for k, v in row.items() if k != "__row_index"})
    return out


def _resolve_select_columns(plan: TabularQueryPlan, headers: list[str]) -> list[str]:
    cols: list[str] = []
    for field in plan.select_fields:
        col = resolve_column_header(plan.profile, field, headers)
        if col and col not in cols:
            cols.append(col)
    if not cols and plan.profile == PROFILE_ZENTAO_BUG:
        for field in ("bug_id", "title"):
            col = resolve_column_header(plan.profile, field, headers)
            if col:
                cols.append(col)
    return cols


def _sheet_row_meta(sheet: dict[str, Any], rows: list[Any]) -> dict[str, Any]:
    stored_rows = len(rows)
    source_rows = int(sheet.get("row_count") or stored_rows)
    stored_count = int(sheet.get("stored_row_count") or stored_rows)
    rows_truncated = bool(sheet.get("rows_truncated") or source_rows > stored_count)
    return {
        "total_rows": source_rows,
        "stored_row_count": stored_count,
        "rows_truncated": rows_truncated,
    }


def _validate_plan_columns(plan: TabularQueryPlan, headers: list[str]) -> Optional[str]:
    header_set = set(headers)
    for flt in plan.filters:
        if flt.column not in header_set:
            return f"列「{flt.column}」不存在于表格中"
    if plan.query_kind == "group_by":
        col = plan.group_by_column or ""
        if not col or col not in header_set:
            return "缺少有效的分组列"
    return None


def execute_tabular_plan(plan: TabularQueryPlan, sections_json: dict[str, Any]) -> dict[str, Any]:
    sheets = sections_json.get("sheets") or []
    sheet = next((sh for sh in sheets if sh.get("name") == plan.sheet_name), sheets[0] if sheets else {})
    headers = [str(h) for h in (sheet.get("headers") or []) if h]
    rows = sheet.get("rows") or []
    row_meta = _sheet_row_meta(sheet, rows)

    column_error = _validate_plan_columns(plan, headers)
    if column_error:
        return {"error": column_error, **row_meta}

    matched = _filter_rows(rows, plan.filters)

    if plan.query_kind == "count":
        return {
            "query_kind": "count",
            "matched_count": len(matched),
            **row_meta,
            "matched_rows": matched,
        }

    if plan.query_kind == "group_by":
        col = plan.group_by_column or plan.group_by_field or ""
        if not col:
            return {"query_kind": "group_by", "error": "missing_group_by", **row_meta}
        counter = Counter(str(r.get(col) or "未知") for r in matched)
        return {
            "query_kind": "group_by",
            "group_by_column": col,
            "group_by_result": dict(counter),
            "matched_count": len(matched),
            **row_meta,
        }

    select_cols = _resolve_select_columns(plan, headers)
    preview: list[dict[str, str]] = []
    for row in matched[:50]:
        if select_cols:
            preview.append({c: row.get(c, "") for c in select_cols})
        else:
            preview.append({k: v for k, v in row.items()})
    return {
        "query_kind": "list",
        "matched_count": len(matched),
        **row_meta,
        "matched_rows_preview": preview,
        "select_columns": select_cols,
    }


def format_tabular_answer(plan: TabularQueryPlan, result: dict[str, Any]) -> str:
    if result.get("error"):
        return "当前未能精确统计：缺少有效的分组字段。"
    flt = plan.filters[0] if plan.filters else None
    label = field_display_label(plan.profile, flt.field, flt.column) if flt else ""
    val = flt.value if flt else ""

    if plan.query_kind == "count":
        n = int(result.get("matched_count") or 0)
        if flt:
            return f"{label}为{val}的记录共 {n} 条。"
        return f"匹配记录共 {n} 条。"

    if plan.query_kind == "group_by":
        groups = result.get("group_by_result") or {}
        col = result.get("group_by_column") or label
        parts = [f"{k}: {v}" for k, v in sorted(groups.items(), key=lambda x: (-x[1], x[0]))[:20]]
        return f"按{col}分组统计（共 {result.get('matched_count', 0)} 条）：" + "；".join(parts)

    n = int(result.get("matched_count") or 0)
    cols = result.get("select_columns") or []
    if not n:
        return f"未找到{label}为{val}的记录。" if flt else "未找到匹配记录。"
    preview = result.get("matched_rows_preview") or []
    lines = []
    for i, row in enumerate(preview[:20], start=1):
        if cols:
            lines.append(f"{i}. " + "，".join(f"{c}={row.get(c, '')}" for c in cols))
        else:
            lines.append(f"{i}. " + "，".join(f"{k}={v}" for k, v in row.items()))
    suffix = f"\n（共 {n} 条，以上展示前 {min(len(preview), 20)} 条）" if n > len(preview) else ""
    head = f"{label}为{val}的记录如下：" if flt else "匹配记录如下："
    return head + "\n" + "\n".join(lines) + suffix
