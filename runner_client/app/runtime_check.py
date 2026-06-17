"""打包版 Runner 运行时自检与 Playwright 浏览器补装"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from runner_client.app.win_subprocess import hidden_runner_subprocess_kwargs

RepairKind = Literal["playwright", "deps"] | None

_HIDDEN_SUBPROCESS_KW = hidden_runner_subprocess_kwargs()


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


def runner_venv_pip(runner_dir: Path) -> Path:
    if os.name == "nt":
        return runner_dir / "venv" / "Scripts" / "pip.exe"
    return runner_dir / "venv" / "bin" / "pip"


def _parse_pyvenv_meta(cfg_path: Path) -> tuple[str, str]:
    version = "3.11.5"
    version_info = "3.11.5.final.0"
    if not cfg_path.is_file():
        return version, version_info
    try:
        for line in cfg_path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            key = key.strip().lower()
            value = value.strip()
            if key == "version" and value:
                version = value
            elif key == "version_info" and value:
                version_info = value
    except OSError:
        pass
    return version, version_info


def portable_pyvenv_cfg_text(venv_dir: Path, *, version: str = "3.11.5", version_info: str = "3.11.5.final.0") -> str:
    venv_dir = venv_dir.resolve()
    return (
        f"home = {venv_dir}\n"
        "implementation = CPython\n"
        f"version_info = {version_info}\n"
        f"version = {version}\n"
        "include-system-site-packages = false\n"
    )


def ensure_runner_venv_home(runner_dir: Path) -> None:
    """打包版将 pyvenv.cfg 规范为 portable 5 行；开发模式保留系统 Python 绑定的 venv。"""
    if not is_packaged_app():
        return
    venv_dir = (runner_dir / "venv").resolve()
    cfg_path = venv_dir / "pyvenv.cfg"
    version, version_info = _parse_pyvenv_meta(cfg_path)
    desired = portable_pyvenv_cfg_text(venv_dir, version=version, version_info=version_info)
    try:
        current = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.is_file() else ""
    except OSError:
        return
    home_mismatch = True
    if cfg_path.is_file():
        try:
            for line in current.splitlines():
                if line.strip().lower().startswith("home"):
                    home = line.split("=", 1)[1].strip()
                    if home:
                        home_mismatch = Path(home).resolve() != venv_dir
                    break
        except OSError:
            home_mismatch = True
    if current == desired and not home_mismatch:
        return
    try:
        cfg_path.write_text(desired, encoding="utf-8")
    except OSError:
        return


def runner_subprocess_env(runner_dir: Path) -> dict[str, str]:
    """与 EngineManager 启动子进程一致：优先从 runner\\venv 加载 DLL / site-packages。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    venv_dir = (runner_dir / "venv").resolve()
    path_prefix: list[str] = []
    for sub in (venv_dir, venv_dir / "Scripts", venv_dir / "DLLs"):
        if sub.is_dir():
            path_prefix.append(str(sub))
    if path_prefix:
        env["PATH"] = os.pathsep.join(path_prefix + [env.get("PATH", "")])
    return env


# (import 名, 说明)
RUNNER_REQUIRED_IMPORTS: tuple[tuple[str, str], ...] = (
    ("jsonpath_ng", "jsonpath-ng（数据工厂 JSON 提取）"),
    ("pika", "pika（消息队列）"),
    ("redis", "redis"),
    ("playwright", "playwright"),
    ("greenlet", "greenlet（Playwright 浏览器引擎依赖）"),
)

PERF_REQUIRED_IMPORTS: tuple[tuple[str, str], ...] = (
    ("httpx", "httpx（压测 HTTP 客户端）"),
    ("numpy", "numpy（压测统计）"),
)


_IMPORT_PROBE_CODE = r"""
import importlib
import sys
checks = ("jsonpath_ng", "pika", "redis", "playwright", "greenlet")
failed = []
for mod in checks:
    try:
        importlib.import_module(mod)
    except Exception as exc:
        failed.append(f"{mod}:{exc}")
if failed:
    print("\n".join(failed), file=sys.stderr)
    raise SystemExit(1)
import greenlet._greenlet  # noqa: F401
"""

_PERF_IMPORT_PROBE_CODE = r"""
import importlib
import sys
checks = ("httpx", "numpy")
failed = []
for mod in checks:
    try:
        importlib.import_module(mod)
    except Exception as exc:
        failed.append(f"{mod}:{exc}")
if failed:
    print("\n".join(failed), file=sys.stderr)
    raise SystemExit(1)
"""


def _decode_subprocess_output(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def _run_runner_python_script(
    runner_dir: Path,
    code: str,
    *,
    timeout: int = 90,
) -> subprocess.CompletedProcess[bytes]:
    py = runner_venv_python(runner_dir)
    return subprocess.run(
        [str(py), "-c", code],
        cwd=str(runner_dir),
        env=runner_subprocess_env(runner_dir),
        capture_output=True,
        timeout=timeout,
        **_HIDDEN_SUBPROCESS_KW,
    )


def runner_python_can_import(runner_dir: Path, module: str) -> bool:
    py = runner_venv_python(runner_dir)
    if not py.is_file():
        return False
    try:
        proc = _run_runner_python_script(
            runner_dir,
            f"import importlib; importlib.import_module({module!r})",
            timeout=60,
        )
        return proc.returncode == 0
    except Exception:
        return False


def probe_runner_imports(runner_dir: Path) -> tuple[list[tuple[str, str]], str]:
    return _probe_imports(runner_dir, RUNNER_REQUIRED_IMPORTS, _IMPORT_PROBE_CODE)


def probe_perf_imports(runner_dir: Path) -> tuple[list[tuple[str, str]], str]:
    return _probe_imports(runner_dir, PERF_REQUIRED_IMPORTS, _PERF_IMPORT_PROBE_CODE)


def _probe_imports(
    runner_dir: Path,
    required: tuple[tuple[str, str], ...],
    probe_code: str,
) -> tuple[list[tuple[str, str]], str]:
    """
    一次性探测 runner venv 关键依赖。
    返回 (缺失列表, 诊断详情)。
    """
    ensure_runner_venv_home(runner_dir)
    py = runner_venv_python(runner_dir)
    if not py.is_file():
        return list(required), f"找不到 Runner Python：{py}"

    try:
        proc = _run_runner_python_script(runner_dir, probe_code, timeout=90)
    except subprocess.TimeoutExpired:
        return list(required), "Runner Python 依赖检查超时"
    except Exception as exc:
        return list(required), f"Runner Python 无法执行：{exc}"

    if proc.returncode == 0:
        return [], ""

    detail_parts: list[str] = []
    stderr = _decode_subprocess_output(proc.stderr)
    stdout = _decode_subprocess_output(proc.stdout)
    if stderr:
        detail_parts.append(stderr)
    if stdout:
        detail_parts.append(stdout)

    failed_modules: set[str] = set()
    for line in (stderr + "\n" + stdout).splitlines():
        mod = line.split(":", 1)[0].strip()
        if mod in {m for m, _ in required}:
            failed_modules.add(mod)

    if not failed_modules:
        for module, _label in required:
            if not runner_python_can_import(runner_dir, module):
                failed_modules.add(module)

    label_map = dict(required)
    missing = [(m, label_map[m]) for m, _ in required if m in failed_modules]
    if not missing:
        missing = list(required)
    detail = "\n".join(detail_parts) if detail_parts else "未知导入错误"
    if proc.returncode not in (0, 1) and not detail_parts:
        detail = f"Runner Python 退出码 {proc.returncode}"
    return missing, detail


def missing_runner_imports(runner_dir: Path) -> list[tuple[str, str]]:
    missing, _ = probe_runner_imports(runner_dir)
    return missing


def format_runner_deps_error(
    runner_dir: Path,
    missing: list[tuple[str, str]],
    *,
    detail: str = "",
) -> str:
    lines = "\n".join(f"  · {label}" for _, label in missing)
    portable_hint = non_portable_venv_hint(runner_dir)
    detail_block = f"\n\n诊断信息：\n{detail}" if detail else ""

    if is_packaged_app():
        return (
            f"Runner 引擎依赖不完整（{('、'.join(label for _, label in missing))}）。\n"
            f"{lines}{detail_block}{portable_hint}\n\n"
            "安装包应已内置完整 runner\\venv，请勿在本机手动 pip。\n"
            "请确认：\n"
            "  1. 解压的是完整 zip（含 BrickCoreRunner.exe、_internal、runner 文件夹）\n"
            "  2. 路径尽量不含中文与空格\n"
            "  3. 重新下载最新 BrickCoreRunner 安装包并整目录覆盖"
        )

    return (
        f"Runner 引擎 Python 依赖不完整：\n{lines}{detail_block}\n\n"
        "请在 runner 目录执行：\n"
        "  venv\\Scripts\\python.exe -m pip install -r requirements.txt\n\n"
        "或重新运行 runner_client\\start-client.bat（会自动补装）。"
    )


def non_portable_venv_hint(runner_dir: Path) -> str:
    """旧版安装包 venv 仍指向打包机 Python 路径时给出明确提示。"""
    cfg = runner_dir / "venv" / "pyvenv.cfg"
    if not cfg.is_file():
        return ""
    try:
        home = ""
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().lower().startswith("home"):
                home = line.split("=", 1)[1].strip()
                break
        if not home:
            return ""
        home_path = Path(home)
        venv_dir = (runner_dir / "venv").resolve()
        if home_path.resolve() == venv_dir:
            return ""
        if home_path.is_dir() and (home_path / "python.exe").is_file():
            return ""
        return (
            f"\n\n检测到 runner\\venv 仍绑定打包机路径：{home}\n"
            "本机无该 Python 时，会误报上述依赖缺失。\n"
            "请重新下载最新 BrickCoreRunner 安装包（需含 portable-python-venv）。"
        )
    except Exception:
        return ""


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


def diagnose_runner_runtime(runner_dir: Path) -> tuple[bool, str, RepairKind]:
    """
    返回 (是否就绪, 说明, 可自动修复类型)。
    开发模式：venv + 系统默认 ms-playwright 有 Chromium 即视为就绪。
    """
    if not (runner_dir / "main.py").is_file():
        return False, f"找不到 Runner 引擎目录：{runner_dir}", None

    ensure_runner_venv_home(runner_dir)

    py = runner_venv_python(runner_dir)
    if not py.is_file():
        if is_packaged_app():
            return (
                False,
                "打包版缺少 runner\\venv 运行时，请重新下载官方 BrickCoreRunner 安装包。",
                None,
            )
        return False, "开发模式请先在 runner 目录创建 venv 并安装依赖。", "deps"

    missing, detail = probe_runner_imports(runner_dir)
    if missing:
        if is_packaged_app():
            return False, format_runner_deps_error(runner_dir, missing, detail=detail), None
        return False, format_runner_deps_error(runner_dir, missing, detail=detail), "deps"

    if playwright_browsers_path_for_engine(runner_dir):
        return True, "", None

    system_dir = system_playwright_browsers_dir()
    if not is_packaged_app() and system_dir and chromium_installed(system_dir):
        return True, "", None

    if is_packaged_app():
        return False, "Playwright Chromium 浏览器未安装或文件不完整。", "playwright"

    return (
        False,
        "请先在 runner 目录执行（需激活 venv）：\nplaywright install chromium",
        None,
    )


def diagnose_perf_runtime(runner_dir: Path) -> tuple[bool, str, RepairKind]:
    """压测 Worker 运行时检查（httpx / numpy）。"""
    if not (runner_dir / "perf_worker.py").is_file():
        return False, f"找不到压测脚本：{runner_dir / 'perf_worker.py'}", None

    ensure_runner_venv_home(runner_dir)
    py = runner_venv_python(runner_dir)
    if not py.is_file():
        if is_packaged_app():
            return (
                False,
                "打包版缺少 runner\\venv 运行时，请重新下载官方 BrickCoreRunner 安装包。",
                None,
            )
        return False, "开发模式请先在 runner 目录创建 venv 并安装依赖。", "deps"

    missing, detail = probe_perf_imports(runner_dir)
    if missing:
        if is_packaged_app():
            return False, format_runner_deps_error(runner_dir, missing, detail=detail), None
        return False, format_runner_deps_error(runner_dir, missing, detail=detail), "deps"

    return True, "", None


def repair_runner_dependencies(
    runner_dir: Path,
    on_output: Callable[[str], None] | None = None,
) -> None:
    """在 runner venv 中安装 requirements.txt"""
    pip = runner_venv_pip(runner_dir)
    if not pip.is_file():
        raise RuntimeError("Runner pip 不可用，无法安装依赖")
    req = runner_dir / "requirements.txt"
    if not req.is_file():
        raise RuntimeError(f"找不到 {req}")

    cmd = [str(pip), "install", "-r", str(req)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(runner_dir),
        env=runner_subprocess_env(runner_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_HIDDEN_SUBPROCESS_KW,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if on_output:
            on_output(line.rstrip("\n"))
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"pip install 失败，退出码 {code}")
    still_missing = missing_runner_imports(runner_dir)
    if still_missing:
        names = ", ".join(label for _, label in still_missing)
        raise RuntimeError(f"依赖安装后仍缺失：{names}")


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
    env = runner_subprocess_env(runner_dir)
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
        **_HIDDEN_SUBPROCESS_KW,
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
