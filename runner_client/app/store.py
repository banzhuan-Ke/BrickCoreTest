from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 内置默认仅 localhost；演示/线上地址请用户在「管理服务器环境」中自行添加（不写入安装包）。
DEFAULT_SERVERS: list[dict[str, Any]] = [
    {"id": "local", "label": "本地开发", "url": "http://localhost:8000"},
]

BUILTIN_SERVER_IDS = frozenset({"local"})


def _config_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path.home() / ".config"
    path = root / "BrickCore" / "runner_client"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path(name: str) -> Path:
    return _config_dir() / name


def _normalize_servers(servers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """保证存在内置 local 项；保留用户自定义环境。"""
    changed = False
    by_id = {str(s.get("id")): s for s in servers if s.get("id")}
    for default in DEFAULT_SERVERS:
        sid = default["id"]
        if sid not in by_id:
            by_id[sid] = dict(default)
            changed = True
            continue
        entry = by_id[sid]
        if not entry.get("label"):
            entry["label"] = default["label"]
            changed = True
        if not (entry.get("url") or "").strip():
            entry["url"] = default["url"]
            changed = True
    ordered: list[dict[str, Any]] = []
    for default in DEFAULT_SERVERS:
        ordered.append(by_id.pop(default["id"], dict(default)))
    ordered.extend(by_id.values())
    return ordered, changed


def load_servers() -> list[dict[str, Any]]:
    path = _config_path("servers.json")
    if not path.exists():
        return list(DEFAULT_SERVERS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return list(DEFAULT_SERVERS)
        servers, changed = _normalize_servers(raw)
        if changed:
            save_servers(servers)
        return servers
    except Exception:
        return list(DEFAULT_SERVERS)


def save_servers(servers: list[dict[str, Any]]) -> None:
    _config_path("servers.json").write_text(
        json.dumps(servers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_session(server_url: str) -> dict[str, Any]:
    path = _config_path("sessions.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(server_url, {})
    except Exception:
        return {}


def save_session(server_url: str, session: dict[str, Any]) -> None:
    path = _config_path("sessions.json")
    all_sessions: dict[str, Any] = {}
    if path.exists():
        try:
            all_sessions = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            all_sessions = {}
    stored = {k: v for k, v in session.items() if k != "password"}
    all_sessions[server_url] = stored
    path.write_text(json.dumps(all_sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_session_password(server_url: str) -> None:
    session = load_session(server_url)
    session.pop("password_token", None)
    save_session(server_url, session)
