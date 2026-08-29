"""平台对外 base URL 解析（Runner 回调、connect 等同源逻辑）。"""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.platform import config as settings
from app.core.runner.runner_connect import resolve_public_base_url

INTERNAL_PLATFORM_BASE_KEY = "_platform_base_url"


def request_base_url(request: Request) -> str:
    """从 FastAPI 请求推导平台对外地址（与 /runner/connect 一致）。"""
    forwarded = request.headers.get("x-forwarded-proto")
    host = request.headers.get("host") or request.url.netloc
    scheme = forwarded or request.url.scheme
    return resolve_public_base_url(f"{scheme}://{host}")


async def resolve_platform_base_url_async(*, request_base_url: str | None = None) -> str:
    """
    解析 Runner 回调用的平台 base URL（async，可读 DB 配置）。
    优先：系统配置 MCP「平台对外地址」→ 环境变量 BASE_URL → 创建任务时的请求 Host。
    """
    from app.core.integration.mcp_config_service import get_mcp_runtime_config

    mcp_cfg = await get_mcp_runtime_config()
    platform_base = (mcp_cfg.base_url or "").strip().rstrip("/")
    if platform_base:
        return platform_base
    env_base = (settings.BASE_URL or "").strip().rstrip("/")
    if env_base:
        return env_base
    req_base = (request_base_url or "").strip().rstrip("/")
    if req_base:
        return req_base
    raise HTTPException(
        status_code=500,
        detail=(
            "无法确定平台回调地址。请在「系统配置 → MCP 配置」填写平台对外地址，"
            "或配置环境变量 BASE_URL，或经浏览器访问平台后再派发 Runner 任务"
        ),
    )


def resolve_platform_base_url(*, request_base_url: str | None = None) -> str:
    """同步解析（不含 DB 配置）；派发路径请用 resolve_platform_base_url_async。"""
    env_base = (settings.BASE_URL or "").strip().rstrip("/")
    if env_base:
        return env_base
    req_base = (request_base_url or "").strip().rstrip("/")
    if req_base:
        return req_base
    raise HTTPException(
        status_code=500,
        detail=(
            "无法确定平台回调地址。请在「系统配置 → MCP 配置」填写平台对外地址，"
            "或配置环境变量 BASE_URL"
        ),
    )


def stash_platform_base_url(cfg: dict | None, platform_base_url: str | None) -> dict[str, str | object]:
    """写入 Browser Lab config_json（内部字段，API 返回时会剥离）。"""
    out = dict(cfg or {})
    if platform_base_url:
        out[INTERNAL_PLATFORM_BASE_KEY] = platform_base_url.strip().rstrip("/")
    return out


def merge_job_platform_base_url(source_ref: dict | None, platform_base_url: str | None) -> dict:
    """写入 ui_agent_job.source_ref（内部字段，API 返回时会剥离）。"""
    ref = dict(source_ref or {})
    if platform_base_url:
        ref[INTERNAL_PLATFORM_BASE_KEY] = platform_base_url.strip().rstrip("/")
    return ref


def pop_internal_platform_base_url(data: dict | None) -> dict:
    """从对外 JSON 中移除内部回调地址字段。"""
    out = dict(data or {})
    out.pop(INTERNAL_PLATFORM_BASE_KEY, None)
    return out
