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

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health_check(self) -> bool:
        try:
            resp = requests.get(self._url("/runner/health"), timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            try:
                resp = requests.get(self._url("/docs"), timeout=5)
                return resp.status_code in (200, 401)
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
        payload = {
            "id": str(uuid.getnode()),
            "ip": socket.gethostbyname(socket.gethostname()),
            "name": device_name,
            "system": platform.system(),
            "username": self.username or device_name,
            "version": platform.version(),
            "hostname": socket.gethostname(),
            "client_version": CLIENT_VERSION,
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
        requests.post(
            self._url("/runner/heartbeat"),
            json={"device_id": device_id, "client_version": CLIENT_VERSION},
            headers={"X-Runner-Token": self.runner_token},
            timeout=10,
        )

    def fetch_version_info(self) -> dict[str, Any] | None:
        try:
            resp = requests.get(self._url("/runner/version"), timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        return None

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
