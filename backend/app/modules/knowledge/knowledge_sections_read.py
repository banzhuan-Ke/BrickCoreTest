"""sections_json v1/v2 统一读取（消费层 Phase 2）"""
from __future__ import annotations

from typing import Any, Optional

from app.modules.knowledge.constants import SECTIONS_JSON_VERSION_V2


def sections_json_version(sections_json: Any) -> int:
    if not isinstance(sections_json, dict):
        return 0
    try:
        return int(sections_json.get("version") or 1)
    except (TypeError, ValueError):
        return 1


def is_sections_json_v2(sections_json: Any) -> bool:
    return sections_json_version(sections_json) >= SECTIONS_JSON_VERSION_V2


def get_parse_warnings(sections_json: Any) -> list[str]:
    if not isinstance(sections_json, dict):
        return []
    warnings = sections_json.get("parse_warnings")
    if isinstance(warnings, list):
        return [str(w) for w in warnings if w]
    return []


def get_prose_outline(sections_json: Any) -> list[dict[str, Any]]:
    if not isinstance(sections_json, dict):
        return []
    structured = sections_json.get("structured")
    if isinstance(structured, dict) and isinstance(structured.get("outline"), list):
        return [item for item in structured["outline"] if isinstance(item, dict)]
    return []


def get_structured_meta(sections_json: Any) -> dict[str, Any]:
    """提取 version / kind / profile 等轻量元信息，供 API 返回。"""
    if not isinstance(sections_json, dict):
        return {
            "sections_version": 1,
            "parse_warnings": [],
            "outline": [],
            "structured_kind": None,
            "structured_profile": None,
            "image_parse": {},
        }
    structured = sections_json.get("structured") if isinstance(sections_json.get("structured"), dict) else {}
    image_parse = {}
    meta = sections_json.get("_meta")
    if isinstance(meta, dict) and isinstance(meta.get("image_parse"), dict):
        image_parse = meta["image_parse"]
    return {
        "sections_version": sections_json_version(sections_json),
        "parse_warnings": get_parse_warnings(sections_json),
        "outline": get_prose_outline(sections_json),
        "structured_kind": structured.get("kind"),
        "structured_profile": structured.get("profile"),
        "image_parse": image_parse,
    }


def iter_tabular_sheets(sections_json: dict[str, Any]) -> list[dict[str, Any]]:
    fmt = sections_json.get("format") or ""
    sheets = sections_json.get("sheets")
    if fmt in ("xlsx", "xls", "csv") and isinstance(sheets, list):
        return [sh for sh in sheets if isinstance(sh, dict)]
    if fmt == "csv" and isinstance(sections_json.get("preview_rows"), list):
        return [
            {
                "name": "CSV",
                "preview_rows": sections_json["preview_rows"],
                "row_count": len(sections_json["preview_rows"]),
            }
        ]
    return []


def _row_dict_to_cells(row: dict[str, Any], headers: list[str]) -> list[str]:
    if headers:
        return [str(row.get(h) or "") for h in headers]
    return [str(v) for k, v in row.items() if k != "__row_index"]


def sheet_display_rows(
    sheet: dict[str, Any],
    *,
    max_rows: int = 30,
) -> tuple[list[list[str]], int]:
    """将 sheet 转为 UI 可展示的二维表；返回 (rows, total_rows)。"""
    headers = [str(h) for h in (sheet.get("headers") or []) if h]
    raw_rows = sheet.get("rows")
    if isinstance(raw_rows, list) and raw_rows and isinstance(raw_rows[0], dict):
        if not headers:
            keys = [k for k in raw_rows[0].keys() if k != "__row_index"]
            headers = keys
        display: list[list[str]] = []
        if headers:
            display.append(headers)
        for row in raw_rows[:max_rows]:
            if isinstance(row, dict):
                display.append(_row_dict_to_cells(row, headers))
        total = int(sheet.get("row_count") or len(raw_rows))
        stored = int(sheet.get("stored_row_count") or len(raw_rows))
        return display, total if total >= stored else stored

    preview_rows = sheet.get("preview_rows") or []
    matrix = [list(r) for r in preview_rows[:max_rows]]
    total = int(sheet.get("row_count") or len(preview_rows))
    return matrix, total


def tabular_sections_to_text(
    sections_json: dict[str, Any],
    *,
    max_sheets: int = 5,
    max_rows_per_sheet: Optional[int] = 20,
) -> str:
    parts: list[str] = []
    for sh in iter_tabular_sheets(sections_json)[:max_sheets]:
        name = sh.get("name") or "Sheet"
        headers = [str(h) for h in (sh.get("headers") or []) if h]
        raw_rows = sh.get("rows")
        lines: list[str] = []

        if isinstance(raw_rows, list) and raw_rows and isinstance(raw_rows[0], dict):
            if headers:
                lines.append(" | ".join(headers))
            limit = len(raw_rows) if max_rows_per_sheet is None else max_rows_per_sheet
            for row in raw_rows[:limit]:
                if isinstance(row, dict):
                    lines.append(" | ".join(_row_dict_to_cells(row, headers)))
            source_total = int(sh.get("row_count") or len(raw_rows))
            stored_total = int(sh.get("stored_row_count") or len(raw_rows))
            if sh.get("rows_truncated") or source_total > stored_total:
                lines.append(
                    f"…（源数据 {source_total} 行，已入库 {stored_total} 行"
                    + (f"，预览 {min(limit, stored_total)} 行）" if max_rows_per_sheet is not None else "）")
                )
            elif max_rows_per_sheet is not None and stored_total > max_rows_per_sheet:
                lines.append(f"…（共 {stored_total} 行，预览 {max_rows_per_sheet} 行）")
        else:
            preview_rows = sh.get("preview_rows") or []
            limit = len(preview_rows) if max_rows_per_sheet is None else max_rows_per_sheet
            for row in preview_rows[:limit]:
                lines.append(" | ".join(str(c) for c in row))
            if max_rows_per_sheet is not None and len(preview_rows) > max_rows_per_sheet:
                lines.append(f"…（共 {len(preview_rows)} 行，预览 {max_rows_per_sheet} 行）")

        if lines:
            parts.append(f"[{name}]\n" + "\n".join(lines))
    return "\n\n".join(parts)


def prose_sections_to_text(
    sections: list[Any],
    *,
    max_sections: Optional[int] = 80,
) -> str:
    parts: list[str] = []
    items = sections if max_sections is None else sections[:max_sections]
    for sec in items:
        if not isinstance(sec, dict):
            continue
        title = (sec.get("title") or "").strip()
        body = (sec.get("content") or sec.get("text") or "").strip()
        if title:
            parts.append(f"## {title}\n{body}")
        elif body:
            parts.append(body)
    return "\n\n".join(parts)


def sections_to_text(
    sections_json: Any,
    *,
    max_sheets: int = 5,
    max_rows_per_sheet: Optional[int] = 20,
    max_sections: Optional[int] = 80,
) -> str:
    """v2 优先、v1 兼容的 sections_json → 扁平文本。"""
    if not isinstance(sections_json, dict):
        return ""

    if is_sections_json_v2(sections_json):
        fulltext = (sections_json.get("fulltext") or "").strip()
        structured = sections_json.get("structured") if isinstance(sections_json.get("structured"), dict) else {}
        if fulltext and structured.get("kind") == "prose":
            return fulltext
        fmt = sections_json.get("format") or ""
        if fmt in ("xlsx", "xls", "csv") or iter_tabular_sheets(sections_json):
            return tabular_sections_to_text(
                sections_json,
                max_sheets=max_sheets,
                max_rows_per_sheet=max_rows_per_sheet,
            )
        sections = sections_json.get("sections") or []
        if fulltext:
            return fulltext
        return prose_sections_to_text(sections, max_sections=max_sections)

    fmt = sections_json.get("format") or ""
    if fmt in ("xlsx", "xls", "csv"):
        return tabular_sections_to_text(
            sections_json,
            max_sheets=max_sheets,
            max_rows_per_sheet=max_rows_per_sheet,
        )
    return prose_sections_to_text(sections_json.get("sections") or [], max_sections=max_sections)


def extract_fulltext_from_sections_json(sections_json: Any) -> str:
    """从 sections_json 提取尽量完整的正文（v2 优先读库内全量，避免重读文件）。"""
    if not isinstance(sections_json, dict):
        return ""

    if is_sections_json_v2(sections_json):
        fulltext = (sections_json.get("fulltext") or "").strip()
        structured = sections_json.get("structured") if isinstance(sections_json.get("structured"), dict) else {}
        kind = structured.get("kind")
        if kind == "prose":
            if fulltext:
                return fulltext
            return prose_sections_to_text(sections_json.get("sections") or [], max_sections=None)
        if kind == "tabular" or iter_tabular_sheets(sections_json):
            text = tabular_sections_to_text(sections_json, max_sheets=50, max_rows_per_sheet=None)
            if text:
                return text
        if fulltext:
            return fulltext

    return sections_to_text(sections_json, max_sheets=10, max_rows_per_sheet=None, max_sections=None)
