"""
元素探查：AI 命名元素 / 生成 App 步骤
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import HTTPException

from app.core.ai_prompts import PromptManager
from app.core.ai_usage_log import log_ai_usage
from app.core.app_inspector_service import get_session, load_session_screenshot_bytes
from app.core.functional_case_to_app import normalize_app_steps
from app.routers.ai.generate import _call_llm, _extract_json_array

logger = logging.getLogger(__name__)


async def suggest_inspector_ai(
    *,
    project_id: int,
    user_info: dict,
    ai_config_id: Optional[int],
    vision_config_id: Optional[int],
    session_id: Optional[str],
    node_attributes: dict[str, Any],
    suggested_locator: Optional[dict],
    driver_mode: str,
    intent: str,
    app_id: Optional[str],
    extra_hint: Optional[str],
) -> dict[str, Any]:
    from app.core.ai_scene_config import resolve_config_for_scene

    intent = (intent or "both").strip().lower()
    if intent not in ("name", "steps", "both"):
        raise HTTPException(status_code=400, detail="intent 须为 name / steps / both")

    config = await resolve_config_for_scene("app_case_generate", ai_config_id)
    vision_hint = ""
    if session_id and vision_config_id:
        session = await get_session(session_id)
        if session:
            try:
                from app.core.encryption import decrypt_value
                from app.core.llm_client import LLMClientFactory
                from app.routers.ai.analyze import _build_extra_body

                img_bytes, mime = await load_session_screenshot_bytes(session)
                vconfig = await resolve_config_for_scene("failure_analysis_vision", vision_config_id)
                api_key = decrypt_value(vconfig.api_key)
                vclient = LLMClientFactory.create(
                    provider=vconfig.provider,
                    api_key=api_key,
                    api_base=vconfig.api_base,
                    model=vconfig.model,
                    timeout=max(int(vconfig.timeout or 60), 120),
                )
                if hasattr(vclient, "chat_with_image"):
                    vresp = await vclient.chat_with_image(
                        system_prompt="你是 Android UI 分析助手。",
                        text="请描述当前屏幕主要可点击控件与文案（中文，简洁）。",
                        image_bytes=img_bytes,
                        image_mime=mime or "image/png",
                        temperature=0.3,
                        max_tokens=vconfig.max_tokens,
                        extra_body=_build_extra_body(vconfig) or None,
                    )
                    vision_hint = (vresp.get("content") or "").strip()
            except Exception as exc:
                logger.warning("[app_inspector_ai] vision failed: %s", exc)

    attrs_text = "\n".join(
        f"- {k}: {v}" for k, v in (node_attributes or {}).items() if v not in (None, "", [])
    )
    locator_text = ""
    if isinstance(suggested_locator, dict) and suggested_locator.get("by"):
        locator_text = f'推荐定位器: by={suggested_locator.get("by")}, value={suggested_locator.get("value")}'

    start = time.time()
    try:
        system_prompt, user_prompt = await PromptManager.render(
            "app_inspector_suggest",
            {
                "intent": intent,
                "driver_mode": driver_mode or "hybrid",
                "app_id": app_id or "",
                "attributes": attrs_text or "（无属性）",
                "locator_text": locator_text,
                "vision_hint": vision_hint or "（未使用 Vision）",
                "extra_hint": extra_hint or "",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Prompt 渲染失败: {exc}") from exc

    resp = await _call_llm(system_prompt, user_prompt, config)
    raw = resp.get("content", "")
    tokens = int(resp.get("tokens") or 0)
    duration_ms = int((time.time() - start) * 1000)

    import json
    import re

    data: dict[str, Any] = {}
    json_str = raw.strip()
    m = re.search(r"\{[\s\S]*\}", json_str)
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = {}

    element_name = (data.get("element_name") or data.get("name") or "").strip()
    steps_raw = data.get("steps") or []
    if isinstance(steps_raw, dict):
        steps_raw = [steps_raw]
    steps, errors = normalize_app_steps(steps_raw) if isinstance(steps_raw, list) else ([], [])

    if intent in ("steps", "both") and not steps and not element_name:
        raise HTTPException(status_code=500, detail="AI 未返回有效结果，请重试")

    await log_ai_usage(
        config,
        "app_case_generate",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        input_summary=f"inspector:{intent}",
        output_summary=element_name or f"{len(steps)} steps",
    )

    return {
        "element_name": element_name,
        "steps": steps,
        "errors": errors,
        "suggested_locator": data.get("locator") if isinstance(data.get("locator"), dict) else suggested_locator,
        "tokens_used": tokens,
        "duration_ms": duration_ms,
        "vision_used": bool(vision_hint),
    }
