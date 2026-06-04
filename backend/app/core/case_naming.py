"""
用例标题命名：项目级可配置模板 + 语义槽位组装（Jinja2）
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Optional

from jinja2 import Template as Jinja2Template

from app.models.sys import Project

CASE_NAMING_GLOBAL_VARS_KEY = "case_naming"

DEFAULT_TITLE_TEMPLATE = (
    "【#{{ story_no }}_{{ main_module }}_{{ sub_module }}】"
    "（{{ feature_point }}）{{ case_description }}"
)

DEFAULT_SLOT_DEFINITIONS: dict[str, dict] = {
    "story_no": {
        "source": "bindings.related_story",
        "transform": "extract_leading_number",
        "label": "需求编号",
    },
    "main_module": {
        "source": "llm.main_module",
        "fallback": "section.level1_title",
        "label": "主功能模块",
    },
    "sub_module": {
        "source": "llm.sub_module",
        "fallback": "section.leaf_title",
        "label": "子功能模块",
    },
    "feature_point": {
        "source": "llm.feature_point",
        "label": "功能点",
    },
    "case_description": {
        "source": "llm.case_description",
        "label": "用例描述",
    },
}

DEFAULT_EXPORT_COLUMNS: list[dict] = [
    {"column": "所属产品", "expr": "{{ case.product or defaults.product }}"},
    {"column": "所属模块", "expr": "{{ defaults.module }}"},
    {"column": "相关研发需求", "expr": "{{ case.related_story or defaults.related_story }}"},
    {"column": "用例标题", "expr": "{{ case.title }}"},
    {"column": "前置条件", "expr": "{{ case.precondition }}"},
    {"column": "步骤", "expr": "{{ steps_text }}"},
    {"column": "预期", "expr": "{{ expects_text }}"},
    {"column": "优先级", "expr": "{{ case.priority }}"},
    {"column": "用例类型", "expr": "{{ case.type or '功能测试' }}"},
    {"column": "适用阶段", "expr": "{{ stage_resolved }}"},
]


def default_template() -> dict:
    return {
        "id": "default",
        "name": "公司默认规范",
        "version": 1,
        "enabled": True,
        "requirement_types": ["*"],
        "title_template": DEFAULT_TITLE_TEMPLATE,
        "slot_definitions": copy.deepcopy(DEFAULT_SLOT_DEFINITIONS),
        "validation": {
            "title_max_length": 500,
            "warn_if_missing_slots": [
                "story_no",
                "main_module",
                "sub_module",
                "feature_point",
                "case_description",
            ],
        },
        "export_columns": copy.deepcopy(DEFAULT_EXPORT_COLUMNS),
    }


def default_naming_config() -> dict:
    tpl = default_template()
    return {
        "active_template_id": tpl["id"],
        "templates": [tpl],
    }


def normalize_naming_config(raw: Optional[dict]) -> dict:
    base = default_naming_config()
    if not raw or not isinstance(raw, dict):
        return base
    templates = raw.get("templates")
    if isinstance(templates, list) and templates:
        normalized_tpls = []
        for t in templates:
            if not isinstance(t, dict):
                continue
            merged = default_template()
            merged.update({k: v for k, v in t.items() if v is not None})
            if isinstance(t.get("slot_definitions"), dict):
                fixed_defs = {}
                for sk, sv in {**DEFAULT_SLOT_DEFINITIONS, **t["slot_definitions"]}.items():
                    if isinstance(sv, dict):
                        sd = dict(sv)
                        src = sd.get("source") or ""
                        fb = sd.get("fallback") or ""
                        if src.startswith("binding."):
                            sd["source"] = "bindings." + src.split(".", 1)[1]
                        if fb.startswith("binding."):
                            sd["fallback"] = "bindings." + fb.split(".", 1)[1]
                        fixed_defs[sk] = sd
                    else:
                        fixed_defs[sk] = sv
                merged["slot_definitions"] = fixed_defs
            if isinstance(t.get("export_columns"), list) and t["export_columns"]:
                merged["export_columns"] = t["export_columns"]
            else:
                merged["export_columns"] = copy.deepcopy(DEFAULT_EXPORT_COLUMNS)
            if isinstance(t.get("validation"), dict):
                merged["validation"] = {**merged["validation"], **t["validation"]}
            if not merged.get("id"):
                merged["id"] = f"tpl_{uuid.uuid4().hex[:8]}"
            normalized_tpls.append(merged)
        base["templates"] = normalized_tpls
    active = raw.get("active_template_id")
    if active and any(t["id"] == active for t in base["templates"]):
        base["active_template_id"] = active
    elif base["templates"]:
        base["active_template_id"] = base["templates"][0]["id"]
    return base


def get_project_naming_config(project: Project) -> dict:
    gv = project.global_vars if isinstance(project.global_vars, dict) else {}
    return normalize_naming_config(gv.get(CASE_NAMING_GLOBAL_VARS_KEY))


async def load_naming_config(project_id: int) -> dict:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return default_naming_config()
    return get_project_naming_config(project)


async def save_naming_config(project_id: int, config: dict) -> dict:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    old = get_project_naming_config(project)
    normalized = normalize_naming_config(config)
    old_by_id = {t["id"]: t for t in old.get("templates") or []}
    for tpl in normalized.get("templates") or []:
        prev = old_by_id.get(tpl.get("id"))
        if not prev:
            continue
        changed = (
            tpl.get("title_template") != prev.get("title_template")
            or tpl.get("slot_definitions") != prev.get("slot_definitions")
            or tpl.get("export_columns") != prev.get("export_columns")
        )
        if changed:
            tpl["version"] = int(prev.get("version") or 1) + 1
    gv = dict(project.global_vars or {})
    gv[CASE_NAMING_GLOBAL_VARS_KEY] = normalized
    project.global_vars = gv
    await project.save()
    return normalized


def find_template_by_id(config: dict, template_id: str) -> Optional[dict]:
    for t in config.get("templates") or []:
        if t.get("id") == template_id and t.get("enabled", True):
            return t
    return None


def resolve_template(
    config: dict,
    requirement_type: str = "default",
    template_id_override: Optional[str] = None,
) -> dict:
    """按需求类型或显式 override 选取模板，否则用 active。"""
    if template_id_override:
        tpl = find_template_by_id(config, template_id_override)
        if tpl:
            return tpl
    req_type = (requirement_type or "default").strip() or "default"
    for t in config.get("templates") or []:
        if not t.get("enabled", True):
            continue
        types = t.get("requirement_types") or ["*"]
        if "*" in types or req_type in types:
            return t
    active_id = config.get("active_template_id")
    tpl = find_template_by_id(config, active_id) if active_id else None
    if tpl:
        return tpl
    templates = config.get("templates") or []
    return templates[0] if templates else default_template()


def _apply_transform(value: Any, transform: Optional[str]) -> str:
    text = str(value or "").strip()
    if not transform:
        return text
    if transform == "extract_leading_number":
        m = re.match(r"^(\d+)", text)
        return m.group(1) if m else ""
    if transform == "strip":
        return text.strip()
    return text


def _read_source(source: str, ctx: dict) -> Any:
    if not source:
        return ""
    parts = source.split(".", 1)
    if len(parts) != 2:
        return ""
    root, key = parts
    bucket = ctx.get(root) or {}
    if isinstance(bucket, dict):
        return bucket.get(key, "")
    return ""


def resolve_slot(slot_name: str, definition: dict, ctx: dict) -> str:
    val = _read_source(definition.get("source", ""), ctx)
    if not str(val or "").strip() and definition.get("fallback"):
        val = _read_source(definition["fallback"], ctx)
    return _apply_transform(val, definition.get("transform"))


def resolve_all_slots(template: dict, ctx: dict) -> tuple[dict[str, str], list[str]]:
    definitions = template.get("slot_definitions") or DEFAULT_SLOT_DEFINITIONS
    slots: dict[str, str] = {}
    warnings: list[str] = []
    validation = template.get("validation") or {}
    warn_missing = validation.get("warn_if_missing_slots") or []

    for name, definition in definitions.items():
        if not isinstance(definition, dict):
            continue
        value = resolve_slot(name, definition, ctx)
        slots[name] = value
        if name in warn_missing and not value:
            label = definition.get("label") or name
            warnings.append(f"缺少槽位「{label}」({name})")

    return slots, warnings


def compose_title(template: dict, slots: dict[str, str]) -> str:
    title_tpl = (template.get("title_template") or DEFAULT_TITLE_TEMPLATE).strip()
    rendered = Jinja2Template(title_tpl).render(**slots).strip()
    max_len = int((template.get("validation") or {}).get("title_max_length") or 500)
    if len(rendered) > max_len:
        rendered = rendered[:max_len]
    return rendered


def preview_title(template: dict, sample_slots: dict[str, str]) -> dict:
    """预览组装结果与缺槽告警。"""
    ctx = {
        "llm": sample_slots,
        "bindings": {
            "related_story": sample_slots.get("story_no", ""),
            "product": sample_slots.get("product", ""),
            "module": sample_slots.get("module", ""),
        },
        "section": {
            "level1_title": sample_slots.get("main_module", ""),
            "level2_title": sample_slots.get("sub_module", ""),
            "leaf_title": sample_slots.get("sub_module", ""),
        },
        "context": {},
    }
    if sample_slots.get("story_no") and not str(sample_slots["story_no"]).startswith(":"):
        ctx["bindings"]["related_story"] = f"{sample_slots['story_no']}:示例需求"

    slots, _warnings = resolve_all_slots(template, ctx)
    for k, v in sample_slots.items():
        if v and k in slots:
            slots[k] = str(v).strip()
    # 告警以最终槽位值为准（预览样例会覆盖自动解析结果）
    warnings: list[str] = []
    warn_missing = (template.get("validation") or {}).get("warn_if_missing_slots") or []
    definitions = template.get("slot_definitions") or DEFAULT_SLOT_DEFINITIONS
    for name in warn_missing:
        if not slots.get(name):
            label = (definitions.get(name) or {}).get("label") or name
            warnings.append(f"缺少槽位「{label}」({name})")
    title = compose_title(template, slots)
    return {"title": title, "slots": slots, "warnings": warnings}


def build_section_context(
    selected_sections: list[dict],
    all_sections: Optional[list[dict]] = None,
) -> dict:
    if not selected_sections:
        return {
            "level1_title": "",
            "level2_title": "",
            "leaf_title": "",
            "path_titles": [],
        }
    by_id = {s.get("id"): s for s in (all_sections or selected_sections) if s.get("id")}
    sec = selected_sections[0]
    path: list[str] = []
    cur: Optional[dict] = sec
    visited = set()
    while cur and cur.get("id") not in visited:
        visited.add(cur.get("id"))
        title = (cur.get("title") or "").strip()
        if title:
            path.insert(0, title)
        pid = cur.get("parent_id")
        cur = by_id.get(pid) if pid else None

    level1 = path[0] if path else ""
    level2 = path[1] if len(path) > 1 else ""
    leaf = path[-1] if path else ""
    return {
        "level1_title": level1,
        "level2_title": level2 or leaf,
        "leaf_title": leaf,
        "path_titles": path,
    }


def apply_naming_to_case_item(
    item: dict,
    template: dict,
    bindings: dict,
    section_ctx: dict,
    *,
    batch_name: str = "",
    requirement_name: str = "",
) -> tuple[dict, list[str]]:
    llm = {
        "main_module": (item.get("main_module") or item.get("module") or "").strip(),
        "sub_module": (item.get("sub_module") or "").strip(),
        "feature_point": (item.get("feature_point") or "").strip(),
        "case_description": (item.get("case_description") or "").strip(),
    }
    ctx = {
        "llm": llm,
        "bindings": bindings,
        "section": section_ctx,
        "context": {
            "batch_name": batch_name,
            "requirement_name": requirement_name,
        },
    }
    slots, warnings = resolve_all_slots(template, ctx)
    title = compose_title(template, slots)
    if not title:
        title = (item.get("title") or "").strip()

    out = {
        **item,
        "title": title,
        "naming_slots": slots,
        "naming_template_id": template.get("id"),
        "naming_template_version": template.get("version", 1),
    }
    return out, warnings


def apply_naming_to_cases(
    items: list[dict],
    template: dict,
    bindings: dict,
    section_ctx: dict,
    *,
    batch_name: str = "",
    requirement_name: str = "",
) -> tuple[list[dict], list[str]]:
    all_warnings: list[str] = []
    result: list[dict] = []
    for item in items:
        out, warnings = apply_naming_to_case_item(
            item,
            template,
            bindings,
            section_ctx,
            batch_name=batch_name,
            requirement_name=requirement_name,
        )
        result.append(out)
        all_warnings.extend(warnings)
    return result, all_warnings


def recalc_title_from_stored_slots(
    item: dict,
    template: dict,
    bindings: dict,
) -> tuple[str, list[str]]:
    """草稿重算：保留 LLM 槽位，重新解析 binding 等自动槽位。"""
    stored = item.get("naming_slots") if isinstance(item.get("naming_slots"), dict) else {}
    llm = {
        "main_module": stored.get("main_module") or item.get("main_module") or item.get("module", ""),
        "sub_module": stored.get("sub_module") or item.get("sub_module", ""),
        "feature_point": stored.get("feature_point") or item.get("feature_point", ""),
        "case_description": stored.get("case_description") or item.get("case_description", ""),
    }
    section_ctx = {
        "level1_title": stored.get("main_module") or llm["main_module"],
        "level2_title": stored.get("sub_module") or llm["sub_module"],
        "leaf_title": stored.get("sub_module") or llm["sub_module"],
        "path_titles": [],
    }
    ctx = {
        "llm": llm,
        "bindings": bindings,
        "section": section_ctx,
        "context": {},
    }
    slots, warnings = resolve_all_slots(template, ctx)
    for key in ("main_module", "sub_module", "feature_point", "case_description"):
        if llm.get(key):
            slots[key] = llm[key]
    title = compose_title(template, slots)
    return title, warnings


def render_export_row(
    case: dict,
    defaults: dict,
    export_columns: list[dict],
    *,
    steps_text: str = "",
    expects_text: str = "",
    stage_resolved: str = "",
) -> dict[str, Any]:
    """按模板 export_columns 渲染导出行。"""
    render_ctx = {
        "case": case,
        "defaults": defaults,
        "steps_text": steps_text,
        "expects_text": expects_text,
        "stage_resolved": stage_resolved,
    }
    row: dict[str, Any] = {}
    for col in export_columns:
        if not isinstance(col, dict):
            continue
        name = col.get("column") or col.get("key") or ""
        expr = col.get("expr") or ""
        if not name:
            continue
        try:
            row[name] = Jinja2Template(expr).render(**render_ctx).strip()
        except Exception:
            row[name] = ""
    return row


def get_export_columns_for_template(template: dict) -> list[str]:
    cols = template.get("export_columns") or DEFAULT_EXPORT_COLUMNS
    return [c.get("column") or c.get("key") or "" for c in cols if isinstance(c, dict)]


def format_naming_rules_for_prompt(template: dict) -> str:
    """供 Prompt 注入的命名说明。"""
    slots = template.get("slot_definitions") or DEFAULT_SLOT_DEFINITIONS
    lines = [
        "【用例标题规范 · 由平台按模板组装，模型勿自行拼接完整标题】",
        f"标题模板：{template.get('title_template', DEFAULT_TITLE_TEMPLATE)}",
        "请为每条用例输出以下语义字段（JSON 字段名固定）：",
        "- main_module: 主功能模块（中文）",
        "- sub_module: 子功能模块（中文）",
        "- feature_point: 功能点名称（由你命名，如「导出功能01」「登录校验02」）",
        "- case_description: 用例描述（说明验证点，会拼入最终用例标题）",
        "不要输出 title 字段；不要重复已有用例的 feature_point。",
    ]
    warn = (template.get("validation") or {}).get("warn_if_missing_slots") or []
    if warn:
        labels = [slots.get(s, {}).get("label", s) for s in warn if s in slots]
        lines.append(f"必填语义槽：{', '.join(labels)}")
    return "\n".join(lines)
