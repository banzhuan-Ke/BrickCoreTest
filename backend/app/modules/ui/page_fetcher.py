"""
页面抓取模块
使用 Playwright 无头浏览器抓取目标页面的简化 DOM 结构
供 AI 生成 UI 测试用例时作为页面上下文
"""

import json
import logging
import asyncio
import os
import re
from datetime import datetime
from typing import Any, Optional
from app.core.shared.locator_utils import normalize_locator, prefer_popup_elements, resolve_locator_on_page
from app.modules.ui.scroll_page_js import SCROLL_PAGE_JS
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ('', '0', 'false', 'no', 'off'):
        return False
    if text in ('1', 'true', 'yes', 'on'):
        return True
    return default

# 最大返回元素数量
MAX_ELEMENTS = 100

# 页面抓取 JS：提取可交互元素的关键信息
EXTRACT_ELEMENTS_JS = """
() => {
    const elements = [];
    const seen = new Set();
    
    function isVisible(el) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        return rect.top < window.innerHeight && rect.bottom > 0;
    }
    
    function getUniqueKey(el) {
        // 必须包含能区分同类元素的属性，否则账号框和密码框（同class、同tag、无id、无text）会被去重
        const tag = el.tagName;
        const id = el.id || '';
        const cls = ((el.className || '').toString());
        const text = (el.textContent || '').slice(0, 30);
        const name = el.name || '';
        const ph = el.placeholder || '';
        const type = el.type || '';
        const title = el.getAttribute('title') || '';
        const role = el.getAttribute('role') || '';
        return tag + '|' + id + '|' + cls + '|' + text + '|' + name + '|' + ph + '|' + type + '|' + title + '|' + role;
    }
    
    function escapeQuotes(str) {
        return (str || '').replace(/"/g, '\\"');
    }

    function isInsidePopup(el) {
        var node = el;
        var depth = 0;
        while (node && node !== document.body && depth < 14) {
            if (!node.tagName) break;
            var role = node.getAttribute('role') || '';
            var cls = (node.className || '').toString();
            var style = window.getComputedStyle(node);
            var isFixed = style.position === 'fixed' || style.position === 'absolute';
            var looksModal = role === 'dialog' || role === 'alertdialog' ||
                /modal|popup|dialog|overlay|mask|drawer|uni-popup|pay-|recharge/i.test(cls);
            var rect = node.getBoundingClientRect();
            if (looksModal && rect.width >= 120 && rect.height >= 60 && (isFixed || role === 'dialog')) {
                return true;
            }
            node = node.parentElement;
            depth++;
        }
        return false;
    }
    
    function getSelector(el) {
        const tag = el.tagName.toLowerCase();
        // 1. data-testid（最稳定，与录制引擎一致）
        const testid = el.getAttribute('data-testid');
        if (testid) return '[data-testid="' + escapeQuotes(testid) + '"]';
        // 2. id
        if (el.id) return '#' + el.id;
        // 3. name
        if (el.name) return tag + '[name="' + escapeQuotes(el.name) + '"]';
        // 4. placeholder（仅 input/textarea）
        if (tag === 'input' && el.placeholder) {
            return 'input[placeholder="' + escapeQuotes(el.placeholder.slice(0, 30)) + '"]';
        }
        // 5. aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return '[aria-label="' + escapeQuotes(ariaLabel) + '"]';
        // 6. role + text（Playwright get_by_role 风格，转换为 CSS 选择器）
        const role = el.getAttribute('role');
        const text = (el.textContent || '').trim();
        if (role && text && text.length > 1 && text.length < 30 && !/^\d+$/.test(text)) {
            return tag + '[role="' + escapeQuotes(role) + '"]:has-text("' + escapeQuotes(text) + '")';
        }
        if (role) {
            return tag + '[role="' + escapeQuotes(role) + '"]';
        }
        // 7. title 属性（常用于图标按钮、卡片等）
        const title = el.getAttribute('title');
        if (title) return tag + '[title="' + escapeQuotes(title.slice(0, 30)) + '"]';
        // 8. has-text 兜底
        if (text && text.length > 1 && text.length < 30 && !/^\d+$/.test(text)) {
            return tag + ':has-text("' + escapeQuotes(text) + '")';
        }
        // 9. class（排除 ng-* 等 Angular/Vue/React 动态类）
        const classes = (el.className || '').toString().split(' ').filter(c => c && !c.startsWith('ng-') && !c.startsWith('v-') && c.length < 30);
        if (classes.length > 0) {
            return tag + '.' + classes[0];
        }
        // 10. 最兜底：纯 tag
        return tag;
    }
    
    function processElement(el) {
        if (!isVisible(el)) return;
        const key = getUniqueKey(el);
        if (seen.has(key)) return;
        seen.add(key);
        
        const tag = el.tagName.toLowerCase();
        const text = (el.textContent || el.value || el.title || '').trim().slice(0, 100);
        const selector = getSelector(el);
        const role = el.getAttribute('role') || '';
        const title = el.getAttribute('title') || '';
        const testid = el.getAttribute('data-testid') || '';
        // 判断是否为可交互元素（与录制引擎一致）
        const clickable = tag === 'button' || tag === 'a' || tag === 'input' || tag === 'select' || tag === 'textarea' ||
                          role === 'button' || role === 'link' || role === 'tab' || role === 'menuitem' ||
                          el.getAttribute('onclick') !== null;
        
        elements.push({
            tag: tag,
            id: el.id || '',
            class: (el.className || '').toString().split(' ').slice(0, 3).join(' ').trim(),
            name: el.name || '',
            type: el.type || '',
            placeholder: el.getAttribute('placeholder') || '',
            aria_label: el.getAttribute('aria-label') || '',
            data_testid: testid,
            title: title,
            role: role,
            text: text,
            selector: selector,
            clickable: clickable,
            in_popup: isInsidePopup(el),
        });
    }
    
    // 1. 标准交互标签
    ['input', 'button', 'a', 'select', 'textarea'].forEach(tag => {
        document.querySelectorAll(tag).forEach(processElement);
    });
    
    // 2. 带有可交互属性的元素（卡片、图标按钮、自定义组件等）
    document.querySelectorAll('[role]:not([role="presentation"]):not([role="none"]), [onclick], [tabindex]:not([tabindex="-1"]), [title]').forEach(processElement);
    
    // 3. 文本元素（用于 text 定位器参考）
    document.querySelectorAll('h1, h2, h3, h4, h5, h6, label, li, dt, dd').forEach(processElement);
    
    // 4. 有可见文本的 span（如 <span class="show-name">控制台</span>）
    document.querySelectorAll('span').forEach(el => {
        const text = (el.textContent || '').trim();
        if (text.length > 0 && text.length < 50 && el.offsetParent !== null) {
            processElement(el);
        }
    });
    
    // 按优先级排序：data-testid > 可交互 > 有 id > 有 name/aria-label/title > 有 role > 有 text
    elements.sort((a, b) => {
        const scoreA = (a.data_testid ? 6 : 0) + (a.clickable ? 5 : 0) + (a.id ? 3 : 0) + (a.name ? 2 : 0) + (a.aria_label ? 2 : 0) + (a.title ? 2 : 0) + (a.role ? 1 : 0) + (a.text ? 1 : 0);
        const scoreB = (b.data_testid ? 6 : 0) + (b.clickable ? 5 : 0) + (b.id ? 3 : 0) + (b.name ? 2 : 0) + (b.aria_label ? 2 : 0) + (b.title ? 2 : 0) + (b.role ? 1 : 0) + (b.text ? 1 : 0);
        return scoreB - scoreA;
    });
    
    return elements.slice(0, 100);
}
"""


async def fetch_page_structure(url: str, timeout: int = 15) -> Optional[dict]:
    """
    抓取目标页面的简化 DOM 结构
    
    :param url: 目标页面 URL
    :param timeout: 总超时时间（秒）
    :return: {
        "title": str,
        "url": str,
        "elements": [...],
        "status_code": int
    }
    失败时返回 None
    """
    if not url or not url.startswith(("http://", "https://")):
        logger.warning(f"[page_fetcher] 无效的 URL: {url}")
        return None

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--lang=zh-CN",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(timeout * 1000)

        logger.info(f"[page_fetcher] 开始抓取页面: {url}")
        start_time = asyncio.get_event_loop().time()

        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        await asyncio.sleep(1)

        raw_elements = await page.evaluate(EXTRACT_ELEMENTS_JS)
        raw_elements = prefer_popup_elements(raw_elements)
        title = await page.title()
        current_url = page.url

        elapsed = round(asyncio.get_event_loop().time() - start_time, 2)
        logger.info(
            f"[page_fetcher] 抓取完成: {current_url}, "
            f"title={title}, elements={len(raw_elements)}, elapsed={elapsed}s"
        )

        elements = []
        for el in raw_elements:
            cleaned = {
                "tag": el.get("tag", ""),
                "id": el.get("id", ""),
                "class": el.get("class", ""),
                "name": el.get("name", ""),
                "type": el.get("type", ""),
                "placeholder": el.get("placeholder", ""),
                "aria_label": el.get("aria_label", ""),
                "data_testid": el.get("data_testid", ""),
                "title": el.get("title", ""),
                "role": el.get("role", ""),
                "text": el.get("text", ""),
                "selector": el.get("selector", ""),
            }
            if not any([
                cleaned["id"], cleaned["name"], cleaned["class"],
                cleaned["aria_label"], cleaned["selector"], cleaned["text"],
                cleaned["data_testid"], cleaned["title"], cleaned["role"],
            ]):
                continue
            elements.append(cleaned)

        return {
            "title": title,
            "url": current_url,
            "elements": elements[:MAX_ELEMENTS],
            "status_code": response.status if response else 0,
        }

    except Exception as e:
        logger.warning(f"[page_fetcher] 抓取页面失败: {url}, error={e}")
        return None

    finally:
        for obj in [page, context, browser]:
            try:
                if obj:
                    await obj.close()
            except Exception:
                pass
        try:
            if playwright:
                await playwright.stop()
        except Exception:
            pass


def format_elements_for_prompt(elements: list) -> str:
    """将元素列表格式化为适合 Prompt 的文本"""
    if not elements:
        return ""

    lines = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        tag = el.get("tag") or "?"
        parts = [f"<{tag}>"]
        for key in ["id", "class", "name", "type", "placeholder", "aria_label", "data_testid", "title", "role", "text", "selector"]:
            if el.get(key):
                parts.append(f"{key}={el[key]}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


MAX_ARIA_SNAPSHOT_CHARS = 14000


async def capture_accessibility_snapshot(page) -> tuple[str, str]:
    """
    抓取页面无障碍树快照（Playwright MCP 思路），失败则降级为 DOM 元素列表。
    返回 (snapshot_text, snapshot_type)，snapshot_type 为 aria 或 dom。
    """
    try:
        snap = await page.locator("body").aria_snapshot()
        if snap and snap.strip():
            text = snap.strip()
            if len(text) > MAX_ARIA_SNAPSHOT_CHARS:
                text = text[:MAX_ARIA_SNAPSHOT_CHARS] + "\n... (truncated)"
            return text, "aria"
    except Exception as e:
        logger.debug(f"[page_fetcher] aria_snapshot 不可用，降级 DOM: {e}")

    try:
        raw_elements = await page.evaluate(EXTRACT_ELEMENTS_JS)
        elements = []
        for el in raw_elements:
            cleaned = {
                "tag": el.get("tag", ""),
                "id": el.get("id", ""),
                "class": el.get("class", ""),
                "name": el.get("name", ""),
                "type": el.get("type", ""),
                "placeholder": el.get("placeholder", ""),
                "aria_label": el.get("aria_label", ""),
                "data_testid": el.get("data_testid", ""),
                "title": el.get("title", ""),
                "role": el.get("role", ""),
                "text": el.get("text", ""),
                "selector": el.get("selector", ""),
            }
            if any([
                cleaned["id"], cleaned["name"], cleaned["class"],
                cleaned["aria_label"], cleaned["selector"], cleaned["text"],
                cleaned["data_testid"], cleaned["title"], cleaned["role"],
            ]):
                elements.append(cleaned)
        dom_text = format_elements_for_prompt(elements[:MAX_ELEMENTS])
        if dom_text:
            return dom_text, "dom"
    except Exception as e:
        logger.warning(f"[page_fetcher] DOM 降级抓取失败: {e}")

    return "(empty snapshot)", "dom"


# ==================== SmartPageExplorer：有状态多轮生成 ====================

class SmartPageExplorer:
    """
    有状态的多页面 AI 探索器
    在同一个 Playwright context 内，循环执行：
    抓取 DOM → AI 生成步骤 → 执行步骤 → 检测页面变化 → 再抓取 → ...
    """

    def __init__(
        self,
        start_url: str,
        description: str,
        max_rounds: int = 3,
        timeout: int = 15,
        screenshots_dir: Optional[str] = None,
    ):
        self.start_url = start_url
        self.description = description
        self.max_rounds = max_rounds
        self.timeout = timeout

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        self.all_steps = []
        self.errors = []
        self.urls_visited = []
        self.page_changes = 0
        self.screenshots = []  # [{url, path, round, step, reason}]

        # 截图保存目录
        if screenshots_dir:
            self.screenshots_dir = screenshots_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.screenshots_dir = os.path.join(base_dir, "static", "screenshots", "explore")
        os.makedirs(self.screenshots_dir, exist_ok=True)

    async def explore(self, llm_generate_func) -> dict:
        """
        执行多轮探索
        :param llm_generate_func: 回调函数，签名：
            async fn(dom_text: str, description: str, executed_steps: list,
                     current_url: str, round_index: int) -> list[dict]
        :return: {"steps": [...], "rounds": int, "page_changes": int,
                  "urls_visited": [...], "errors": [...]}
        """
        await self._init_browser()

        try:
            await self.page.goto(self.start_url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(1)

            for round_idx in range(1, self.max_rounds + 1):
                logger.info(f"[SmartPageExplorer] 开始第 {round_idx}/{self.max_rounds} 轮探索")

                # 1. 抓取当前页面 DOM
                snapshot = await self._extract_current_snapshot()
                self.urls_visited.append(snapshot["url"])
                # 每轮开始时截图，记录页面初始状态
                await self._take_screenshot(
                    round_index=round_idx,
                    step_index=0,
                    reason=f"第 {round_idx} 轮开始，页面: {snapshot['url']}"
                )

                # 2. 调用 AI 生成步骤
                dom_text = format_elements_for_prompt(snapshot["elements"])
                steps = await llm_generate_func(
                    dom_text=dom_text,
                    description=self.description,
                    executed_steps=self.all_steps.copy(),
                    current_url=snapshot["url"],
                    round_index=round_idx,
                )

                if not steps:
                    logger.info(f"[SmartPageExplorer] 第 {round_idx} 轮 AI 返回空步骤，探索完成")
                    break

                # 3. 执行生成的步骤
                page_changed_in_round = False
                step_executed_count = 0
                for step in steps:
                    success, error = await self._execute_step(step)
                    step_executed_count += 1
                    if not success:
                        self.errors.append(f"第 {round_idx} 轮第 {step_executed_count} 步执行失败: {error}")
                        logger.warning(f"[SmartPageExplorer] 步骤执行失败: {error}")
                        # 截图保存现场
                        screenshot_url = await self._take_screenshot(
                            round_index=round_idx,
                            step_index=step_executed_count,
                            reason=f"执行失败: {step.get('method', '')} - {error[:100]}"
                        )
                        if screenshot_url:
                            self.errors.append(f"截图已保存: {screenshot_url}")
                        # 保留该轮所有步骤（包括执行失败的和未执行的）
                        self.all_steps.extend(steps)
                        logger.info(f"[SmartPageExplorer] 保留该轮全部 {len(steps)} 个步骤（含未执行部分），终止探索")
                        return self._build_result(round_idx)

                    # 每步执行后检测页面是否变化
                    changed, reason = await self._is_page_changed(snapshot)
                    if changed:
                        self.page_changes += 1
                        page_changed_in_round = True
                        logger.info(f"[SmartPageExplorer] 页面变化 detected: {reason}")
                        # 页面变化时截图，记录变化后的状态
                        await self._take_screenshot(
                            round_index=round_idx,
                            step_index=steps.index(step) + 1,
                            reason=f"页面变化: {reason}"
                        )
                        # 将已执行的步骤加入 all_steps，剩余步骤也保留但标记为未执行
                        executed_count = steps.index(step) + 1
                        self.all_steps.extend(steps[:executed_count])
                        if executed_count < len(steps):
                            logger.info(f"[SmartPageExplorer] 已执行 {executed_count} 步，剩余 {len(steps) - executed_count} 步将在下一轮重新生成")
                        break

                if not page_changed_in_round:
                    self.all_steps.extend(steps)

                # 4. 判断是否需要继续
                if not page_changed_in_round:
                    logger.info(f"[SmartPageExplorer] 第 {round_idx} 轮无页面变化，探索完成")
                    break

                # 页面变化后，等待新页面稳定（SPA 首页可能需要更长时间加载）
                await self._wait_for_dom_stable(max_wait=10)

            return self._build_result(min(round_idx, self.max_rounds))

        except Exception as e:
            logger.error(f"[SmartPageExplorer] 探索异常: {e}", exc_info=True)
            self.errors.append(f"探索异常: {str(e)}")
            return self._build_result(0)

        finally:
            await self._close()

    async def _wait_for_dom_stable(self, max_wait: int = 10):
        """
        等待页面 DOM 稳定（适用于 SPA 动态加载场景）
        连续抓取 DOM，间隔 1 秒，如果元素数量连续两次不变（或变化 <10%），认为页面稳定。
        但 SPA 框架（Angular/Vue/React）可能在 DOM 数量稳定后才异步渲染组件，
        因此强制至少等待 3 秒，确保关键元素（如导航按钮）已渲染。
        """
        prev_count = -1
        stable_count = 0
        min_wait_seconds = 3  # 强制最少等 3 秒，给 SPA 异步渲染留时间
        for i in range(max_wait):
            try:
                raw_elements = await self.page.evaluate(EXTRACT_ELEMENTS_JS)
                current_count = len(raw_elements)
            except Exception:
                current_count = 0

            if prev_count >= 0:
                change_ratio = abs(current_count - prev_count) / max(prev_count, 1)
                if change_ratio < 0.1:
                    stable_count += 1
                    # 必须同时满足：连续 2 次稳定 + 至少等了 min_wait_seconds 秒
                    if stable_count >= 2 and (i + 1) >= min_wait_seconds:
                        logger.info(f"[SmartPageExplorer] DOM 已稳定，元素数: {current_count}，共等待 {i+1} 秒")
                        # 稳定后再额外等 2 秒，让 SPA 异步组件（如导航栏）完成渲染
                        await asyncio.sleep(2)
                        logger.info(f"[SmartPageExplorer] 额外等待 2 秒完成，开始抓取")
                        return
                else:
                    stable_count = 0

            prev_count = current_count
            await asyncio.sleep(1)

        logger.info(f"[SmartPageExplorer] DOM 等待超时（{max_wait}秒），当前元素数: {prev_count}")

    async def _init_browser(self):
        """初始化 Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--lang=zh-CN",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout * 1000)

    async def _extract_current_snapshot(self) -> dict:
        """抓取当前页面的 DOM 快照"""
        raw_elements = await self.page.evaluate(EXTRACT_ELEMENTS_JS)
        title = await self.page.title()
        current_url = self.page.url

        popup_only = prefer_popup_elements(raw_elements if isinstance(raw_elements, list) else [])
        if popup_only is not raw_elements and popup_only:
            logger.info("[SmartPageExplorer] 快照优先弹窗内 %s 个元素", len(popup_only))
            raw_elements = popup_only

        elements = []
        for el in raw_elements:
            cleaned = {
                "tag": el.get("tag", ""),
                "id": el.get("id", ""),
                "class": el.get("class", ""),
                "name": el.get("name", ""),
                "type": el.get("type", ""),
                "placeholder": el.get("placeholder", ""),
                "aria_label": el.get("aria_label", ""),
                "data_testid": el.get("data_testid", ""),
                "title": el.get("title", ""),
                "role": el.get("role", ""),
                "text": el.get("text", ""),
                "selector": el.get("selector", ""),
            }
            if not any([
                cleaned["id"], cleaned["name"], cleaned["class"],
                cleaned["aria_label"], cleaned["selector"], cleaned["text"],
                cleaned["data_testid"], cleaned["title"], cleaned["role"],
            ]):
                continue
            elements.append(cleaned)

        return {
            "title": title,
            "url": current_url,
            "elements": elements[:MAX_ELEMENTS],
        }

    def _coerce_locator(self, locator: Any) -> str:
        """将 locator 统一为字符串（兼容 LLM 返回的 dict / 函数写法）"""
        return normalize_locator(locator)

    def _resolve_locator(self, locator: Any):
        """
        解析定位器，支持 Playwright 原生定位 API 与 >> 链式 scope。
        """
        locator_str = self._coerce_locator(locator)
        if not locator_str:
            return None
        loc = resolve_locator_on_page(self.page, locator_str)
        if loc is None:
            return None
        return loc.first

    async def extract_interactive_elements(self) -> list:
        """提取当前页可见可交互元素（与录制/自愈 DOM 列表一致）"""
        if not self.page:
            return []
        try:
            raw = await self.page.evaluate(EXTRACT_ELEMENTS_JS)
            if not isinstance(raw, list):
                return []
            filtered = prefer_popup_elements(raw)
            if filtered is not raw:
                logger.info("[page_fetcher] 检测到弹窗层，优先使用弹窗内 %s 个元素", len(filtered))
            return filtered[:MAX_ELEMENTS]
        except Exception as e:
            logger.debug("[page_fetcher] extract_interactive_elements: %s", e)
            return []

    async def _resolve_click_locator(self, locator: Any):
        """
        点击时优先匹配 button/link，避免 get_by_text 误点页面说明等非按钮文本。
        """
        locator_str = self._coerce_locator(locator)
        if " >> " in locator_str or "||" in locator_str:
            return self._resolve_locator(locator_str)
        if not locator_str.startswith("get_by_text="):
            return self._resolve_locator(locator_str)
        text = locator_str.split("=", 1)[1].strip().strip("'\"")
        if not text:
            return self._resolve_locator(locator_str)
        candidates = [
            self.page.get_by_role("button").filter(has_text=text),
            self.page.locator("button, [role='button']").filter(has_text=text),
            self.page.get_by_role("link").filter(has_text=text),
        ]
        for loc in candidates:
            try:
                if await loc.count() > 0:
                    return loc.first
            except Exception:
                continue
        return self._resolve_locator(locator_str)

    def _extract_locator_text(self, locator: Any) -> Optional[str]:
        """从 locator 字符串提取可用于文本/title 匹配的片段"""
        from app.core.shared.locator_utils import extract_locator_text

        text = extract_locator_text(locator)
        if text:
            return text

        import re

        locator_str = self._coerce_locator(locator)
        if not locator_str:
            return None
        if locator_str.startswith("get_by_label="):
            return locator_str[13:].strip()
        if locator_str.startswith("get_by_placeholder="):
            return locator_str[19:].strip()
        for pattern in (
            r'\[title="([^"]+)"\]',
            r'text="([^"]+)"',
        ):
            match = re.search(pattern, locator_str)
            if match:
                return match.group(1)
        return None

    async def _wait_for_element_with_fallback(self, locator: str, timeout_ms: int = 20000) -> None:
        """
        等待元素可见；失败时 scroll、文本/title 可见匹配、点击可见同名元素、降级 attached。
        """
        loc = self._resolve_locator(locator)
        chunk = min(max(timeout_ms // 3, 3000), 10000)

        try:
            await loc.wait_for(timeout=chunk, state="visible")
            return
        except Exception as e1:
            logger.debug(f"[wait_for_element] visible 等待失败: {e1}")

        try:
            await loc.scroll_into_view_if_needed(timeout=3000)
            await loc.wait_for(timeout=chunk, state="visible")
            logger.info("[wait_for_element] scroll 后可见")
            return
        except Exception:
            pass

        text_content = self._extract_locator_text(locator)
        if text_content:
            try:
                await self.page.get_by_text(text_content, exact=False).first.wait_for(
                    timeout=chunk, state="visible"
                )
                logger.info(f"[wait_for_element] get_by_text 可见兜底: {text_content[:40]}")
                return
            except Exception:
                pass
            try:
                await self.page.locator(f'[title="{text_content}"]').first.wait_for(
                    timeout=chunk, state="visible"
                )
                logger.info(f"[wait_for_element] title 可见兜底: {text_content[:40]}")
                return
            except Exception:
                pass
            try:
                result = await self.page.evaluate(
                    """(text) => {
                        const isVis = (el) => {
                            const r = el.getBoundingClientRect();
                            if (r.width === 0 || r.height === 0) return false;
                            const s = getComputedStyle(el);
                            if (s.display === 'none' || s.visibility === 'hidden') return false;
                            return r.top < innerHeight && r.bottom > 0;
                        };
                        const nodes = Array.from(document.querySelectorAll(
                            '[title], a, button, div, span, li, [role="button"], [role="link"]'
                        ));
                        for (const el of nodes) {
                            const t = (el.getAttribute('title') || el.textContent || '').trim();
                            if (!t.includes(text)) continue;
                            if (isVis(el)) {
                                el.scrollIntoView({ block: 'center' });
                                el.click();
                                return 'click';
                            }
                        }
                        return null;
                    }""",
                    text_content,
                )
                if result:
                    await asyncio.sleep(0.5)
                    logger.info(f"[wait_for_element] JS 点击可见元素兜底: {text_content[:40]}")
                    return
            except Exception as e_js:
                logger.debug(f"[wait_for_element] JS 兜底失败: {e_js}")

        try:
            await loc.wait_for(timeout=chunk, state="attached")
            logger.info("[wait_for_element] 降级为 attached（元素已在 DOM）")
            return
        except Exception as e_final:
            raise e_final

    async def _execute_step(self, step: dict) -> tuple[bool, str | None]:
        """
        在当前 page 上执行单个步骤（轻量级执行器）
        返回: (是否成功, 错误信息)
        """
        method = step.get("method", "")
        params = step.get("params", {}) or {}
        if isinstance(params.get("locator"), dict):
            params = {**params, "locator": self._coerce_locator(params.get("locator"))}

        try:
            if method == "fill_value":
                locator = params.get("locator", "")
                value = str(params.get("value", ""))
                if locator:
                    try:
                        # 用 .first 避免 strict mode violation
                        await self._resolve_locator(locator).fill(value)
                    except Exception as e1:
                        logger.debug(f"[fill_value] 第一层 fill 失败: {e1}")
                        # 兜底：如果 locator 包含 placeholder 且精确匹配失败，
                        # 尝试用 JS 搜索 placeholder 包含关键文本的 input
                        placeholder_match = __import__('re').search(r'placeholder="([^"]+)"', locator)
                        if placeholder_match:
                            placeholder_text = placeholder_match.group(1)
                            result = await self.page.evaluate(
                                """(args) => {
                                    const [phText, inputValue] = args;
                                    const inputs = Array.from(document.querySelectorAll('input, textarea'));
                                    for (const input of inputs) {
                                        if (input.offsetParent === null) continue;
                                        const rect = input.getBoundingClientRect();
                                        if (rect.width === 0 || rect.height === 0) continue;
                                        // 部分匹配 placeholder
                                        if (input.placeholder && input.placeholder.includes(phText)) {
                                            input.value = inputValue;
                                            input.dispatchEvent(new Event('input', {bubbles: true}));
                                            input.dispatchEvent(new Event('change', {bubbles: true}));
                                            return true;
                                        }
                                        // 如果是 password 类型且预期是密码输入，直接匹配 type
                                        if (input.type === 'password' && inputValue.length > 3) {
                                            input.value = inputValue;
                                            input.dispatchEvent(new Event('input', {bubbles: true}));
                                            input.dispatchEvent(new Event('change', {bubbles: true}));
                                            return true;
                                        }
                                    }
                                    return false;
                                }""",
                                [placeholder_text, value]
                            )
                            if result:
                                logger.info(f"[fill_value] JS 兜底成功: placeholder 包含 '{placeholder_text}'")
                            else:
                                raise e1
                        else:
                            raise e1

            elif method == "click_ele":
                locator = params.get("locator", "")
                if locator:
                    try:
                        # 用 .first 避免 strict mode violation；get_by_text 优先收敛到 button
                        await (await self._resolve_click_locator(locator)).click()
                    except Exception as e1:
                        logger.debug(f"[click_ele] 第一层点击失败: {e1}")
                        # 提取 has-text 中的文本，尝试 title 定位器兜底
                        has_text_match = __import__('re').search(r':has-text\("([^"]+)"\)', locator)
                        text_content = has_text_match.group(1) if has_text_match else None
                        if not text_content:
                            loc_norm = self._coerce_locator(locator)
                            if loc_norm.startswith("get_by_text="):
                                text_content = loc_norm.split("=", 1)[1].strip().strip("'\"")
                        fallback_ok = False
                        if text_content:
                            try:
                                btn = self.page.locator("button").filter(has_text=text_content)
                                if await btn.count() > 0:
                                    await btn.first.click()
                                    logger.info(f"[click_ele] button filter 兜底成功: {text_content}")
                                    fallback_ok = True
                            except Exception:
                                pass
                        if text_content and not fallback_ok:
                            # 尝试 [title="xxx"]
                            try:
                                await self.page.locator(f'[title="{text_content}"]').first.click()
                                logger.info(f"[click_ele] title 兜底成功: [title=\"{text_content}\"]")
                                fallback_ok = True
                            except Exception:
                                pass
                            # 含 $ 时 :has-text 会解析失败，优先 get_by_text
                            if not fallback_ok and text_content:
                                try:
                                    await self.page.get_by_text(text_content, exact=False).first.click()
                                    logger.info(f"[click_ele] get_by_text 兜底成功: {text_content[:40]}")
                                    fallback_ok = True
                                except Exception:
                                    pass
                            # 尝试 div/span:has-text("xxx")（文本不含 $ 时）
                            if not fallback_ok and text_content and "$" not in text_content and "\\" not in text_content:
                                for tag in ['div', 'span', 'a', 'i']:
                                    try:
                                        await self.page.locator(f'{tag}:has-text("{text_content}")').first.click()
                                        logger.info(f"[click_ele] {tag}:has-text 兜底成功: {tag}:has-text(\"{text_content}\")")
                                        fallback_ok = True
                                        break
                                    except Exception:
                                        pass
                            # JS 兜底：在页面上搜索包含该文本的元素并点击
                            if not fallback_ok:
                                try:
                                    result = await self.page.evaluate(
                                        """(text) => {
                                            // 优先找 title 匹配
                                            let el = document.querySelector('[title="' + text + '"], [title*="' + text + '"]');
                                            if (el && el.offsetParent !== null) { el.click(); return 'title'; }
                                            // 再找 button/a/div/span/i 中包含文本的
                                            const candidates = Array.from(document.querySelectorAll('button, a, div, span, i, svg, path')).filter(e =>
                                                e.offsetParent !== null && e.textContent.includes(text)
                                            );
                                            candidates.sort((a, b) => a.textContent.trim().length - b.textContent.trim().length);
                                            if (candidates.length > 0) { candidates[0].click(); return 'text'; }
                                            return null;
                                        }""",
                                        text_content
                                    )
                                    if result:
                                        logger.info(f"[click_ele] JS 兜底成功 ({result}): '{text_content}'")
                                        fallback_ok = True
                                except Exception as e_js:
                                    logger.debug(f"[click_ele] JS 兜底失败: {e_js}")
                        if not fallback_ok:
                            try:
                                await self._resolve_locator(locator).click(force=True)
                            except Exception as e2:
                                logger.debug(f"[click_ele] force 点击失败: {e2}")
                                await self._resolve_locator(locator).evaluate("el => el.click()")

            elif method == "double_click_ele":
                locator = params.get("locator", "")
                if locator:
                    try:
                        await self._resolve_locator(locator).dblclick()
                    except Exception as e1:
                        logger.debug(f"[double_click_ele] 第一层失败: {e1}")
                        try:
                            await self._resolve_locator(locator).dblclick(force=True)
                        except Exception as e2:
                            logger.debug(f"[double_click_ele] 第二层 force 失败: {e2}")
                            # 用 Playwright locator.evaluate 支持扩展语法
                            await self._resolve_locator(locator).evaluate(
                                "el => { const ev = new MouseEvent('dblclick', {bubbles: true}); el.dispatchEvent(ev); }"
                            )

            elif method == "hover":
                locator = params.get("locator", "")
                if locator:
                    try:
                        await self._resolve_locator(locator).hover()
                    except Exception as e1:
                        logger.debug(f"[hover] 第一层失败: {e1}")
                        try:
                            await self._resolve_locator(locator).hover(force=True)
                        except Exception as e2:
                            logger.debug(f"[hover] 第二层 force 失败: {e2}")
                            # 用 Playwright locator.evaluate 支持扩展语法
                            await self._resolve_locator(locator).evaluate(
                                "el => { const ev = new MouseEvent('mouseover', {bubbles: true}); el.dispatchEvent(ev); }"
                            )

            elif method == "clear_value":
                locator = params.get("locator", "")
                if locator:
                    await self._resolve_locator(locator).fill("")

            elif method == "type_value":
                locator = params.get("locator", "")
                value = str(params.get("value", ""))
                if locator:
                    await self._resolve_locator(locator).type(value)

            elif method == "select_option":
                locator = params.get("locator", "")
                value = params.get("value", "")
                if locator:
                    await self._resolve_locator(locator).select_option(value)

            elif method == "open_url":
                url = params.get("url", "")
                if url:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)

            elif method == "refresh":
                await self.page.reload(wait_until="domcontentloaded", timeout=self.timeout * 1000)

            elif method == "wait_for_time":
                ms = params.get("timeout", 2000)
                await asyncio.sleep(ms / 1000)

            elif method == "wait_for_element":
                locator = params.get("locator", "")
                ms = params.get("timeout", 20000)
                if locator:
                    await self._wait_for_element_with_fallback(locator, ms)

            elif method == "wait_for_load":
                await self.page.wait_for_load_state("load", timeout=self.timeout * 1000)

            elif method == "scroll_to_height":
                mode = str(params.get("position") or params.get("scroll_mode") or "").strip().lower()
                height = params.get("height", 0)
                if mode in ("top", "start"):
                    await self.page.evaluate(SCROLL_PAGE_JS, ["top", None])
                elif mode in ("bottom", "end"):
                    await self.page.evaluate(SCROLL_PAGE_JS, ["bottom", None])
                elif mode in ("middle", "center", "mid"):
                    await self.page.evaluate(SCROLL_PAGE_JS, ["middle", None])
                elif mode in ("down", "page_down"):
                    delta = abs(int(height)) if height not in (None, "") else 600
                    info = await self.page.evaluate(SCROLL_PAGE_JS, ["down", delta])
                    if not (info or {}).get("moved"):
                        vp = self.page.viewport_size or {"width": 1280, "height": 720}
                        await self.page.mouse.move(int(vp["width"] / 2), int(vp["height"] / 2))
                        await self.page.mouse.wheel(0, delta)
                elif mode in ("up", "page_up"):
                    delta = abs(int(height)) if height not in (None, "") else 600
                    info = await self.page.evaluate(SCROLL_PAGE_JS, ["up", delta])
                    if not (info or {}).get("moved"):
                        vp = self.page.viewport_size or {"width": 1280, "height": 720}
                        await self.page.mouse.move(int(vp["width"] / 2), int(vp["height"] / 2))
                        await self.page.mouse.wheel(0, -delta)
                else:
                    await self.page.evaluate(SCROLL_PAGE_JS, ["to", int(height or 0)])

            elif method == "scroll_to_element":
                locator = params.get("locator", "")
                if locator:
                    loc = self.page.locator(locator)
                    await loc.first.scroll_into_view_if_needed(timeout=params.get("timeout", 20000))

            elif method == "click_by_text":
                text = params.get("text", "")
                exact = _coerce_bool(params.get("exact", False))
                index = max(int(params.get("index", 1)) - 1, 0)
                if text:
                    loc = self.page.get_by_text(text, exact=exact).nth(index)
                    await loc.click(timeout=params.get("timeout", 20000))

            elif method == "wait_for_element_hidden":
                locator = params.get("locator", "")
                ms = params.get("timeout", 20000)
                if locator:
                    loc = self.page.locator(locator)
                    await loc.first.wait_for(state="hidden", timeout=ms)

            elif method == "wait_for_url_contains":
                fragment = params.get("url", "")
                ms = params.get("timeout", 20000)
                use_regex = _coerce_bool(params.get("use_regex", False))
                if fragment:
                    frag = str(fragment)
                    pattern = re.compile(frag) if use_regex else re.compile(re.escape(frag))
                    await self.page.wait_for_url(pattern, timeout=ms)

            elif method == "switch_to_latest_page":
                pages = self.context.pages
                if pages:
                    self.page = pages[-1]

            elif method == "execute_script":
                script = params.get("script", "")
                if script:
                    await self.page.evaluate(script)

            elif method == "press_key":
                key = params.get("key", "")
                if key:
                    await self.page.keyboard.press(key)

            elif method == "go_back":
                await self.page.go_back(wait_until="domcontentloaded", timeout=self.timeout * 1000)

            else:
                # 不支持的 method，跳过但不报错（如断言、提取等不需要执行）
                logger.debug(f"[SmartPageExplorer] 跳过不需要执行的 method: {method}")
                return True, None

            return True, None

        except Exception as e:
            return False, f"{method} 执行失败: {str(e)}"

    async def _is_page_changed(self, snapshot_before: dict) -> tuple[bool, str]:
        """
        检测页面是否发生显著变化
        返回: (是否变化, 原因)
        """
        # 策略 1：URL 变化
        current_url = self.page.url
        if current_url != snapshot_before["url"]:
            return True, f"url_changed: {snapshot_before['url']} -> {current_url}"

        # 策略 2：等待一小段时间后检测 DOM 变化
        await asyncio.sleep(0.5)
        raw_elements = await self.page.evaluate(EXTRACT_ELEMENTS_JS)
        current_count = len(raw_elements)
        before_count = len(snapshot_before["elements"])

        if before_count == 0:
            ratio = current_count
        else:
            ratio = current_count / before_count

        if ratio > 1.5 or ratio < 0.5:
            return True, f"dom_ratio_changed: {before_count} -> {current_count} (ratio={ratio:.2f})"

        # 策略 3：检测关键导航元素出现（如从登录页到首页，通常会出现导航栏）
        # 简单判断：如果元素列表的前 5 个元素完全不同，认为页面结构变了
        if before_count > 0 and current_count > 0:
            before_ids = {e.get("id", "") for e in snapshot_before["elements"][:5]}
            current_ids = {e.get("id", "") for e in raw_elements[:5]}
            if before_ids and current_ids and not before_ids.intersection(current_ids):
                return True, "dom_structure_changed"

        return False, "no_change"

    async def _take_screenshot(self, round_index: int, step_index: int, reason: str) -> Optional[str]:
        """
        截取当前页面截图
        返回可访问的 URL 路径，如 /static/screenshots/explore/xxx.png
        """
        if not self.page:
            return None
        try:
            filename = f"explore_{datetime.now().strftime('%Y%m%d_%H%M%S')}_r{round_index}_s{step_index}.png"
            filepath = os.path.join(self.screenshots_dir, filename)
            await self.page.screenshot(path=filepath, full_page=False)
            # URL 路径：FastAPI static 挂载在 /static，对应 backend/static
            url_path = f"/static/screenshots/explore/{filename}"
            self.screenshots.append({
                "url": url_path,
                "path": filepath,
                "round": round_index,
                "step": step_index,
                "reason": reason,
            })
            logger.info(f"[SmartPageExplorer] 截图已保存: {url_path}")
            return url_path
        except Exception as e:
            logger.warning(f"[SmartPageExplorer] 截图失败: {e}")
            return None

    def _build_result(self, rounds: int) -> dict:
        """构建返回结果"""
        # 去重 urls_visited
        unique_urls = []
        for url in self.urls_visited:
            if url not in unique_urls:
                unique_urls.append(url)

        return {
            "steps": self.all_steps,
            "rounds": rounds,
            "page_changes": self.page_changes,
            "urls_visited": unique_urls,
            "errors": self.errors,
            "screenshots": [{"url": s["url"], "round": s["round"], "step": s["step"], "reason": s["reason"]} for s in self.screenshots],
        }

    async def _close(self):
        """清理资源"""
        for obj in [self.page, self.context, self.browser]:
            try:
                if obj:
                    await obj.close()
            except Exception:
                pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
