"""性能测试运行时状态（exec / workers 共享，避免循环引用）。"""
from __future__ import annotations

import asyncio
from typing import Dict

_running_records: Dict[int, asyncio.Event] = {}
_running_progress: Dict[int, Dict] = {}
