"""兼容层：将本模块替换为 brickcore_tm.quality_gate（含私有符号）。"""
from __future__ import annotations

import sys
from typing import Any

try:
    from brickcore_tm import quality_gate as _impl

    sys.modules[__name__] = _impl
except ImportError:  # pragma: no cover

    def __getattr__(name: str) -> Any:
        from app.modules.test_management.premium_gateway import raise_tm_premium_required

        raise_tm_premium_required()
