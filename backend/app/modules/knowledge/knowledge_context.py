"""资料库全文上下文拼接（Phase 1 全文模式）"""
from __future__ import annotations

from typing import Any, Optional

from app.core.platform.config import KNOWLEDGE_FULLTEXT_MAX_CHARS
from app.models.knowledge import AiKnowledgeDocument, AiKnowledgeFolder
from app.modules.knowledge.knowledge_storage import load_document_source
from app.modules.knowledge.parsers.zentao_bug import parse_zentao_bug_export

# 拼接顺序：需求 → 计划 → Bug → 其他
_DOC_TYPE_ORDER = {
    "requirement": 0,
    "iteration_plan": 1,
    "test_plan": 2,
    "bug_export": 3,
    "task_export": 4,
    "summary": 5,
    "other": 9,
}


from app.modules.knowledge.knowledge_sections_read import sections_to_text as _sections_to_text


async def load_documents_for_refs(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> list[AiKnowledgeDocument]:
    docs: list[AiKnowledgeDocument] = []
    if document_ids:
        rows = await AiKnowledgeDocument.filter(
            project_id=project_id,
            id__in=document_ids,
            is_del=False,
        ).all()
        docs.extend(rows)
    if folder_ids:
        rows = await AiKnowledgeDocument.filter(
            project_id=project_id,
            folder_id__in=folder_ids,
            is_del=False,
        ).all()
        seen = {d.id for d in docs}
        for r in rows:
            if r.id not in seen:
                docs.append(r)
    docs.sort(key=lambda d: (_DOC_TYPE_ORDER.get(d.doc_type, 8), d.id))
    return docs


def _is_bug_export_candidate(doc: AiKnowledgeDocument) -> bool:
    """判断是否应尝试按 Bug 导出解析（用于统计 bug_total 等）。"""
    if doc.doc_type == "bug_export":
        return True
    fname = (doc.file_name or "").lower()
    title = (doc.title or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".csv")):
        return False
    hints = ("bug", "缺陷", "zentao", "禅道")
    return any(h in fname or h in title for h in hints)


async def build_knowledge_context(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    max_chars: Optional[int] = None,
) -> dict[str, Any]:
    """构建全文 knowledge_context 与 Bug 解析摘要。"""
    limit = max_chars or KNOWLEDGE_FULLTEXT_MAX_CHARS
    docs = await load_documents_for_refs(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )

    parts: list[str] = []
    bug_doc_ids: set[int] = set()
    bug_docs: list[AiKnowledgeDocument] = []
    total_chars = 0
    raw_total_chars = 0
    refs: list[dict[str, Any]] = []

    def _track_bug_doc(doc: AiKnowledgeDocument) -> None:
        if doc.id not in bug_doc_ids and _is_bug_export_candidate(doc):
            bug_doc_ids.add(doc.id)
            bug_docs.append(doc)

    for doc in docs:
        label = f"《{doc.title}》({doc.doc_type})"
        text = _sections_to_text(doc.sections_json)
        if not text and doc.storage:
            try:
                from app.modules.knowledge.knowledge_ingest import parse_document_content

                raw = load_document_source(doc.storage, doc.file_name)
                _track_bug_doc(doc)
                parsed = parse_document_content(raw, doc.file_name, doc_type=doc.doc_type)
                text = _sections_to_text(parsed.get("sections_json"))
            except Exception:
                text = ""
        else:
            _track_bug_doc(doc)
        chunk = f"--- {label} ---\n{text}".strip()
        if not chunk or chunk == f"--- {label} ---":
            continue
        raw_total_chars += len(chunk)
        if total_chars + len(chunk) > limit:
            remain = limit - total_chars
            if remain > 200:
                parts.append(chunk[:remain] + "\n…（已截断）")
                total_chars = limit
            break
        parts.append(chunk)
        total_chars += len(chunk)
        refs.append({"document_id": doc.id, "title": doc.title, "doc_type": doc.doc_type})

    bug_summary_parts: list[str] = []
    bug_total = 0
    merged_severity: dict[str, int] = {}
    merged_status: dict[str, int] = {}
    merged_resolution: dict[str, int] = {}
    merged_opened_by: dict[str, int] = {}
    merged_assigned_to: dict[str, int] = {}
    merged_resolved_by: dict[str, int] = {}
    merged_priority: dict[str, int] = {}
    merged_module: dict[str, int] = {}
    bug_open_count = 0
    bug_closed_count = 0
    all_bugs: list[dict[str, str]] = []

    def _merge_counter(dst: dict[str, int], src: dict[str, int]) -> None:
        for k, v in src.items():
            dst[k] = dst.get(k, 0) + v

    for doc in bug_docs:
        try:
            raw = load_document_source(doc.storage or {}, doc.file_name)
            parsed = parse_zentao_bug_export(raw, doc.file_name)
            bug_total += parsed.get("total") or 0
            bug_open_count += parsed.get("open_count") or 0
            bug_closed_count += parsed.get("closed_count") or 0
            _merge_counter(merged_severity, parsed.get("by_severity") or {})
            _merge_counter(merged_status, parsed.get("by_status") or {})
            _merge_counter(merged_resolution, parsed.get("by_resolution") or {})
            _merge_counter(merged_opened_by, parsed.get("by_opened_by") or {})
            _merge_counter(merged_assigned_to, parsed.get("by_assigned_to") or {})
            _merge_counter(merged_resolved_by, parsed.get("by_resolved_by") or {})
            _merge_counter(merged_priority, parsed.get("by_priority") or {})
            _merge_counter(merged_module, parsed.get("by_module") or {})
            for b in parsed.get("bugs") or []:
                if len(all_bugs) < 500:
                    all_bugs.append(b)
            bug_summary_parts.append(f"{doc.title}：{parsed.get('summary_text', '')}")
        except Exception:
            continue

    return {
        "knowledge_context": "\n\n".join(parts),
        "knowledge_summary": "\n\n".join(parts)[:8000],
        "bug_export_summary": "\n".join(bug_summary_parts),
        "bug_total": bug_total,
        "bug_open_count": bug_open_count,
        "bug_closed_count": bug_closed_count,
        "bug_by_severity": merged_severity,
        "bug_by_status": merged_status,
        "bug_by_resolution": merged_resolution,
        "bug_by_opened_by": merged_opened_by,
        "bug_by_assigned_to": merged_assigned_to,
        "bug_by_resolved_by": merged_resolved_by,
        "bug_by_priority": merged_priority,
        "bug_by_module": merged_module,
        "bugs": all_bugs,
        "refs": refs,
        "truncated": total_chars >= limit or raw_total_chars > limit,
        "raw_total_chars": raw_total_chars,
    }


async def append_knowledge_context_to_prompt(
    user_prompt: str,
    project_id: int,
    *,
    knowledge_folder_ids: Optional[list[int]] = None,
    knowledge_document_ids: Optional[list[int]] = None,
    scene: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """将资料库上下文追加到 Prompt 末尾，返回 (prompt, knowledge_meta)。"""
    from app.modules.knowledge.knowledge_refs_resolve import resolve_knowledge_refs_for_scene

    folder_ids, document_ids = knowledge_folder_ids, knowledge_document_ids
    if scene:
        folder_ids, document_ids = await resolve_knowledge_refs_for_scene(
            project_id,
            scene,
            folder_ids=knowledge_folder_ids,
            document_ids=knowledge_document_ids,
        )
    if not folder_ids and not document_ids:
        return user_prompt, {"refs": [], "resolved_folder_ids": [], "resolved_document_ids": []}
    kctx = await build_knowledge_context(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    ktext = (kctx.get("knowledge_context") or "").strip()
    if ktext:
        user_prompt += (
            "\n\n## 迭代测试资料库参考\n"
            "以下材料来自项目资料库，分析失败原因时可参考历史缺陷、测试范围与相关说明；"
            "仍须以当前失败步骤、日志与截图为准。\n\n"
            f"{ktext}"
        )
    if kctx.get("bug_export_summary"):
        user_prompt += f"\n\n## Bug 导出摘要\n{kctx['bug_export_summary']}"
    meta = {
        "refs": kctx.get("refs") or [],
        "resolved_folder_ids": folder_ids or [],
        "resolved_document_ids": document_ids or [],
        "strategy_hint": kctx.get("strategy_hint"),
    }
    return user_prompt, meta


async def estimate_knowledge_refs(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """估算资料引用规模与检索策略。"""
    from app.modules.knowledge.knowledge_context_mapreduce import should_mapreduce_knowledge
    from app.modules.knowledge.knowledge_project_settings import resolve_knowledge_settings

    settings = await resolve_knowledge_settings(project_id)
    limit = int(settings.get("fulltext_max_chars") or KNOWLEDGE_FULLTEXT_MAX_CHARS)
    docs = await load_documents_for_refs(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    ctx = await build_knowledge_context(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    raw = int(ctx.get("raw_total_chars") or 0)
    effective = len(ctx.get("knowledge_context") or "")
    truncated = bool(ctx.get("truncated"))
    if should_mapreduce_knowledge(ctx, settings):
        strategy = "mapreduce"
        strategy_label = "将使用智能检索（Map-Reduce）"
    elif truncated or raw > limit:
        strategy = "rag"
        strategy_label = "将使用智能检索"
    else:
        strategy = "fulltext"
        strategy_label = "将使用全文引用"
    from app.modules.knowledge.knowledge_bug_hints import summarize_bug_modules

    bug_hints = await summarize_bug_modules(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    folder_names: dict[int, str] = {}
    folder_ids_in_docs = {d.folder_id for d in docs if d.folder_id}
    if folder_ids_in_docs:
        rows = await AiKnowledgeFolder.filter(id__in=list(folder_ids_in_docs), is_del=False).all()
        folder_names = {f.id: f.name for f in rows}
    return {
        "doc_count": len(docs),
        "raw_total_chars": raw,
        "effective_chars": effective,
        "truncated": truncated,
        "strategy_hint": strategy,
        "strategy_label": strategy_label,
        "threshold": limit,
        "bug_hints": bug_hints,
        "refs": [
            {
                "id": d.id,
                "title": d.title,
                "doc_type": d.doc_type,
                "char_count": d.char_count or 0,
                "folder_id": d.folder_id,
                "folder_name": folder_names.get(d.folder_id) if d.folder_id else None,
            }
            for d in docs
        ],
    }
