"""
AI 分析：失败根因分析（支持 UI Vision 读图）
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.ai.ai_prompts import PromptManager
from app.core.llm.ai_usage_log import log_ai_usage
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.encryption import decrypt_value
from app.modules.ai.failure_context import build_api_failure_context, build_app_failure_context, build_ui_failure_context
from app.core.shared.report_summary_context import (
    ReportType,
    build_report_execution_data,
    collect_failure_targets,
    fetch_recent_failures,
)
from app.core.llm.llm_client import LLMClientFactory
from app.core.llm.llm_invoke import resolve_vision_max_tokens
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW
from app.models.ai import AiConfig, AiGenerateRecord
from app.models.http import ApiRunRecord
from app.models.ui import UiCaseExecution
from app.models.app import AppCaseExecution
from app.routers.ai.generate import _build_extra_body, _call_llm, _get_ai_config
from app.modules.ai.ai_scene_config import resolve_vision_config
from app.routers.ai.requirements import _resolve_project_id
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["AI分析"])

# 报告摘要仍保留 24h 缓存窗口；失败分析为永久缓存直至 force_refresh
REPORT_SUMMARY_CACHE_HOURS = 24


class AnalyzeFailureRequest(BaseModel):
    target_type: Literal["api", "ui", "app"]
    target_id: int = Field(..., description="ApiRunRecord.id 或 UiCaseExecution.id")
    ai_config_id: Optional[int] = Field(None, description="文本分析模型，不传用默认配置")
    vision_config_id: Optional[int] = Field(None, description="UI 截图 Vision 模型，不传则自动匹配")
    use_vision: bool = Field(False, description="是否启用截图识图（默认关闭，纯文本分析）")
    force_refresh: bool = Field(False, description="忽略缓存重新分析")
    knowledge_folder_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文件夹",
    )
    knowledge_document_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文档",
    )


class FailureTargetItem(BaseModel):
    target_type: Literal["api", "ui", "app"]
    target_id: int


class BatchFailureRequest(BaseModel):
    targets: Optional[list[FailureTargetItem]] = Field(None, description="显式指定失败记录列表")
    report_type: Optional[ReportType] = Field(None, description="从套件/计划执行记录采集失败项")
    record_id: Optional[int] = Field(None, description="report_type 对应的执行记录 ID")
    limit: int = Field(5, ge=1, le=10, description="从报告中采集的最大失败数")
    ai_config_id: Optional[int] = None
    vision_config_id: Optional[int] = None
    use_vision: bool = False
    force_refresh: bool = False
    knowledge_folder_ids: Optional[list[int]] = None
    knowledge_document_ids: Optional[list[int]] = None


class ReportSummaryRequest(BaseModel):
    report_type: ReportType
    record_id: int
    ai_config_id: Optional[int] = None
    force_refresh: bool = False


def _is_likely_vision_model(model: str) -> bool:
    m = (model or "").lower()
    return "vl" in m or "vision" in m or "gpt-4o" in m


def _extract_json_object(text: str) -> dict[str, Any]:
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
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _analysis_to_response(record: AiGenerateRecord) -> dict[str, Any]:
    out = record.output_content if isinstance(record.output_content, dict) else {}
    inp = record.input_summary if isinstance(record.input_summary, dict) else {}
    return {
        "analysis_id": record.id,
        "target_type": inp.get("target_type"),
        "target_id": inp.get("target_id"),
        "root_cause": out.get("root_cause") or "",
        "possible_causes": out.get("possible_causes") or [],
        "suggestions": out.get("suggestions") or [],
        "confidence": out.get("confidence"),
        "category": out.get("category") or "",
        "raw_response": out.get("raw_response") or "",
        "vision_used": bool(inp.get("vision_used")),
        "vision_config_name": inp.get("vision_config_name"),
        "cached": True,
        "create_time": record.create_time.strftime("%Y-%m-%d %H:%M:%S") if record.create_time else "",
        "tokens_used": record.tokens_used or 0,
        "duration_ms": record.duration_ms or 0,
    }


async def _find_cached_analysis(
    project_id: int,
    target_type: str,
    target_id: int,
) -> Optional[AiGenerateRecord]:
    """查找该失败记录的最近一次成功分析（永久有效，直至手动重新分析）"""
    records = (
        await AiGenerateRecord.filter(
            project_id=project_id,
            generate_type="failure_analysis",
            status="accepted",
        )
        .order_by("-id")
        .limit(100)
    )
    for rec in records:
        inp = rec.input_summary if isinstance(rec.input_summary, dict) else {}
        if inp.get("target_type") == target_type and inp.get("target_id") == target_id:
            return rec
    return None


async def _get_vision_config(vision_config_id: Optional[int]) -> Optional[AiConfig]:
    return await resolve_vision_config(vision_config_id)


async def _call_vision_analysis(
    vision_config: AiConfig,
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[bytes, str, str]],
) -> dict:
    import logging

    logger = logging.getLogger(__name__)
    api_key = decrypt_value(vision_config.api_key)
    client = LLMClientFactory.create(
        provider=vision_config.provider,
        api_key=api_key,
        api_base=vision_config.api_base,
        model=vision_config.model,
        timeout=max(int(vision_config.timeout or 60), 120),
    )
    if not hasattr(client, "chat_with_images"):
        raise HTTPException(status_code=400, detail="Vision 客户端不支持读图")
    extra_body = _build_extra_body(vision_config)
    kwargs = {
        "system_prompt": system_prompt,
        "text": user_prompt,
        "temperature": min(float(vision_config.temperature or 0.3), 0.5),
        "max_tokens": resolve_vision_max_tokens(vision_config),
        "extra_body": extra_body or None,
    }
    try:
        return await client.chat_with_images(images=images, **kwargs)
    except Exception as exc:
        if len(images or []) <= 1:
            raise
        logger.warning("多图 Vision 调用失败，降级为失败步单图重试: %s", exc)
        return await client.chat_with_images(images=[images[-1]], **kwargs)


async def _find_cached_report_summary(
    project_id: int,
    report_type: str,
    record_id: int,
) -> Optional[AiGenerateRecord]:
    since = datetime.now() - timedelta(hours=REPORT_SUMMARY_CACHE_HOURS)
    records = (
        await AiGenerateRecord.filter(
            project_id=project_id,
            generate_type="report_summary",
            create_time__gte=since,
        )
        .order_by("-id")
        .limit(20)
    )
    for rec in records:
        inp = rec.input_summary if isinstance(rec.input_summary, dict) else {}
        if inp.get("report_type") == report_type and inp.get("record_id") == record_id:
            if rec.status == "accepted":
                return rec
    return None


def _summary_to_response(record: AiGenerateRecord) -> dict[str, Any]:
    out = record.output_content if isinstance(record.output_content, dict) else {}
    inp = record.input_summary if isinstance(record.input_summary, dict) else {}
    return {
        "summary_id": record.id,
        "report_type": inp.get("report_type"),
        "record_id": inp.get("record_id"),
        "report_name": inp.get("report_name"),
        "summary": out.get("summary") or "",
        "highlights": out.get("highlights") or [],
        "recommendations": out.get("recommendations") or [],
        "raw_response": out.get("raw_response") or "",
        "cached": True,
        "create_time": record.create_time.strftime("%Y-%m-%d %H:%M:%S") if record.create_time else "",
        "tokens_used": record.tokens_used or 0,
        "duration_ms": record.duration_ms or 0,
    }


async def _append_knowledge_context_to_prompt(
    user_prompt: str,
    project_id: int,
    *,
    knowledge_folder_ids: Optional[list[int]] = None,
    knowledge_document_ids: Optional[list[int]] = None,
) -> tuple[str, dict[str, Any]]:
    from app.modules.knowledge.knowledge_context import append_knowledge_context_to_prompt as _append

    return await _append(
        user_prompt,
        project_id,
        knowledge_folder_ids=knowledge_folder_ids,
        knowledge_document_ids=knowledge_document_ids,
        scene="failure_analysis",
    )


async def _execute_failure_analysis(
    *,
    project_id: int,
    target_type: str,
    target_id: int,
    username: str,
    ai_config_id: Optional[int],
    vision_config_id: Optional[int],
    use_vision: bool = False,
    force_refresh: bool = False,
    knowledge_folder_ids: Optional[list[int]] = None,
    knowledge_document_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_refs_resolve import resolve_knowledge_refs_for_scene
    from app.modules.ai.ai_project_settings import assert_failure_analysis_enabled

    try:
        await assert_failure_analysis_enabled(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    resolved_folders, resolved_docs = await resolve_knowledge_refs_for_scene(
        project_id,
        "failure_analysis",
        folder_ids=knowledge_folder_ids,
        document_ids=knowledge_document_ids,
    )
    has_knowledge_refs = bool(resolved_folders or resolved_docs)
    if not force_refresh and not has_knowledge_refs:
        cached = await _find_cached_analysis(project_id, target_type, target_id)
        if cached:
            data = _analysis_to_response(cached)
            data["cached"] = True
            return data

    prompt_vars, context_images, screenshot_url, case_name = await _load_target(
        target_type, target_id, project_id
    )

    try:
        system_prompt, user_prompt = await PromptManager.render("failure_analysis", prompt_vars)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    user_prompt, knowledge_meta = await _append_knowledge_context_to_prompt(
        user_prompt,
        project_id,
        knowledge_folder_ids=knowledge_folder_ids,
        knowledge_document_ids=knowledge_document_ids,
    )

    vision_config: Optional[AiConfig] = None
    text_config: Optional[AiConfig] = None
    t0 = time.time()
    usage_scene = "failure_analysis"

    vision_requested = bool(use_vision)
    use_vision = vision_requested and target_type in ("ui", "app") and bool(context_images)
    if use_vision:
        vision_config = await _get_vision_config(vision_config_id)
        if not vision_config or not _is_likely_vision_model(vision_config.model):
            use_vision = False

    try:
        if use_vision and vision_config:
            usage_scene = "failure_analysis_vision"
            try:
                llm_resp = await _call_vision_analysis(
                    vision_config, system_prompt, user_prompt, context_images
                )
                text_config = vision_config
            except Exception as vision_exc:
                logger.warning("Vision 分析失败，降级为纯文本: %s", vision_exc)
                use_vision = False
                text_config = await _get_ai_config(ai_config_id, scene="failure_analysis")
                llm_resp = await _call_llm(
                    system_prompt, user_prompt, text_config, min_timeout=90, max_retries=1
                )
        else:
            text_config = await _get_ai_config(ai_config_id, scene="failure_analysis")
            llm_resp = await _call_llm(system_prompt, user_prompt, text_config, min_timeout=90, max_retries=1)
    except Exception as e:
        llm_error = str(e)
        duration_ms = int((time.time() - t0) * 1000)
        fail_config = vision_config if use_vision and vision_config else text_config
        await log_ai_usage(
            fail_config,
            usage_scene,
            username=username,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"{target_type}#{target_id} {case_name}"[:500],
            output_summary=llm_error[:500],
            target_type=target_type,
            target_id=target_id,
        )
        raise

    duration_ms = int((time.time() - t0) * 1000)
    raw_response = llm_resp.get("content") or ""
    tokens_used = int(llm_resp.get("tokens") or 0)
    parsed = _extract_json_object(raw_response)

    status = "accepted" if parsed.get("root_cause") else "rejected"
    output_content = {**parsed, "raw_response": raw_response}
    input_summary = {
        "target_type": target_type,
        "target_id": target_id,
        "case_name": case_name,
        "vision_used": bool(use_vision and vision_config),
        "vision_requested": vision_requested,
        "vision_config_name": vision_config.name if vision_config and use_vision else None,
        "has_screenshot": bool(context_images),
        "screenshot_url": screenshot_url,
        "context_image_count": len(context_images or []),
    }

    record = await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="failure_analysis",
        input_summary=input_summary,
        output_content=output_content,
        status=status,
        ai_config_id=text_config.id if text_config else None,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=username,
    )

    await log_ai_usage(
        text_config,
        usage_scene,
        username=username,
        project_id=project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=f"{target_type}#{target_id} {case_name}"[:500],
        output_summary=(parsed.get("root_cause") or raw_response[:200])[:500],
        target_type=target_type,
        target_id=target_id,
        analysis_id=record.id,
        vision_used=bool(use_vision and vision_config),
        parsed=status == "accepted",
    )

    if status != "accepted":
        return {
            "analysis_id": record.id,
            "target_type": target_type,
            "target_id": target_id,
            "case_name": case_name,
            "raw_response": raw_response,
            "vision_used": bool(use_vision and vision_config),
            "parsed": False,
            "cached": False,
            "ok": False,
        }

    data = _analysis_to_response(record)
    data["cached"] = False
    data["ok"] = True
    if knowledge_meta.get("refs"):
        data["knowledge_sources"] = knowledge_meta
    return data


async def _assert_failure_analysis_record_env(project_id: int, env: dict | None) -> None:
    from app.modules.ai.ai_project_settings import (
        assert_failure_analysis_for_execution_env,
        load_ai_project_settings,
    )

    settings = await load_ai_project_settings(project_id)
    try:
        record_env = env if isinstance(env, dict) else {}
        assert_failure_analysis_for_execution_env(settings, record_env)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _load_target(
    target_type: str,
    target_id: int,
    project_id: int,
) -> tuple[dict[str, Any], list[tuple[bytes, str, str]], Optional[str], str]:
    """返回 prompt_vars, context_images, screenshot_url, case_name"""
    if target_type == "api":
        record = await ApiRunRecord.get_or_none(id=target_id, project_id=project_id)
        if not record:
            raise HTTPException(status_code=404, detail="接口执行记录不存在")
        if record.status not in ("failed", "error"):
            raise HTTPException(status_code=400, detail="仅支持分析失败或错误的执行记录")
        ctx = await build_api_failure_context(record)
        return ctx, [], None, ctx.get("case_name") or ""

    if target_type == "app":
        record = await AppCaseExecution.get_or_none(id=target_id, is_del=False).prefetch_related("case")
        if not record:
            raise HTTPException(status_code=404, detail="App 执行记录不存在")
        case = await record.case
        if case and int(case.project_id) != project_id:
            raise HTTPException(status_code=403, detail="无权访问该执行记录")
        if record.status not in ("fail", "failed", "error"):
            raise HTTPException(status_code=400, detail="仅支持分析失败或错误的执行记录")
        await _assert_failure_analysis_record_env(project_id, record.env)
        ctx, image_payload, screenshot_url = await build_app_failure_context(record)
        images: list[tuple[bytes, str, str]] = []
        if image_payload:
            images = [(image_payload[0], image_payload[1], "失败截图")]
        return ctx, images, screenshot_url, ctx.get("case_name") or ""

    record = await UiCaseExecution.get_or_none(id=target_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=404, detail="UI 执行记录不存在")
    if record.case and int(record.case.project_id) != project_id:
        raise HTTPException(status_code=403, detail="无权访问该执行记录")
    if not record.case:
        raise HTTPException(status_code=404, detail="关联用例不存在")
    if record.status not in ("fail", "failed", "error"):
        raise HTTPException(status_code=400, detail="仅支持分析失败或错误的执行记录")
    await _assert_failure_analysis_record_env(project_id, record.env)
    ctx, context_images, screenshot_url = await build_ui_failure_context(record)
    return ctx, context_images, screenshot_url, ctx.get("case_name") or ""


@router.post(
    "/failure",
    summary="AI 分析失败原因",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def analyze_failure(
    body: AnalyzeFailureRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")

    data = await _execute_failure_analysis(
        project_id=project_id,
        target_type=body.target_type,
        target_id=body.target_id,
        username=username,
        ai_config_id=body.ai_config_id,
        vision_config_id=body.vision_config_id,
        use_vision=body.use_vision,
        force_refresh=body.force_refresh,
        knowledge_folder_ids=body.knowledge_folder_ids,
        knowledge_document_ids=body.knowledge_document_ids,
    )

    if data.get("ok") is False:
        return StandardResponse(
            data=data,
            message="LLM 返回未能解析为结构化结果，请查看原始回复",
            code=200,
        )
    if data.get("cached"):
        return StandardResponse(data=data, message="已返回缓存的分析结果")
    return StandardResponse(data=data, message="分析完成")


@router.post(
    "/failure/batch",
    summary="批量 AI 分析失败用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def analyze_failure_batch(
    body: BatchFailureRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")

    targets: list[dict[str, Any]] = []
    if body.targets:
        for t in body.targets:
            targets.append({"target_type": t.target_type, "target_id": t.target_id, "case_name": "", "error_msg": ""})
    elif body.report_type and body.record_id is not None:
        targets = await collect_failure_targets(body.report_type, body.record_id, project_id, body.limit)
    else:
        raise HTTPException(status_code=400, detail="请提供 targets 或 report_type + record_id")

    if not targets:
        return StandardResponse(data={"results": [], "success_count": 0, "total": 0}, message="没有可分析的失败用例")

    results: list[dict[str, Any]] = []
    success_count = 0
    for item in targets:
        try:
            data = await _execute_failure_analysis(
                project_id=project_id,
                target_type=item["target_type"],
                target_id=int(item["target_id"]),
                username=username,
                ai_config_id=body.ai_config_id,
                vision_config_id=body.vision_config_id,
                use_vision=body.use_vision,
                force_refresh=body.force_refresh,
                knowledge_folder_ids=body.knowledge_folder_ids,
                knowledge_document_ids=body.knowledge_document_ids,
            )
            if item.get("case_name"):
                data["case_name"] = item["case_name"]
            if data.get("ok"):
                success_count += 1
            results.append(data)
        except HTTPException as e:
            results.append(
                {
                    "target_type": item["target_type"],
                    "target_id": item["target_id"],
                    "case_name": item.get("case_name"),
                    "ok": False,
                    "error": e.detail,
                }
            )
        except Exception as e:
            logger.exception("batch failure analysis error")
            results.append(
                {
                    "target_type": item["target_type"],
                    "target_id": item["target_id"],
                    "case_name": item.get("case_name"),
                    "ok": False,
                    "error": str(e),
                }
            )

    return StandardResponse(
        data={
            "results": results,
            "success_count": success_count,
            "total": len(results),
        },
        message=f"批量分析完成：{success_count}/{len(results)} 条成功",
    )


@router.post(
    "/report-summary",
    summary="AI 生成测试报告摘要",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def analyze_report_summary(
    body: ReportSummaryRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")

    if not body.force_refresh:
        cached = await _find_cached_report_summary(project_id, body.report_type, body.record_id)
        if cached:
            data = _summary_to_response(cached)
            return StandardResponse(data=data, message="已返回缓存的报告摘要")

    exec_data = await build_report_execution_data(body.report_type, body.record_id, project_id)
    import json as _json

    prompt_ctx = {"execution_data": _json.dumps(exec_data, ensure_ascii=False, indent=2)[:14000]}
    try:
        system_prompt, user_prompt = await PromptManager.render("report_summary", prompt_ctx)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    text_config = await _get_ai_config(body.ai_config_id, scene="failure_analysis")
    t0 = time.time()
    try:
        llm_resp = await _call_llm(system_prompt, user_prompt, text_config, min_timeout=90, max_retries=1)
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        await log_ai_usage(
            text_config,
            "report_summary",
            username=username,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"{body.report_type}#{body.record_id}"[:500],
            output_summary=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {str(e)}") from e
    duration_ms = int((time.time() - t0) * 1000)
    raw_response = llm_resp.get("content") or ""
    tokens_used = int(llm_resp.get("tokens") or 0)
    parsed = _extract_json_object(raw_response)

    status = "accepted" if parsed.get("summary") else "rejected"
    output_content = {**parsed, "raw_response": raw_response}
    input_summary = {
        "report_type": body.report_type,
        "record_id": body.record_id,
        "report_name": exec_data.get("name"),
    }

    record = await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="report_summary",
        input_summary=input_summary,
        output_content=output_content,
        status=status,
        ai_config_id=text_config.id if text_config else None,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=username,
    )

    await log_ai_usage(
        text_config,
        "report_summary",
        username=username,
        project_id=project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=f"{body.report_type}#{body.record_id} {exec_data.get('name', '')}"[:500],
        output_summary=(parsed.get("summary") or raw_response[:200])[:500],
        report_type=body.report_type,
        record_id=body.record_id,
        summary_id=record.id,
        parsed=status == "accepted",
    )

    if status != "accepted":
        return StandardResponse(
            data={"summary_id": record.id, "raw_response": raw_response, "parsed": False},
            message="LLM 返回未能解析为结构化摘要",
            code=200,
        )

    data = _summary_to_response(record)
    data["cached"] = False
    return StandardResponse(data=data, message="报告摘要生成完成")


@router.get(
    "/report-summary/by-record",
    summary="按执行记录查询最近报告摘要",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_report_summary_by_record(
    report_type: ReportType = Query(...),
    record_id: int = Query(...),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    cached = await _find_cached_report_summary(project_id, report_type, record_id)
    if not cached:
        return StandardResponse(data=None, message="暂无报告摘要")
    return StandardResponse(data=_summary_to_response(cached))


@router.get(
    "/failure/by-target",
    summary="按执行记录查询最近分析",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_analysis_by_target(
    target_type: Literal["api", "ui", "app"] = Query(...),
    target_id: int = Query(...),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    cached = await _find_cached_analysis(project_id, target_type, target_id)
    if not cached:
        return StandardResponse(data=None, message="暂无分析记录")
    return StandardResponse(data=_analysis_to_response(cached))


@router.get(
    "/failure/{analysis_id}",
    summary="分析结果详情",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_analysis_detail(
    analysis_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    record = await AiGenerateRecord.get_or_none(
        id=analysis_id,
        project_id=project_id,
        generate_type="failure_analysis",
    )
    if not record:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return StandardResponse(data=_analysis_to_response(record))
