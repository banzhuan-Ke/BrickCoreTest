"""CE stubs for non-open-sourced knowledge models."""
from __future__ import annotations


class _DummyQuery:
    async def delete(self) -> int:
        return 0


class AiKnowledgeChunk:
    @classmethod
    def filter(cls, **kwargs) -> _DummyQuery:
        return _DummyQuery()
