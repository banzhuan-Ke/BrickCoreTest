#!/usr/bin/env bash
# BrickCore Runner — macOS engine release (Nuitka .so, no business .py)
# Output: runner_client/dist/BrickCoreRunner-mac/ + .zip
#
# Must run ON macOS (Apple Silicon or Intel). Cannot cross-build from Windows.
# From Windows: push code and run .github/workflows/build-runner-mac.yml, then download Artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER_SRC="$ROOT/runner"
CLIENT_DIR="$ROOT/runner_client"
DIST_DIR="$CLIENT_DIR/dist/BrickCoreRunner-mac"
RUNNER_DEST="$DIST_DIR/runner"
PYTHON_VERSION="${PYTHON_VERSION:-3.11.5}"
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
SKIP_RUNTIME=0
SKIP_NUITKA=0
SKIP_SOURCE_STRIP=0

usage() {
    cat <<'EOF'
Usage: ./scripts/build_runner_mac.sh [options]

  --skip-runtime       Reuse existing runner/venv and runner/browsers
  --skip-nuitka        Keep .py sources (dev only)
  --skip-source-strip  Same as --skip-nuitka
  -h, --help           Show help

Requires: macOS, Python 3.11 (full CPython), Xcode Command Line Tools (clang).
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-runtime) SKIP_RUNTIME=1; shift ;;
        --skip-nuitka|--skip-source-strip) SKIP_NUITKA=1; SKIP_SOURCE_STRIP=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

find_python311() {
    local candidates=()
    if command -v python3.11 >/dev/null 2>&1; then
        candidates+=("$(command -v python3.11)")
    fi
    if command -v python3 >/dev/null 2>&1; then
        candidates+=("$(command -v python3)")
    fi
    for py in "${candidates[@]}"; do
        [[ -x "$py" ]] || continue
        local ver
        ver="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
        [[ "$ver" == "3.11" ]] || continue
        # Reject embeddable / broken installs
        if "$py" -c "import venv, pip" >/dev/null 2>&1; then
            echo "$py"
            return 0
        fi
    done
    echo "Full CPython 3.11 not found. Install from https://www.python.org/downloads/ or: brew install python@3.11" >&2
    exit 1
}

copy_runner_engine() {
    echo "[2/8] Copy runner engine sources ..."
    rm -rf "$RUNNER_DEST"
    mkdir -p "$RUNNER_DEST"

    for sub in WebEngine tools; do
        [[ -d "$RUNNER_SRC/$sub" ]] || continue
        mkdir -p "$RUNNER_DEST/$sub"
        while IFS= read -r -d '' f; do
            rel="${f#"$RUNNER_SRC/$sub"/}"
            dest="$RUNNER_DEST/$sub/$rel"
            mkdir -p "$(dirname "$dest")"
            cp "$f" "$dest"
        done < <(find "$RUNNER_SRC/$sub" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0)
    done

    for name in settings.py main.py perf_worker.py requirements.txt; do
        [[ -f "$RUNNER_SRC/$name" ]] && cp "$RUNNER_SRC/$name" "$RUNNER_DEST/$name"
    done
}

setup_runner_runtime() {
    local base_py="$1"
    echo "[3/8] Create runner venv ($("$base_py" --version)) ..."
    "$base_py" -m pip install -q virtualenv -i "$PIP_INDEX"
    rm -rf "$RUNNER_DEST/venv"
    "$base_py" -m virtualenv "$RUNNER_DEST/venv" --copies

    local venv_py="$RUNNER_DEST/venv/bin/python"
    local venv_pip="$RUNNER_DEST/venv/bin/pip"
    "$venv_py" -m pip install -q -U pip -i "$PIP_INDEX"
    "$venv_pip" install -r "$RUNNER_DEST/requirements.txt" -i "$PIP_INDEX"

    mkdir -p "$RUNNER_DEST/browsers"
    export PLAYWRIGHT_BROWSERS_PATH="$RUNNER_DEST/browsers"
    echo "[4/8] Install Playwright Chromium (mac) ..."
    "$venv_py" -m playwright install chromium

    "$venv_py" -c "import jsonpath_ng, pika, redis, httpx, numpy; import greenlet; from playwright.sync_api import sync_playwright; print('venv ok')"
}

write_module_launcher() {
    local launcher_path="$1"
    local module_stem="$2"
    local entry_mode="${3:-main}"
    local venv_py="$RUNNER_DEST/venv/bin/python"
    MODULE_STEM="$module_stem" ENTRY_MODE="$entry_mode" LAUNCHER_PATH="$launcher_path" "$venv_py" <<'PY'
from pathlib import Path
import os

module_stem = os.environ["MODULE_STEM"]
entry_mode = os.environ["ENTRY_MODE"]
launcher_path = Path(os.environ["LAUNCHER_PATH"])
entry_block = "_mod.main()"
if entry_mode == "asyncio_main":
    entry_block = "import asyncio\nasyncio.run(_mod.main())"

content = f'''# BrickCore release launcher (loads Nuitka .so; do not edit)
import importlib.util
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_venv = (_root / "venv").resolve()
_cfg = _venv / "pyvenv.cfg"
_version, _version_info = "3.11.5", "3.11.5.final.0"
if _cfg.is_file():
    try:
        for _line in _cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip().lower(), _v.strip()
            if _k == "version" and _v:
                _version = _v
            elif _k == "version_info" and _v:
                _version_info = _v
    except OSError:
        pass
_desired_cfg = (
    f"home = {{_venv}}\\n"
    "implementation = CPython\\n"
    f"version_info = {{_version_info}}\\n"
    f"version = {{_version}}\\n"
    "include-system-site-packages = false\\n"
)
try:
    _current_cfg = _cfg.read_text(encoding="utf-8", errors="replace") if _cfg.is_file() else ""
    if _current_cfg != _desired_cfg:
        _cfg.write_text(_desired_cfg, encoding="utf-8")
except OSError:
    pass
if os.name == "nt":
    _path_add = []
    for _d in (_venv, _venv / "Scripts", _venv / "DLLs"):
        if _d.is_dir():
            _path_add.append(str(_d))
    if _path_add:
        os.environ["PATH"] = os.pathsep.join(_path_add + [os.environ.get("PATH", "")])
else:
    _bin = _venv / "bin"
    if _bin.is_dir():
        os.environ["PATH"] = os.pathsep.join([str(_bin), os.environ.get("PATH", "")])

_mod_file = None
for _pat in ("{module_stem}.cpython-*.so", "{module_stem}.cp*.so", "{module_stem}*.so"):
    _mod_file = next(_root.glob(_pat), None)
    if _mod_file is not None:
        break
if _mod_file is None:
    raise SystemExit("Missing compiled module: {module_stem}*.so")
_spec = importlib.util.spec_from_file_location("{module_stem}", _mod_file)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["{module_stem}"] = _mod
_spec.loader.exec_module(_mod)
{entry_block}
'''
launcher_path.write_text(content, encoding="utf-8")
PY
}

collect_engine_py_sources() {
    local runner_dir="$1"
    local -a files=()
    for name in settings.py main.py perf_worker.py; do
        [[ -f "$runner_dir/$name" ]] && files+=("$runner_dir/$name")
    done
    for sub in WebEngine tools; do
        [[ -d "$runner_dir/$sub" ]] || continue
        while IFS= read -r -d '' f; do
            [[ "$(basename "$f")" == "__init__.py" ]] && continue
            files+=("$f")
        done < <(find "$runner_dir/$sub" -name '*.py' -type f -print0)
    done
    printf '%s\n' "${files[@]}"
}

nuitka_compile_engine() {
    local venv_py="$RUNNER_DEST/venv/bin/python"
    local venv_pip="$RUNNER_DEST/venv/bin/pip"
    echo "[5/8] Install Nuitka ..."
    "$venv_pip" install -q nuitka ordered-set zstandard -i "$PIP_INDEX"

    echo "[6/8] Nuitka compile -> .so (may take several minutes) ..."
    if ! xcrun --find clang >/dev/null 2>&1; then
        echo "Xcode Command Line Tools required: xcode-select --install" >&2
        exit 1
    fi

    mapfile -t sources < <(collect_engine_py_sources "$RUNNER_DEST")
    pushd "$RUNNER_DEST" >/dev/null
    for py_file in "${sources[@]}"; do
        local rel="${py_file#"$RUNNER_DEST"/}"
        local out_dir="."
        [[ "$rel" == */* ]] && out_dir="$(dirname "$rel")"
        echo "  nuitka: $rel"
        "$venv_py" -m nuitka --module --nofollow-imports --remove-output --output-dir="$out_dir" "$rel"
    done
    popd >/dev/null

    local removed=0
    for py_file in "${sources[@]}"; do
        rm -f "$py_file"
        removed=$((removed + 1))
    done

    write_module_launcher "$RUNNER_DEST/main.py" main main
    write_module_launcher "$RUNNER_DEST/perf_worker.py" perf_worker asyncio_main

    ( cd "$RUNNER_DEST" && "$venv_py" -c "import settings; import tools.db_client; import WebEngine.runner; print('import smoke ok')" )
    echo "  Nuitka: removed $removed .py sources"
}

make_portable_venv() {
    local base_py="$1"
    local venv_dir="$RUNNER_DEST/venv"
    local venv_py="$venv_dir/bin/python"
    echo "[7/8] Bundle portable Python into runner/venv ..."
    local base_prefix
    base_prefix="$("$base_py" -c 'import sys; print(sys.base_prefix)')"
    local venv_lib="$venv_dir/lib/python3.11"
    local base_lib="$base_prefix/lib/python3.11"
    if [[ -d "$base_lib" ]]; then
        for item in "$base_lib"/*; do
            [[ "$(basename "$item")" == "site-packages" ]] && continue
            cp -R "$item" "$venv_lib/" 2>/dev/null || true
        done
    fi
    local py_ver
    py_ver="$("$venv_py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    cat >"$venv_dir/pyvenv.cfg" <<EOF
home = $(cd "$venv_dir" && pwd)
implementation = CPython
version_info = 3.11.5.final.0
version = $py_ver
include-system-site-packages = false
EOF
    "$venv_py" -c "import jsonpath_ng, pika, redis; import greenlet; from playwright.sync_api import sync_playwright; print('portable venv ok')"
}

prune_release_tree() {
    echo "  Prune dev artifacts ..."
    find "$RUNNER_DEST" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
    find "$RUNNER_DEST" -name '*.pyc' -path '*/venv/*' -prune -o -name '*.pyc' -print -delete 2>/dev/null || true
    for name in README.md WINDOWS_SETUP.md .idea profiles LOCAL start-local.bat start-online.bat start-headless-linux.sh .env .env.example settings.build icon.ico; do
        rm -rf "$RUNNER_DEST/$name" 2>/dev/null || true
    done
    for name in image video logs; do
        rm -rf "$RUNNER_DEST/$name"
        mkdir -p "$RUNNER_DEST/$name"
    done
    if [[ "$SKIP_SOURCE_STRIP" -eq 0 ]]; then
        while IFS= read -r -d '' f; do
            [[ "$f" == *"/venv/"* ]] && continue
            local rel="${f#"$RUNNER_DEST"/}"
            [[ "$rel" == "main.py" || "$rel" == "perf_worker.py" ]] && continue
            [[ "$(basename "$f")" == "__init__.py" ]] && continue
            rm -f "$f"
        done < <(find "$RUNNER_DEST" -name '*.py' -type f -print0)
    fi
}

write_dist_helpers() {
    local version="1.0.0"
    if [[ -f "$CLIENT_DIR/__init__.py" ]]; then
        version="$(grep -E '^__version__' "$CLIENT_DIR/__init__.py" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
    fi
    echo "$version" >"$DIST_DIR/VERSION.txt"

    cat >"$DIST_DIR/start-mac.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$ROOT/runner"
ENV_FILE="$RUNNER/.env"
VENV_PY="$RUNNER/venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
    echo "Missing runner/venv — use official BrickCoreRunner-mac.zip" >&2
    exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing runner/.env — run ./connect-mac.sh first" >&2
    exit 1
fi
export PLAYWRIGHT_BROWSERS_PATH="$RUNNER/browsers"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
cd "$RUNNER"
exec "$VENV_PY" main.py
EOF
    chmod +x "$DIST_DIR/start-mac.sh"

    cp "$ROOT/scripts/connect_runner_mac.py" "$DIST_DIR/connect-mac.py"
    cat >"$DIST_DIR/connect-mac.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/runner/venv/bin/python" "$ROOT/connect-mac.py" "$@"
EOF
    chmod +x "$DIST_DIR/connect-mac.sh"

    cat >"$DIST_DIR/README.txt" <<EOF
BrickCore Runner — macOS release (Nuitka engine)
================================================
1. Unzip this folder anywhere.
2. First time: ./connect-mac.sh
   (login platform, set device name — writes runner/.env on THIS Mac)
3. Start: ./start-mac.sh
4. Confirm device online in platform Device Management.

Headed browser debug: add HEADLESS=false to runner/.env
Do not copy runner/ from Windows BrickCoreRunner.zip — it will not run on Mac.
Version: $version
EOF
}

main() {
    echo "[1/8] Resolve Python 3.11 ..."
    local base_py
    base_py="$(find_python311)"
    echo "  Base: $base_py ($(uname -m))"

    rm -rf "$DIST_DIR"
    mkdir -p "$DIST_DIR"
    copy_runner_engine

    if [[ "$SKIP_RUNTIME" -eq 0 ]]; then
        setup_runner_runtime "$base_py"
    else
        echo "[3/8] Skipped runtime setup (--skip-runtime)"
        [[ -x "$RUNNER_DEST/venv/bin/python" ]] || { echo "runner/venv missing" >&2; exit 1; }
    fi

    if [[ "$SKIP_NUITKA" -eq 0 ]]; then
        nuitka_compile_engine
    else
        echo "[5/8] Skipped Nuitka (--skip-nuitka)"
    fi

    prune_release_tree
    make_portable_venv "$base_py"
    write_dist_helpers

    echo "[8/8] Verify dist imports ..."
    ( cd "$RUNNER_DEST" && "$RUNNER_DEST/venv/bin/python" -c "import settings; import tools.db_client; import WebEngine.runner; import jsonpath_ng, pika, redis; import greenlet._greenlet; from playwright.sync_api import sync_playwright; print('dist ok')" )

    local zip_path="$CLIENT_DIR/dist/BrickCoreRunner-mac.zip"
    rm -f "$zip_path"
    (cd "$CLIENT_DIR/dist" && ditto -c -k --sequesterRsrc --keepParent "BrickCoreRunner-mac" "$(basename "$zip_path")")

    echo ""
    echo "=== macOS build complete ==="
    echo "Output: $DIST_DIR"
    echo "Zip:    $zip_path"
    echo "Send BrickCoreRunner-mac.zip to Mac colleagues (arm64 vs x64 must match builder CPU)."
    echo "They must run ./connect-mac.sh on the Mac once before ./start-mac.sh"
}

main "$@"
