"""环境级 UI 慢站执行策略（global_vars 保留键）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

UI_TIMEOUT_SCALE_KEY = "__ui_timeout_scale"
UI_NAV_WAIT_UNTIL_KEY = "__ui_nav_wait_until"
UI_BUSY_SELECTORS_KEY = "__ui_busy_selectors"
UI_READY_SELECTOR_KEY = "__ui_ready_selector"
UI_READINESS_RETRY_KEY = "__ui_readiness_retry"
UI_BUSY_APPEAR_PROBE_MS_KEY = "__ui_busy_appear_probe_ms"
UI_ACTION_SETTLE_MS_KEY = "__ui_action_settle_ms"
UI_ACTION_SETTLE_QUIET_MS_KEY = "__ui_action_settle_quiet_ms"

UI_EXEC_STRATEGY_KEYS = frozenset(
    {
        UI_TIMEOUT_SCALE_KEY,
        UI_NAV_WAIT_UNTIL_KEY,
        UI_BUSY_SELECTORS_KEY,
        UI_READY_SELECTOR_KEY,
        UI_READINESS_RETRY_KEY,
        UI_BUSY_APPEAR_PROBE_MS_KEY,
        UI_ACTION_SETTLE_MS_KEY,
        UI_ACTION_SETTLE_QUIET_MS_KEY,
    }
)

ALLOWED_NAV_WAIT_UNTIL = frozenset({"commit", "domcontentloaded", "load", "networkidle"})

DEFAULT_TIMEOUT_SCALE = 1.0
DEFAULT_NAV_WAIT_UNTIL = "domcontentloaded"
DEFAULT_READINESS_RETRY = 0
DEFAULT_BUSY_APPEAR_PROBE_MS = 800
DEFAULT_ACTION_SETTLE_MS = 0
DEFAULT_ACTION_SETTLE_QUIET_MS = 300
MIN_TIMEOUT_SCALE = 0.5
MAX_TIMEOUT_SCALE = 5.0
MAX_READINESS_RETRY = 3
MIN_BUSY_APPEAR_PROBE_MS = 0
MAX_BUSY_APPEAR_PROBE_MS = 5000
MIN_ACTION_SETTLE_MS = 0
MAX_ACTION_SETTLE_MS = 30000
MIN_ACTION_SETTLE_QUIET_MS = 0
MAX_ACTION_SETTLE_QUIET_MS = 5000


def _extract_plain(raw: Any) -> Any:
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def normalize_timeout_scale(raw: Any) -> Optional[float]:
    """规范化超时倍率；空值返回 None（表示可不写入）。"""
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    try:
        scale = float(val)
    except (TypeError, ValueError) as exc:
        raise ValueError("UI 超时倍率必须是数字") from exc
    if scale < MIN_TIMEOUT_SCALE or scale > MAX_TIMEOUT_SCALE:
        raise ValueError(f"UI 超时倍率须在 {MIN_TIMEOUT_SCALE}–{MAX_TIMEOUT_SCALE} 之间")
    return round(scale, 3)


def normalize_nav_wait_until(raw: Any) -> Optional[str]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    s = str(val).strip().lower()
    if s not in ALLOWED_NAV_WAIT_UNTIL:
        raise ValueError(
            "导航等待须为 commit / domcontentloaded / load / networkidle 之一"
        )
    return s


def normalize_busy_selectors(raw: Any) -> Optional[List[str]]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    items: List[str] = []
    if isinstance(val, list):
        for item in val:
            s = str(item or "").strip()
            if s:
                items.append(s)
    else:
        text = str(val).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            s = line.strip()
            if s:
                items.append(s)
    if not items:
        return None
    if len(items) > 20:
        raise ValueError("忙碌选择器最多 20 个")
    for s in items:
        if len(s) > 200:
            raise ValueError("单个忙碌选择器长度不能超过 200 字符")
        # 轻量语法检查：明显非法的选择器在保存时就拦下
        if s.count("(") != s.count(")") or s.count("[") != s.count("]"):
            raise ValueError(f"忙碌选择器括号不匹配：{s}")
        if s.count("'") % 2 != 0 or s.count('"') % 2 != 0:
            raise ValueError(f"忙碌选择器引号不匹配：{s}")
    return items


def normalize_ready_selector(raw: Any) -> Optional[str]:
    val = _extract_plain(raw)
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if len(s) > 300:
        raise ValueError("就绪选择器长度不能超过 300 字符")
    if s.count("(") != s.count(")") or s.count("[") != s.count("]"):
        raise ValueError(f"就绪选择器括号不匹配：{s}")
    if s.count("'") % 2 != 0 or s.count('"') % 2 != 0:
        raise ValueError(f"就绪选择器引号不匹配：{s}")
    return s


def normalize_readiness_retry(raw: Any) -> Optional[int]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError) as exc:
        raise ValueError("就绪重试次数必须是整数") from exc
    if n < 0 or n > MAX_READINESS_RETRY:
        raise ValueError(f"就绪重试次数须在 0–{MAX_READINESS_RETRY} 之间")
    return n


def normalize_busy_appear_probe_ms(raw: Any) -> Optional[int]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError) as exc:
        raise ValueError("忙碌遮罩探测窗口必须是整数毫秒") from exc
    if n < MIN_BUSY_APPEAR_PROBE_MS or n > MAX_BUSY_APPEAR_PROBE_MS:
        raise ValueError(
            f"忙碌遮罩探测窗口须在 {MIN_BUSY_APPEAR_PROBE_MS}–{MAX_BUSY_APPEAR_PROBE_MS}ms 之间"
        )
    return n


def normalize_action_settle_ms(raw: Any) -> Optional[int]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError) as exc:
        raise ValueError("操作后页面沉降预算必须是整数毫秒") from exc
    if n < MIN_ACTION_SETTLE_MS or n > MAX_ACTION_SETTLE_MS:
        raise ValueError(
            f"操作后页面沉降预算须在 {MIN_ACTION_SETTLE_MS}–{MAX_ACTION_SETTLE_MS}ms 之间"
        )
    return n


def normalize_action_settle_quiet_ms(raw: Any) -> Optional[int]:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError) as exc:
        raise ValueError("操作后 DOM 静默窗口必须是整数毫秒") from exc
    if n < MIN_ACTION_SETTLE_QUIET_MS or n > MAX_ACTION_SETTLE_QUIET_MS:
        raise ValueError(
            f"操作后 DOM 静默窗口须在 {MIN_ACTION_SETTLE_QUIET_MS}–{MAX_ACTION_SETTLE_QUIET_MS}ms 之间"
        )
    return n


def normalize_ui_exec_strategy_value(key: str, raw: Any) -> Any:
    """normalize_global_vars 用：返回应写入的值，或 None 表示删除该键。"""
    if key == UI_TIMEOUT_SCALE_KEY:
        scale = normalize_timeout_scale(raw)
        if scale is None or abs(scale - DEFAULT_TIMEOUT_SCALE) < 1e-9:
            return None
        return scale
    if key == UI_NAV_WAIT_UNTIL_KEY:
        wait = normalize_nav_wait_until(raw)
        if wait is None or wait == DEFAULT_NAV_WAIT_UNTIL:
            return None
        return wait
    if key == UI_BUSY_SELECTORS_KEY:
        return normalize_busy_selectors(raw)
    if key == UI_READY_SELECTOR_KEY:
        return normalize_ready_selector(raw)
    if key == UI_READINESS_RETRY_KEY:
        retry = normalize_readiness_retry(raw)
        if retry is None or retry == DEFAULT_READINESS_RETRY:
            return None
        return retry
    if key == UI_BUSY_APPEAR_PROBE_MS_KEY:
        probe = normalize_busy_appear_probe_ms(raw)
        if probe is None or probe == DEFAULT_BUSY_APPEAR_PROBE_MS:
            return None
        return probe
    if key == UI_ACTION_SETTLE_MS_KEY:
        settle = normalize_action_settle_ms(raw)
        if settle is None or settle == DEFAULT_ACTION_SETTLE_MS:
            return None
        return settle
    if key == UI_ACTION_SETTLE_QUIET_MS_KEY:
        quiet = normalize_action_settle_quiet_ms(raw)
        if quiet is None or quiet == DEFAULT_ACTION_SETTLE_QUIET_MS:
            return None
        return quiet
    raise ValueError(f"未知 UI 执行策略键：{key}")


def parse_ui_timeout_scale(global_vars: dict | None) -> float:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        scale = normalize_timeout_scale(gv.get(UI_TIMEOUT_SCALE_KEY))
    except ValueError:
        return DEFAULT_TIMEOUT_SCALE
    return float(scale) if scale is not None else DEFAULT_TIMEOUT_SCALE


def parse_ui_nav_wait_until(global_vars: dict | None) -> str:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        wait = normalize_nav_wait_until(gv.get(UI_NAV_WAIT_UNTIL_KEY))
    except ValueError:
        return DEFAULT_NAV_WAIT_UNTIL
    return wait or DEFAULT_NAV_WAIT_UNTIL


def parse_ui_busy_selectors(global_vars: dict | None) -> List[str]:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        items = normalize_busy_selectors(gv.get(UI_BUSY_SELECTORS_KEY))
    except ValueError:
        return []
    return list(items or [])


def parse_ui_ready_selector(global_vars: dict | None) -> str:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        sel = normalize_ready_selector(gv.get(UI_READY_SELECTOR_KEY))
    except ValueError:
        return ""
    return sel or ""


def parse_ui_readiness_retry(global_vars: dict | None) -> int:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        n = normalize_readiness_retry(gv.get(UI_READINESS_RETRY_KEY))
    except ValueError:
        return DEFAULT_READINESS_RETRY
    return DEFAULT_READINESS_RETRY if n is None else int(n)


def parse_ui_busy_appear_probe_ms(global_vars: dict | None) -> int:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        n = normalize_busy_appear_probe_ms(gv.get(UI_BUSY_APPEAR_PROBE_MS_KEY))
    except ValueError:
        return DEFAULT_BUSY_APPEAR_PROBE_MS
    return DEFAULT_BUSY_APPEAR_PROBE_MS if n is None else int(n)


def parse_ui_action_settle_ms(global_vars: dict | None) -> int:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        n = normalize_action_settle_ms(gv.get(UI_ACTION_SETTLE_MS_KEY))
    except ValueError:
        return DEFAULT_ACTION_SETTLE_MS
    return DEFAULT_ACTION_SETTLE_MS if n is None else int(n)


def parse_ui_action_settle_quiet_ms(global_vars: dict | None) -> int:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        n = normalize_action_settle_quiet_ms(gv.get(UI_ACTION_SETTLE_QUIET_MS_KEY))
    except ValueError:
        return DEFAULT_ACTION_SETTLE_QUIET_MS
    return DEFAULT_ACTION_SETTLE_QUIET_MS if n is None else int(n)


def build_ui_exec_strategy_payload(
    global_vars: dict | None,
    *,
    timeout_scale_override: Optional[float] = None,
) -> Dict[str, Any]:
    """构建下发给 Runner 的 UI 执行策略字段（含启动登录态注入）。"""
    from app.core.shared.ui_auth_inject import build_ui_auth_inject_payload

    scale = parse_ui_timeout_scale(global_vars)
    if timeout_scale_override is not None:
        normalized = normalize_timeout_scale(timeout_scale_override)
        if normalized is not None:
            scale = float(normalized)
    payload: Dict[str, Any] = {
        "ui_timeout_scale": scale,
        "ui_nav_wait_until": parse_ui_nav_wait_until(global_vars),
        "ui_busy_selectors": parse_ui_busy_selectors(global_vars),
        "ui_ready_selector": parse_ui_ready_selector(global_vars),
        "ui_readiness_retry": parse_ui_readiness_retry(global_vars),
        "ui_busy_appear_probe_ms": parse_ui_busy_appear_probe_ms(global_vars),
        "ui_action_settle_ms": parse_ui_action_settle_ms(global_vars),
        "ui_action_settle_quiet_ms": parse_ui_action_settle_quiet_ms(global_vars),
    }
    payload.update(build_ui_auth_inject_payload(global_vars))
    return payload
