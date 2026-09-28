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

_MENU_HOST_CLASS_RE = re.compile(
    r"menu-item|dropdown-menu__item|dropdown-item|select-dropdown__item|"
    r"ant-select-item|el-cascader-node|ui-env-option",
    re.I,
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
    if not s or len(s) < 2:
        return True
    if re.match(
        r"^(ng-|_ngcontent-|ember\d+|jsx-|css-|radix-|:r\d+|el-id-|el-popover-|"
        r"cdk-overlay-|el-popper-|el-overlay-|\d+$)",
        s,
        re.I,
    ):
        return True
    if re.search(r"\d{6,}", s):
        return True
    if re.match(r"^(ember|react|vue|ng)[-_]", s, re.I):
        return True
    digits = sum(ch.isdigit() for ch in s)
    if len(s) >= 6 and digits / len(s) > 0.45:
        return True
    return False


def _unsafe_css_has_text(text: str) -> bool:
    return bool(re.search(r'[\$\\"]', text or ""))


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


def _pick_stable_class(classes: str) -> str:
    for c in str(classes or "").split():
        if not c or c.startswith("ng-") or c.startswith("v-") or len(c) >= 40:
            continue
        if _MENU_HOST_CLASS_RE.search(c) or c.startswith(("el-", "ant-", "nz-", "ui-")):
            return c
    for c in str(classes or "").split():
        if c and not c.startswith("ng-") and not c.startswith("v-") and len(c) < 30:
            return c
    return ""


def build_elevated_candidates(element_data: dict[str, Any]) -> list[str]:
    """由 elevate* 字段生成抬升候选（菜单整项等）。"""
    elevate_tag = (element_data.get("elevateTag") or "").strip().lower()
    if not elevate_tag:
        return []
    elevate_text = (element_data.get("elevateText") or "").strip()
    elevate_class = element_data.get("elevateClass") or ""
    cur_tag = (element_data.get("tag") or "").strip().lower()
    cur_text = (
        element_data.get("accessibleName") or element_data.get("text") or ""
    ).strip()
    cur_class = element_data.get("class") or ""
    if (
        elevate_tag == cur_tag
        and elevate_text == cur_text
        and str(elevate_class) == str(cur_class)
    ):
        return []
    snap = {
        "tag": elevate_tag,
        "class": elevate_class,
        "text": elevate_text,
        "accessibleName": elevate_text,
        "role": element_data.get("elevateRole") or "",
        "dataTestid": element_data.get("elevateDataTestid") or "",
        "cssPath": element_data.get("elevateCssPath") or "",
        "popupRoot": element_data.get("popupRoot") or "",
        "region": element_data.get("region") or "",
        "ancestorRole": element_data.get("ancestorRole") or "menu",
    }
    return build_rule_candidates(snap)


def _neighbor_climb_levels(element_data: dict[str, Any]) -> list[int]:
    raw = element_data.get("neighborClimb")
    if raw is None:
        raw = element_data.get("neighborClimbLevels")
    if raw is not None and str(raw).strip() != "":
        try:
            return [max(0, min(8, int(raw)))]
        except (TypeError, ValueError):
            pass
    return [0, 1]


def _neighbor_rel_axis(
    climb: int,
    neighbor_rel: str,
    t_tag: str,
    sibling_idx: int,
    stable: str = "",
) -> str:
    cls = f'[contains(@class,"{stable}")]' if stable else ""
    step = f"{neighbor_rel}::{t_tag}{cls}[{sibling_idx}]"
    if climb <= 0:
        return step
    return f"ancestor::*[{climb}]/{step}"


def _neighbor_locs_for_climb(
    *,
    neighbor_text: str,
    n_lit: str,
    n_tag: str,
    t_tag: str,
    neighbor_rel: str,
    sibling_idx: int,
    climb: int,
    stable: str = "",
) -> list[str]:
    axis = _neighbor_rel_axis(climb, neighbor_rel, t_tag, sibling_idx)
    leaf = (
        f"//{n_tag}[normalize-space()={n_lit}]"
        f"[not(.//{n_tag}[normalize-space()={n_lit}])]"
    )
    out = [
        f"get_by_text={neighbor_text} >> xpath=./{axis}",
        f"xpath={leaf}/{axis}",
    ]
    if stable:
        axis_c = _neighbor_rel_axis(climb, neighbor_rel, t_tag, sibling_idx, stable)
        out.append(f"xpath={leaf}/{axis_c}")
    return out


def build_neighbor_candidates(element_data: dict[str, Any]) -> list[str]:
    """由 neighbor* 字段生成相邻相对定位。

    通用：按 neighborClimb（文案叶节点到兄弟容器的层数）生成相对轴，
    不针对某一业务组件写死。climb 未知时仅试 0/1 两档。
    """
    neighbor_text = (element_data.get("neighborText") or "").strip()
    neighbor_rel = (element_data.get("neighborRelation") or "").strip()
    neighbor_tag = (element_data.get("neighborTag") or "*").strip() or "*"
    tag = (
        (element_data.get("neighborTargetTag") or "").strip()
        or (element_data.get("tag") or "*").strip()
        or "*"
    )
    try:
        sibling_idx = max(1, int(element_data.get("neighborSiblingIndex") or 1))
    except (TypeError, ValueError):
        sibling_idx = 1
    if (
        not neighbor_text
        or neighbor_rel not in ("following-sibling", "preceding-sibling")
        or not (1 < len(neighbor_text) <= 40)
    ):
        return []
    n_lit = _xpath_string_literal(neighbor_text)
    n_tag = re.sub(r"[^a-zA-Z0-9_-]", "", neighbor_tag) or "*"
    t_tag = re.sub(r"[^a-zA-Z0-9_-]", "", tag) or "*"
    if not n_lit:
        return []
    stable = _pick_stable_class(element_data.get("class") or "")
    climbs = _neighbor_climb_levels(element_data)
    out: list[str] = []
    for climb in climbs:
        out.extend(
            _neighbor_locs_for_climb(
                neighbor_text=neighbor_text,
                n_lit=n_lit,
                n_tag=n_tag,
                t_tag=t_tag,
                neighbor_rel=neighbor_rel,
                sibling_idx=sibling_idx,
                climb=climb,
                stable=stable,
            )
        )
    css = (element_data.get("cssPath") or "").strip()
    m = re.match(r"^(#[^\s>#]+)", css)
    if m:
        eid = m.group(1)[1:]
        if eid and not is_dynamic_element_id(eid):
            scope = m.group(1)
            scoped: list[str] = []
            for climb in climbs:
                for loc in _neighbor_locs_for_climb(
                    neighbor_text=neighbor_text,
                    n_lit=n_lit,
                    n_tag=n_tag,
                    t_tag=t_tag,
                    neighbor_rel=neighbor_rel,
                    sibling_idx=sibling_idx,
                    climb=climb,
                ):
                    if loc.startswith("get_by_text="):
                        scoped.append(f"{scope} >> {loc}")
                    elif loc.startswith("xpath=//"):
                        scoped.append(f"{scope} >> xpath=." + loc[len("xpath=") :])
            out = scoped + out
    return _dedupe(out)


def _xpath_string_literal(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    chunks: list[str] = []
    buf = ""
    for ch in s:
        if ch == "'":
            if buf:
                chunks.append(f'"{buf}"')
                buf = ""
            chunks.append('"\'"')
        elif ch == '"':
            if buf:
                chunks.append(f"'{buf}'")
                buf = ""
            chunks.append("'\"'")
        else:
            buf += ch
    if buf:
        if "'" not in buf:
            chunks.append(f"'{buf}'")
        else:
            chunks.append(f'"{buf}"')
    return "concat(" + ", ".join(chunks) + ")"


def build_tagged_candidates(element_data: dict[str, Any]) -> list[dict[str, str]]:
    """当前所选 + 抬升 + 相邻，带来源标签。"""
    tagged: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(loc: str, source: str) -> None:
        loc = (loc or "").strip()
        if not loc or loc in seen:
            return
        seen.add(loc)
        tagged.append({"locator": loc, "source": source})

    for loc in build_rule_candidates(element_data):
        _push(loc, "current")
    for loc in build_elevated_candidates(element_data):
        _push(loc, "elevated")
    for loc in build_neighbor_candidates(element_data):
        _push(loc, "neighbor")
    return tagged


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
    if title and tag and not _unsafe_css_has_text(title):
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
        stable = _pick_stable_class(classes)
        if tag and stable and not _unsafe_css_has_text(text):
            candidates.append(f'{tag}.{stable}:has-text("{text}")')

    name = element_data.get("name") or ""
    if name and tag and not _unsafe_css_has_text(name):
        candidates.append(f'{tag}[name="{name}"]')

    aria = element_data.get("ariaLabel") or ""
    if aria and tag and not _unsafe_css_has_text(aria):
        candidates.append(f'{tag}[aria-label="{aria}"]')

    placeholder = element_data.get("placeholder") or ""
    if placeholder and tag in ("input", "textarea"):
        if not _unsafe_css_has_text(placeholder):
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
