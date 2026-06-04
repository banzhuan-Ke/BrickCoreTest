#!/usr/bin/env python3
"""从 backend/app/mcp/server.py 生成 MCP 工具清单 Markdown，写入带标记的文档片段。"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PY = ROOT / "backend/app/mcp/server.py"
ASSISTANT_TOOLS_PY = ROOT / "backend/app/core/assistant_tools.py"
GENERATED_CATALOG = ROOT / "docs/generated/mcp-tools-catalog.md"

MARKER_COUNT = ("<!-- mcp-tools:auto:count:start -->", "<!-- mcp-tools:auto:count:end -->")
MARKER_CATALOG = ("<!-- mcp-tools:auto:catalog:start -->", "<!-- mcp-tools:auto:catalog:end -->")
MARKER_CONFIRM = ("<!-- mcp-tools:auto:confirm-pairs:start -->", "<!-- mcp-tools:auto:confirm-pairs:end -->")
MARKER_ASSISTANT = ("<!-- mcp-tools:auto:assistant-stats:start -->", "<!-- mcp-tools:auto:assistant-stats:end -->")
MARKER_PLAN_COUNT = ("<!-- mcp-tools:auto:plan-count:start -->", "<!-- mcp-tools:auto:plan-count:end -->")

CATEGORY_SPECS: list[tuple[str, set[str]]] = [
    (
        "1. 项目上下文（只读，较安全）",
        {
            "list_projects",
            "get_project",
            "get_project_overview",
            "list_environments",
            "list_modules",
        },
    ),
    (
        "2. 需求用例",
        {
            "list_requirements",
            "get_requirement",
            "list_requirement_cases",
            "get_generate_job",
            "get_requirement_latest_job",
            "preview_trigger_generate",
            "confirm_trigger_generate",
        },
    ),
    (
        "3. 接口自动化（只读）",
        {
            "list_api_definitions",
            "get_api_definition",
            "list_api_categories",
            "list_api_test_cases",
            "list_api_suites",
            "list_api_plans",
            "list_api_run_records",
            "list_api_cron_jobs",
            "list_mock_apis",
        },
    ),
    (
        "4. UI 自动化（只读）",
        {
            "list_ui_tasks",
            "list_ui_cases",
            "list_ui_suites",
            "list_online_devices",
            "list_ui_run_records",
            "list_ui_cron_jobs",
        },
    ),
    (
        "5. 性能测试（只读）",
        {
            "list_perf_scenes",
            "list_perf_records",
            "list_perf_cron_jobs",
            "list_perf_workers",
        },
    ),
    (
        "6. 功能用例库",
        {"search_functional_cases", "get_functional_case"},
    ),
    (
        "6.1 问答准确性评测",
        {"list_qa_eval_sets", "get_qa_eval_run"},
    ),
    (
        "7. 测试执行（preview → confirm）",
        {
            "preview_run_api_suite",
            "confirm_run_api_suite",
            "preview_run_api_plan",
            "confirm_run_api_plan",
            "preview_run_api_case",
            "confirm_run_api_case",
            "preview_run_ui_case",
            "confirm_run_ui_case",
            "preview_run_ui_task",
            "confirm_run_ui_task",
            "preview_run_ui_suite",
            "confirm_run_ui_suite",
            "preview_run_qa_eval",
            "confirm_run_qa_eval",
            "preview_run_perf_scene",
            "confirm_run_perf_scene",
            "get_execution_record",
        },
    ),
    (
        "8. 失败分析",
        {"list_recent_failures", "analyze_failure"},
    ),
    (
        "9. 其他",
        {"get_server_info"},
    ),
]

DESC_OVERRIDES: dict[str, str] = {
    "get_project_overview": "**推荐：一次获取项目全貌摘要**",
    "list_requirement_cases": "**列出需求工作区已生成用例（默认摘要，不含 steps 全文）**",
    "preview_trigger_generate": "**预览**提交用例生成（危险操作第 1 步）",
    "confirm_trigger_generate": "**确认**提交用例生成（危险操作第 2 步）",
    "preview_run_api_suite": "**预览**执行接口套件",
    "confirm_run_api_suite": "**确认**异步执行接口套件",
    "preview_run_api_plan": "**预览**执行接口测试计划",
    "confirm_run_api_plan": "**确认**异步执行接口测试计划",
    "preview_run_api_case": "**预览**执行单条接口用例（case_id 或 case_name + env_id）",
    "confirm_run_api_case": "**确认**同步执行单条接口用例",
    "preview_run_ui_case": "**预览**执行单条 Web UI 用例（+ device_id）",
    "confirm_run_ui_case": "**确认**执行单条 Web UI 用例",
    "preview_run_ui_task": "**预览**执行 UI 测试计划",
    "confirm_run_ui_task": "**确认**执行 UI 测试计划",
    "preview_run_ui_suite": "**预览**执行 Web UI 套件",
    "confirm_run_ui_suite": "**确认**执行 Web UI 套件",
    "preview_run_qa_eval": "**预览**提交问答准确性评测跑批",
    "confirm_run_qa_eval": "**确认**提交问答准确性评测跑批",
    "preview_run_perf_scene": "**预览**启动压测场景",
    "confirm_run_perf_scene": "**确认**启动压测场景",
    "get_execution_record": "查执行记录摘要（api_suite / api_plan / ui_plan / **ui_case** / perf）",
}

CONFIRM_EFFECTS: dict[str, str] = {
    "preview_trigger_generate": "提交需求文档 AI 批量生成用例",
    "preview_run_api_suite": "异步执行接口测试套件",
    "preview_run_api_plan": "异步执行接口测试计划",
    "preview_run_api_case": "同步执行单条接口用例",
    "preview_run_ui_case": "执行单条 Web UI 用例（占 Runner）",
    "preview_run_qa_eval": "提交问答准确性评测跑批",
    "preview_run_ui_task": "执行 UI 测试计划（占 Runner）",
    "preview_run_ui_suite": "执行 Web UI 套件（占 Runner）",
    "preview_run_perf_scene": "启动压测场景",
}

DOC_TARGETS: list[Path] = [
    ROOT / "docs/其他文档/MCP-Server使用说明.md",
    ROOT / "docs-site/guide/mcp-server.md",
    ROOT / "docs/平台优化计划.md",
]


def parse_register_tools(server_text: str) -> dict[str, str]:
    tools: dict[str, str] = {}
    i = 0
    lines = server_text.splitlines()
    while i < len(lines):
        line = lines[i]
        if "_register(" not in line:
            i += 1
            continue
        block_lines = [line]
        while not block_lines[-1].rstrip().endswith(")"):
            i += 1
            if i >= len(lines):
                break
            block_lines.append(lines[i])
        block = " ".join(part.strip() for part in block_lines)
        name_match = re.search(r'_register\s*\(\s*"([^"]+)"', block)
        desc_match = re.search(r',\s*"([^"]*)"\s*\)\s*$', block)
        if name_match:
            name = name_match.group(1)
            desc = desc_match.group(1) if desc_match else name
            tools[name] = desc
        i += 1
    return tools


def parse_get_server_info(server_text: str) -> tuple[str, str] | None:
    match = re.search(
        r'@mcp\.tool\(name="([^"]+)"\)\s*\nasync def \1\([^)]*\)[^:]*:\s*\n\s*"""([^"]*)"""',
        server_text,
    )
    if match:
        return match.group(1), match.group(2)
    return None


def parse_assistant_tool_counts(text: str) -> tuple[int, int]:
    readonly_match = re.search(
        r"READONLY_TOOL_NAMES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)",
        text,
        re.DOTALL,
    )
    preview_match = re.search(
        r"PREVIEW_TOOL_NAMES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)",
        text,
        re.DOTALL,
    )
    if not readonly_match or not preview_match:
        raise ValueError("无法解析 assistant_tools.py 中的工具白名单")
    readonly = re.findall(r'"([^"]+)"', readonly_match.group(1))
    preview = re.findall(r'"([^"]+)"', preview_match.group(1))
    return len(readonly), len(preview)


def display_description(name: str, description: str) -> str:
    return DESC_OVERRIDES.get(name, description)


def render_table(tools: dict[str, str], names: list[str]) -> str:
    rows = []
    for name in names:
        desc = display_description(name, tools[name])
        tool_cell = f"**`{name}`**" if name in {"get_project_overview", "list_requirement_cases"} else f"`{name}`"
        rows.append(f"| {tool_cell} | {desc} |")
    return "\n".join(
        [
            "| 工具 | 说明 |",
            "|------|------|",
            *rows,
        ]
    )


def build_catalog_markdown(tools: dict[str, str]) -> str:
    sections: list[str] = []
    assigned: set[str] = set()
    for title, names in CATEGORY_SPECS:
        ordered = [name for name in tools if name in names]
        if not ordered:
            continue
        assigned.update(ordered)
        body = render_table(tools, ordered)
        if title == "6.1 问答准确性评测":
            body += "\n| `preview_run_qa_eval` / `confirm_run_qa_eval` | 提交跑批（见 §7） |"
        sections.append(f"### {title}\n\n{body}")
    missing = sorted(set(tools) - assigned)
    if missing:
        raise ValueError(f"以下工具未分配到文档分组: {', '.join(missing)}")
    return "\n\n".join(sections)


def build_confirm_pairs_markdown(tools: dict[str, str]) -> str:
    rows = []
    for preview, effect in CONFIRM_EFFECTS.items():
        confirm = preview.replace("preview_", "confirm_", 1)
        if confirm not in tools:
            raise ValueError(f"缺少与 {preview} 对应的确认工具 {confirm}")
        rows.append(f"| `{preview}` | `{confirm}` | {effect} |")
    return "\n".join(
        [
            "| 预览工具 | 确认工具 | 会做什么 |",
            "|----------|----------|----------|",
            *rows,
        ]
    )


def replace_marked_block(text: str, start: str, end: str, new_body: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{new_body.rstrip()}\n{end}"
    if not pattern.search(text):
        raise ValueError(f"未找到标记块: {start} ... {end}")
    return pattern.sub(replacement, text, count=1)


def load_tools() -> dict[str, str]:
    server_text = SERVER_PY.read_text(encoding="utf-8")
    tools = parse_register_tools(server_text)
    extra = parse_get_server_info(server_text)
    if extra:
        tools[extra[0]] = extra[1]
    return tools


def generate_fragments(tools: dict[str, str], assistant_text: str) -> dict[str, str]:
    readonly_count, preview_count = parse_assistant_tool_counts(assistant_text)
    total = len(tools)
    today = date.today().isoformat()
    return {
        "count": (
            f"当前 MCP Server 提供 **{total} 个工具**，分 9 组"
            f"（与平台内助手共用 `mcp/tools.py`；清单由 `scripts/generate_mcp_tools_docs.py` 于 {today} 同步）："
        ),
        "catalog": build_catalog_markdown(tools),
        "confirm_pairs": build_confirm_pairs_markdown(tools),
        "assistant_stats": (
            f"与对外 MCP 共用同一套后端工具（MCP 共 **{total}** 个，"
            f"助手只读白名单 **{readonly_count}** 个 + **{preview_count}** 个 preview）；"
            f"外部 Kimi/Cursor 仍走 MCP 接入。"
        ),
        "plan_count": (
            f"当前 **{total} 个 MCP 工具**（与 `server.py` 注册一致，由 `scripts/generate_mcp_tools_docs.py` 同步）。"
            f"说明：[MCP-Server使用说明.md](./其他文档/MCP-Server使用说明.md)"
        ),
    }


def write_generated_catalog(tools: dict[str, str], fragments: dict[str, str]) -> None:
    GENERATED_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_CATALOG.write_text(
        "\n".join(
            [
                "# MCP 工具清单（自动生成）",
                "",
                f"> 源文件：`backend/app/mcp/server.py`",
                f"> 生成命令：`python scripts/generate_mcp_tools_docs.py`",
                "",
                fragments["count"],
                "",
                fragments["catalog"],
                "",
                "## 危险操作 preview → confirm",
                "",
                fragments["confirm_pairs"],
                "",
            ]
        ),
        encoding="utf-8",
    )


def apply_patches(fragments: dict[str, str]) -> list[Path]:
    changed: list[Path] = []

    mcp_doc = ROOT / "docs/其他文档/MCP-Server使用说明.md"
    text = mcp_doc.read_text(encoding="utf-8")
    text = replace_marked_block(text, *MARKER_COUNT, fragments["count"])
    text = replace_marked_block(text, *MARKER_CATALOG, fragments["catalog"])
    text = replace_marked_block(text, *MARKER_CONFIRM, fragments["confirm_pairs"])
    mcp_doc.write_text(text, encoding="utf-8")
    changed.append(mcp_doc)

    guide = ROOT / "docs-site/guide/mcp-server.md"
    guide_text = guide.read_text(encoding="utf-8")
    guide_text = replace_marked_block(guide_text, *MARKER_ASSISTANT, fragments["assistant_stats"])
    guide.write_text(guide_text, encoding="utf-8")
    changed.append(guide)

    plan = ROOT / "docs/平台优化计划.md"
    plan_text = plan.read_text(encoding="utf-8")
    plan_text = replace_marked_block(plan_text, *MARKER_PLAN_COUNT, fragments["plan_count"])
    plan.write_text(plan_text, encoding="utf-8")
    changed.append(plan)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate MCP tool catalog docs from server.py")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查文档是否与 server.py 一致，不写入文件",
    )
    args = parser.parse_args()

    if not SERVER_PY.is_file():
        print(f"找不到 {SERVER_PY}", file=sys.stderr)
        return 1

    tools = load_tools()
    assistant_text = ASSISTANT_TOOLS_PY.read_text(encoding="utf-8")
    fragments = generate_fragments(tools, assistant_text)

    if args.check:
        current_catalog = build_catalog_markdown(tools)
        for path in DOC_TARGETS:
            if not path.is_file():
                print(f"缺少文档: {path}", file=sys.stderr)
                return 1
        mcp_doc = (ROOT / "docs/其他文档/MCP-Server使用说明.md").read_text(encoding="utf-8")
        if MARKER_CATALOG[0] not in mcp_doc:
            print("MCP 文档缺少 auto 标记，请先运行一次不带 --check 的生成", file=sys.stderr)
            return 1
        existing = re.search(
            re.escape(MARKER_CATALOG[0]) + r"(.*?)" + re.escape(MARKER_CATALOG[1]),
            mcp_doc,
            re.DOTALL,
        )
        if not existing or existing.group(1).strip() != current_catalog.strip():
            print("MCP 工具清单文档已过期，请运行: python scripts/generate_mcp_tools_docs.py", file=sys.stderr)
            return 1
        print(f"OK: {len(tools)} MCP tools documented")
        return 0

    write_generated_catalog(tools, fragments)
    changed = apply_patches(fragments)
    print(f"Generated catalog for {len(tools)} tools")
    for path in changed:
        print(f"  updated {path.relative_to(ROOT)}")
    print(f"  updated {GENERATED_CATALOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
