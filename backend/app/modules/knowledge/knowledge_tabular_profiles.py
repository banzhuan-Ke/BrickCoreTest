"""表格 profile 列别名与字段映射"""
from __future__ import annotations

import re
from typing import Any, Optional

PROFILE_ZENTAO_BUG = "zentao_bug"
PROFILE_ITERATION_PLAN = "iteration_plan"
PROFILE_GENERIC_TABLE = "generic_table"

_ZENTAO_FIELD_ALIASES: dict[str, list[str]] = {
    "bug_owner": ["bug归属人", "归属人", "bug owner", "owner"],
    "resolved_by": ["解决者", "解决人", "处理人", "由谁解决"],
    "assigned_to": ["指派给", "负责人", "指派"],
    "severity": ["严重程度", "严重级别", "级别"],
    "bug_id": ["bug编号", "编号", "缺陷编号", "id"],
    "title": ["bug标题", "标题", "缺陷标题"],
    "status": ["状态", "bug状态"],
    "priority": ["优先级"],
}

_ITERATION_FIELD_ALIASES: dict[str, list[str]] = {
    "owner": ["负责人", "责任人"],
    "req_content": ["需求内容", "需求说明", "需求"],
    "content": ["任务内容", "工作项", "内容", "任务"],
    "members": ["参与人", "测试人员", "人员", "成员"],
    "start_date": ["开始日期", "开始时间"],
    "end_date": ["结束日期", "完成日期", "结束时间"],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())


def resolve_field_for_profile(profile: str, spoken: str) -> Optional[str]:
    spoken_n = _norm(spoken)
    if not spoken_n:
        return None
    aliases = _ZENTAO_FIELD_ALIASES if profile == PROFILE_ZENTAO_BUG else _ITERATION_FIELD_ALIASES
    if profile == PROFILE_GENERIC_TABLE:
        return spoken.strip()
    for field, words in aliases.items():
        for w in words:
            wn = _norm(w)
            if spoken_n == wn:
                return field
    for field, words in aliases.items():
        for w in words:
            wn = _norm(w)
            if len(spoken_n) >= 2 and len(wn) >= 2 and (spoken_n in wn or wn in spoken_n):
                return field
    return None


def _header_match(headers: list[str], spoken: str) -> Optional[str]:
    spoken_n = _norm(spoken)
    if not spoken_n:
        return None
    for h in headers:
        hn = _norm(h)
        if spoken_n == hn:
            return h
    for h in headers:
        hn = _norm(h)
        if len(spoken_n) >= 2 and len(hn) >= 2 and (spoken_n in hn or hn in spoken_n):
            return h
    return None


def resolve_column_header(
    profile: str,
    field: str,
    headers: list[str],
    *,
    spoken: str = "",
) -> Optional[str]:
    """profile 标准字段 → 实际表头列名（必须命中真实 headers）。"""
    if profile == PROFILE_GENERIC_TABLE:
        return _header_match(headers, spoken or field)

    if profile == PROFILE_ZENTAO_BUG:
        display_map = {
            "bug_owner": "BUG归属人",
            "resolved_by": "解决者",
            "assigned_to": "指派给",
            "severity": "严重程度",
            "bug_id": "Bug编号",
            "title": "Bug标题",
            "status": "状态",
            "priority": "优先级",
        }
        preferred = display_map.get(field, "")
        if preferred:
            matched = _header_match(headers, preferred)
            if matched:
                return matched
        for h in headers:
            hn = _norm(h)
            for alias in _ZENTAO_FIELD_ALIASES.get(field, []):
                an = _norm(alias)
                if an and (an == hn or (len(an) >= 2 and len(hn) >= 2 and (an in hn or hn in an))):
                    return h
        return None

    if profile == PROFILE_ITERATION_PLAN:
        for h in headers:
            hn = _norm(h)
            for alias in _ITERATION_FIELD_ALIASES.get(field, []):
                an = _norm(alias)
                if an and (an == hn or (len(an) >= 2 and len(hn) >= 2 and (an in hn or hn in an))):
                    return h
    return None


def field_display_label(profile: str, field: str, column: str) -> str:
    if column:
        return column
    if profile == PROFILE_ZENTAO_BUG:
        return {
            "bug_owner": "BUG归属人",
            "resolved_by": "解决者",
            "assigned_to": "指派给",
            "bug_id": "Bug编号",
            "title": "Bug标题",
        }.get(field, field)
    return field
