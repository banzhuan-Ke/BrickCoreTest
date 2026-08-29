"""兼容层：实现位于 brickcore_tm.export_service（Pro 内置 / CE 扩展包）。

展平/筛选工具始终开源，见 matrix_export_utils。
"""
from __future__ import annotations

from typing import Any

from app.modules.test_management.matrix_export_utils import (  # noqa: F401
    filter_flat_rows,
    flatten_matrix_rows,
)

try:
    from brickcore_tm.export_service import (  # noqa: F401
        build_quality_summary,
        build_release_export_package,
        build_traceability_csv,
    )
except ImportError:  # pragma: no cover

    def __getattr__(name: str) -> Any:
        from app.modules.test_management.premium_gateway import raise_tm_premium_required

        if name in ("flatten_matrix_rows", "filter_flat_rows"):
            raise AttributeError(name)
        raise_tm_premium_required()
