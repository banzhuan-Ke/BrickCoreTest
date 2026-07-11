"""智能浏览器任务描述 AI 优化（browser-use 可执行性）。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
from app.core.llm.ai_usage_log import log_ai_usage
from app.core.platform.encryption import decrypt_value
from app.core.llm.llm_client import LLMClientFactory
from app.models.ai import AiConfig

logger = logging.getLogger(__name__)

_SCENE = "browser_lab_task_optimize"
_FALLBACK_SCENE = "browser_lab"

_SYSTEM_PROMPT = """你是 browser-use 智能浏览器任务描述优化专家。
用户会提供起始 URL（平台执行时会自动从该 URL 打开页面）与原始任务描述。
请将描述改写成 **browser-use Agent 可直接执行** 的中文任务说明。

## browser-use 执行特点（通用）
- 单模型：全程一个 LLM，优先通过 DOM **元素 index** 点击/输入；Vision 为可选增强，默认按 DOM 够用写法
- 用 **顺序步骤**（建议 1. 2. 3. 或自然段），每步一个明确动作 + 目标控件/区域
- 菜单导航：沿用用户原文中的 **真实菜单/按钮文案**，不要臆造模块英文名或用户未提到的系统名称
- 可点击路径：写清按钮/链接/输入框的可见文字；图标/头像类写「点右上角用户名/头像区域 → 下拉项名称」
- **禁止**写「截图找按钮」「视觉定位」「反复尝试直到成功」等模糊或无限重试表述
- 列表/表格搜索：通常为 **模糊匹配**；搜不到或结果多条时，写「在表格中逐行核对目标列，点该行操作按钮（如查看/编辑/详情）确认」，**同一搜索操作最多尝试 2 次**
- 表格单元格文字过短可能在元素列表中不完整：可写「点目标行的操作列按钮确认」而非死磕搜索
- 布局与稳定性（通用，勿写死特定站点结构）：
  - 执行视口宽度有限（默认约 1920），极宽表格/列表的「操作」列仍可能在视口外
  - 有搜索/筛选时优先写「先搜索或筛选缩小结果，再操作目标行」，减少横向滚动
  - 操作按钮不可见时写「在表格或列表的可滚动区域内横向滚动，直到目标按钮可见」，勿只写「滚动页面」
  - 行内操作可能在「更多」「⋯」等下拉中：沿用用户原文里的真实按钮/菜单文案，按「点入口 → 点菜单项」写，勿臆造独立按钮
  - 侧栏/主导航收起导致菜单文字不可见：写「若导航已收起，先点侧栏或顶部的展开/菜单切换按钮，再点目标菜单」
  - 有层级菜单：先展开父级，再点子菜单
- **禁止**要求 Agent「正则/DOM/脚本查找页面文本」；步骤只用点击、输入、滚动、等待等标准交互
- 登录：若任务含账号密码，逐步写出输入框与登录按钮；若未提供密码/账号则不要编造
- 续跑场景：任务宜保留登录信息（CDP 续跑会丢失 Cookie）
- 结尾写 **成功标准**（怎样算任务完成、需中文总结什么）
- 不要重复写「先访问起始 URL」——平台已配置起始 URL；任务正文从该页面上要做的操作写起即可
- 保留用户全部业务目标与关键数据，不增删需求
- 输出纯任务正文，不要 markdown 代码块，不要解释 browser-use 原理

## 输出格式（严格 JSON）
{
  "task_text": "优化后的完整任务描述（纯中文）",
  "changes_summary": "简要说明做了哪些优化（1～3 句）"
}
"""


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


async def _resolve_optimize_config(ai_config_id: Optional[int]) -> AiConfig:
    if ai_config_id:
        cfg = await AiConfig.get_or_none(id=ai_config_id, is_del=False, is_enabled=True)
        if not cfg:
            raise ValueError("指定的 AI 配置不存在或未启用")
        return cfg
    try:
        return await resolve_config_for_scene(_SCENE, None)
    except Exception:
        return await resolve_config_for_scene(_FALLBACK_SCENE, None)


async def optimize_browser_lab_task_text(
    *,
    task_text: str,
    start_url: str = "",
    case_name: str = "",
    ai_config_id: Optional[int] = None,
    username: str = "",
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """优化任务描述，返回 { task_text, changes_summary, tokens_used }。"""
    original = (task_text or "").strip()
    if len(original) < 2:
        raise ValueError("任务描述过短，无法优化")

    config = await _resolve_optimize_config(ai_config_id)
    scene_overrides = await get_scene_llm_overrides(_SCENE)
    if not scene_overrides:
        scene_overrides = await get_scene_llm_overrides(_FALLBACK_SCENE)

    user_parts = [
        f"起始 URL（平台会自动打开，任务正文无需再写访问该 URL）：{start_url.strip() or '（未提供）'}"
    ]
    if case_name.strip():
        user_parts.append(f"用例名称：{case_name.strip()}")
    user_parts.append(f"原始任务描述：\n{original}")
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
            {"role": "system", "content": _SYSTEM_PROMPT},
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
        logger.warning("[browser_lab.optimize] parse failed: %s", ex)
        raise ValueError("AI 返回格式无法解析，请重试或更换模型") from ex

    optimized = (parsed.get("task_text") or "").strip()
    if len(optimized) < 2:
        raise ValueError("AI 未返回有效任务描述")
    if len(optimized) > 4000:
        optimized = optimized[:4000]

    summary = (parsed.get("changes_summary") or "").strip()[:1000]

    try:
        await log_ai_usage(
            config,
            _SCENE,
            username=username,
            project_id=project_id,
            tokens_used=tokens,
            duration_ms=duration_ms,
            status="success",
            input_summary=original[:500],
            output_summary=optimized[:500],
        )
    except Exception as ex:
        logger.warning("[browser_lab.optimize] usage log failed: %s", ex)

    return {
        "task_text": optimized,
        "original_task_text": original,
        "changes_summary": summary,
        "tokens_used": tokens,
    }
