"""下载平台发布的 Runner 客户端 zip（需已登录 token）"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable

import requests

from runner_client.app.api_client import BrickCoreApi, DEFAULT_TIMEOUT


def default_download_path(filename: str = "BrickCoreRunner.zip") -> Path:
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads / filename


def download_client_package(
    api: BrickCoreApi,
    dest: Path | None = None,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """将安装包下载到 dest；返回最终文件路径。"""
    if not api.user_token:
        raise ValueError("请先登录平台后再下载安装包")
    dest = dest or default_download_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = api._url("/runner/client-download")
    with requests.get(
        url,
        headers={"Authorization": f"Bearer {api.user_token}"},
        stream=True,
        timeout=DEFAULT_TIMEOUT * 4,
    ) as resp:
        if resp.status_code != 200:
            raise RuntimeError(BrickCoreApi._extract_error(resp))
        total = int(resp.headers.get("content-length") or 0)
        received = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                received += len(chunk)
                if progress and total:
                    progress(received, total)
    if dest.stat().st_size < 1024:
        raise RuntimeError("下载文件过小，可能安装包尚未上传到服务器")
    return dest


def peek_zip_root_name(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")]
        if not names:
            return ""
        return names[0].split("/")[0]
