"""资料库业务操作审计（补充中间件，写入可读性更强的 path_name）"""
from __future__ import annotations

from typing import Any, Optional

from app.models.sys import OperationLog


async def log_knowledge_operation(
    user_info: dict,
    *,
    action: str,
    path_name: str,
    path: str,
    method: str = "POST",
    params: Optional[dict[str, Any]] = None,
    status_code: int = 200,
    ip: str = "",
) -> None:
    user_id = int(user_info.get("user_id") or user_info.get("id") or 0)
    username = str(user_info.get("username") or user_info.get("sub") or "system")
    safe_params = params if isinstance(params, dict) else {}
    try:
        await OperationLog.create(
            user_id=user_id,
            username=username,
            action=action,
            module="迭代测试资料库",
            method=method,
            path=path[:255],
            path_name=path_name[:100],
            params=safe_params,
            ip=ip or "",
            status_code=status_code,
        )
    except Exception:
        pass
