#!/usr/bin/env python3
"""将文档中心内置文档重置为 docs-site 源文件（清除 DB 正文覆盖）。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tortoise import Tortoise  # noqa: E402

from app.core.config import TORTOISE_ORM  # noqa: E402
from app.core.docs_catalog import get_builtin_doc_entries  # noqa: E402
from app.models.sys import PlatformDoc  # noqa: E402


async def main() -> int:
    await Tortoise.init(config=TORTOISE_ORM)
    entries = get_builtin_doc_entries()
    cleared = 0
    for doc_id in entries:
        doc = await PlatformDoc.get_or_none(builtin_id=doc_id, is_del=False)
        if doc and doc.content:
            doc.content = None
            doc.update_by = "sync-script"
            await doc.save(update_fields=["content", "update_by", "update_time"])
            cleared += 1
            print(f"  cleared: {doc_id}")
    await Tortoise.close_connections()
    print(f"Done. {cleared}/{len(entries)} overrides cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
