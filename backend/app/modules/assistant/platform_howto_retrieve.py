"""平台「怎么用」检索：帮助中心内置文档 + Skill 清单 + 菜单跳转提示。

供小测 Skill `platform_how_to` 使用；只读本地 docs-site 白名单，不编造未登记能力。
"""
from __future__ import annotations

import re
from typing import Any

from app.core.shared.docs_catalog import get_builtin_doc_entries, read_builtin_markdown

# 常见问法 → 文档 id / 站内路径（可叠加检索命中）
_TOPIC_HINTS: list[dict[str, Any]] = [
    {
        "keywords": ("失败分析", "根因", "近期失败", "ui_failure", "failure_analysis"),
        "doc_ids": ("platform-assistant", "ai-testing", "web-troubleshooting"),
        "routes": (
            {"path": "/ai-skills", "label": "技能清单"},
            {"path": "/docs?doc=platform-assistant", "label": "帮助：平台助手"},
        ),
        "skill_codes": ("ui_failure_analysis", "failure_to_defect_draft"),
        "blurb": "在小测点技能快捷入口「失败分析」或「失败→缺陷」，或打开技能清单「快速使用」；也可说「分析近期失败」。",
    },
    {
        "keywords": ("数据工厂", "sql", "库断言", "数据源", "redis", "elasticsearch", "查库", "查询控制台", "es"),
        "doc_ids": ("data-factory",),
        "routes": (
            {"path": "/api-data-factory", "label": "数据工厂"},
            {"path": "/docs?doc=data-factory", "label": "帮助：数据工厂"},
        ),
        "skill_codes": ("nl_to_sql_template",),
        "blurb": "菜单：接口自动化 → 数据工厂；可配置环境数据源（含 Elasticsearch）、SQL 模板、查询控制台与通用工具；小测可用 query_datasource 只读查库，或技能快捷入口「NL→SQL模板」。",
    },
    {
        "keywords": ("资料库", "知识库", "rag", "knowledge", "迭代资料"),
        "doc_ids": ("knowledge-base",),
        "routes": (
            {"path": "/docs?doc=knowledge-base", "label": "帮助：迭代资料库"},
        ),
        "skill_codes": ("knowledge_qa",),
        "blurb": "在小测用技能快捷入口「资料库问答」，或技能清单快速使用；需项目已启用资料库。",
    },
    {
        "keywords": ("小测", "平台助手", "assistant", "技能", "skill", "chip", "快速使用"),
        "doc_ids": ("platform-assistant", "ai-testing"),
        "routes": (
            {"path": "/ai-skills", "label": "技能清单"},
            {"path": "/docs?doc=platform-assistant", "label": "帮助：平台助手"},
        ),
        "skill_codes": (),
        "blurb": "右下角「小测」浮窗可对话与点技能快捷入口；技能清单页可「快速使用」打开小测表单。",
    },
    {
        "keywords": ("执行器", "runner", "设备", "客户端", "adb"),
        "doc_ids": ("runner-client", "runner-install-guide", "runner-troubleshooting"),
        "routes": (
            {"path": "/docs?doc=runner-client", "label": "帮助：执行器"},
            {"path": "/docs?doc=runner-install-guide", "label": "帮助：安装指南"},
        ),
        "skill_codes": (),
        "blurb": "系统管理 → 设备管理查看在线 Runner；安装与排查见帮助中心执行器章节。",
    },
    {
        "keywords": ("web", "ui自动化", "录制", "拾取", "交互调试"),
        "doc_ids": ("ui-automation", "web-recording-playback", "web-troubleshooting"),
        "routes": (
            {"path": "/docs?doc=ui-automation", "label": "帮助：Web 自动化"},
            {"path": "/docs?doc=web-recording-playback", "label": "帮助：录制回放"},
        ),
        "skill_codes": ("ui_steps_from_nl", "ui_locator_suggest"),
        "blurb": "Web 自动化 → 用例管理；录制/交互调试在用例编辑页工具栏。",
    },
    {
        "keywords": ("接口", "api", "swagger", "curl", "mock"),
        "doc_ids": ("api-automation", "api-mock", "api-auth"),
        "routes": (
            {"path": "/docs?doc=api-automation", "label": "帮助：接口自动化"},
            {"path": "/docs?doc=api-mock", "label": "帮助：Mock"},
        ),
        "skill_codes": ("api_definition_to_cases", "curl_to_cases", "mock_response_generate"),
        "blurb": "接口模块维护定义与用例；小测可用「接口→用例」「curl→用例」「生成 Mock」。",
    },
    {
        "keywords": ("压测", "性能", "perf", "journey", "qps"),
        "doc_ids": ("perf-testing",),
        "routes": (
            {"path": "/docs?doc=perf-testing", "label": "帮助：性能测试"},
        ),
        "skill_codes": ("perf_scene_from_nl", "perf_journey_from_suite"),
        "blurb": "性能测试模块管理场景与报告；小测可用「一句话压测」「套件→压测」生成场景草稿。",
    },
    {
        "keywords": ("需求", "测试点", "功能用例", "requirement", "转web", "转app"),
        "doc_ids": ("ai-testing",),
        "routes": (
            {"path": "/docs?doc=ai-testing", "label": "帮助：AI 测试"},
        ),
        "skill_codes": (
            "requirement_to_test_points",
            "test_points_to_functional_cases",
            "functional_case_to_ui_case",
            "functional_case_to_app_case",
        ),
        "blurb": "需求测试中心维护需求与功能用例；小测技能快捷入口支持「需求→测试点」「测试点→用例」「功能用例→Web/App」。",
    },
    {
        "keywords": ("智能浏览器", "browser lab", "browser-lab"),
        "doc_ids": ("browser-lab",),
        "routes": (
            {"path": "/docs?doc=browser-lab", "label": "帮助：智能浏览器"},
        ),
        "skill_codes": ("browser_lab_to_ui_case",),
        "blurb": "AI → 智能浏览器创建探索任务；完成后可用技能快捷入口「浏览器→用例」转入 Web 用例。",
    },
    {
        "keywords": ("mcp", "外部", "cursor", "ide"),
        "doc_ids": ("mcp-server",),
        "routes": (
            {"path": "/docs?doc=mcp-server", "label": "帮助：MCP"},
        ),
        "skill_codes": (),
        "blurb": "对外 MCP 与站内小测共用工具层；接入说明见帮助中心 MCP 章节。",
    },
]

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.M)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _score_text(query_tokens: list[str], text: str) -> float:
    if not query_tokens or not text:
        return 0.0
    low = text.lower()
    score = 0.0
    for t in query_tokens:
        if t in low:
            score += 2.0 if len(t) >= 3 else 1.0
            score += low.count(t) * 0.15
    return score


def _snippet_around(text: str, query_tokens: list[str], max_len: int = 420) -> str:
    if not text:
        return ""
    low = text.lower()
    pos = -1
    for t in query_tokens:
        i = low.find(t)
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    if pos < 0:
        return text[:max_len].strip()
    start = max(0, pos - 80)
    end = min(len(text), start + max_len)
    chunk = text[start:end].strip()
    if start > 0:
        chunk = "…" + chunk
    if end < len(text):
        chunk = chunk + "…"
    return chunk


def _section_snippets(md: str, query_tokens: list[str], limit: int = 2) -> list[str]:
    """按标题切段，取相关段落。"""
    if not md:
        return []
    parts = _HEADING_RE.split(md)
    # split → [pre, h1, title1, body1, h2, title2, body2, ...]
    sections: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        sections.append(("", parts[0]))
    i = 1
    while i + 2 < len(parts):
        title = (parts[i + 1] or "").strip()
        body = parts[i + 2] or ""
        sections.append((title, body))
        i += 3
    ranked: list[tuple[float, str]] = []
    for title, body in sections:
        blob = f"{title}\n{body}"
        sc = _score_text(query_tokens, blob)
        if sc <= 0:
            continue
        snip = f"### {title}\n{_snippet_around(body, query_tokens)}" if title else _snippet_around(
            body, query_tokens
        )
        ranked.append((sc, snip))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in ranked[:limit]]


def match_topic_hints(query: str) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return []
    hits: list[dict[str, Any]] = []
    for tip in _TOPIC_HINTS:
        if any(str(k).lower() in q for k in tip["keywords"]):
            hits.append(tip)
    return hits


def search_builtin_docs(query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
    """在内置帮助文档中检索，返回带跳转的片段。"""
    q = (query or "").strip()
    tokens = _tokens(q)
    if not tokens and not q:
        return []

    entries = get_builtin_doc_entries()
    # 主题命中文档加权
    boost_ids: set[str] = set()
    for tip in match_topic_hints(q):
        boost_ids.update(tip.get("doc_ids") or ())

    ranked: list[tuple[float, dict[str, Any]]] = []
    for doc_id, (_rel, title) in entries.items():
        try:
            _t, md = read_builtin_markdown(doc_id)
        except Exception:
            continue
        score = _score_text(tokens, title) * 3.0 + _score_text(tokens, md)
        if doc_id in boost_ids:
            score += 8.0
        if score <= 0:
            continue
        snippets = _section_snippets(md, tokens) or [_snippet_around(md, tokens)]
        ranked.append(
            (
                score,
                {
                    "doc_id": doc_id,
                    "title": title,
                    "path": f"/docs?doc={doc_id}",
                    "score": round(score, 2),
                    "snippets": snippets[:2],
                },
            )
        )
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[: max(1, min(int(top_k or 5), 8))]]


def match_skills(query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """按名称/描述/code 匹配内置 Skill（需扩展包已安装）。"""
    try:
        from brickcore_assist.skills.registry import list_skill_manifests
    except Exception:
        return []

    q = (query or "").strip().lower()
    tokens = _tokens(query or "")
    boost_codes: set[str] = set()
    for tip in match_topic_hints(query or ""):
        boost_codes.update(str(c) for c in (tip.get("skill_codes") or ()))

    ranked: list[tuple[float, dict[str, Any]]] = []
    for m in list_skill_manifests() or []:
        if not isinstance(m, dict):
            continue
        code = str(m.get("code") or "")
        name = str(m.get("name") or "")
        desc = str(m.get("description") or "")
        blob = f"{code} {name} {desc}".lower()
        score = _score_text(tokens, blob)
        if code in boost_codes:
            score += 10.0
        if q and (q in blob or q in code.lower() or q in name.lower()):
            score += 4.0
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                {
                    "code": code,
                    "name": name,
                    "description": desc[:240],
                    "path": "/ai-skills",
                    "score": round(score, 2),
                },
            )
        )
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[: max(1, min(int(limit or 6), 10))]]


def collect_platform_howto_context(query: str, *, top_k: int = 5) -> dict[str, Any]:
    """汇总检索上下文，供 Skill 生成确定性回答或 LLM 润色。"""
    q = (query or "").strip()
    tips = match_topic_hints(q)
    docs = search_builtin_docs(q, top_k=top_k)
    skills = match_skills(q, limit=6)

    routes: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    blurbs: list[str] = []
    for tip in tips:
        b = str(tip.get("blurb") or "").strip()
        if b and b not in blurbs:
            blurbs.append(b)
        for r in tip.get("routes") or ():
            if not isinstance(r, dict):
                continue
            path = str(r.get("path") or "").strip()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            routes.append({"path": path, "label": str(r.get("label") or path)})
    for d in docs:
        path = str(d.get("path") or "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            routes.append({"path": path, "label": f"帮助：{d.get('title') or d.get('doc_id')}"})

    return {
        "query": q,
        "topic_blurbs": blurbs,
        "docs": docs,
        "skills": skills,
        "routes": routes[:12],
        "has_hits": bool(docs or skills or blurbs),
    }


def build_deterministic_howto_answer(ctx: dict[str, Any]) -> str:
    """不依赖 LLM 的 Markdown 回答（检索无命中时也给导航提示）。"""
    q = str(ctx.get("query") or "").strip() or "（未提供问题）"
    lines = [f"## 平台使用说明", "", f"**问题**：{q}", ""]

    blurbs = ctx.get("topic_blurbs") or []
    if blurbs:
        lines.append("### 快捷指引")
        for b in blurbs[:4]:
            lines.append(f"- {b}")
        lines.append("")

    skills = ctx.get("skills") or []
    if skills:
        lines.append("### 相关技能（小测 / 技能清单）")
        for s in skills[:6]:
            if not isinstance(s, dict):
                continue
            lines.append(
                f"- **{s.get('name') or s.get('code')}**（`{s.get('code')}`）："
                f"{(s.get('description') or '')[:120]}"
            )
        lines.append("")
        lines.append(
            "使用方式：打开右下角 **小测** 点对应技能快捷入口，或进入 "
            "[技能清单](/ai-skills) 点「快速使用」（会走预览确认，不会在清单页直接写入）。"
        )
        lines.append("")

    docs = ctx.get("docs") or []
    if docs:
        lines.append("### 帮助文档摘录")
        for d in docs[:5]:
            if not isinstance(d, dict):
                continue
            title = d.get("title") or d.get("doc_id")
            path = d.get("path") or f"/docs?doc={d.get('doc_id')}"
            lines.append(f"- **[{title}]({path})**")
            for sn in (d.get("snippets") or [])[:1]:
                lines.append("")
                lines.append(str(sn)[:500])
                lines.append("")
        lines.append("")

    routes = ctx.get("routes") or []
    if routes:
        lines.append("### 可跳转入口")
        for r in routes[:10]:
            if not isinstance(r, dict):
                continue
            lines.append(f"- [{r.get('label') or r.get('path')}]({r.get('path')})")
        lines.append("")

    if not ctx.get("has_hits"):
        lines.append("### 未精确命中")
        lines.append(
            "未在帮助中心与技能清单中找到足够匹配内容。你可以："
        )
        lines.append("- 打开 [帮助中心](/docs) 按模块浏览")
        lines.append("- 打开 [技能清单](/ai-skills) 查看当前可用 Skill")
        lines.append("- 换关键词再问（例如：失败分析、数据工厂、执行器、资料库）")
        lines.append("")
        lines.append(
            "> 说明：本回答仅依据平台已登记的帮助文档与 Skill 清单，不会编造未上线能力。"
        )
    else:
        lines.append(
            "> 说明：以上内容来自帮助中心与 Skill 清单检索；若与页面不一致，以当前菜单与帮助正文为准。"
        )

    return "\n".join(lines).strip()
