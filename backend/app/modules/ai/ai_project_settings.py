"""
项目级 AI 执行设置（存 Project.global_vars['ai_settings']）
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from app.models.sys import Project
from app.core.shared.start_url import validate_apm_trace_base_url, validate_default_start_url

AI_SETTINGS_GLOBAL_VARS_KEY = "ai_settings"

RECORDING_LOCATOR_STRATEGIES = frozenset({
    "semantic_first",
    "structure_path_first",
    "xpath_first",
})

DEFAULT_REQUIREMENT_CASE_SETTINGS: dict[str, Any] = {
    "auto_count_enabled_default": False,
    "auto_count_min_floor": 4,
    "auto_count_max_cap": 30,
    "auto_count_min_ratio": 0.7,
    "auto_count_max_ratio": 1.5,
    "fixed_count_hard_max": 50,
}

DEFAULT_AI_PROJECT_SETTINGS: dict[str, Any] = {
    "locator_heal_enabled": True,
    "locator_heal_default_on_execute": True,
    "locator_heal_allow_run_override": True,
    "ai_act_enabled": False,
    "ai_act_default_on_execute": False,
    "ai_act_allow_run_override": True,
    "ai_act_max_per_case": 3,
    "recording_locator_strategy": "semantic_first",
    "default_start_url": "",
    # 交互调试按步试跑：单步等待封顶（秒），仅 debug 会话生效，正式执行不受影响
    "debug_max_step_timeout_seconds": 5,
    "failure_analysis_enabled": True,
    "failure_analysis_default_on_report": True,
    "failure_analysis_allow_run_override": True,
    "perf_ai_analysis_enabled": False,
    "perf_ai_analysis_default_on_run": False,
    "perf_ai_analysis_allow_run_override": True,
    "requirement_case": copy.deepcopy(DEFAULT_REQUIREMENT_CASE_SETTINGS),
    "stability_n": 20,
    "stability_recent_k": 5,
    "stability_unstable_min_n": 10,
    "stability_unstable_pass_below": 0.85,
    "stability_unstable_first_pass_below": 0.85,
    "stability_unstable_salvage_min": 3,
    "stability_unstable_switch_min_n": 5,
    "stability_unstable_switch_min": 3,
    "apm_trace_base_url": "",
}

_STRING_SETTINGS_KEYS = frozenset({
    "recording_locator_strategy",
    "default_start_url",
    "apm_trace_base_url",
})
_NESTED_SETTINGS_KEYS = frozenset({"requirement_case"})
_INT_SETTINGS_KEYS = frozenset({
    "ai_act_max_per_case",
    "debug_max_step_timeout_seconds",
})
_STABILITY_INT_KEYS = frozenset({
    "stability_n",
    "stability_recent_k",
    "stability_unstable_min_n",
    "stability_unstable_salvage_min",
    "stability_unstable_switch_min_n",
    "stability_unstable_switch_min",
})
_STABILITY_RATE_KEYS = frozenset({
    "stability_unstable_pass_below",
    "stability_unstable_first_pass_below",
})


def _apply_stability_setting(target: dict[str, Any], key: str, value: Any) -> None:
    if key == "stability_n":
        target[key] = normalize_stability_n(value)
    elif key == "stability_recent_k":
        target[key] = normalize_stability_recent_k(value)
    elif key == "stability_unstable_min_n":
        target[key] = _clamp_int(value, 10, 5, 50)
    elif key == "stability_unstable_salvage_min":
        target[key] = _clamp_int(value, 3, 0, 20)
    elif key == "stability_unstable_switch_min_n":
        target[key] = _clamp_int(value, 5, 3, 50)
    elif key == "stability_unstable_switch_min":
        target[key] = _clamp_int(value, 3, 0, 20)
    elif key in _STABILITY_RATE_KEYS:
        target[key] = normalize_stability_rate(value)

STABILITY_N_DEFAULT = 20
STABILITY_N_MIN = 5
STABILITY_N_MAX = 50
STABILITY_RECENT_K_DEFAULT = 5
STABILITY_RECENT_K_MIN = 1
STABILITY_RECENT_K_MAX = 20
STABILITY_RATE_DEFAULT = 0.85


def normalize_stability_n(value: Any) -> int:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return STABILITY_N_DEFAULT
    try:
        num = int(value)
    except (TypeError, ValueError):
        return STABILITY_N_DEFAULT
    if num <= 0:
        return STABILITY_N_DEFAULT
    return max(STABILITY_N_MIN, min(STABILITY_N_MAX, num))


def normalize_stability_recent_k(value: Any) -> int:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return STABILITY_RECENT_K_DEFAULT
    try:
        num = int(value)
    except (TypeError, ValueError):
        return STABILITY_RECENT_K_DEFAULT
    if num <= 0:
        return STABILITY_RECENT_K_DEFAULT
    return max(STABILITY_RECENT_K_MIN, min(STABILITY_RECENT_K_MAX, num))


def normalize_stability_rate(value: Any, default: float = STABILITY_RATE_DEFAULT) -> float:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return default
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num > 1:
        num = num / 100.0
    return max(0.5, min(1.0, round(num, 4)))


def get_stability_policy(settings: dict[str, Any] | None) -> dict[str, Any]:
    src = settings if isinstance(settings, dict) else {}
    min_n = _clamp_int(src.get("stability_unstable_min_n"), 10, 5, 50)
    salvage_min = _clamp_int(src.get("stability_unstable_salvage_min"), 3, 0, 20)
    switch_min_n = _clamp_int(src.get("stability_unstable_switch_min_n"), 5, 3, 50)
    switch_min = _clamp_int(src.get("stability_unstable_switch_min"), 3, 0, 20)
    return {
        "n": normalize_stability_n(src.get("stability_n")),
        "recent_k": normalize_stability_recent_k(src.get("stability_recent_k")),
        "rules": {
            "min_n": min_n,
            "pass_below": normalize_stability_rate(src.get("stability_unstable_pass_below")),
            "first_pass_below": normalize_stability_rate(src.get("stability_unstable_first_pass_below")),
            "salvage_min": salvage_min,
            "switch_min_n": switch_min_n,
            "switch_min": switch_min,
        },
    }

# 交互调试单步超时：1～120 秒
DEBUG_MAX_STEP_TIMEOUT_SECONDS_DEFAULT = 5
DEBUG_MAX_STEP_TIMEOUT_SECONDS_MIN = 1
DEBUG_MAX_STEP_TIMEOUT_SECONDS_MAX = 120


def normalize_debug_max_step_timeout_seconds(value: Any) -> int:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return DEBUG_MAX_STEP_TIMEOUT_SECONDS_DEFAULT
    try:
        num = int(value)
    except (TypeError, ValueError):
        return DEBUG_MAX_STEP_TIMEOUT_SECONDS_DEFAULT
    if num <= 0:
        return DEBUG_MAX_STEP_TIMEOUT_SECONDS_DEFAULT
    return max(
        DEBUG_MAX_STEP_TIMEOUT_SECONDS_MIN,
        min(DEBUG_MAX_STEP_TIMEOUT_SECONDS_MAX, num),
    )


def normalize_recording_locator_strategy(value: Any) -> str:
    val = str(value or "").strip()
    if val in RECORDING_LOCATOR_STRATEGIES:
        return val
    return str(DEFAULT_AI_PROJECT_SETTINGS["recording_locator_strategy"])


def _clamp_float(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def normalize_requirement_case_settings(raw: Any) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_REQUIREMENT_CASE_SETTINGS)
    if not isinstance(raw, dict):
        return base
    base["auto_count_enabled_default"] = bool(
        raw.get("auto_count_enabled_default", base["auto_count_enabled_default"])
    )
    base["auto_count_min_floor"] = _clamp_int(
        raw.get("auto_count_min_floor", base["auto_count_min_floor"]), 4, 1, 50
    )
    base["auto_count_max_cap"] = _clamp_int(
        raw.get("auto_count_max_cap", base["auto_count_max_cap"]), 30, 5, 100
    )
    if base["auto_count_max_cap"] < base["auto_count_min_floor"]:
        base["auto_count_max_cap"] = base["auto_count_min_floor"]
    base["auto_count_min_ratio"] = _clamp_float(
        raw.get("auto_count_min_ratio", base["auto_count_min_ratio"]), 0.7, 0.3, 1.0
    )
    base["auto_count_max_ratio"] = _clamp_float(
        raw.get("auto_count_max_ratio", base["auto_count_max_ratio"]), 1.5, 1.0, 3.0
    )
    if base["auto_count_max_ratio"] < base["auto_count_min_ratio"]:
        base["auto_count_max_ratio"] = base["auto_count_min_ratio"]
    base["fixed_count_hard_max"] = _clamp_int(
        raw.get("fixed_count_hard_max", base["fixed_count_hard_max"]), 50, 10, 100
    )
    return base


def resolve_soft_count_range(recommended: int, rc: Optional[dict] = None) -> dict[str, Any]:
    """由建议条数 R + 项目配置算出 soft_min / soft_max 与区间说明。"""
    settings = normalize_requirement_case_settings(rc)
    r = max(1, int(recommended or 1))
    floor = int(settings["auto_count_min_floor"])
    cap = int(settings["auto_count_max_cap"])
    min_ratio = float(settings["auto_count_min_ratio"])
    max_ratio = float(settings["auto_count_max_ratio"])

    soft_min = max(floor, int(round(r * min_ratio)))
    soft_max = min(cap, max(soft_min, int(round(r * max_ratio))))
    range_explain = (
        f"区间来源：建议 {r} × 系数 {min_ratio:g}～{max_ratio:g}，"
        f"夹绝对 {floor}～{cap}"
    )
    return {
        "base_recommended_count": r,
        "soft_min_count": soft_min,
        "soft_max_count": soft_max,
        "range_explain": range_explain,
        "auto_count_min_floor": floor,
        "auto_count_max_cap": cap,
        "auto_count_min_ratio": min_ratio,
        "auto_count_max_ratio": max_ratio,
        "fixed_count_hard_max": int(settings["fixed_count_hard_max"]),
        "auto_count_enabled_default": bool(settings["auto_count_enabled_default"]),
    }


def normalize_ai_project_settings(raw: Any) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_AI_PROJECT_SETTINGS)
    if isinstance(raw, dict):
        for key in DEFAULT_AI_PROJECT_SETTINGS:
            if key not in raw or raw[key] is None:
                continue
            if key == "requirement_case":
                base[key] = normalize_requirement_case_settings(raw[key])
            elif key == "ai_act_max_per_case":
                try:
                    base[key] = max(1, min(10, int(raw[key])))
                except (TypeError, ValueError):
                    base[key] = DEFAULT_AI_PROJECT_SETTINGS["ai_act_max_per_case"]
            elif key == "debug_max_step_timeout_seconds":
                base[key] = normalize_debug_max_step_timeout_seconds(raw[key])
            elif key in _STABILITY_INT_KEYS or key in _STABILITY_RATE_KEYS:
                _apply_stability_setting(base, key, raw[key])
            elif key == "recording_locator_strategy":
                base[key] = normalize_recording_locator_strategy(raw[key])
            elif key in _STRING_SETTINGS_KEYS:
                base[key] = str(raw[key] or "").strip()
            elif key in _INT_SETTINGS_KEYS:
                continue
            else:
                base[key] = bool(raw[key])
    return base


def get_ai_project_settings_from_project(project: Project) -> dict[str, Any]:
    gv = project.global_vars if isinstance(project.global_vars, dict) else {}
    return normalize_ai_project_settings(gv.get(AI_SETTINGS_GLOBAL_VARS_KEY))


async def load_ai_project_settings(project_id: int) -> dict[str, Any]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return normalize_ai_project_settings(None)
    return get_ai_project_settings_from_project(project)


def get_requirement_case_settings(settings: Optional[dict] = None) -> dict[str, Any]:
    if isinstance(settings, dict) and isinstance(settings.get("requirement_case"), dict):
        return normalize_requirement_case_settings(settings["requirement_case"])
    return normalize_requirement_case_settings(None)


async def load_requirement_case_settings(project_id: int) -> dict[str, Any]:
    settings = await load_ai_project_settings(project_id)
    return get_requirement_case_settings(settings)


async def save_ai_project_settings(project_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    current = get_ai_project_settings_from_project(project)
    for key in DEFAULT_AI_PROJECT_SETTINGS:
        if key not in updates:
            continue
        if key == "requirement_case":
            # 支持整对象替换，也支持在已有对象上合并
            merged = {**current.get("requirement_case", {}), **(updates[key] or {})}
            current[key] = normalize_requirement_case_settings(merged)
        elif key == "ai_act_max_per_case":
            try:
                current[key] = max(1, min(10, int(updates[key])))
            except (TypeError, ValueError):
                pass
        elif key == "debug_max_step_timeout_seconds":
            current[key] = normalize_debug_max_step_timeout_seconds(updates[key])
        elif key in _STABILITY_INT_KEYS or key in _STABILITY_RATE_KEYS:
            _apply_stability_setting(current, key, updates[key])
        elif key == "recording_locator_strategy":
            current[key] = normalize_recording_locator_strategy(updates[key])
        elif key in _STRING_SETTINGS_KEYS:
            if key == "default_start_url":
                current[key] = validate_default_start_url(updates[key])
            elif key == "apm_trace_base_url":
                current[key] = validate_apm_trace_base_url(updates[key])
            else:
                current[key] = str(updates[key] or "").strip()
        elif key in _INT_SETTINGS_KEYS:
            continue
        else:
            current[key] = bool(updates[key])
    gv = dict(project.global_vars or {})
    gv[AI_SETTINGS_GLOBAL_VARS_KEY] = current
    project.global_vars = gv
    await project.save()
    return current


async def resolve_ai_act_for_execute(
    project_id: int,
    user_override: Optional[bool] = None,
) -> bool:
    """计算本次 UI 执行是否启用 AI Act 兜底（自愈失败后再调 LLM）。"""
    settings = await load_ai_project_settings(project_id)
    if not settings["ai_act_enabled"]:
        return False
    if user_override is not None and settings["ai_act_allow_run_override"]:
        return bool(user_override)
    return bool(settings["ai_act_default_on_execute"])


async def resolve_locator_heal_for_execute(
    project_id: int,
    user_override: Optional[bool] = None,
) -> bool:
    """
    计算本次 UI 执行是否启用定位器自愈。
    优先级：项目总开关 OFF → False；允许覆盖且用户传参 → 用户值；否则 → 项目默认。
    """
    settings = await load_ai_project_settings(project_id)
    if not settings["locator_heal_enabled"]:
        return False
    if user_override is not None and settings["locator_heal_allow_run_override"]:
        return bool(user_override)
    return settings["locator_heal_default_on_execute"]


async def resolve_recording_locator_strategy(project_id: int) -> str:
    settings = await load_ai_project_settings(project_id)
    return normalize_recording_locator_strategy(settings.get("recording_locator_strategy"))


async def resolve_debug_max_step_timeout_seconds(project_id: int) -> int:
    settings = await load_ai_project_settings(project_id)
    return normalize_debug_max_step_timeout_seconds(
        settings.get("debug_max_step_timeout_seconds")
    )


async def resolve_failure_analysis_for_report(
    project_id: int,
    user_override: Optional[bool] = None,
) -> bool:
    """计算本次执行报告是否启用失败 AI 分析入口。"""
    settings = await load_ai_project_settings(project_id)
    if user_override is not None and settings["failure_analysis_allow_run_override"]:
        env = {"failure_analysis_on_report": bool(user_override)}
        return evaluate_failure_analysis_visibility(settings, env)
    return evaluate_failure_analysis_visibility(settings, None)


def evaluate_failure_analysis_visibility(settings: dict, env: dict | None) -> bool:
    """与前端 useFailureAnalysisGate 保持一致。"""
    if not settings.get("failure_analysis_enabled", True):
        return False
    env_flag = (env or {}).get("failure_analysis_on_report")
    if env_flag is False:
        return False
    if env_flag is True:
        return True
    return settings.get("failure_analysis_default_on_report", True) is not False


async def assert_failure_analysis_enabled(project_id: int) -> None:
    """API 侧校验：项目是否允许失败 AI 分析。"""
    settings = await load_ai_project_settings(project_id)
    if not settings["failure_analysis_enabled"]:
        raise ValueError("项目已关闭失败 AI 分析")


def assert_failure_analysis_for_execution_env(settings: dict, env: dict | None) -> None:
    """校验单次执行是否允许失败 AI 分析（env 由执行时写入）。"""
    if not evaluate_failure_analysis_visibility(settings, env):
        if not settings.get("failure_analysis_enabled", True):
            raise ValueError("项目已关闭失败 AI 分析")
        raise ValueError("本次执行未启用失败 AI 分析")


async def resolve_perf_ai_for_run(
    project_id: int,
    user_override: Optional[bool] = None,
) -> bool:
    """计算本次压测结束后是否自动触发 AI 分析。"""
    settings = await load_ai_project_settings(project_id)
    if not settings.get("perf_ai_analysis_enabled", False):
        return False
    if user_override is not None and settings.get("perf_ai_analysis_allow_run_override", True):
        return bool(user_override)
    return bool(settings.get("perf_ai_analysis_default_on_run", False))


async def assert_perf_ai_analysis_enabled(project_id: int) -> None:
    settings = await load_ai_project_settings(project_id)
    if not settings.get("perf_ai_analysis_enabled", False):
        raise ValueError("项目已关闭压测 AI 分析")
