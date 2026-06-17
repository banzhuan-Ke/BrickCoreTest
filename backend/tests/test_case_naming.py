"""用例命名：槽位告警、story_no 回退、内置模板"""
from app.core.case_naming import (
    apply_naming_to_case_item,
    compose_title,
    default_template,
    effective_warn_missing_slots,
    generic_template,
    parse_title_template_vars,
    preview_title,
    resolve_all_slots,
    resolve_template,
    zentao_no_story_template,
    default_naming_config,
)
from app.core.export_profile import EXPORT_PROFILE_GENERIC
from app.core.zentao_bindings import normalize_bindings, validate_bindings


def test_effective_warn_missing_slots_only_used_in_template():
    tpl = zentao_no_story_template()
    warned = effective_warn_missing_slots(tpl)
    assert "story_no" not in warned
    assert "main_module" in warned


def test_default_template_warns_story_no_when_used():
    tpl = default_template()
    warned = effective_warn_missing_slots(tpl)
    assert "story_no" not in warned
    assert "main_module" in warned


def test_story_no_fallback_to_requirement_id():
    tpl = default_template()
    ctx = {
        "llm": {
            "main_module": "模块A",
            "sub_module": "子模块B",
            "feature_point": "功能01",
            "case_description": "验证点",
        },
        "bindings": {"related_story": "纯中文需求名"},
        "section": {"level1_title": "", "leaf_title": ""},
        "context": {"requirement_id": "42", "story_code": ""},
    }
    slots, warnings = resolve_all_slots(tpl, ctx)
    assert slots["story_no"] == "42"
    assert not any("story_no" in w for w in warnings)


def test_story_no_extracts_leading_number_first():
    tpl = default_template()
    ctx = {
        "llm": {},
        "bindings": {"related_story": "3174:新增空调设备"},
        "section": {},
        "context": {"requirement_id": "99"},
    }
    slots, _ = resolve_all_slots(tpl, ctx)
    assert slots["story_no"] == "3174"


def test_compose_title_cleans_empty_story_no():
    tpl = default_template()
    slots = {
        "story_no": "",
        "main_module": "主模块",
        "sub_module": "子模块",
        "feature_point": "功能01",
        "case_description": "描述",
    }
    title = compose_title(tpl, slots)
    assert "#_" not in title
    assert "主模块" in title


def test_generic_export_profile_skips_zentao_validation():
    bindings = normalize_bindings(
        {"export_profile": EXPORT_PROFILE_GENERIC, "product": "", "module": "", "related_story": ""}
    )
    assert validate_bindings(bindings) == []


def test_apply_naming_no_story_no_warning():
    tpl = zentao_no_story_template()
    item = {
        "main_module": "主模块",
        "sub_module": "子模块",
        "feature_point": "功能01",
        "case_description": "验证导入",
    }
    bindings = {"related_story": "新增空调设备", "product": "P", "module": "M"}
    section_ctx = {"level1_title": "", "leaf_title": ""}
    out, warnings = apply_naming_to_case_item(
        item,
        tpl,
        bindings,
        section_ctx,
        requirement_id=7,
    )
    assert out["title"]
    assert not any("story_no" in w for w in warnings)


def test_parse_title_template_vars():
    vars_set = parse_title_template_vars(
        "【#{{ story_no }}_{{ main_module }}】（{{ feature_point }}）"
    )
    assert vars_set == {"story_no", "main_module", "feature_point"}


def test_generic_template_preview():
    tpl = generic_template()
    result = preview_title(
        tpl,
        {
            "main_module": "登录",
            "feature_point": "校验01",
            "case_description": "密码错误提示",
        },
    )
    assert result["title"]
    assert "登录" in result["title"]


def test_resolve_template_prefers_active_over_default():
    config = default_naming_config()
    config["active_template_id"] = "zentao_no_story"
    tpl = resolve_template(config, "default", None, "zentao")
    assert tpl["id"] == "zentao_no_story"


def test_resolve_template_requirement_override_wins():
    config = default_naming_config()
    config["active_template_id"] = "zentao_no_story"
    tpl = resolve_template(config, "default", "generic", "zentao")
    assert tpl["id"] == "generic"
