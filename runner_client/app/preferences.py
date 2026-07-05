from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from runner_client.app.store import _config_path

DEFAULT_PREFERENCES: dict[str, Any] = {
    "remember_password": True,
    "minimize_to_tray": True,
    "close_hides_to_tray": True,
    "autostart": False,
    "engine_web_enabled": True,
    "engine_app_enabled": False,
    "runner_viewport_width": 1920,
    "runner_viewport_height": 1080,
    "runner_case_error_retries": 1,
}


def load_preferences() -> dict[str, Any]:
    path = _config_path("preferences.json")
    if not path.exists():
        return dict(DEFAULT_PREFERENCES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_PREFERENCES)
        if isinstance(data, dict):
            merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_PREFERENCES)


def save_preferences(prefs: dict[str, Any]) -> None:
    path = _config_path("preferences.json")
    path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def autostart_executable() -> str | None:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return None


def set_windows_autostart(enabled: bool) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "仅支持 Windows 开机自启"
    exe = autostart_executable()
    if not exe:
        return False, "开发模式（python 启动）不支持开机自启，请使用打包后的 BrickCoreRunner.exe"
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "BrickCoreRunner", 0, winreg.REG_SZ, exe)
            else:
                try:
                    winreg.DeleteValue(key, "BrickCoreRunner")
                except FileNotFoundError:
                    pass
        return True, ""
    except OSError as exc:
        return False, str(exc)
