"""Phase 2 评审 / 计划 / 手工运行规则"""

REVIEW_DECISIONS = frozenset({"pending", "approved", "changes_requested", "rejected"})
REVIEW_STATUSES = frozenset({
    "pending",
    "in_review",
    "approved",
    "changes_requested",
    "cancelled",
})

PLAN_TYPES = frozenset({"smoke", "regression", "acceptance", "performance", "custom"})
PLAN_STATUSES = frozenset({"draft", "ready", "running", "completed", "cancelled"})

# cancelled 仅用于自动化归一化（Phase 3）；手工取消未跑项写 skipped
MANUAL_RESULTS = frozenset({"not_run", "passed", "failed", "blocked", "skipped"})
RESULTS_NEED_MESSAGE = frozenset({"failed", "blocked"})
RUN_ITEM_STATUSES = frozenset({"pending", "running", "done", "blocked"})

DEFAULT_CHECKLIST = [
    {"key": "steps_clear", "label": "步骤与预期清晰可执行", "required": True},
    {"key": "data_ready", "label": "测试数据与前置条件完备", "required": True},
    {"key": "priority_ok", "label": "优先级与风险合理", "required": False},
    {"key": "no_dup", "label": "无重复/冗余用例", "required": False},
]


def aggregate_item_decision(decisions: list[dict], required_reviewer_ids: list[int]) -> str:
    """全部必选评审人通过才 approved；任一 rejected / changes_requested 优先。"""
    by_user = {}
    for d in decisions or []:
        rid = d.get("reviewer_id")
        if rid is None:
            continue
        by_user[int(rid)] = (d.get("decision") or "pending").strip()

    required = [int(x) for x in (required_reviewer_ids or [])]
    if not required:
        # 无指定评审人时，取最近一条有效结论
        vals = [v for v in by_user.values() if v != "pending"]
        if not vals:
            return "pending"
        if "rejected" in vals:
            return "rejected"
        if "changes_requested" in vals:
            return "changes_requested"
        if all(v == "approved" for v in vals):
            return "approved"
        return "pending"

    vals = []
    for rid in required:
        vals.append(by_user.get(rid, "pending"))
    if "rejected" in vals:
        return "rejected"
    if "changes_requested" in vals:
        return "changes_requested"
    if any(v == "pending" for v in vals):
        return "pending"
    if all(v == "approved" for v in vals):
        return "approved"
    return "pending"


def aggregate_review_status(item_decisions: list[str]) -> str:
    if not item_decisions:
        return "pending"
    if any(d == "rejected" for d in item_decisions):
        return "changes_requested"
    if any(d == "changes_requested" for d in item_decisions):
        return "changes_requested"
    if any(d == "pending" for d in item_decisions):
        return "in_review"
    if all(d == "approved" for d in item_decisions):
        return "approved"
    return "in_review"
