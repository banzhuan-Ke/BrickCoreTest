"""测试管理 Phase 1 schemas"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class StandardResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class ReleaseCreateBody(BaseModel):
    project_id: int
    release_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    owner_id: Optional[int] = None
    planned_start_at: Optional[datetime] = None
    planned_release_at: Optional[datetime] = None
    external_url: Optional[str] = None


class ReleaseUpdateBody(BaseModel):
    release_key: Optional[str] = Field(None, max_length=64)
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    owner_id: Optional[int] = None
    planned_start_at: Optional[datetime] = None
    planned_release_at: Optional[datetime] = None
    external_url: Optional[str] = None


class ReleaseTransitionBody(BaseModel):
    status: str = Field(..., description="目标状态")


class RequirementCreateBody(BaseModel):
    requirement_key: str = Field(..., min_length=1, max_length=128)
    title: str = ""
    url: Optional[str] = None
    note: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url_protocol(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        u = str(value).strip()
        if not u:
            return None
        lower = u.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("url 须为 http(s) 链接")
        return u


class RequirementUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    url: Optional[str] = None
    note: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url_protocol(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        u = str(value).strip()
        if not u:
            return None
        lower = u.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("url 须为 http(s) 链接")
        return u


class RequirementUpgradeBody(BaseModel):
    name: Optional[str] = Field(None, max_length=500)
    initial_content: Optional[str] = None


class ScopeBatchAddBody(BaseModel):
    functional_case_ids: List[int] = Field(..., min_length=1)
    risk_level: str = "medium"
    owner_id: Optional[int] = None
    requirement_key: Optional[str] = None


class ScopeUpdateBody(BaseModel):
    risk_level: Optional[str] = None
    scope_status: Optional[str] = None
    owner_id: Optional[int] = None
    requirement_key: Optional[str] = None
    note: Optional[str] = None


class ScopeBatchUpdateBody(BaseModel):
    scope_ids: List[int] = Field(..., min_length=1)
    risk_level: Optional[str] = None
    owner_id: Optional[int] = None
    clear_owner: bool = False


class AssetLinkCreateBody(BaseModel):
    project_id: int
    functional_case_id: int
    asset_type: str
    asset_id: int
    link_type: str = "primary"
    coverage_note: Optional[str] = None


class AssetLinkUpdateBody(BaseModel):
    link_type: Optional[str] = None
    coverage_note: Optional[str] = None
    health_status: Optional[str] = None


class SeedLinksBody(BaseModel):
    project_id: int


# ========== Phase 2 ==========


class ReviewTemplateCreateBody(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    checklist: Optional[List[Any]] = None
    is_default: bool = False


class ReviewTemplateUpdateBody(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    checklist: Optional[List[Any]] = None
    is_default: Optional[bool] = None


class ReviewCreateBody(BaseModel):
    project_id: int
    title: str = Field(..., min_length=1, max_length=200)
    functional_case_ids: List[int] = Field(..., min_length=1)
    reviewer_ids: List[int] = Field(..., min_length=1)
    release_id: Optional[int] = None
    template_id: Optional[int] = None
    due_at: Optional[datetime] = None


class ReviewItemDecisionBody(BaseModel):
    decision: str
    comment: Optional[str] = None
    checklist_result: Optional[dict] = None
    reviewer_id: Optional[int] = None
    attachments: Optional[List[dict]] = None


class ReviewFinalizeBody(BaseModel):
    decision: str = Field(..., description="approved / changes_requested / rejected")
    comment: Optional[str] = None


class PlanCreateBody(BaseModel):
    project_id: int
    release_id: int
    name: str = Field(..., min_length=1, max_length=200)
    plan_type: str = "regression"
    environment_id: Optional[int] = None
    entry_criteria: Optional[str] = None
    exit_criteria: Optional[str] = None
    description: Optional[str] = None
    from_scope: bool = True
    scope_ids: Optional[List[int]] = None
    include_automation: bool = False


class PlanUpdateBody(BaseModel):
    name: Optional[str] = None
    plan_type: Optional[str] = None
    environment_id: Optional[int] = None
    entry_criteria: Optional[str] = None
    exit_criteria: Optional[str] = None
    description: Optional[str] = None


class PlanRunCreateBody(BaseModel):
    environment_id: Optional[int] = None
    item_ids: Optional[List[int]] = None
    trigger_source: str = "web"
    dispatch_automation: bool = False
    device_id: Optional[str] = None


class AutomationDispatchBody(BaseModel):
    device_id: Optional[str] = None


class DefectCreateBody(BaseModel):
    project_id: int
    release_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    severity: str = "major"
    priority: str = "p2"
    status: str = "open"
    found_in: Optional[str] = None
    assignee_id: Optional[int] = None
    reporter_id: Optional[int] = None
    external_system: Optional[str] = None
    external_key: Optional[str] = None
    external_url: Optional[str] = None
    attachments: Optional[List[Any]] = None
    links: Optional[List[dict]] = None


class DefectUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    severity: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    found_in: Optional[str] = None
    fixed_in: Optional[str] = None
    assignee_id: Optional[int] = None
    reporter_id: Optional[int] = None
    handler_id: Optional[int] = None
    attributor_id: Optional[int] = None
    release_id: Optional[int] = None
    external_system: Optional[str] = None
    external_key: Optional[str] = None
    external_url: Optional[str] = None
    resolution_type: Optional[str] = None
    resolution_detail: Optional[str] = None
    root_cause: Optional[str] = None
    attachments: Optional[List[Any]] = None


class DefectTransitionBody(BaseModel):
    """负责人处理流转：填意见后进入下一状态，可顺带改处理人。"""
    to_status: str
    comment: Optional[str] = Field(None, max_length=10000)
    assignee_id: Optional[int] = None
    handler_id: Optional[int] = None
    attributor_id: Optional[int] = None
    resolution_type: Optional[str] = None
    resolution_detail: Optional[str] = None


class DefectFromRunItemBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: str = "major"
    priority: str = "p2"
    assignee_id: Optional[int] = None
    reporter_id: Optional[int] = None


class DefectCommentBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class DefectLinkBody(BaseModel):
    link_type: str = "run_item"
    run_item_id: Optional[int] = None
    functional_case_id: Optional[int] = None
    requirement_id: Optional[int] = None
    asset_type: Optional[str] = None
    asset_id: Optional[int] = None
    external_url: Optional[str] = None
    note: Optional[str] = None


class ManualResultBody(BaseModel):
    result_status: str
    result_message: Optional[str] = None
    assignee_id: Optional[int] = None
    evidence_json: Optional[dict] = None


class RunItemAssigneeBody(BaseModel):
    assignee_id: Optional[int] = None
    clear_assignee: bool = False


# ========== Phase 3 补全 ==========


class RequirementReviewCreateBody(BaseModel):
    project_id: int
    requirement_id: int
    reviewer_ids: List[int] = Field(..., min_length=1)
    ai_assist_summary: Optional[str] = None


class RequirementReviewItemBody(BaseModel):
    category: str = "other"
    comment: Optional[str] = None
    suggested_fix: Optional[str] = None
    section_id: Optional[str] = None
    severity: str = "medium"


class RequirementReviewCompleteBody(BaseModel):
    decision: str = Field(..., description="approved/changes_requested/rejected")
    summary: Optional[str] = None


class RequirementReviewDecisionBody(BaseModel):
    """评审人提交个人结论（多人聚合，非覆盖）。"""
    decision: str = Field(..., description="approved/changes_requested/rejected")
    comment: Optional[str] = Field(None, max_length=5000)
    reviewer_id: Optional[int] = None


# ========== Phase 4：质量门禁 ==========


class QualitySnapshotCreateBody(BaseModel):
    note: Optional[str] = None
    force: bool = False


class QualityWaiverBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    note: Optional[str] = None
