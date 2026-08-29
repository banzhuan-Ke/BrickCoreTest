"""Web Runner 执行参数（视口、失败重跑），供客户端设置与引擎子进程注入。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from runner_client.app.engine_manager import repo_runner_dir
from runner_client.app.preferences import load_preferences, save_preferences

DEFAULT_VIEWPORT_WIDTH = 1920
DEFAULT_VIEWPORT_HEIGHT = 1080
DEFAULT_CASE_ERROR_RETRIES = 1

MIN_VIEWPORT_WIDTH = 800
MIN_VIEWPORT_HEIGHT = 600
MAX_CASE_ERROR_RETRIES = 5

PREF_VIEWPORT_WIDTH = "runner_viewport_width"
PREF_VIEWPORT_HEIGHT = "runner_viewport_height"
PREF_CASE_ERROR_RETRIES = "runner_case_error_retries"
PREF_BROWSER_LAB_STEP_MAX_WIDTH = "browser_lab_step_max_width"
PREF_BROWSER_LAB_GIF_MAX_WIDTH = "browser_lab_gif_max_width"
PREF_BROWSER_LAB_GIF_FRAME_SKIP = "browser_lab_gif_frame_skip"

ENV_VIEWPORT_WIDTH = "RUNNER_VIEWPORT_WIDTH"
ENV_VIEWPORT_HEIGHT = "RUNNER_VIEWPORT_HEIGHT"
ENV_CASE_ERROR_RETRIES = "RUNNER_CASE_ERROR_RETRIES"
ENV_BROWSER_LAB_STEP_MAX_WIDTH = "BROWSER_LAB_STEP_MAX_WIDTH"
ENV_BROWSER_LAB_GIF_MAX_WIDTH = "BROWSER_LAB_GIF_MAX_WIDTH"
ENV_BROWSER_LAB_GIF_FRAME_SKIP = "BROWSER_LAB_GIF_FRAME_SKIP"
ENV_UI_DEBUG_HOTKEYS = "UI_DEBUG_HOTKEYS_JSON"
PREF_UI_DEBUG_HOTKEYS = "ui_debug_hotkeys"

DEFAULT_BROWSER_LAB_STEP_MAX_WIDTH = 1280
DEFAULT_BROWSER_LAB_GIF_MAX_WIDTH = 960
DEFAULT_BROWSER_LAB_GIF_FRAME_SKIP = 1
MIN_BROWSER_LAB_STEP_MAX_WIDTH = 640
MIN_BROWSER_LAB_GIF_MAX_WIDTH = 320
MAX_BROWSER_LAB_STEP_MAX_WIDTH = 2560
MAX_BROWSER_LAB_GIF_MAX_WIDTH = 1920
MIN_BROWSER_LAB_GIF_FRAME_SKIP = 1
MAX_BROWSER_LAB_GIF_FRAME_SKIP = 5


def _clamp_int(value: Any, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    n = max(minimum, n)
    if maximum is not None:
        n = min(maximum, n)
    return n


def normalize_execution_prefs(prefs: dict[str, Any]) -> dict[str, int]:
    return {
        PREF_VIEWPORT_WIDTH: _clamp_int(
            prefs.get(PREF_VIEWPORT_WIDTH),
            DEFAULT_VIEWPORT_WIDTH,
            MIN_VIEWPORT_WIDTH,
        ),
        PREF_VIEWPORT_HEIGHT: _clamp_int(
            prefs.get(PREF_VIEWPORT_HEIGHT),
            DEFAULT_VIEWPORT_HEIGHT,
            MIN_VIEWPORT_HEIGHT,
        ),
        PREF_CASE_ERROR_RETRIES: _clamp_int(
            prefs.get(PREF_CASE_ERROR_RETRIES),
            DEFAULT_CASE_ERROR_RETRIES,
            0,
            MAX_CASE_ERROR_RETRIES,
        ),
        PREF_BROWSER_LAB_STEP_MAX_WIDTH: _clamp_int(
            prefs.get(PREF_BROWSER_LAB_STEP_MAX_WIDTH),
            DEFAULT_BROWSER_LAB_STEP_MAX_WIDTH,
            MIN_BROWSER_LAB_STEP_MAX_WIDTH,
            MAX_BROWSER_LAB_STEP_MAX_WIDTH,
        ),
        PREF_BROWSER_LAB_GIF_MAX_WIDTH: _clamp_int(
            prefs.get(PREF_BROWSER_LAB_GIF_MAX_WIDTH),
            DEFAULT_BROWSER_LAB_GIF_MAX_WIDTH,
            MIN_BROWSER_LAB_GIF_MAX_WIDTH,
            MAX_BROWSER_LAB_GIF_MAX_WIDTH,
        ),
        PREF_BROWSER_LAB_GIF_FRAME_SKIP: _clamp_int(
            prefs.get(PREF_BROWSER_LAB_GIF_FRAME_SKIP),
            DEFAULT_BROWSER_LAB_GIF_FRAME_SKIP,
            MIN_BROWSER_LAB_GIF_FRAME_SKIP,
            MAX_BROWSER_LAB_GIF_FRAME_SKIP,
        ),
    }


def execution_env_from_prefs(prefs: dict[str, Any]) -> dict[str, str]:
    from runner_client.app.ui_debug_hotkeys import hotkeys_to_json, merge_hotkeys

    normalized = normalize_execution_prefs(prefs)
    hotkeys = merge_hotkeys(prefs.get(PREF_UI_DEBUG_HOTKEYS) if isinstance(prefs, dict) else None)
    return {
        ENV_VIEWPORT_WIDTH: str(normalized[PREF_VIEWPORT_WIDTH]),
        ENV_VIEWPORT_HEIGHT: str(normalized[PREF_VIEWPORT_HEIGHT]),
        ENV_CASE_ERROR_RETRIES: str(normalized[PREF_CASE_ERROR_RETRIES]),
        ENV_BROWSER_LAB_STEP_MAX_WIDTH: str(normalized[PREF_BROWSER_LAB_STEP_MAX_WIDTH]),
        ENV_BROWSER_LAB_GIF_MAX_WIDTH: str(normalized[PREF_BROWSER_LAB_GIF_MAX_WIDTH]),
        ENV_BROWSER_LAB_GIF_FRAME_SKIP: str(normalized[PREF_BROWSER_LAB_GIF_FRAME_SKIP]),
        ENV_UI_DEBUG_HOTKEYS: hotkeys_to_json(hotkeys),
    }


def apply_execution_config_to_env(env: dict[str, str], prefs: dict[str, Any] | None = None) -> dict[str, str]:
    source = prefs if prefs is not None else load_preferences()
    env.update(execution_env_from_prefs(source))
    return env


def _update_dotenv_file(env_path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    written: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            out.append(line)

    for key, value in updates.items():
        if key not in written:
            out.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out).rstrip("\n")
    env_path.write_text(text + "\n", encoding="utf-8")


def sync_execution_config_to_runner_dotenv(prefs: dict[str, Any] | None = None) -> None:
    """将执行参数写入 runner/.env，便于开发模式直接启动引擎。"""
    updates = execution_env_from_prefs(prefs or load_preferences())
    _update_dotenv_file(repo_runner_dir() / ".env", updates)


def save_execution_prefs(
    viewport_width: int,
    viewport_height: int,
    case_error_retries: int,
    *,
    browser_lab_step_max_width: int | None = None,
    browser_lab_gif_max_width: int | None = None,
    browser_lab_gif_frame_skip: int | None = None,
    base_prefs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefs = dict(base_prefs if base_prefs is not None else load_preferences())
    prefs[PREF_VIEWPORT_WIDTH] = _clamp_int(
        viewport_width, DEFAULT_VIEWPORT_WIDTH, MIN_VIEWPORT_WIDTH
    )
    prefs[PREF_VIEWPORT_HEIGHT] = _clamp_int(
        viewport_height, DEFAULT_VIEWPORT_HEIGHT, MIN_VIEWPORT_HEIGHT
    )
    prefs[PREF_CASE_ERROR_RETRIES] = _clamp_int(
        case_error_retries, DEFAULT_CASE_ERROR_RETRIES, 0, MAX_CASE_ERROR_RETRIES
    )
    if browser_lab_step_max_width is not None:
        prefs[PREF_BROWSER_LAB_STEP_MAX_WIDTH] = _clamp_int(
            browser_lab_step_max_width,
            DEFAULT_BROWSER_LAB_STEP_MAX_WIDTH,
            MIN_BROWSER_LAB_STEP_MAX_WIDTH,
            MAX_BROWSER_LAB_STEP_MAX_WIDTH,
        )
    if browser_lab_gif_max_width is not None:
        prefs[PREF_BROWSER_LAB_GIF_MAX_WIDTH] = _clamp_int(
            browser_lab_gif_max_width,
            DEFAULT_BROWSER_LAB_GIF_MAX_WIDTH,
            MIN_BROWSER_LAB_GIF_MAX_WIDTH,
            MAX_BROWSER_LAB_GIF_MAX_WIDTH,
        )
    if browser_lab_gif_frame_skip is not None:
        prefs[PREF_BROWSER_LAB_GIF_FRAME_SKIP] = _clamp_int(
            browser_lab_gif_frame_skip,
            DEFAULT_BROWSER_LAB_GIF_FRAME_SKIP,
            MIN_BROWSER_LAB_GIF_FRAME_SKIP,
            MAX_BROWSER_LAB_GIF_FRAME_SKIP,
        )
    save_preferences(prefs)
    sync_execution_config_to_runner_dotenv(prefs)
    return prefs
