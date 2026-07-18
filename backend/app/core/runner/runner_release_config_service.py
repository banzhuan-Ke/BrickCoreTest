"""执行器安装包发布配置（DB 优先，环境变量 RUNNER_CLIENT_DOWNLOAD_URL 兜底）"""
from __future__ import annotations

from typing import Any

from app.core.platform import config as settings
from app.core.runner.runner_release import runner_package_path
from app.models.sys import SystemRunnerReleaseConfig


async def resolve_external_download() -> tuple[str, str, str]:
    """返回 (url, label, source: platform|env|none)"""
    row = await SystemRunnerReleaseConfig.first()
    if row:
        url = (row.external_download_url or "").strip()
        if url:
            label = (row.external_download_label or "网盘下载").strip() or "网盘下载"
            return url, label, "platform"
    env_url = (settings.RUNNER_CLIENT_DOWNLOAD_URL or "").strip()
    if env_url:
        return env_url, "网盘下载", "env"
    return "", "网盘下载", "none"


def resolve_platform_api_download_url(request_base_url: str = "") -> str:
    base = (request_base_url or settings.BASE_URL or "").rstrip("/")
    if base:
        return f"{base}/runner/client-download"
    return ""


async def enrich_release_info(info: dict[str, Any], request_base_url: str = "") -> dict[str, Any]:
    """合并本地包与外链下载信息，供 /runner/version 与 /runner/client-release 使用。"""
    ext_url, ext_label, ext_source = await resolve_external_download()
    local_available = bool(info.get("package_available"))

    info["platform_package_available"] = local_available
    info["external_download_url"] = ext_url
    info["external_download_available"] = bool(ext_url)
    info["external_download_label"] = ext_label
    info["download_config_source"] = ext_source

    if ext_url:
        info["runner_client_download_url"] = ext_url
    elif local_available:
        info["runner_client_download_url"] = resolve_platform_api_download_url(request_base_url)
    else:
        info["runner_client_download_url"] = ""

    base = (request_base_url or settings.BASE_URL or "").rstrip("/")
    if info.get("perf_package_available") and base:
        info["perf_package_download_url"] = f"{base}/runner/perf-client-download?platform=win"
    else:
        info["perf_package_download_url"] = ""
    if info.get("perf_package_mac_available") and base:
        info["perf_package_mac_download_url"] = f"{base}/runner/perf-client-download?platform=mac"
    else:
        info["perf_package_mac_download_url"] = ""

    return info


async def get_runner_release_config_for_admin() -> dict[str, Any]:
    row = await SystemRunnerReleaseConfig.first()
    local_path = runner_package_path()
    local_available = local_path.is_file()
    from app.core.runner.runner_release import perf_package_path

    perf_win = perf_package_path("win")
    perf_mac = perf_package_path("mac")
    perf_win_ok = perf_win.is_file()
    perf_mac_ok = perf_mac.is_file()
    common = {
        "platform_package_available": local_available,
        "platform_package_size_bytes": local_path.stat().st_size if local_available else 0,
        "perf_package_available": perf_win_ok,
        "perf_package_size_bytes": perf_win.stat().st_size if perf_win_ok else 0,
        "perf_package_mac_available": perf_mac_ok,
        "perf_package_mac_size_bytes": perf_mac.stat().st_size if perf_mac_ok else 0,
    }
    if not row:
        env_url = (settings.RUNNER_CLIENT_DOWNLOAD_URL or "").strip()
        return {
            "external_download_url": env_url,
            "external_download_label": "网盘下载",
            "using_env_fallback": bool(env_url),
            **common,
            "update_by": "",
            "update_time": "",
        }
    return {
        "id": row.id,
        "external_download_url": row.external_download_url or "",
        "external_download_label": row.external_download_label or "网盘下载",
        "using_env_fallback": False,
        **common,
        "update_by": row.update_by or "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }


async def save_runner_release_config(
    *,
    external_download_url: str,
    external_download_label: str,
    username: str,
) -> dict[str, Any]:
    url = (external_download_url or "").strip()
    label = (external_download_label or "网盘下载").strip() or "网盘下载"
    row = await SystemRunnerReleaseConfig.first()
    if row:
        row.external_download_url = url
        row.external_download_label = label
        row.update_by = username
        await row.save()
    else:
        await SystemRunnerReleaseConfig.create(
            external_download_url=url,
            external_download_label=label,
            update_by=username,
        )
    return await get_runner_release_config_for_admin()
