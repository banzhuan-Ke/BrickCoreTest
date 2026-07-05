"""AI 场景与 LLM 配置绑定"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.ai import AiConfig, AiSceneBinding

# scene -> (label, description)
AI_SCENE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "failure_analysis": ("失败根因分析", "执行记录一键 AI 分析（文本）"),
    "failure_analysis_vision": ("失败分析 · Vision", "UI 失败截图多模态读图"),
    "requirement_case": ("需求 / 功能用例生成", "需求文档、测试点、方案、用例生成"),
    "ui_case_generate": ("UI 步骤生成", "单页 / 多轮探索模式"),
    "ui_case_agent": ("UI Agent 探索", "MCP 式逐步规划执行"),
    "app_case_generate": ("App 步骤生成", "功能用例 / 自然语言生成 App 自动化步骤"),
    "locator_heal": ("定位器自愈", "步骤失败时 AI 修复选择器"),
    "api_case_generate": ("API 用例生成", "基于接口定义生成用例"),
    "mock_data_generate": ("Mock 响应生成", "AI 生成 Mock 接口响应 JSON"),
    "platform_assistant": ("平台内 AI 助手", "看板/各页面的只读问答与项目总结"),
    "report_summary": ("测试报告摘要", "执行报告 AI 摘要与建议"),
    "requirement_test_point": ("需求测试点生成", "从需求文档 AI 提取测试点"),
    "requirement_test_point_case": ("测试点→用例生成", "基于测试点批量生成功能用例"),
    "requirement_test_scheme": ("测试方案生成", "基于测试点生成测试方案文档"),
    "recorder_optimize": ("录制步骤优化", "录制弹窗内 AI 精简步骤并追加断言"),
    "case_steps_optimize": ("用例步骤优化", "用例编辑页 AI 优化步骤并追加断言"),
    "qa_judge": ("问答准确性评判", "知识库问答评测 LLM 打分"),
    "browser_lab": ("智能浏览器", "browser-use 自然语言驱动浏览器演示/探索"),
    "browser_lab_task_optimize": ("智能浏览器 · 任务描述优化", "将自然语言任务改写为 browser-use 可执行描述"),
}

AI_SCENE_GROUPS: list[dict[str, str]] = [
    {"id": "assistant", "label": "平台助手"},
    {"id": "generate", "label": "用例生成"},
    {"id": "analysis", "label": "失败分析"},
    {"id": "vision", "label": "多模态 Vision"},
    {"id": "other", "label": "其他增强"},
]

# scene -> 推荐配置（用于场景绑定引导）
AI_SCENE_RECOMMENDATIONS: dict[str, dict[str, Any]] = {
    "platform_assistant": {
        "group": "assistant",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "偏低温度，便于稳定整理工具 JSON 与 Markdown",
    },
    "requirement_case": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.5～0.7",
        "tip": "生成类场景可适当提高温度",
    },
    "requirement_test_point": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.5～0.7",
        "tip": "测试点提取需要一定创造性",
    },
    "requirement_test_point_case": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.5～0.7",
        "tip": "与需求用例生成共用同一模型即可",
    },
    "requirement_test_scheme": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.5～0.7",
        "tip": "方案生成偏结构化输出",
    },
    "ui_case_generate": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "UI 步骤需严格 JSON，温度不宜过高",
    },
    "ui_case_agent": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "Agent 探索模式与 UI 生成可共用",
    },
    "app_case_generate": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "App 步骤 JSON 输出，建议低温度；可与 UI 生成共用模型",
    },
    "api_case_generate": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "API 用例 JSON 输出，建议低温度",
    },
    "mock_data_generate": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "Mock 响应 JSON，可与 API 用例生成共用模型",
    },
    "recorder_optimize": {
        "group": "other",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "录制后步骤优化需保持步骤结构稳定",
    },
    "case_steps_optimize": {
        "group": "other",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "用例编辑页优化可与录制步骤优化共用同一模型",
    },
    "failure_analysis": {
        "group": "analysis",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.2～0.4",
        "tip": "根因分析偏推理，温度宜低",
    },
    "report_summary": {
        "group": "analysis",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.3～0.5",
        "tip": "报告摘要与失败分析可共用",
    },
    "failure_analysis_vision": {
        "group": "vision",
        "recommended_provider": "qwen",
        "recommended_model": "qwen-vl-max",
        "temperature_hint": "0.2～0.4",
        "tip": "建议绑定 Vision/多模态模型（如 qwen-vl、openchat-vl）；也可手动选择任意已启用配置",
    },
    "locator_heal": {
        "group": "other",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.2～0.4",
        "tip": "定位器修复需精确输出",
    },
    "qa_judge": {
        "group": "analysis",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-chat",
        "temperature_hint": "0.1～0.3",
        "tip": "建议绑定 DeepSeek 文本模型，并在「参数覆盖」中设置 max_tokens≥16384、timeout≥180",
        "default_overrides": {"max_tokens": 32768, "temperature": 0.1, "timeout": 300},
    },
    "browser_lab": {
        "group": "generate",
        "recommended_provider": "openai",
        "recommended_model": "gpt-4o",
        "temperature_hint": "0.2～0.4",
        "tip": "演示/探索型任务：推荐 deepseek-v4-flash（关闭思考模式）或 gpt-4o；DeepSeek v4 须在 AI 配置中关闭「思考模式」才能 function calling；开思考模式仅适合纯探索、成功率较低；Linux 云部署为无头模式",
        "default_overrides": {"max_tokens": 8192, "temperature": 0.3, "timeout": 300},
    },
    "browser_lab_task_optimize": {
        "group": "generate",
        "recommended_provider": "deepseek",
        "recommended_model": "deepseek-v4-flash",
        "temperature_hint": "0.2～0.4",
        "tip": "纯文本改写，推荐 deepseek-v4-flash 或 deepseek-chat；须关闭思考模式；未绑定时回退「智能浏览器」场景模型",
        "default_overrides": {"max_tokens": 4096, "temperature": 0.3, "timeout": 120},
    },
}

SCENE_OVERRIDE_KEYS = frozenset({"max_tokens", "temperature", "timeout", "min_timeout"})


def is_likely_vision_model(model: str) -> bool:
    m = (model or "").lower()
    return "vl" in m or "vision" in m or "gpt-4o" in m


async def _pick_default_config() -> Optional[AiConfig]:
    config = await AiConfig.filter(is_default=True, is_enabled=True, is_del=False).first()
    if not config:
        config = await AiConfig.filter(is_enabled=True, is_del=False).first()
    if not config:
        config = await AiConfig.filter(is_del=False).first()
    return config


async def _get_config_by_id(config_id: int) -> AiConfig:
    config = await AiConfig.get_or_none(id=config_id, is_del=False, is_enabled=True)
    if not config:
        raise HTTPException(status_code=400, detail="指定的 AI 配置不存在或未启用")
    return config


async def resolve_config_for_scene(
    scene: str,
    config_id: Optional[int] = None,
) -> AiConfig:
    """优先显式 config_id，其次场景绑定，最后全局默认。"""
    if config_id:
        return await _get_config_by_id(config_id)

    if scene:
        binding = await AiSceneBinding.get_or_none(scene=scene)
        if binding and binding.config_id:
            bound = await AiConfig.get_or_none(
                id=binding.config_id, is_del=False, is_enabled=True
            )
            if bound:
                return bound

    config = await _pick_default_config()
    if not config:
        label = AI_SCENE_DEFINITIONS.get(scene, (scene, ""))[0]
        raise HTTPException(
            status_code=400,
            detail=(
                f"没有可用的 LLM 配置。请前往 AI 测试 → AI 模型配置："
                f"在「场景绑定」中为「{label}」指定模型，或创建并启用一个全局默认配置。"
            ),
        )
    return config


async def resolve_vision_config(
    config_id: Optional[int] = None,
    scene: str = "failure_analysis_vision",
) -> Optional[AiConfig]:
    """Vision 场景：绑定优先，其次显式 ID，再扫描 Vision 模型。"""
    if config_id:
        return await _get_config_by_id(config_id)

    binding = await AiSceneBinding.get_or_none(scene=scene)
    if binding and binding.config_id:
        cfg = await AiConfig.get_or_none(
            id=binding.config_id, is_del=False, is_enabled=True
        )
        if cfg:
            return cfg

    configs = await AiConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    for cfg in configs:
        if is_likely_vision_model(cfg.model):
            return cfg
    return await _pick_default_config()


async def list_scene_bindings() -> dict[str, Any]:
    rows = {r.scene: r for r in await AiSceneBinding.all()}
    enabled = await AiConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    config_options = [
        {"id": c.id, "name": c.name, "model": c.model, "provider": c.provider, "is_default": c.is_default}
        for c in enabled
    ]
    result: list[dict[str, Any]] = []
    unbound = 0
    for scene, (label, desc) in AI_SCENE_DEFINITIONS.items():
        row = rows.get(scene)
        config_id = row.config_id if row else None
        if not config_id:
            unbound += 1
        rec = AI_SCENE_RECOMMENDATIONS.get(scene, {})
        overrides = {}
        if row and isinstance(row.overrides, dict):
            overrides = {k: row.overrides[k] for k in SCENE_OVERRIDE_KEYS if k in row.overrides}
        result.append({
            "scene": scene,
            "label": label,
            "description": desc,
            "config_id": config_id,
            "overrides": overrides,
            "vision_only": scene == "failure_analysis_vision",
            "group": rec.get("group", "other"),
            "recommended_provider": rec.get("recommended_provider", ""),
            "recommended_model": rec.get("recommended_model", ""),
            "temperature_hint": rec.get("temperature_hint", ""),
            "tip": rec.get("tip", ""),
            "default_overrides": rec.get("default_overrides") or {},
        })
    return {
        "bindings": result,
        "config_options": config_options,
        "groups": AI_SCENE_GROUPS,
        "has_enabled_config": bool(config_options),
        "unbound_count": unbound,
    }


def _pick_config_for_recommendation(
    enabled: list[AiConfig],
    rec: dict[str, Any],
    *,
    vision_only: bool = False,
) -> AiConfig | None:
    if not enabled:
        return None
    preferred_model = (rec.get("recommended_model") or "").strip()
    preferred_provider = (rec.get("recommended_provider") or "").strip()
    candidates = enabled
    if vision_only:
        candidates = [c for c in enabled if is_likely_vision_model(c.model)]
        if not candidates:
            return None
    for c in candidates:
        if preferred_model and c.model == preferred_model:
            return c
    for c in candidates:
        if preferred_provider and c.provider == preferred_provider:
            return c
    default = next((c for c in candidates if c.is_default), None)
    return default or candidates[0]


async def apply_scene_recommendations(username: str) -> dict[str, Any]:
    """将未绑定场景按推荐 provider/model 匹配到已有启用配置。"""
    payload = await list_scene_bindings()
    enabled_rows = await AiConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    enabled = list(enabled_rows)
    applied = 0
    skipped: list[str] = []
    for item in payload["bindings"]:
        if item.get("config_id"):
            continue
        scene = item["scene"]
        rec = AI_SCENE_RECOMMENDATIONS.get(scene, {})
        match = _pick_config_for_recommendation(
            enabled,
            rec,
            vision_only=scene == "failure_analysis_vision",
        )
        if not match:
            skipped.append(item["label"])
            continue
        row = await AiSceneBinding.get_or_none(scene=scene)
        if not row:
            row = AiSceneBinding(scene=scene, config_id=match.id, update_by=username, overrides={})
        else:
            row.config_id = match.id
            row.update_by = username
        if not row.overrides and rec.get("default_overrides"):
            row.overrides = dict(rec["default_overrides"])
        await row.save()
        applied += 1
    result = await list_scene_bindings()
    result["applied_count"] = applied
    result["skipped_labels"] = skipped
    return result


async def save_scene_bindings(items: list[dict[str, Any]], username: str) -> None:
    enabled_ids = set(
        await AiConfig.filter(is_del=False, is_enabled=True).values_list("id", flat=True)
    )
    for item in items:
        scene = (item.get("scene") or "").strip()
        if scene not in AI_SCENE_DEFINITIONS:
            raise HTTPException(status_code=400, detail=f"未知场景: {scene}")
        config_id = item.get("config_id")
        raw_overrides = item.get("overrides") or {}
        overrides = {}
        if isinstance(raw_overrides, dict):
            for k in SCENE_OVERRIDE_KEYS:
                if k in raw_overrides and raw_overrides[k] is not None:
                    overrides[k] = raw_overrides[k]
        if config_id is not None:
            if config_id not in enabled_ids:
                raise HTTPException(status_code=400, detail=f"场景 {scene} 绑定的配置无效或未启用")

        row = await AiSceneBinding.get_or_none(scene=scene)
        if config_id is None:
            if row:
                await row.delete()
            continue
        if not row:
            row = AiSceneBinding(
                scene=scene, config_id=config_id, overrides=overrides, update_by=username
            )
        else:
            row.config_id = config_id
            row.overrides = overrides
            row.update_by = username
        await row.save()


async def get_scene_llm_overrides(scene: str) -> dict[str, Any]:
    """读取场景绑定的 LLM 参数覆盖（max_tokens / temperature / timeout / min_timeout）。"""
    row = await AiSceneBinding.get_or_none(scene=scene)
    if not row or not isinstance(row.overrides, dict):
        return {}
    return {k: row.overrides[k] for k in SCENE_OVERRIDE_KEYS if k in row.overrides and row.overrides[k] is not None}
