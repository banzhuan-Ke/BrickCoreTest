"""Secure JMX XML parsing with size / depth / node limits."""
from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as safe_fromstring

MAX_JMX_BYTES = 5 * 1024 * 1024
MAX_NODES = 8000
MAX_DEPTH = 64
MAX_FIELD_LEN = 200_000


class JmxParseError(ValueError):
    """Raised when JMX content is invalid or unsafe."""


def parse_jmx_bytes(content: bytes) -> Element:
    """Parse .jmx bytes into a root Element. Does not execute scripts or load external entities."""
    if not content:
        raise JmxParseError("空文件")
    if len(content) > MAX_JMX_BYTES:
        raise JmxParseError(f"文件过大，上限 {MAX_JMX_BYTES // (1024 * 1024)}MB")

    # Reject obvious XXE / DTD attempts before parse (defense in depth; defusedxml also blocks)
    head = content[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head or (b"system " in head and b"entity" in head):
        raise JmxParseError("拒绝包含 DTD / 外部实体的 JMX")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise JmxParseError("文件编码必须为 UTF-8") from exc

    try:
        root = safe_fromstring(text)
    except Exception as exc:
        raise JmxParseError(f"XML 解析失败: {exc}") from exc

    if root is None:
        raise JmxParseError("空 XML")

    tag = _local_tag(root.tag)
    if tag not in ("jmeterTestPlan", "hashTree"):
        # Some exports wrap oddly; still require jmeterTestPlan preferably
        if tag != "jmeterTestPlan":
            raise JmxParseError(f"非 JMeter 测试计划根节点: {tag}")

    node_count = 0
    _walk_limits(root, depth=0, node_count_ref=[node_count])
    return root


def _local_tag(tag: str) -> str:
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return str(tag)


def _walk_limits(el: Element, depth: int, node_count_ref: list[int]) -> None:
    if depth > MAX_DEPTH:
        raise JmxParseError(f"XML 层级过深，上限 {MAX_DEPTH}")
    node_count_ref[0] += 1
    if node_count_ref[0] > MAX_NODES:
        raise JmxParseError(f"节点数过多，上限 {MAX_NODES}")
    for child in list(el):
        _walk_limits(child, depth + 1, node_count_ref)


def element_to_shallow_dict(el: Element) -> dict[str, Any]:
    """Debug helper: shallow attrs + text for a node."""
    return {
        "tag": _local_tag(el.tag),
        "attrib": dict(el.attrib or {}),
        "text": (el.text or "").strip()[:200],
    }
