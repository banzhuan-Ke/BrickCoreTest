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
    """识别开源发行版。

    - Docker：在 compose 中设置 ``BRICKCORE_EDITION=ce``。
    - 本机：未设环境变量时，根据是否存在 ``runner/WebEngine`` 判断。
    """
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

KNOWLEDGE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_test_knowledge",
        "ask_test_knowledge",
        "list_knowledge_folders",
    }
)


@lru_cache(maxsize=1)
def knowledge_feature_enabled() -> bool:
    """通用资料库能力开关。开源发行版默认开启，可用环境变量关闭。"""
    raw = os.getenv("BRICKCORE_KNOWLEDGE_ENABLED", "").strip().lower()
    if raw in ("1", "true", "on", "yes"):
        return True
    if raw in ("0", "false", "off", "no"):
        return False
    return True


def qa_eval_feature_enabled() -> bool:
    """扩展评测能力开关；开源发行版默认关闭。"""
    return False


# 行业资料库扩展包关联的 AI 场景（未启用扩展包时不暴露）
KNOWLEDGE_PACK_PROMPT_SCENES: frozenset[str] = frozenset(
    {
        "knowledge_pack_scheme_narrative",
        "knowledge_pack_report_narrative",
    }
)


def knowledge_pack_addon_enabled() -> bool:
    """行业资料库扩展包：开源发行版不启用。"""
    return False


# 兼容 Pro 旧符号名（sync 后通用路由仍可能引用）
def knowledge_digitech_pack_enabled() -> bool:
    return knowledge_pack_addon_enabled()
