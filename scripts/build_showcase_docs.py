#!/usr/bin/env python3
"""Export doc-center (CE showcase set) to showcase/docs for static hosting."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "showcase" / "docs"
CONTENT = OUT / "content"

SOURCES: list[tuple[str, str, str]] = [
    ("home", "scripts/ce-stubs/docs-index-ce.md", "使用说明"),
    ("quick-start", "docs-site/guide/quick-start.md", "平台概览"),
    ("highlights", "scripts/ce-stubs/docs-highlights-ce.md", "亮点功能"),
    ("project-setup", "docs-site/guide/project-setup.md", "项目与环境"),
    ("test-catalog", "docs-site/guide/test-catalog.md", "测试目录"),
    ("ui-automation", "scripts/ce-stubs/docs-ui-automation-ce.md", "UI 自动化"),
    ("runner-client", "docs-site/guide/runner-client.md", "执行器使用说明"),
    ("runner-packaging", "scripts/ce-stubs/docs-runner-packaging-ce.md", "执行器获取与发布"),
    ("api-automation", "docs-site/guide/api-automation.md", "接口自动化"),
    ("data-factory", "docs-site/guide/data-factory.md", "数据工厂"),
    ("api-auth", "docs-site/guide/api-auth.md", "Token 授权"),
    ("perf-testing", "docs-site/guide/perf-testing.md", "性能测试"),
    ("ai-testing", "docs-site/guide/ai-testing.md", "AI 测试"),
    ("platform-assistant", "docs-site/guide/platform-assistant.md", "平台内 AI 助手"),
    ("mcp-server", "docs-site/guide/mcp-server.md", "MCP 外部接入"),
    ("system-admin", "scripts/ce-stubs/docs-system-admin-ce.md", "系统管理"),
]

LINK_REPLACEMENTS = [
    (re.compile(r"\]\(\.\./docs-site/guide/([a-z0-9-]+)\.md([^)]*)\)"), r"](#\1\2)"),
    (re.compile(r"\]\(\.\./\.\./README\.md([^)]*)\)"), r"](https://gitee.com/BanZhuanKeOrz/BrickCore\1)"),
    (re.compile(r"\]\(guide/([a-z0-9-]+)\.md([^)]*)\)"), r"](#\1\2)"),
    (re.compile(r"\]\(([a-z0-9-]+)\.md(?:#([^)]*))?\)"), r"](#\1)"),
    (re.compile(r"\]\(\.\./docs-site/[^)]+\)"), r"](#home)"),
]


def convert_links(text: str) -> str:
    for pattern, repl in LINK_REPLACEMENTS:
        text = pattern.sub(repl, text)
    return text


def main() -> None:
    CONTENT.mkdir(parents=True, exist_ok=True)
    for doc_id, rel, _title in SOURCES:
        src = ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(rel)
        body = convert_links(src.read_text(encoding="utf-8"))
        (CONTENT / f"{doc_id}.md").write_text(body, encoding="utf-8")

    def child(doc_id: str, title: str) -> dict:
        return {"id": doc_id, "title": title, "file": f"content/{doc_id}.md"}

    manifest = {
        "title": "BrickCore 使用说明",
        "updated": date.today().isoformat(),
        "platformUrl": "http://43.142.83.156/",
        "showcaseUrl": "http://43.142.83.156/showcase/",
        "groups": [
            {
                "id": "group-start",
                "title": "快速开始",
                "children": [child(d, t) for d, _, t in SOURCES[:5]],
            },
            {
                "id": "group-guide",
                "title": "功能模块",
                "children": [child(d, t) for d, _, t in SOURCES[5:15]],
            },
            {
                "id": "group-system",
                "title": "系统管理",
                "children": [child(d, t) for d, _, t in SOURCES[15:]],
            },
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Showcase docs: {len(SOURCES)} files -> {CONTENT}")
    print(f"Manifest: {OUT / 'manifest.json'}")


if __name__ == "__main__":
    main()
