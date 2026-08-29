"""CE / 未装包时的占位：调用高级能力时统一抛出 tm_premium_required。"""
from __future__ import annotations

from typing import Any, Callable

from app.modules.test_management.premium_gateway import (
    TM_PREMIUM_REQUIRED_CODE,
    get_tm_premium_info,
    raise_tm_premium_required,
)


class TmPremiumMissingError(RuntimeError):
    def __init__(self, message: str | None = None):
        info = get_tm_premium_info()
        super().__init__(message or info.get("message") or TM_PREMIUM_REQUIRED_CODE)
        self.info = info


def _missing_call(name: str) -> Callable[..., Any]:
    def _fn(*_args: Any, **_kwargs: Any) -> Any:
        raise_tm_premium_required()

    _fn.__name__ = name
    _fn.__qualname__ = name
    return _fn


def bind_missing(module_globals: dict[str, Any], names: list[str]) -> None:
    """向模块 globals 注入占位函数（仅当扩展包不可用时使用）。"""
    for name in names:
        if name not in module_globals:
            module_globals[name] = _missing_call(name)
