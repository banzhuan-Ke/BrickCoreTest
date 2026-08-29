"""向本机 Runner 引擎进程写入停止指令（不依赖平台 MQ）。"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from runner_client.app.engine_manager import repo_runner_dir


def _queue_path() -> Path:
    path = repo_runner_dir() / "logs" / "local_control.queue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def request_stop_active_agent(*, source: str = "runner_client") -> None:
    """请求停止当前智能浏览器 / UI Agent 等 Agent 类任务。"""
    payload = {
        "action": "stop_active_agent",
        "ts": time.time(),
        "source": source,
        "id": uuid.uuid4().hex,
    }
    path = _queue_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
