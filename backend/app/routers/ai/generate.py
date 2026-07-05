"""
AI 生成接口路由
支持：API 测试用例生成、UI 测试用例生成
"""
import asyncio
import json
import re
import time
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from app.core.auth import is_authenticated, require_permissions, verify_runner_or_internal
from app.core.permissions import AI_TEST_EXECUTE, APP_CASE_EDIT, UI_CASE_EDIT
from app.core.ai_prompts import PromptManager, append_extra_instructions
from app.core.ai_usage_log import log_ai_usage
from app.core.llm_client import LLMClientFactory
from app.core.encryption import decrypt_value
from app.core.page_fetcher import fetch_page_structure, format_elements_for_prompt, SmartPageExplorer
from app.core.ui_agent_explorer import UiMcpAgentExplorer
from app.core.ui_locator_heal import heal_locator
from app.core.ui_keywords import (
    UI_DEFAULT_PARAMS as _UI_DEFAULT_PARAMS,
    UI_REQUIRED_PARAMS as _UI_REQUIRED_PARAMS,
    UI_VALID_METHODS as _UI_VALID_METHODS,
    METHOD_TO_KEYWORD as _UI_METHOD_TO_KEYWORD,
)
from app.models.ai import AiConfig, AiGenerateRecord
from app.models.http import ApiDefinition, ApiTestCase
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["AI生成"])

UI_AGENT_MAX_STEPS = 30
UI_AGENT_DEFAULT_STEPS = 15
UI_AGENT_DAILY_LIMIT = int(__import__("os").getenv("UI_AGENT_DAILY_LIMIT", "100"))

_POPUP_FLOW_KEYWORDS = re.compile(
    r"弹窗|弹出|弹层|浮层|充值|对话框|drawer|modal|popup|弹.*支付|支付.*弹",
    re.IGNORECASE,
)


def _description_suggests_popup_flow(description: str) -> bool:
    return bool(_POPUP_FLOW_KEYWORDS.search(description or ""))


# ========== JSON 提取与清洗工具 ==========

def _extract_json_array(text: str) -> list:
    """
    从 LLM 返回的文本中提取 JSON 数组
    支持：markdown 代码块、纯 JSON、带前后缀文本、被截断的不完整 JSON
    """
    if not text:
        return []

    text = text.strip()

    # 1. 尝试匹配 ```json ... ``` 代码块
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    matches = re.findall(code_block_pattern, text)
    if matches:
        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for key in ("cases", "case", "data", "results", "result"):
                        if key in data and isinstance(data[key], list):
                            return data[key]
            except json.JSONDecodeError:
                continue

    # 2. 尝试直接匹配最外层的 JSON 数组 [ ... ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        # 尝试修复被截断的 JSON（补充缺失的 ] 和 }）
        try:
            fixed = _fix_truncated_json(text[start:end + 1])
            if fixed:
                data = json.loads(fixed)
                if isinstance(data, list):
                    return data
        except json.JSONDecodeError:
            pass

    # 3. 尝试匹配最外层的 JSON 对象 { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                for key in ("cases", "case", "data", "results", "result"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                for v in data.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            pass

    return []


def _extract_json_object(text: str) -> dict:
    """从 LLM 响应提取 JSON 对象"""
    if not text:
        return {}
    text = text.strip()
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    for match in re.findall(code_block_pattern, text):
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _fix_truncated_json(text: str) -> str | None:
    """尝试修复被 LLM 截断的不完整 JSON"""
    text = text.strip()
    # 统计括号平衡
    open_brackets = text.count("[") - text.count("]")
    open_braces = text.count("{") - text.count("}")
    open_quotes = text.count('"') % 2

    fixed = text
    # 补全缺失的字符串引号
    if open_quotes:
        fixed += '"'
    # 补全缺失的对象右括号
    for _ in range(open_braces):
        fixed += "}"
    # 补全缺失的数组右括号
    for _ in range(open_brackets):
        fixed += "]"

    # 如果最后一个有效字符是逗号，去掉它（截断前可能正在写下一个字段）
    # 找最后一个非空白字符
    stripped = fixed.rstrip()
    if stripped.endswith(","):
        fixed = stripped[:-1]
        # 重新补全括号
        open_brackets = fixed.count("[") - fixed.count("]")
        open_braces = fixed.count("{") - fixed.count("}")
        for _ in range(open_braces):
            fixed += "}"
        for _ in range(open_brackets):
            fixed += "]"

    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        return None


def _normalize_assertions(assertions: list) -> list[dict]:
    """将 AI 生成的断言字段映射为系统标准字段"""
    result = []
    for a in assertions or []:
        if not isinstance(a, dict):
            continue
        # 兼容旧字段名：source -> type, property -> target
        assertion_type = a.get("type") or a.get("source", "status_code")
        target = a.get("target")
        if target is None:
            target = a.get("property")
        result.append({
            "type": assertion_type,
            "target": target,
            "operator": a.get("operator", "equals"),
            "expected": a.get("expected"),
            "description": a.get("description", ""),
        })
    return result


def _normalize_extractors(extractors: list) -> list[dict]:
    """将 AI 生成的提取器字段映射为系统标准字段"""
    result = []
    for e in extractors or []:
        if not isinstance(e, dict):
            continue
        source = e.get("source", "json")
        # 兼容旧值：json_path / regex -> json
        if source in ("json_path", "regex"):
            source = "json"
        result.append({
            "name": e.get("name", ""),
            "source": source,
            "path": e.get("path") or e.get("property", ""),
            "description": e.get("description", ""),
        })
    return result


def _validate_api_cases(cases: list) -> tuple[list[str], list[dict]]:
    """
    校验 API 用例字段完整性，并做字段标准化
    返回：(错误列表, 有效用例列表)
    """
    errors = []
    valid_cases = []
    required_fields = {"name", "request_headers", "request_params", "request_body", "assertions", "extractors"}
    valid_assertion_types = {"status_code", "json_path", "header", "response_time", "contains", "not_contains"}
    valid_assertion_operators = {"equals", "not_equals", "contains", "not_contains", "regex", "gt", "lt", "gte", "lte", "in", "not_in"}
    valid_extractor_sources = {"json", "header"}

    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"第 {i + 1} 条用例不是对象")
            continue

        missing = required_fields - set(case.keys())
        if missing:
            errors.append(f"第 {i + 1} 条用例缺少字段: {', '.join(missing)}")

        # 标准化请求参数：兼容 AI 返回 {} 而不是 [] 的情况
        request_params = case.get("request_params", [])
        if isinstance(request_params, dict):
            # 将 {key: value} 转换为 [{name, value}] 格式
            if request_params:
                request_params = [
                    {"name": k, "value": str(v), "type": "string", "required": True, "description": ""}
                    for k, v in request_params.items()
                ]
            else:
                request_params = []
        elif not isinstance(request_params, list):
            request_params = []
        case["request_params"] = request_params

        # 标准化请求体类型和字段
        case["request_body_type"] = case.get("request_body_type", "json")
        case["request_body_fields"] = case.get("request_body_fields", []) or []
        if not isinstance(case["request_body_fields"], list):
            case["request_body_fields"] = []
        # form-data 类型时 request_body 必须是对象（空对象也行）
        if case["request_body_type"] == "form-data":
            if not isinstance(case.get("request_body"), dict):
                case["request_body"] = {}

        # 标准化断言和提取器
        normalized_assertions = _normalize_assertions(case.get("assertions", []))
        normalized_extractors = _normalize_extractors(case.get("extractors", []))
        case["assertions"] = normalized_assertions
        case["extractors"] = normalized_extractors

        # 校验断言
        for j, assertion in enumerate(normalized_assertions):
            if assertion.get("type") not in valid_assertion_types:
                errors.append(f"第 {i + 1} 条用例第 {j + 1} 个断言 type 不合法: {assertion.get('type')}")
            if assertion.get("operator") not in valid_assertion_operators:
                errors.append(f"第 {i + 1} 条用例第 {j + 1} 个断言 operator 不合法: {assertion.get('operator')}")

        # 校验变量提取
        for j, extractor in enumerate(normalized_extractors):
            if extractor.get("source") not in valid_extractor_sources:
                errors.append(f"第 {i + 1} 条用例第 {j + 1} 个提取器 source 不合法: {extractor.get('source')}")

        valid_cases.append(case)

    return errors, valid_cases


async def _get_default_ai_config() -> Optional[AiConfig]:
    """获取默认 LLM 配置"""
    from app.core.ai_scene_config import _pick_default_config
    return await _pick_default_config()


async def _get_ai_config(config_id: Optional[int], scene: Optional[str] = None) -> AiConfig:
    """按 ID 或场景绑定获取 LLM 配置，未指定则返回默认配置"""
    from app.core.ai_scene_config import resolve_config_for_scene
    return await resolve_config_for_scene(scene or "", config_id)


def _build_extra_body(config: AiConfig, *, disable_thinking: bool = False) -> dict:
    """根据配置构造 extra_body（用于 thinking 等供应商特定参数）"""
    extra_body = {}
    if disable_thinking:
        return extra_body
    if config.thinking_enabled:
        extra_body["thinking"] = {"type": "enabled"}
    return extra_body


def _is_retryable_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "timeout",
            "timed out",
            "stream timeout",
            "connection",
            "503",
            "502",
            "504",
            "429",
            "rate limit",
        )
    )


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    config: AiConfig,
    *,
    min_timeout: int = 0,
    max_retries: int = 0,
    param_overrides: dict | None = None,
    disable_thinking: bool = False,
) -> dict:
    """调用 LLM，返回 {"content": str, "tokens": int}
    param_overrides: 场景绑定上的 max_tokens / temperature / timeout / min_timeout 覆盖
    """
    po = param_overrides or {}
    api_key = decrypt_value(config.api_key)
    eff_timeout = int(po.get("timeout") or config.timeout or 60)
    if po.get("min_timeout") is not None:
        eff_timeout = max(eff_timeout, int(po["min_timeout"]))
    timeout = max(eff_timeout, int(min_timeout or 0))
    eff_temperature = po.get("temperature", config.temperature)
    eff_max_tokens = int(po.get("max_tokens") or config.max_tokens or 4096)
    client = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=timeout,
    )
    extra_body = _build_extra_body(config, disable_thinking=disable_thinking)
    kwargs = {}
    if not disable_thinking and config.thinking_enabled and config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_err: Optional[Exception] = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return await client.chat(
                messages=messages,
                temperature=eff_temperature,
                max_tokens=eff_max_tokens,
                extra_body=extra_body or None,
                stream=False,
                **kwargs,
            )
        except Exception as e:
            last_err = e
            if attempt < attempts - 1 and _is_retryable_llm_error(e):
                wait_s = 3 * (attempt + 1)
                logger.warning(
                    "[_call_llm] 第 %s/%s 次失败(%s)，%ss 后重试 model=%s prompt_len=%s",
                    attempt + 1,
                    attempts,
                    e,
                    wait_s,
                    config.model,
                    len(user_prompt or ""),
                )
                await asyncio.sleep(wait_s)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM 调用失败")


def _normalize_ui_steps(steps: list) -> tuple[list[dict], list[str]]:
    """校验并规范化 UI 步骤"""
    valid_steps = []
    errors = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"第 {i + 1} 步不是对象")
            continue

        method = step.get("method", "")
        if method not in _UI_VALID_METHODS:
            errors.append(f"第 {i + 1} 步 method '{method}' 不在支持列表中，已跳过")
            continue

        params = step.get("params", {}) or {}
        if not isinstance(params, dict):
            params = {}

        # 校验必填参数
        required = _UI_REQUIRED_PARAMS.get(method, set())
        missing = required - set(params.keys())
        if missing:
            errors.append(f"第 {i + 1} 步 '{method}' 缺少必填参数: {', '.join(missing)}")

        # 填充默认值
        defaults = _UI_DEFAULT_PARAMS.get(method, {})
        for key, val in defaults.items():
            if key not in params or params[key] is None:
                params[key] = val

        # 规范化字段
        standard_keyword = _UI_METHOD_TO_KEYWORD.get(method, step.get("keyword", method))

        normalized = {
            "id": f"step_{int(time.time() * 1000)}_{i}",
            "keyword": standard_keyword,
            "desc": step.get("desc", standard_keyword),
            "method": method,
            "params": params,
            "children": step.get("children", []) if isinstance(step.get("children"), list) else [],
        }
        valid_steps.append(normalized)

    return valid_steps, errors


# ========== UI 用例生成 ==========

class GenerateUiCaseRequest(BaseModel):
    description: str = Field(..., description="自然语言描述测试步骤", min_length=1, max_length=2000)
    page_url: Optional[str] = Field(default=None, description="目标页面URL")
    ai_config_id: Optional[int] = Field(default=None, description="指定 LLM 配置ID")
    auto_explore: bool = Field(default=False, description="是否启用多轮探索模式（登录态、跨页面）")
    max_rounds: int = Field(default=3, ge=1, le=10, description="最大探索轮次")


@router.post("/ui-case", summary="AI 生成 UI 测试用例步骤")
async def generate_ui_case(
    body: GenerateUiCaseRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    基于自然语言描述，使用 AI 生成 UI 自动化测试步骤
    支持两种模式：
    1. 单页面模式（auto_explore=false）：基于 page_url 抓取 DOM 后一次性生成
    2. 多轮探索模式（auto_explore=true）：在同一个浏览器 context 内执行-抓取-生成循环
    """
    start_time = time.time()
    project_id = user_info.get("project_id") or user_info.get("current_project_id")

    # 1. 获取 LLM 配置
    config = await _get_ai_config(body.ai_config_id, scene="ui_case_generate")

    # 2. 多轮探索模式（显式开启，或描述涉及弹窗/支付等动态浮层）
    use_explore = body.auto_explore or _description_suggests_popup_flow(body.description)
    if use_explore and body.page_url:
        return await _generate_ui_case_explore(body, config, project_id, user_info, start_time)

    # 3. 单页面模式（原有逻辑）
    return await _generate_ui_case_single(body, config, project_id, user_info, start_time)


async def _generate_ui_case_single(body, config, project_id, user_info, start_time):
    """单页面模式生成 UI 用例步骤"""
    page_elements_text = ""
    fetched_elements = []
    if body.page_url:
        try:
            page_data = await fetch_page_structure(body.page_url, timeout=15)
            if page_data:
                fetched_elements = page_data.get("elements", [])
                page_elements_text = format_elements_for_prompt(fetched_elements)
                logger.info(
                    f"[generate_ui_case] 页面抓取成功: {page_data.get('url')}, "
                    f"elements={len(fetched_elements)}"
                )
            else:
                logger.warning(f"[generate_ui_case] 页面抓取失败，降级为纯描述生成: {body.page_url}")
        except Exception as e:
            logger.warning(f"[generate_ui_case] 页面抓取异常，降级为纯描述生成: {e}")

    # 渲染 Prompt
    try:
        system_prompt, user_prompt = await PromptManager.render("ui_case_generation", {
            "description": body.description,
            "page_url": body.page_url or "",
            "page_elements": page_elements_text,
        })
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Prompt 渲染失败: {str(e)}")

    # 调用 LLM
    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "ui_case_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=body.description[:500],
            output_summary=str(e)[:500],
            mode="single",
        )
        logger.error(f"[generate_ui_case] LLM 调用失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM 调用失败: {str(e)}"
        )

    raw_response = resp.get("content", "")
    tokens_used = resp.get("tokens", 0)

    # 提取 JSON
    steps = _extract_json_array(raw_response)
    if not steps:
        logger.warning(f"[generate_ui_case] 无法从 LLM 响应中提取 JSON 数组，原始响应: {raw_response[:500]}")
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "ui_case_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            status="success",
            input_summary=body.description[:500],
            output_summary="JSON 解析失败",
            mode="single",
            parse_ok=False,
        )
        await AiGenerateRecord.create(
            project_id=project_id,
            generate_type="ui_case",
            input_summary={"description": body.description, "page_url": body.page_url},
            output_content={"raw_response": raw_response, "steps": [], "errors": ["无法解析 JSON 数组"]},
            status="rejected",
            ai_config_id=config.id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            create_by=user_info.get("username", ""),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI 返回内容无法解析为 JSON 数组，请重试或调整描述"
        )

    # 校验与规范化
    valid_steps, errors = _normalize_ui_steps(steps)

    # 记录生成历史
    duration_ms = int((time.time() - start_time) * 1000)
    record_id = await _save_ui_generate_record(
        project_id, body, config, valid_steps, errors, raw_response, tokens_used, duration_ms, user_info
    )

    await log_ai_usage(
        config,
        "ui_case_generate",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=body.description[:500],
        output_summary=f"生成 {len(valid_steps)} 步",
        mode="single",
        record_id=record_id,
    )

    return StandardResponse(data={
        "steps": valid_steps,
        "errors": errors,
        "raw_response": raw_response,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
        "record_id": record_id,
    })


async def _generate_ui_case_explore(body, config, project_id, user_info, start_time):
    """多轮探索模式生成 UI 用例步骤"""
    total_tokens = 0
    last_raw_response = ""

    async def llm_generate_func(dom_text, description, executed_steps, current_url, round_index):
        nonlocal total_tokens, last_raw_response

        # 格式化已执行步骤
        executed_steps_text = ""
        if executed_steps:
            executed_steps_text = json.dumps(executed_steps, ensure_ascii=False, indent=2)

        # 渲染 Prompt
        try:
            system_prompt, user_prompt = await PromptManager.render("ui_case_generation", {
                "description": description,
                "page_url": current_url,
                "page_elements": dom_text,
                "executed_steps": executed_steps_text,
                "executed_steps_count": len(executed_steps),
                "current_url": current_url,
                "round_index": round_index,
            })
        except ValueError as e:
            logger.error(f"[explore] Prompt 渲染失败: {e}")
            return []

        # 调用 LLM
        try:
            resp = await _call_llm(system_prompt, user_prompt, config)
        except Exception as e:
            logger.error(f"[explore] LLM 调用失败: {e}")
            return []

        last_raw_response = resp.get("content", "")
        total_tokens += resp.get("tokens", 0)

        # 提取 JSON
        steps = _extract_json_array(last_raw_response)
        if not steps:
            logger.warning(f"[explore] 第 {round_index} 轮无法解析 JSON，响应: {last_raw_response[:300]}")
            return []

        # 校验与规范化
        valid_steps, errs = _normalize_ui_steps(steps)
        if errs:
            logger.warning(f"[explore] 第 {round_index} 轮步骤校验警告: {errs}")

        return valid_steps

    # 启动 SmartPageExplorer
    explorer = SmartPageExplorer(
        start_url=body.page_url,
        description=body.description,
        max_rounds=body.max_rounds,
        timeout=15,
    )

    try:
        result = await explorer.explore(llm_generate_func)
    except Exception as e:
        logger.error(f"[generate_ui_case_explore] 探索异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"多轮探索失败: {str(e)}"
        )

    duration_ms = int((time.time() - start_time) * 1000)

    # 记录生成历史
    record_id = await _save_ui_generate_record(
        project_id, body, config,
        result["steps"], result["errors"], last_raw_response,
        total_tokens, duration_ms, user_info,
        extra_output={
            "explore_info": {
                "rounds": result["rounds"],
                "page_changes": result["page_changes"],
                "urls_visited": result["urls_visited"],
                "screenshots": result.get("screenshots", []),
            }
        }
    )

    await log_ai_usage(
        config,
        "ui_case_generate",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=body.description[:500],
        output_summary=f"探索 {result['rounds']} 轮，{len(result['steps'])} 步",
        mode="explore",
        record_id=record_id,
    )

    return StandardResponse(data={
        "steps": result["steps"],
        "errors": result["errors"],
        "raw_response": last_raw_response,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "record_id": record_id,
        "explore_info": {
            "rounds": result["rounds"],
            "page_changes": result["page_changes"],
            "urls_visited": result["urls_visited"],
            "screenshots": result.get("screenshots", []),
        },
    })


class GenerateUiCaseAgentRequest(BaseModel):
    description: str = Field(..., description="自然语言测试目标", min_length=1, max_length=2000)
    page_url: str = Field(..., description="起始页面 URL", min_length=1, max_length=500)
    ai_config_id: Optional[int] = Field(default=None, description="指定 LLM 配置ID")
    max_steps: int = Field(
        default=UI_AGENT_DEFAULT_STEPS,
        ge=1,
        le=UI_AGENT_MAX_STEPS,
        description="最大 Agent 步数（每步 1 次 LLM）",
    )


def _compact_agent_executed_steps(steps: list | None, *, tail: int = 10) -> str:
    """Agent 规划时压缩已执行步骤，避免 prompt 膨胀导致重复规划"""
    if not steps:
        return ""
    if len(steps) <= tail:
        return json.dumps(steps, ensure_ascii=False, indent=2)
    payload = {
        "total_executed": len(steps),
        "note": "仅展示最近步骤，禁止重复相同 method+locator",
        "recent_steps": steps[-tail:],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _prepend_agent_browser_steps(steps: list, start_url: str) -> list:
    """Agent 在 Backend 内已打开浏览器，返回步骤需补 Runner 前置 open_browser / open_url"""
    methods = {s.get("method") for s in steps if isinstance(s, dict)}
    prefix: list[dict] = []
    ts = int(time.time() * 1000)
    if "open_browser" not in methods:
        prefix.append({
            "id": f"step_{ts}_pre0",
            "keyword": "打开浏览器",
            "method": "open_browser",
            "desc": "打开浏览器",
            "params": {"browser_type": "chromium"},
            "children": [],
        })
    if "open_url" not in methods and (start_url or "").strip():
        url = start_url.strip()
        prefix.append({
            "id": f"step_{ts}_pre1",
            "keyword": "访问页面url",
            "method": "open_url",
            "desc": f"访问 {url}",
            "params": {"url": url, "wait_until": "load", "timeout": 30000},
            "children": [],
        })
    return prefix + list(steps)


async def _check_agent_daily_quota(project_id: Optional[int]) -> None:
    if not project_id or UI_AGENT_DAILY_LIMIT <= 0:
        return
    from datetime import datetime

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = await AiGenerateRecord.filter(
        project_id=project_id,
        generate_type__in=["ui_case_agent", "locator_heal"],
        create_time__gte=today_start,
    ).count()
    if count >= UI_AGENT_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"今日 AI Agent/自愈调用已达上限（{UI_AGENT_DAILY_LIMIT} 次）",
        )


async def _generate_ui_case_agent(
    body: GenerateUiCaseAgentRequest,
    config: AiConfig,
    project_id: Optional[int],
    user_info: dict,
    start_time: float,
) -> dict[str, Any]:
    """MCP 式 Agent 探索生成 UI 步骤（供路由与功能用例转 UI 复用）"""
    await _check_agent_daily_quota(project_id)

    total_tokens = 0
    last_raw_response = ""

    async def llm_plan_func(
        accessibility_snapshot,
        snapshot_type,
        description,
        executed_steps,
        current_url,
        step_index,
        stuck_hint: str = "",
    ):
        nonlocal total_tokens, last_raw_response
        executed_steps_text = _compact_agent_executed_steps(executed_steps)
        hint = (stuck_hint or "").strip()
        try:
            system_prompt, user_prompt = await PromptManager.render("ui_agent_plan", {
                "description": description,
                "accessibility_snapshot": accessibility_snapshot,
                "snapshot_type": snapshot_type,
                "executed_steps": executed_steps_text,
                "current_url": current_url,
                "step_index": step_index,
                "stuck_hint": hint,
                "has_stuck_hint": bool(hint),
            })
        except ValueError as e:
            logger.error(f"[ui_agent] Prompt 渲染失败: {e}")
            return {"done": True, "message": f"Prompt 渲染失败: {e}"}

        try:
            resp = await _call_llm(system_prompt, user_prompt, config)
        except Exception as e:
            logger.error(f"[ui_agent] LLM 调用失败: {e}")
            return {"done": True, "message": f"LLM 调用失败: {e}"}

        last_raw_response = resp.get("content", "")
        total_tokens += resp.get("tokens", 0)
        parsed = _extract_json_object(last_raw_response)
        if not parsed:
            logger.warning(f"[ui_agent] 第 {step_index} 步无法解析 JSON: {last_raw_response[:300]}")
            return {"done": True, "message": "无法解析 LLM 响应"}

        if parsed.get("done"):
            return {"done": True, "message": parsed.get("message") or "完成"}

        step = parsed.get("step")
        if not step:
            return {"done": True, "message": "LLM 未返回 step"}

        valid_steps, errs = _normalize_ui_steps([step])
        if errs:
            logger.warning(f"[ui_agent] 第 {step_index} 步校验警告: {errs}")
        if not valid_steps:
            return {"done": True, "message": "步骤校验失败"}

        return {"done": False, "step": valid_steps[0]}

    async def llm_heal_func(
        method,
        failed_locator,
        step_desc,
        error_message,
        page_url,
        accessibility_snapshot,
        snapshot_type,
    ):
        nonlocal total_tokens
        try:
            result = await heal_locator(
                method=method,
                failed_locator=failed_locator,
                step_desc=step_desc,
                error_message=error_message,
                page_url=page_url,
                accessibility_snapshot=accessibility_snapshot,
                call_llm=lambda s, u: _call_llm(s, u, config),
                ai_config_id=config.id,
            )
            total_tokens += result.get("tokens_used") or 0
            return result
        except Exception as e:
            logger.warning(f"[ui_agent] 自愈失败: {e}")
            return {"success": False, "reason": str(e)}

    explorer = UiMcpAgentExplorer(
        start_url=body.page_url.strip(),
        description=body.description,
        max_rounds=1,
        timeout=15,
    )

    try:
        result = await explorer.agent_explore(
            llm_plan_func,
            max_steps=body.max_steps,
            heal_func=llm_heal_func,
        )
    except Exception as e:
        logger.error(f"[ui_agent] 探索异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent 探索失败: {str(e)}") from e

    result["steps"] = _prepend_agent_browser_steps(result.get("steps") or [], body.page_url)

    duration_ms = int((time.time() - start_time) * 1000)

    record_id = None
    if project_id:
        try:
            record = await AiGenerateRecord.create(
                project_id=project_id,
                generate_type="ui_case_agent",
                input_summary={
                    "description": body.description,
                    "page_url": body.page_url,
                    "max_steps": body.max_steps,
                },
                output_content={
                    "steps": result["steps"],
                    "errors": result["errors"],
                    "agent_log": result.get("agent_log", []),
                    "raw_response": last_raw_response,
                },
                status="pending",
                ai_config_id=config.id,
                tokens_used=total_tokens,
                duration_ms=duration_ms,
                create_by=user_info.get("username", ""),
            )
            record_id = record.id
        except Exception as e:
            logger.warning(f"[ui_agent] 保存记录失败: {e}")

    await log_ai_usage(
        config,
        "ui_case_agent",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=body.description[:500],
        output_summary=f"Agent {len(result.get('steps') or [])} 步",
        page_url=body.page_url,
        record_id=record_id,
    )

    return {
        "steps": result["steps"],
        "errors": result["errors"],
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "record_id": record_id,
        "agent_info": {
            "mode": "agent_mcp",
            "executed_steps": result.get("executed_steps", 0),
            "agent_log": result.get("agent_log", []),
            "urls_visited": result.get("urls_visited", []),
            "screenshots": result.get("screenshots", []),
        },
        "raw_response": last_raw_response,
    }


@router.post(
    "/ui-case/agent",
    summary="MCP 式 Agent 探索生成 UI 步骤",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_ui_case_agent(
    body: GenerateUiCaseAgentRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    Playwright MCP 思路：accessibility snapshot → 逐步规划 → 执行 → 固化标准 steps。
    每步调用 1 次文本 LLM，适合探索性生成，不建议直接用于 CI 定时任务。
    """
    start_time = time.time()
    project_id = user_info.get("project_id") or user_info.get("current_project_id")

    config = await _get_ai_config(body.ai_config_id, scene="ui_case_agent")

    data = await _generate_ui_case_agent(body, config, project_id, user_info, start_time)
    return StandardResponse(data=data)


class LocatorHealRequest(BaseModel):
    method: str = Field(..., description="步骤方法名")
    failed_locator: str = Field(..., description="失败的定位器")
    step_desc: Optional[str] = Field(default=None, max_length=500)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    page_url: Optional[str] = Field(default=None, max_length=500)
    accessibility_snapshot: Optional[str] = Field(default=None, max_length=50000)
    page_elements: Optional[list] = Field(default=None, description="Runner 抓取的元素列表")
    ai_config_id: Optional[int] = None
    project_id: Optional[int] = Field(default=None, description="Runner 执行所属项目 ID")
    replay_steps: Optional[list] = Field(default=None, description="用例步骤列表，用于回放")
    replay_through_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="回放 steps[0:through_index] 后抓 snapshot（不含当前编辑步）",
    )


async def _locator_heal_handler(
    body: LocatorHealRequest,
    project_id: Optional[int],
    username: str,
) -> dict[str, Any]:
    try:
        await _check_agent_daily_quota(project_id)
    except HTTPException as exc:
        return {"success": False, "reason": str(exc.detail)}

    try:
        config = await _get_ai_config(body.ai_config_id, scene="locator_heal")
    except HTTPException as e:
        return {"success": False, "reason": e.detail}

    start_time = time.time()

    snapshot = body.accessibility_snapshot
    page_url = body.page_url
    page_elements = body.page_elements

    if body.replay_steps is not None and body.replay_through_index is not None:
        from app.core.step_replay_snapshot import capture_snapshot_after_replay

        replay_result = await capture_snapshot_after_replay(
            body.replay_steps,
            body.replay_through_index,
            fallback_url=body.page_url or "",
        )
        if not replay_result.get("success"):
            return {
                "success": False,
                "reason": replay_result.get("reason") or "步骤回放失败",
                **{k: v for k, v in replay_result.items() if k != "success"},
            }
        snapshot = replay_result.get("accessibility_snapshot")
        page_url = replay_result.get("page_url") or page_url

    from app.core.ai_scene_config import get_scene_llm_overrides

    overrides = await get_scene_llm_overrides("locator_heal")

    async def call_llm(system_prompt: str, user_prompt: str) -> dict:
        return await _call_llm(
            system_prompt,
            user_prompt,
            config,
            min_timeout=30,
            param_overrides=overrides,
            disable_thinking=True,
        )

    try:
        result = await heal_locator(
            method=body.method,
            failed_locator=body.failed_locator,
            step_desc=body.step_desc,
            error_message=body.error_message,
            page_url=page_url,
            accessibility_snapshot=snapshot,
            page_elements=page_elements,
            call_llm=call_llm,
        )
    except Exception as exc:
        logger.exception("[locator_heal] heal_locator failed")
        return {"success": False, "reason": f"自愈处理异常: {exc}"}

    duration_ms = int((time.time() - start_time) * 1000)
    tokens_used = result.get("tokens_used", 0)

    if project_id:
        try:
            await AiGenerateRecord.create(
                project_id=project_id,
                generate_type="locator_heal",
                input_summary={
                    "method": body.method,
                    "failed_locator": body.failed_locator,
                    "page_url": body.page_url,
                },
                output_content=result,
                status="imported" if result.get("success") else "rejected",
                ai_config_id=config.id,
                tokens_used=tokens_used,
                duration_ms=duration_ms,
                create_by=username or "system",
            )
        except Exception as e:
            logger.warning(f"[locator_heal] 保存记录失败: {e}")

    try:
        await log_ai_usage(
            config,
            "locator_heal",
            username=username,
            project_id=project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=f"{body.method}: {body.failed_locator}"[:500],
            output_summary=(result.get("locator") or result.get("reason") or "")[:500],
            status="success" if result.get("success") else "failed",
        )
    except Exception as exc:
        logger.warning("[locator_heal] log_ai_usage failed: %s", exc)

    return {
        **result,
        "duration_ms": duration_ms,
    }


@router.post(
    "/locator-heal",
    summary="UI 步骤定位器自愈",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def locator_heal(
    body: LocatorHealRequest,
    user_info: dict = Depends(is_authenticated),
):
    """基于页面 snapshot 为失败步骤推荐新 locator（编辑页手动触发）"""
    project_id = user_info.get("project_id") or user_info.get("current_project_id")
    result = await _locator_heal_handler(
        body,
        project_id,
        user_info.get("username") or user_info.get("sub") or "",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "自愈失败")
    return StandardResponse(
        data={
            "locator": result["locator"],
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "snapshot_type": result.get("snapshot_type"),
            "tokens_used": result.get("tokens_used", 0),
            "duration_ms": result.get("duration_ms", 0),
        },
        message="已生成新定位器",
    )


@router.post(
    "/locator-heal/internal",
    summary="UI 定位器自愈（Runner 内部）",
    dependencies=[Depends(verify_runner_or_internal)],
)
async def locator_heal_internal(
    body: LocatorHealRequest,
    project_id: Optional[int] = None,
):
    """Runner 步骤失败时调用，需 X-Runner-Token 或 X-Internal-Token"""
    effective_project_id = project_id or body.project_id
    result = await _locator_heal_handler(body, effective_project_id, "runner")
    return StandardResponse(data=result)


class ApplyHealedLocatorBody(BaseModel):
    case_id: int = Field(..., ge=1)
    step_index: int = Field(..., ge=0, description="步骤序号，从 0 开始")
    new_locator: str = Field(..., min_length=1, max_length=2000)
    original_locator: Optional[str] = Field(default=None, max_length=2000)


@router.post(
    "/locator-heal/apply-to-case",
    summary="将自愈后的定位器写回 UI 用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, UI_CASE_EDIT))],
)
async def apply_healed_locator_to_case(
    body: ApplyHealedLocatorBody,
    user_info: dict = Depends(is_authenticated),
):
    """执行报告确认后，将 AI 自愈的 locator 持久化到用例 steps"""
    from app.models.ui import Case

    case = await Case.get_or_none(id=body.case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")

    steps = case.steps if isinstance(case.steps, list) else []
    if body.step_index >= len(steps):
        raise HTTPException(status_code=400, detail=f"步骤序号超出范围（共 {len(steps)} 步）")

    step = steps[body.step_index]
    if not isinstance(step, dict):
        raise HTTPException(status_code=400, detail="步骤数据格式异常")

    params = step.get("params")
    if not isinstance(params, dict):
        params = {}
        step["params"] = params

    locator_key = "selector" if "selector" in params and "locator" not in params else "locator"
    old_locator = params.get(locator_key) or params.get("locator") or params.get("selector")
    params[locator_key] = body.new_locator.strip()
    if locator_key == "locator" and "selector" in params:
        params.pop("selector", None)
    elif locator_key == "selector" and "locator" in params:
        params.pop("locator", None)

    steps[body.step_index] = step
    case.steps = steps
    await case.save()

    return StandardResponse(
        data={
            "case_id": body.case_id,
            "step_index": body.step_index,
            "locator_key": locator_key,
            "original_locator": body.original_locator or old_locator,
            "new_locator": body.new_locator.strip(),
        },
        message="已写回用例定位器",
    )


# ========== App 用例生成 ==========

class GenerateAppCaseRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    app_id: Optional[str] = Field(default=None, max_length=200)
    driver_mode: str = Field(default="hybrid")
    ai_config_id: Optional[int] = None


@router.post(
    "/app-case",
    summary="AI 生成 App 测试步骤",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_app_case(
    body: GenerateAppCaseRequest,
    user_info: dict = Depends(is_authenticated),
):
    from app.core.functional_case_to_app import (
        AppGenerationContext,
        _generate_app_steps,
        validate_app_generation_context,
    )

    project_id = user_info.get("project_id") or user_info.get("current_project_id")
    ctx = AppGenerationContext(
        app_id=body.app_id,
        driver_mode=body.driver_mode or "hybrid",
        ai_config_id=body.ai_config_id,
    )
    validate_app_generation_context(ctx)
    data = await _generate_app_steps(
        description=body.description,
        ctx=ctx,
        project_id=project_id,
        user_info=user_info,
    )
    return StandardResponse(data=data)


class AppInspectorSuggestRequest(BaseModel):
    session_id: Optional[str] = None
    node_attributes: dict = Field(default_factory=dict)
    suggested_locator: Optional[dict] = None
    driver_mode: str = Field(default="hybrid")
    intent: str = Field(default="both", description="name / steps / both")
    app_id: Optional[str] = None
    extra_hint: Optional[str] = Field(default=None, max_length=500)
    ai_config_id: Optional[int] = None
    vision_config_id: Optional[int] = None


@router.post(
    "/app-inspector-suggest",
    summary="元素探查 AI：命名元素 / 生成步骤",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def app_inspector_suggest(
    body: AppInspectorSuggestRequest,
    user_info: dict = Depends(is_authenticated),
):
    from app.core.app_inspector_ai import suggest_inspector_ai

    project_id = user_info.get("project_id") or user_info.get("current_project_id")
    data = await suggest_inspector_ai(
        project_id=project_id,
        user_info=user_info,
        ai_config_id=body.ai_config_id,
        vision_config_id=body.vision_config_id,
        session_id=body.session_id,
        node_attributes=body.node_attributes or {},
        suggested_locator=body.suggested_locator,
        driver_mode=body.driver_mode,
        intent=body.intent,
        app_id=body.app_id,
        extra_hint=body.extra_hint,
    )
    return StandardResponse(data=data)


class AppLocatorHealRequest(BaseModel):
    method: str
    failed_locator: dict
    step_desc: Optional[str] = Field(default=None, max_length=500)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    match_score: Optional[float] = None
    control_tree_excerpt: Optional[str] = Field(default=None, max_length=30000)
    screenshot_base64: Optional[str] = Field(default=None, max_length=500000)
    ai_config_id: Optional[int] = None
    vision_config_id: Optional[int] = None


async def _app_locator_heal_handler(body: AppLocatorHealRequest, project_id: Optional[int], username: str) -> dict:
    from app.core.app_locator_heal import heal_app_locator

    try:
        config = await _get_ai_config(body.ai_config_id, scene="locator_heal")
    except HTTPException as e:
        return {"success": False, "reason": e.detail}

    start_time = time.time()

    async def call_llm(system_prompt: str, user_prompt: str) -> dict:
        return await _call_llm(system_prompt, user_prompt, config, min_timeout=30)

    call_vision = None
    if body.screenshot_base64 and body.vision_config_id:
        try:
            import base64 as b64mod
            from app.routers.ai.analyze import _call_vision_analysis

            vision_config = await _get_ai_config(body.vision_config_id, scene="failure_analysis_vision")
            img_bytes = b64mod.b64decode(body.screenshot_base64)

            async def _vcall(prompt: str, _b64: str) -> dict:
                return await _call_vision_analysis(
                    vision_config,
                    "你是 Android UI 分析助手。",
                    prompt,
                    img_bytes,
                    "image/png",
                )

            call_vision = _vcall
        except Exception as exc:
            logger.warning("[app_locator_heal] vision config: %s", exc)

    result = await heal_app_locator(
        method=body.method,
        failed_locator=body.failed_locator,
        step_desc=body.step_desc,
        error_message=body.error_message,
        match_score=body.match_score,
        control_tree_excerpt=body.control_tree_excerpt,
        screenshot_base64=body.screenshot_base64,
        call_llm=call_llm,
        call_vision=call_vision,
    )
    result["duration_ms"] = int((time.time() - start_time) * 1000)

    if project_id and result.get("success"):
        try:
            await AiGenerateRecord.create(
                project_id=project_id,
                generate_type="locator_heal",
                input_summary={"method": body.method, "failed_locator": body.failed_locator},
                output_content=result,
                status="imported",
                ai_config_id=config.id,
                tokens_used=result.get("tokens_used", 0),
                duration_ms=result["duration_ms"],
                create_by=username or "system",
            )
        except Exception as exc:
            logger.warning("[app_locator_heal] save record: %s", exc)
    return result


@router.post(
    "/app-locator-heal",
    summary="App 步骤定位器自愈",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def app_locator_heal(
    body: AppLocatorHealRequest,
    user_info: dict = Depends(is_authenticated),
):
    project_id = user_info.get("project_id") or user_info.get("current_project_id")
    result = await _app_locator_heal_handler(
        body, project_id, user_info.get("username") or user_info.get("sub") or ""
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "自愈失败")
    return StandardResponse(data=result, message="已生成新定位器")


@router.post(
    "/app-locator-heal/internal",
    summary="App 定位器自愈（Runner 内部）",
    dependencies=[Depends(verify_runner_or_internal)],
)
async def app_locator_heal_internal(
    body: AppLocatorHealRequest,
    project_id: Optional[int] = None,
):
    return StandardResponse(data=await _app_locator_heal_handler(body, project_id, "runner"))


async def _save_ui_generate_record(
    project_id, body, config, valid_steps, errors, raw_response,
    tokens_used, duration_ms, user_info, extra_output=None
):
    """保存 UI 生成记录，返回 record_id"""
    if not project_id:
        logger.warning("[generate_ui_case] user_info 中缺少 project_id，跳过保存生成记录")
        return None

    output = {"steps": valid_steps, "errors": errors, "raw_response": raw_response}
    if extra_output:
        output.update(extra_output)

    try:
        record = await AiGenerateRecord.create(
            project_id=project_id,
            generate_type="ui_case",
            input_summary={
                "description": body.description,
                "page_url": body.page_url,
                "auto_explore": getattr(body, "auto_explore", False),
                "max_rounds": getattr(body, "max_rounds", 3),
            },
            output_content=output,
            status="pending",
            ai_config_id=config.id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            create_by=user_info.get("username", ""),
        )
        return record.id
    except Exception as e:
        logger.warning(f"[generate_ui_case] 保存生成记录失败: {e}")
        return None


# ========== API 用例生成 ==========

class GenerateApiCaseRequest(BaseModel):
    api_definition_id: int = Field(..., description="接口定义ID")
    count: int = Field(default=3, ge=1, le=10, description="生成用例数量")
    prompt_override: Optional[str] = Field(default=None, description="用户额外补充要求")
    ai_config_id: Optional[int] = Field(default=None, description="指定 LLM 配置ID")
    catalog_id: Optional[int] = Field(default=None, description="目标目录ID")


class ImportApiCaseRequest(BaseModel):
    api_definition_id: int = Field(..., description="接口定义ID")
    cases: list[dict] = Field(..., description="AI 生成的用例列表")
    catalog_id: Optional[int] = Field(default=None, description="目标目录ID")


EXISTING_CASES_LIMIT = 8


def _truncate_json_text(obj, max_len: int = 800) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


async def _load_existing_cases_for_prompt(api_definition_id: int) -> tuple[str, int]:
    """加载接口已有用例摘要，供 LLM 参考并避免重复。"""
    qs = ApiTestCase.filter(api_id=api_definition_id, is_del=False).order_by("-update_time")
    total = await qs.count()
    if total == 0:
        return "", 0

    cases = await qs.limit(EXISTING_CASES_LIMIT)
    lines: list[str] = []
    for idx, case in enumerate(cases, start=1):
        lines.append(f"{idx}. 名称: {case.name}")
        if case.priority:
            lines.append(f"   优先级: {case.priority}")
        if case.tags:
            lines.append(f"   标签: {_truncate_json_text(case.tags, 200)}")
        if case.assertions:
            lines.append(f"   断言: {_truncate_json_text(case.assertions, 700)}")
        if case.extractors:
            lines.append(f"   变量提取: {_truncate_json_text(case.extractors, 400)}")
        if case.request_body:
            lines.append(f"   请求体: {_truncate_json_text(case.request_body, 500)}")
        if case.request_params:
            lines.append(f"   请求参数: {_truncate_json_text(case.request_params, 400)}")
    return "\n".join(lines), total


@router.post("/api-case", summary="AI 生成 API 测试用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def generate_api_case(
    body: GenerateApiCaseRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    基于接口定义，使用 AI 生成 API 测试用例
    """
    start_time = time.time()
    project_id = user_info.get("project_id") or user_info.get("current_project_id")

    # 1. 查询接口定义
    api_def = await ApiDefinition.get_or_none(id=body.api_definition_id, is_del=False)
    if not api_def:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="接口定义不存在")

    # 2. 获取 LLM 配置
    config = await _get_ai_config(body.ai_config_id, scene="api_case_generate")

    # 准备响应结构信息
    # 提取响应 schema 和示例，确保传入 Prompt 的数据清晰
    response_schema_raw = api_def.response_schema or {}
    response_schema_json = ""
    response_example = ""
    
    if isinstance(response_schema_raw, dict):
        # 提取 schema 部分（优先用 .schema，如果本身就是 schema 对象则直接用）
        schema_obj = response_schema_raw.get("schema")
        if schema_obj is not None:
            response_schema_json = json.dumps(schema_obj, ensure_ascii=False, indent=2)
        elif "type" in response_schema_raw or "properties" in response_schema_raw:
            # 直接是 schema 对象（兼容旧数据）
            response_schema_json = json.dumps(response_schema_raw, ensure_ascii=False, indent=2)
        
        # 提取 example 部分
        example_obj = response_schema_raw.get("example")
        if example_obj is not None:
            if isinstance(example_obj, str):
                response_example = example_obj
            else:
                response_example = json.dumps(example_obj, ensure_ascii=False, indent=2)

    existing_cases_text, existing_cases_count = await _load_existing_cases_for_prompt(body.api_definition_id)

    # 3. 渲染 Prompt
    try:
        system_prompt, user_prompt = await PromptManager.render("api_case_generation", {
            "api_name": api_def.name or "",
            "method": api_def.method or "",
            "path": api_def.path or "",
            "description": api_def.description or "",
            "headers": json.dumps(api_def.headers or {}, ensure_ascii=False, indent=2),
            "params": json.dumps(api_def.params or [], ensure_ascii=False, indent=2),
            "body": json.dumps(api_def.body or {}, ensure_ascii=False, indent=2),
            "body_type": api_def.body_type or "json",
            "body_fields": json.dumps(api_def.body_fields or [], ensure_ascii=False, indent=2) if api_def.body_fields else "",
            "response_schema": response_schema_json,
            "response_example": response_example,
            "existing_cases": existing_cases_text,
            "existing_cases_count": existing_cases_count,
            "existing_cases_limit": EXISTING_CASES_LIMIT,
            "count": body.count,
            "extra": body.prompt_override or "",
        })
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Prompt 渲染失败: {str(e)}")

    user_prompt = append_extra_instructions(user_prompt, body.prompt_override, scene="api_case")

    # 4. 调用 LLM
    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "api_case_generate",
            user_info=user_info,
            project_id=project_id or api_def.project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"{api_def.method} {api_def.path}"[:500],
            output_summary=str(e)[:500],
            api_definition_id=body.api_definition_id,
        )
        logger.error(f"[generate_api_case] LLM 调用失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM 调用失败: {str(e)}"
        )

    raw_response = resp.get("content", "")
    tokens_used = resp.get("tokens", 0)

    # 5. 提取 JSON
    cases = _extract_json_array(raw_response)
    if not cases:
        logger.warning(f"[generate_api_case] 无法从 LLM 响应中提取 JSON 数组，原始响应前500字: {raw_response[:500]}")
        # 记录生成历史
        duration_ms = int((time.time() - start_time) * 1000)
        
        # 判断是否是 token 截断导致（JSON 未正常闭合）
        stripped = raw_response.strip()
        is_truncated = False
        if stripped:
            # 如果响应不以 ] 或 } 结尾，很可能是被截断了
            last_char = stripped[-1]
            is_truncated = last_char not in ("]", "}")
        
        error_msg = "无法解析 JSON 数组"
        if is_truncated:
            error_msg = f"AI 生成内容被截断（当前 max_tokens={config.max_tokens}），请增大 AI 配置的 max_tokens（建议 16384 或更高）或减少生成数量"
        elif not stripped:
            error_msg = "AI 返回空内容，请检查 LLM 配置"
        
        await AiGenerateRecord.create(
            project_id=project_id or api_def.project_id,
            generate_type="api_case",
            input_summary={
                "api_definition_id": body.api_definition_id,
                "api_name": api_def.name,
                "method": api_def.method,
                "path": api_def.path,
            },
            output_content={"raw_response": raw_response, "cases": [], "errors": [error_msg]},
            status="rejected",
            ai_config_id=config.id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            create_by=user_info.get("username", ""),
        )
        await log_ai_usage(
            config,
            "api_case_generate",
            user_info=user_info,
            project_id=project_id or api_def.project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=f"{api_def.method} {api_def.path}"[:500],
            output_summary=error_msg[:500],
            api_definition_id=body.api_definition_id,
            parse_ok=False,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

    # 6. 校验字段
    errors, valid_cases = _validate_api_cases(cases)

    # 7. 记录生成历史
    duration_ms = int((time.time() - start_time) * 1000)
    record = await AiGenerateRecord.create(
        project_id=project_id or api_def.project_id,
        generate_type="api_case",
        input_summary={
            "api_definition_id": body.api_definition_id,
            "api_name": api_def.name,
            "method": api_def.method,
            "path": api_def.path,
            "count": body.count,
            "prompt_override": body.prompt_override,
        },
        output_content={"cases": valid_cases, "errors": errors, "raw_response": raw_response},
        status="pending",
        ai_config_id=config.id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=user_info.get("username", ""),
    )

    await log_ai_usage(
        config,
        "api_case_generate",
        user_info=user_info,
        project_id=project_id or api_def.project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=f"{api_def.method} {api_def.path}, count={body.count}"[:500],
        output_summary=f"生成 {len(valid_cases)} 条用例",
        api_definition_id=body.api_definition_id,
        record_id=record.id,
    )

    return StandardResponse(data={
        "cases": valid_cases,
        "errors": errors,
        "raw_response": raw_response,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
        "record_id": record.id,
        "existing_cases_count": existing_cases_count,
    })


@router.post("/api-case/import", summary="导入 AI 生成的 API 测试用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def import_api_cases(
    body: ImportApiCaseRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    将 AI 生成的用例批量导入为正式的 ApiTestCase
    """
    username = user_info.get("username", "")
    project_id = user_info.get("project_id") or user_info.get("current_project_id")

    # 查询接口定义
    api_def = await ApiDefinition.get_or_none(id=body.api_definition_id, is_del=False)
    if not api_def:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="接口定义不存在")

    # 校验用例
    _, valid_cases = _validate_api_cases(body.cases)
    if not valid_cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有有效的用例可导入")

    imported_ids = []
    for case_data in valid_cases:
        case = await ApiTestCase.create(
            name=case_data.get("name", "AI生成用例")[:100],
            api_id=body.api_definition_id,
            project_id=api_def.project_id,
            catalog_id=body.catalog_id,
            request_headers=case_data.get("request_headers", {}),
            request_params=case_data.get("request_params", []),
            request_body=case_data.get("request_body", {}),
            request_body_type=case_data.get("request_body_type", "json"),
            request_body_fields=case_data.get("request_body_fields", []) or [],
            assertions=case_data.get("assertions", []),
            extractors=case_data.get("extractors", []),
            priority=case_data.get("priority", "P2"),
            tags=case_data.get("tags", []),
            create_by=username,
        )
        imported_ids.append(case.id)

    # 更新生成记录状态
    # 查找最近的 api_case 生成记录
    record = await AiGenerateRecord.filter(
        generate_type="api_case",
    ).order_by("-id").first()
    if record:
        record.status = "imported"
        record.imported_target_id = imported_ids[0] if imported_ids else None
        record.imported_target_type = "api_test_case"
        await record.save()

    return StandardResponse(data={
        "imported_count": len(imported_ids),
        "imported_ids": imported_ids,
    })


# ========== 页面预抓取接口 ==========

class FetchPageRequest(BaseModel):
    url: str = Field(..., description="目标页面URL", min_length=1, max_length=500)


@router.post("/fetch-page", summary="预抓取页面元素结构")
async def fetch_page(
    body: FetchPageRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    使用 Playwright 无头浏览器抓取目标页面的可交互元素列表
    供前端 AI 生成 UI 用例时展示页面结构
    """
    try:
        page_data = await fetch_page_structure(body.url, timeout=15)
    except Exception as e:
        logger.error(f"[fetch_page] 抓取异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"页面抓取失败: {str(e)}"
        )

    if not page_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法抓取目标页面，请检查 URL 是否可访问"
        )

    return StandardResponse(data={
        "title": page_data.get("title", ""),
        "url": page_data.get("url", ""),
        "elements": page_data.get("elements", []),
        "status_code": page_data.get("status_code", 0),
    })
