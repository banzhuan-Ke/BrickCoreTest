"""tabular 文档行级 RAG 分块"""
from __future__ import annotations

from typing import Any


def _format_row_line(headers: list[str], row: dict[str, Any]) -> str:
    parts: list[str] = []
    for h in headers:
        if not h:
            continue
        val = str(row.get(h) or "").strip()
        if val:
            parts.append(f"{h}: {val}")
    if not parts:
        for k, v in row.items():
            if k == "__row_index":
                continue
            val = str(v or "").strip()
            if val:
                parts.append(f"{k}: {val}")
    return " | ".join(parts)


def build_tabular_chunk_specs(
    sheets: list[dict[str, Any]],
    *,
    rows_per_chunk: int = 5,
) -> list[dict[str, Any]]:
    """每 1～5 行一块，块头重复表头上下文。"""
    specs: list[dict[str, Any]] = []
    rows_per_chunk = max(1, min(int(rows_per_chunk or 5), 10))

    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        sheet_name = (sheet.get("name") or "Sheet").strip()
        headers = [str(h) for h in (sheet.get("headers") or []) if h]
        raw_rows = sheet.get("rows") or []
        if not isinstance(raw_rows, list) or not raw_rows:
            continue

        header_line = " | ".join(headers) if headers else ""
        batch: list[dict[str, Any]] = []
        batch_indexes: list[int] = []

        def _flush_batch() -> None:
            if not batch:
                return
            lines = [f"[{sheet_name}]"]
            if header_line:
                lines.append(header_line)
            for row in batch:
                if isinstance(row, dict):
                    lines.append(_format_row_line(headers, row))
            text = "\n".join(lines).strip()
            if text:
                specs.append(
                    {
                        "text": text,
                        "section_title": sheet_name[:200],
                        "meta": {
                            "sheet_name": sheet_name,
                            "row_indexes": list(batch_indexes),
                        },
                    }
                )
            batch.clear()
            batch_indexes.clear()

        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            batch.append(row)
            idx = row.get("__row_index")
            if idx is not None:
                batch_indexes.append(int(idx))
            if len(batch) >= rows_per_chunk:
                _flush_batch()
        _flush_batch()

    return specs
