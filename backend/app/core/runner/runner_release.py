"""Runner / 压测精简包发布信息（zip 放置于 static/runner/）"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.platform import config as settings
from app.core.runner.runner_notices import merge_notices_into_release

PACKAGE_FILENAME = os.getenv("RUNNER_CLIENT_PACKAGE_FILENAME", "BrickCoreRunner.zip")
PERF_PACKAGE_FILENAME = os.getenv("PERF_PACKAGE_FILENAME", "BrickCorePerf.zip")
PERF_PACKAGE_FILENAME_MAC = os.getenv("PERF_PACKAGE_FILENAME_MAC", "BrickCorePerf-mac.zip")


def runner_package_dir() -> Path:
    path = Path(settings.STATIC_DIR) / "runner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runner_package_path() -> Path:
    return runner_package_dir() / PACKAGE_FILENAME


def perf_package_path(platform: str = "win") -> Path:
    name = PERF_PACKAGE_FILENAME_MAC if platform == "mac" else PERF_PACKAGE_FILENAME
    return runner_package_dir() / name


def build_client_release_info(request_base_url: str = "") -> dict[str, Any]:
    package = runner_package_path()
    available = package.is_file()
    size_bytes = package.stat().st_size if available else 0
    perf_win = perf_package_path("win")
    perf_mac = perf_package_path("mac")
    perf_win_ok = perf_win.is_file()
    perf_mac_ok = perf_mac.is_file()
    base = {
        "runner_engine_version": settings.RUNNER_ENGINE_VERSION,
        "runner_client_version_min": settings.RUNNER_CLIENT_VERSION_MIN,
        "runner_client_version_latest": settings.RUNNER_CLIENT_VERSION_LATEST,
        "runner_client_download_url": "",
        "package_filename": PACKAGE_FILENAME,
        "package_available": available,
        "package_size_bytes": size_bytes,
        "package_upload_hint": str(runner_package_dir()),
        "platform_package_available": available,
        "external_download_url": "",
        "external_download_available": False,
        "external_download_label": "网盘下载",
        "download_config_source": "none",
        "storage_mode": "presigned" if settings.STORAGE_TYPE.lower() == "minio" else settings.STORAGE_TYPE,
        "middleware_isolation": settings.RUNNER_MIDDLEWARE_ISOLATION,
        "perf_package_filename": PERF_PACKAGE_FILENAME,
        "perf_package_available": perf_win_ok,
        "perf_package_size_bytes": perf_win.stat().st_size if perf_win_ok else 0,
        "perf_package_download_url": "",
        "perf_package_mac_filename": PERF_PACKAGE_FILENAME_MAC,
        "perf_package_mac_available": perf_mac_ok,
        "perf_package_mac_size_bytes": perf_mac.stat().st_size if perf_mac_ok else 0,
        "perf_package_mac_download_url": "",
    }
    return merge_notices_into_release(base)
