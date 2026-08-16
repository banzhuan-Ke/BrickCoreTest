from __future__ import annotations

import json
import os
import platform
import socket
import uuid
from pathlib import Path
from typing import Any, Optional

import requests

from runner_client import __version__ as CLIENT_VERSION
from runner_client.app.engine_capabilities import detect_runner_capabilities
from runner_client.app.bcpack import read_installed_package_version
from runner_client.app.engine_manager import app_root_dir


def _report_client_version() -> str:
    try:
        return read_installed_package_version(app_root_dir(), fallback=CLIENT_VERSION)
    except Exception:
        return CLIENT_VERSION

DEFAULT_TIMEOUT = 30


def parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in (version or "0").strip().split("."):
        token = segment.split("-")[0].split("+")[0]
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts or (0,))


def compare_version(left: str, right: str) -> int:
    a = parse_version(left)
    b = parse_version(right)
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def is_version_below(current: str, minimum: str) -> bool:
    return compare_version(current, minimum) < 0


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class BrickCoreApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.user_token: str = ""
        self.runner_token: str = ""
        self.username: str = ""
        self.engine_web_enabled: bool = True
        self.engine_app_enabled: bool = False

    def _engine_flags(self) -> tuple[bool, bool]:
        return bool(self.engine_web_enabled), bool(self.engine_app_enabled)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health_check(self) -> bool:
        """探活平台 HTTP API。优先单路径，失败再试 version（最多 2 次请求）。"""
        try:
            resp = requests.get(self._url("/runner/health"), timeout=5)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        try:
            resp = requests.get(self._url("/runner/version"), timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = requests.post(
            self._url("/sys/users/login"),
            json={"username": username, "password": password},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        data = resp.json()
        self.user_token = data.get("token", "")
        user = data.get("user") or {}
        self.username = user.get("username") or username
        if not self.user_token:
            raise ApiError("登录成功但未返回 token")
        return data

    def connect_runner(self, device_name: str) -> dict[str, Any]:
        if not self.user_token:
            raise ApiError("请先登录")
        enable_web, enable_app = self._engine_flags()
        caps = detect_runner_capabilities(enable_web=enable_web, enable_app=enable_app)
        payload = {
            "id": str(uuid.getnode()),
            "ip": socket.gethostbyname(socket.gethostname()),
            "name": device_name,
            "system": platform.system(),
            "username": self.username or device_name,
            "version": platform.version(),
            "hostname": socket.gethostname(),
            "client_version": _report_client_version(),
            **caps,
        }
        resp = requests.post(
            self._url("/runner/connect"),
            json=payload,
            headers={"Authorization": f"Bearer {self.user_token}"},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        data = resp.json()
        self.runner_token = data.get("runner_token", "")
        return data

    def disconnect_runner(self, device_id: str) -> None:
        if not self.runner_token:
            return
        try:
            requests.post(
                self._url("/runner/disconnect"),
                json={"device_id": device_id},
                headers={"X-Runner-Token": self.runner_token},
                timeout=10,
            )
        except requests.RequestException:
            pass
        finally:
            self.runner_token = ""

    def heartbeat(self, device_id: str) -> None:
        if not self.runner_token:
            return
        enable_web, enable_app = self._engine_flags()
        caps = detect_runner_capabilities(enable_web=enable_web, enable_app=enable_app)
        resp = requests.post(
            self._url("/runner/heartbeat"),
            json={
                "device_id": device_id,
                "client_version": _report_client_version(),
                "runner_engine_types": caps.get("runner_engine_types"),
                "app_platform": caps.get("app_platform", ""),
                "app_udid": caps.get("app_udid", ""),
                "app_connection": caps.get("app_connection", ""),
                "toolchain_status": caps.get("toolchain_status", {}),
            },
            headers={"X-Runner-Token": self.runner_token},
            timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)

    def fetch_version_info(self) -> dict[str, Any] | None:
        try:
            resp = requests.get(self._url("/runner/version"), timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        return None

    def _auth_headers(self) -> dict[str, str]:
        if not self.user_token:
            raise ApiError("请先登录")
        return {"Authorization": f"Bearer {self.user_token}"}

    def _runner_headers(self) -> dict[str, str]:
        if not self.runner_token:
            raise ApiError("Runner 未上线")
        return {"X-Runner-Token": self.runner_token}

    def fetch_active_recording(self) -> dict[str, Any] | None:
        """查询本设备进行中的 Web 录制（Runner token）。"""
        resp = requests.get(
            self._url("/runner/active-recording"),
            headers=self._runner_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else None
        return data if isinstance(data, dict) else None

    def pause_recording(self, record_id: int) -> dict[str, Any]:
        resp = requests.post(
            self._url(f"/ai/record/{record_id}/pause"),
            json={},
            headers=self._auth_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        return body.get("data") if isinstance(body, dict) else body

    def resume_recording(self, record_id: int) -> dict[str, Any]:
        resp = requests.post(
            self._url(f"/ai/record/{record_id}/resume"),
            json={},
            headers=self._auth_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        return body.get("data") if isinstance(body, dict) else body

    def stop_recording(self, record_id: int) -> dict[str, Any]:
        resp = requests.post(
            self._url(f"/ai/record/{record_id}/stop"),
            json={},
            headers=self._auth_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        return body.get("data") if isinstance(body, dict) else body

    def save_recording_variable(self, record_id: int, var_name: str, source: str = "text") -> dict[str, Any]:
        resp = requests.post(
            self._url(f"/ai/record/{record_id}/save-variable"),
            json={"var_name": var_name, "source": source},
            headers=self._auth_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        return body.get("data") if isinstance(body, dict) else body

    def list_projects(self, *, page: int = 1, size: int = 200) -> list[dict[str, Any]]:
        if not self.user_token:
            raise ApiError("请先登录")
        resp = requests.get(
            self._url("/sys/projects"),
            params={"page": page, "size": size},
            headers={"Authorization": f"Bearer {self.user_token}"},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else body
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def unregister_perf_worker(self, project_id: int, *, host: str | None = None) -> None:
        from runner_client.app.perf_worker_manager import perf_worker_token

        hostname = host or socket.gethostname()
        headers: dict[str, str] = {}
        if self.runner_token:
            headers["X-Runner-Token"] = self.runner_token
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        if not headers:
            raise ApiError("压测下线缺少认证：请先登录或保持 Runner 会话")
        resp = requests.post(
            self._url("/perf/workers/unregister"),
            params={"project_id": project_id},
            json={"token": perf_worker_token(), "host": hostname},
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ApiError(self._extract_error(resp), resp.status_code)

    def download_client_package(self, dest: Path) -> Path:
        from runner_client.app.package_updater import download_client_package

        return download_client_package(self, dest)

    @staticmethod
    def resolve_download_url(base_url: str, version_info: dict[str, Any] | None) -> str:
        if version_info:
            url = (version_info.get("runner_client_download_url") or "").strip()
            # 需 Bearer 的 API 下载地址不能用浏览器直接打开
            if url and "client-download" not in url:
                return url
        root = (base_url or "").rstrip("/")
        if root:
            static_url = f"{root}/static/runner/BrickCoreRunner.zip"
            if version_info and version_info.get("package_available"):
                return static_url
        return ""

    @staticmethod
    def _extract_error(resp: requests.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = body["detail"]
                if isinstance(detail, list):
                    return "; ".join(str(x) for x in detail)
                return str(detail)
        except Exception:
            pass
        return resp.text or f"HTTP {resp.status_code}"
