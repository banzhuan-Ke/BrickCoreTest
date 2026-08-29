"""基于 element_data 生成定位候选（对齐录制优先级，平台侧实现）。"""
from __future__ import annotations

import re
from typing import Any

_COMMON_SHORT_TEXTS = {
    "登入", "登录", "确定", "取消", "提交", "保存", "新增", "删除", "编辑",
    "搜索", "查询", "重置", "下一步", "上一步", "完成", "关闭", "返回",
    "更多", "展开", "收起", "详情", "操作", "管理", "设置", "首页", "退出",
    "导入", "导出", "下载", "上传", "预览", "复制", "粘贴", "全选", "清空",
    "运行", "报告", "查看", "启用", "禁用", "刷新", "同步", "发布",
}

_TAG_ROLE_MAP = {
    "button": "button",
    "a": "link",
    "input": "textbox",
    "select": "combobox",
    "textarea": "textbox",
    "img": "img",
    "h1": "heading", "h2": "heading", "h3": "heading",
    "ul": "list", "ol": "list", "li": "listitem",
    "table": "table", "nav": "navigation", "form": "form",
    "dialog": "dialog",
}

_INDEX_PATTERNS = (
    re.compile(r"第\s*(\d+)\s*个"),
    re.compile(r"index\s*[=:]\s*(\d+)", re.I),
    re.compile(r"nth\s*[=:]\s*(\d+)", re.I),
)


def extract_suggested_index(intent: str) -> int | None:
    text = (intent or "").strip()
    if not text:
        return None
    for pat in _INDEX_PATTERNS:
        m = pat.search(text)
        if m:
            n = int(m.group(1))
            if n >= 1:
                return n
    return None


def is_dynamic_element_id(elem_id: str) -> bool:
    s = (elem_id or "").strip()
    if not s:
        return True
    if re.match(r"^el-id-", s, re.I):
        return True
    if re.search(r"\d{6,}", s):
        return True
    if re.match(r"^(ember|react|vue|ng)[-_]", s, re.I):
        return True
    return False


def _unsafe_css_has_text(text: str) -> bool:
    return bool(re.search(r"[\$\\]", text or ""))


def _infer_role(element_data: dict[str, Any]) -> str:
    explicit = (element_data.get("role") or "").strip()
    if explicit:
        return explicit
    tag = (element_data.get("tag") or "").lower()
    input_type = (element_data.get("inputType") or "").lower()
    if tag == "input":
        if input_type == "checkbox":
            return "checkbox"
        if input_type == "radio":
            return "radio"
        if input_type in ("submit", "button", "reset"):
            return "button"
        if input_type in ("email", "tel", "url", "search", "password", "text", "number", ""):
            return "textbox"
    return _TAG_ROLE_MAP.get(tag, "")


def _dedupe(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        c = (c or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def build_rule_candidates(element_data: dict[str, Any]) -> list[str]:
    if not element_data:
        return []
    tag = (element_data.get("tag") or "").lower()
    text = (element_data.get("accessibleName") or element_data.get("text") or "").strip()
    classes = element_data.get("class") or ""
    region = (element_data.get("region") or "").strip()
    popup_root = (element_data.get("popupRoot") or "").strip()
    is_common_short = text in _COMMON_SHORT_TEXTS
    candidates: list[str] = []

    testid = element_data.get("dataTestid") or ""
    if testid:
        candidates.append(f'[data-testid="{testid}"]')

    elem_id = element_data.get("id") or ""
    if elem_id and not is_dynamic_element_id(elem_id):
        candidates.append(f"#{elem_id}")

    title = element_data.get("title") or ""
    if title and tag:
        candidates.append(f'{tag}[title="{title}"]')

    if popup_root and text and len(text) < 40 and not is_common_short:
        candidates.append(f"{popup_root} >> get_by_text={text}")
        role = _infer_role(element_data)
        if role:
            candidates.append(f"{popup_root} >> get_by_role={role}, {text}")

    if text and not is_common_short and 1 < len(text) < 30 and not text.isdigit():
        role = _infer_role(element_data)
        if role:
            candidates.append(f"get_by_role={role}, {text}")
        candidates.append(f"get_by_text={text}")

    name = element_data.get("name") or ""
    if name and tag:
        candidates.append(f'{tag}[name="{name}"]')

    aria = element_data.get("ariaLabel") or ""
    if aria and tag:
        candidates.append(f'{tag}[aria-label="{aria}"]')

    placeholder = element_data.get("placeholder") or ""
    if placeholder and tag in ("input", "textarea"):
        candidates.append(f'{tag}[placeholder="{placeholder}"]')
        candidates.append(f"get_by_placeholder={placeholder}")

    fillable_role = _infer_role(element_data)
    is_fillable = (
        tag in ("input", "textarea")
        and (element_data.get("inputType") or "text").lower()
        not in ("checkbox", "radio", "file", "hidden", "button", "submit", "reset", "image")
    ) or fillable_role == "textbox"
    if is_fillable:
        if fillable_role == "textbox" or tag in ("input", "textarea"):
            candidates.append("get_by_role=textbox")
            if text and not is_common_short and 1 < len(text) < 30:
                candidates.append(f"get_by_role=textbox, {text}")
        if placeholder:
            candidates.append(f"get_by_placeholder={placeholder}")

    if classes and tag:
        class_list = [
            c for c in str(classes).split()
            if c and not c.startswith("ng-") and not c.startswith("v-") and len(c) < 30
        ]
        if class_list:
            shallow = f"{tag}.{class_list[0]}"
            if not (
                tag == "div"
                and class_list[0] in ("el-input", "el-textarea", "ant-input-affix-wrapper")
            ):
                candidates.append(shallow)

    if text and tag and len(text) < 30 and not _unsafe_css_has_text(text):
        candidates.append(f'{tag}:has-text("{text}")')

    if is_common_short and text and len(text) < 30:
        role = _infer_role(element_data)
        if role:
            candidates.append(f"get_by_role={role}, {text}")
        candidates.append(f"get_by_text={text}")

    if region and text and len(text) < 30:
        candidates.append(f"{region} >> get_by_text={text}")
        role = _infer_role(element_data)
        if role:
            candidates.append(f"{region} >> get_by_role={role}, {text}")

    # 结构路径作中后段兜底：cssPath 优先于 structurePath，勿 insert(0) 反转
    for key in ("cssPath", "tableXPath", "tableRowXPath", "dropdownXPath", "structurePath"):
        val = (element_data.get(key) or "").strip()
        if val:
            candidates.append(val)

    abs_xpath = (element_data.get("absoluteXPath") or "").strip()
    if abs_xpath:
        if abs_xpath.startswith("/") and not abs_xpath.startswith("//"):
            abs_xpath = f"xpath={abs_xpath}"
        candidates.append(abs_xpath)

    if tag and not candidates:
        candidates.append(tag)

    return _dedupe(candidates)
