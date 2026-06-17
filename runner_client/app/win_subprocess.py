"""Windows 下隐藏子进程控制台窗口（打包 GUI exe 上线时避免闪多个黑框）。"""
from __future__ import annotations

import os
import subprocess


def _supports_create_no_window() -> bool:
    return os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW")


def hidden_runner_subprocess_kwargs() -> dict:
    """
    短生命周期子进程（依赖探测、pip、playwright install）。
    打包版 BrickCoreRunner.exe 为 console=False，若不隐藏则每次 python.exe 都会弹黑窗。
    """
    if os.name != "nt":
        return {}
    if _supports_create_no_window():
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si}


def engine_runner_subprocess_kwargs() -> dict:
    """Runner 引擎长驻子进程：保留 CREATE_NEW_PROCESS_GROUP 便于 terminate，同时隐藏窗口。"""
    if os.name != "nt":
        return {}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if _supports_create_no_window():
        flags |= subprocess.CREATE_NO_WINDOW
        return {"creationflags": flags}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
