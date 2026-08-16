from __future__ import annotations

import os
import queue
import subprocess
import uuid
from typing import Optional

from runner_client.app.engine_manager import (
    _OutputReader,
    repo_runner_dir,
    runner_python_executable,
)
from runner_client.app.runtime_check import diagnose_perf_runtime
from runner_client.app.win_subprocess import engine_runner_subprocess_kwargs


def perf_worker_token() -> str:
    """与设备绑定的稳定 token，便于重复上线复用 PerfWorker 记录。"""
    return f"rc-{uuid.getnode():x}"


class PerfWorkerManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._out_queue: Optional[queue.Queue[str | None]] = None
        self._reader: Optional[_OutputReader] = None
        self._log_offset = 0
        self.runner_dir = repo_runner_dir()
        self.log_path = self.runner_dir / "logs" / "perf_worker.log"

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(
        self,
        *,
        master_url: str,
        name: str,
        project_id: int,
        max_concurrent: int,
        runner_token: str | None = None,
        access_token: str | None = None,
    ) -> None:
        if self.is_running:
            raise RuntimeError("压测 Worker 已在运行")
        if not (self.runner_dir / "perf_worker.py").is_file():
            raise FileNotFoundError(f"找不到压测脚本: {self.runner_dir / 'perf_worker.py'}")

        ok, message, repair = diagnose_perf_runtime(self.runner_dir)
        if not ok:
            hint = "请安装 runner 依赖（httpx、numpy）。" if repair == "deps" else ""
            raise RuntimeError(f"{message}\n{hint}".strip())

        if max_concurrent < 1:
            raise ValueError("最大并发必须大于 0")
        if project_id < 1:
            raise ValueError("请选择有效的压测项目")

        rt = (runner_token or "").strip()
        at = (access_token or "").strip()
        # 仅「性能测试」角色不上报 UI 设备，不会拿到 X-Runner-Token；须用登录 JWT 注册
        if not rt and not at:
            raise RuntimeError(
                "压测 Worker 注册缺少认证：请先登录；"
                "若仅开压测角色，将使用登录 JWT；也可改选「UI + 压测」上线。"
            )

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            self._log_offset = self.log_path.stat().st_size
        else:
            self._log_offset = 0

        py_exe = runner_python_executable()
        token = perf_worker_token()
        self._out_queue = queue.Queue()
        cmd = [
            py_exe,
            "-u",
            "perf_worker.py",
            "--master",
            master_url.rstrip("/"),
            "--token",
            token,
            "--name",
            name,
            "--max-concurrent",
            str(max_concurrent),
            "--project-id",
            str(project_id),
            "--agent-kind",
            "runner_client",
        ]
        if rt:
            cmd.extend(["--runner-token", rt])
        if at:
            cmd.extend(["--access-token", at])
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if rt:
            env["RUNNER_TOKEN"] = rt
        if at:
            env["PERF_ACCESS_TOKEN"] = at
        print(f"[client] perf worker python: {py_exe}", flush=True)
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self.runner_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **engine_runner_subprocess_kwargs(),
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

    def discard_displayed_logs(self) -> None:
        """面板「清空显示」：游标移到文件末尾，并排空 stdout 队列。"""
        try:
            if self.log_path.exists():
                self._log_offset = self.log_path.stat().st_size
            else:
                self._log_offset = 0
        except OSError:
            self._log_offset = 0
        if not self._out_queue:
            return
        saw_sentinel = False
        while True:
            try:
                item = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                saw_sentinel = True
                break
        if saw_sentinel:
            self._out_queue.put(None)

    def read_new_log_lines(self, max_lines: int = 200) -> str:
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

    def read_log_file_content(self, max_bytes: int = 2 * 1024 * 1024) -> tuple[str, bool]:
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

    def log_file_size(self) -> int:
        if not self.log_path.exists():
            return 0
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0
