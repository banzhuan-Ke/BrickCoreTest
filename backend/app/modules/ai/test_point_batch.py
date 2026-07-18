"""测试点批量生成：章节拆分规划与异步任务执行。"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.llm.ai_usage_log import log_ai_usage
from app.models.ai import AiRequirement, AiRequirementGenerateJob, AiRequirementTestPoint
from app.modules.ai.ai_prompts import PromptManager
from app.modules.ai.requirement_document import (
    build_interleaved_content,
    collect_image_indices,
    estimate_scope,
    resolve_sections,
    truncate_scope_text,
)
from app.modules.ai.test_analysis import (
    format_scope_section_titles,
    map_point_section_titles,
    normalize_test_points,
)

logger = logging.getLogger(__name__)

# 单批目标 token 上限（低于 WARN，留出生成输出空间）
DEFAULT_MAX_TOKENS_PER_BATCH = 10_000


class GenerateTestPointsBatchItem(BaseModel):
    name: str = Field(default="", description="批次名称")
    scope_section_ids: list[str] = Field(..., min_length=1)
    count: int = Field(default=30, ge=5, le=100)
    replace_existing: bool = Field(default=False, description="替换同名批次旧测试点")
    supplement: bool = Field(default=False, description="补充生成，避免重复")


class GenerateTestPointsBatchRequest(BaseModel):
    vision_config_id: Optional[int] = None
    text_config_id: Optional[int] = None
    replace_all: bool = False
    batches: list[GenerateTestPointsBatchItem] = Field(..., min_length=1, max_length=30)
    knowledge_folder_ids: Optional[list[int]] = None
    knowledge_document_ids: Optional[list[int]] = None


class PlanTestPointsBatchRequest(BaseModel):
    scope_section_ids: list[str] = Field(default_factory=list)
    default_count: int = Field(default=30, ge=5, le=100)
    max_tokens_per_batch: int = Field(default=DEFAULT_MAX_TOKENS_PER_BATCH, ge=3000, le=24000)


def _section_est_tokens(section: dict) -> int:
    chars = int(section.get("char_count") or 0)
    images = len(section.get("image_indices") or [])
    return int(chars / 1.6) + images * 600


def _suggest_count_for_sections(sections: list[dict], default: int) -> int:
    chars = sum(int(s.get("char_count") or 0) for s in sections)
    if chars <= 0:
        return default
    suggested = max(5, min(100, chars // 350))
    return min(default, suggested) if default else suggested


def _batch_name_from_sections(sections: list[dict], index: int) -> str:
    if not sections:
        return f"批次{index}"
    title = (sections[0].get("title") or "").strip()
    if len(sections) > 1 and title:
        return f"{title[:36]}等{len(sections)}节"
    return title[:40] if title else f"批次{index}"


def plan_test_point_batches(
    req: AiRequirement,
    scope_section_ids: list[str],
    *,
    default_count: int = 30,
    max_tokens_per_batch: int = DEFAULT_MAX_TOKENS_PER_BATCH,
) -> list[dict[str, Any]]:
    """按 token 预算将选中章节拆成多批（保持文档顺序）。"""
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    all_sections = meta.get("sections") or []
    if not all_sections:
        return [{
            "name": "全文",
            "scope_section_ids": scope_section_ids or ["sec-1"],
            "count": default_count,
            "estimated_tokens": 0,
            "section_titles": ["全文"],
        }]

    selected = resolve_sections(all_sections, scope_section_ids or None)
    if not selected:
        raise ValueError("请至少选择一个章节/范围")

    id_order = {s.get("id"): idx for idx, s in enumerate(all_sections) if s.get("id")}
    selected.sort(key=lambda s: id_order.get(s.get("id"), 999999))

    batches: list[dict[str, Any]] = []
    current_sections: list[dict] = []
    current_tokens = 0
    batch_idx = 0

    def _flush() -> None:
        nonlocal current_sections, current_tokens, batch_idx
        if not current_sections:
            return
        batch_idx += 1
        batches.append({
            "name": _batch_name_from_sections(current_sections, batch_idx),
            "scope_section_ids": [s.get("id") for s in current_sections if s.get("id")],
            "count": _suggest_count_for_sections(current_sections, default_count),
            "estimated_tokens": current_tokens,
            "exceeds_budget": current_tokens > max_tokens_per_batch,
            "section_titles": [(s.get("title") or "").strip() for s in current_sections],
        })
        current_sections = []
        current_tokens = 0

    for sec in selected:
        sec_tokens = _section_est_tokens(sec)
        if current_sections and current_tokens + sec_tokens > max_tokens_per_batch:
            _flush()
        current_sections.append(sec)
        current_tokens += sec_tokens
    _flush()
    return batches


def _batch_source_ref(batch_name: str) -> str:
    name = (batch_name or "").strip()
    return f"batch:{name}" if name else ""


def _requirement_sections(req: AiRequirement) -> list[dict]:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    return meta.get("sections") or []


async def _build_scoped_content_for_batch(
    req: AiRequirement,
    scope_section_ids: list[str],
    vision_config_id: Optional[int],
    *,
    username: str = "",
):
    from app.modules.ai.requirement_storage import load_images_from_meta
    from app.routers.ai.requirements import _analyze_images_with_vision, _get_ai_config

    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    blocks = meta.get("blocks") or []
    all_sections = meta.get("sections") or []
    if not all_sections:
        all_sections = [{
            "id": "sec-1",
            "title": "全文",
            "level": 1,
            "block_ids": [b.get("id") for b in blocks if b.get("id")],
            "char_count": len(req.original_content or ""),
            "image_indices": list(range(meta.get("image_count", 0))),
        }]
    selected_sections = resolve_sections(all_sections, scope_section_ids)
    if not selected_sections:
        raise HTTPException(status_code=400, detail="请至少选择一个章节/范围")

    scoped_image_indices = collect_image_indices(selected_sections)
    image_count = len(scoped_image_indices)
    vision_text_by_index: dict[int, str] = {}
    total_tokens = 0
    vision_report: dict = {"skipped": True, "message": "当前范围内无图片，已跳过读图"}

    if image_count > 0:
        if not vision_config_id:
            raise HTTPException(
                status_code=400,
                detail=f"选中范围包含 {image_count} 张图片，请选择 Vision 模型配置",
            )
        vision_config = await _get_ai_config(vision_config_id)
        vision_report = {
            "skipped": False,
            "config_name": vision_config.name,
            "model": vision_config.model,
            "provider": vision_config.provider,
        }
        images = load_images_from_meta(meta)
        vision_text_by_index, v_tokens, vision_detail = await _analyze_images_with_vision(
            vision_config,
            images,
            blocks,
            selected_sections,
            scoped_image_indices,
            project_id=req.project_id,
            username=username,
            requirement_id=req.id,
        )
        vision_report.update(vision_detail)
        total_tokens += v_tokens

    scoped_content = build_interleaved_content(blocks, selected_sections, vision_text_by_index)
    if not scoped_content.strip():
        scoped_content = (req.original_content or "")[:8000]
    scoped_content, _ = truncate_scope_text(scoped_content)
    scope_est = estimate_scope(scoped_content, image_count)
    if scope_est["level"] == "block":
        raise HTTPException(
            status_code=400,
            detail=scope_est["message"] + "；请减少本批章节后重试",
        )
    if not scoped_content.strip():
        raise HTTPException(status_code=400, detail="选中范围内无有效文字或图片内容")

    return scoped_content, vision_report, scope_est, selected_sections, total_tokens


async def execute_single_test_point_batch(
    req: AiRequirement,
    project_id: int,
    user_info: dict,
    *,
    vision_config_id: Optional[int],
    text_config_id: Optional[int],
    scope_section_ids: list[str],
    count: int,
    batch_name: str = "",
    replace_existing: bool = False,
    supplement: bool = False,
    knowledge_folder_ids: Optional[list[int]] = None,
    knowledge_document_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """执行单批测试点生成，返回 created_count / points / generate_report / tokens_used。"""
    from app.routers.ai.generate import _call_llm, _extract_json_array
    from app.routers.ai.requirements import _get_ai_config

    start_time = time.time()
    req_id = req.id
    username = user_info.get("username") or user_info.get("sub") or "system"
    batch_ref = _batch_source_ref(batch_name)

    if replace_existing and batch_ref:
        await AiRequirementTestPoint.filter(
            requirement_id=req_id, source_ref=batch_ref, is_del=False
        ).update(is_del=True)

    scoped_content, vision_report, scope_est, selected_sections, total_tokens = await _build_scoped_content_for_batch(
        req, scope_section_ids, vision_config_id, username=username
    )

    existing_titles = ""
    if supplement and batch_ref:
        existing = await AiRequirementTestPoint.filter(
            requirement_id=req_id, source_ref=batch_ref, is_del=False
        ).order_by("id")
        if existing:
            existing_titles = "\n".join(f"- {p.title}" for p in existing[:60])

    gen_config = await _get_ai_config(text_config_id)
    try:
        system_prompt, user_prompt = await PromptManager.render(
            "requirement_doc_to_test_points",
            {
                "requirement_name": req.name,
                "scoped_content": scoped_content,
                "scope_section_titles": format_scope_section_titles(selected_sections),
                "count": count,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if supplement and existing_titles:
        user_prompt += f"\n\n【已有测试点 · 请勿重复】\n{existing_titles}"

    from app.modules.knowledge.knowledge_context import append_knowledge_context_to_prompt

    user_prompt, _ = await append_knowledge_context_to_prompt(
        user_prompt,
        project_id,
        knowledge_folder_ids=knowledge_folder_ids,
        knowledge_document_ids=knowledge_document_ids,
        scene="test_points",
    )

    try:
        resp = await _call_llm(system_prompt, user_prompt, gen_config, min_timeout=600, max_retries=2)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            gen_config,
            "requirement_test_point",
            user_info=user_info,
            project_id=project_id,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"需求#{req_id} {req.name}, batch={batch_name}"[:500],
            output_summary=str(e)[:500],
            requirement_id=req_id,
            batch_name=batch_name,
        )
        raise
    raw_response = resp.get("content", "") or ""
    total_tokens += int(resp.get("tokens") or 0)
    default_section_ids = [s.get("id") for s in selected_sections if s.get("id")]
    normalized = normalize_test_points(_extract_json_array(raw_response), section_ids=default_section_ids)
    for item in normalized:
        mapped = map_point_section_titles(item, _requirement_sections(req))
        if mapped:
            item["section_ids"] = mapped

    created = []
    for idx, item in enumerate(normalized):
        pt = await AiRequirementTestPoint.create(
            requirement_id=req_id,
            project_id=project_id,
            title=item["title"],
            description=item.get("description"),
            test_type=item.get("test_type", "正向"),
            priority=item.get("priority", "P2"),
            module_path=item.get("module_path", ""),
            main_module=item.get("main_module", ""),
            sub_module=item.get("sub_module", ""),
            acceptance_ref=item.get("acceptance_ref"),
            section_ids=item.get("section_ids") or default_section_ids,
            source_ref=batch_ref or None,
            status="draft",
            sort_order=idx,
            extra=item.get("extra") or {},
            create_by=username,
        )
        created.append({
            "id": pt.id,
            "title": pt.title,
            "source_ref": pt.source_ref,
        })

    duration_ms = int((time.time() - start_time) * 1000)
    report = {
        "vision": vision_report,
        "scope_estimate": scope_est,
        "scope": {
            "section_ids": default_section_ids,
            "section_titles": format_scope_section_titles(selected_sections).split("、"),
        },
        "parsed_count": len(created),
        "requested_count": count,
        "model": gen_config.model,
        "config_name": gen_config.name,
        "batch_name": batch_name,
    }
    await log_ai_usage(
        gen_config,
        "requirement_test_point",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=f"需求#{req_id} {req.name}, batch={batch_name}"[:500],
        output_summary=f"生成 {len(created)} 条测试点",
        requirement_id=req_id,
        batch_name=batch_name,
    )
    return {
        "created_count": len(created),
        "points": created,
        "generate_report": report,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
    }


async def run_batch_test_points_core(
    req: AiRequirement,
    project_id: int,
    body: GenerateTestPointsBatchRequest,
    username: str,
    *,
    job: Optional[AiRequirementGenerateJob] = None,
) -> dict[str, Any]:
    from app.routers.ai.requirements import _batch_scope_fields

    user_info = {"username": username}
    req_id = req.id

    if body.replace_all:
        await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).update(is_del=True)

    if job:
        job.status = "running"
        job.total_batches = len(body.batches)
        job.done_batches = 0
        job.current_batch_name = ""
        job.batch_results = []
        await job.save()

    batch_start = time.time()
    batch_results: list[dict] = []
    total_tokens = 0
    last_report: dict = {}

    for idx, item in enumerate(body.batches):
        batch_name = (item.name or "").strip() or f"批次{idx + 1}"
        if job:
            job.current_batch_name = batch_name
            await job.save(update_fields=["current_batch_name", "update_time"])

        try:
            data = await execute_single_test_point_batch(
                req,
                project_id,
                user_info,
                vision_config_id=body.vision_config_id,
                text_config_id=body.text_config_id,
                scope_section_ids=item.scope_section_ids,
                count=item.count,
                batch_name=batch_name,
                replace_existing=item.replace_existing,
                supplement=item.supplement,
                knowledge_folder_ids=body.knowledge_folder_ids,
                knowledge_document_ids=body.knowledge_document_ids,
            )
            total_tokens += data["tokens_used"]
            gr = data.get("generate_report") or {}
            last_report = gr
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": True,
                "supplement": item.supplement,
                "requested_count": item.count,
                "created_count": data["created_count"],
                "parsed_count": gr.get("parsed_count", data["created_count"]),
                "tokens_used": data["tokens_used"],
                "duration_ms": data["duration_ms"],
                "generate_report": gr,
                "error": None,
                **_batch_scope_fields(req, item.scope_section_ids, gr),
            })
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": False,
                "created_count": 0,
                "error": detail,
                **_batch_scope_fields(req, item.scope_section_ids),
            })
        except Exception as e:
            logger.error("[test_point_batch] 批次 %s 失败: %s", batch_name, e, exc_info=True)
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": False,
                "created_count": 0,
                "error": str(e),
                **_batch_scope_fields(req, item.scope_section_ids),
            })

        if job:
            job.done_batches = idx + 1
            job.batch_results = batch_results
            job.tokens_used = total_tokens
            await job.save(update_fields=["done_batches", "batch_results", "tokens_used", "update_time"])

    duration_ms = int((time.time() - batch_start) * 1000)
    success_count = sum(1 for b in batch_results if b["success"])
    created_total = sum(b.get("created_count", 0) for b in batch_results)
    combined_report = {
        "batch_mode": True,
        "job_kind": "test_points",
        "batch_results": batch_results,
        "vision": last_report.get("vision") if last_report else None,
        "duration_ms": duration_ms,
        "tokens_used": total_tokens,
        "created_count": created_total,
    }

    if job:
        job.current_batch_name = ""
        job.tokens_used = total_tokens
        job.duration_ms = duration_ms
        job.generate_report = combined_report
        job.batch_results = batch_results
        job.finish_time = datetime.now()
        if success_count == 0:
            first_err = next((b["error"] for b in batch_results if b.get("error")), "全部批次失败")
            job.status = "failed"
            job.error = first_err
        else:
            job.status = "completed"
            if success_count < len(body.batches):
                job.error = f"部分批次失败（{success_count}/{len(body.batches)} 批成功）"
            else:
                job.error = None
        await job.save()

    if success_count == 0:
        first_err = next((b["error"] for b in batch_results if b.get("error")), "全部批次失败")
        raise HTTPException(status_code=500, detail=first_err)

    return {
        "created_count": created_total,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "generate_report": combined_report,
        "batch_results": batch_results,
        "success_count": success_count,
        "total_batches": len(body.batches),
    }


async def execute_test_points_generate_job(job: AiRequirementGenerateJob) -> None:
    payload = job.payload or {}
    body = GenerateTestPointsBatchRequest.model_validate(payload)
    req = await AiRequirement.get_or_none(
        id=job.requirement_id, project_id=job.project_id, is_del=False
    )
    if not req:
        job.status = "failed"
        job.error = "需求不存在或已删除"
        job.finish_time = datetime.now()
        await job.save()
        return
    try:
        await run_batch_test_points_core(req, job.project_id, body, job.create_by, job=job)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        if job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error = detail
            job.finish_time = datetime.now()
            await job.save()
    except Exception as e:
        logger.error("[test_point_batch] 异步任务 %s 失败: %s", job.id, e, exc_info=True)
        if job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error = str(e)
            job.finish_time = datetime.now()
            await job.save()
