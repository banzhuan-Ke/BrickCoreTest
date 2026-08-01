"""Pydantic models for JMeter import preview/commit."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ConflictStrategy = Literal["create_always", "skip_existing", "merge_case"]


class JmeterUnsupportedNode(BaseModel):
    source_path: str
    type: str
    reason: str


class JmeterPreviewCounts(BaseModel):
    apis: int = 0
    cases: int = 0
    suites: int = 0
    perf_scenes: int = 0
    unsupported: int = 0
    warnings: int = 0


class JmeterPreviewResponse(BaseModel):
    preview_token: str
    test_plan_name: str
    counts: JmeterPreviewCounts
    apis: List[Dict[str, Any]] = Field(default_factory=list)
    cases: List[Dict[str, Any]] = Field(default_factory=list)
    suites: List[Dict[str, Any]] = Field(default_factory=list)
    perf_scenes: List[Dict[str, Any]] = Field(default_factory=list)
    unsupported_nodes: List[JmeterUnsupportedNode] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    todos: List[str] = Field(default_factory=list)


class JmeterCommitRequest(BaseModel):
    preview_token: str = Field(..., description="preview 返回的短期 token")
    project_id: int
    catalog_id: Optional[int] = None
    conflict_strategy: ConflictStrategy = "merge_case"
    create_suites: bool = True
    create_perf_scenes: bool = False
    selected_sampler_paths: Optional[List[str]] = Field(
        None, description="仅导入勾选的 sampler source_path；空或省略表示全部"
    )


class JmeterCommitItemResult(BaseModel):
    source_path: str
    action: str  # created | merged | skipped | failed
    api_id: Optional[int] = None
    case_id: Optional[int] = None
    message: Optional[str] = None


class JmeterCommitResponse(BaseModel):
    test_plan_name: str
    created_apis: int = 0
    created_cases: int = 0
    merged_cases: int = 0
    skipped: int = 0
    failed: int = 0
    created_suites: int = 0
    suite_ids: List[int] = Field(default_factory=list)
    created_scenes: int = 0
    scene_ids: List[int] = Field(default_factory=list)
    items: List[JmeterCommitItemResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    todos: List[str] = Field(default_factory=list)
