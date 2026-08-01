"""资料库问答 — retrieve / smart 双模式 + v2 旁路"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from fastapi import HTTPException

from app.core.llm.ai_usage_log import log_ai_usage
from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings
from app.modules.knowledge.knowledge_qa_prose import try_prose_enhanced_qa
from app.modules.knowledge.knowledge_qa_tabular import try_tabular_qa
from app.modules.knowledge.knowledge_retrieve import retrieve_knowledge

QA_MODES = {"retrieve", "smart"}

_OPEN_THINK = "<" + "think>"
_CLOSE_THINK = "</" + "think>"
_OPEN_REDACTED = "<" + "redacted_reasoning>"
_CLOSE_REDACTED = "</" + "redacted_reasoning>"

_REASONING_BLOCK_RE = re.compile(
    rf"(?:{_OPEN_THINK}[\s\S]*?{_CLOSE_THINK}|{_OPEN_REDACTED}[\s\S]*?{_CLOSE_REDACTED})",
    re.IGNORECASE,
)
_UNCLOSED_REASONING_RE = re.compile(
    rf"^(?:{_OPEN_THINK}|{_OPEN_REDACTED})[\s\S]*?(?:{_CLOSE_THINK}|{_CLOSE_REDACTED})\s*",
    re.IGNORECASE,
)
_ONLY_REASONING_RE = re.compile(
    rf"^(?:{_OPEN_THINK}|{_OPEN_REDACTED})[\s\S]*$",
    re.IGNORECASE,
)


def clean_qa_answer(text: str) -> str:
    """移除模型思考过程标签，仅保留面向用户的回答正文。"""
    s = (text or "").strip()
    if not s:
        return ""
    prev = None
    while prev != s:
        prev = s
        s = _REASONING_BLOCK_RE.sub("", s).strip()
    s = _UNCLOSED_REASONING_RE.sub("", s).strip()
    if _ONLY_REASONING_RE.match(s):
        return ""
    return s


def normalize_qa_mode(mode: Any) -> str:
    key = str(mode or "retrieve").strip().lower()
    if key in QA_MODES:
        return key
    return "retrieve"


def _synthesize_retrieve_chunks_from_context(
    context_text: str,
    *,
    prose_basis: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """prose 旁路仅有 context_text 时，为检索模式合成可展示的分块。"""
    ctx = (context_text or "").strip()
    if not ctx:
        return []

    prose_basis = prose_basis or {}
    doc_ids = list(prose_basis.get("document_ids") or [])
    sections_used = list(prose_basis.get("sections_used") or [])
    default_doc_id = int(doc_ids[0]) if doc_ids else 0

    if re.search(r"^## ", ctx, re.MULTILINE):
        body = ctx
        if ctx.startswith("---"):
            first_nl = ctx.find("\n")
            body = ctx[first_nl + 1 :].strip() if first_nl > 0 else ctx
        parts = re.split(r"(?=^## )", body, flags=re.MULTILINE)
        chunks: list[dict[str, Any]] = []
        idx = 0
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.startswith("## "):
                nl = part.find("\n")
                sec_title = part[3:nl].strip() if nl > 0 else part[3:].strip()
                text = part
                matched = next(
                    (
                        s
                        for s in sections_used
                        if sec_title in (s.get("title") or "") or (s.get("title") or "") in sec_title
                    ),
                    None,
                )
                doc_id = int(matched.get("document_id") or default_doc_id) if matched else default_doc_id
                title = (matched.get("title") if matched else None) or sec_title
            else:
                text = part
                sec = sections_used[idx] if idx < len(sections_used) else {}
                doc_id = int(sec.get("document_id") or default_doc_id)
                title = sec.get("title") or "正文"
            chunks.append(
                {
                    "document_id": doc_id,
                    "title": title or "章节",
                    "chunk_index": idx,
                    "text": text,
                    "score": None,
                }
            )
            idx += 1
        if chunks:
            return chunks

    doc_blocks = re.split(r"(?=--- 《)", ctx)
    doc_blocks = [b.strip() for b in doc_blocks if b.strip()]
    if len(doc_blocks) > 1 or (doc_blocks and doc_blocks[0].startswith("--- 《")):
        chunks = []
        for i, block in enumerate(doc_blocks):
            m = re.match(r"--- 《([^》]+)》", block)
            title = m.group(1) if m else (
                sections_used[i].get("title") if i < len(sections_used) else f"文档{i + 1}"
            )
            doc_id = int(doc_ids[i] if i < len(doc_ids) else default_doc_id)
            nl = block.find("\n")
            text = block[nl + 1 :].strip() if nl > 0 else block
            chunks.append(
                {
                    "document_id": doc_id,
                    "title": title,
                    "chunk_index": i,
                    "text": text or block,
                    "score": None,
                }
            )
        return chunks

    title = sections_used[0].get("title") if sections_used else (
        f"文档#{default_doc_id}" if default_doc_id else "检索内容"
    )
    return [
        {
            "document_id": default_doc_id,
            "title": title,
            "chunk_index": 0,
            "text": ctx,
            "score": None,
        }
    ]


def chunks_to_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for row in chunks:
        doc_id = int(row.get("document_id") or 0)
        chunk_index = int(row.get("chunk_index") or 0)
        key = (doc_id, chunk_index)
        if key in seen:
            continue
        seen.add(key)
        text = str(row.get("text") or "")
        sources.append(
            {
                "document_id": doc_id,
                "title": row.get("title") or f"文档#{doc_id}",
                "chunk_index": chunk_index,
                "score": row.get("score"),
                "text_preview": text[:240] + ("…" if len(text) > 240 else ""),
            }
        )
    return sources


def _merge_qa_base(
    qa_mode: str,
    query: str,
    payload: dict[str, Any],
    *,
    max_chars: int,
) -> dict[str, Any]:
    chunks = payload.get("chunks") or []
    if qa_mode == "retrieve" and not chunks and (payload.get("context_text") or "").strip():
        chunks = _synthesize_retrieve_chunks_from_context(
            payload.get("context_text") or "",
            prose_basis=payload.get("prose_basis"),
        )
    sources = chunks_to_sources(chunks) if chunks else []
    context_truncated = bool(payload.get("context_truncated") or payload.get("truncated"))
    context_chunk_count = int(payload.get("context_chunk_count") or len(chunks))
    hit_count = int(payload.get("hit_count") or 0)
    if qa_mode == "retrieve" and chunks and hit_count < len(chunks):
        hit_count = len(chunks)
    base = {
        "mode": qa_mode,
        "query": query,
        "strategy": payload.get("strategy") or "none",
        "answer_path": payload.get("answer_path") or payload.get("strategy") or "rag",
        "doc_count": int(payload.get("doc_count") or 0),
        "hit_count": hit_count,
        "chunks": chunks,
        "sources": sources,
        "context_text": payload.get("context_text") or "",
        "context_truncated": context_truncated,
        "context_chunk_count": context_chunk_count,
        "message": payload.get("message"),
        "tabular_basis": payload.get("tabular_basis"),
        "prose_basis": payload.get("prose_basis"),
        "matched_rows_preview": payload.get("matched_rows_preview"),
        "group_by_result": payload.get("group_by_result"),
        "tabular_fallback": payload.get("tabular_fallback"),
        "tabular_fallback_reason": payload.get("tabular_fallback_reason"),
        "question_type": payload.get("question_type"),
    }
    if payload.get("answer"):
        base["answer"] = payload["answer"]
    if context_truncated and qa_mode == "smart" and not base.get("message"):
        base["message"] = (
            f"检索到 {base['hit_count']} 条引用，但合并上下文仅纳入前 {context_chunk_count} 条"
            f"（已达 {max_chars} 字符上限）。回答可能不完整。"
        )
    if payload.get("tabular_fallback") and payload.get("tabular_fallback_reason"):
        if payload.get("answer_path") == "tabular_fallback":
            base["message"] = payload.get("message")
        else:
            base["message"] = f"表格精确统计未命中：{payload['tabular_fallback_reason']}。已回退 RAG。"
    return base


def _tabular_stat_failure_answer(reason: str) -> str:
    detail = (reason or "未知原因").strip()
    return (
        f"无法对该问题给出精确表格统计：{detail}。"
        "请指定 1 份 Excel/CSV、确认已 reparse 为 v2，并核对列名与过滤条件；"
        "也可改用检索模式查看原文片段，避免把模型推断当作精确数字。"
    )


def _build_tabular_fallback_result(
    qa_mode: str,
    query: str,
    *,
    reason: str,
    question_type: str,
) -> dict[str, Any]:
    payload = {
        "strategy": "none",
        "answer_path": "tabular_fallback",
        "tabular_fallback": True,
        "tabular_fallback_reason": reason,
        "question_type": question_type,
        "doc_count": 0,
        "hit_count": 0,
        "context_text": "",
        "message": _tabular_stat_failure_answer(reason),
    }
    if qa_mode == "smart":
        payload["answer"] = payload["message"]
    base = _merge_qa_base(qa_mode, query, payload, max_chars=0)
    base["usage"] = None
    return base


async def _generate_smart_answer(
    project_id: int,
    *,
    query: str,
    context_text: str,
    base: dict[str, Any],
    max_chars: int,
    ai_config_id: Optional[int],
    username: str,
) -> dict[str, Any]:
    from app.modules.ai.ai_prompts import PromptManager
    from app.modules.ai.ai_scene_config import get_scene_llm_overrides
    from app.routers.ai.generate import _call_llm, _get_ai_config

    if not (context_text or "").strip():
        return {
            **base,
            "answer": "未在资料库中找到相关内容，请尝试更换关键词、扩大文件夹范围，或确认文档已建立词法索引。",
            "usage": None,
        }

    settings = await load_knowledge_project_settings(project_id)
    cfg_id = ai_config_id or settings.get("knowledge_qa_ai_config_id")
    config = await _get_ai_config(cfg_id, scene="knowledge_qa")
    scene_overrides = await get_scene_llm_overrides("knowledge_qa")

    ctx = {
        "query": query,
        "context_text": context_text[:max_chars],
        "source_count": len(base.get("sources") or []),
        "strategy": base.get("strategy"),
    }
    llm_context = ctx["context_text"]
    if len(context_text) > max_chars:
        base = {**base, "context_truncated": True}
        if qa_mode == "smart" and not base.get("message"):
            base["message"] = (
                f"上下文已达 {max_chars} 字符上限，模型仅看到前 {len(llm_context)} 字符，回答可能不完整。"
            )
    system_prompt, user_prompt = await PromptManager.render("knowledge_qa", ctx)
    t0 = time.time()
    resp = await _call_llm(
        system_prompt,
        user_prompt,
        config,
        min_timeout=120,
        max_retries=1,
        param_overrides=scene_overrides or None,
        disable_thinking=True,
    )
    answer = clean_qa_answer(str(resp.get("content") or ""))
    if not answer:
        answer = "未能生成有效回答，请稍后重试或改用检索模式查看原文片段。"

    duration_ms = int((time.time() - t0) * 1000)
    tokens = int(resp.get("tokens") or 0)
    await log_ai_usage(
        config,
        "knowledge_qa",
        username=username,
        project_id=project_id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        input_summary=f"qa smart query={query[:80]} sources={len(base.get('sources') or [])}",
        output_summary=f"answer_len={len(answer)}",
    )
    return {
        **base,
        "answer": answer,
        "context_text": llm_context,
        "usage": {
            "total_tokens": tokens,
            "prompt_tokens": resp.get("prompt_tokens"),
            "completion_tokens": resp.get("completion_tokens"),
            "duration_ms": duration_ms,
        },
    }


async def ask_knowledge(
    project_id: int,
    *,
    mode: str,
    query: str,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
    max_chars: int = 32000,
    strategy: Optional[str] = None,
    ai_config_id: Optional[int] = None,
    username: str = "",
) -> dict[str, Any]:
    """资料问答：try_tabular_qa → try_prose_enhanced_qa → retrieve_knowledge。"""
    qa_mode = normalize_qa_mode(mode)
    q = (query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")

    tabular = await try_tabular_qa(
        project_id,
        query=q,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    if tabular and tabular.get("answer") and not tabular.get("tabular_fallback"):
        base = _merge_qa_base(qa_mode, q, tabular, max_chars=max_chars)
        if qa_mode == "retrieve":
            return base
        return base

    tabular_qtype = (tabular or {}).get("question_type")
    if tabular and tabular.get("tabular_fallback") and tabular_qtype in ("stat", "coverage"):
        return _build_tabular_fallback_result(
            qa_mode,
            q,
            reason=str(tabular.get("tabular_fallback_reason") or "表格精确统计未命中"),
            question_type=tabular_qtype,
        )

    prose = await try_prose_enhanced_qa(
        project_id,
        query=q,
        folder_ids=folder_ids,
        document_ids=document_ids,
        top_k=top_k,
        max_chars=max_chars,
        strategy=strategy,
    )
    if prose and (prose.get("context_text") or prose.get("chunks")):
        base = _merge_qa_base(qa_mode, q, prose, max_chars=max_chars)
        if qa_mode == "retrieve":
            return base
        return await _generate_smart_answer(
            project_id,
            query=q,
            context_text=base.get("context_text") or "",
            base=base,
            max_chars=max_chars,
            ai_config_id=ai_config_id,
            username=username,
        )

    retrieval = await retrieve_knowledge(
        project_id,
        query=q,
        folder_ids=folder_ids,
        document_ids=document_ids,
        top_k=top_k,
        max_chars=max_chars,
        strategy=strategy,
    )
    retrieval["answer_path"] = retrieval.get("strategy") or "rag"
    base = _merge_qa_base(qa_mode, q, retrieval, max_chars=max_chars)
    if qa_mode == "retrieve":
        return base
    return await _generate_smart_answer(
        project_id,
        query=q,
        context_text=base.get("context_text") or "",
        base=base,
        max_chars=max_chars,
        ai_config_id=ai_config_id,
        username=username,
    )
