"""CE stub for knowledge retrieval."""
from __future__ import annotations

from typing import Any


async def retrieve_knowledge(*args, **kwargs) -> dict[str, Any]:
    return {"items": [], "total": 0, "sources": [], "enabled": False}
