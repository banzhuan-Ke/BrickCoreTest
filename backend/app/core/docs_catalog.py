"""
平台内置文档目录（路径白名单，禁止任意文件读取）
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.core.edition import is_community_edition


def _resolve_repo_root() -> Path:
    """定位 docs-site 所在目录（本地 monorepo 根或 Docker /app）。"""
    here = Path(__file__).resolve()
    for root in (here.parents[2], here.parents[3]):
        if (root / "docs-site" / "index.md").is_file():
            return root
    return here.parents[3]


_REPO_ROOT = _resolve_repo_root()

# id -> (相对仓库根的路径, 标题)
BUILTIN_DOC_ENTRIES: dict[str, tuple[str, str]] = {
    "home": ("docs-site/index.md", "使用说明"),
    "quick-start": ("docs-site/guide/quick-start.md", "平台概览"),
    "highlights": ("docs-site/guide/highlights.md", "亮点功能"),
    "project-setup": ("docs-site/guide/project-setup.md", "项目与环境"),
    "test-catalog": ("docs-site/guide/test-catalog.md", "测试目录"),
    "ui-automation": ("docs-site/guide/ui-automation.md", "UI 自动化"),
    "runner-client": ("docs-site/guide/runner-client.md", "执行器使用说明"),
    "runner-packaging": ("docs-site/guide/runner-packaging.md", "执行器打包说明"),
    "runner-troubleshooting": ("docs-site/guide/runner-troubleshooting.md", "Runner 排查指南"),
    "runner-linux-server": ("docs-site/guide/runner-linux-server.md", "Linux 无头 Runner"),
    "api-automation": ("docs-site/guide/api-automation.md", "接口自动化"),
    "data-factory": ("docs-site/guide/data-factory.md", "数据工厂"),
    "api-auth": ("docs-site/guide/api-auth.md", "Token 授权"),
    "perf-testing": ("docs-site/guide/perf-testing.md", "性能测试"),
    "ai-testing": ("docs-site/guide/ai-testing.md", "AI 测试"),
    "browser-lab": ("docs-site/guide/browser-lab.md", "智能浏览器"),
    "platform-assistant": ("docs-site/guide/platform-assistant.md", "平台内 AI 助手"),
    "mcp-server": ("docs-site/guide/mcp-server.md", "MCP 外部接入"),
    "docker-deploy": ("docs-site/guide/docker-deploy.md", "Docker 部署"),
    "release-notes": ("docs-site/guide/release-notes.md", "版本更新记录"),
    "system-admin": ("docs-site/guide/system-admin.md", "系统管理"),
}

# 公开部署：隐藏无源码支撑的条目；打包页改标题
_CE_HIDDEN_DOC_IDS = frozenset({"runner-linux-server"})
_CE_DOC_TITLE_OVERRIDES: dict[str, str] = {
    "runner-packaging": "执行器获取与发布",
}

BUILTIN_DOC_TREE: list[dict[str, Any]] = [
    {
        "id": "group-start",
        "title": "快速开始",
        "type": "group",
        "children": [
            {"id": "home", "title": "使用说明", "type": "builtin"},
            {"id": "quick-start", "title": "平台概览", "type": "builtin"},
            {"id": "highlights", "title": "亮点功能", "type": "builtin"},
            {"id": "release-notes", "title": "版本更新记录", "type": "builtin"},
            {"id": "project-setup", "title": "项目与环境", "type": "builtin"},
            {"id": "test-catalog", "title": "测试目录", "type": "builtin"},
        ],
    },
    {
        "id": "group-guide",
        "title": "功能模块",
        "type": "group",
        "children": [
            {"id": "ui-automation", "title": "UI 自动化", "type": "builtin"},
            {"id": "api-automation", "title": "接口自动化", "type": "builtin"},
            {"id": "data-factory", "title": "数据工厂", "type": "builtin"},
            {"id": "api-auth", "title": "Token 授权", "type": "builtin"},
            {"id": "perf-testing", "title": "性能测试", "type": "builtin"},
            {"id": "ai-testing", "title": "AI 测试", "type": "builtin"},
            {"id": "browser-lab", "title": "智能浏览器", "type": "builtin"},
            {"id": "platform-assistant", "title": "平台内 AI 助手", "type": "builtin"},
            {"id": "mcp-server", "title": "MCP 外部接入", "type": "builtin"},
        ],
    },
    {
        "id": "group-runner",
        "title": "执行器与部署",
        "type": "group",
        "children": [
            {"id": "runner-client", "title": "执行器使用说明", "type": "builtin"},
            {"id": "runner-packaging", "title": "执行器打包说明", "type": "builtin"},
            {"id": "runner-troubleshooting", "title": "Runner 排查指南", "type": "builtin"},
            {"id": "runner-linux-server", "title": "Linux 无头 Runner", "type": "builtin"},
            {"id": "docker-deploy", "title": "Docker 部署", "type": "builtin"},
        ],
    },
    {
        "id": "group-system",
        "title": "系统管理",
        "type": "group",
        "children": [
            {"id": "system-admin", "title": "系统管理", "type": "builtin"},
        ],
    },
]


def _apply_ce_tree(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group in tree:
        children: list[dict[str, Any]] = []
        for child in group.get("children", []):
            cid = child["id"]
            if cid in _CE_HIDDEN_DOC_IDS:
                continue
            title = _CE_DOC_TITLE_OVERRIDES.get(cid, child["title"])
            children.append({**child, "title": title})
        if children:
            out.append({**group, "children": children})
    return out


def get_builtin_doc_tree() -> list[dict[str, Any]]:
    tree = copy.deepcopy(BUILTIN_DOC_TREE)
    if is_community_edition():
        return _apply_ce_tree(tree)
    return tree


def get_builtin_doc_entries() -> dict[str, tuple[str, str]]:
    entries = dict(BUILTIN_DOC_ENTRIES)
    if is_community_edition():
        for doc_id, title in _CE_DOC_TITLE_OVERRIDES.items():
            if doc_id in entries:
                rel, _ = entries[doc_id]
                entries[doc_id] = (rel, title)
    return entries


BUILTIN_GROUP_IDS = {g["id"] for g in BUILTIN_DOC_TREE}
BUILTIN_DOC_IDS = set(BUILTIN_DOC_ENTRIES.keys())


def is_builtin_group(entry_id: str) -> bool:
    return entry_id in BUILTIN_GROUP_IDS


def is_builtin_doc(entry_id: str) -> bool:
    if entry_id in _CE_HIDDEN_DOC_IDS and is_community_edition():
        return False
    return entry_id in BUILTIN_DOC_IDS


def is_builtin_entry(entry_id: str) -> bool:
    return is_builtin_group(entry_id) or is_builtin_doc(entry_id)


def resolve_builtin_path(doc_id: str) -> Path:
    entries = get_builtin_doc_entries()
    entry = entries.get(doc_id)
    if not entry:
        raise FileNotFoundError(f"未知文档: {doc_id}")
    rel, _title = entry
    path = (_REPO_ROOT / rel).resolve()
    if not str(path).startswith(str(_REPO_ROOT.resolve())):
        raise PermissionError("非法路径")
    if not path.is_file():
        raise FileNotFoundError(f"文档文件不存在: {rel}")
    return path


def read_builtin_markdown(doc_id: str) -> tuple[str, str]:
    entries = get_builtin_doc_entries()
    path = resolve_builtin_path(doc_id)
    title = entries[doc_id][1]
    return title, path.read_text(encoding="utf-8")


def _override_title(entry_id: str, default_title: str, overrides: dict[str, Any]) -> str:
    # 公开部署以内置 docs-site 文件为准，避免历史 DB 覆盖带入旧正文/标题
    if is_community_edition():
        return default_title
    row = overrides.get(entry_id)
    if row and getattr(row, "title", None):
        return row.title
    return default_title


def _builtin_has_content_override(row: Any | None) -> bool:
    if not row:
        return False
    if is_community_edition():
        return bool(getattr(row, "is_hidden", False))
    return True


def merge_builtin_tree(overrides: dict[str, Any]) -> list[dict[str, Any]]:
    """合并内置目录与数据库覆盖（标题、隐藏）。"""
    result: list[dict[str, Any]] = []
    for group in get_builtin_doc_tree():
        gid = group["id"]
        go = overrides.get(gid)
        if go and getattr(go, "is_hidden", False):
            continue
        children: list[dict[str, Any]] = []
        for child in group.get("children", []):
            cid = child["id"]
            co = overrides.get(cid)
            if co and getattr(co, "is_hidden", False):
                continue
            children.append({
                **child,
                "title": _override_title(cid, child["title"], overrides),
                "has_override": _builtin_has_content_override(co),
            })
        if not children:
            continue
        result.append({
            **group,
            "title": _override_title(gid, group["title"], overrides),
            "children": children,
            "has_override": _builtin_has_content_override(go),
        })
    return result


def build_manage_builtin_items(overrides: dict[str, Any]) -> list[dict[str, Any]]:
    """管理列表中的内置条目（含已隐藏，便于恢复）。"""
    entries = get_builtin_doc_entries()
    items: list[dict[str, Any]] = []
    for group in get_builtin_doc_tree():
        gid = group["id"]
        go = overrides.get(gid)
        items.append({
            "builtin_id": gid,
            "title": _override_title(gid, group["title"], overrides),
            "type": "builtin_group",
            "doc_type": "group",
            "is_hidden": bool(go and go.is_hidden),
            "has_override": _builtin_has_content_override(go),
            "content": "",
            "sort_order": go.sort_order if go else 0,
        })
        for child in group.get("children", []):
            cid = child["id"]
            co = overrides.get(cid)
            default_title = entries.get(cid, ("", child["title"]))[1]
            if is_community_edition():
                try:
                    _, file_md = read_builtin_markdown(cid)
                except (FileNotFoundError, PermissionError):
                    file_md = ""
                content = file_md
            else:
                content = co.content if co and co.content else ""
            items.append({
                "builtin_id": cid,
                "title": _override_title(cid, default_title, overrides),
                "type": "builtin",
                "doc_type": "markdown",
                "is_hidden": bool(co and co.is_hidden),
                "has_override": _builtin_has_content_override(co),
                "content": content,
                "sort_order": co.sort_order if co else 0,
            })
    return items
