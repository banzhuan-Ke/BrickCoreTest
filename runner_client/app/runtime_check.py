"""打包版 Runner 运行时自检与 Playwright 浏览器补装"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def is_packaged_app() -> bool:
    return getattr(sys, "frozen", False)


def playwright_browsers_dir(runner_dir: Path) -> Path:
    return runner_dir / "browsers"


def system_playwright_browsers_dir() -> Path | None:
    """playwright install 默认缓存目录（开发模式常用）"""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        return Path(local) / "ms-playwright" if local else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def runner_venv_python(runner_dir: Path) -> Path:
    if os.name == "nt":
        return runner_dir / "venv" / "Scripts" / "python.exe"
    return runner_dir / "venv" / "bin" / "python"


def chromium_installed(browsers_dir: Path) -> bool:
    if not browsers_dir.is_dir():
        return False
    if os.name == "nt":
        return any(browsers_dir.glob("chromium-*/chrome-win/chrome.exe"))
    if sys.platform == "darwin":
        return any(
            browsers_dir.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")
        )
    return any(browsers_dir.glob("chromium-*/chrome-linux/chrome"))


def playwright_browsers_path_for_engine(runner_dir: Path) -> str | None:
    """
    返回应注入 PLAYWRIGHT_BROWSERS_PATH 的路径。
    开发模式若浏览器在系统默认目录，返回 None（让 Playwright 自行查找）。
    """
    bundled = playwright_browsers_dir(runner_dir)
    if chromium_installed(bundled):
        return str(bundled)
    if is_packaged_app():
        return str(bundled)
    return None


def diagnose_runner_runtime(runner_dir: Path) -> tuple[bool, str, bool]:
    """
    返回 (是否就绪, 说明, 是否可自动修复)。
    开发模式：venv + 系统默认 ms-playwright 有 Chromium 即视为就绪。
    """
    if not (runner_dir / "main.py").is_file():
        return False, f"找不到 Runner 引擎目录：{runner_dir}", False

    py = runner_venv_python(runner_dir)
    if not py.is_file():
        if is_packaged_app():
            return (
                False,
                "打包版缺少 runner\\venv 运行时，请重新下载官方 BrickCoreRunner 安装包。",
                False,
            )
        return False, "开发模式请先在 runner 目录创建 venv 并安装依赖。", False

    if playwright_browsers_path_for_engine(runner_dir):
        return True, "", False

    system_dir = system_playwright_browsers_dir()
    if not is_packaged_app() and system_dir and chromium_installed(system_dir):
        return True, "", False

    if is_packaged_app():
        return False, "Playwright Chromium 浏览器未安装或文件不完整。", True

    return (
        False,
        "请先在 runner 目录执行（需激活 venv）：\nplaywright install chromium",
        False,
    )


def repair_playwright_browsers(
    runner_dir: Path,
    on_output: Callable[[str], None] | None = None,
) -> None:
    """在 runner venv 中安装 Chromium 到 runner/browsers"""
    py = runner_venv_python(runner_dir)
    if not py.is_file():
        raise RuntimeError("Runner Python 运行时不可用，无法补装浏览器")

    browsers = playwright_browsers_dir(runner_dir)
    browsers.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)

    cmd = [str(py), "-m", "playwright", "install", "chromium"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(runner_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if on_output:
            on_output(line.rstrip("\n"))
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"playwright install 失败，退出码 {code}")
    if not chromium_installed(browsers):
        raise RuntimeError("浏览器安装完成但未检测到 Chromium，请检查网络或磁盘空间")


def write_runtime_manifest(runner_dir: Path, *, python_version: str = "") -> None:
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "python_version": python_version,
        "playwright_browsers_path": "browsers",
        "venv_path": "venv",
    }
    (runner_dir / ".runtime-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_runtime_manifest(runner_dir: Path) -> dict:
    path = runner_dir / ".runtime-manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
