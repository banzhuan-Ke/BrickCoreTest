"""
测试用例步骤与预期对齐（保证 1:1 数量一致）
"""
import re
from typing import Any


_NUMBERED_LINE = re.compile(r"^\s*\d+[.、．)\]]\s*", re.MULTILINE)


def _strip_number_prefix(text: str) -> str:
    return re.sub(r"^\s*\d+[.、．)\]]\s*", "", (text or "").strip()).strip()


def split_numbered_lines(text: str) -> list[str]:
    """将「1.xxx\\n2.yyy」或单段文本拆成多条"""
    if not text or not str(text).strip():
        return []
    raw = str(text).strip().replace("\r\n", "\n")
    if not _NUMBERED_LINE.search(raw):
        return [raw]

    chunks = re.split(r"\n\s*(?=\d+[.、．)\]]\s*)", raw)
    if len(chunks) <= 1:
        chunks = re.split(r"(?=\d+[.、．)\]]\s*)", raw)

    lines: list[str] = []
    for chunk in chunks:
        line = _strip_number_prefix(chunk)
        if line:
            lines.append(line)
    return lines if lines else [raw]


def _parse_steps_field(steps: Any) -> list[dict]:
    """从 AI/前端多种结构解析为 [{step, expect}, ...]"""
    pairs: list[dict] = []

    if isinstance(steps, list):
        for st in steps:
            if isinstance(st, dict):
                step_text = (
                    st.get("step")
                    or st.get("action")
                    or st.get("步骤")
                    or st.get("操作")
                    or ""
                ).strip()
                expect_text = (
                    st.get("expect")
                    or st.get("expected")
                    or st.get("预期")
                    or st.get("期望")
                    or ""
                ).strip()
                if step_text or expect_text:
                    pairs.append({"step": step_text, "expect": expect_text})
            elif isinstance(st, str) and st.strip():
                pairs.append({"step": st.strip(), "expect": ""})
    elif isinstance(steps, str) and steps.strip():
        pairs.append({"step": steps.strip(), "expect": ""})

    return pairs


def align_steps_expects(
    steps: Any,
    *,
    fallback_expect: str = "符合预期",
    min_steps: int = 1,
) -> list[dict]:
    """
    保证返回的 steps 数组每条同时有 step、expect，且条数一致。
    支持：多步合并在一个字符串、预期少写一条等情况自动补齐。
    """
    pairs = _parse_steps_field(steps)

    if not pairs and isinstance(steps, dict):
        pairs = _parse_steps_field(steps.get("items") or steps.get("list"))

    if not pairs:
        return [{"step": "执行操作", "expect": fallback_expect}]

    all_steps: list[str] = []
    all_expects: list[str] = []

    for item in pairs:
        step_lines = split_numbered_lines(item.get("step") or "")
        expect_lines = split_numbered_lines(item.get("expect") or "")

        if not step_lines and not expect_lines:
            continue
        if not step_lines:
            step_lines = [""] * max(len(expect_lines), 1)
        if not expect_lines:
            expect_lines = [""] * len(step_lines)

        n = max(len(step_lines), len(expect_lines))
        for i in range(n):
            s = (step_lines[i] if i < len(step_lines) else "").strip()
            e = (expect_lines[i] if i < len(expect_lines) else "").strip()
            all_steps.append(s or f"执行步骤 {len(all_steps) + 1}")
            if e:
                all_expects.append(e)
            elif i < len(expect_lines):
                all_expects.append(fallback_expect)
            else:
                all_expects.append(fallback_expect)

    if not all_steps:
        return [{"step": "执行操作", "expect": fallback_expect}]

    n = max(len(all_steps), len(all_expects), min_steps)
    while len(all_steps) < n:
        all_steps.append(f"执行步骤 {len(all_steps) + 1}")
    while len(all_expects) < n:
        all_expects.append(
            all_expects[-1] if all_expects else fallback_expect
        )

    if len(all_expects) > n:
        all_expects = all_expects[:n]
    if len(all_steps) > n:
        all_steps = all_steps[:n]

    # 最终以较大长度对齐（防止 expect 多写）
    n = max(len(all_steps), len(all_expects))
    result = []
    for i in range(n):
        s = (all_steps[i] if i < len(all_steps) else "").strip() or f"执行步骤 {i + 1}"
        e = (all_expects[i] if i < len(all_expects) else "").strip() or fallback_expect
        result.append({"step": s, "expect": e})

    return result
