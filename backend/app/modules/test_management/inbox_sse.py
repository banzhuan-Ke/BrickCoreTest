"""兼容层：将本模块替换为 brickcore_tm.inbox_sse（含私有符号）。

未安装扩展包时不得在 ``from ... import name`` 阶段抛 503（会阻断 uvicorn 启动）；
改为注入占位函数，仅在实际调用时 raise_tm_premium_required。
"""
from __future__ import annotations

import sys
from typing import Any

try:
    from brickcore_tm import inbox_sse as _impl

    sys.modules[__name__] = _impl
except ImportError:  # pragma: no cover
    from app.modules.test_management._premium_missing import bind_missing

    bind_missing(
        globals(),
        [
            "acquire_inbox_stream_slot",
            "iter_inbox_sse",
            "release_inbox_stream_slot",
        ],
    )

    def __getattr__(name: str) -> Any:
        from app.modules.test_management.premium_gateway import raise_tm_premium_required

        raise_tm_premium_required()
