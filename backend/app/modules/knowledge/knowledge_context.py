"""CE stubs for knowledge context helpers."""
from __future__ import annotations

from typing import Any


async def append_knowledge_context_to_prompt(*args, **kwargs) -> tuple[str, dict[str, Any]]:
    prompt = kwargs.get("user_prompt") or ""
    return prompt, {"enabled": False, "refs": []}


async def build_knowledge_context(*args, **kwargs) -> dict[str, Any]:
    return {"enabled": False, "knowledge_context": "", "refs": []}


async def estimate_knowledge_refs(*args, **kwargs) -> dict[str, Any]:
    return {"enabled": False, "refs": [], "count": 0}
