from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from runner_client.app.runtime_check import playwright_browsers_path_for_engine


def app_root_dir() -> Path:
    """开发：仓库根目录；打包：exe 所在目录"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def repo_runner_dir() -> Path:
    return app_root_dir() / "runner"


def playwright_browsers_dir() -> Path:
    return repo_runner_dir() / "browsers"


def runner_python_executable() -> str:
    runner_dir = repo_runner_dir()
    if os.name == "nt":
        venv_py = runner_dir / "venv" / "Scripts" / "python.exe"
    else:
        venv_py = runner_dir / "venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def build_engine_env(connect: dict[str, Any], device_name: str) -> dict[str, str]:
    """将 connect 响应转为子进程环境变量（内存注入，不写密码到安装包）"""
    env = os.environ.copy()
    mq = connect["mq"]
    redis = connect["redis"]

    env["BASE_URL"] = connect["base_url"]
    env["RUNNER_TOKEN"] = connect.get("runner_token", "")
    env["RUNNER_VERSION"] = connect.get("engine_version", "1.0.0")
    env["DEVICE_NAME"] = device_name
    env["DEVICE_ID"] = connect.get("device_id", str(uuid.getnode()))

    env["MQ_HOST"] = str(mq["host"])
    env["MQ_PORT"] = str(mq["port"])
    env["MQ_USERNAME"] = str(mq["username"])
    env["MQ_PASSWORD"] = str(mq["password"])

    env["REDIS_HOST"] = str(redis["host"])
    env["REDIS_PORT"] = str(redis["port"])
    env["REDIS_USERNAME"] = str(redis.get("username") or "")
    env["REDIS_PASSWORD"] = str(redis.get("password") or "")
    env["REDIS_DB"] = str(redis.get("db", 15))

    env["STORAGE_TYPE"] = str(connect.get("storage_type", "minio"))
    env["UPLOAD_MODE"] = str(connect.get("upload_mode", "presigned"))
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    browsers_path = playwright_browsers_path_for_engine(repo_runner_dir())
    if browsers_path:
        env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    for key in (
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
        "MINIO_SECURE",
        "INTERNAL_API_KEY",
        "RUNNER_LEGACY",
    ):
        env.pop(key, None)
    return env


def _decode_subprocess_line(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(encoding).rstrip("\r\n")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


class _OutputReader(threading.Thread):
    """后台读取子进程 stdout（二进制 + 多编码解码），避免阻塞 Qt 主线程。"""

    def __init__(self, proc: subprocess.Popen, out_queue: queue.Queue[str | None]) -> None:
        super().__init__(daemon=True)
        self._proc = proc
        self._queue = out_queue

    def run(self) -> None:
        stdout = self._proc.stdout
        if not stdout:
            self._queue.put(None)
            return
        try:
            for raw in iter(stdout.readline, b""):
                line = _decode_subprocess_line(raw)
                if line:
                    self._queue.put(line)
        finally:
            self._queue.put(None)


class EngineManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._out_queue: Optional[queue.Queue[str | None]] = None
        self._reader: Optional[_OutputReader] = None
        self._log_offset = 0
        self.runner_dir = repo_runner_dir()
        self.log_path = self.runner_dir / "logs" / "playwright.log"

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, connect: dict[str, Any], device_name: str) -> None:
        if self.is_running:
            raise RuntimeError("Runner 引擎已在运行")
        if not (self.runner_dir / "main.py").is_file():
            raise FileNotFoundError(f"找不到 Runner 引擎: {self.runner_dir / 'main.py'}")

        env = build_engine_env(connect, device_name)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # 仅从本次上线后写入的内容开始读取（保留文件中的历史记录）
        if self.log_path.exists():
            self._log_offset = self.log_path.stat().st_size
        else:
            self._log_offset = 0
        self._out_queue = queue.Queue()
        self._proc = subprocess.Popen(
            [runner_python_executable(), "main.py"],
            cwd=str(self.runner_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self._reader = _OutputReader(self._proc, self._out_queue)
        self._reader.start()

    def stop(self) -> None:
        if not self._proc:
            return
        proc = self._proc
        self._proc = None
        self._out_queue = None
        self._reader = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def read_new_output(self) -> str:
        if not self._out_queue:
            return ""
        lines: list[str] = []
        while len(lines) < 200:
            try:
                line = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            lines.append(line)
        return "\n".join(lines)

    def read_new_log_lines(self, max_lines: int = 200) -> str:
        """从 UTF-8 日志文件读取本次上线后的新行（避免 stdout 编码乱码）。"""
        if not self.log_path.exists():
            return ""
        try:
            with self.log_path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_offset)
                lines: list[str] = []
                for line in fh:
                    lines.append(line.rstrip("\n\r"))
                    if len(lines) >= max_lines:
                        break
                self._log_offset = fh.tell()
            return "\n".join(lines)
        except Exception:
            return ""

    def log_file_size(self) -> int:
        if not self.log_path.exists():
            return 0
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    def read_log_file_content(self, max_bytes: int = 2 * 1024 * 1024) -> tuple[str, bool]:
        """读取日志文件全文（供历史查看）。返回 (内容, 是否被截断)。"""
        if not self.log_path.exists():
            return "", False
        try:
            size = self.log_path.stat().st_size
            truncated = size > max_bytes
            read_from = max(0, size - max_bytes) if truncated else 0
            with self.log_path.open("rb") as fh:
                if read_from:
                    fh.seek(read_from)
                data = fh.read()
            text = data.decode("utf-8", errors="replace")
            if truncated:
                text = f"...（文件较大，仅显示最近 {max_bytes // 1024}KB）...\n\n" + text
            return text, truncated
        except Exception as exc:
            return f"读取日志失败：{exc}", False

    def clear_log_file(self) -> None:
        """删除磁盘上的 Runner 日志文件（需在下线后操作）。"""
        if self.log_path.exists():
            self.log_path.unlink()
        self._log_offset = 0
