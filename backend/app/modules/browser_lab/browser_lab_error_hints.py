"""Browser Lab / browser-use 错误分类与提示（Runner 回调等复用）。"""
from __future__ import annotations

from typing import Any

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
