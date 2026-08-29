"""测试描述 AI 优化（智能浏览器 / UI 用例生成等场景共用）。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.llm.llm_client import LLMClientFactory
from app.core.platform.encryption import decrypt_value
from app.models.ai import AiConfig
from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene

logger = logging.getLogger(__name__)

SCENE_BROWSER_LAB = "browser_lab_task_optimize"
SCENE_UI_CASE = "ui_case_description_optimize"
SCENE_UI_AGENT_SOLIDIFY = "ui_agent_solidify_optimize"

_BROWSER_LAB_FALLBACK = "browser_lab"
_UI_CASE_FALLBACK = "ui_case_generate"
_UI_AGENT_SOLIDIFY_FALLBACK = "ui_case_agent"

_BROWSER_LAB_SYSTEM = """你是 browser-use 智能浏览器任务描述优化专家。
用户会提供起始 URL（平台执行时会自动从该 URL 打开页面）与原始任务描述。
请将描述改写成 **browser-use Agent 可直接执行** 的中文任务说明。

## browser-use 执行特点（通用）
- 单模型：全程一个 LLM，优先通过 DOM **元素 index** 点击/输入；Vision 为可选增强，默认按 DOM 够用写法
- 用 **顺序步骤**（建议 1. 2. 3. 或自然段），每步一个明确动作 + 目标控件/区域
- 菜单导航：沿用用户原文中的 **真实菜单/按钮文案**，不要臆造模块英文名或用户未提到的系统名称
- 可点击路径：写清按钮/链接/输入框的可见文字；图标/头像类写「点右上角用户名/头像区域 → 下拉项名称」
- **禁止**写「截图找按钮」「视觉定位」「反复尝试直到成功」等模糊或无限重试表述
- 列表/表格搜索：通常为 **模糊匹配**；搜不到或结果多条时，写「在表格中逐行核对目标列，点该行操作按钮确认」，**同一搜索操作最多尝试 2 次**
- 布局与稳定性：有搜索/筛选时优先缩小结果；侧栏收起时先展开导航；有层级菜单先父后子
- **禁止**要求 Agent「正则/DOM/脚本查找页面文本」；步骤只用点击、输入、滚动、等待等标准交互
- 登录：若任务含账号密码，逐步写出输入框与登录按钮；若未提供则不要编造
- 结尾写 **成功标准**（怎样算任务完成、需中文总结什么）
- 不要重复写「先访问起始 URL」——平台已配置起始 URL
- 保留用户全部业务目标与关键数据，不增删需求
- 输出纯任务正文，不要 markdown 代码块

## 输出格式（严格 JSON）
{
  "task_text": "优化后的完整任务描述（纯中文）",
  "changes_summary": "简要说明做了哪些优化（1～3 句）"
}
"""

_UI_CASE_SYSTEM = """你是 Web UI 自动化测试描述优化专家。
用户会提供目标页面 URL 与原始「测试描述」，用于 **AI 生成 Playwright 步骤**（单页 / 多轮探索 / Agent 探索）。
请将描述改写成模型与 Runner 可直接理解的中文说明。

## 撰写规范
- 用 **顺序步骤**（1. 2. 3.）或 **「→」串联流程**；关键验证写「→ 预期：…」或单独一句成功标准
- **登录**：若涉及登录，逐步写出账号、密码、登录按钮可见文案；未提供密码/账号则不要编造
- **导航**：沿用用户原文中的 **真实菜单/模块/页面名称**；不同模块须区分清楚（勿把「智能浏览器」与「Web 自动化」等混为一谈）
- **单页模式**：聚焦当前页上的操作与断言，不必写跨页跳转（除非用户明确要求）
- **探索 / Agent 模式**：写完整业务流程（含登录后跳转、进入子模块、搜索、断言）
- **Agent 逐步规划**：每步只做一个动作；填表/搜索用「在 XX 输入框输入 YY」，不要写「先点击输入框再输入」；搜索后写「点搜索/查询按钮或按 Enter」
- 列表/表格：搜索多为模糊匹配；命中多条时写「逐行核对目标列」
- **禁止**模糊表述（「找到按钮」「截图定位」「反复尝试直到成功」）
- 保留用户全部业务目标与关键数据，不增删需求
- 输出纯中文任务正文，不要 markdown 代码块

## 输出格式（严格 JSON）
{
  "task_text": "优化后的完整测试描述（纯中文）",
  "changes_summary": "简要说明做了哪些优化（1～3 句）"
}
"""

_UI_AGENT_SOLIDIFY_SYSTEM = """你是 Browser Lab → UI Agent 固化目标描述优化专家。
用户从智能浏览器任务导入，需将描述改写为 **逐步 snapshot 规划 + Playwright 执行** 可直接遵循的中文目标。

## Agent 固化执行特点
- 每轮只规划**一步**；用无障碍树定位，优先 #id、get_by_role、get_by_placeholder、get_by_label
- **填表/搜索**：写「在账号/密码/搜索框输入 XX」，Agent 会用 fill_value 直接写入；**禁止**写「先点击输入框」
- **登录**：逐步写账号、密码、登录按钮可见文案；未提供凭证则不要编造
- **列表搜索**：输入关键词 → 点「搜索」「查询」或 Enter；命中多条时写逐行核对
- **侧栏菜单**（Element Plus 等）：写完整菜单名，有层级时父菜单 → 子菜单
- **禁止**写入「任务已成功」「最终结论」「✅」等结论型报告或 markdown 标题/表格
- **禁止**要求截图、视觉定位、DOM 脚本、无限重试
- 保留用户全部业务目标；不写「先打开起始 URL」（平台已配置）
- 控制在 **800 字以内**，用 1. 2. 3. 顺序步骤；末尾一句成功标准即可

## 输出格式（严格 JSON）
{
  "task_text": "优化后的 Agent 固化目标描述（纯中文）",
  "changes_summary": "简要说明做了哪些优化（1～3 句）"
}
"""

_SCENE_PROMPTS = {
    SCENE_BROWSER_LAB: (_BROWSER_LAB_SYSTEM, _BROWSER_LAB_FALLBACK),
    SCENE_UI_CASE: (_UI_CASE_SYSTEM, _UI_CASE_FALLBACK),
    SCENE_UI_AGENT_SOLIDIFY: (_UI_AGENT_SOLIDIFY_SYSTEM, _UI_AGENT_SOLIDIFY_FALLBACK),
}


def _extract_json_object(text: str) -> dict[str, Any]:
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


async def _resolve_optimize_config(
    scene: str,
    ai_config_id: Optional[int],
    *,
    fallback_scene: str,
) -> AiConfig:
    if ai_config_id:
        cfg = await AiConfig.get_or_none(id=ai_config_id, is_del=False, is_enabled=True)
        if not cfg:
            raise ValueError("指定的 AI 配置不存在或未启用")
        return cfg
    try:
        return await resolve_config_for_scene(scene, None)
    except Exception:
        return await resolve_config_for_scene(fallback_scene, None)


async def optimize_description_text(
    scene: str,
    *,
    task_text: str,
    start_url: str = "",
    case_name: str = "",
    ai_config_id: Optional[int] = None,
    username: str = "",
    project_id: Optional[int] = None,
    generation_mode: str = "",
) -> dict[str, Any]:
    """优化描述，返回 { task_text, original_task_text, changes_summary, tokens_used }。"""
    if scene not in _SCENE_PROMPTS:
        raise ValueError(f"不支持的优化场景: {scene}")

    system_prompt, fallback_scene = _SCENE_PROMPTS[scene]
    original = (task_text or "").strip()
    if len(original) < 2:
        raise ValueError("描述过短，无法优化")

    config = await _resolve_optimize_config(scene, ai_config_id, fallback_scene=fallback_scene)
    scene_overrides = await get_scene_llm_overrides(scene)
    if not scene_overrides:
        scene_overrides = await get_scene_llm_overrides(fallback_scene)

    user_parts = [
        f"目标页面 URL（平台会自动打开或作为参考，正文无需重复写访问该 URL）：{start_url.strip() or '（未提供）'}"
    ]
    mode = (generation_mode or "").strip().lower()
    if scene == SCENE_UI_CASE and mode in ("single", "explore", "agent", "solidify"):
        mode_labels = {
            "single": "单页面（当前页 DOM 一次性生成 Playwright 步骤）",
            "explore": "多轮探索（执行→再抓 DOM→再生成）",
            "agent": "Agent 探索（逐步 snapshot 规划执行）",
            "solidify": "Browser Lab 导入 · Agent 重新固化（逐步 snapshot 规划）",
        }
        user_parts.append(f"生成模式：{mode_labels[mode]}")
    if scene == SCENE_UI_AGENT_SOLIDIFY:
        user_parts.append("用途：Browser Lab 任务导入后 Agent 重新固化，须逐步真实操作页面")
    if case_name.strip():
        user_parts.append(f"用例名称：{case_name.strip()}")
    user_parts.append(f"原始描述：\n{original}")
    user_prompt = "\n\n".join(user_parts)

    api_key = decrypt_value(config.api_key)
    timeout = int(scene_overrides.get("timeout") or config.timeout or 120)
    max_tokens = int(scene_overrides.get("max_tokens") or min(config.max_tokens or 4096, 4096))
    temperature = scene_overrides.get("temperature", config.temperature)
    if temperature is None:
        temperature = 0.3

    client = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=timeout,
    )

    t0 = time.time()
    result = await client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=float(temperature),
        max_tokens=max_tokens,
        stream=False,
    )
    duration_ms = int((time.time() - t0) * 1000)
    tokens = int(result.get("tokens") or 0)

    try:
        parsed = _extract_json_object(result.get("content") or "")
    except (json.JSONDecodeError, ValueError) as ex:
        logger.warning("[description.optimize] parse failed scene=%s: %s", scene, ex)
        raise ValueError("AI 返回格式无法解析，请重试或更换模型") from ex

    optimized = (parsed.get("task_text") or "").strip()
    if len(optimized) < 2:
        raise ValueError("AI 未返回有效描述")
    if len(optimized) > 4000:
        optimized = optimized[:4000]

    summary = (parsed.get("changes_summary") or "").strip()[:1000]

    try:
        await log_ai_usage(
            config,
            scene,
            username=username,
            project_id=project_id,
            tokens_used=tokens,
            duration_ms=duration_ms,
            status="success",
            input_summary=original[:500],
            output_summary=optimized[:500],
        )
    except Exception as ex:
        logger.warning("[description.optimize] usage log failed: %s", ex)

    return {
        "task_text": optimized,
        "original_task_text": original,
        "changes_summary": summary,
        "tokens_used": tokens,
    }
