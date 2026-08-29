"""定位助手可选 LLM 增强。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.llm.llm_client import LLMClientFactory
from app.core.platform.encryption import decrypt_value
from app.modules.ai.ai_prompts import PromptManager
from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
from app.modules.ui.locator_assist.validate import is_allowed_locator, normalize_locator, safe_index

logger = logging.getLogger(__name__)

_SCENE = "locator_assist"
_FALLBACK = "locator_heal"


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("模型返回为空")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("模型返回不是 JSON 对象")
    return data


def _text_grounded(locator: str, raw_element: str, intent: str) -> bool:
    blob = f"{raw_element}\n{intent}"
    m = re.search(r"get_by_(?:text|label|placeholder|role)=(?:[^,=]+,\s*)?(.+)$", locator)
    if not m:
        return True
    needle = (m.group(1) or "").strip().strip("\"'")
    if len(needle) < 2:
        return True
    return needle in blob


async def enhance_candidates_with_ai(
    *,
    project_id: Optional[int],
    username: str,
    raw_element: str,
    intent: str,
    element_summary: dict[str, Any],
    rule_candidates: list[dict[str, Any]],
    step_method: str = "",
    ai_config_id: Optional[int] = None,
    suggested_index: int = 1,
) -> tuple[list[dict[str, Any]], bool, str]:
    """返回 (ai_candidates, used, warning)。失败时 used=False。"""
    try:
        try:
            cfg = await resolve_config_for_scene(_SCENE, ai_config_id)
        except Exception:
            cfg = await resolve_config_for_scene(_FALLBACK, ai_config_id)
    except Exception as exc:
        return [], False, f"无可用 AI 配置，已仅用规则：{exc}"

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "ui_locator_assist",
            {
                "step_method": step_method or "click_ele",
                "intent": intent or "（无）",
                "suggested_index": suggested_index,
                "element_summary": json.dumps(element_summary or {}, ensure_ascii=False)[:3000],
                "rule_candidates": json.dumps(
                    [c.get("locator") for c in rule_candidates[:8]],
                    ensure_ascii=False,
                ),
                "raw_element": (raw_element or "")[:4000],
            },
        )
    except Exception as exc:
        logger.warning("locator_assist prompt render failed: %s", exc)
        return [], False, "Prompt 渲染失败，已仅用规则"

    if not system_prompt or not user_prompt:
        return [], False, "Prompt 不可用，已仅用规则"

    api_key = decrypt_value(cfg.api_key) if cfg.api_key else ""
    overrides = await get_scene_llm_overrides(_SCENE)
    if not overrides:
        overrides = await get_scene_llm_overrides(_FALLBACK)
    timeout = int(overrides.get("timeout") or cfg.timeout or 120)
    max_tokens = int(overrides.get("max_tokens") or min(int(cfg.max_tokens or 2000), 2000))
    temperature = overrides.get("temperature", cfg.temperature)
    if temperature is None:
        temperature = 0.3

    client = LLMClientFactory.create(
        provider=cfg.provider,
        api_key=api_key,
        api_base=cfg.api_base,
        model=cfg.model,
        timeout=timeout,
    )

    t0 = time.time()
    try:
        result = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(temperature),
            max_tokens=max_tokens,
            stream=False,
        )
        content = (result or {}).get("content") or ""
        data = _extract_json(content)
        items_raw = data.get("candidates") if isinstance(data, dict) else None
        if not isinstance(items_raw, list):
            items_raw = []
        out: list[dict[str, Any]] = []
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            loc = normalize_locator(str(it.get("locator") or ""))
            if not loc or not is_allowed_locator(loc):
                continue
            conf = it.get("confidence") or "medium"
            reason = (it.get("reason") or "AI 建议").strip()
            if not _text_grounded(loc, raw_element, intent):
                conf = "low"
                reason = f"{reason}（文案未在原料中校验到）".strip()
            out.append({
                "locator": loc,
                "index": safe_index(it.get("index"), suggested_index or 1),
                "source": "ai",
                "confidence": conf,
                "reason": reason,
            })
        await log_ai_usage(
            cfg,
            _SCENE,
            username=username or "",
            project_id=project_id,
            tokens_used=int((result or {}).get("tokens") or 0),
            duration_ms=int((time.time() - t0) * 1000),
            status="success",
            input_summary=(raw_element or "")[:300],
            output_summary=str([c["locator"] for c in out])[:300],
        )
        return out, True, ""
    except Exception as exc:
        logger.warning("locator_assist AI failed: %s", exc)
        try:
            await log_ai_usage(
                cfg,
                _SCENE,
                username=username or "",
                project_id=project_id,
                duration_ms=int((time.time() - t0) * 1000),
                status="failed",
                input_summary=(raw_element or "")[:300],
                output_summary=str(exc)[:300],
            )
        except Exception:
            pass
        return [], False, f"AI 增强失败，已仅用规则：{exc}"
