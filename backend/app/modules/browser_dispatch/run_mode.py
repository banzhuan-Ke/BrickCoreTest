"""Browser Lab / UI Agent 运行位置（平台仅派发 Runner）。"""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import HTTPException

from app.core.platform.config import ALGORITHM, SECRET_KEY
from app.core.platform import config as settings
from app.models.sys import Device

_BROWSER_JOB_TYP = "browser_job"
_DEFAULT_JOB_TOKEN_TTL = 7200
_MAX_JOB_TOKEN_TTL = 86400


def estimate_job_token_ttl_seconds(
    *,
    max_steps: int = 25,
    step_timeout: int = 390,
    buffer_seconds: int = 3600,
) -> int:
    estimated = int(max_steps) * int(step_timeout) + int(buffer_seconds)
    return min(max(_DEFAULT_JOB_TOKEN_TTL, estimated), _MAX_JOB_TOKEN_TTL)


def verify_internal_job_token(
    token: str, *, expected_project_id: int | None = None
) -> dict[str, Any]:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as ex:
        raise HTTPException(status_code=401, detail="内部任务 token 已过期") from ex
    except jwt.InvalidTokenError as ex:
        raise HTTPException(status_code=401, detail="内部任务 token 无效") from ex
    if data.get("typ") != _BROWSER_JOB_TYP:
        raise HTTPException(status_code=401, detail="非浏览器任务 token")
    if not data.get("job_id"):
        raise HTTPException(status_code=401, detail="内部任务 token 缺少 job_id")
    if expected_project_id is not None and int(data.get("project_id") or 0) != int(expected_project_id):
        raise HTTPException(status_code=403, detail="任务 token 与项目不匹配")
    return data


def get_browser_run_defaults() -> dict[str, Any]:
    """前端设备选择与派发开关；浏览器任务固定 Runner，无本机回退。"""
    return {
        "default_mode": "runner",
        "runner_dispatch_enabled": bool(settings.BROWSER_RUN_DISPATCH_ENABLED),
    }


def resolve_run_mode(
    requested: str | None = None,
    *,
    default_mode: str | None = None,
    allow_local: bool | None = None,
) -> str:
    """浏览器 Agent 任务固定 Runner；忽略 requested / default_mode / allow_local。"""
    return "runner"


async def validate_device_online(device_id: str | None, *, require_web: bool = True) -> Device:
    did = (device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="Runner 模式须选择在线执行设备")
    device = await Device.get_or_none(id=did, is_del=False)
    if not device:
        raise HTTPException(status_code=400, detail=f"设备 {did} 不存在")
    if device.status != "在线":
        name = device.name or did
        raise HTTPException(status_code=400, detail=f"设备「{name}」当前离线，请重新上线 Runner")
    if require_web:
        engines = device.runner_engine_types or []
        if engines and "web" not in engines:
            name = device.name or did
            raise HTTPException(
                status_code=400,
                detail=f"设备「{name}」未启用 Web 自动化，请在 Runner 客户端勾选后重新上线",
            )
    return device


def build_internal_token(
    *,
    job_id: str,
    project_id: int,
    task_type: str = "browser_lab",
    ttl_seconds: int = _DEFAULT_JOB_TOKEN_TTL,
) -> str:
    expire = int(time.time()) + max(60, int(ttl_seconds))
    payload = {
        "typ": _BROWSER_JOB_TYP,
        "job_id": str(job_id),
        "project_id": int(project_id),
        "task_type": (task_type or "browser_lab").strip(),
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def analyze_import_steps(steps: list[dict] | None) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    weak_count = 0
    strong_count = 0
    candidate_steps = 0
    _ELEMENT_METHODS = frozenset({"click_ele", "fill_value", "select_option", "hover_ele"})
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict):
            continue
        meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
        method = step.get("method") or ""
        if method in _ELEMENT_METHODS:
            strength = (meta.get("locator_strength") or "").strip().lower()
            if strength == "strong":
                strong_count += 1
            if meta.get("candidates"):
                candidate_steps += 1
        if not meta.get("needs_manual_locator") and meta.get("locator_strength") != "weak":
            continue
        weak_count += 1
        desc = (step.get("desc") or step.get("method") or "").strip()[:80]
        warnings.append(
            {
                "step_index": i,
                "step_id": step.get("id"),
                "reason": "needs_manual_locator",
                "message": f"第 {i + 1} 步「{desc}」定位器为启发式生成，导入后请核对",
            }
        )
    total = len(steps or [])
    return {
        "import_warnings": warnings,
        "weak_locator_count": weak_count,
        "strong_locator_count": strong_count,
        "steps_with_candidates": candidate_steps,
        "is_draft": True,
        "import_mode": "quick",
        "quality_score": max(0, min(100, 100 - weak_count * 12 + strong_count * 5 + candidate_steps * 3)),
        "step_count": total,
    }
