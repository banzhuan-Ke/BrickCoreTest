"""部署版本识别（文档目录与部分文案分支）。"""
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
    """识别部署版本（Docker 环境变量 BRICKCORE_EDITION 或本地目录结构）。"""
    raw = os.getenv("BRICKCORE_EDITION", "").strip().lower()
    if raw in ("ce", "community", "oss"):
        return True
    if raw in ("pro", "enterprise", "commercial"):
        return False
    return not (_repo_root() / "runner" / "WebEngine").is_dir()


QA_EVAL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_qa_eval_sets",
        "get_qa_eval_run",
        "preview_run_qa_eval",
        "confirm_run_qa_eval",
    }
)


def qa_eval_feature_enabled() -> bool:
    """问答准确性评测能力开关。"""
    return not is_community_edition()
