"""
MCP 式 UI Agent 探索器
逐步：accessibility snapshot → LLM 规划单步 → 执行 → 循环
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from app.core.agent_locator import (
    action_made_progress,
    refine_agent_step_locator,
    structural_fingerprint,
)
from app.core.locator_utils import normalize_locator
from app.core.page_fetcher import SmartPageExplorer, capture_accessibility_snapshot
from app.core.ui_locator_heal import HEALABLE_METHODS

logger = logging.getLogger(__name__)

PlanFunc = Callable[..., Awaitable[dict]]
HealFunc = Callable[..., Awaitable[dict]]

_MAX_REPLAN_PER_INDEX = 3
_DUPLICATE_STUCK_HINT = (
    "刚规划的操作与最近已执行步骤相同（相同 method+locator），禁止重复。"
    "请根据 snapshot 规划下一步；点击按钮必须优先使用 snapshot/DOM 中的 "
    "#id、[data-testid]、get_by_role=button,<完整名称>，勿用 get_by_text 短词。"
)
_NO_PROGRESS_STUCK_HINT = (
    "上一步操作后页面结构未变化（URL/主导航未变），说明定位可能点错或前置条件未满足。"
    "请换用 snapshot 中该控件的 #id 或 get_by_role，勿重复相同 click。"
)


class UiMcpAgentExplorer(SmartPageExplorer):
    """基于无障碍树 snapshot 的逐步 Agent 探索"""

    @staticmethod
    def _step_signature(step: dict) -> str:
        method = (step.get("method") or "").strip()
        params = step.get("params") or {}
        loc = normalize_locator(params.get("locator") if isinstance(params, dict) else "")
        return f"{method}|{loc}"

    @staticmethod
    def _is_duplicate_step(step: dict, executed_steps: list) -> bool:
        sig = UiMcpAgentExplorer._step_signature(step)
        if not sig or sig == "|":
            return False
        method = (step.get("method") or "").strip()
        # 点击类：与历史任一步相同即视为重复（避免 #8~#15 连点登录）
        if method == "click_ele":
            return any(UiMcpAgentExplorer._step_signature(s) == sig for s in executed_steps)
        recent = executed_steps[-5:] if executed_steps else []
        return any(UiMcpAgentExplorer._step_signature(s) == sig for s in recent)

    async def agent_explore(
        self,
        llm_plan_func: PlanFunc,
        max_steps: int = 15,
        heal_func: Optional[HealFunc] = None,
    ) -> dict[str, Any]:
        """
        :param llm_plan_func: async fn(accessibility_snapshot, snapshot_type, description,
            executed_steps, current_url, step_index) -> {done, message?, step?}
        :param heal_func: 可选，步骤失败时调用一次定位器自愈并重试
        """
        agent_log: list[dict[str, Any]] = []
        await self._init_browser()

        try:
            await self.page.goto(
                self.start_url,
                wait_until="domcontentloaded",
                timeout=self.timeout * 1000,
            )
            try:
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(1)

            self.urls_visited.append(self.page.url)
            await self._take_screenshot(
                round_index=0,
                step_index=0,
                reason=f"Agent 开始: {self.page.url}",
            )

            executed_count = 0
            for step_idx in range(1, max_steps + 1):
                snap_text, snap_type = await capture_accessibility_snapshot(self.page)
                current_url = self.page.url

                stuck_hint = ""
                step_committed = False
                task_done = False
                step_failed = False

                for replan in range(_MAX_REPLAN_PER_INDEX):
                    plan = await llm_plan_func(
                        accessibility_snapshot=snap_text,
                        snapshot_type=snap_type,
                        description=self.description,
                        executed_steps=self.all_steps.copy(),
                        current_url=current_url,
                        step_index=step_idx,
                        stuck_hint=stuck_hint,
                    )

                    if plan.get("done"):
                        agent_log.append({
                            "step": step_idx,
                            "done": True,
                            "message": plan.get("message") or "任务完成",
                            "url": current_url,
                            "snapshot_type": snap_type,
                        })
                        logger.info(f"[UiMcpAgent] 第 {step_idx} 步标记完成: {plan.get('message')}")
                        step_committed = True
                        task_done = True
                        break

                    step = plan.get("step")
                    if not step or not isinstance(step, dict):
                        msg = f"第 {step_idx} 步 LLM 未返回有效 step"
                        self.errors.append(msg)
                        agent_log.append({"step": step_idx, "error": msg, "url": current_url})
                        step_committed = True
                        step_failed = True
                        break

                    if self._is_duplicate_step(step, self.all_steps):
                        agent_log.append({
                            "step": step_idx,
                            "replan": replan + 1,
                            "duplicate_skipped": True,
                            "signature": self._step_signature(step),
                            "url": current_url,
                        })
                        stuck_hint = _DUPLICATE_STUCK_HINT
                        logger.warning(
                            "[UiMcpAgent] 第 %s 步重复规划已跳过: %s",
                            step_idx,
                            self._step_signature(step),
                        )
                        continue

                    params = step.get("params")
                    if isinstance(params, dict) and isinstance(params.get("locator"), dict):
                        params["locator"] = self._coerce_locator(params.get("locator"))
                        step["params"] = params

                    dom_elements = await self.extract_interactive_elements()
                    old_loc = normalize_locator((step.get("params") or {}).get("locator"))
                    step = refine_agent_step_locator(step, dom_elements)
                    new_loc = normalize_locator((step.get("params") or {}).get("locator"))
                    if new_loc != old_loc:
                        logger.info("[UiMcpAgent] 定位优选 %s -> %s", old_loc[:50], new_loc[:50])

                    url_before = current_url
                    struct_before = structural_fingerprint(url_before, snap_text)
                    logger.info(
                        "[UiMcpAgent] 执行 step_idx=%s replan=%s method=%s sig=%s",
                        step_idx,
                        replan + 1,
                        step.get("method"),
                        self._step_signature(step),
                    )
                    success, error = await self._execute_step(step)
                    log_entry: dict[str, Any] = {
                        "step": step_idx,
                        "url": current_url,
                        "snapshot_type": snap_type,
                        "planned_method": step.get("method"),
                        "planned_desc": step.get("desc"),
                        "success": success,
                        "replan": replan + 1 if replan else None,
                    }

                    if not success and heal_func:
                        success, error, heal_info = await self._try_heal_and_retry(
                            step=step,
                            error=error or "",
                            page_url=current_url,
                            snap_text=snap_text,
                            snap_type=snap_type,
                            heal_func=heal_func,
                        )
                        if heal_info:
                            log_entry["heal"] = heal_info

                    if not success:
                        log_entry["error"] = error
                        agent_log.append(log_entry)
                        self.errors.append(f"Agent 第 {step_idx} 步执行失败: {error}")
                        shot = await self._take_screenshot(
                            round_index=0,
                            step_index=step_idx,
                            reason=f"Agent 执行失败: {error[:120] if error else ''}",
                        )
                        if shot:
                            log_entry["screenshot"] = shot
                        self.all_steps.append(step)
                        step_committed = True
                        step_failed = True
                        break

                    await asyncio.sleep(0.5)
                    snap_text, snap_type = await capture_accessibility_snapshot(self.page)
                    current_url = self.page.url
                    struct_after = structural_fingerprint(current_url, snap_text)

                    progressed = action_made_progress(
                        method=(step.get("method") or ""),
                        url_before=url_before,
                        url_after=current_url,
                        struct_before=struct_before,
                        struct_after=struct_after,
                    )
                    no_progress = not progressed

                    if no_progress and replan < _MAX_REPLAN_PER_INDEX - 1:
                        agent_log.append({
                            "step": step_idx,
                            "replan": replan + 1,
                            "no_progress_after_action": True,
                            "signature": self._step_signature(step),
                            "struct_before": struct_before[:8],
                            "struct_after": struct_after[:8],
                            "url": current_url,
                        })
                        stuck_hint = _NO_PROGRESS_STUCK_HINT
                        logger.warning(
                            "[UiMcpAgent] 第 %s 步无结构进展 url=%s sig=%s",
                            step_idx,
                            current_url,
                            self._step_signature(step),
                        )
                        continue

                    if no_progress:
                        msg = f"第 {step_idx} 步执行后页面结构无变化（url={current_url}）"
                        self.errors.append(msg)
                        agent_log.append({"step": step_idx, "error": msg, "url": current_url})
                        step_committed = True
                        step_failed = True
                        break

                    self.all_steps.append(step)
                    executed_count += 1
                    agent_log.append(log_entry)
                    step_committed = True

                    if current_url not in self.urls_visited:
                        self.urls_visited.append(current_url)
                    break

                if task_done:
                    break
                if step_failed:
                    break
                if not step_committed:
                    msg = f"第 {step_idx} 步连续 {_MAX_REPLAN_PER_INDEX} 次重复或无进展，已中止"
                    self.errors.append(msg)
                    agent_log.append({"step": step_idx, "error": msg, "url": current_url})
                    break

                await asyncio.sleep(0.4)

            return self._build_agent_result(executed_count, agent_log)

        except Exception as e:
            logger.error(f"[UiMcpAgent] 探索异常: {e}", exc_info=True)
            self.errors.append(f"Agent 探索异常: {str(e)}")
            return self._build_agent_result(0, agent_log)

        finally:
            await self._close()

    async def _try_heal_and_retry(
        self,
        *,
        step: dict,
        error: str,
        page_url: str,
        snap_text: str,
        snap_type: str,
        heal_func: HealFunc,
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """失败时调用一次定位器自愈并重试执行"""
        method = (step.get("method") or "").strip()
        params = step.get("params") or {}
        failed_locator = params.get("locator") if isinstance(params, dict) else ""
        if not failed_locator or method not in HEALABLE_METHODS:
            return False, error, None

        try:
            heal_result = await heal_func(
                method=method,
                failed_locator=str(failed_locator),
                step_desc=step.get("desc") or "",
                error_message=error,
                page_url=page_url,
                accessibility_snapshot=snap_text,
                snapshot_type=snap_type,
            )
        except Exception as e:
            logger.warning(f"[UiMcpAgent] 自愈调用异常: {e}")
            return False, error, None

        if not heal_result.get("success") or not heal_result.get("locator"):
            return False, error, {
                "attempted": True,
                "success": False,
                "reason": heal_result.get("reason") or "自愈未给出新定位器",
            }

        old_locator = str(failed_locator)
        new_locator = heal_result["locator"]
        step["params"]["locator"] = new_locator
        logger.info(f"[UiMcpAgent] 自愈重试: {old_locator[:60]} -> {new_locator[:60]}")

        success, retry_error = await self._execute_step(step)
        heal_info = {
            "attempted": True,
            "success": success,
            "from_locator": old_locator,
            "to_locator": new_locator,
            "reason": heal_result.get("reason") or "",
            "confidence": heal_result.get("confidence"),
        }
        if success:
            return True, None, heal_info
        return False, retry_error, heal_info

    def _build_agent_result(self, executed_count: int, agent_log: list[dict]) -> dict[str, Any]:
        base = self._build_result(rounds=executed_count)
        base["steps"] = dedupe_agent_steps(base.get("steps") or [])
        base["agent_log"] = agent_log
        base["mode"] = "agent_mcp"
        base["executed_steps"] = executed_count
        return base


def dedupe_agent_steps(steps: list) -> list:
    """合并 Agent 输出中连续/重复的点击（兜底）"""
    out: list = []
    seen_click: set[str] = set()
    prev_sig: Optional[str] = None
    for s in steps:
        if not isinstance(s, dict):
            continue
        sig = UiMcpAgentExplorer._step_signature(s)
        if sig and sig == prev_sig:
            continue
        method = (s.get("method") or "").strip()
        if method == "click_ele" and sig and sig in seen_click:
            continue
        if method == "click_ele" and sig:
            seen_click.add(sig)
        out.append(s)
        prev_sig = sig
    if len(out) < len(steps):
        logger.info("[UiMcpAgent] 步骤去重 %s → %s", len(steps), len(out))
    return out
