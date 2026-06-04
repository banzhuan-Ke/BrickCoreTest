"""
需求文档结构化：章节、范围选择、交错正文与读图结果、Token 估算
"""
from __future__ import annotations

import re
from typing import Any, Optional

# 单次生成建议上限（字符，中文约 1.5~2 token/字）
MAX_SCOPE_CHARS = 48000
WARN_ESTIMATED_INPUT_TOKENS = 12000
BLOCK_ESTIMATED_INPUT_TOKENS = 28000
FALLBACK_SECTION_CHARS = 4500

_HEADING_MD = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def blocks_to_sections(blocks: list[dict], source_type: str) -> list[dict]:
    """由块列表构建章节树（扁平列表，含 level）"""
    if not blocks:
        return [{
            "id": "sec-1",
            "title": "全文",
            "level": 1,
            "block_ids": [],
            "char_count": 0,
            "image_indices": [],
        }]

    if source_type == "pdf":
        return attach_section_parents(_sections_from_pdf_pages(blocks))

    # Word / 其他：按标题块切分
    sections: list[dict] = []
    current: Optional[dict] = None
    sec_idx = 0

    def _flush():
        nonlocal current, sec_idx
        if not current:
            return
        current["char_count"] = len(current.get("_text_buf", ""))
        current.pop("_text_buf", None)
        sections.append(current)
        current = None

    for blk in blocks:
        bid = blk.get("id") or f"b{len(blocks)}"
        btype = blk.get("type") or "paragraph"
        if btype == "heading":
            _flush()
            sec_idx += 1
            current = {
                "id": f"sec-{sec_idx}",
                "title": (blk.get("text") or f"章节 {sec_idx}").strip()[:200],
                "level": int(blk.get("level") or 1),
                "block_ids": [bid],
                "image_indices": [],
                "_text_buf": "",
            }
            t = (blk.get("text") or "").strip()
            if t:
                current["_text_buf"] += t + "\n"
        else:
            if not current:
                sec_idx += 1
                current = {
                    "id": f"sec-{sec_idx}",
                    "title": "正文",
                    "level": 1,
                    "block_ids": [],
                    "image_indices": [],
                    "_text_buf": "",
                }
            current["block_ids"].append(bid)
            if btype == "image":
                idx = blk.get("image_index")
                if idx is not None and idx not in current["image_indices"]:
                    current["image_indices"].append(idx)
            else:
                t = (blk.get("text") or "").strip()
                if t:
                    current["_text_buf"] += t + "\n"

    _flush()

    if not sections:
        return attach_section_parents(_chunk_sections_by_chars(blocks, "正文"))

    # 无标题时仅一个大块 → 按字数再切
    if len(sections) == 1 and sections[0]["title"] in ("正文", "全文"):
        total = sections[0]["char_count"]
        if total > FALLBACK_SECTION_CHARS * 1.5:
            return attach_section_parents(_chunk_sections_by_chars(blocks, "分块"))

    return attach_section_parents(sections)


def attach_section_parents(sections: list[dict]) -> list[dict]:
    """按标题 level 为扁平章节附加 parent_id，供前端树形展示"""
    stack: list[tuple[str, int]] = []
    for sec in sections:
        level = int(sec.get("level") or 1)
        while stack and stack[-1][1] >= level:
            stack.pop()
        sec["parent_id"] = stack[-1][0] if stack else None
        stack.append((sec["id"], level))
    return sections


def compute_section_coverage(
    all_sections: list[dict],
    cases: list[Any],
) -> dict:
    """统计章节覆盖：已生成用例涉及章节 / 未覆盖列表"""
    if not all_sections:
        return {
            "total": 0,
            "covered_count": 0,
            "uncovered_count": 0,
            "covered_section_ids": [],
            "uncovered_sections": [],
        }
    all_ids = {s.get("id") for s in all_sections if s.get("id")}
    covered: set[str] = set()
    for case in cases:
        if isinstance(case, dict):
            ids = case.get("section_ids") or []
        else:
            ids = getattr(case, "section_ids", None) or []
        for sid in ids:
            if sid in all_ids:
                covered.add(sid)
    uncovered = [s for s in all_sections if s.get("id") not in covered]
    return {
        "total": len(all_ids),
        "covered_count": len(covered),
        "uncovered_count": len(uncovered),
        "covered_section_ids": sorted(covered),
        "uncovered_sections": [
            {"id": s.get("id"), "title": s.get("title"), "level": s.get("level")}
            for s in uncovered
        ],
    }


def _sections_from_pdf_pages(blocks: list[dict]) -> list[dict]:
    by_page: dict[int, dict] = {}
    for blk in blocks:
        page = int(blk.get("page") or 1)
        if page not in by_page:
            by_page[page] = {
                "id": f"page-{page}",
                "title": f"第 {page} 页",
                "level": 1,
                "block_ids": [],
                "image_indices": [],
                "_text_buf": "",
            }
        sec = by_page[page]
        bid = blk.get("id") or ""
        if bid:
            sec["block_ids"].append(bid)
        if blk.get("type") == "image":
            idx = blk.get("image_index")
            if idx is not None:
                sec["image_indices"].append(idx)
        else:
            t = (blk.get("text") or "").strip()
            if t:
                sec["_text_buf"] += t + "\n"

    sections = []
    for page in sorted(by_page.keys()):
        s = by_page[page]
        s["char_count"] = len(s.pop("_text_buf", ""))
        sections.append(s)
    return sections or _chunk_sections_by_chars(blocks, "分块")


def _chunk_sections_by_chars(blocks: list[dict], prefix: str) -> list[dict]:
    sections = []
    buf_ids: list[str] = []
    buf_images: list[int] = []
    buf_text = ""
    sec_idx = 0

    def _flush():
        nonlocal buf_ids, buf_images, buf_text, sec_idx
        if not buf_ids and not buf_text:
            return
        sec_idx += 1
        sections.append({
            "id": f"sec-{sec_idx}",
            "title": f"{prefix} {sec_idx}",
            "level": 1,
            "block_ids": list(buf_ids),
            "image_indices": list(buf_images),
            "char_count": len(buf_text),
        })
        buf_ids = []
        buf_images = []
        buf_text = ""

    for blk in blocks:
        bid = blk.get("id") or ""
        t = (blk.get("text") or "").strip()
        if blk.get("type") == "image":
            idx = blk.get("image_index")
            if idx is not None:
                buf_images.append(idx)
            if bid:
                buf_ids.append(bid)
        elif t:
            if len(buf_text) + len(t) > FALLBACK_SECTION_CHARS and buf_text:
                _flush()
            if bid:
                buf_ids.append(bid)
            buf_text += t + "\n"
    _flush()
    return sections


def resolve_sections(
    all_sections: list[dict],
    selected_ids: Optional[list[str]] = None,
) -> list[dict]:
    if not all_sections:
        return []
    if not selected_ids:
        return list(all_sections)
    id_set = set(selected_ids)
    return [s for s in all_sections if s.get("id") in id_set]


def section_text(blocks: list[dict], section: dict) -> str:
    id_set = set(section.get("block_ids") or [])
    parts = []
    for blk in blocks:
        if blk.get("id") not in id_set:
            continue
        if blk.get("type") == "image":
            continue
        t = (blk.get("text") or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def build_interleaved_content(
    blocks: list[dict],
    sections: list[dict],
    vision_text_by_image: Optional[dict[int, str]] = None,
) -> str:
    """按阅读顺序输出：章节标题 → 段落 → [图N 理解] → …"""
    vision_text_by_image = vision_text_by_image or {}
    block_map = {b.get("id"): b for b in blocks if b.get("id")}
    parts: list[str] = []

    for sec in sections:
        title = sec.get("title") or "章节"
        parts.append(f"## {title}\n")
        for bid in sec.get("block_ids") or []:
            blk = block_map.get(bid)
            if not blk:
                continue
            if blk.get("type") == "image":
                idx = blk.get("image_index")
                anchor = blk.get("anchor") or (f"第 {blk.get('page')} 页" if blk.get("page") else "")
                vtext = vision_text_by_image.get(idx, "") if idx is not None else ""
                label = f"[图-{idx + 1 if idx is not None else '?'}]"
                if anchor:
                    label += f" ({anchor})"
                if vtext:
                    parts.append(f"{label}\n{vtext}\n")
                else:
                    parts.append(f"{label}（未读图或读图失败）\n")
            else:
                t = (blk.get("text") or "").strip()
                if t:
                    parts.append(t + "\n")
        parts.append("")
    return "\n".join(parts).strip()


def collect_image_indices(
    sections: list[dict],
    blocks: Optional[list[dict]] = None,
) -> list[int]:
    """收集选中章节内的图片索引；若章节未写 image_indices 则从 blocks 回退。"""
    indices: list[int] = []
    seen: set[int] = set()

    def _add(idx: Any) -> None:
        if idx is None:
            return
        i = int(idx)
        if i not in seen:
            seen.add(i)
            indices.append(i)

    for sec in sections:
        for idx in sec.get("image_indices") or []:
            _add(idx)

    if not indices and blocks:
        block_map = {b.get("id"): b for b in blocks if b.get("id")}
        scope_block_ids: set[str] = set()
        for sec in sections:
            scope_block_ids.update(sec.get("block_ids") or [])
        for bid in scope_block_ids:
            blk = block_map.get(bid)
            if blk and blk.get("type") == "image":
                _add(blk.get("image_index"))

    return indices


def estimate_scope(
    scoped_text: str,
    image_count: int = 0,
) -> dict:
    chars = len(scoped_text or "")
    # 中文为主：粗算 input tokens
    est_tokens = int(chars / 1.6) + image_count * 600
    level = "ok"
    if est_tokens >= BLOCK_ESTIMATED_INPUT_TOKENS:
        level = "block"
    elif est_tokens >= WARN_ESTIMATED_INPUT_TOKENS:
        level = "warn"
    return {
        "char_count": chars,
        "image_count": image_count,
        "estimated_input_tokens": est_tokens,
        "warn_tokens": WARN_ESTIMATED_INPUT_TOKENS,
        "block_tokens": BLOCK_ESTIMATED_INPUT_TOKENS,
        "max_scope_chars": MAX_SCOPE_CHARS,
        "level": level,
        "message": _estimate_message(level, est_tokens, chars),
    }


def _estimate_message(level: str, tokens: int, chars: int) -> str:
    if level == "block":
        return f"预估输入约 {tokens} tokens（{chars} 字），已接近上限，请减少选中章节"
    if level == "warn":
        return f"预估输入约 {tokens} tokens，章节较多，建议缩小范围或降低目标用例数"
    return f"预估输入约 {tokens} tokens，可生成"


def truncate_scope_text(text: str, max_chars: int = MAX_SCOPE_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n…（后续内容已截断，请缩小章节范围）", True


def vision_summary_to_text(parsed: Any) -> str:
    if isinstance(parsed, dict):
        import json
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    return str(parsed or "").strip()
