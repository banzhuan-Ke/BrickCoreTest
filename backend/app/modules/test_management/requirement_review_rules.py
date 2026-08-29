"""需求可测性评审 — 常量"""
from __future__ import annotations

REQUIREMENT_REVIEW_STATUSES = frozenset({
    "pending",
    "in_review",
    "approved",
    "changes_requested",
    "rejected",
})

# AiRequirement.review_status（闸门用）
REQUIREMENT_GATE_STATUSES = frozenset({
    "pending",
    "in_review",
    "approved",
    "rejected",
    "changes_requested",
})

REQUIREMENT_REVIEW_CATEGORIES = frozenset({
    "scope_unclear",
    "acceptance_missing",
    "edge_case_gap",
    "priority_issue",
    "testability_risk",
    "other",
})

CATEGORY_LABELS = {
    "scope_unclear": "范围不明确",
    "acceptance_missing": "缺少验收标准",
    "edge_case_gap": "边界场景遗漏",
    "priority_issue": "优先级问题",
    "testability_risk": "可测试性风险",
    "other": "其他",
}


def requirement_design_allowed(review_status: str) -> bool:
    return (review_status or "").strip() == "approved"
