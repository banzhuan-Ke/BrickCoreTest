"""资料库 Bug 导出模块分布提示（生成用例时参考）"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from app.modules.knowledge.knowledge_context import load_documents_for_refs
from app.modules.knowledge.parsers.zentao_bug import parse_zentao_bug_export
from app.modules.knowledge.knowledge_storage import load_document_source


def _is_bug_export(doc) -> bool:
    dt = (doc.doc_type or "").strip()
    if dt == "bug_export":
        return True
    name = (doc.file_name or doc.title or "").lower()
    return "bug" in name and name.endswith((".xlsx", ".xls", ".csv"))


async def summarize_bug_modules(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_n: int = 8,
) -> dict[str, Any]:
    """汇总所选资料中 Bug 导出按模块分布，供生成用例提示。"""
    docs = await load_documents_for_refs(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    bug_docs = [d for d in docs if _is_bug_export(d)]
    module_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    total_bugs = 0
    open_count = 0

    for doc in bug_docs:
        try:
            raw = load_document_source(doc.storage or {}, doc.file_name)
            parsed = parse_zentao_bug_export(raw, doc.file_name or "bug.xlsx")
        except Exception:
            continue
        total_bugs += int(parsed.get("total") or 0)
        open_count += int(parsed.get("open_count") or 0)
        for mod, cnt in (parsed.get("by_module") or {}).items():
            module_counter[str(mod or "(未分类)")] += int(cnt)
        for sev, cnt in (parsed.get("by_severity") or {}).items():
            severity_counter[str(sev)] += int(cnt)

    top_modules = [
        {"module": name, "count": count}
        for name, count in module_counter.most_common(top_n)
    ]
    hint_lines: list[str] = []
    if top_modules:
        parts = [f"{m['module']}({m['count']})" for m in top_modules[:5]]
        hint_lines.append(f"历史 Bug 高发模块：{'、'.join(parts)}")
        hint_lines.append("建议在生成用例时对上述模块增加回归与边界场景覆盖。")

    return {
        "bug_doc_count": len(bug_docs),
        "bug_total": total_bugs,
        "bug_open_count": open_count,
        "top_modules": top_modules,
        "by_severity": dict(severity_counter.most_common(6)),
        "hint_text": "\n".join(hint_lines),
        "has_hints": bool(top_modules),
    }
