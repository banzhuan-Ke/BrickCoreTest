"""项目设置相关 Schema（执行与自愈 / 功能用例策略等）。"""
from typing import Optional

from pydantic import BaseModel, Field


class RequirementCaseSettingsBody(BaseModel):
    """字段均为可选，支持 requirement_case 局部更新（未传字段不覆盖）。"""
    auto_count_enabled_default: Optional[bool] = Field(None, description="需求用例生成默认开启 AI 自定条数")
    auto_count_min_floor: Optional[int] = Field(None, ge=1, le=50, description="AI 自定条数绝对下限")
    auto_count_max_cap: Optional[int] = Field(None, ge=5, le=100, description="AI 自定条数绝对上限")
    auto_count_min_ratio: Optional[float] = Field(None, ge=0.3, le=1.0, description="软下限 = 建议条数 × 系数")
    auto_count_max_ratio: Optional[float] = Field(None, ge=1.0, le=3.0, description="软上限 = 建议条数 × 系数")
    fixed_count_hard_max: Optional[int] = Field(None, ge=10, le=100, description="参考条数模式硬上限")


class AiExecutionSettingsBody(BaseModel):
    """字段均为可选；PUT 仅合并客户端显式提交的字段，避免默认值静默重置。"""
    locator_heal_enabled: Optional[bool] = Field(None, description="项目是否允许 Runner 定位器自愈")
    locator_heal_default_on_execute: Optional[bool] = Field(None, description="执行时默认是否开启自愈")
    locator_heal_allow_run_override: Optional[bool] = Field(None, description="是否允许运行弹窗单次覆盖自愈")
    ai_act_enabled: Optional[bool] = Field(None, description="项目是否允许 AI Act 兜底")
    ai_act_default_on_execute: Optional[bool] = Field(None, description="执行时默认是否开启 AI Act")
    ai_act_allow_run_override: Optional[bool] = Field(None, description="是否允许运行弹窗单次覆盖 AI Act")
    ai_act_max_per_case: Optional[int] = Field(None, ge=1, le=10, description="单用例 AI Act 最大次数")
    recording_locator_strategy: Optional[str] = Field(
        None,
        description="录制默认定位策略: semantic_first | structure_path_first | xpath_first",
    )
    default_start_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Web 录制/交互调试默认起始 URL（步骤无 open_url 时预填）",
    )
    failure_analysis_enabled: Optional[bool] = Field(None, description="项目是否允许失败 AI 分析")
    failure_analysis_default_on_report: Optional[bool] = Field(None, description="报告页默认是否展示失败 AI 分析入口")
    failure_analysis_allow_run_override: Optional[bool] = Field(None, description="是否允许运行弹窗单次覆盖")
    requirement_case: Optional[RequirementCaseSettingsBody] = Field(
        default=None,
        description="功能用例生成策略（条数模式软上下限等）",
    )


def payload_from_execution_settings_body(body: AiExecutionSettingsBody) -> dict:
    """转为可交给 save_ai_project_settings 的局部更新字典。"""
    payload = body.model_dump(exclude_unset=True)
    if isinstance(payload.get("requirement_case"), dict):
        payload["requirement_case"] = {
            k: v for k, v in payload["requirement_case"].items() if v is not None
        }
    return payload
