"""
测试用例步骤与预期对齐（保证 1:1 数量一致）
"""
import re
from typing import Any


_NUMBERED_LINE = re.compile(r"^\s*\d+[.、．)\]]\s*", re.MULTILINE)
_PLACEHOLDER_STEP = re.compile(r"^执行步骤 \d+$")


def _empty_step_fallback(step_index: int, expect: str, *, fallback_expect: str) -> str:
    """步骤为空但有预期时，用预期摘要代替「执行步骤 N」占位"""
    e = (expect or "").strip()
    if e and e != fallback_expect:
        return f"确认：{e[:120]}"
    return f"执行步骤 {step_index}"


def _trim_duplicate_trailing_expects(step_lines: list[str], expect_lines: list[str]) -> list[str]:
    """AI 常在 expect 里重复编号预期却无对应 step，去掉与上一条相同的多余预期"""
    if not step_lines or len(expect_lines) <= len(step_lines):
        return expect_lines
    trimmed = list(expect_lines)
    while len(trimmed) > len(step_lines):
        anchor = trimmed[len(step_lines) - 1]
        extra = trimmed[len(step_lines)]
        if extra == anchor:
            trimmed.pop(len(step_lines))
        else:
            break
    return trimmed


def _dedupe_redundant_step_pairs(result: list[dict], *, fallback_expect: str) -> list[dict]:
    """去掉与上一步预期相同、且 step 为占位/确认文案的多余步骤"""
    if len(result) < 2:
        return result
    cleaned = [result[0]]
    for item in result[1:]:
        prev = cleaned[-1]
        step = (item.get("step") or "").strip()
        expect = (item.get("expect") or "").strip()
        prev_expect = (prev.get("expect") or "").strip()
        if expect == prev_expect and (
            _PLACEHOLDER_STEP.match(step)
            or step.startswith("确认：")
            or _is_auto_placeholder(step, expect, fallback_expect=fallback_expect)
        ):
            continue
        cleaned.append(item)
    return cleaned


def _is_auto_placeholder(step: str, expect: str, *, fallback_expect: str) -> bool:
    return bool(_PLACEHOLDER_STEP.match((step or "").strip())) and (expect or "").strip() == fallback_expect


def normalize_corner_quotes(text: str) -> str:
    """UI 元素名：「按钮」→ \"按钮\" """
    if not text:
        return text
    return str(text).replace("「", '"').replace("」", '"')


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
) -> list[dict]:
    """
    保证返回的 steps 数组每条同时有 step、expect，且条数一致。
    支持：多步合并在一个字符串、预期少写一条等情况自动补齐；不强制最少步数。
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
        expect_lines = _trim_duplicate_trailing_expects(step_lines, expect_lines)

        n = max(len(step_lines), len(expect_lines))
        for i in range(n):
            s = (step_lines[i] if i < len(step_lines) else "").strip()
            e = (expect_lines[i] if i < len(expect_lines) else "").strip()
            if not s:
                s = _empty_step_fallback(len(all_steps) + 1, e, fallback_expect=fallback_expect)
            all_steps.append(s)
            if e:
                all_expects.append(e)
            elif i < len(expect_lines):
                all_expects.append(fallback_expect)
            else:
                all_expects.append(fallback_expect)

    if not all_steps:
        return [{"step": "执行操作", "expect": fallback_expect}]

    n = max(len(all_steps), len(all_expects))
    result = []
    for i in range(n):
        e = (all_expects[i] if i < len(all_expects) else "").strip() or fallback_expect
        s = (all_steps[i] if i < len(all_steps) else "").strip()
        if not s:
            s = _empty_step_fallback(i + 1, e, fallback_expect=fallback_expect)
        result.append({
            "step": normalize_corner_quotes(s),
            "expect": normalize_corner_quotes(e),
        })

    while len(result) > 1 and _is_auto_placeholder(
        result[-1]["step"], result[-1]["expect"], fallback_expect=fallback_expect
    ):
        result.pop()

    return _dedupe_redundant_step_pairs(result, fallback_expect=fallback_expect)
