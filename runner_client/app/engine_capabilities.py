"""探测 Runner 客户端引擎能力（web / app）。"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from runner_client.app.engine_manager import repo_runner_dir
from runner_client.app.runtime_check import runner_subprocess_env, runner_venv_python
from runner_client.app.win_subprocess import hidden_runner_subprocess_kwargs

_HIDDEN_SUBPROCESS_KW = hidden_runner_subprocess_kwargs()
_adb_lock = threading.Lock()
_probe_cache: tuple[float, dict[str, Any]] | None = None
_PROBE_TTL_SEC = 10.0


def invalidate_app_toolchain_cache() -> None:
    """强制下次探测重新执行（用户点击「刷新检测」时）。"""
    global _probe_cache
    _probe_cache = None


def _resolve_adb() -> str:
    return shutil.which("adb") or ""


def _adb_subprocess_env(adb: str) -> dict[str, str]:
    env = os.environ.copy()
    adb_dir = str(Path(adb).resolve().parent)
    env["PATH"] = adb_dir + os.pathsep + env.get("PATH", "")
    return env


def _run_adb(args: list[str], *, timeout: float = 8) -> subprocess.CompletedProcess[str] | None:
    """串行调用 adb，隐藏控制台窗口，cwd 设为 platform-tools 目录。"""
    adb = _resolve_adb()
    if not adb:
        return None
    adb_dir = str(Path(adb).resolve().parent)
    try:
        with _adb_lock:
            return subprocess.run(
                [adb, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=adb_dir,
                env=_adb_subprocess_env(adb),
                **_HIDDEN_SUBPROCESS_KW,
            )
    except Exception:
        return None


def _probe_uiautomator2() -> bool:
    runner_dir = repo_runner_dir()
    venv_py = runner_venv_python(runner_dir)
    if venv_py.is_file():
        try:
            proc = subprocess.run(
                [str(venv_py), "-c", "import uiautomator2"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                env=runner_subprocess_env(runner_dir),
                **_HIDDEN_SUBPROCESS_KW,
            )
            return proc.returncode == 0
        except Exception:
            return False
    try:
        import uiautomator2  # noqa: F401

        return True
    except Exception:
        return False


def _probe_adb() -> bool:
    proc = _run_adb(["version"], timeout=5)
    return proc is not None and proc.returncode == 0


def list_adb_devices() -> list[dict[str, str]]:
    """解析 adb devices 输出，返回 serial/state 列表。"""
    proc = _run_adb(["devices"], timeout=8)
    if proc is None or proc.returncode != 0:
        return []
    devices: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        serial = serial.strip()
        if not serial:
            continue
        devices.append({"serial": serial, "state": state.strip()})
    return devices


def _pick_app_device(devices: list[dict[str, str]]) -> tuple[str, str]:
    """返回 (udid, connection)，优先 state=device。"""
    for item in devices:
        if item.get("state") == "device":
            serial = (item.get("serial") or "").strip()
            if serial:
                conn = "wifi" if (":" in serial or "_adb-tls-connect" in serial) else "usb"
                return serial, conn
    return "", ""


def probe_app_toolchain(*, force: bool = False) -> dict[str, Any]:
    """探测 App 工具链与本机 Android 设备（与用户是否勾选启用无关）。"""
    global _probe_cache
    now = time.monotonic()
    if not force and _probe_cache and (now - _probe_cache[0]) < _PROBE_TTL_SEC:
        return dict(_probe_cache[1])

    adb_ok = _probe_adb()
    u2_ok = _probe_uiautomator2()
    devices = list_adb_devices() if adb_ok else []
    app_udid, app_connection = _pick_app_device(devices) if adb_ok and u2_ok else ("", "")
    result = {
        "adb_ok": adb_ok,
        "u2_ok": u2_ok,
        "app_udid": app_udid,
        "app_connection": app_connection,
        "toolchain_ready": adb_ok and u2_ok and bool(app_udid),
        "devices": devices,
    }
    _probe_cache = (now, result)
    return dict(result)


def build_capabilities_from_toolchain(
    toolchain: dict[str, Any],
    *,
    enable_web: bool = True,
    enable_app: bool = False,
) -> dict[str, Any]:
    """由已探测的 toolchain 组装 connect/heartbeat 字段，避免重复 adb 调用。"""
    engine_types: list[str] = []
    app_platform = ""
    app_udid = ""
    app_connection = ""
    toolchain_status: dict[str, Any] = {}

    if enable_web:
        engine_types.append("web")
        toolchain_status["web"] = "ok"

    adb_ok = toolchain["adb_ok"]
    u2_ok = toolchain["u2_ok"]
    app_udid = toolchain["app_udid"]
    app_connection = toolchain["app_connection"]
    toolchain_status["adb"] = "ok" if adb_ok else "missing"
    toolchain_status["uiautomator2"] = "ok" if u2_ok else "missing"

    if enable_app and toolchain["toolchain_ready"]:
        engine_types.append("app")
        app_platform = "android"

    return {
        "runner_engine_types": engine_types,
        "app_platform": app_platform,
        "app_udid": app_udid,
        "app_connection": app_connection,
        "toolchain_status": toolchain_status,
    }


def detect_runner_capabilities(
    *,
    enable_web: bool = True,
    enable_app: bool = False,
    force_probe: bool = False,
) -> dict[str, Any]:
    """返回 connect/heartbeat 所需的引擎能力字段（按用户勾选的引擎过滤）。"""
    toolchain = probe_app_toolchain(force=force_probe)
    return build_capabilities_from_toolchain(
        toolchain,
        enable_web=enable_web,
        enable_app=enable_app,
    )
