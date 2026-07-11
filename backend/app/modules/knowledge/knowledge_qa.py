"""CE stub for knowledge QA."""
from __future__ import annotations

from typing import Any


def normalize_qa_mode(mode: str | None) -> str:
    value = (mode or "smart").strip().lower()
    return value if value in {"retrieve", "smart"} else "smart"


async def ask_knowledge(*args, **kwargs) -> dict[str, Any]:
    return {
        "mode": normalize_qa_mode(kwargs.get("mode")),
        "answer": "",
        "items": [],
        "sources": [],
        "enabled": False,
        "message": "Knowledge base is not available in CE.",
    }
