# -*- coding: utf-8 -*-
"""确保 pytest 优先导入本仓库 backend 下的 `app` 包，避免 PYTHONPATH 中其它目录的 `app.py` 抢占。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
backend_str = str(BACKEND_ROOT)

# 本目录置于 sys.path 最前
while backend_str in sys.path:
    sys.path.remove(backend_str)
sys.path.insert(0, backend_str)

# 若已错误加载了外部 app（文件模块/其它包），清掉以便重新从本仓库导入
_mod = sys.modules.get("app")
if _mod is not None:
    origin = (getattr(_mod, "__file__", None) or "").replace("\\", "/")
    if f"{BACKEND_ROOT.as_posix()}/app" not in origin:
        for key in list(sys.modules):
            if key == "app" or key.startswith("app."):
                del sys.modules[key]
