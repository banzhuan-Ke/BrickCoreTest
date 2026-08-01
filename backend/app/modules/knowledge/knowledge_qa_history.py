"""资料库问答历史记录"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.knowledge import AiKnowledgeQaRecord


def _record_to_list_item(row: AiKnowledgeQaRecord) -> dict[str, Any]:
    payload = getattr(row, "result_json", None)
    payload = payload if isinstance(payload, dict) else {}
    return {
        "id": row.id,
        "mode": row.mode,
        "query": row.query,
        "answer_preview": (row.answer or "")[:160],
        "strategy": row.strategy,
        "answer_path": payload.get("answer_path") or row.strategy,
        "hit_count": row.hit_count,
        "doc_count": row.doc_count,
        "tokens_used": row.tokens_used,
        "duration_ms": row.duration_ms,
        "username": row.username,
        "folder_ids": row.folder_ids if isinstance(row.folder_ids, list) else [],
        "create_time": row.create_time.isoformat() if row.create_time else None,
    }


def _record_to_detail(row: AiKnowledgeQaRecord) -> dict[str, Any]:
    payload = row.result_json if isinstance(row.result_json, dict) else {}
    return {
        **_record_to_list_item(row),
        "answer": row.answer,
        "top_k": row.top_k,
        "document_ids": row.document_ids if isinstance(row.document_ids, list) else [],
        "sources": row.sources_json if isinstance(row.sources_json, list) else [],
        "result": payload,
    }


async def save_qa_record(
    project_id: int,
    username: str,
    *,
    mode: str,
    query: str,
    result: dict[str, Any],
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
) -> int:
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    row = await AiKnowledgeQaRecord.create(
        project_id=project_id,
        username=username or "",
        mode=mode,
        query=query[:500],
        answer=(result.get("answer") or None),
        strategy=str(result.get("strategy") or "none"),
        folder_ids=folder_ids or [],
        document_ids=document_ids or [],
        top_k=top_k,
        hit_count=int(result.get("hit_count") or 0),
        doc_count=int(result.get("doc_count") or 0),
        tokens_used=int(usage.get("total_tokens") or 0),
        duration_ms=int(usage.get("duration_ms") or 0),
        sources_json=result.get("sources") or [],
        result_json=result,
    )
    return row.id


async def list_qa_records(
    project_id: int,
    *,
    username: str,
    page: int = 1,
    size: int = 20,
    mode: Optional[str] = None,
) -> dict[str, Any]:
    qs = AiKnowledgeQaRecord.filter(
        project_id=project_id,
        username=username or "",
        is_del=False,
    )
    if mode:
        qs = qs.filter(mode=mode)
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_record_to_list_item(r) for r in rows],
    }


async def get_qa_record(record_id: int, project_id: int, *, username: str) -> dict[str, Any]:
    row = await AiKnowledgeQaRecord.get_or_none(
        id=record_id,
        project_id=project_id,
        username=username or "",
        is_del=False,
    )
    if not row:
        raise HTTPException(status_code=404, detail="问答记录不存在")
    return _record_to_detail(row)


async def delete_qa_record(record_id: int, project_id: int, *, username: str) -> None:
    row = await AiKnowledgeQaRecord.get_or_none(
        id=record_id,
        project_id=project_id,
        username=username or "",
        is_del=False,
    )
    if not row:
        raise HTTPException(status_code=404, detail="问答记录不存在")
    row.is_del = True
    await row.save()


async def batch_delete_qa_records(
    project_id: int,
    *,
    username: str,
    record_ids: list[int],
) -> dict[str, int]:
    ids = [int(i) for i in record_ids if i]
    if not ids:
        return {"deleted_count": 0}
    updated = await AiKnowledgeQaRecord.filter(
        project_id=project_id,
        username=username or "",
        id__in=ids,
        is_del=False,
    ).update(is_del=True)
    return {"deleted_count": updated}
