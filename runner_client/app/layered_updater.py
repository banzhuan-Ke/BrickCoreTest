"""分层增量：下载、解密、staging，并拉起覆盖助手。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests

from runner_client.app.api_client import BrickCoreApi, DEFAULT_TIMEOUT
from runner_client.app.bcpack import (
    decrypt_bcpack_to_zip,
    read_installed_package_version,
    select_update_plan,
    sha256_file,
)
from runner_client.app.engine_manager import app_root_dir
from runner_client.app.runtime_check import is_packaged_app


ProgressCb = Callable[[str, int, int], None]


def install_root() -> Path:
    return app_root_dir()


def assert_safe_install_root(root: Path | None = None) -> Path:
    """禁止在源码开发树误覆盖；仅允许打包安装目录。"""
    root = (root or install_root()).resolve()
    exe = root / "BrickCoreRunner.exe"
    if is_packaged_app():
        if not exe.is_file():
            raise RuntimeError(f"打包目录缺少 BrickCoreRunner.exe：{root}")
        return root
    # 开发模式：仅当明确是 dist 安装布局时才允许（含 exe + runner + VERSION）
    if exe.is_file() and (root / "runner").is_dir() and (root / "VERSION.txt").is_file():
        return root
    raise RuntimeError(
        "当前不是打包安装目录，已禁止一键增量覆盖（避免误改源码仓）。"
        "请使用正式 BrickCoreRunner 安装包，或改下完整 zip 手动覆盖。"
    )


def package_version(*, baked_fallback: str) -> str:
    return read_installed_package_version(install_root(), fallback=baked_fallback)


def download_url_to_file(
    url: str,
    dest: Path,
    *,
    headers: dict[str, str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=headers or {}, stream=True, timeout=DEFAULT_TIMEOUT * 8) as resp:
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
    if dest.stat().st_size < 64:
        dest.unlink(missing_ok=True)
        raise RuntimeError("下载文件过小，增量包可能不存在")
    return dest


def download_patch_channel(
    api: BrickCoreApi,
    channel: Mapping[str, Any],
    dest_dir: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    if not api.user_token:
        raise ValueError("请先登录平台后再下载增量包")
    channel_id = str(channel.get("id") or "").strip()
    if not channel_id:
        raise ValueError("增量通道缺少 id")
    filename = str(channel.get("filename") or f"{channel_id}.bcpack")
    # 防止路径穿越
    filename = Path(filename).name
    if not filename or filename in {".", ".."}:
        raise ValueError("非法增量文件名")
    dest = dest_dir / filename
    url = api._url(f"/runner/client-patch/{channel_id}")
    download_url_to_file(
        url,
        dest,
        headers={"Authorization": f"Bearer {api.user_token}"},
        progress=progress,
    )
    expect = str(channel.get("sha256") or "").strip().lower()
    if expect:
        actual = sha256_file(dest).lower()
        if actual != expect:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"增量包校验失败：{filename}")
    return dest


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """防 zip slip：成员路径必须落在 dest_dir 内。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise RuntimeError(f"增量包含非法路径：{info.filename}")
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
                raise RuntimeError(f"增量包路径穿越：{info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def extract_bcpack_to_staging(bcpack_path: Path, staging_dir: Path) -> Path:
    blob = bcpack_path.read_bytes()
    zip_bytes = decrypt_bcpack_to_zip(blob)
    if len(zip_bytes) < 32:
        raise RuntimeError("解密后的增量内容过小")
    staging_dir.mkdir(parents=True, exist_ok=True)
    zip_path = staging_dir / (bcpack_path.stem + ".zip")
    zip_path.write_bytes(zip_bytes)
    extract_root = staging_dir / "files"
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    _safe_extract_zip(zip_path, extract_root)
    zip_path.unlink(missing_ok=True)
    return extract_root


def merge_staging_layers(layer_dirs: Sequence[Path], merged: Path) -> Path:
    if merged.exists():
        shutil.rmtree(merged, ignore_errors=True)
    merged.mkdir(parents=True, exist_ok=True)
    for layer in layer_dirs:
        for path in layer.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(layer)
            dest = merged / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    return merged


def write_apply_helper_script(
    *,
    install_dir: Path,
    staging_files: Path,
    main_exe: Path,
    wait_pid: int,
    script_path: Path,
    cleanup_dir: Path | None = None,
) -> Path:
    """生成 cmd 助手：等待主进程退出 → 覆盖 → 重启。

    script_path 应放在 cleanup_dir 之外或同级临时目录，避免覆盖过程删掉正在执行的脚本。
    """
    install_s = str(install_dir.resolve()).replace('"', "")
    staging_s = str(staging_files.resolve()).replace('"', "")
    exe_s = str(main_exe.resolve()).replace('"', "")
    cleanup_s = str((cleanup_dir or staging_files.parent).resolve()).replace('"', "")
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f"set \"INSTALL={install_s}\"",
        f"set \"STAGING={staging_s}\"",
        f"set \"EXE={exe_s}\"",
        f"set \"CLEANUP={cleanup_s}\"",
        f"set \"WAITPID={wait_pid}\"",
        "echo BrickCore updater: waiting for PID %WAITPID% ...",
        "set /a _tries=0",
        ":waitloop",
        "set /a _tries+=1",
        "if %_tries% GEQ 120 (",
        "  echo Timeout waiting for client exit.",
        "  pause",
        "  exit /b 1",
        ")",
        "tasklist /FI \"PID eq %WAITPID%\" 2>nul | find \"%WAITPID%\" >nul",
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto waitloop",
        ")",
        "timeout /t 1 /nobreak >nul",
        "echo Applying update files ...",
        "robocopy \"%STAGING%\" \"%INSTALL%\" /E /IS /IT /R:2 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np",
        "set \"RC=%ERRORLEVEL%\"",
        "if %RC% GEQ 8 (",
        "  echo robocopy failed with %RC%",
        "  pause",
        "  exit /b %RC%",
        ")",
        "echo Restarting client ...",
        # /D 保证工作目录正确；勿在本脚本内 del %~f0，否则 cmd 读后续行会报「找不到批处理文件」
        "start \"\" /D \"%INSTALL%\" \"%EXE%\"",
        "timeout /t 2 /nobreak >nul",
        "rmdir /s /q \"%CLEANUP%\" 2>nul",
        "exit /b 0",
        "",
    ]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\r\n".join(lines), encoding="gbk", errors="replace")
    return script_path


def launch_apply_helper(script_path: Path) -> None:
    # 仅 CREATE_NEW_CONSOLE：避免与 DETACHED_PROCESS 组合导致助手无法拉起
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    subprocess.Popen(
        ["cmd.exe", "/c", str(script_path)],
        cwd=str(script_path.parent),
        creationflags=creationflags,
        close_fds=True,
    )


def _filter_available_channels(
    plan_channels: Sequence[Mapping[str, Any]],
    version_info: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    summary = version_info.get("update_channels")
    if not isinstance(summary, list) or not summary:
        return list(plan_channels)
    avail = {
        str(c.get("id") or ""): c
        for c in summary
        if isinstance(c, Mapping) and c.get("available")
    }
    if not avail:
        raise RuntimeError("服务器增量通道均不可用，请改用完整安装包")
    out: list[Mapping[str, Any]] = []
    for ch in plan_channels:
        cid = str(ch.get("id") or "")
        meta = avail.get(cid)
        if not meta:
            raise RuntimeError(f"增量通道 {cid} 在服务器上不可用，请改用完整安装包")
        merged = dict(ch)
        merged.update({k: meta[k] for k in ("filename", "sha256", "size") if meta.get(k)})
        out.append(merged)
    return out


def prepare_layered_update(
    api: BrickCoreApi,
    version_info: Mapping[str, Any],
    *,
    baked_gui_version: str,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """下载并解密增量到 staging，返回 apply 所需路径；若需整包则 action=full。"""
    install = assert_safe_install_root()
    current = package_version(baked_fallback=baked_gui_version)
    manifest = version_info.get("update_manifest")
    if not isinstance(manifest, dict):
        manifest = None
    plan = select_update_plan(current, manifest, gui_version=baked_gui_version)
    if plan["action"] == "none":
        return plan
    if plan["action"] != "patch" or not plan.get("channels"):
        return {**plan, "action": "full"}

    try:
        channels = _filter_available_channels(plan["channels"], version_info)
    except RuntimeError as exc:
        return {"action": "full", "channels": [], "reason": str(exc)}

    work = Path(tempfile.mkdtemp(prefix="BrickCoreUpdate_"))
    # helper 脚本放在 work 外，避免清理 staging 时误伤正在执行的 cmd
    helper_dir = Path(tempfile.mkdtemp(prefix="BrickCoreUpdater_"))
    layer_dirs: list[Path] = []
    try:
        for idx, channel in enumerate(channels):
            label = str(channel.get("id") or f"ch{idx}")
            if progress:
                progress(f"下载 {label}", 0, 1)

            def _cb(received: int, total: int, _label=label) -> None:
                if progress:
                    progress(f"下载 {_label}", received, total)

            pack = download_patch_channel(api, channel, work / "packs", progress=_cb)
            extracted = extract_bcpack_to_staging(pack, work / f"layer_{label}")
            layer_dirs.append(extracted)
        merged = merge_staging_layers(layer_dirs, work / "merged")
        if not any(merged.rglob("*")):
            raise RuntimeError("增量解压结果为空")
        helper = write_apply_helper_script(
            install_dir=install,
            staging_files=merged,
            main_exe=install / "BrickCoreRunner.exe",
            wait_pid=os.getpid(),
            script_path=helper_dir / "apply_update.cmd",
            cleanup_dir=work,
        )
        return {
            **plan,
            "channels": list(channels),
            "work_dir": str(work),
            "helper_dir": str(helper_dir),
            "staging_files": str(merged),
            "helper_script": str(helper),
            "install_dir": str(install),
            "current_version": current,
        }
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(helper_dir, ignore_errors=True)
        raise
