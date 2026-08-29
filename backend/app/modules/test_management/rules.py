"""测试管理 Phase 1 — 常量与纯函数规则"""

RELEASE_STATUS_DRAFT = "draft"
RELEASE_STATUS_TESTING = "testing"
RELEASE_STATUS_READY = "ready"
RELEASE_STATUS_RELEASED = "released"
RELEASE_STATUS_ARCHIVED = "archived"

RELEASE_STATUSES = frozenset({
    RELEASE_STATUS_DRAFT,
    RELEASE_STATUS_TESTING,
    RELEASE_STATUS_READY,
    RELEASE_STATUS_RELEASED,
    RELEASE_STATUS_ARCHIVED,
})

# from -> allowed targets
RELEASE_TRANSITIONS: dict[str, frozenset[str]] = {
    RELEASE_STATUS_DRAFT: frozenset({RELEASE_STATUS_TESTING, RELEASE_STATUS_ARCHIVED}),
    RELEASE_STATUS_TESTING: frozenset({RELEASE_STATUS_READY, RELEASE_STATUS_ARCHIVED}),
    RELEASE_STATUS_READY: frozenset({
        RELEASE_STATUS_TESTING,
        RELEASE_STATUS_RELEASED,
        RELEASE_STATUS_ARCHIVED,
    }),
    RELEASE_STATUS_RELEASED: frozenset({RELEASE_STATUS_ARCHIVED}),
    RELEASE_STATUS_ARCHIVED: frozenset(),
}

SCOPE_MUTABLE_STATUSES = frozenset({
    RELEASE_STATUS_DRAFT,
    RELEASE_STATUS_TESTING,
    RELEASE_STATUS_READY,
})

ASSET_TYPES = frozenset({"ui_case", "app_case", "api_case", "perf_scene"})
LINK_TYPES = frozenset({"primary", "partial", "regression"})
RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
SCOPE_STATUSES = frozenset({
    "planned",
    "ready",
    "blocked",
    "not_applicable",
    "completed",
})
AUTOMATION_STATUSES = frozenset({"none", "partial", "covered", "unstable"})
HEALTH_STATUSES = frozenset({"unknown", "healthy", "unstable", "broken"})


def can_transition_release(current: str, target: str) -> bool:
    return target in RELEASE_TRANSITIONS.get(current or "", frozenset())


def release_scope_editable(status: str) -> bool:
    return (status or "") in SCOPE_MUTABLE_STATUSES


def release_requirement_editable(status: str) -> bool:
    """Phase 1：需求条目与范围同等可编辑窗口。"""
    return release_scope_editable(status)


def release_defect_editable(status: str) -> bool:
    """released 仍可维护缺陷；archived 只读。"""
    return (status or "") in SCOPE_MUTABLE_STATUSES | {RELEASE_STATUS_RELEASED}


def compute_automation_status(link_types: list[str] | set[str] | None) -> str:
    """Phase 1：仅按映射类型聚合，不含运行稳定性。"""
    types = {str(t or "").strip() for t in (link_types or []) if str(t or "").strip()}
    if not types:
        return "none"
    if "primary" in types:
        return "covered"
    if types & {"partial", "regression"}:
        return "partial"
    return "none"
