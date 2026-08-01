"""Runner / 压测精简包发布信息（zip 放置于 static/runner/）"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.platform import config as settings
from app.core.runner.runner_notices import merge_notices_into_release

PACKAGE_FILENAME = os.getenv("RUNNER_CLIENT_PACKAGE_FILENAME", "BrickCoreRunner.zip")
PERF_PACKAGE_FILENAME = os.getenv("PERF_PACKAGE_FILENAME", "BrickCorePerf.zip")
PERF_PACKAGE_FILENAME_MAC = os.getenv("PERF_PACKAGE_FILENAME_MAC", "BrickCorePerf-mac.zip")
UPDATE_MANIFEST_FILENAME = "update_manifest.json"


def runner_package_dir() -> Path:
    path = Path(settings.STATIC_DIR) / "runner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runner_package_path() -> Path:
    return runner_package_dir() / PACKAGE_FILENAME


def runner_patches_dir() -> Path:
    path = runner_package_dir() / "patches"
    path.mkdir(parents=True, exist_ok=True)
    return path


def update_manifest_path() -> Path:
    return runner_patches_dir() / UPDATE_MANIFEST_FILENAME


def perf_package_path(platform: str = "win") -> Path:
    name = PERF_PACKAGE_FILENAME_MAC if platform == "mac" else PERF_PACKAGE_FILENAME
    return runner_package_dir() / name


def load_update_manifest() -> dict[str, Any] | None:
    path = update_manifest_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def resolve_patch_file(channel_id: str) -> tuple[Path, str] | None:
    """根据通道 id 解析 patches 目录下的 .bcpack。"""
    cid = (channel_id or "").strip().lower()
    if not cid or "/" in cid or "\\" in cid or ".." in cid:
        return None
    manifest = load_update_manifest()
    filename = ""
    if isinstance(manifest, dict):
        for ch in manifest.get("channels") or []:
            if not isinstance(ch, dict):
                continue
            if str(ch.get("id") or "").strip().lower() == cid:
                filename = str(ch.get("filename") or "").strip()
                break
    if not filename:
        # 必须由 update_manifest.json 指明文件名，避免无清单时按字符串排序误选版本
        return None
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    path = runner_patches_dir() / filename
    if not path.is_file():
        return None
    if path.suffix.lower() != ".bcpack":
        return None
    # 必须落在 patches 目录内
    try:
        path.resolve().relative_to(runner_patches_dir().resolve())
    except ValueError:
        return None
    return path, filename


def patch_channels_summary() -> list[dict[str, Any]]:
    manifest = load_update_manifest()
    if not isinstance(manifest, dict):
        return []
    out: list[dict[str, Any]] = []
    for ch in manifest.get("channels") or []:
        if not isinstance(ch, dict):
            continue
        filename = str(ch.get("filename") or "")
        path = runner_patches_dir() / filename if filename else None
        available = bool(path and path.is_file())
        size = path.stat().st_size if available and path else int(ch.get("size") or 0)
        out.append(
            {
                "id": ch.get("id"),
                "to_version": ch.get("to_version"),
                "filename": filename,
                "size": size,
                "sha256": ch.get("sha256") or "",
                "layers": ch.get("layers") or [],
                "encrypted": bool(ch.get("encrypted", True)),
                "requires_gui": bool(ch.get("requires_gui")),
                "available": available,
            }
        )
    return out


def build_client_release_info(request_base_url: str = "") -> dict[str, Any]:
    package = runner_package_path()
    available = package.is_file()
    size_bytes = package.stat().st_size if available else 0
    perf_win = perf_package_path("win")
    perf_mac = perf_package_path("mac")
    perf_win_ok = perf_win.is_file()
    perf_mac_ok = perf_mac.is_file()
    manifest = load_update_manifest()
    channels = patch_channels_summary()
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
        "update_manifest": manifest,
        "update_channels": channels,
        "update_patches_available": any(c.get("available") for c in channels),
        "update_patches_hint": str(runner_patches_dir()),
    }
    return merge_notices_into_release(base)
