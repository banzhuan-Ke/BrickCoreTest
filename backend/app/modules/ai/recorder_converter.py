"""
录制操作转换器
将 Runner 上报的原始操作列表转换为平台标准 UI 步骤

作者：AI 协作助手
日期：2026-04-22
"""

import re
import time
from typing import List, Dict, Any

from app.modules.ai.recorder_quality import (
    apply_index_from_meta,
    assess_step_quality,
    collect_step_locator_candidates,
    pick_best_locator,
    should_repick_locator,
)
from app.core.shared.ui_keywords import METHOD_TO_KEYWORD


# 原始操作类型 → 平台 method 映射
ACTION_TO_METHOD = {
    "click": "click_ele",
    "dblclick": "double_click_ele",
    "fill": "fill_value",
    "select": "select_option",
    "navigate": "open_url",
    "wait": "wait_for_time",
    "wait_popup": "wait_for_element",
    "hover": "hover",
    "keydown": "press_key",
    "scroll": "scroll",
    "contextmenu": "mouse_click",
    "file": "upload_file",
    "drag_and_drop": "drag_and_drop",
}

# Method 默认参数
METHOD_DEFAULTS = {
    "click_ele": {"locator": "", "index": 1, "force": False, "timeout": 20000},
    "double_click_ele": {"locator": "", "index": 1, "force": False, "timeout": 20000},
    "fill_value": {"locator": "", "value": "", "timeout": 20000},
    "select_option": {"locator": "", "value": "", "timeout": 20000},
    "open_url": {"url": "", "wait_until": "load", "timeout": 30000},
    "wait_for_time": {"timeout": 2000},
    "wait_for_element": {"locator": "", "timeout": 20000},
    "hover": {"locator": "", "wait_time": 500},
    "press_key": {"key": "", "locator": "", "timeout": 20000},
    "scroll": {"x": 0, "y": 0},
    "mouse_click": {"x": 0, "y": 0, "button": "right", "locator": "", "timeout": 20000},
    "upload_file": {"locator": "", "file_path": "", "timeout": 20000},
    "drag_and_drop": {
        "start_selector": "",
        "end_selector": "",
        "source_position_x": "",
        "source_position_y": "",
        "target_position_x": "",
        "target_position_y": "",
        "timeout": 20000,
    },
}


def convert_actions_to_steps(raw_actions: List[dict]) -> List[dict]:
    """
    将原始录制操作列表转换为平台标准步骤
    
    处理逻辑：
    1. 去重：同一元素 500ms 内的连续点击合并
    2. 输入合并：连续的 focus + input 合并为 fill_value
    3. 等待插入：操作间时间差 > 2 秒时插入 wait_for_time
    4. 生成自然语言描述
    """
    if not raw_actions:
        return []

    # 第一步：按时间排序并去重
    actions = sorted(raw_actions, key=lambda a: a.get("timestamp", 0))
    deduped = _dedup_actions(actions)

    # 第二步：合并输入事件
    merged = _merge_input_actions(deduped)

    # 第三步：插入等待
    with_waits = _insert_wait_actions(merged)

    # 第三步半：首次进入弹窗时插入 wait_for_element
    with_popup_waits = _insert_popup_wait_actions(with_waits)

    # 第四步：转换为平台步骤
    steps = []
    for action in with_popup_waits:
        step = _action_to_step(action)
        if step:
            steps.append(step)

    for i, step in enumerate(steps):
        step.setdefault("meta", {})["rec_step_index"] = i + 1

    return steps


def _dedup_actions(actions: List[dict]) -> List[dict]:
    """去重：同一元素 500ms 内的连续点击合并"""
    result = []
    for action in actions:
        action_type = action.get("action_type", "")
        if action_type in ("click", "dblclick") and result:
            last = result[-1]
            if last.get("action_type") == action_type:
                last_selector = last.get("selector", "")
                curr_selector = action.get("selector", "")
                last_time = last.get("timestamp", 0)
                curr_time = action.get("timestamp", 0)
                if last_selector == curr_selector and curr_time - last_time < 500:
                    continue  # 跳过重复点击
        result.append(action)
    return result


def _merge_input_actions(actions: List[dict]) -> List[dict]:
    """合并输入事件：连续的 input 合并为单个 fill"""
    result = []
    pending_fill = None

    for action in actions:
        action_type = action.get("action_type", "")

        if action_type == "fill":
            selector = action.get("selector", "")
            value = action.get("value", "")

            if pending_fill and pending_fill.get("selector") == selector:
                # 同一输入框，更新值
                pending_fill["value"] = value
                pending_fill["timestamp"] = action.get("timestamp", 0)
            else:
                # 新的输入框，保存上一个，开始新的
                if pending_fill:
                    result.append(pending_fill)
                pending_fill = dict(action)
        else:
            # 非输入事件，先保存 pending_fill
            if pending_fill:
                result.append(pending_fill)
                pending_fill = None
            result.append(action)

    # 最后可能还有一个 pending_fill
    if pending_fill:
        result.append(pending_fill)

    return result


def _insert_wait_actions(actions: List[dict]) -> List[dict]:
    """在操作间插入等待
    
    策略：
    1. 操作间隔 > 8 秒：插入 wait_for_time（用户自然停顿，如思考/查找元素）
    2. hover 后：插入 0.5 秒等待（给悬浮菜单/按钮的显示动画留时间）
    3. navigate 后的等待已由录制引擎自动插入（1 秒），此处不再额外插入
    
    说明：自动化框架（click_ele / fill_value 等）本身依赖 Playwright 的自动等待，
    录制期间用户的自然停顿（2~6 秒）通常不需要显式 wait_for_time。
    """
    result = []
    for i, action in enumerate(actions):
        if i > 0:
            prev_action = actions[i - 1]
            prev_time = prev_action.get("timestamp", 0)
            curr_time = action.get("timestamp", 0)
            gap = curr_time - prev_time
            prev_type = prev_action.get("action_type", "")
            
            # hover 后插入 0.5 秒等待，给悬浮菜单显示动画留时间
            if prev_type == "hover":
                result.append({
                    "action_type": "wait",
                    "value": "500",
                    "timestamp": prev_time + 100,
                })
            # 操作间隔 > 8 秒，插入等待（用户自然停顿）
            elif gap > 8000:
                wait_ms = min(gap, 10000)
                result.append({
                    "action_type": "wait",
                    "value": str(wait_ms),
                    "timestamp": prev_time + 100,
                })
        result.append(action)
    return result


def _popup_root(meta: dict) -> str:
    return ((meta or {}).get("popupRoot") or "").strip()


def _popup_wait_locator(action: dict) -> str:
    """为首次进入弹窗生成 wait_for_element 定位符。"""
    meta = action.get("meta") or {}
    popup_root = _popup_root(meta)
    text = (action.get("element_text") or meta.get("text") or meta.get("accessibleName") or "").strip()
    if popup_root.startswith("get_by_role="):
        return popup_root
    if "$" in text:
        m = re.search(r"\$\d+\.?\d*", text)
        if m:
            if popup_root:
                return f"{popup_root} >> get_by_text={m.group(0)}"
            return f"get_by_text={m.group(0)}"
    if popup_root and text:
        return popup_root
    if popup_root:
        return popup_root
    return "get_by_role=dialog"


def _insert_popup_wait_actions(actions: List[dict]) -> List[dict]:
    """检测到首次进入弹窗层时，自动插入 wait_for_element。"""
    result: List[dict] = []
    for i, action in enumerate(actions):
        curr_root = _popup_root(action.get("meta"))
        prev_root = _popup_root(actions[i - 1].get("meta")) if i > 0 else ""
        if curr_root and not prev_root and action.get("action_type") in (
            "click", "dblclick", "fill", "select", "hover"
        ):
            result.append({
                "action_type": "wait_popup",
                "selector": _popup_wait_locator(action),
                "timestamp": max(0, int(action.get("timestamp", 0)) - 50),
                "meta": {"popupRoot": curr_root},
            })
        result.append(action)
    return result


def _action_to_step(action: dict) -> dict:
    """将单个原始操作转换为平台步骤"""
    action_type = action.get("action_type", "")
    method = ACTION_TO_METHOD.get(action_type)

    if not method:
        return None

    # 构建参数
    params = dict(METHOD_DEFAULTS.get(method, {}))

    if action_type == "navigate":
        params["url"] = action.get("url", "")
        desc = f"打开页面: {params['url'][:50]}"
    elif action_type == "fill":
        params["locator"] = action.get("selector", "")
        params["value"] = action.get("value", "")
        # recorder_engine 中将 placeholder 存到了 element_text 字段
        placeholder = action.get("element_text", "")
        desc = _generate_fill_desc(params["locator"], params["value"], placeholder)
    elif action_type in ("click", "dblclick"):
        params["locator"] = action.get("selector", "")
        element_text = action.get("element_text", "")
        desc = _generate_click_desc(params["locator"], element_text, action_type)
    elif action_type == "select":
        params["locator"] = action.get("selector", "")
        params["value"] = action.get("value", "")
        desc = f"选择下拉框选项: {params['value']}"
    elif action_type == "wait":
        params["timeout"] = int(action.get("value", 2000))
        desc = f"等待 {params['timeout'] // 1000} 秒"
    elif action_type == "wait_popup":
        params["locator"] = action.get("selector", "")
        params["timeout"] = 20000
        desc = "等待弹窗出现"
    elif action_type == "hover":
        params["locator"] = action.get("selector", "")
        element_text = action.get("element_text", "")
        if element_text:
            desc = f"悬停到 '{element_text}'"
        else:
            desc = f"悬停到元素: {params['locator']}"
    elif action_type == "keydown":
        params["key"] = action.get("value", "")
        params["locator"] = action.get("selector", "")
        key = params["key"]
        element_text = action.get("element_text", "")
        if element_text:
            desc = f"在 '{element_text}' 上按 {key} 键"
        else:
            desc = f"按 {key} 键"
    elif action_type == "scroll":
        scroll_top = int(action.get("value", 0))
        scroll_left = int(action.get("element_text", 0))
        params["y"] = scroll_top
        params["x"] = scroll_left
        desc = f"滚动页面到 ({scroll_left}, {scroll_top})"
    elif action_type == "contextmenu":
        params["locator"] = action.get("selector", "")
        params["button"] = "right"
        element_text = action.get("element_text", "")
        if element_text:
            desc = f"右键点击 '{element_text}'"
        else:
            desc = f"右键点击元素: {params['locator']}"
    elif action_type == "file":
        params["locator"] = action.get("selector", "")
        params["file_path"] = ""
        desc = f"上传文件到: {params['locator']}"
    elif action_type == "drag_and_drop":
        params["start_selector"] = action.get("selector", "")
        params["end_selector"] = (
            action.get("value", "")
            or (action.get("meta") or {}).get("end_selector", "")
        )
        source_label = action.get("element_text", "")
        target_label = (action.get("meta") or {}).get("target_label", "")
        if source_label and target_label:
            desc = f"拖拽 '{source_label}' 到 '{target_label}'"
        else:
            desc = f"拖拽元素到目标: {params['end_selector']}"
    else:
        desc = f"执行操作: {action_type}"

    meta = dict(action.get("meta", {}))
    runner_candidates = action.get("candidates") or []
    if runner_candidates:
        meta["candidates"] = list(runner_candidates)
    # 合并 Runner 候选 + meta 字段推导项，避免旧 Runner 或 sparse 上报时前端只有 1 条
    pre_step = {"meta": meta, "params": params}
    merged_candidates = collect_step_locator_candidates(pre_step)
    if merged_candidates:
        meta["candidates"] = merged_candidates

    step = {
        "id": f"step_{int(time.time() * 1000)}_{hash(action.get('selector', '')) % 1000}",
        "keyword": _method_to_keyword(method),
        "desc": desc,
        "method": method,
        "params": params,
        "children": [],
        "meta": meta,
    }
    if method in ("click_ele", "double_click_ele", "hover", "fill_value", "wait_for_element") and params.get("locator"):
        if should_repick_locator(step):
            best, _source, updates = pick_best_locator(step, original_locator=params.get("locator"))
            if best:
                step["params"]["locator"] = best
                meta.update(updates)
                step["meta"] = meta
    step = apply_index_from_meta(step)
    return assess_step_quality(step)


def _generate_fill_desc(locator: str, value: str, placeholder: str) -> str:
    """生成输入操作的描述"""
    if placeholder:
        return f"在 '{placeholder}' 输入框输入 '{value}'"
    # 从 selector 中提取
    if "placeholder=" in locator:
        try:
            ph = locator.split('placeholder="')[1].split('"')[0]
            return f"在 '{ph}' 输入框输入 '{value}'"
        except:
            pass
    if "#" in locator:
        elem_id = locator.replace("#", "")
        return f"在 '{elem_id}' 输入框输入 '{value}'"
    return f"输入文本: '{value}'"


def _generate_click_desc(locator: str, element_text: str, action_type: str) -> str:
    """生成点击操作的描述"""
    verb = "双击" if action_type == "dblclick" else "点击"
    if element_text:
        return f"{verb} '{element_text}'"
    # 从 selector 中提取
    if ":has-text(" in locator:
        try:
            text = locator.split(':has-text("')[1].split('")')[0]
            return f"{verb} '{text}'"
        except:
            pass
    if "#" in locator:
        elem_id = locator.replace("#", "")
        return f"{verb} '{elem_id}' 按钮/链接"
    return f"{verb}元素: {locator}"


def _method_to_keyword(method: str) -> str:
    """method → keyword 映射（与 ActionGroup / Runner 对齐）"""
    return METHOD_TO_KEYWORD.get(method, method)


def optimize_steps_with_llm(steps: List[dict], description: str, llm_client) -> List[dict]:
    """
    （可选）使用 LLM 优化步骤描述
    
    将步骤列表 + 用户原始描述传给 LLM，让 LLM 生成更自然的描述。
    当前版本预留接口，不强制调用 LLM。
    """
    # TODO: 接入 LLM 优化
    return steps
