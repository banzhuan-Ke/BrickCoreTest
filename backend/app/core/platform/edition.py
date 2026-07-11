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
    """识别社区版。

    - Docker 部署：backend 镜像仅含 backend+docs-site，须在 compose 中设
      ``BRICKCORE_EDITION``（Pro 用 ``pro``，CE 用 ``ce``）。
    - 本机全量仓库：未设环境变量时，根据是否存在 ``runner/WebEngine`` 判断。
    """
    raw = os.getenv("BRICKCORE_EDITION", "").strip().lower()
    if raw in ("ce", "community", "oss"):
        return True
    if raw in ("pro", "enterprise", "commercial"):
        return False
    return not (_repo_root() / "runner" / "WebEngine").is_dir()



@lru_cache(maxsize=1)
def knowledge_feature_enabled() -> bool:
    """通用资料库能力开关。"""
    raw = os.getenv("BRICKCORE_KNOWLEDGE_ENABLED", "").strip().lower()
    if raw in ("1", "true", "on", "yes"):
        return True
    if raw in ("0", "false", "off", "no"):
        return False
    return not is_community_edition()



# Pro 定制资料库文档包关联的 AI 场景（未启用时不暴露给 CE / 未配置 Pro 环境）
KNOWLEDGE_PACK_PROMPT_SCENES: frozenset[str] = frozenset(
    {
        "digitech_scheme_narrative",
        "digitech_report_narrative",
    }
)


def knowledge_digitech_pack_enabled() -> bool:
    """Pro 定制资料库文档包：CE 永不启用；需非 CE 且 ``BRICKCORE_KNOWLEDGE_PACK`` 已配置。"""
    if is_community_edition():
        return False
    raw = os.getenv("BRICKCORE_KNOWLEDGE_PACK", "").strip().lower()
    return bool(raw) and raw not in ("0", "false", "off", "none")
