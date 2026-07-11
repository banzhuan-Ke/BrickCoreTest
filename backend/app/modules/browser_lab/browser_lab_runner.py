"""browser-use 智能浏览器任务执行器（Linux 云部署默认无头 + 截图流）。"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.platform import config as settings
from app.core.llm.ai_usage_log import log_ai_usage
from app.modules.ai.browser_use_llm import browser_use_supports_vision, build_browser_use_llm
from app.models.ai import BrowserLabCase, BrowserLabTask

logger = logging.getLogger(__name__)

_run_semaphore = asyncio.Semaphore(max(1, settings.BROWSER_LAB_MAX_CONCURRENT))
_stop_flags: dict[int, bool] = {}


def request_stop(task_id: int) -> None:
    _stop_flags[task_id] = True


def _should_stop(task_id: int) -> bool:
    return _stop_flags.get(task_id, False)


def _extract_tokens_from_history(history: Any) -> int:
    """从 browser-use AgentHistoryList.usage 提取总 Token。"""
    if history is None:
        return 0
    usage = getattr(history, "usage", None)
    if not usage:
        return 0
    total = int(getattr(usage, "total_tokens", 0) or 0)
    if total:
        return total
    prompt = int(getattr(usage, "total_prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "total_completion_tokens", 0) or 0)
    return prompt + completion


_CDP_SCREENSHOT_MARKERS = (
    "capturescreenshot",
    "internal error",
    "-32603",
    "clean screenshot",
    "screenshot failed",
    "screenshotwatchdog",
    "domwatchdog",
    "timeout error",
    "browser state",
)

# LLM/API 不可用时不应重启浏览器续跑（否则会反复拉起 Chrome，徒增 CPU/内存）
_LLM_INFRA_MARKERS = (
    "connection error",
    "connect error",
    "connection refused",
    "connection reset",
    "name or service not known",
    "failed to establish a new connection",
    "modelprovidererror",
    "api key",
    "unauthorized",
    "401",
    "403",
    "429",
    "rate limit",
    "invalid_request_error",
    "error code: 400",
)

# 模型不支持 Vision 时 browser-use 仍会发 image_url，须视为 LLM 配置问题而非 CDP 截图失败
_VISION_API_REJECTION_MARKERS = (
    "image_url",
    "expected `text`",
    "expected text",
    "deserialize the json body",
    "does not support image",
    "multimodal",
)


def _text_indicates_cdp_screenshot_failure(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _CDP_SCREENSHOT_MARKERS)


def _text_indicates_vision_api_rejection(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _VISION_API_REJECTION_MARKERS)


def _text_indicates_llm_infra_failure(text: str) -> bool:
    t = (text or "").lower()
    if _text_indicates_vision_api_rejection(t):
        return True
    return any(m in t for m in _LLM_INFRA_MARKERS)


def _format_browser_lab_error_message(raw: str, *, use_vision: bool) -> str:
    """为常见 LLM 错误附加可操作提示。"""
    msg = (raw or "").strip()[:4000]
    if use_vision and _text_indicates_vision_api_rejection(msg):
        hint = (
            "当前模型/API 不支持 Vision 截图（messages 中的 image_url 被拒绝）。"
            "请在执行选项关闭「Vision 截图理解」，或绑定支持多模态的模型（如 gpt-4o、qwen-vl）。"
        )
        if hint not in msg:
            return f"{msg}\n\n{hint}"[:4000]
    return msg


def _should_restart_browser_after_run(history: Any, exc: BaseException | None = None) -> bool:
    """判断是否为 CDP/截图类失败，适合重启 browser session 后续跑。"""
    if exc is not None:
        msg = str(exc)
        if _text_indicates_llm_infra_failure(msg):
            return False
        if _text_indicates_cdp_screenshot_failure(msg):
            return True
    if history is None:
        return False
    if history.is_successful() is True:
        return False
    if history.is_done() and history.is_successful() is not False:
        return False

    for h in getattr(history, "history", []) or []:
        for result in getattr(h, "result", []) or []:
            err = getattr(result, "error", None)
            if not err:
                continue
            msg = str(err)
            if _text_indicates_llm_infra_failure(msg):
                return False
            if _text_indicates_cdp_screenshot_failure(msg):
                return True

    # 连续失败停止且无 done：日志里常见 captureScreenshot Internal error 但 error 字段为空
    if not history.is_done() and history.number_of_steps() >= 2:
        tail = (history.history or [])[-4:]
        tail_errors = [
            str(getattr(r, "error", "") or "")
            for h in tail
            for r in (h.result or [])
            if getattr(r, "error", None)
        ]
        if tail_errors and all(_text_indicates_llm_infra_failure(e) for e in tail_errors):
            return False
        blank_failures = sum(1 for h in tail if h.model_output is None)
        error_failures = len(tail_errors)
        if blank_failures >= 2 or error_failures >= 2:
            return True
    return False


def _merge_histories(histories: list[Any]) -> Any:
    """合并多段 Agent 运行的 token 统计，返回最后一段 history 作为主结果。"""
    if not histories:
        return None
    if len(histories) == 1:
        return histories[0]
    last = histories[-1]
    prompt = completion = total = 0
    for h in histories:
        usage = getattr(h, "usage", None)
        if not usage:
            continue
        prompt += int(getattr(usage, "total_prompt_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
        completion += int(
            getattr(usage, "total_completion_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        )
        total += int(getattr(usage, "total_tokens", 0) or 0)
    if total <= 0:
        total = prompt + completion
    try:
        usage_obj = getattr(last, "usage", None)
        if usage_obj is not None:
            if hasattr(usage_obj, "total_prompt_tokens"):
                usage_obj.total_prompt_tokens = prompt
                usage_obj.total_completion_tokens = completion
                usage_obj.total_tokens = total
            elif hasattr(usage_obj, "prompt_tokens"):
                usage_obj.prompt_tokens = prompt
                usage_obj.completion_tokens = completion
                usage_obj.total_tokens = total
    except Exception:
        pass
    return last


def _build_resume_task_text(
    base_task: str,
    *,
    restart_index: int,
    resume_url: str,
    recent_steps: list[dict[str, Any]],
    last_memory: str,
) -> str:
    lines = [
        base_task,
        "",
        f"【续跑-第{restart_index}次浏览器重启】上次因页面截图(CDP)异常中断，浏览器已重新启动。",
        f"请先导航到：{resume_url}",
        "以下进度已完成，请勿重复，从下一步继续：",
    ]
    for s in recent_steps:
        goal = (s.get("next_goal") or "").strip()
        if goal:
            lines.append(f"- Step {s.get('index')}: {goal[:200]}")
    if last_memory.strip():
        lines.append(f"上次 memory 摘要：{last_memory.strip()[:600]}")
    lines.append("优先点击元素 index 继续任务，不要连续 wait/截图。")
    return "\n".join(lines)


def _recent_step_events(step_log: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    steps = [e for e in step_log if e.get("type") == "step" and int(e.get("index") or 0) > 0]
    return steps[-limit:]


def _action_fingerprint(actions: list) -> str:
    """归一化一步内的操作序列，用于检测重复重试。"""
    parts: list[str] = []
    for act in actions:
        if not isinstance(act, dict):
            parts.append(str(act)[:40])
            continue
        for name, payload in act.items():
            if not isinstance(payload, dict):
                parts.append(name)
                continue
            if name == "input":
                parts.append(f"input:{str(payload.get('text', ''))[:24]}")
            elif name == "click":
                parts.append(f"click:{payload.get('index')}")
            elif name == "send_keys":
                parts.append(f"keys:{str(payload.get('keys', ''))[:16]}")
            elif name == "evaluate":
                parts.append("evaluate")
            elif name == "wait":
                parts.append("wait")
            else:
                parts.append(name)
    return "|".join(parts)


def _goal_indicates_search_retry(goal: str) -> bool:
    g = (goal or "").lower()
    keys = (
        "搜索",
        "查询",
        "重新输入",
        "清空搜索",
        "search",
        "retry",
        "再次",
        "重新尝试",
        "触发搜索",
    )
    return any(k in g for k in keys)


def _detect_stagnation_stop(stagnation: dict[str, Any], *, max_repeat: int) -> str | None:
    """返回自动停止原因；无则 None。"""
    if stagnation.get("wait_streak", 0) >= max_repeat:
        return f"连续 {max_repeat} 步仅 wait/截图无进展，已自动停止"

    goals = stagnation.get("recent_goals") or []
    if len(goals) >= max_repeat and goals[-1] and len(set(goals[-max_repeat:])) == 1:
        return f"连续 {max_repeat} 步目标重复，已自动停止"

    fps = stagnation.get("recent_fingerprints") or []
    if len(fps) >= max_repeat and fps[-1]:
        tail = fps[-max_repeat:]
        if len(set(tail)) == 1:
            return f"同一操作已连续重试 {max_repeat} 次，已自动停止"

    search_goals = [g for g in goals[-max_repeat:] if _goal_indicates_search_retry(g)]
    if len(search_goals) >= max_repeat:
        return f"搜索/查询已重复 {max_repeat} 次仍无进展，已自动停止"

    return None


def _resolve_browser_restart_limits(cfg: dict[str, Any]) -> int:
    """从任务配置解析 CDP 续跑次数；0 表示不续跑。"""
    if not bool(cfg.get("enable_browser_restart", True)):
        return 0
    cap = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP)
    default_n = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS)
    n = int(cfg.get("max_browser_restarts", default_n))
    return min(max(0, n), cap)


def _resolve_max_repeat_steps(cfg: dict[str, Any]) -> int:
    """从任务配置解析重复操作上限。"""
    cap = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS_CAP)
    default_n = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS)
    n = int(cfg.get("max_repeat_steps", default_n))
    return min(max(2, n), cap)


def _resolve_browser_lab_timeouts(config, scene_overrides: dict | None = None) -> tuple[int, int]:
    """返回 (llm_timeout, step_timeout)。优先场景参数覆盖，其次模型配置 timeout。"""
    overrides = scene_overrides or {}
    base_timeout = overrides.get("timeout") or config.timeout or 180
    llm_timeout = max(120, int(base_timeout))
    step_timeout = max(
        settings.BROWSER_LAB_STEP_TIMEOUT,
        llm_timeout + 90,
    )
    return llm_timeout, step_timeout


def _task_dir(task_id: int) -> Path:
    root = Path(settings.BROWSER_LAB_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(task_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _append_step_event(task_id: int, event: dict[str, Any]) -> None:
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        return
    log = list(task.step_log or [])
    log.append(event)
    task.step_log = log
    task.steps_count = len([e for e in log if e.get("type") == "step"])
    await task.save(update_fields=["step_log", "steps_count"])


async def run_browser_lab_task(task_id: int, username: str = "") -> None:
    """后台执行 browser-use Agent。"""
    async with _run_semaphore:
        task = await BrowserLabTask.get_or_none(id=task_id)
        if not task:
            return

        from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene

        ai_config_id = (task.config_json or {}).get("ai_config_id")
        try:
            config = await resolve_config_for_scene("browser_lab", ai_config_id)
            scene_overrides = await get_scene_llm_overrides("browser_lab")
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.finished_at = datetime.now(timezone.utc)
            await task.save()
            await _append_step_event(task_id, {"type": "error", "message": task.error_message or "配置错误"})
            return

        cfg = task.config_json or {}
        max_steps = int(cfg.get("max_steps") or settings.BROWSER_LAB_DEFAULT_MAX_STEPS)
        max_steps = min(max_steps, settings.BROWSER_LAB_MAX_STEPS_CAP)
        use_vision = bool(cfg.get("use_vision", True)) and browser_use_supports_vision(config)
        generate_gif = bool(cfg.get("generate_gif", True))

        if _should_stop(task_id):
            task.status = "stopped"
            task.error_message = "用户已停止"
            task.finished_at = datetime.now(timezone.utc)
            await task.save()
            await _append_step_event(
                task_id,
                {"type": "done", "status": "stopped", "summary": "用户已停止"},
            )
            _stop_flags.pop(task_id, None)
            return

        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        task.ai_config_id = config.id
        await task.save(update_fields=["status", "started_at", "ai_config_id"])

        work_dir = _task_dir(task_id)
        gif_path = work_dir / "replay.gif"

        try:
            from app.modules.browser_lab.browser_lab_gif_patch import apply_browser_use_gif_cjk_patch

            apply_browser_use_gif_cjk_patch()
            from browser_use import Agent
            from browser_use.browser.profile import BrowserProfile
        except ImportError:
            task.status = "failed"
            task.error_message = (
                "未安装 browser-use。请在 Backend 容器执行: pip install browser-use && playwright install chromium"
            )
            task.finished_at = datetime.now(timezone.utc)
            await task.save()
            await _append_step_event(
                task_id,
                {"type": "error", "message": task.error_message or "启动失败"},
            )
            return

        llm = build_browser_use_llm(config)
        max_repeat_steps = _resolve_max_repeat_steps(cfg)
        max_llm_failures = max(1, int(settings.BROWSER_LAB_MAX_LLM_FAILURES))
        anti_loop_hint = (
            "优先通过交互元素列表中的 index 点击，不要在同一页面连续两次以上只做 wait/截图而无进展。"
            "若按钮（如「控制台」）不在元素列表中，可点击右上角用户名/头像区域或直接导航，勿反复等待。"
            f"同一操作（如重复搜索、重复点击同一按钮）最多尝试 {max_repeat_steps - 1} 次，"
            "无进展应换策略（如直接查看表格各行、点编辑/记录）或总结失败原因，勿无限重试。"
            "列表搜索为模糊匹配（名称/任务/URL），命中多条时逐行核对用例名称。"
        )
        full_task = (
            f"从 {task.start_url} 开始执行。任务：{task.task_text} "
            f"{anti_loop_hint} "
            "完成后用中文总结执行结果。"
        )
        extend_system_message = (
            "请始终使用简体中文填写 next_goal、memory、thinking 及最终总结；"
            "页面上的中文按钮/菜单名称保持原样。"
            f"禁止对同一失败操作机械重复超过 {max_repeat_steps} 次；"
            "宽表格操作列不在视口内时，对表格或列表的 scroll 容器横向 scroll，勿只对 window scroll；"
            "行内操作可能在下拉菜单中，先点「更多」「⋯」等入口再点目标项；"
            "导航收起时先点展开/菜单切换按钮；"
            "表格单元格文本若为空，可读 title 属性或点行内操作按钮查看。"
        )

        stagnation: dict[str, Any] = {
            "recent_goals": [],
            "wait_streak": 0,
            "recent_fingerprints": [],
            "stop_reason": "",
        }

        def _action_names(actions: list) -> list[str]:
            names: list[str] = []
            for act in actions:
                if isinstance(act, dict):
                    names.extend(act.keys())
                else:
                    names.append(str(act))
            return names

        async def on_step(
            browser_state: Any,
            model_output: Any,
            step_number: int,
        ) -> None:
            if _should_stop(task_id):
                return

            thinking = getattr(model_output, "thinking", None) or ""
            next_goal = getattr(model_output, "next_goal", None) or ""
            memory = getattr(model_output, "memory", None) or ""
            actions = []
            for act in getattr(model_output, "action", []) or []:
                try:
                    actions.append(act.model_dump(exclude_none=True))
                except Exception:
                    actions.append(str(act))

            goal_key = (next_goal or "").strip().lower()[:120]
            stagnation["recent_goals"].append(goal_key)
            if len(stagnation["recent_goals"]) > 8:
                stagnation["recent_goals"].pop(0)

            action_names = _action_names(actions)
            fp = _action_fingerprint(actions)
            if fp:
                stagnation["recent_fingerprints"].append(fp)
                if len(stagnation["recent_fingerprints"]) > 8:
                    stagnation["recent_fingerprints"].pop(0)

            wait_only = not action_names or action_names == ["wait"]
            vision_stall = any(
                k in goal_key
                for k in (
                    "screenshot",
                    "visually locate",
                    "visual inspection",
                    "截图",
                    "视觉定位",
                    "视觉检查",
                )
            )
            if wait_only and vision_stall:
                stagnation["wait_streak"] += 1
            else:
                stagnation["wait_streak"] = 0

            stop_reason = _detect_stagnation_stop(stagnation, max_repeat=max_repeat_steps)
            if stop_reason:
                logger.warning(
                    "[browser_lab] task %s stagnation at step %s: %s",
                    task_id,
                    step_number,
                    stop_reason,
                )
                stagnation["stop_reason"] = stop_reason
                request_stop(task_id)

            screenshot_b64 = getattr(browser_state, "screenshot", None)
            screenshot_file = None
            if screenshot_b64:
                try:
                    raw = base64.b64decode(screenshot_b64)
                    screenshot_file = f"step_{step_number:03d}.jpg"
                    (work_dir / screenshot_file).write_bytes(raw)
                except Exception as ex:
                    logger.warning("[browser_lab] screenshot save failed: %s", ex)
                    screenshot_file = None

            await _append_step_event(
                task_id,
                {
                    "type": "step",
                    "index": step_number,
                    "url": getattr(browser_state, "url", "") or "",
                    "title": getattr(browser_state, "title", "") or "",
                    "thinking": (thinking or "")[:2000],
                    "next_goal": (next_goal or "")[:1000],
                    "memory": (memory or "")[:1000],
                    "actions": actions[:5],
                    "screenshot_file": screenshot_file,
                },
            )

        async def should_stop() -> bool:
            return _should_stop(task_id)

        llm_timeout, step_timeout = _resolve_browser_lab_timeouts(config, scene_overrides)
        viewport_w = max(800, settings.BROWSER_LAB_VIEWPORT_WIDTH)
        viewport_h = max(600, settings.BROWSER_LAB_VIEWPORT_HEIGHT)
        logger.info(
            "[browser_lab] task %s model=%s(%s) timeouts: llm=%ss step=%ss viewport=%sx%s "
            "(config_timeout=%s scene_override_timeout=%s)",
            task_id,
            config.name,
            config.model,
            llm_timeout,
            step_timeout,
            viewport_w,
            viewport_h,
            config.timeout,
            scene_overrides.get("timeout"),
        )

        # 云服务器常无法访问 Chrome Web Store，默认扩展下载会长时间卡住
        browser_profile = BrowserProfile(
            headless=True,
            disable_security=True,
            enable_default_extensions=False,
            captcha_solver=False,
            window_size={"width": viewport_w, "height": viewport_h},
        )

        await _append_step_event(
            task_id,
            {
                "type": "step",
                "index": 0,
                "url": task.start_url,
                "next_goal": (
                    f"正在启动无头浏览器（模型 {config.name}，单步超时 {step_timeout}s）…"
                ),
                "thinking": "",
                "memory": "",
                "actions": [],
            },
        )

        if _should_stop(task_id):
            task = await BrowserLabTask.get(id=task_id)
            task.status = "stopped"
            task.error_message = "用户已停止"
            task.finished_at = datetime.now(timezone.utc)
            await task.save()
            await _append_step_event(
                task_id,
                {"type": "done", "status": "stopped", "summary": "用户已停止"},
            )
            _stop_flags.pop(task_id, None)
            return

        base_task_text = full_task
        current_task_text = full_task
        histories: list[Any] = []
        steps_completed = 0
        max_restarts = _resolve_browser_restart_limits(cfg)
        restart_count = 0
        fatal_exc: Exception | None = None

        while True:
            if _should_stop(task_id):
                break
            remaining_steps = max_steps - steps_completed
            if remaining_steps <= 0:
                break

            is_final_attempt = restart_count >= max_restarts
            # CDP 续跑开启时首轮不会走到 is_final_attempt，内联 GIF 仅在无续跑或已达续跑上限时启用；
            # 其余情况在任务结束后由 ensure_replay_gif 补生成。
            enable_gif = bool(generate_gif and (max_restarts == 0 or is_final_attempt))
            resume_url_for_run: str | None = None
            if restart_count > 0:
                fresh_nav = await BrowserLabTask.get(id=task_id)
                recent_nav = _recent_step_events(list(fresh_nav.step_log or []))
                resume_url_for_run = (recent_nav[-1].get("url") if recent_nav else None) or task.start_url

            agent = Agent(
                task=current_task_text,
                llm=llm,
                browser_profile=browser_profile,
                use_vision=use_vision,
                generate_gif=str(gif_path) if enable_gif else False,
                extend_system_message=extend_system_message,
                register_new_step_callback=on_step,
                register_should_stop_callback=should_stop,
                calculate_cost=True,
                directly_open_url=restart_count == 0,
                initial_actions=(
                    [{"navigate": {"url": resume_url_for_run, "new_tab": False}}]
                    if resume_url_for_run
                    else None
                ),
                max_failures=max_llm_failures,
                step_timeout=step_timeout,
                llm_timeout=llm_timeout,
                loop_detection_enabled=True,
                loop_detection_window=12,
            )

            segment_history = None
            segment_exc: Exception | None = None
            try:
                segment_history = await agent.run(max_steps=remaining_steps)
            except Exception as ex:
                segment_exc = ex
                logger.exception(
                    "[browser_lab] task %s agent segment failed (attempt %s)",
                    task_id,
                    restart_count + 1,
                )

            if segment_history is not None:
                histories.append(segment_history)
                steps_completed += int(segment_history.number_of_steps() or 0)

            if _should_stop(task_id):
                break
            if segment_history is not None and segment_history.is_successful() is True:
                break

            should_restart = (
                max_restarts > 0
                and restart_count < max_restarts
                and _should_restart_browser_after_run(segment_history, segment_exc)
            )
            if not should_restart:
                if segment_exc is not None and segment_history is None:
                    fatal_exc = segment_exc
                break

            restart_count += 1
            logger.warning(
                "[browser_lab] task %s CDP/screenshot failure, restarting browser session (%s/%s)",
                task_id,
                restart_count,
                max_restarts,
            )

            fresh = await BrowserLabTask.get(id=task_id)
            recent = _recent_step_events(list(fresh.step_log or []))
            resume_url = (recent[-1].get("url") if recent else None) or task.start_url
            last_memory = (recent[-1].get("memory") if recent else None) or ""

            await _append_step_event(
                task_id,
                {
                    "type": "step",
                    "index": steps_completed,
                    "url": resume_url,
                    "next_goal": (
                        f"检测到 CDP 截图异常，已重启浏览器并续跑（{restart_count}/{max_restarts}）"
                    ),
                    "thinking": "",
                    "memory": last_memory[:500],
                    "actions": [],
                },
            )

            current_task_text = _build_resume_task_text(
                base_task_text,
                restart_index=restart_count,
                resume_url=resume_url,
                recent_steps=recent,
                last_memory=last_memory,
            )
            stagnation["recent_goals"].clear()
            stagnation["wait_streak"] = 0
            stagnation["recent_fingerprints"].clear()
            stagnation["stop_reason"] = ""
            await asyncio.sleep(2)

        history = _merge_histories(histories)

        if generate_gif and history is not None and not gif_path.exists():
            from app.modules.browser_lab.browser_lab_gif_patch import ensure_replay_gif

            ensure_replay_gif(base_task_text or task.task_text or "", history, gif_path)

        if fatal_exc is not None and history is None:
            task = await BrowserLabTask.get(id=task_id)
            if _should_stop(task_id):
                task.status = "stopped"
                task.error_message = "用户已停止"
            else:
                task.status = "failed"
                task.error_message = _format_browser_lab_error_message(
                    str(fatal_exc), use_vision=use_vision
                )
            task.finished_at = datetime.now(timezone.utc)
            await task.save()
            await _append_step_event(
                task_id,
                {"type": "error", "message": task.error_message or "执行失败"},
            )
            _stop_flags.pop(task_id, None)
            return

        task = await BrowserLabTask.get(id=task_id)
        summary = ""
        error_msg = ""
        if history is not None:
            try:
                summary = history.final_result() or ""
            except Exception:
                summary = ""
            if not summary:
                try:
                    if history.is_successful():
                        summary = "任务已完成"
                    elif history.has_errors():
                        errs = [e for e in history.errors() if e]
                        error_msg = errs[-1] if errs else "执行失败"
                        summary = error_msg
                except Exception:
                    summary = "执行结束"

        if _should_stop(task_id):
            task.status = "stopped"
            auto_reason = (stagnation.get("stop_reason") or "").strip()
            if auto_reason:
                task.error_message = auto_reason
                task.result_summary = auto_reason
            else:
                task.error_message = "用户已停止"
                task.result_summary = "用户已停止"
        elif history is not None and history.has_errors() and history.is_successful() is not True:
            task.status = "failed"
            task.error_message = _format_browser_lab_error_message(
                error_msg or summary or "执行失败", use_vision=use_vision
            )
            task.result_summary = (summary or task.error_message)[:8000]
        else:
            task.status = "done"
            task.result_summary = (summary or "执行结束")[:8000]

        if restart_count > 0:
            note = f"（曾因 CDP 截图异常自动重启浏览器续跑 {restart_count} 次）"
            task.result_summary = ((task.result_summary or "") + note)[:8000]

        if gif_path.exists():
            task.gif_path = f"browser_lab/{task_id}/replay.gif"

        tokens = _extract_tokens_from_history(history)
        task.tokens_used = tokens
        if tokens:
            logger.info("[browser_lab] task %s tokens_used=%s", task_id, tokens)
        task.finished_at = datetime.now(timezone.utc)
        await task.save()

        if task.case_id:
            case = await BrowserLabCase.get_or_none(id=task.case_id, is_del=False)
            if case:
                case.run_count = int(case.run_count or 0) + 1
                case.last_run_at = task.finished_at
                case.last_status = task.status
                await case.save(update_fields=["run_count", "last_run_at", "last_status"])

        await _append_step_event(
            task_id,
            {
                "type": "done",
                "status": task.status,
                "summary": task.result_summary or "",
                "error_message": task.error_message or "",
                "tokens_used": tokens,
                "gif_path": task.gif_path,
                "gif_url": f"/static/{task.gif_path}" if task.gif_path else None,
            },
        )

        try:
            duration_ms = 0
            if task.started_at and task.finished_at:
                duration_ms = int((task.finished_at - task.started_at).total_seconds() * 1000)
            await log_ai_usage(
                config,
                "browser_lab",
                username=username,
                project_id=task.project_id,
                tokens_used=tokens,
                duration_ms=duration_ms,
                status="success" if task.status == "done" else "failed",
                input_summary=(task.task_text or "")[:500],
                output_summary=(task.result_summary or "")[:500],
                task_id=task_id,
                steps=task.steps_count,
            )
        except Exception as ex:
            logger.warning("[browser_lab] usage log failed: %s", ex)

        _stop_flags.pop(task_id, None)


def ensure_browser_lab_dir() -> None:
    os.makedirs(settings.BROWSER_LAB_DIR, exist_ok=True)
