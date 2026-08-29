"""BL-1 动作缓存确定性回放（Playwright，零 token）。"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from app.core.platform import config as settings
from app.modules.browser_lab.browser_lab_action_cache_core import (
    ALLOWED_CACHE_OPS,
    SCHEMA_VERSION,
    urls_match_template,
)

logger = logging.getLogger(__name__)

StepCallback = Callable[[dict[str, Any]], Awaitable[None]]
StopCallback = Callable[[], bool]


def _parse_locator(page, selector: str):
    """支持 get_by_text= / get_by_label= / 裸 CSS/xpath。"""
    sel = (selector or "").strip()
    if not sel:
        raise ValueError("空 selector")
    if sel.startswith("get_by_text="):
        text = sel[len("get_by_text=") :].strip()
        return page.get_by_text(text, exact=False)
    if sel.startswith("get_by_label="):
        text = sel[len("get_by_label=") :].strip()
        return page.get_by_label(text, exact=False)
    if sel.startswith("xpath=") or sel.startswith("//") or sel.startswith("(//"):
        xpath = sel[6:] if sel.startswith("xpath=") else sel
        return page.locator(f"xpath={xpath}")
    return page.locator(sel)


async def _resolve_value(action: dict, variables: dict[str, Any] | None) -> str:
    variables = variables or {}
    if action.get("sensitive") and not (
        isinstance(action.get("value_from"), str) and action.get("value_from").startswith("var:")
    ):
        raise ValueError("敏感字段缺少 value_from，无法回放")
    value_from = action.get("value_from")
    if isinstance(value_from, str) and value_from.startswith("var:"):
        key = value_from[4:]
        if key not in variables:
            raise ValueError(f"缺少变量 {key}")
        return "" if variables[key] is None else str(variables[key])
    val = action.get("value")
    return "" if val is None else str(val)


async def _prepare_target(loc, timeout: int):
    """可见等待 + 滚入视口，降低 SPA 懒加载误降级。"""
    target = loc.first
    await target.wait_for(state="visible", timeout=timeout)
    try:
        await target.scroll_into_view_if_needed(timeout=min(5000, timeout))
    except Exception:
        pass
    return target


async def _click_or_fill(page, action: dict, *, variables: dict | None) -> None:
    op = (action.get("op") or "").lower()
    selector = (action.get("selector") or "").strip()
    timeout = int(action.get("timeout_ms") or 15000)
    if not selector:
        raise ValueError(f"{op} 缺少稳定 selector（弱定位已跳过）")
    loc = _parse_locator(page, selector)
    target = await _prepare_target(loc, timeout)

    if op == "click":
        try:
            await target.click(timeout=timeout, force=False)
        except Exception:
            await target.click(timeout=timeout, force=True)
        return

    if op == "fill":
        value = await _resolve_value(action, variables)
        await target.fill(value, timeout=timeout)
        return

    if op == "select":
        value = await _resolve_value(action, variables)
        option_selector = (action.get("option_selector") or "").strip()
        try:
            await target.select_option(value, timeout=timeout)
            return
        except Exception:
            pass
        # 自定义下拉：先点开控件，再点选项（优先专用 option_selector / role=option）
        await target.click(timeout=timeout, force=False)
        if option_selector:
            opt = _parse_locator(page, option_selector)
            opt_target = await _prepare_target(opt, timeout)
            await opt_target.click(timeout=timeout, force=False)
            return
        try:
            await page.get_by_role("option", name=value, exact=False).first.click(timeout=timeout)
            return
        except Exception as ex:
            raise ValueError(
                f"select 失败且无可靠 option 定位（勿用页面级 get_by_text）：{ex}"
            ) from ex

    raise ValueError(f"不支持的元素操作: {op}")


async def _run_assertions(page, assertions: dict | None) -> None:
    assertions = assertions or {}
    final_tpl = (assertions.get("final_url_template") or "").strip()
    if assertions.get("require_final_url") and final_tpl:
        actual = page.url or ""
        if not urls_match_template(actual, final_tpl):
            raise AssertionError(
                f"终态 URL 不匹配：actual={actual!r} template={final_tpl!r}"
            )
    title_contains = (assertions.get("title_contains") or "").strip()
    if title_contains:
        title = await page.title()
        if title_contains not in (title or ""):
            raise AssertionError(
                f"终态 title 未包含 {title_contains!r}，实际={title!r}"
            )
    for text in assertions.get("text_contains") or []:
        t = (text or "").strip()
        if not t or len(t) < 2:
            continue
        body = await page.locator("body").inner_text(timeout=5000)
        if t not in (body or ""):
            raise AssertionError(f"终态文案未找到: {t!r}")


def check_actions_schema(actions: list, schema_version: int | None) -> None:
    if int(schema_version or 0) != SCHEMA_VERSION:
        raise ValueError(
            f"缓存 schema_version={schema_version} 与当前 {SCHEMA_VERSION} 不兼容"
        )
    for action in actions:
        if not isinstance(action, dict) or not action.get("op"):
            raise ValueError("缓存动作缺少 op")
        op = str(action.get("op") or "").strip().lower()
        if op not in ALLOWED_CACHE_OPS:
            raise ValueError(f"缓存动作 op 不在白名单: {op}")


async def replay_cached_actions(
    *,
    start_url: str,
    actions: list[dict],
    assertions: dict | None = None,
    variables: dict[str, Any] | None = None,
    on_step: Optional[StepCallback] = None,
    should_stop: Optional[StopCallback] = None,
    headless: bool = True,
    schema_version: int | None = SCHEMA_VERSION,
) -> dict[str, Any]:
    """逐步回放缓存动作并校验终态断言。成功返回 summary dict，失败抛异常。"""
    if not actions:
        raise ValueError("缓存动作为空")
    check_actions_schema(actions, schema_version)

    from playwright.async_api import async_playwright

    viewport_w = max(800, settings.BROWSER_LAB_VIEWPORT_WIDTH)
    viewport_h = max(600, settings.BROWSER_LAB_VIEWPORT_HEIGHT)
    step_events: list[dict[str, Any]] = []
    playwright = None
    browser = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--lang=zh-CN",
            ],
        )
        context = await browser.new_context(
            viewport={"width": viewport_w, "height": viewport_h},
            locale="zh-CN",
        )
        page = await context.new_page()
        page.set_default_timeout(30000)

        await page.goto(start_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        start_event = {
            "type": "step",
            "index": 0,
            "url": page.url,
            "title": await page.title(),
            "next_goal": "缓存回放：打开起始页",
            "actions": [{"navigate": {"url": start_url}}],
            "cache_replay": True,
        }
        step_events.append(start_event)
        if on_step:
            await on_step(start_event)

        for i, action in enumerate(actions, start=1):
            if should_stop and should_stop():
                raise RuntimeError("用户已停止")
            if not isinstance(action, dict):
                continue
            op = (action.get("op") or "").lower()
            try:
                if op == "navigate":
                    url = (action.get("url") or "").strip()
                    if not url:
                        raise ValueError("navigate 缺少 url")
                    if action.get("new_tab"):
                        page = await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded")
                elif op == "wait":
                    ms = int(action.get("timeout_ms") or 1000)
                    await page.wait_for_timeout(max(100, min(ms, 60000)))
                elif op == "scroll":
                    y = int(action.get("y") or 400)
                    await page.evaluate(f"window.scrollBy(0, {y});")
                elif op == "press":
                    key = str(action.get("key") or "Enter")
                    await page.keyboard.press(key)
                elif op in ("click", "fill", "select"):
                    if (action.get("strength") or "") == "weak" and not (action.get("selector") or "").strip():
                        raise ValueError("弱定位动作不可回放")
                    await _click_or_fill(page, action, variables=variables)
                else:
                    logger.info("[browser_lab_cache_replay] skip unsupported op=%s", op)
                    continue

                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass

                safe_payload = {
                    k: v
                    for k, v in action.items()
                    if k not in ("value", "options")
                }
                if "value" in action and "value_from" not in action:
                    safe_payload["value"] = "***"
                event = {
                    "type": "step",
                    "index": i,
                    "url": page.url,
                    "title": await page.title(),
                    "next_goal": f"缓存回放：{op}",
                    "actions": [{op: safe_payload}],
                    "cache_replay": True,
                }
                step_events.append(event)
                if on_step:
                    await on_step(event)
            except Exception as ex:
                raise RuntimeError(f"回放第 {i} 步失败（{op}）: {ex}") from ex

        await _run_assertions(page, assertions)
        summary = {
            "ok": True,
            "steps": len(step_events),
            "final_url": page.url,
            "final_title": await page.title(),
            "step_events": step_events,
            "message": "动作缓存回放成功（零 token）",
        }
        return summary
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            if playwright:
                await playwright.stop()
        except Exception:
            pass
