"""报告生成共享工具（iteration_report 与 Pro 定制包共用）"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from app.core.shared.report_summary_context import build_report_execution_data


def extract_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    for match in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text):
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def format_counter_text(counter: dict[str, int]) -> str:
    if not counter:
        return "无"
    return "；".join(f"{k}:{v}" for k, v in sorted(counter.items(), key=lambda x: -x[1]))


def pass_rate_display(exec_data: dict[str, Any]) -> str:
    has_exec = bool(exec_data.get("exec_records")) or bool(exec_data.get("total_cases"))
    if not has_exec:
        return "-"
    rate = exec_data.get("pass_rate")
    if rate is None:
        return "-"
    return f"{rate}%"


def format_multiline_lines(text: str) -> list[str]:
    """将 AI 段落或编号列表拆成多行，供 Word {%p for line in ... %} 渲染。"""
    if not text:
        return []
    raw = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [ln.strip() for ln in raw.split("\n") if ln.strip()]
    parts = re.split(r"(?=\d+[.、．]\s*)", raw)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) > 1:
        return parts
    if "；" in raw:
        return [p.strip() for p in raw.split("；") if p.strip()]
    return [raw]


def build_bug_analysis_text(knowledge: dict[str, Any]) -> str:
    """预格式化缺陷分析段落，供自定义模板用 {{ bug_analysis_text }} 一行引用。"""
    total = int(knowledge.get("bug_total") or 0)
    open_count = int(knowledge.get("bug_open_count") or 0)
    closed_count = int(knowledge.get("bug_closed_count") or 0)
    summary = (knowledge.get("bug_export_summary") or "").strip()
    rows = build_bug_stats_rows(knowledge)
    if total <= 0 and not summary and not rows:
        return "本轮未关联 Bug 导出或无有效缺陷数据。"
    lines = [f"Bug 总数：{total}，未关闭：{open_count}，已关闭：{closed_count}。"]
    if summary:
        lines.append(summary)
    if rows:
        lines.append("缺陷分布：")
        for row in rows:
            lines.append(f"- {row['dimension']} / {row['label']}：{row['count']}")
    return "\n".join(lines)


def build_bug_analysis_lines(knowledge: dict[str, Any]) -> list[str]:
    return format_multiline_lines(build_bug_analysis_text(knowledge))


def build_counter_table_rows(dimensions: list[tuple[str, dict[str, int]]]) -> list[dict[str, Any]]:
    """将多组计数器展开为 Word 表格行（dimension / label / count）。"""
    rows: list[dict[str, Any]] = []
    for dim_label, counter in dimensions:
        if not isinstance(counter, dict) or not counter:
            continue
        for label, count in sorted(counter.items(), key=lambda x: -x[1]):
            rows.append({"dimension": dim_label, "label": str(label), "count": int(count)})
    return rows


def build_pct_table_rows(counter: dict[str, int]) -> list[dict[str, Any]]:
    """Bug 统计表行：label / count / pct（占比百分比字符串）。"""
    if not counter:
        return []
    total = sum(int(v) for v in counter.values()) or 1
    rows: list[dict[str, Any]] = []
    for label, count in sorted(counter.items(), key=lambda x: -int(x[1])):
        c = int(count)
        rows.append(
            {
                "label": str(label),
                "count": c,
                "pct": f"{c / total * 100:.1f}%",
            }
        )
    return rows


def build_bug_stats_rows(knowledge: dict[str, Any]) -> list[dict[str, Any]]:
    """合并各维度 Bug 计数，供 Word 表格循环渲染。"""
    dimensions = (
        ("严重程度", knowledge.get("bug_by_severity") or {}),
        ("状态", knowledge.get("bug_by_status") or {}),
        ("解决方案", knowledge.get("bug_by_resolution") or {}),
        ("创建人", knowledge.get("bug_by_opened_by") or {}),
        ("归属/指派人", knowledge.get("bug_by_assigned_to") or {}),
        ("解决人", knowledge.get("bug_by_resolved_by") or {}),
        ("优先级", knowledge.get("bug_by_priority") or {}),
        ("模块", knowledge.get("bug_by_module") or {}),
    )
    return build_counter_table_rows(list(dimensions))


def build_bug_detail_rows(bugs: list[dict[str, Any]], *, limit: int = 50) -> list[dict[str, str]]:
    """Bug 明细节选，供 Word 表格循环（可选，默认通用模板不含）。"""
    rows: list[dict[str, str]] = []
    for b in bugs or []:
        if len(rows) >= limit:
            break
        if not isinstance(b, dict):
            continue
        rows.append(
            {
                "bug_id": str(b.get("bug_id") or ""),
                "title": str(b.get("title") or ""),
                "module": str(b.get("module") or b.get("module_merged") or ""),
                "severity": str(b.get("severity") or ""),
                "status": str(b.get("status") or ""),
                "resolution": str(b.get("resolution") or ""),
                "opened_by": str(b.get("opened_by") or ""),
                "assigned_to": str(b.get("assigned_to") or ""),
                "resolved_by": str(b.get("resolved_by") or ""),
            }
        )
    return rows


SOURCE_REF_KIND_LABELS: dict[str, str] = {
    "folder": "迭代文件夹",
    "document": "资料文档",
    "template": "输出模板",
    "exec_record": "执行记录",
}


def build_source_refs(
    *,
    folder: Any | None,
    knowledge: dict[str, Any],
    template_inspect: dict[str, Any],
    exec_data: dict[str, Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if folder is not None:
        refs.append(
            {
                "kind": "folder",
                "kind_label": SOURCE_REF_KIND_LABELS["folder"],
                "title": getattr(folder, "name", "") or "",
                "detail": getattr(folder, "iteration_label", "") or "",
            }
        )
    for r in knowledge.get("refs") or []:
        if not isinstance(r, dict):
            continue
        refs.append(
            {
                "kind": "document",
                "kind_label": SOURCE_REF_KIND_LABELS["document"],
                "title": r.get("title") or "",
                "detail": r.get("doc_type") or "",
                "document_id": r.get("document_id"),
            }
        )
    ti = template_inspect or {}
    refs.append(
        {
            "kind": "template",
            "kind_label": SOURCE_REF_KIND_LABELS["template"],
            "title": ti.get("template_name") or "内置模板",
            "detail": ti.get("source") or "",
        }
    )
    for rec in exec_data.get("exec_records") or []:
        if not isinstance(rec, dict):
            continue
        refs.append(
            {
                "kind": "exec_record",
                "kind_label": SOURCE_REF_KIND_LABELS["exec_record"],
                "title": rec.get("name") or "执行记录",
                "detail": f"{rec.get('report_type') or ''} · 通过率 {rec.get('pass_rate') or 0}%",
            }
        )
    return refs


async def aggregate_exec_records(
    project_id: int,
    exec_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    failed_cases: list[dict[str, Any]] = []
    total_cases = 0
    success_cases = 0
    failed_count = 0
    duration_parts: list[str] = []

    for ref in exec_records:
        rtype = ref.get("report_type") or ref.get("type")
        rid = ref.get("record_id") or ref.get("id")
        if not rtype or not rid:
            continue
        try:
            data = await build_report_execution_data(rtype, int(rid), project_id)  # type: ignore[arg-type]
        except HTTPException:
            continue
        summaries.append(
            {
                "name": data.get("name") or "未知",
                "report_type": rtype,
                "pass_rate": data.get("pass_rate_percent", 0),
                "total_cases": data.get("total_cases", 0),
                "failed_cases": data.get("failed_cases", 0),
            }
        )
        total_cases += int(data.get("total_cases") or 0)
        success_cases += int(data.get("success_cases") or 0)
        failed_count += int(data.get("failed_cases") or 0)
        if data.get("duration_ms"):
            duration_parts.append(f"{data.get('name')}: {round(data['duration_ms'] / 1000, 1)}s")
        elif data.get("duration_sec"):
            duration_parts.append(f"{data.get('name')}: {data['duration_sec']}s")
        for key in ("failed_case_samples", "failed_item_samples", "failed_suite_samples"):
            for item in data.get(key) or []:
                if not isinstance(item, dict):
                    continue
                if key == "failed_suite_samples":
                    for sub in item.get("failed_case_samples") or []:
                        failed_cases.append(
                            {
                                "case_name": sub.get("case_name") or item.get("suite_name") or "未知",
                                "status": sub.get("status") or "failed",
                                "error_msg": (sub.get("error_hint") or sub.get("error_msg") or "")[:300],
                            }
                        )
                else:
                    failed_cases.append(
                        {
                            "case_name": item.get("case_name") or item.get("name") or "未知",
                            "status": item.get("status") or "failed",
                            "error_msg": (
                                item.get("error_msg")
                                or item.get("error_hint")
                                or item.get("error")
                                or ""
                            )[:300],
                        }
                    )

    pass_rate = round(success_cases / total_cases * 100, 1) if total_cases else 0
    return {
        "exec_records": summaries,
        "failed_cases": failed_cases[:30],
        "total_cases": total_cases,
        "failed_case_count": failed_count,
        "pass_rate": pass_rate,
        "exec_duration": "；".join(duration_parts[:5]) if duration_parts else "-",
    }
