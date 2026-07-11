"""
录制步骤质量评估与 AI 优化后 locator 保护
"""
from __future__ import annotations

import re
from typing import Any, Optional

# 与录制引擎 / 前端 LocatorSelector 保持一致
COMMON_SHORT_TEXTS = frozenset({
    "登入", "登录", "确定", "取消", "提交", "保存", "新增", "删除", "编辑",
    "搜索", "查询", "重置", "下一步", "上一步", "完成", "关闭", "返回",
    "更多", "展开", "收起", "详情", "操作", "管理", "设置", "首页", "退出",
    "导入", "导出", "下载", "上传", "预览", "复制", "粘贴", "全选", "清空",
})


def _unsafe_css_has_text(text: str) -> bool:
    return bool(re.search(r"[\$\\]", text or ""))


LOCATOR_METHODS = frozenset({
    "click_ele", "double_click_ele", "hover", "fill_value", "press_key",
    "select_option", "upload_file", "assert_ele", "mouse_click",
})

DRAG_METHODS = frozenset({"drag_and_drop", "frame_drag_and_drop"})

GENERIC_CLASS_HINTS = (
    "show-name", "text-link", "btn", "button", "link", "item", "cell",
    "anticon", "icon", "wrapper", "content", "td-content", "base-name",
    "ant-table", "el-table", "nz-table", "table-operate", "operate",
)

_DYNAMIC_ID_RE = re.compile(
    r"^(ng-|_ngcontent-|ember\d+|jsx-|css-|radix-|:r\d+|\d+$)",
    re.I,
)

INDEX_ELIGIBLE_METHODS = frozenset({
    "click_ele", "double_click_ele", "hover", "fill_value", "select_option",
    "upload_file", "assert_ele", "assert_text", "assert_visible", "assert_hidden",
    "assert_value", "extract_text", "extract_attribute", "wait_for_element",
    "press_key", "mouse_click",
})


def is_dynamic_element_id(elem_id: str) -> bool:
    """Angular/React 等运行时生成的 id 不宜作为默认定位。"""
    eid = (elem_id or "").strip()
    if not eid or len(eid) < 2:
        return True
    if _DYNAMIC_ID_RE.search(eid):
        return True
    digits = sum(ch.isdigit() for ch in eid)
    if len(eid) >= 6 and digits / len(eid) > 0.45:
        return True
    return False


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        c = (c or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _build_candidates_from_meta(meta: dict) -> list[str]:
    """与前端 LocatorSelector 对齐，从 meta 推导备选定位。"""
    opts: list[str] = []
    tag = (meta.get("tag") or "").lower()
    text = (meta.get("accessibleName") or meta.get("text") or "").strip()
    region = (meta.get("region") or "").strip()
    popup_root = (meta.get("popupRoot") or "").strip()
    match_index = int(meta.get("matchIndex") or 0)
    elem_id = (meta.get("id") or "").strip()
    name = (meta.get("name") or "").strip()
    cls = (meta.get("class") or "").strip()
    aria = (meta.get("ariaLabel") or "").strip()
    placeholder = (meta.get("placeholder") or "").strip()
    data_testid = (meta.get("dataTestid") or "").strip()
    role = (meta.get("role") or "").strip()
    title = (meta.get("title") or "").strip()
    is_common = text in COMMON_SHORT_TEXTS
    row_ctx = (meta.get("rowContext") or "").strip()
    input_type = (meta.get("inputType") or "").strip().lower()

    if data_testid:
        opts.append(f'[data-testid="{data_testid}"]')
    if elem_id and not is_dynamic_element_id(elem_id):
        opts.append(f"#{elem_id}")
    if role and text and len(text) < 30 and not text.isdigit():
        opts.append(f"get_by_role={role}, {text}")
    if cls:
        class_list = [c for c in cls.split() if c and not c.startswith("ng-") and not c.startswith("v-") and len(c) < 30]
        if class_list:
            prefix = tag or "*"
            opts.append(f"{prefix}.{class_list[0]}")
    if name:
        prefix = tag or "*"
        opts.append(f'{prefix}[name="{name}"]')
    if aria:
        prefix = tag or "*"
        opts.append(f'{prefix}[aria-label="{aria}"]')
    if placeholder and tag in ("input", "textarea"):
        opts.append(f'{tag}[placeholder="{placeholder}"]')
        opts.append(f"get_by_placeholder={placeholder}")
    if title:
        prefix = tag or "*"
        opts.append(f'{prefix}[title="{title}"]')
    if text and len(text) < 30 and not text.isdigit():
        opts.append(f"get_by_text={text}")
    if popup_root and text and len(text) < 40:
        opts.append(f"{popup_root} >> get_by_text={text}")
        if role:
            opts.append(f"{popup_root} >> get_by_role={role}, {text}")
    if tag and text:
        class_part = f"[@class='{cls.split()[0]}']" if cls else ""
        opts.append(f'//{tag}{class_part}[contains(.,"{text}")]')
    if region and text:
        opts.append(f"{region} >> get_by_text={text}")
        if role:
            opts.append(f"{region} >> get_by_role={role}, {text}")
        if not _unsafe_css_has_text(text):
            opts.append(f'{region} {tag}:has-text("{text}")')
    if is_common and text:
        inferred = role or ("button" if tag in ("button", "a") else "")
        if inferred and f"get_by_role={inferred}, {text}" not in opts:
            opts.append(f"get_by_role={inferred}, {text}")
    if match_index > 1 and text:
        opts.append(f"get_by_text={text}")
    if row_ctx and len(row_ctx) >= 2:
        row_key = row_ctx[:48].replace("'", "")
        if input_type == "checkbox" or role == "checkbox":
            opts.insert(0, f'//tr[contains(.,"{row_key}")]//input[@type="checkbox"]')
            opts.insert(0, f'//tr[contains(.,"{row_key}")]//span[contains(@class,"checkbox")]')
        if text and len(text) < 40:
            opts.insert(0, f'//tr[contains(.,"{row_key}")]//*[contains(.,"{text[:32]}")]')
    return _dedupe_candidates(opts)


def collect_step_locator_candidates(step: dict) -> list[str]:
    """合并 meta.candidates 与 meta 推导项，供智能选 locator。"""
    meta = step.get("meta") or {}
    merged = list(meta.get("candidates") or [])
    merged.extend(_build_candidates_from_meta(meta))
    current = (step.get("params") or {}).get("locator") or ""
    if current:
        merged.append(current)
    return _dedupe_candidates(merged)


def _score_locator(candidate: str, step: dict, ai_suggested: Optional[str] = None) -> float:
    """为候选定位打分，越高越适合作为默认 locator。"""
    meta = step.get("meta") or {}
    accessible = (meta.get("accessibleName") or meta.get("text") or "").strip()
    desc = step.get("desc") or ""
    desc_targets = extract_desc_targets(desc)
    score = 0.0

    if candidate.startswith("[data-testid="):
        score += 100
    elif candidate.startswith("#"):
        elem_id = candidate[1:].split()[0]
        score += 25 if is_dynamic_element_id(elem_id) else 92

    if candidate.startswith("get_by_placeholder="):
        score += 78
    if "[title=" in candidate or candidate.startswith("get_by_label="):
        score += 70
    if candidate.startswith("//tr[contains"):
        score += 80
    if candidate.startswith("//") and "contains(text()," in candidate:
        score -= 55
    if re.match(r"^[a-z]+\.[a-zA-Z0-9_-]+$", candidate):
        score += 58

    if desc_targets:
        primary = desc_targets[0]
        if primary in candidate:
            score += 85
        elif accessible and (_locator_mentions_text(candidate, accessible) or accessible in candidate):
            score += 35
        for word in COMMON_SHORT_TEXTS:
            if word != primary and word in candidate and primary not in candidate:
                score -= 50

    popup_root = (meta.get("popupRoot") or "").strip()
    if popup_root and len(popup_root) > 2:
        if candidate.startswith(f"{popup_root} >>"):
            score += 85
        elif popup_root.startswith(("get_by_", "#", "[")) or "." in popup_root:
            if candidate.startswith("get_by_text=") and " >> " not in candidate:
                score -= 35

    ambiguous = accessible in COMMON_SHORT_TEXTS or any(t in COMMON_SHORT_TEXTS for t in desc_targets)
    if ambiguous:
        if " >> " in candidate:
            score += 75
        if candidate.startswith("get_by_text=") and " >> " not in candidate:
            score -= 25

    cand_lower = candidate.lower()
    if any(h in cand_lower for h in GENERIC_CLASS_HINTS):
        score -= 35

    if candidate.startswith("get_by_role=") and accessible and accessible not in COMMON_SHORT_TEXTS:
        score += 55
    if candidate.startswith("get_by_text=") and " >> " not in candidate and not ambiguous:
        score += 50

    match_index = int(meta.get("matchIndex") or 0)
    if match_index > 1:
        if " >> " in candidate or candidate.startswith("//tr[contains"):
            score += 40
        if candidate.startswith("get_by_text=") and " >> " not in candidate:
            score -= 45

    if ai_suggested and candidate == ai_suggested:
        score += 12

    return score


def pick_best_locator(
    step: dict,
    ai_locator: Optional[str] = None,
    original_locator: Optional[str] = None,
) -> tuple[str, str, dict[str, Any]]:
    """
    从候选池智能选择默认 locator。
    返回 (locator, source, meta_updates)，source: ai | rule | unchanged
    """
    allowed = collect_step_locator_candidates(step)
    if original_locator:
        allowed = _dedupe_candidates(allowed + [original_locator])

    current = (step.get("params") or {}).get("locator") or original_locator or ""
    if not allowed:
        return current, "unchanged", {}

    if ai_locator and ai_locator in allowed:
        rule_best = max(allowed, key=lambda c: _score_locator(c, step))
        ai_score = _score_locator(ai_locator, step, ai_suggested=ai_locator)
        rule_score = _score_locator(rule_best, step)
        if ai_score > rule_score:
            if ai_locator == current:
                return ai_locator, "unchanged", {}
            updates: dict[str, Any] = {"locator_pick_source": "ai", "locator_ai_chosen": ai_locator}
            if original_locator and original_locator != ai_locator:
                updates["locator_original"] = original_locator
            return ai_locator, "ai", updates

    best = max(allowed, key=lambda c: _score_locator(c, step, ai_suggested=ai_locator if ai_locator in allowed else None))
    if best == current:
        return best, "unchanged", {}

    updates: dict[str, Any] = {"locator_pick_source": "rule", "locator_rule_chosen": best}
    if ai_locator and ai_locator != best:
        updates["locator_ai_suggested"] = ai_locator
    if original_locator and original_locator != best:
        updates["locator_original"] = original_locator
    return best, "rule", updates


def should_repick_locator(step: dict) -> bool:
    """录制器已给出稳定链式/语义定位时，转换阶段不再用候选池覆盖。"""
    locator = ((step.get("params") or {}).get("locator") or "").strip()
    if not locator:
        return False
    if " >> " in locator or "||" in locator:
        return False
    if locator.startswith("//tr[contains"):
        return False
    meta = step.get("meta") or {}
    if meta.get("locatorRunnerFinal"):
        return False
    popup = (meta.get("popupRoot") or "").strip()
    region = (meta.get("region") or "").strip()
    text = (meta.get("accessibleName") or meta.get("text") or "").strip()
    if popup and text and locator == f"{popup} >> get_by_text={text}":
        return False
    if region and locator.startswith(f"{region} >>"):
        return False
    if meta.get("dataTestid"):
        dt = meta["dataTestid"]
        if f'data-testid="{dt}"' in locator:
            return False
    elem_id = (meta.get("id") or "").strip()
    if elem_id and not is_dynamic_element_id(elem_id) and locator == f"#{elem_id}":
        return False
    if locator.startswith("get_by_placeholder="):
        return False
    return True


def _normalize_desc(desc: str) -> str:
    text = (desc or "").strip()
    text = re.sub(r"['\"「」]", "", text)
    return re.sub(r"\s+", "", text)


def extract_desc_targets(desc: str) -> list[str]:
    """从步骤描述提取引号内或动作后的目标文案。"""
    desc = (desc or "").strip()
    targets: list[str] = []
    for pattern in (
        r"点击['「]([^'」]+)['」]",
        r"悬停到['「]([^'」]+)['」]",
        r"双击['「]([^'」]+)['」]",
        r"点击\s+(.+?)(?:\s*按钮|\s*链接|$)",
        r"点击\s*(\S+)",
    ):
        for m in re.finditer(pattern, desc):
            t = m.group(1).strip()
            if t and t not in targets:
                targets.append(t)
    return targets


def _locator_mentions_text(locator: str, text: str) -> bool:
    if not locator or not text:
        return False
    return text in locator


def assess_step_quality(step: dict) -> dict[str, Any]:
    """
    评估单步录制/转换质量，写入 meta.quality。
    level: ok | warn | risk
    """
    meta = dict(step.get("meta") or {})
    method = step.get("method") or ""
    params = step.get("params") or {}
    desc = step.get("desc") or ""
    locator = params.get("locator") or ""
    reasons: list[str] = []

    accessible = (meta.get("accessibleName") or meta.get("text") or "").strip()
    match_index = int(meta.get("matchIndex") or 0)

    if method in ("click_ele", "double_click_ele", "hover", "fill_value"):
        all_candidates = collect_step_locator_candidates(step)
        if all_candidates:
            meta["candidates"] = all_candidates
        if not meta.get("dataTestid") and len(all_candidates) <= 2:
            reasons.append("无 data-testid 且候选较少，建议前端为关键按钮添加 data-testid")
        if not locator:
            reasons.append("缺少定位表达式")
        if len(all_candidates) <= 1:
            reasons.append("候选定位仅 1 种，建议手动核对或重录")
        cls = (meta.get("class") or "").lower()
        if cls and any(h in cls for h in GENERIC_CLASS_HINTS):
            reasons.append(f"使用了较通用的 class（{meta.get('class', '')[:40]}）")
        if accessible and accessible in COMMON_SHORT_TEXTS:
            has_context = " >> " in locator or "get_by_text=" in locator or "get_by_role=" in locator
            if not has_context and not meta.get("region"):
                reasons.append(f"常见短词「{accessible}」且未使用区域上下文定位")
        if match_index > 1 and int(params.get("index") or 1) == 1:
            reasons.append(f"页面上存在多个「{accessible or '相似元素'}」，建议设置 params.index={match_index}")

        desc_targets = extract_desc_targets(desc)
        if desc_targets:
            primary = desc_targets[0]
            if accessible and primary not in accessible and accessible not in primary:
                if not _locator_mentions_text(locator, primary):
                    reasons.append(f"描述为「{primary}」，但捕获元素文案为「{accessible}」")

    level = "ok"
    if reasons:
        level = "risk" if any("描述为" in r or "缺少定位" in r for r in reasons) else "warn"

    meta["quality"] = {
        "level": level,
        "reasons": reasons,
        "accessibleName": accessible,
        "region": meta.get("region") or "",
    }
    step["meta"] = meta
    return step


def apply_index_from_meta(step: dict) -> dict:
    """matchIndex>1 且未显式设置 index 时，写入默认 index。"""
    meta = step.get("meta") or {}
    match_index = int(meta.get("matchIndex") or 0)
    if match_index <= 1:
        return step
    params = step.setdefault("params", {})
    if step.get("method") in INDEX_ELIGIBLE_METHODS and int(params.get("index") or 1) == 1:
        params["index"] = match_index
    return step


def _step_locator_key(step: dict) -> tuple:
    method = step.get("method") or ""
    params = step.get("params") or {}
    if method == "open_url":
        return method, params.get("url") or ""
    if method in DRAG_METHODS:
        return (
            method,
            params.get("start_selector") or "",
            params.get("end_selector") or "",
        )
    return method, params.get("locator") or ""


def _meta_label(step: dict) -> str:
    """步骤用于匹配 meta 的语义标签（捕获文案或描述目标）。"""
    meta = step.get("meta") or {}
    text = (meta.get("accessibleName") or meta.get("text") or "").strip()
    if text:
        return _normalize_desc(text)
    targets = extract_desc_targets(step.get("desc") or "")
    return _normalize_desc(targets[0]) if targets else ""


def _find_original_for_optimized(
    opt: dict,
    original_steps: list[dict],
    used: set[int],
) -> tuple[Optional[dict], Optional[int]]:
    """为优化步骤找到最匹配的原始步骤及其下标。"""
    from app.modules.ai.recorder_step_merge import parse_source_step_ids

    source_indices = parse_source_step_ids(opt)
    if source_indices:
        for idx in source_indices:
            if 0 <= idx < len(original_steps) and idx not in used:
                return original_steps[idx], idx
        # 均已占用时仍取首个溯源步，便于合并场景合并 meta
        idx = source_indices[0]
        if 0 <= idx < len(original_steps):
            return original_steps[idx], idx

    opt_method = opt.get("method") or ""
    opt_desc = _normalize_desc(opt.get("desc") or "")
    opt_key = _step_locator_key(opt)

    for i, orig in enumerate(original_steps):
        if i in used:
            continue
        if _step_locator_key(orig) == opt_key:
            return orig, i

    for i, orig in enumerate(original_steps):
        if i in used:
            continue
        if orig.get("method") != opt_method:
            continue
        if _normalize_desc(orig.get("desc") or "") == opt_desc:
            return orig, i

    opt_targets = extract_desc_targets(opt.get("desc") or "")
    if opt_targets:
        for i, orig in enumerate(original_steps):
            if i in used:
                continue
            if orig.get("method") != opt_method:
                continue
            orig_loc = ((orig.get("params") or {}).get("locator") or "").strip()
            orig_acc = _meta_label(orig) or _normalize_desc(
                (orig.get("meta") or {}).get("accessibleName") or (orig.get("meta") or {}).get("text") or ""
            )
            for target in opt_targets:
                norm_target = _normalize_desc(target)
                if target in orig_loc or _locator_mentions_text(orig_loc, target):
                    return orig, i
                if orig_acc and (norm_target == orig_acc or norm_target in orig_acc or orig_acc in norm_target):
                    return orig, i

    opt_label = _meta_label(opt) or opt_desc
    if opt_label:
        for i, orig in enumerate(original_steps):
            if i in used:
                continue
            if orig.get("method") != opt_method:
                continue
            orig_label = _meta_label(orig) or _normalize_desc(orig.get("desc") or "")
            if not orig_label:
                continue
            if opt_label == orig_label or opt_label in orig_label or orig_label in opt_label:
                return orig, i

    return None, None


def resolve_locators_after_optimize(optimized_steps: list, original_steps: list) -> dict[str, int]:
    """
    AI 优化后：合并 meta，并从候选池智能选择 params.locator（允许 AI 在候选内重选）。
    open_url 的 url 仍强制与原始一致。
    """
    stats = {"ai_picked": 0, "rule_picked": 0, "unchanged": 0, "url_restored": 0}
    if not optimized_steps or not original_steps:
        return stats

    used: set[int] = set()

    for opt in optimized_steps:
        if not isinstance(opt, dict):
            continue

        from app.modules.ai.recorder_step_merge import (
            merge_meta_from_originals,
            merge_params_from_originals,
            parse_source_step_ids,
            resolve_original_steps_for_optimized,
        )

        source_indices = parse_source_step_ids(opt)
        orig: Optional[dict] = None
        if source_indices:
            originals = [
                original_steps[i]
                for i in source_indices
                if 0 <= i < len(original_steps) and isinstance(original_steps[i], dict)
            ]
            if originals:
                merge_meta_from_originals(opt, originals)
                merge_params_from_originals(opt, originals)
                from app.modules.ai.recorder_step_merge import _pick_primary_original
                orig = _pick_primary_original(opt, originals)
                orig_idx = source_indices[0] if source_indices[0] not in used else None
                if orig_idx is not None:
                    used.add(orig_idx)
            else:
                orig, orig_idx = _find_original_for_optimized(opt, original_steps, used)
                if orig and orig_idx is not None:
                    used.add(orig_idx)
        else:
            orig, orig_idx = _find_original_for_optimized(opt, original_steps, used)
            if orig and orig_idx is not None:
                used.add(orig_idx)

        if orig:
            merged_meta = dict(orig.get("meta") or {})
            merged_meta.update(opt.get("meta") or {})
            opt["meta"] = merged_meta

        opt_params = opt.setdefault("params", {})
        orig_params = (orig.get("params") or {}) if orig else {}
        method = opt.get("method") or ""

        if method == "open_url":
            orig_url = orig_params.get("url", "")
            if orig_url and opt_params.get("url") != orig_url:
                opt_params["url"] = orig_url
                stats["url_restored"] += 1
            continue

        if method in DRAG_METHODS:
            restored = False
            for key in ("start_selector", "end_selector"):
                orig_val = orig_params.get(key, "")
                if orig_val and opt_params.get(key) != orig_val:
                    opt_params[key] = orig_val
                    restored = True
            if restored:
                stats["unchanged"] += 1
            continue

        if method not in LOCATOR_METHODS:
            continue

        ai_loc = opt_params.get("locator")
        orig_loc = orig_params.get("locator", "")

        lock_step = {"params": orig_params, "meta": opt.get("meta") or {}} if orig else None
        if lock_step and not should_repick_locator(lock_step):
            if orig_loc:
                opt_params["locator"] = orig_loc
                if ai_loc and ai_loc != orig_loc:
                    opt.setdefault("meta", {})["locator_ai_rejected"] = ai_loc
            stats["unchanged"] += 1
            continue

        best, source, meta_updates = pick_best_locator(opt, ai_locator=ai_loc, original_locator=orig_loc)
        if best:
            opt_params["locator"] = best
        if meta_updates:
            opt.setdefault("meta", {}).update(meta_updates)
        if source == "ai":
            stats["ai_picked"] += 1
        elif source == "rule":
            stats["rule_picked"] += 1
        else:
            stats["unchanged"] += 1

    return stats


def restore_locators_from_original(optimized_steps: list, original_steps: list) -> int:
    """兼容旧调用：改为智能选 locator，返回变更步数。"""
    stats = resolve_locators_after_optimize(optimized_steps, original_steps)
    return stats["ai_picked"] + stats["rule_picked"]


def assess_steps(steps: list) -> list:
    """批量评估并应用 index 默认值。"""
    result = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step = apply_index_from_meta(dict(step))
        result.append(assess_step_quality(step))
    return result
