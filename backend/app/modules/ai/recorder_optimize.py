"""
录制步骤 AI 优化：页面上下文提取、断言步骤生成
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ASSERTION_METHODS = frozenset({
    "kw_assert_visible",
    "kw_assert_element_text",
    "kw_assert_page_url",
    "kw_assert_page_title",
    "kw_assert_hidden",
    "kw_assert_not_exist",
    "kw_assert_not_visible",
    "kw_assert_enabled",
})

_APP_ASSERTION_METHODS = frozenset({
    "assert_exists",
    "assert_not_exists",
    "assert_text",
    "assert_text_contains",
})

# 否定类预期关键词 → 建议断言类型
_NOT_EXIST_HINTS = (
    "不存在", "不应出现", "不应显示", "不应有", "没有该", "无该", "不包含",
    "未出现", "不出现", "没有「", "无「", "缺少", "不应包含",
)
_NOT_VISIBLE_HINTS = (
    "不可见", "未显示", "看不到", "不展示", "未展示", "未露出",
)
_HIDDEN_HINTS = (
    "隐藏", "收起", "折叠", "collapsed",
)

_ACTION_METHODS = frozenset({
    "click_ele",
    "fill_value",
    "hover",
    "double_click_ele",
    "select_option",
})

# 从功能用例描述中提取「预期：xxx」
_EXPECT_PATTERNS = (
    re.compile(r"→\s*预期[:：]\s*(.+?)(?:\n|$)"),
    re.compile(r"预期[:：]\s*(.+?)(?:\n|$)"),
    re.compile(r"预期结果[:：]\s*(.+?)(?:\n|$)"),
)


def _extract_json_from_text(content: str) -> Optional[str]:
    md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if md_match:
        return md_match.group(1).strip()
    start = content.find('{')
    if start == -1:
        return None
    count = 0
    in_string = False
    escape = False
    for i, c in enumerate(content[start:], start):
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            count += 1
        elif c == '}':
            count -= 1
            if count == 0:
                return content[start:i + 1]
    return None


def extract_expectations(description: str) -> list[str]:
    """从测试描述中提取预期结果列表"""
    if not description:
        return []
    expects: list[str] = []
    seen: set[str] = set()
    for pat in _EXPECT_PATTERNS:
        for m in pat.finditer(description):
            text = (m.group(1) or "").strip()
            if text and text not in seen and len(text) <= 200:
                seen.add(text)
                expects.append(text)
    return expects


def infer_assertion_type_hint(expectation: str) -> str:
    """根据预期文案推断建议使用的断言 method"""
    text = (expectation or "").strip()
    if not text:
        return "kw_assert_visible（正向）"
    if any(k in text for k in _NOT_EXIST_HINTS):
        return "kw_assert_not_exist（DOM 无匹配，如菜单/列表无该项）"
    if any(k in text for k in _NOT_VISIBLE_HINTS):
        return "kw_assert_not_visible（DOM 可有，但对用户不可见）"
    if any(k in text for k in _HIDDEN_HINTS):
        return "kw_assert_hidden（CSS hidden / 未挂载）"
    if any(k in text for k in ("仅显示", "只显示", "仅有", "只有")):
        return "kw_assert_visible + kw_assert_not_exist（应出现的用 visible，不应出现的用 not_exist）"
    return "kw_assert_visible / kw_assert_element_text（正向）"


def format_expectations_for_assert_prompt(expectations: list[str], description: str = "") -> str:
    """为 LLM 格式化预期列表，附带断言类型建议"""
    lines: list[str] = []
    for e in expectations:
        lines.append(f"- {e}  → 建议: {infer_assertion_type_hint(e)}")
    if not lines and description:
        # 从全文再扫一遍否定表述
        for pat in (
            r"不存在[「\"']?([^」\"'\n，。；]+)",
            r"不应出现[「\"']?([^」\"'\n，。；]+)",
            r"无[「\"']([^」\"'\n，。；]+)[」\"']?选项",
        ):
            for m in re.finditer(pat, description):
                target = (m.group(1) or "").strip()
                if target and len(target) <= 40:
                    lines.append(
                        f"- （从描述推断）不应出现「{target}」"
                        f"  → 建议: kw_assert_not_exist"
                    )
    if lines:
        return "\n".join(lines)
    if description:
        budget = compute_assertion_budget(description)
        return (
            f"（描述中无明确「预期：」；仅对主要业务节点生成约 {budget} 条 outcome 断言，"
            "勿对表单输入框做操作前可见性断言）"
        )
    return "（请从测试描述推断）"


def compute_assertion_budget(description: str) -> int:
    """
    根据测试描述估算断言条数上限。
    有明确「预期：」时按条数略放宽；否则按业务流程分段（然后/逗号等）计数，默认偏少。
    """
    text = (description or "").strip()
    if not text:
        return 0

    expectations = extract_expectations(text)
    if expectations:
        return min(len(expectations) + 1, 6)

    segments = re.split(r"[，,；;]|然后|接着|之后|并且|再", text)
    segments = [s.strip() for s in segments if s.strip() and len(s) > 2]
    if segments:
        # 无明确「预期：」时偏保守，避免流程类描述膨胀为大量字段可见性断言
        return min(max(1, len(segments)), 2)
    return 1


_PREFLIGHT_ASSERT_HINTS = (
    "输入框", "输入栏", "文本框", "请输入", "密码框", "用户名字段", "密码字段",
    "搜索框", "登录按钮", "登录页", "查询页", "密码输入", "用户名输入",
)

# 描述里含这些词才保留 kw_assert_visible（业务结果向）
_OUTCOME_ASSERT_KEYWORDS = (
    "成功", "失败", "结果", "列表", "跳转", "包含", "不存在", "不应", "错误", "提示",
)

_ACTION_WITH_LOCATOR = frozenset({
    "click_ele", "fill_value", "hover", "double_click_ele", "select_option",
    "type_value", "wait_for_element",
})


def _assertion_placement(assertion: dict) -> str:
    return str(
        assertion.get("placement")
        or (assertion.get("meta") or {}).get("assertion_placement")
        or "before"
    ).lower()


def _is_redundant_preflight_assertion(assertion: dict) -> bool:
    """过滤「输入前断言输入框可见」等低价值断言"""
    desc = (assertion.get("desc") or "").lower()
    if any(h in desc for h in _PREFLIGHT_ASSERT_HINTS):
        return True
    if re.search(r"显示.+框|按钮可见|页面显示", desc):
        return True

    method = assertion.get("method") or ""
    if method == "kw_assert_visible":
        if _assertion_placement(assertion) == "before":
            return True
        if not any(k in desc for k in _OUTCOME_ASSERT_KEYWORDS):
            if re.search(r"(输入|密码|按钮|搜索|登录|查询|框|表单|可见)", desc):
                return True

    params = assertion.get("params") or {}
    locator = str(params.get("locator") or "")
    loc_lower = locator.lower()
    if loc_lower.startswith("get_by_text="):
        label = locator.split("=", 1)[1].strip()
        if "请输入" in label or label.endswith("输入"):
            return True
    if _assertion_placement(assertion) == "before" and (
        "input" in loc_lower
        or "#input" in loc_lower
        or "placeholder" in desc
    ):
        return True
    return False


def _rewrite_weak_assertion_locator(locator: str) -> str:
    """
    将易失败的 get_by_text 写法改为更通用的定位方式。
    Playwright 的 get_by_text 不匹配 input placeholder，应使用 get_by_placeholder。
    """
    loc = (locator or "").strip()
    if not loc.lower().startswith("get_by_text="):
        return loc
    text = loc.split("=", 1)[1].strip()
    if not text:
        return loc
    if text.startswith("请输入"):
        return f"get_by_placeholder={text}"
    # 短文案且无句读，多为 placeholder（如「模糊搜索」）
    if len(text) <= 20 and not re.search(r"[，。！？、\s]", text):
        return f"get_by_placeholder={text}"
    return loc


def _locator_from_anchor_steps(action_steps: list, anchor_step: Any) -> Optional[str]:
    """从锚定操作步骤及其邻近步骤复制已验证过的 locator"""
    if anchor_step is None:
        return None
    try:
        idx = int(anchor_step) - 1
    except (TypeError, ValueError):
        return None
    if idx < 0 or idx >= len(action_steps):
        return None
    for j in range(idx, min(len(action_steps), idx + 3)):
        step = action_steps[j]
        if not isinstance(step, dict):
            continue
        if step.get("method") not in _ACTION_WITH_LOCATOR:
            continue
        loc = (step.get("params") or {}).get("locator") or ""
        if loc and str(loc).strip():
            return str(loc).strip()
    for j in range(max(0, idx - 2), idx):
        step = action_steps[j]
        if not isinstance(step, dict):
            continue
        if step.get("method") not in _ACTION_WITH_LOCATOR:
            continue
        loc = (step.get("params") or {}).get("locator") or ""
        if loc and str(loc).strip():
            return str(loc).strip()
    return None


def should_generate_assertions(description: str) -> tuple[bool, str]:
    """是否应进入断言生成阶段；返回 (是否生成, 跳过原因)。"""
    text = (description or "").strip()
    if not text:
        return False, "empty_description"
    expectations = extract_expectations(text)
    if expectations:
        return True, ""
    if re.search(r"预期", text):
        return True, ""
    return False, "no_expectations_in_description"


def refine_assertion_candidates(
    candidates: list,
    *,
    action_steps: list,
    max_count: int,
) -> list:
    """规范化 locator、对齐录制步骤、过滤并裁剪断言条数"""
    if not candidates or max_count <= 0:
        return []

    refined: list = []
    for ass in candidates:
        if not isinstance(ass, dict):
            continue
        params = ass.setdefault("params", {})
        loc = str(params.get("locator") or "").strip()
        if loc:
            params["locator"] = _rewrite_weak_assertion_locator(loc)

        anchor = ass.get("anchor_step") or (ass.get("meta") or {}).get("anchor_step")
        if anchor is not None and action_steps:
            try:
                anchor_idx = int(anchor) - 1
                if anchor_idx < 0 or anchor_idx >= len(action_steps):
                    anchor_idx = max(0, min(anchor_idx, len(action_steps) - 1))
                    ass["anchor_step"] = anchor_idx + 1
            except (TypeError, ValueError):
                pass
        step_loc = _locator_from_anchor_steps(action_steps, ass.get("anchor_step"))
        if step_loc:
            cur = str(params.get("locator") or "")
            prefer_step = (
                cur.startswith("get_by_text=")
                or cur.startswith("get_by_label=")
                or cur.startswith("get_by_placeholder=")
                or not cur
            )
            if prefer_step and step_loc.startswith(("#", "[", ".")):
                params["locator"] = step_loc
            elif prefer_step and step_loc.startswith(("get_by_", "#")):
                params["locator"] = step_loc

        refined.append(ass)

    return cap_assertion_steps(refined, max_count=max_count)


def _assertion_priority(assertion: dict) -> int:
    """数值越大越优先保留"""
    method = assertion.get("method") or ""
    placement = str(
        assertion.get("placement")
        or (assertion.get("meta") or {}).get("assertion_placement")
        or ""
    ).lower()
    score = 0
    if placement == "after":
        score += 20
    elif placement == "before":
        score += 5
    if method in ("kw_assert_page_url", "kw_assert_page_title"):
        score += 15
    elif method in ("kw_assert_not_exist", "kw_assert_not_visible", "kw_assert_hidden"):
        score += 12
    elif method == "kw_assert_element_text":
        score += 10
    elif method == "kw_assert_visible":
        score += 6
    if _is_redundant_preflight_assertion(assertion):
        score -= 100
    return score


def cap_assertion_steps(candidates: list, *, max_count: int) -> list:
    """按预算上限保留高价值断言，并剔除输入前可见性类断言"""
    if max_count <= 0 or not candidates:
        return []
    filtered = [c for c in candidates if isinstance(c, dict) and not _is_redundant_preflight_assertion(c)]
    if not filtered:
        return []
    if len(filtered) <= max_count:
        return filtered
    ranked = sorted(
        enumerate(filtered),
        key=lambda item: (_assertion_priority(item[1]), -item[0]),
        reverse=True,
    )
    kept_indices = sorted(i for i, _ in ranked[:max_count])
    return [filtered[i] for i in kept_indices]


def extract_page_context(raw_actions: list, *, max_lines: int = 60) -> str:
    """
    从录制原始操作中汇总「页面可见文本 + 定位器」快照，供断言推断使用。
    非实时 DOM，但比纯描述更接近录制结束时的页面状态。
    """
    if not raw_actions:
        return ""
    lines: list[str] = []
    seen: set[str] = set()

    for act in raw_actions:
        if not isinstance(act, dict):
            continue
        text = (act.get("element_text") or act.get("text") or "").strip()
        selector = (act.get("selector") or "").strip()
        url = (act.get("url") or "").strip()
        action_type = (act.get("action_type") or "").strip()

        if url and url not in seen:
            seen.add(url)
            lines.append(f"- [navigate] URL: {url}")

        if text and len(text) <= 120:
            key = f"{action_type}:{text}:{selector}"
            if key not in seen:
                seen.add(key)
                loc = selector or "（无 selector）"
                lines.append(f"- [{action_type or 'action'}] 可见文本: 「{text}」 | 定位: {loc}")

        if len(lines) >= max_lines:
            break

    return "\n".join(lines)


def _build_locator_meta_map(raw_actions: list) -> dict[str, dict]:
    """text/selector -> meta 映射，供断言步骤补 meta"""
    mapping: dict[str, dict] = {}
    for act in raw_actions or []:
        if not isinstance(act, dict):
            continue
        meta = act.get("meta") or {}
        if not meta:
            continue
        text = (act.get("element_text") or "").strip()
        selector = (act.get("selector") or "").strip()
        if text:
            mapping[text.lower()] = meta
        if selector:
            mapping[selector] = meta
    return mapping


def _patch_assertion_meta(steps: list, raw_actions: list) -> None:
    """为断言步骤补回 meta（便于前端 LocatorSelector 微调）"""
    loc_map = _build_locator_meta_map(raw_actions)
    for step in steps:
        if not isinstance(step, dict):
            continue
        if not str(step.get("method", "")).startswith("kw_assert_"):
            continue
        if step.get("meta"):
            continue
        locator = (step.get("params") or {}).get("locator") or ""
        text = (step.get("params") or {}).get("text") or ""
        meta = loc_map.get(locator) or (loc_map.get(text.lower()) if text else None)
        if meta:
            step["meta"] = meta


def _normalize_locator_key(locator: str) -> str:
    if not locator:
        return ""
    return str(locator).strip().lower()


def _text_from_get_by_text(locator: str) -> str:
    loc = str(locator or "")
    if loc.lower().startswith("get_by_text="):
        return loc.split("=", 1)[1].strip()
    return ""


def _find_matching_action_index(action_steps: list, assertion: dict) -> int:
    """返回与断言最相关的操作步骤下标；无匹配时返回 len(action_steps)。"""
    ass_params = assertion.get("params") or {}
    ass_loc = _normalize_locator_key(ass_params.get("locator") or "")
    ass_text = (ass_params.get("text") or "").strip().lower()
    ass_gb_text = _text_from_get_by_text(ass_params.get("locator") or "").lower()

    for i in range(len(action_steps) - 1, -1, -1):
        step = action_steps[i]
        if step.get("method") not in _ACTION_METHODS:
            continue
        params = step.get("params") or {}
        step_loc = _normalize_locator_key(params.get("locator") or "")
        step_desc = (step.get("desc") or "").lower()
        step_gb_text = _text_from_get_by_text(params.get("locator") or "").lower()

        if ass_loc and step_loc and (
            ass_loc == step_loc or ass_loc in step_loc or step_loc in ass_loc
        ):
            return i
        if ass_gb_text and step_gb_text and (
            ass_gb_text in step_gb_text or step_gb_text in ass_gb_text
        ):
            return i
        for kw in (ass_text, ass_gb_text):
            if kw and len(kw) >= 2 and kw in step_desc:
                return i
    return len(action_steps)


def insert_assertions_into_steps(action_steps: list, assertions: list) -> list:
    """
    按 placement + anchor_step 将断言插入步骤流。
    同一操作前/后可有多条断言；多条断言按 anchor 锚定到原始步骤序号。
    """
    if not assertions:
        return list(action_steps)

    before_map: dict[int, list] = {}
    after_map: dict[int, list] = {}
    trailing: list = []

    for ass in assertions:
        if not isinstance(ass, dict):
            continue
        meta = ass.get("meta") or {}
        placement = str(
            ass.get("placement") or meta.get("assertion_placement") or "before"
        ).lower()
        if placement not in ("before", "after"):
            placement = "before"

        anchor_step = ass.get("anchor_step")
        if anchor_step is None:
            anchor_step = meta.get("anchor_step")

        anchor_idx: Optional[int] = None
        if anchor_step is not None:
            try:
                anchor_idx = int(anchor_step) - 1
            except (TypeError, ValueError):
                anchor_idx = None

        if anchor_idx is None:
            anchor_idx = _find_matching_action_index(action_steps, ass)
            if anchor_idx >= len(action_steps):
                trailing.append(ass)
                continue

        if anchor_idx < 0:
            trailing.append(ass)
        elif placement == "before":
            before_map.setdefault(anchor_idx, []).append(ass)
        else:
            after_map.setdefault(anchor_idx, []).append(ass)

    result: list = []
    for i, step in enumerate(action_steps):
        result.extend(before_map.get(i, []))
        result.append(step)
        result.extend(after_map.get(i, []))
    result.extend(trailing)
    return result


def _build_steps_text_for_assert(steps: list) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            continue
        params = json.dumps(s.get("params") or {}, ensure_ascii=False)
        lines.append(f"{i}. [{s.get('method')}] {s.get('desc', '')} | params: {params}")
    return "\n".join(lines)


async def generate_assertion_steps(
    *,
    trimmed_steps: list,
    description: str,
    page_context: str,
    raw_actions: list,
    config,
    step_module: str = "ui",
) -> tuple[list, int, Optional[str]]:
    """第二阶段：基于描述 + 页面快照生成断言步骤（仅追加，不改已有操作）。返回 (断言列表, tokens, 跳过原因)。"""
    from app.modules.ai.ai_prompts import PromptManager
    from app.core.llm.llm_client import LLMClientFactory
    from app.core.platform.encryption import decrypt_value
    from app.routers.ai.generate import _normalize_ui_steps

    module = (step_module or "ui").strip().lower()
    assertion_methods = _APP_ASSERTION_METHODS if module == "app" else _ASSERTION_METHODS
    prompt_code = "app_record_append_assertions" if module == "app" else "ui_record_append_assertions"

    expectations = extract_expectations(description)
    should_gen, skip_reason = should_generate_assertions(description)
    if not should_gen:
        logger.info("[recorder.assert] 跳过断言生成: %s", skip_reason)
        return [], 0, skip_reason

    max_assertions = compute_assertion_budget(description)
    expectations_text = format_expectations_for_assert_prompt(expectations, description)
    steps_text = _build_steps_text_for_assert(trimmed_steps)
    try:
        system_prompt, user_prompt = await PromptManager.render(
            code=prompt_code,
            context={
                "description": description or ("App 自动化测试" if module == "app" else "录制页面操作"),
                "expectations_text": expectations_text,
                "steps_text": steps_text,
                "steps_count": len(trimmed_steps),
                "page_context": page_context or "（未启用页面文本快照）",
                "has_page_context": bool(page_context) and module == "ui",
                "max_assertions": max_assertions,
            },
        )
    except Exception as e:
        logger.warning("[recorder.assert] Prompt 渲染失败: %s", e)
        return [], 0, "prompt_render_failed"

    api_key = decrypt_value(config.api_key)
    client = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=config.timeout,
    )
    extra_body = {}
    if config.thinking_enabled:
        extra_body["thinking"] = {"type": "enabled"}
    kwargs = {}
    if config.thinking_enabled and config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort

    try:
        result = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
            extra_body=extra_body or None,
            **kwargs,
        )
    except Exception as e:
        logger.warning("[recorder.assert] LLM 调用失败: %s", e)
        return [], 0, "llm_call_failed"

    content = result.get("content", "")
    tokens_used = int(result.get("tokens") or 0)
    json_str = _extract_json_from_text(content)
    if not json_str:
        logger.warning("[recorder.assert] 未解析到 JSON")
        return [], tokens_used, "no_json_in_response"

    try:
        data = json.loads(json_str)
        raw_assertions = data.get("assertions") or data.get("steps") or []
        if not isinstance(raw_assertions, list):
            return [], tokens_used, "invalid_assertions_payload"

        candidates = []
        for s in raw_assertions:
            if not isinstance(s, dict):
                continue
            method = s.get("method", "")
            if method not in assertion_methods:
                logger.warning("[recorder.assert] 跳过不支持的断言 method: %s", method)
                continue
            if not s.get("desc"):
                s["desc"] = s.get("keyword") or method
            candidates.append(s)

        if not candidates:
            return [], tokens_used, "empty_assertions"

        before_cap = len(candidates)
        if module == "app":
            refined = candidates[:max_assertions]
        else:
            refined = refine_assertion_candidates(
                candidates,
                action_steps=trimmed_steps,
                max_count=max_assertions,
            )
        candidates = refined
        if before_cap != len(candidates):
            logger.info(
                "[recorder.assert] 断言精炼 %s → %s（上限 %s）",
                before_cap,
                len(candidates),
                max_assertions,
            )

        placement_hints = []
        for s in candidates:
            placement = str(s.get("placement") or "before").lower()
            if placement not in ("before", "after"):
                placement = "before"
            placement_hints.append({
                "placement": placement,
                "anchor_step": s.get("anchor_step"),
            })

        if module == "app":
            from app.modules.ai.functional_case_to_app import normalize_app_steps

            valid, errors = normalize_app_steps(candidates)
        else:
            valid, errors = _normalize_ui_steps(candidates)
        if errors:
            logger.warning("[recorder.assert] 断言校验提示: %s", errors[:5])
        _patch_assertion_meta(valid, raw_actions)

        for i, s in enumerate(valid):
            s.setdefault("meta", {})
            if isinstance(s["meta"], dict):
                s["meta"]["ai_inferred_assertion"] = True
                if i < len(placement_hints):
                    hint = placement_hints[i]
                    s["meta"]["assertion_placement"] = hint["placement"]
                    if hint["anchor_step"] is not None:
                        s["meta"]["anchor_step"] = hint["anchor_step"]

        logger.info("[recorder.assert] 生成断言 %s 条", len(valid))
        return valid, tokens_used, None
    except Exception as e:
        logger.warning("[recorder.assert] JSON 解析失败: %s", e)
        return [], tokens_used, "json_parse_failed"
