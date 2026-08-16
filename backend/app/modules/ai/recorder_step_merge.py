"""录制步骤 AI 优化后的 meta/params 合并与溯源。"""
from __future__ import annotations

from typing import Any, Optional

from app.modules.ai.recorder_quality import (
    DRAG_METHODS,
    extract_desc_targets,
    _normalize_desc,
)

# 各 method 需从原始步骤恢复的 config 字段（LLM 不输出 config）
_PRESERVE_CONFIG_KEYS: tuple[str, ...] = ("pre_wait_ms", "timeout", "retry")

# 各 method 需从原始步骤恢复的 params 字段（LLM 易误改或合并时丢失）
_PRESERVE_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "open_url": ("url",),
    "fill_value": ("value", "timeout", "index", "clear"),
    "click_ele": ("index", "timeout", "button", "clickCount", "force"),
    "double_click_ele": ("index", "timeout", "button"),
    "hover": ("index", "timeout"),
    "press_key": ("key", "timeout"),
    "wait_for_time": ("timeout",),
    "select_option": ("value", "label", "index", "timeout"),
    "upload_file": ("file_path", "index", "timeout"),
    "scroll": ("direction", "distance", "timeout"),
    "mouse_click": ("x", "y", "button", "timeout"),
    "drag_and_drop": ("start_selector", "end_selector", "timeout"),
    "frame_drag_and_drop": ("start_selector", "end_selector", "timeout"),
}


def parse_source_step_ids(step: dict, *, pop: bool = False) -> list[int]:
    """解析 LLM 返回的 source_step_ids（1-based）为 0-based 下标列表。"""
    raw = step.pop("source_step_ids", None) if pop else step.get("source_step_ids")
    if raw is None:
        raw = (step.get("meta") or {}).get("source_step_ids")
    if not isinstance(raw, list):
        return []
    indices: list[int] = []
    for item in raw:
        try:
            idx = int(item) - 1
            if idx >= 0:
                indices.append(idx)
        except (TypeError, ValueError):
            continue
    return indices


def resolve_original_steps_for_optimized(
    opt: dict,
    original_steps: list[dict],
    used: Optional[set[int]] = None,
) -> list[dict]:
    """根据 source_step_ids 或单步匹配，解析优化步骤对应的原始步骤列表。"""
    if not original_steps:
        return []

    source_indices = parse_source_step_ids(opt)
    if source_indices:
        resolved: list[dict] = []
        for idx in source_indices:
            if 0 <= idx < len(original_steps):
                orig = original_steps[idx]
                if isinstance(orig, dict):
                    resolved.append(orig)
        if resolved:
            return resolved

    from app.modules.ai.recorder_quality import _find_original_for_optimized

    used_set = used if used is not None else set()
    orig, _ = _find_original_for_optimized(opt, original_steps, used_set)
    return [orig] if orig else []


def _pick_primary_original(opt: dict, originals: list[dict]) -> Optional[dict]:
    """多步合并时，选取用于 locator/params 的主原始步骤。

    优先：优化步 desc 目标文案与原始 accessibleName/desc/locator 对齐的步骤，
    避免 LLM 把 [登录, 菜单] 合错源或写错 source_step_ids 后，候选首位变成 #btn-login。
    """
    if not originals:
        return None
    if len(originals) == 1:
        return originals[0]

    method = opt.get("method") or ""
    opt_targets = [
        _normalize_desc(t) for t in extract_desc_targets(opt.get("desc") or "") if t
    ]
    opt_desc = _normalize_desc(opt.get("desc") or "")

    def _match_score(orig: dict) -> int:
        score = 0
        if orig.get("method") == method:
            score += 10
        meta = orig.get("meta") or {}
        label = _normalize_desc(
            (meta.get("accessibleName") or meta.get("text") or "").strip()
        )
        orig_desc = _normalize_desc(orig.get("desc") or "")
        loc = str((orig.get("params") or {}).get("locator") or "")
        eid = str(meta.get("id") or "").strip().lower()
        for t in opt_targets:
            if not t:
                continue
            if label and (t == label or t in label or label in t):
                score += 50
            if t in orig_desc or (orig_desc and orig_desc in t):
                score += 40
            if t and (t in loc.replace(" ", "") or t in loc):
                score += 25
            # #menu-iframe-shell ↔ 多iframe壳：id 片段弱匹配
            compact = t.replace(" ", "")
            if eid and compact and (
                compact in eid.replace("-", "")
                or any(p and p in compact for p in eid.replace("_", "-").split("-") if len(p) >= 4)
            ):
                score += 15
        if opt_desc and orig_desc and (
            opt_desc == orig_desc or opt_desc in orig_desc or orig_desc in opt_desc
        ):
            score += 20
        return score

    scored = [( _match_score(o), i, o) for i, o in enumerate(originals)]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if scored[0][0] > 0:
        return scored[0][2]

    for orig in reversed(originals):
        if orig.get("method") == method:
            return orig

    for orig in reversed(originals):
        if method == "fill_value" and orig.get("method") in ("fill_value", "click_ele"):
            if (orig.get("params") or {}).get("value") not in (None, ""):
                return orig
        if method == "click_ele" and orig.get("method") == "click_ele":
            return orig

    return originals[-1]


def original_matches_opt_intent(opt: dict, orig: dict) -> bool:
    """原始步是否与优化步描述意图一致（用于发现错误 source_step_ids）。"""
    if not opt or not orig:
        return False
    targets = extract_desc_targets(opt.get("desc") or "")
    if not targets:
        # 无引号目标时，仅比较 method + 规范化 desc
        opt_desc = _normalize_desc(opt.get("desc") or "")
        orig_desc = _normalize_desc(orig.get("desc") or "")
        if not opt_desc:
            return True
        return bool(orig_desc) and (
            opt_desc == orig_desc or opt_desc in orig_desc or orig_desc in opt_desc
        )
    meta = orig.get("meta") or {}
    label = _normalize_desc(
        (meta.get("accessibleName") or meta.get("text") or "").strip()
    )
    orig_desc = _normalize_desc(orig.get("desc") or "")
    loc = str((orig.get("params") or {}).get("locator") or "")
    for t in targets:
        nt = _normalize_desc(t)
        if not nt:
            continue
        if label and (nt == label or nt in label or label in nt):
            return True
        if nt in orig_desc or (orig_desc and orig_desc in nt):
            return True
        if nt in loc or nt in loc.replace(" ", ""):
            return True
    return False


def rebind_originals_to_opt_intent(
    opt: dict,
    originals: list[dict],
    all_original_steps: list[dict],
) -> list[dict]:
    """若溯源原始步与优化 desc 意图不符，按描述在全量原始步中重绑。"""
    if not originals:
        return originals
    primary = _pick_primary_original(opt, originals)
    if primary and original_matches_opt_intent(opt, primary):
        # 仍可能混入无关 click；只保留意图匹配的
        matched = [o for o in originals if original_matches_opt_intent(opt, o)]
        return matched or [primary]
    # source_step_ids 整体错绑：忽略溯源与污染 locator，按 desc 重找
    from app.modules.ai.recorder_quality import _find_original_for_optimized

    probe = dict(opt)
    probe.pop("source_step_ids", None)
    meta = dict(probe.get("meta") or {})
    meta.pop("source_step_ids", None)
    probe["meta"] = meta
    # 勿用错绑的 locator 去精确匹配原始步（否则永远命中登录 #btn-login）
    params = dict(probe.get("params") or {})
    params.pop("locator", None)
    probe["params"] = params
    found, _ = _find_original_for_optimized(probe, all_original_steps, set())
    if found:
        return [found]
    return originals


def merge_meta_from_originals(opt: dict, originals: list[dict]) -> bool:
    """合并一个或多个原始步骤的 meta（含 candidates）到优化步骤。

    candidates 以主原始步（意图匹配）为先，再追加其余，避免盲信错误首位。
    """
    if not originals:
        return False

    primary = _pick_primary_original(opt, originals)
    ordered: list[dict] = []
    if primary is not None:
        ordered.append(primary)
    for orig in originals:
        if orig is not primary:
            ordered.append(orig)

    merged: dict[str, Any] = dict(opt.get("meta") or {})
    for orig in ordered:
        om = orig.get("meta") or {}
        if not om:
            continue
        # candidates 合并去重（主步在前）
        existing = list(merged.get("candidates") or [])
        for c in om.get("candidates") or []:
            if c and c not in existing:
                existing.append(c)
        if existing:
            merged["candidates"] = existing
        for key, val in om.items():
            if key == "candidates":
                continue
            # 主步字段优先覆盖空值；非主步不覆盖已有非空
            if orig is primary:
                if key not in merged or merged[key] in (None, "", [], {}):
                    merged[key] = val
                elif key in ("id", "accessibleName", "text", "cssPath", "frameUrl") and val not in (
                    None,
                    "",
                    [],
                    {},
                ):
                    merged[key] = val
            elif key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = val

    source_ids = parse_source_step_ids(opt)
    if source_ids:
        merged["source_step_ids"] = [i + 1 for i in source_ids]

    opt["meta"] = merged
    return True

def merge_params_from_originals(opt: dict, originals: list[dict]) -> int:
    """从原始步骤恢复关键 params，返回恢复字段数。"""
    if not originals:
        return 0

    method = opt.get("method") or ""
    opt_params = opt.setdefault("params", {})
    if not isinstance(opt_params, dict):
        opt_params = {}
        opt["params"] = opt_params

    primary = _pick_primary_original(opt, originals)
    restored = 0

    def _restore_from(orig: dict) -> None:
        nonlocal restored
        orig_params = orig.get("params") or {}
        keys = _PRESERVE_PARAM_KEYS.get(method, ())
        for key in keys:
            if key not in orig_params:
                continue
            orig_val = orig_params[key]
            if orig_val in (None, ""):
                continue
            if opt_params.get(key) != orig_val:
                opt_params[key] = orig_val
                restored += 1

    if primary:
        _restore_from(primary)

    # 合并 fill：value 优先取自 fill_value 原始步
    if method == "fill_value":
        for orig in originals:
            if orig.get("method") != "fill_value":
                continue
            val = (orig.get("params") or {}).get("value")
            if val not in (None, "") and opt_params.get("value") != val:
                opt_params["value"] = val
                restored += 1
                break

    # locator：意图匹配的主原始步优先；防止错绑 source 后留下别步的 #btn-login
    if method not in ("open_url", *DRAG_METHODS) and primary and original_matches_opt_intent(
        opt, primary
    ):
        primary_loc = str((primary.get("params") or {}).get("locator") or "").strip()
        if primary_loc:
            cur = str(opt_params.get("locator") or "").strip()
            primary_cands = [
                str(c).strip()
                for c in ((primary.get("meta") or {}).get("candidates") or [])
                if str(c).strip()
            ]
            if not cur or (cur != primary_loc and cur not in primary_cands):
                opt_params["locator"] = primary_loc
                restored += 1
    elif method not in ("open_url", *DRAG_METHODS):
        orig_locs = [
            (o.get("params") or {}).get("locator", "")
            for o in originals
            if (o.get("params") or {}).get("locator")
        ]
        if orig_locs and not opt_params.get("locator"):
            opt_params["locator"] = orig_locs[-1]
            restored += 1

    return restored


def merge_config_from_originals(opt: dict, originals: list[dict]) -> int:
    """从原始步骤恢复 config（如 pre_wait_ms），返回恢复字段数。"""
    if not originals:
        return 0

    primary = _pick_primary_original(opt, originals) or originals[-1]
    orig_config = primary.get("config") if isinstance(primary.get("config"), dict) else {}
    opt_config = opt.setdefault("config", {})
    if not isinstance(opt_config, dict):
        opt_config = {}
        opt["config"] = opt_config

    restored = 0
    for key in _PRESERVE_CONFIG_KEYS:
        val = orig_config.get(key)
        if val is None and key == "pre_wait_ms" and "pre_wait_ms" in primary:
            val = primary.get("pre_wait_ms")
        if val is None:
            continue
        if key not in opt_config:
            opt_config[key] = val
            restored += 1
    return restored


def _meta_is_rich(meta: dict) -> bool:
    """meta 是否已含定位候选或捕获文案，无需再模糊匹配。"""
    if not meta:
        return False
    return bool(
        meta.get("candidates")
        or meta.get("text")
        or meta.get("accessibleName")
        or meta.get("id")
        or meta.get("dataTestid")
    )


def patch_meta_from_original_steps(optimized_steps: list, original_steps: list) -> dict[str, int]:
    """从原始步骤补回 meta；优先 source_step_ids，再回退 locator/desc 匹配。"""
    stats = {"meta_patched": 0, "params_restored": 0, "config_restored": 0, "source_traced": 0}
    if not optimized_steps or not original_steps:
        return stats

    locator_meta_map: dict[tuple, dict] = {}
    desc_meta_map: dict[tuple, dict] = {}
    label_meta_map: dict[tuple, dict] = {}

    index_meta_map: dict[int, dict] = {}
    for i, orig in enumerate(original_steps):
        if not isinstance(orig, dict):
            continue
        meta = orig.get("meta") or {}
        if meta:
            index_meta_map[i] = meta
            rec_idx = meta.get("rec_step_index")
            if rec_idx is not None:
                try:
                    index_meta_map[int(rec_idx) - 1] = meta
                except (TypeError, ValueError):
                    pass

    for orig in original_steps:
        if not isinstance(orig, dict):
            continue
        meta = orig.get("meta", {})
        if not meta:
            continue
        method = orig.get("method", "")
        params = orig.get("params", {})
        if method == "open_url":
            locator_meta_map[(method, params.get("url", ""))] = meta
        else:
            locator_meta_map[(method, params.get("locator", ""))] = meta
        desc_meta_map[(method, _normalize_desc(orig.get("desc", "")))] = meta
        acc = (meta.get("accessibleName") or meta.get("text") or "").strip()
        if acc:
            label_meta_map[(method, _normalize_desc(acc))] = meta
        for target in extract_desc_targets(orig.get("desc", "")):
            label_meta_map[(method, _normalize_desc(target))] = meta

    for opt in optimized_steps:
        if not isinstance(opt, dict):
            continue

        source_indices = parse_source_step_ids(opt)
        if source_indices:
            originals = [
                original_steps[i]
                for i in source_indices
                if 0 <= i < len(original_steps) and isinstance(original_steps[i], dict)
            ]
            if originals:
                originals = rebind_originals_to_opt_intent(
                    opt, originals, original_steps
                )
                if merge_meta_from_originals(opt, originals):
                    stats["meta_patched"] += 1
                stats["params_restored"] += merge_params_from_originals(opt, originals)
                stats["config_restored"] += merge_config_from_originals(opt, originals)
                stats["source_traced"] += 1
                parse_source_step_ids(opt, pop=True)
                continue

        meta = opt.get("meta") or {}
        if _meta_is_rich(meta):
            originals = resolve_original_steps_for_optimized(opt, original_steps)
            stats["params_restored"] += merge_params_from_originals(opt, originals)
            stats["config_restored"] += merge_config_from_originals(opt, originals)
            continue

        # 尝试 rec_step_index 精确匹配
        rec_idx = meta.get("rec_step_index") or meta.get("source_step_ids")
        if isinstance(rec_idx, list) and rec_idx:
            try:
                rec_idx = int(rec_idx[0])
            except (TypeError, ValueError):
                rec_idx = None
        if rec_idx is not None:
            try:
                idx = int(rec_idx) - 1
                if 0 <= idx < len(original_steps):
                    orig_meta = index_meta_map.get(idx) or (original_steps[idx].get("meta") or {})
                    if orig_meta:
                        merge_meta_from_originals(opt, [original_steps[idx]])
                        stats["meta_patched"] += 1
                        stats["params_restored"] += merge_params_from_originals(opt, [original_steps[idx]])
                        stats["config_restored"] += merge_config_from_originals(opt, [original_steps[idx]])
                        continue
            except (TypeError, ValueError):
                pass

        method = opt.get("method", "")
        params = opt.get("params", {})
        if method == "open_url":
            key = (method, params.get("url", ""))
        else:
            key = (method, params.get("locator", ""))

        meta = locator_meta_map.get(key)
        if not meta:
            meta = desc_meta_map.get((method, _normalize_desc(opt.get("desc", ""))))
        if not meta:
            for target in extract_desc_targets(opt.get("desc", "")):
                meta = label_meta_map.get((method, _normalize_desc(target)))
                if meta:
                    break
        if meta:
            opt["meta"] = dict(meta)
            stats["meta_patched"] += 1
        originals = resolve_original_steps_for_optimized(opt, original_steps)
        stats["params_restored"] += merge_params_from_originals(opt, originals)
        stats["config_restored"] += merge_config_from_originals(opt, originals)

    return stats
