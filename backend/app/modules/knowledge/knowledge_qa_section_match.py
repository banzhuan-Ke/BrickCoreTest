"""outline / section 标题与 query 词法匹配"""
from __future__ import annotations

import re
from typing import Any

from app.modules.knowledge.knowledge_qa_classify import classify_qa_question


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text or "") if t}


def score_section_match(query: str, section: dict[str, Any]) -> float:
    title = (section.get("title") or "").strip()
    if not title:
        return 0.0
    q_tokens = _tokens(query)
    t_tokens = _tokens(title)
    if not q_tokens or not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    if overlap <= 0:
        if title in query or any(t in query for t in t_tokens):
            return 0.6
        return 0.0
    return overlap / max(len(q_tokens), 1)


def pick_sections_for_query(
    query: str,
    sections: list[dict[str, Any]],
    *,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        score = score_section_match(query, sec)
        if score > 0:
            scored.append((score, sec))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [sec for _, sec in scored[:top_n]]

    classification = classify_qa_question(query)
    if classification.get("question_type") == "locate":
        chap = re.search(r"第([一二三四五六七八九十0-9]+)章", query)
        if chap:
            key = chap.group(0)
            hits = [sec for sec in sections if key in (sec.get("title") or "")]
            if hits:
                return hits[:top_n]
        return []
    return []
