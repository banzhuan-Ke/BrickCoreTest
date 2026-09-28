"""将用户粘贴的 outerHTML / 属性 / JSON 归一为 element_data。"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse


class _FirstTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tag = ""
        self.attrs: dict[str, str] = {}
        self.text_parts: list[str] = []
        self._depth = 0
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        if self._depth == 0:
            self.tag = (tag or "").lower()
            self.attrs = {k: (v or "") for k, v in attrs if k}
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        self._depth = max(0, self._depth - 1)
        if self._depth == 0 and self.tag:
            self._done = True

    def handle_data(self, data: str) -> None:
        if self._done or self._depth < 1:
            return
        t = (data or "").strip()
        if t:
            self.text_parts.append(t)


_ATTR_LINE = re.compile(
    r"^(?P<k>[\w:-]+)\s*[:=]\s*(?P<v>.+)$",
    re.IGNORECASE,
)

_IFRAME_OPEN_RE = re.compile(r"<iframe\b([^>]*)>", re.IGNORECASE)
_HTML_TAG_OPEN_RE = re.compile(r"<([a-zA-Z][\w:-]*)\b[^>]*>", re.IGNORECASE)
_ATTR_IN_TAG_RE = re.compile(
    r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    re.IGNORECASE,
)

_GENERIC_IFRAME_PATH_SEGS = frozenset({
    "index", "list", "home", "main", "default", "app", "view", "page", "s",
})


def _visible_text_from_parts(parts: list[str], limit: int = 50) -> str:
    joined = " ".join(parts).strip()
    return joined[:limit]


def _parse_attr_blob(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_IN_TAG_RE.finditer(blob or ""):
        key = (m.group(1) or "").lower()
        val = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        out[key] = unquote(val or "")
    return out


def _distinctive_src_segment(src: str) -> str:
    """从 iframe src 提取短 path 片段，避免把 token 写进定位器。"""
    path = urlparse(src or "").path or ""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        raw = (src or "").strip()
        return raw[-40:] if len(raw) >= 3 else ""
    for p in reversed(parts):
        if p.lower() not in _GENERIC_IFRAME_PATH_SEGS and len(p) >= 3:
            return p[-40:]
    if len(parts) >= 2:
        return "/".join(parts[-2:])[-40:]
    return parts[-1][-40:]


def iframe_segment_from_attrs(attrs: dict[str, str]) -> str:
    """由 iframe 属性生成单段选择器（对齐录制侧偏好）。"""
    name = (attrs.get("name") or "").strip()
    eid = (attrs.get("id") or "").strip()
    title = (attrs.get("title") or "").strip()
    src = (attrs.get("src") or "").strip()
    cls = (attrs.get("class") or "").strip()

    if name and re.match(r"^[\w:-]+$", name):
        return f'iframe[name="{name}"]'
    if eid and re.match(r"^[A-Za-z_][\w:-]*$", eid):
        return f'iframe[id="{eid}"]'
    if title:
        safe = title.replace('"', '\\"')[:80]
        return f'iframe[title="{safe}"]'

    src_key = _distinctive_src_segment(src) if src else ""
    if len(src_key) >= 3:
        safe = src_key.replace('"', "")
        return f'iframe[src*="{safe}"]'

    class_list = [c for c in cls.split() if c and not c.startswith("ng-") and len(c) < 40]
    if class_list:
        return f"iframe.{class_list[0]}"
    return "iframe"


def extract_iframe_segments(raw: str) -> list[str]:
    """按粘贴顺序提取各层 iframe 选择器。"""
    segs: list[str] = []
    seen: set[str] = set()
    for m in _IFRAME_OPEN_RE.finditer(raw or ""):
        attrs = _parse_attr_blob(m.group(1) or "")
        seg = iframe_segment_from_attrs(attrs)
        if not seg or seg in seen:
            continue
        seen.add(seg)
        segs.append(seg)
    return segs


def _target_html_chunk(raw: str) -> str:
    """优先取「最像目标控件」的非 iframe 标签片段，避免点中内部装饰子节点。"""
    text = raw or ""
    scored: list[tuple[int, int]] = []
    for m in _HTML_TAG_OPEN_RE.finditer(text):
        tag = (m.group(1) or "").lower()
        if tag == "iframe":
            continue
        attrs = _parse_attr_blob(m.group(0))
        score = 0
        if attrs.get("id"):
            score += 4
        if attrs.get("aria-label") or attrs.get("aria-labelledby"):
            score += 3
        if attrs.get("data-action") or attrs.get("data-testid") or attrs.get("data-fun"):
            score += 2
        if attrs.get("role"):
            score += 1
        if tag in ("button", "a", "input", "select", "textarea", "label"):
            score += 2
        # 纯装饰小节点降权
        cls = attrs.get("class") or ""
        if tag == "div" and ("img-" in cls or "icon" in cls) and not attrs.get("id"):
            score -= 2
        scored.append((score, m.start()))
    if not scored:
        return text
    scored.sort(key=lambda x: (x[0], x[1]))
    return text[scored[-1][1] :]


def parse_raw_element(raw: str) -> dict[str, Any]:
    """返回 element_data；解析失败时仍带 rawPreview 供 AI 使用。"""
    text = (raw or "").strip()
    if not text:
        return {}

    # JSON（拾取 / 录制 element）
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                data = data[0]
            if isinstance(data, dict):
                out = _normalize_dict_element(data)
                # JSON 里也可带 frame / framePrefix
                fp = (data.get("framePrefix") or data.get("frame") or "").strip()
                if fp:
                    out["framePrefix"] = fp
                    out["frameChain"] = [p for p in fp.split("||") if p.strip()]
                return enrich_relation_hints(out, text)
        except json.JSONDecodeError:
            pass

    # outerHTML（可含多层 iframe + 目标元素）
    if "<" in text and ">" in text:
        frames = extract_iframe_segments(text)
        target_chunk = _target_html_chunk(text)
        parser = _FirstTagParser()
        try:
            parser.feed(target_chunk)
            parser.close()
        except Exception:
            parser = _FirstTagParser()
        if parser.tag and parser.tag != "iframe":
            attrs = parser.attrs
            text_val = _visible_text_from_parts(parser.text_parts)
            out = _attrs_to_element(parser.tag, attrs, text_val, raw_preview=text[:3000])
            if frames:
                out["frameChain"] = frames
                out["framePrefix"] = "||".join(frames)
            return enrich_relation_hints(out, text)
        # 只贴了 iframe：仍返回弱解析 + frame 信息
        if frames:
            return {
                "tag": "",
                "text": "",
                "rawPreview": text[:3000],
                "parseWeak": True,
                "frameChain": frames,
                "framePrefix": "||".join(frames),
            }

    # 属性行：id=saveBtn\nclass=btn primary
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and all(_ATTR_LINE.match(ln) for ln in lines[:12]):
        attrs: dict[str, str] = {}
        for ln in lines:
            m = _ATTR_LINE.match(ln)
            if m:
                attrs[m.group("k").lower()] = m.group("v").strip().strip("\"'")
        tag = (attrs.pop("tag", None) or attrs.pop("tagname", None) or "div").lower()
        text_val = attrs.pop("text", "") or attrs.pop("innertext", "") or attrs.get("aria-label", "")
        return enrich_relation_hints(
            _attrs_to_element(tag, attrs, text_val, raw_preview=text[:2000]),
            text,
        )

    return {"tag": "", "text": text[:80], "rawPreview": text[:2000], "parseWeak": True}


def _normalize_dict_element(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    mapping = {
        "tag": "tag",
        "tagName": "tag",
        "text": "text",
        "accessibleName": "accessibleName",
        "id": "id",
        "class": "class",
        "className": "class",
        "name": "name",
        "title": "title",
        "placeholder": "placeholder",
        "role": "role",
        "ariaLabel": "ariaLabel",
        "aria-label": "ariaLabel",
        "dataTestid": "dataTestid",
        "data-testid": "dataTestid",
        "inputType": "inputType",
        "type": "inputType",
        "region": "region",
        "popupRoot": "popupRoot",
        "cssPath": "cssPath",
        "structurePath": "structurePath",
        "tableXPath": "tableXPath",
        "tableRowXPath": "tableRowXPath",
        "dropdownXPath": "dropdownXPath",
        "absoluteXPath": "absoluteXPath",
        "matchIndex": "matchIndex",
        "rowContext": "rowContext",
        "framePrefix": "framePrefix",
        "frame": "framePrefix",
        "neighborText": "neighborText",
        "neighborRelation": "neighborRelation",
        "neighborTag": "neighborTag",
        "neighborSiblingIndex": "neighborSiblingIndex",
        "neighborClimb": "neighborClimb",
        "neighborClimbLevels": "neighborClimb",
        "neighborTargetTag": "neighborTargetTag",
        "elevateTag": "elevateTag",
        "elevateClass": "elevateClass",
        "elevateText": "elevateText",
        "elevateRole": "elevateRole",
        "elevateDataTestid": "elevateDataTestid",
        "elevateCssPath": "elevateCssPath",
        "elevateMatchIndex": "elevateMatchIndex",
        "ancestorRole": "ancestorRole",
    }
    for src, dst in mapping.items():
        if src in data and data[src] not in (None, ""):
            out[dst] = data[src]
    if "tag" in out:
        out["tag"] = str(out["tag"]).lower()
    return out


def _attrs_to_element(
    tag: str,
    attrs: dict[str, str],
    text: str,
    *,
    raw_preview: str = "",
) -> dict[str, Any]:
    aria = attrs.get("aria-label") or attrs.get("arialabel") or ""
    testid = attrs.get("data-testid") or attrs.get("dataTestid") or ""
    class_name = attrs.get("class") or attrs.get("classname") or ""
    input_type = attrs.get("type") or ""
    out: dict[str, Any] = {
        "tag": tag,
        "text": text,
        "accessibleName": aria or text or attrs.get("title") or "",
        "id": attrs.get("id") or "",
        "class": class_name,
        "name": attrs.get("name") or "",
        "title": attrs.get("title") or "",
        "placeholder": attrs.get("placeholder") or "",
        "role": attrs.get("role") or "",
        "ariaLabel": aria,
        "dataTestid": testid,
        "inputType": input_type,
    }
    if raw_preview:
        out["rawPreview"] = raw_preview
    return out


_MENU_HOST_HINT = re.compile(
    r"menu-item|dropdown-menu__item|dropdown-item|select-dropdown__item|ant-select-item",
    re.I,
)


def enrich_relation_hints(element: dict[str, Any], raw: str = "") -> dict[str, Any]:
    """从 outerHTML / 已有字段补 elevate*、neighbor*（供抬升/相邻候选）。"""
    if not element:
        return element
    out = dict(element)
    raw = raw or str(element.get("rawPreview") or "")
    cls = str(out.get("class") or "")
    text = (out.get("accessibleName") or out.get("text") or "").strip()

    # 邻接：span 文案 + 后随 anticon / tip 图标（不依赖当前解析到的 tag）
    if not out.get("neighborText"):
        m = re.search(
            r"<(?P<ntag>span|label|div|p)\b[^>]*>\s*(?P<ntxt>[^<]{2,40}?)\s*</(?P=ntag)>\s*"
            r"<(?:i|span|em|svg)\b[^>]*class=\"[^\"]*(?:anticon|question|info-circle|el-icon)[^\"]*\"",
            raw,
            re.I | re.S,
        )
        if m:
            ntxt = re.sub(r"\s+", " ", (m.group("ntxt") or "").strip())
            if 1 < len(ntxt) <= 40:
                out["neighborText"] = ntxt
                out["neighborRelation"] = "following-sibling"
                out["neighborTag"] = (m.group("ntag") or "span").lower()
                # 图标真实 tag（供相对定位目标，勿用外层 div）
                window = raw[m.start() : m.start() + len(m.group(0)) + 80]
                icon_m = re.search(
                    r"<(?P<itag>i|span|em|svg)\b[^>]*class=\"[^\"]*(?:anticon|question|info-circle|el-icon)",
                    window,
                    re.I,
                )
                if icon_m:
                    out["neighborTargetTag"] = (icon_m.group("itag") or "i").lower()
                # 只补 neighbor* 字段，不静默改当前 tag/class（点中什么就是什么）

    # 抬升：当前不是菜单项，但目标附近能看到 menu-item 宿主（勿扫整页无关菜单）
    if not out.get("elevateTag"):
        role = (out.get("role") or "").lower()
        already_host = role in ("menuitem", "option") or bool(_MENU_HOST_HINT.search(cls))
        if not already_host:
            # 优先在含当前 class/text 的局部窗口内找祖先菜单项
            search_raw = raw
            anchor = ""
            if cls:
                first_cls = str(cls).split()[0] if str(cls).split() else ""
                if first_cls and len(first_cls) >= 3:
                    pos = raw.lower().find(first_cls.lower())
                    if pos >= 0:
                        search_raw = raw[max(0, pos - 400) : pos + 600]
                        anchor = first_cls
            if text and len(text) >= 2 and not anchor:
                pos = raw.find(text)
                if pos >= 0:
                    search_raw = raw[max(0, pos - 400) : pos + 600]
            m2 = re.search(
                r"<(?P<etag>li|div|span)\b([^>]*class=\"([^\"]*(?:menu-item|dropdown-menu__item|"
                r"dropdown-item|select-dropdown__item|ant-select-item)[^\"]*)\"[^>]*)>",
                search_raw,
                re.I,
            )
            if m2:
                etag = (m2.group("etag") or "li").lower()
                ecls = m2.group(3) or ""
                etext = text
                if out.get("neighborText"):
                    etext = str(out.get("neighborText"))
                out["elevateTag"] = etag
                out["elevateClass"] = ecls
                out["elevateText"] = (etext or "")[:40]
                out["ancestorRole"] = out.get("ancestorRole") or "menu"
    return out


def apply_frame_prefix(locator: str, frame_prefix: str) -> str:
    """给定位器加上 iframe|| 链；已有 || 则不重复。"""
    loc = (locator or "").strip()
    prefix = (frame_prefix or "").strip().strip("|")
    if not loc:
        return ""
    if not prefix:
        return loc
    if "||" in loc:
        return loc
    return f"{prefix}||{loc}"
