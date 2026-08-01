"""资料库问答 — 问题类型分类"""
from __future__ import annotations

import re
from typing import Any

_STAT_RE = re.compile(r"(有多少|多少个|多少条|数量|统计|计数|共.*几|几个|总数)")
_COVERAGE_RE = re.compile(r"(列出|列举|有哪些|全部|所有|清单|编号和|编号及)")
_LOCATE_RE = re.compile(r"(哪一?章|哪一节|在哪.*节|讲了什么|说了什么|主要内容|章节|第.章)")
_GROUP_RE = re.compile(r"(按.*统计|按.*分组|分组|分布|各.*多少)")
_MIXED_RE = re.compile(r"(高优先级|严重|P[0-3]|的.*有哪些|的.*多少)")


def classify_qa_question(query: str) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"question_type": "semantic", "confidence": 0.0}

    if _GROUP_RE.search(q):
        return {"question_type": "stat", "confidence": 0.85, "query_kind_hint": "group_by"}
    if _STAT_RE.search(q):
        return {"question_type": "stat", "confidence": 0.9, "query_kind_hint": "count"}
    if _COVERAGE_RE.search(q):
        return {"question_type": "coverage", "confidence": 0.85, "query_kind_hint": "list"}
    if _LOCATE_RE.search(q):
        return {"question_type": "locate", "confidence": 0.85}
    if _MIXED_RE.search(q):
        return {"question_type": "mixed", "confidence": 0.7}

    return {"question_type": "semantic", "confidence": 0.5}
