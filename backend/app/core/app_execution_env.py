"""App 执行环境 payload 组装与报告展示回填。"""
from __future__ import annotations

from typing import Any

from app.models.app import AppCase

APP_DRIVER_MODE_LABELS: dict[str, str] = {
    "hybrid": "混合控件+图像",
    "native": "仅控件",
    "vision": "仅图像",
    "hybrid_web": "混合 WebView",
    "mobile_chrome": "手机 Chrome H5",
}


def driver_mode_display(mode: str | None) -> str:
    key = (mode or "").strip()
    if not key:
        return "—"
    label = APP_DRIVER_MODE_LABELS.get(key, key)
    return f"{label} ({key})"


APP_TRIGGER_SOURCE_LABELS: dict[str, str] = {
    "manual": "手动",
    "cron": "定时任务",
    "assistant": "小测",
    "mcp": "MCP",
}


def infer_case_app_id(case: AppCase | None) -> str:
    """从用例步骤推断默认包名（首个「启动应用」步骤）。"""
    if not case:
        return ""
    for step in case.steps or []:
        if (step.get("method") or "") != "launch_app":
            continue
        app_id = (step.get("params") or {}).get("app_id")
        if app_id:
            return str(app_id).strip()
    return ""


def normalize_trigger_source(trigger_source: str | None, *, cronjob_id: str | None = None) -> str:
    if trigger_source and str(trigger_source).strip():
        return str(trigger_source).strip()
    if cronjob_id:
        return "cron"
    return "manual"


def trigger_source_label(code: str | None) -> str:
    key = (code or "").strip() or "manual"
    return APP_TRIGGER_SOURCE_LABELS.get(key, key)


def build_case_env(
    base_env: dict[str, Any],
    case: AppCase,
    *,
    trigger_source: str | None = None,
    cronjob_id: str | None = None,
) -> dict[str, Any]:
    """为用例执行记录写入完整 env（驱动模式、包名、触发来源）。"""
    out = dict(base_env)
    out["driver_mode"] = case.driver_mode or "hybrid"
    if not (out.get("app_id") or "").strip():
        inferred = infer_case_app_id(case)
        if inferred:
            out["app_id"] = inferred
    out["trigger_source"] = normalize_trigger_source(trigger_source, cronjob_id=cronjob_id)
    return out


def enrich_app_env_for_display(
    env: dict[str, Any] | None,
    *,
    case: AppCase | None = None,
    cronjob_id: str | None = None,
) -> dict[str, Any]:
    """报告/详情展示时回填缺失字段（兼容历史记录）。"""
    if not isinstance(env, dict):
        env = {}
    out = dict(env)
    if case:
        if not out.get("driver_mode"):
            out["driver_mode"] = case.driver_mode or "hybrid"
        if not (out.get("app_id") or "").strip():
            inferred = infer_case_app_id(case)
            if inferred:
                out["app_id"] = inferred
    if not out.get("trigger_source"):
        out["trigger_source"] = normalize_trigger_source(None, cronjob_id=cronjob_id)
    return out
