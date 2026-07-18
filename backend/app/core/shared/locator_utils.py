"""
定位器字符串规范化（与 Runner tools.locator_normalize 逻辑一致）
"""
import re
from typing import Any

_HAS_TEXT_INNER_RE = re.compile(r':has-text\("((?:[^"\\]|\\.)*)"\)')


def ensure_xpath_engine_prefix(locator: str) -> str:
    """
    绝对 XPath（/html/...）必须加 xpath= 前缀。
    Playwright 的 locator() 对以单个 / 开头的字符串按 CSS 解析，会报 Unexpected token \"/\"。
    以 // 或 .// 开头的相对 XPath 由 Playwright 自动识别，无需前缀。
    """
    s = (locator or "").strip()
    if not s:
        return s
    head = s.split("=", 1)[0].strip().lower()
    if head in ("xpath", "css", "id", "text", "internal:control", "internal:has-text", "internal:attr"):
        return s
    if s.startswith(("//", ".//", "(//", "(/")):
        return s
    if s.startswith("/") and not s.startswith("//"):
        return f"xpath={s}"
    return s


def text_unsafe_for_css_has_text(text: str) -> bool:
    """Playwright 将 :has-text() 走 CSS 解析时，$ 等字符会触发 BADSTRING。"""
    return bool(re.search(r"[\$\\]", text or ""))


def _strip_wrapping_quotes(value: str) -> str:
    """去掉 LLM 偶发写入的包裹引号，如 'row' / \"0302\"。"""
    s = (value or "").strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1].strip()
    return s


_NAME_PREFIX_RE = re.compile(r"^name\s*=\s*(.+)$", re.I | re.DOTALL)


def _strip_role_name_part(value: str) -> str:
    """去掉 get_by_role 名称段的 name= 前缀，如 name=\"登入\" → 登入。"""
    s = _strip_wrapping_quotes(value)
    m = _NAME_PREFIX_RE.match(s)
    if m:
        return _strip_wrapping_quotes(m.group(1).strip())
    return s


def _normalize_get_by_role_segment(segment: str) -> str:
    """规范化 get_by_role=role, name 片段（含链式子段）。"""
    if not segment.startswith("get_by_role="):
        return segment
    role_part = segment[len("get_by_role="):]
    parts = role_part.split(",", 1)
    role = _strip_wrapping_quotes(parts[0])
    if len(parts) > 1:
        name = _strip_role_name_part(parts[1])
        return f"get_by_role={role}, {name}"
    return f"get_by_role={role}"


def _normalize_native_value_segment(segment: str) -> str:
    """规范化单段原生定位写法（去引号等）。"""
    for prefix in (
        "get_by_text=",
        "get_by_label=",
        "get_by_placeholder=",
        "get_by_alt_text=",
        "get_by_title=",
    ):
        if segment.startswith(prefix):
            return prefix + _strip_wrapping_quotes(segment[len(prefix):])
    if segment.startswith("get_by_role="):
        return _normalize_get_by_role_segment(segment)
    return segment


_ROLE_SHORTHAND_RE = re.compile(
    r"^(row|cell|columnheader|gridcell|button|link|menuitem|tab|textbox)=(.+)$",
    re.I,
)


def _coerce_role_shorthand_segment(segment: str) -> str:
    """LLM 偶发 row=名称 / cell=4 写法 → get_by_role=row, 名称"""
    s = (segment or "").strip()
    m = _ROLE_SHORTHAND_RE.match(s)
    if m:
        role = m.group(1).lower()
        name = _strip_wrapping_quotes(m.group(2).strip())
        return f"get_by_role={role}, {name}"
    return s


def _normalize_chain_segment(segment: str) -> str:
    seg = _coerce_role_shorthand_segment(segment.strip())
    return ensure_xpath_engine_prefix(_normalize_native_value_segment(seg))


def _normalize_native_locator_segments(locator: str) -> str:
    """规范化链式定位器中的原生写法片段。"""
    if " >> " in locator:
        return " >> ".join(
            _normalize_chain_segment(part.strip())
            for part in locator.split(" >> ")
        )
    return _normalize_chain_segment(locator)


def coerce_unsafe_has_text_locator(locator: str) -> str:
    """
    将含 $ 等字符的 tag:has-text("...") 转为 tag >> get_by_text=... 或 get_by_text=...
    """
    s = (locator or "").strip()
    if not s or ":has-text(" not in s:
        return s
    m = _HAS_TEXT_INNER_RE.search(s)
    if not m:
        return s
    text = m.group(1).replace('\\"', '"')
    if not text_unsafe_for_css_has_text(text):
        return s
    before = s[: m.start()].rstrip()
    if before:
        return f"{before} >> get_by_text={text}"
    return f"get_by_text={text}"


def extract_locator_text(locator: Any) -> str:
    """从定位字符串提取可用于文本匹配的片段（含链式 get_by_text）。"""
    locator_str = normalize_locator(locator)
    if not locator_str:
        return ""
    if " >> get_by_text=" in locator_str:
        return locator_str.rsplit(" >> get_by_text=", 1)[1].strip()
    if locator_str.startswith("get_by_text="):
        return locator_str[12:].strip()
    m = _HAS_TEXT_INNER_RE.search(locator_str)
    if m:
        return m.group(1).replace('\\"', '"')
    return ""


def prefer_popup_elements(raw: list) -> list:
    """页面存在弹窗层时，优先返回弹窗内元素列表。"""
    if not isinstance(raw, list):
        return []
    popup_only = [el for el in raw if el.get("in_popup")]
    if popup_only:
        return popup_only
    return raw


def normalize_locator(locator: Any) -> str:
    if locator is None:
        return ""
    if isinstance(locator, dict):
        role = locator.get("get_by_role") or locator.get("role")
        if role:
            name = (locator.get("name") or locator.get("label") or "").strip()
            return _normalize_native_value_segment(
                f"get_by_role={role}, {name}" if name else f"get_by_role={role}"
            )
        text = locator.get("get_by_text") or locator.get("text")
        if text:
            return _normalize_native_value_segment(f"get_by_text={text}")
        ph = locator.get("get_by_placeholder") or locator.get("placeholder")
        if ph:
            return _normalize_native_value_segment(f"get_by_placeholder={ph}")
        for key in ("selector", "css", "locator", "value"):
            val = locator.get(key)
            if val and isinstance(val, str):
                return ensure_xpath_engine_prefix(coerce_unsafe_has_text_locator(val.strip()))
        return str(locator).strip()

    s = str(locator).strip()
    if not s:
        return ""

    s = coerce_unsafe_has_text_locator(s)

    m = re.match(r"^get_by_placeholder\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_placeholder={m.group(1)}"

    m = re.match(r"^get_by_text\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_text={m.group(1)}"

    m = re.match(r"^get_by_label\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_label={m.group(1)}"

    m = re.match(r"^get_by_title\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_title={m.group(1)}"

    m = re.match(
        r"^get_by_role\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*name\s*=\s*['\"](.+?)['\"]\s*)?\)$",
        s,
    )
    if m:
        role, name = m.group(1), m.group(2)
        return _normalize_native_locator_segments(
            coerce_unsafe_has_text_locator(
                f"get_by_role={role}, {name}" if name else f"get_by_role={role}"
            )
        )

    return _normalize_native_locator_segments(coerce_unsafe_has_text_locator(s))


_NATIVE_PREFIXES = (
    "get_by_role=",
    "get_by_text=",
    "get_by_label=",
    "get_by_placeholder=",
    "get_by_alt_text=",
    "get_by_title=",
)


def _resolve_root_locator(scope, sel: str):
    if sel.startswith("get_by_role="):
        role_part = sel[12:]
        parts = role_part.split(",", 1)
        role = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else None
        return scope.get_by_role(role, name=name) if name else scope.get_by_role(role)
    if sel.startswith("get_by_text="):
        return scope.get_by_text(sel.split("=", 1)[1])
    if sel.startswith("get_by_label="):
        return scope.get_by_label(sel.split("=", 1)[1])
    if sel.startswith("get_by_placeholder="):
        return scope.get_by_placeholder(sel.split("=", 1)[1])
    if sel.startswith("get_by_alt_text="):
        return scope.get_by_alt_text(sel.split("=", 1)[1])
    if sel.startswith("get_by_title="):
        return scope.get_by_title(sel.split("=", 1)[1])
    return scope.locator(sel)


def _resolve_child_locator(parent_loc, child_sel: str):
    if child_sel.startswith("get_by_role="):
        role_part = child_sel[12:]
        parts = role_part.split(",", 1)
        role = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else None
        return parent_loc.get_by_role(role, name=name) if name else parent_loc.get_by_role(role)
    if child_sel.startswith("get_by_text="):
        return parent_loc.get_by_text(child_sel.split("=", 1)[1])
    if child_sel.startswith("get_by_label="):
        return parent_loc.get_by_label(child_sel.split("=", 1)[1])
    if child_sel.startswith("get_by_placeholder="):
        return parent_loc.get_by_placeholder(child_sel.split("=", 1)[1])
    if child_sel.startswith("get_by_alt_text="):
        return parent_loc.get_by_alt_text(child_sel.split("=", 1)[1])
    if child_sel.startswith("get_by_title="):
        return parent_loc.get_by_title(child_sel.split("=", 1)[1])
    return parent_loc.locator(child_sel)


def _resolve_locator_on_scope(scope, locator_str: str):
    locator_str = (locator_str or "").strip()
    if " >> " in locator_str:
        parent_sel, child_sel = locator_str.split(" >> ", 1)
        parent_sel = parent_sel.strip()
        child_sel = child_sel.strip()
        if parent_sel and child_sel:
            parent_loc = _resolve_locator_on_scope(scope, parent_sel)
            return _resolve_locator_on_scope(parent_loc, child_sel)
    if locator_str.startswith(_NATIVE_PREFIXES):
        return _resolve_root_locator(scope, locator_str)
    return scope.locator(locator_str)


def resolve_locator_on_page(page, locator: Any):
    """将平台定位字符串解析为 Playwright Locator（不含 .first / iframe）。"""
    locator_str = normalize_locator(locator)
    if not locator_str or not page:
        return None
    return _resolve_locator_on_scope(page, locator_str)


def resolve_locator_on_frame(frame_locator, locator: Any):
    """在 FrameLocator 内解析平台定位字符串（支持 get_by_text= 等原生写法）。"""
    locator_str = normalize_locator(locator)
    if not locator_str or not frame_locator:
        return None
    return _resolve_locator_on_scope(frame_locator, locator_str)
