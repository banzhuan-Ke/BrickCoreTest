"""
社区版 / 商业版识别（文档目录、部分文案分支用）。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for root in (here.parents[2], here.parents[3]):
        if (root / "docs-site" / "index.md").is_file():
            return root
    return here.parents[3]


@lru_cache(maxsize=1)
def is_community_edition() -> bool:
    """CE：显式环境变量，或仓库内无 runner/WebEngine 源码目录。"""
    raw = os.getenv("BRICKCORE_EDITION", "").strip().lower()
    if raw in ("ce", "community", "oss"):
        return True
    if raw in ("pro", "enterprise", "commercial"):
        return False
    return not (_repo_root() / "runner" / "WebEngine").is_dir()
