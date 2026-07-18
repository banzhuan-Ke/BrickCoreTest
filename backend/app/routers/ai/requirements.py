"""
AI 需求文档 → 功能测试用例
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW, PROJECT_EDIT
from app.modules.ai.vision_image_cache import lookup_vision_result, store_vision_result
from app.core.case.case_naming import (
    BUILTIN_TEMPLATE_CATALOG,
    apply_naming_to_cases,
    build_section_context,
    default_naming_config,
    format_naming_rules_for_prompt,
    get_export_columns_for_template,
    load_naming_config,
    preview_title,
    resolve_all_slots,
    recalc_title_from_stored_slots,
    render_export_row,
    resolve_template,
    save_naming_config,
    suggest_template_id_for_profile,
)
from app.core.shared.export_profile import EXPORT_PROFILE_GENERIC, EXPORT_PROFILE_LABELS
from app.modules.ai.requirement_storage import (
    get_storage_summary,
    load_images_from_meta,
    load_requirement_source,
    save_requirement_images,
    save_requirement_source,
)
from app.core.case.case_steps import align_steps_expects, normalize_corner_quotes
from app.modules.ai.document_loader import load_document, SUPPORTED_EXTENSIONS
from app.modules.ai.ai_project_settings import (
    load_requirement_case_settings,
    resolve_soft_count_range,
)
from app.modules.ai.requirement_document import (
    BLOCK_ESTIMATED_INPUT_TOKENS,
    attach_section_parents,
    build_interleaved_content,
    collect_image_indices,
    compute_section_coverage,
    estimate_scope,
    recommend_case_count,
    resolve_sections,
    section_text,
    truncate_scope_text,
    vision_summary_to_text,
)
from app.modules.ai.zentao_case_types import DEFAULT_ZENTAO_CASE_TYPE, split_case_type_fields
from app.modules.ai.zentao_bindings import (
    apply_bindings_to_case_fields,
    bindings_for_export,
    build_requirement_case_extra,
    get_export_profile,
    get_requirement_bindings,
    load_project_bindings,
    merge_bindings,
    normalize_bindings,
    save_project_bindings,
    validate_bindings,
)
from app.modules.ai.zentao_case_export import (
    STAGE_OPTIONS,
    ZENTAO_DEFAULT_COLUMNS,
    build_xlsx_bytes,
    case_to_export_row,
    format_numbered_cell,
)
from app.core.platform.encryption import decrypt_value
from app.core.llm.ai_usage_log import log_ai_usage
from app.core.llm.llm_client import LLMClientFactory
from app.modules.ai.ai_prompts import PromptManager, append_extra_instructions
from app.models.ai import (
    AiConfig,
    AiGenerateRecord,
    AiRequirement,
    AiRequirementCase,
    AiRequirementGenerateJob,
    AiRequirementTestPoint,
    AiRequirementTestScheme,
)
from app.routers.ai.generate import _call_llm, _extract_json_array, _get_default_ai_config
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/requirements", tags=["AI需求用例"])

# 原文件存储目录（已迁移至 MinIO，见 requirement_storage；保留常量兼容旧引用）
REQ_FILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "static",
    "ai_requirements",
)

MAX_IMAGES_FOR_VISION = 20
VISION_CONTEXT_MAX_CHARS = 6000


def _resolve_project_id(user_info: dict, project_id: Optional[int] = None) -> int:
    """从 Query 参数或 JWT 解析项目 ID（与平台其他模块一致，优先 Query）"""
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    if not pid:
        raise HTTPException(status_code=400, detail="请先在顶部导航栏选择项目")
    return int(pid)


_TP_KEYWORDS_RE = re.compile(r"tp:#?(\d+)", re.I)


def _parse_test_point_ids_from_keywords(keywords: str) -> list[int]:
    if not keywords:
        return []
    seen: set[int] = set()
    out: list[int] = []
    for m in _TP_KEYWORDS_RE.findall(str(keywords)):
        tid = int(m)
        if tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def _case_test_point_ids(case: AiRequirementCase) -> list[int]:
    """从 extra 或 keywords 解析关联测试点 ID（兼容历史数据）。"""
    extra = getattr(case, "extra", None) or {}
    if isinstance(extra, dict):
        raw = extra.get("test_point_ids") or []
        if isinstance(raw, list) and raw:
            ids: list[int] = []
            seen: set[int] = set()
            for x in raw:
                try:
                    tid = int(x)
                except (TypeError, ValueError):
                    continue
                if tid not in seen:
                    seen.add(tid)
                    ids.append(tid)
            if ids:
                return ids
    return _parse_test_point_ids_from_keywords(getattr(case, "keywords", None) or "")


def _normalize_keywords_text(keywords: Any) -> str:
    """将 LLM 返回的 keywords（可能是 str / list）规范为字符串。"""
    if keywords is None:
        return ""
    if isinstance(keywords, str):
        return keywords.strip()
    if isinstance(keywords, (list, tuple)):
        parts = [str(x).strip() for x in keywords if x is not None and str(x).strip()]
        return ", ".join(parts)
    return str(keywords).strip()


def _merge_test_point_keywords(keywords: Any, test_point_ids: list[int]) -> str:
    kw = _normalize_keywords_text(keywords)
    if not test_point_ids:
        return kw
    if _TP_KEYWORDS_RE.search(kw):
        return kw
    suffix = " ".join(f"tp:#{i}" for i in test_point_ids[:8])
    return f"{kw} {suffix}".strip() if kw else suffix


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    code_block = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    for block in code_block:
        try:
            data = json.loads(block.strip())
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


def _requirement_to_dict(req: AiRequirement) -> dict:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    return {
        "id": req.id,
        "name": req.name,
        "source_type": req.source_type,
        "parse_status": req.parse_status,
        "parse_error": req.parse_error,
        "text_length": len(req.original_content or ""),
        "page_count": meta.get("page_count", 0),
        "image_count": meta.get("image_count", 0),
        "file_name": meta.get("file_name", ""),
        "storage": get_storage_summary(meta),
        "warnings": meta.get("warnings", []),
        "section_count": len(meta.get("sections") or []),
        "last_generate": meta.get("last_generate"),
        "export_defaults": meta.get("export_defaults") or {},
        "requirement_type": meta.get("requirement_type") or "default",
        "naming_template_id": meta.get("naming_template_id"),
        "zentao_effective": meta.get("zentao_effective"),
        "create_time": req.create_time.strftime("%Y-%m-%d %H:%M:%S") if req.create_time else "",
        "update_time": req.update_time.strftime("%Y-%m-%d %H:%M:%S") if req.update_time else "",
        "create_by": req.create_by,
    }


def _case_to_dict(case: AiRequirementCase) -> dict:
    tp_ids = _case_test_point_ids(case)
    extra = getattr(case, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    return {
        "id": case.id,
        "requirement_id": case.requirement_id,
        "product": getattr(case, "product", None) or "",
        "module": case.module,
        "func_module": case.module,
        "zentao_module": (extra.get("zentao_module") or "").strip(),
        "related_story": getattr(case, "related_story", None) or "",
        "title": case.title,
        "precondition": case.precondition or "",
        "steps": case.steps or [],
        "priority": case.priority,
        "type": case.type,
        "stage": getattr(case, "stage", None) or "系统测试阶段",
        "keywords": case.keywords,
        "status": case.status,
        "source_ref": case.source_ref,
        "section_ids": getattr(case, "section_ids", None) or [],
        "test_point_ids": tp_ids,
        "extra": extra,
        "naming_template_id": getattr(case, "naming_template_id", None),
        "naming_template_version": getattr(case, "naming_template_version", None),
        "naming_slots": getattr(case, "naming_slots", None) or {},
        "create_time": case.create_time.strftime("%Y-%m-%d %H:%M:%S") if case.create_time else "",
    }


async def _get_ai_config(config_id: Optional[int]) -> AiConfig:
    from app.modules.ai.ai_scene_config import resolve_config_for_scene
    return await resolve_config_for_scene("requirement_case", config_id)


async def _get_vision_config(config_id: Optional[int]) -> Optional[AiConfig]:
    from app.modules.ai.ai_scene_config import resolve_vision_config
    return await resolve_vision_config(config_id)


def _merge_vision_reports(reports: list[dict]) -> Optional[dict]:
    """合并多批次 Vision 报告，避免仅展示最后一批（无图批次会误显示已跳过）。"""
    reports = [r for r in reports if isinstance(r, dict)]
    if not reports:
        return None
    ran = [r for r in reports if not r.get("skipped")]
    if not ran:
        out = dict(reports[-1])
        if len(reports) > 1:
            out["batch_note"] = f"共 {len(reports)} 批，各批范围内均无图片"
        return out
    if len(ran) == 1 and len(reports) == 1:
        return ran[0]

    merged: dict = {
        "skipped": False,
        "partial": False,
        "config_name": ran[-1].get("config_name"),
        "model": ran[-1].get("model"),
        "provider": ran[-1].get("provider"),
        "image_total": 0,
        "ok_count": 0,
        "fail_count": 0,
        "images": [],
        "batches_with_vision": len(ran),
        "batches_skipped_no_images": len(reports) - len(ran),
    }
    for r in ran:
        merged["ok_count"] += int(r.get("ok_count") or 0)
        merged["fail_count"] += int(r.get("fail_count") or 0)
        merged["image_total"] += int(
            r.get("image_total") or len(r.get("images") or [])
        )
        merged["images"].extend(r.get("images") or [])
        merged["cache_hit_count"] = int(merged.get("cache_hit_count") or 0) + int(r.get("cache_hit_count") or 0)
        merged["cache_miss_count"] = int(merged.get("cache_miss_count") or 0) + int(r.get("cache_miss_count") or 0)
        if r.get("warning") and not merged.get("warning"):
            merged["warning"] = r["warning"]
        if r.get("partial"):
            merged["partial"] = True
    merged["success"] = merged["ok_count"] > 0 and merged["fail_count"] == 0
    if merged["fail_count"] > 0 and merged["ok_count"] > 0:
        merged["partial"] = True
    skipped_n = merged["batches_skipped_no_images"]
    if skipped_n:
        merged["batch_note"] = (
            f"共 {len(reports)} 批：{merged['batches_with_vision']} 批已读图，"
            f"{skipped_n} 批范围内无图片已跳过"
        )
    return merged


def _aggregate_batch_case_gen(batch_results: list[dict]) -> Optional[dict]:
    """汇总批量任务顶层 case_gen，避免只展示最后一批的条数语义。"""
    if not batch_results:
        return None
    success_batches = [b for b in batch_results if b.get("success")]
    modes: list[str] = []
    for b in batch_results:
        m = (b.get("count_mode") or "").strip().lower()
        if m in ("fixed", "auto"):
            modes.append(m)
    unique_modes = sorted(set(modes))
    mixed = len(unique_modes) > 1
    if mixed:
        count_mode = "mixed"
    elif unique_modes:
        count_mode = unique_modes[0]
    else:
        count_mode = "fixed"

    parsed_total = sum(
        int(b.get("parsed_count") or b.get("created_count") or 0) for b in success_batches
    )
    created_total = sum(int(b.get("created_count") or 0) for b in batch_results)
    tokens = sum(int(b.get("tokens_used") or 0) for b in batch_results)
    any_trunc = any(bool(b.get("partial_truncated")) for b in batch_results)

    # 与合计入库对齐：多批 auto 的总软区间 = 各批 soft_min/max 之和（不是包络 min/max）
    auto_range_pairs = [
        (int(b["soft_min_count"]), int(b["soft_max_count"]))
        for b in success_batches
        if b.get("count_mode") == "auto"
        and b.get("soft_min_count") is not None
        and b.get("soft_max_count") is not None
    ]
    fixed_requested = [
        int(b["requested_count"])
        for b in success_batches
        if b.get("count_mode") == "fixed" and b.get("requested_count") is not None
    ]

    last_cg: dict = {}
    for b in reversed(batch_results):
        cg = (b.get("generate_report") or {}).get("case_gen")
        if isinstance(cg, dict) and cg:
            last_cg = cg
            break

    agg_soft_min: Optional[int] = None
    agg_soft_max: Optional[int] = None
    if count_mode == "auto" and not mixed and auto_range_pairs:
        agg_soft_min = sum(lo for lo, _ in auto_range_pairs)
        agg_soft_max = sum(hi for _, hi in auto_range_pairs)

    if mixed:
        note = (
            f"批量含多种条数模式（{'/'.join(unique_modes)}）："
            f"成功 {len(success_batches)}/{len(batch_results)} 批，合计入库 {created_total} 条；明细见各批次"
        )
        range_explain = "见各批次明细"
    elif count_mode == "auto":
        note = (
            f"批量 AI 自定：成功 {len(success_batches)}/{len(batch_results)} 批，"
            f"合计入库 {created_total} 条"
        )
        if len(auto_range_pairs) <= 1:
            range_explain = (
                success_batches[0].get("range_explain") if success_batches else None
            )
        elif agg_soft_min is not None and agg_soft_max is not None:
            range_explain = (
                f"合计软区间 {agg_soft_min}～{agg_soft_max}（各批 soft_min/max 相加）；明细见各批次"
            )
        else:
            range_explain = "见各批次明细"
    else:
        note = (
            f"批量参考条数：成功 {len(success_batches)}/{len(batch_results)} 批，"
            f"合计入库 {created_total} 条"
        )
        range_explain = None

    return {
        "aggregated": True,
        "batch_mode": True,
        "success": bool(success_batches),
        "count_mode": count_mode,
        "mixed_modes": mixed,
        "modes": unique_modes,
        "batch_total": len(batch_results),
        "batch_success_count": len(success_batches),
        "requested_count": (
            sum(fixed_requested)
            if fixed_requested and count_mode == "fixed" and not mixed
            else None
        ),
        "soft_min_count": agg_soft_min,
        "soft_max_count": agg_soft_max,
        "range_explain": range_explain,
        "parsed_count": parsed_total,
        "actual_created_count": created_total,
        "partial_truncated": any_trunc,
        "count_note": note,
        "tokens": tokens or last_cg.get("tokens"),
        "config_name": None if mixed else last_cg.get("config_name"),
        "model": None if mixed else last_cg.get("model"),
        "provider": None if mixed else last_cg.get("provider"),
        # 顶层不展示单批补充语义，避免误导
        "supplement_mode": False,
    }


def _find_section_for_image(sections: list[dict], image_index: int) -> Optional[dict]:
    for sec in sections:
        if image_index in (sec.get("image_indices") or []):
            return sec
    return sections[0] if sections else None


async def _analyze_images_with_vision(
    vision_config: AiConfig,
    images: list[dict],
    blocks: list[dict],
    sections: list[dict],
    image_indices: Optional[list[int]] = None,
    *,
    project_id: Optional[int] = None,
    username: str = "",
    requirement_id: Optional[int] = None,
) -> tuple[dict[int, str], int, dict]:
    """返回 (image_index -> 读图文本, tokens, 报告)"""
    report = {
        "skipped": False,
        "config_name": vision_config.name,
        "model": vision_config.model,
        "provider": vision_config.provider,
        "image_total": len(images),
        "images": [],
        "ok_count": 0,
        "fail_count": 0,
        "cache_hit_count": 0,
        "cache_miss_count": 0,
    }
    if not images:
        report["skipped"] = True
        report["message"] = "未加载到图片文件（可能解析或存储异常）"
        return {}, 0, report

    allowed = set(image_indices if image_indices is not None else [img.get("index") for img in images])
    images = [img for img in images if img.get("index") in allowed]

    if not images:
        report["skipped"] = True
        report["message"] = "当前选中章节无图片"
        return {}, 0, report

    api_key = decrypt_value(vision_config.api_key)
    client = LLMClientFactory.create(
        provider=vision_config.provider,
        api_key=api_key,
        api_base=vision_config.api_base,
        model=vision_config.model,
        timeout=max(vision_config.timeout, 120),
    )
    if not hasattr(client, "chat_with_image"):
        raise HTTPException(status_code=400, detail="Vision 客户端不支持读图")

    system_prompt, user_template_base = await PromptManager.render(
        "requirement_doc_understand",
        {"doc_text_excerpt": "（见下方章节上下文）"},
    )

    vision_text_by_index: dict[int, str] = {}
    total_tokens = 0
    session_cache: dict[str, dict] = {}
    for img in images[:MAX_IMAGES_FOR_VISION]:
        idx = img.get("index", len(report["images"]) + 1)
        item = {"index": idx, "ok": False, "tokens": 0, "content": "", "error": None, "section_title": ""}
        sec = _find_section_for_image(sections, idx)
        if sec:
            item["section_title"] = sec.get("title") or ""
        ctx = section_text(blocks, sec) if sec else ""
        if not ctx.strip():
            ctx = "（该图附近无提取到正文，请仅根据图片内容分析）"
        excerpt = ctx[:VISION_CONTEXT_MAX_CHARS]
        user_text = user_template_base.replace("（见下方章节上下文）", excerpt)

        img_bytes = img.get("data") or b""
        cached = await lookup_vision_result(
            project_id=project_id,
            image_bytes=img_bytes,
            model=vision_config.model,
            session_cache=session_cache,
        )
        if cached:
            vision_text_by_index[idx] = cached["vision_text"]
            item["ok"] = True
            item["cached"] = True
            item["cache_source"] = cached.get("cache_source")
            item["content"] = (cached.get("raw_content") or cached["vision_text"])[:12000]
            report["ok_count"] += 1
            report["cache_hit_count"] += 1
            report["images"].append(item)
            continue

        report["cache_miss_count"] += 1
        img_t0 = time.time()
        try:
            resp = await client.chat_with_image(
                system_prompt=system_prompt,
                text=user_text,
                image_bytes=img_bytes,
                image_mime=img.get("mime", "image/png"),
                temperature=0.3,
                max_tokens=min(vision_config.max_tokens, 4096),
            )
            item["tokens"] = resp.get("tokens", 0)
            total_tokens += item["tokens"]
            raw_content = resp.get("content", "") or ""
            item["content"] = raw_content[:12000]
            item["ok"] = True
            report["ok_count"] += 1
            parsed = _extract_json_object(raw_content)
            if parsed:
                vision_text_by_index[idx] = vision_summary_to_text(parsed)
            else:
                vision_text_by_index[idx] = raw_content[:4000]
            await store_vision_result(
                project_id=project_id,
                image_bytes=img_bytes,
                model=vision_config.model,
                vision_text=vision_text_by_index[idx],
                raw_content=raw_content,
                tokens_used=item["tokens"],
                session_cache=session_cache,
            )
            if project_id:
                await log_ai_usage(
                    vision_config,
                    "requirement_doc_understand",
                    username=username,
                    project_id=project_id,
                    tokens_used=item["tokens"],
                    duration_ms=int((time.time() - img_t0) * 1000),
                    input_summary=f"需求#{requirement_id or '-'} · 图片 {idx}"[:500],
                    output_summary=(item["content"] or "")[:500],
                    requirement_id=requirement_id,
                    image_index=idx,
                )
        except Exception as e:
            logger.warning(f"[requirements] Vision 图片分析失败: {e}")
            err = str(e)
            item["error"] = err
            report["fail_count"] += 1
            vision_text_by_index[idx] = f"（读图失败: {err}）"
            if project_id:
                await log_ai_usage(
                    vision_config,
                    "requirement_doc_understand",
                    username=username,
                    project_id=project_id,
                    tokens_used=0,
                    duration_ms=int((time.time() - img_t0) * 1000),
                    status="failed",
                    input_summary=f"需求#{requirement_id or '-'} · 图片 {idx}"[:500],
                    output_summary=err[:500],
                    requirement_id=requirement_id,
                    image_index=idx,
                )
        report["images"].append(item)

    report["success"] = report["ok_count"] > 0 and report["fail_count"] == 0
    report["partial"] = report["ok_count"] > 0 and report["fail_count"] > 0
    report["vision_summary_preview"] = build_interleaved_content(
        blocks, sections, vision_text_by_index
    )[:12000]
    return vision_text_by_index, total_tokens, report


def _batch_source_ref(batch_name: str) -> str:
    name = (batch_name or "").strip()
    return f"batch:{name}" if name else ""


async def _load_existing_cases_for_batch(
    requirement_id: int,
    batch_name: str,
) -> list[AiRequirementCase]:
    ref = _batch_source_ref(batch_name)
    if not ref or ref == "batch:":
        return []
    return await AiRequirementCase.filter(
        requirement_id=requirement_id,
        source_ref=ref,
        is_del=False,
    ).order_by("id")


async def _delete_cases_for_batch(requirement_id: int, batch_name: str) -> int:
    ref = _batch_source_ref(batch_name)
    if not ref or ref == "batch:":
        return 0
    return await AiRequirementCase.filter(
        requirement_id=requirement_id,
        source_ref=ref,
        is_del=False,
    ).update(is_del=True)


def _format_existing_cases_for_prompt(
    cases: list[AiRequirementCase],
    max_list: int = 50,
) -> tuple[str, int]:
    """返回 (prompt 文本, 已有条数)"""
    n = len(cases)
    if not n:
        return "（本批次尚无已入库用例；请根据需求范围设计新用例，但仍会写入同一批次名）", 0
    lines: list[str] = []
    for i, c in enumerate(cases[:max_list], 1):
        steps = c.steps if isinstance(c.steps, list) else []
        step_parts: list[str] = []
        for j, st in enumerate(steps[:4]):
            if isinstance(st, dict):
                step_parts.append(f"{j + 1}.{(st.get('step') or '')[:50]}")
        step_brief = " | ".join(step_parts) if step_parts else "（无步骤）"
        lines.append(
            f"{i}. 模块:{c.module} | 功能点:{(c.naming_slots or {}).get('feature_point', '-')} | "
            f"标题:{c.title}\n"
            f"   描述:{(c.naming_slots or {}).get('case_description', '')[:120]}\n"
            f"   前置:{(c.precondition or '')[:100]}\n"
            f"   步骤:{step_brief}"
        )
    if n > max_list:
        lines.append(f"... 另有 {n - max_list} 条未列出，新用例须与全部已有用例区分")
    return "\n".join(lines), n


def _normalize_count_mode(raw: Optional[str]) -> str:
    mode = (raw or "fixed").strip().lower()
    return mode if mode in ("fixed", "auto") else "fixed"


def _case_count_quality_hint(
    requested: Optional[int],
    char_count: int,
    section_count: int,
    image_count: int = 0,
    *,
    count_mode: str = "fixed",
    soft_min: Optional[int] = None,
    soft_max: Optional[int] = None,
    range_explain: str = "",
) -> str:
    """注入 Prompt：条数目标 / AI 自定区间与范围体量说明"""
    sections = max(section_count, 1)
    rec = recommend_case_count(char_count, sections, image_count)
    recommended = rec["recommended_count"]
    core_min = rec["core_min_count"]

    grounding = (
        "【图文冲突】正文/表格文字与高保原型截图不一致时，**以文字为准**；"
        "禁止写入文字未定义的按钮、状态、筛选项或固定控件数量。"
    )

    if count_mode == "auto":
        lo = soft_min or rec["core_min_count"]
        hi = soft_max or recommended
        explain = range_explain or f"建议约 {recommended} 条"
        return (
            f"{grounding}\n"
            f"【AI 自定条数】不设精确目标条数。请按功能点覆盖生成，实际条数落在约 {lo}～{hi} 条。\n"
            f"{explain}\n"
            "优先覆盖各主要功能点的主路径/核心操作闭环，其次异常/权限/边界；"
            "禁止浅浏览凑数；禁止超过区间上限大量灌水。"
        )

    requested = int(requested or recommended)
    if requested < core_min or requested < int(recommended * 0.7):
        return (
            f"{grounding}\n"
            f"【条数偏少 · 优先保核心】参考目标仅 {requested} 条，相对本范围建议约 {recommended} 条偏少"
            f"（核心保底约 {core_min}）。\n"
            f"必须优先覆盖范围内**每个主要功能点的主路径/核心操作闭环**"
            f"（进入→关键动作含编辑/提交/重试等→可观察结果/刷新），"
            f"其次再安排少量异常/权限/边界；"
            f"**禁止**把额度花在「打开页面看看」、只读浏览、重复展示类浅用例上。"
            f"额度不足时宁可省略次要异常，也要保证核心交互与关键闭环不断档。"
        )
    if char_count < 2500 and requested > 8:
        return (
            f"{grounding}\n"
            f"【条数提示】本次范围约 {char_count} 字、{sections} 个章节，参考目标 {requested} 条可能偏高"
            f"（建议约 {recommended} 条）。"
            f"请按需求分支/边界/异常/权限拆分**高质量**用例，**实际条数可明显少于 {requested}**；"
            "禁止为凑条数输出大量「一步操作+一句泛化预期」的浅用例。"
        )
    if char_count < 5000 and requested > max(12, recommended + 4):
        return (
            f"{grounding}\n"
            f"【条数提示】参考目标 {requested} 条，范围约 {char_count} 字（建议约 {recommended} 条）。"
            "**质量与覆盖维度优先于凑满条数**；宁可少生成，也不要堆一步式用例。"
        )
    return (
        f"{grounding}\n"
        f"【条数提示】参考目标约 {requested} 条（本范围建议约 {recommended} 条），以覆盖要点为准，可略少或略多；"
        "每条须可独立执行，步骤与预期须具体、可验证。"
        "配比上先保证主路径与关键动作闭环，再覆盖异常/边界/权限。"
    )


def _case_count_expectation_note_v2(
    *,
    count_mode: str,
    requested: Optional[int],
    parsed: int,
    soft_min: int,
    soft_max: int,
    truncated: bool = False,
) -> str:
    if parsed <= 0:
        return "未解析到用例"
    parts: list[str] = []
    if count_mode == "auto":
        parts.append(f"AI 自定模式，软区间 {soft_min}～{soft_max}，实际入库 {parsed} 条")
        if parsed < soft_min:
            parts.append("低于软下限，可用补充生成补全缺口")
        elif parsed > soft_max:
            parts.append("超过软上限")
    else:
        req = int(requested or 0)
        if parsed == req:
            parts.append(f"与参考目标 {req} 条一致")
        elif parsed < req:
            parts.append(
                f"少于参考目标 {req} 条（实际入库 {parsed} 条），可对同范围使用「补充生成」或调高目标后重试"
            )
        else:
            parts.append(
                f"多于参考目标 {req} 条（实际入库 {parsed} 条）："
                "为模型在需求范围内自行扩展，非系统将多处条数相加"
            )
    if truncated:
        parts.append(f"已按项目上限截断并仅保留前 {parsed} 条（partial_truncated）")
    return "；".join(parts)


def _format_scope_section_titles(sections: list[dict]) -> str:
    titles = [(s.get("title") or "").strip() for s in (sections or []) if (s.get("title") or "").strip()]
    if not titles:
        return "（未指定章节标题）"
    return "、".join(titles[:20])


def _batch_scope_fields(
    req: AiRequirement,
    section_ids: Optional[list[str]],
    generate_report: Optional[dict] = None,
) -> dict[str, Any]:
    """批次结果中附带章节范围，便于历史报告展示"""
    scope = (generate_report or {}).get("scope") if isinstance(generate_report, dict) else None
    if isinstance(scope, dict) and scope.get("section_ids"):
        return {
            "scope_section_ids": list(scope.get("section_ids") or []),
            "scope_section_titles": list(scope.get("section_titles") or []),
        }
    ids = list(section_ids or [])
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    all_sections = meta.get("sections") or []
    selected = resolve_sections(all_sections, ids)
    return {
        "scope_section_ids": ids,
        "scope_section_titles": [(s.get("title") or "").strip() for s in selected if (s.get("title") or "").strip()],
    }


def _case_count_expectation_note(requested: int, parsed: int) -> str:
    """生成报告中的条数预期说明（不做截断，仅解释目标与实际差异）"""
    if parsed <= 0:
        return "未解析到用例"
    if parsed == requested:
        return f"与参考目标 {requested} 条一致"
    if parsed < requested:
        return (
            f"少于参考目标 {requested} 条（实际入库 {parsed} 条），"
            "可对同范围使用「补充生成」或调高目标后重试"
        )
    return (
        f"多于参考目标 {requested} 条（实际入库 {parsed} 条）："
        "为模型在需求范围内自行扩展，非系统将多处条数相加；平台按返回结果全部入库，未截断"
    )


def _format_existing_feature_points(cases: list[AiRequirementCase]) -> str:
    points: list[str] = []
    for c in cases:
        slots = c.naming_slots if isinstance(c.naming_slots, dict) else {}
        fp = (slots.get("feature_point") or "").strip()
        if fp and fp not in points:
            points.append(fp)
    if not points:
        return "（暂无已记录的功能点名称）"
    return "、".join(points[:80])


def _requirement_naming_meta(req: AiRequirement) -> tuple[str, Optional[str]]:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    req_type = (meta.get("requirement_type") or "default").strip() or "default"
    tpl_override = meta.get("naming_template_id") or None
    return req_type, tpl_override


def _requirement_story_code(req: Optional[AiRequirement]) -> str:
    if not req:
        return ""
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    return str(meta.get("story_code") or "").strip()


async def _resolve_naming_template(project_id: int, req: Optional[AiRequirement] = None):
    config = await load_naming_config(project_id)
    req_type, tpl_override = _requirement_naming_meta(req) if req else ("default", None)
    project_b = await load_project_bindings(project_id)
    export_profile = get_export_profile(project_b)
    template = resolve_template(config, req_type, tpl_override, export_profile)
    return config, template


def _normalize_cases(raw_cases: list) -> list[dict]:
    normalized = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        raw_steps = item.get("steps") or item.get("step_list")
        if raw_steps is None and (item.get("step") or item.get("expect")):
            raw_steps = [{"step": item.get("step", ""), "expect": item.get("expect", "")}]
        if isinstance(raw_steps, list) and item.get("expect_list"):
            expects = item.get("expect_list") or []
            if isinstance(expects, list):
                merged = []
                for i, st in enumerate(raw_steps):
                    if isinstance(st, dict):
                        merged.append(st)
                    else:
                        exp = expects[i] if i < len(expects) else ""
                        merged.append({"step": str(st), "expect": str(exp)})
                raw_steps = merged

        norm_steps = align_steps_expects(raw_steps)

        priority = str(item.get("priority", "2"))
        if priority.upper().startswith("P"):
            priority = {"P0": "1", "P1": "2", "P2": "3", "P3": "4"}.get(priority.upper(), "2")

        main_module = (item.get("main_module") or item.get("feature_module") or "").strip()
        sub_module = (item.get("sub_module") or item.get("page_module") or "").strip()
        feature_point = (item.get("feature_point") or "").strip()
        case_description = (
            item.get("case_description") or item.get("description") or ""
        ).strip()
        legacy_title = (item.get("title") or item.get("name") or "").strip()

        if not feature_point and not case_description and legacy_title:
            case_description = legacy_title
            legacy_title = ""

        if not feature_point and not case_description:
            continue

        func_module = (
            item.get("module")
            or main_module
            or sub_module
            or "默认模块"
        ).strip()

        zentao_type, test_design = split_case_type_fields(item, default_zentao=DEFAULT_ZENTAO_CASE_TYPE)

        row = {
            "module": func_module,
            "main_module": main_module or func_module,
            "sub_module": sub_module,
            "feature_point": feature_point,
            "case_description": case_description,
            "title": legacy_title,
            "precondition": normalize_corner_quotes(
                (item.get("precondition") or item.get("pre_condition") or "").strip()
            ),
            "steps": norm_steps,
            "priority": priority if priority in ("1", "2", "3", "4") else "2",
            "type": zentao_type,
            "test_design": test_design,
            "keywords": _normalize_keywords_text(
                item.get("keywords")
                or (item.get("tags") if item.get("tags") else "")
            ),
        }
        raw_tp = item.get("test_point_ids") or item.get("source_test_point_ids")
        if raw_tp is not None:
            if isinstance(raw_tp, (int, str)):
                raw_tp = [raw_tp]
            tp_ids = [int(x) for x in raw_tp if str(x).isdigit()]
            if tp_ids:
                row["test_point_ids"] = tp_ids
        normalized.append(row)
    return normalized


async def _effective_zentao_bindings(project_id: int, req: Optional[AiRequirement] = None) -> dict:
    project_b = await load_project_bindings(project_id)
    req_b = get_requirement_bindings(
        req.parsed_content if req and isinstance(req.parsed_content, dict) else None
    )
    return merge_bindings(project_b, req_b)


def _persist_requirement_bindings(req: AiRequirement, bindings: dict, effective: dict) -> None:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    meta["export_defaults"] = normalize_bindings(bindings)
    meta["zentao_effective"] = effective
    req.parsed_content = meta


class ZentaoBindingsBody(BaseModel):
    export_profile: Optional[str] = Field(
        default=None,
        description="导出目标：zentao（禅道 XLSX）| generic（通用 XLSX）",
    )
    product: str = Field(default="", description="所属产品")
    module: str = Field(default="", description="所属模块（禅道路径）")
    related_story: str = Field(default="", description="相关研发需求")


class ExportDefaultsBody(ZentaoBindingsBody):
    """需求级覆盖（可只填部分字段，其余继承项目配置）"""
    pass


class CaseNamingPreviewBody(BaseModel):
    template_id: Optional[str] = Field(default=None, description="指定模板ID，默认当前生效")
    title_template: Optional[str] = Field(
        default=None,
        description="表单中未保存的标题模板，传入则覆盖已存模板用于预览",
    )
    sample_slots: dict = Field(default_factory=dict, description="预览用语义槽位")


class CaseNamingConfigBody(BaseModel):
    active_template_id: str = Field(default="default")
    templates: list[dict] = Field(default_factory=list)


class RequirementNamingMetaBody(BaseModel):
    requirement_type: str = Field(default="default", description="需求类型，用于匹配模板")
    naming_template_id: Optional[str] = Field(default=None, description="显式指定模板ID")


class UpdateRequirementBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="需求名称")


class RecalcTitlesRequest(BaseModel):
    case_ids: Optional[list[int]] = Field(default=None, description="指定用例ID，空则全部草稿")


class GenerateCasesRequest(BaseModel):
    vision_config_id: Optional[int] = Field(default=None, description="Vision 模型配置（文档含图时必填）")
    case_gen_config_id: Optional[int] = Field(default=None, description="用例生成模型配置（DeepSeek 等文本模型）")
    count_mode: str = Field(
        default="fixed",
        description="条数模式：fixed=参考条数，auto=AI 自定条数（仅受软区间约束）",
    )
    count: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="fixed 模式参考条数；auto 模式可省略（后端仍会落库建议条数与软区间）",
    )
    replace_existing: bool = Field(default=False, description="是否替换已有用例")
    supplement_batch_name: Optional[str] = Field(
        default=None,
        description="补充生成：按批次名匹配 source_ref=batch:名称 的已有用例并追加，不删旧用例",
    )
    export_defaults: Optional[ExportDefaultsBody] = Field(default=None, description="禅道导出默认值")
    scope_section_ids: Optional[list[str]] = Field(
        default=None,
        description="生成范围：章节 ID 列表，空或不传表示全部章节",
    )
    extra_instructions: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="用户额外要求，优先于默认 Prompt 规则",
    )
    batch_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="写入 source_ref=batch:名称；单次生成建议传章节/批次名便于筛选",
    )
    knowledge_folder_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文件夹 ID 列表",
    )
    knowledge_document_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文档 ID 列表",
    )


class ScopeEstimateRequest(BaseModel):
    scope_section_ids: Optional[list[str]] = None


class GenerateCasesBatchItem(BaseModel):
    name: str = Field(default="", description="批次名称（展示用）")
    scope_section_ids: list[str] = Field(..., min_length=1, description="本批章节 ID")
    count_mode: str = Field(default="fixed", description="本批条数模式：fixed | auto")
    count: Optional[int] = Field(default=None, ge=1, le=100, description="fixed 模式本批参考条数")
    supplement: bool = Field(
        default=False,
        description="补充生成：按本批名称匹配已有用例发给模型后追加",
    )
    replace: bool = Field(
        default=False,
        description="替换本批：生成前删除同批次名已有用例后重新生成",
    )
    export_defaults: Optional[ExportDefaultsBody] = Field(
        default=None,
        description="本批禅道覆盖（可选，留空继承项目/需求）",
    )
    extra_instructions: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="本批额外要求（可选，覆盖批量级默认）",
    )


class RetryGenerateBatchRequest(BaseModel):
    batch_index: int = Field(..., ge=0, description="batch_results 中的批次序号")
    count_mode: Optional[str] = Field(None, description="覆盖本批条数模式：fixed | auto")
    count: Optional[int] = Field(None, ge=1, le=100, description="覆盖本批参考条数（fixed）")
    vision_config_id: Optional[int] = None
    case_gen_config_id: Optional[int] = None
    extra_instructions: Optional[str] = Field(None, max_length=2000)


class GenerateCasesBatchRequest(BaseModel):
    vision_config_id: Optional[int] = None
    case_gen_config_id: Optional[int] = None
    replace_existing: bool = Field(default=False, description="开始前清空已有用例")
    extra_instructions: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="批量生成默认额外要求，各批次可单独覆盖",
    )
    knowledge_folder_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文件夹 ID 列表",
    )
    knowledge_document_ids: Optional[list[int]] = Field(
        default=None,
        description="可选：引用资料库文档 ID 列表",
    )
    batches: list[GenerateCasesBatchItem] = Field(..., min_length=1, max_length=30)


class UpdateCaseRequest(BaseModel):
    module: Optional[str] = Field(default=None, description="功能模块（非禅道路径）")
    title: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[list] = None
    priority: Optional[str] = None
    type: Optional[str] = None
    keywords: Optional[str] = None
    status: Optional[str] = None


class ImportToLibraryRequest(BaseModel):
    case_ids: list[int] = Field(..., min_length=1, description="工作区用例 ID 列表")
    duplicate_title_mode: str = Field(
        default="skip",
        description="标题+模块重复时：skip 跳过，overwrite 覆盖库中已有用例",
    )


class BatchDeleteCasesRequest(BaseModel):
    case_ids: list[int] = Field(default_factory=list)


@router.post("/upload", summary="上传需求文档", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def upload_requirement(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    project_id: int = Form(..., description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)

    file_name = file.filename or "requirement.pdf"
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式，支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    try:
        loaded = load_document(content, file_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[requirements] 文档解析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档解析失败: {str(e)}")

    req_name = (name or os.path.splitext(file_name)[0]).strip() or "未命名需求"

    requirement = await AiRequirement.create(
        project_id=project_id,
        name=req_name,
        source_type=loaded.source_type,
        original_content=loaded.text,
        parsed_content={},
        parse_status="parsed",
        create_by=user_info.get("username", ""),
    )

    try:
        storage_meta = save_requirement_source(requirement.id, file_name, content)
    except RuntimeError as e:
        logger.error(f"[requirements] 文档存储失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    _apply_parsed_document(requirement, loaded, file_name, storage_meta)
    await requirement.save()

    return StandardResponse(
        message="上传成功",
        data=_requirement_to_dict(requirement),
    )


def _apply_parsed_document(
    requirement: AiRequirement,
    loaded,
    file_name: str,
    storage_meta: dict,
) -> None:
    """将解析结果写入需求（保留 export_defaults 等用户配置）"""
    meta = requirement.parsed_content if isinstance(requirement.parsed_content, dict) else {}
    preserved = {
        k: meta[k]
        for k in ("export_defaults", "zentao_effective", "last_generate", "requirement_type", "naming_template_id")
        if k in meta
    }
    image_meta = save_requirement_images(requirement.id, loaded.images)
    file_path = storage_meta.get("file_path") or ""
    requirement.source_type = loaded.source_type
    requirement.original_content = loaded.text
    requirement.parse_status = "parsed"
    requirement.parse_error = None
    requirement.parsed_content = {
        "file_name": file_name,
        "file_path": file_path,
        "storage": storage_meta.get("storage"),
        "page_count": loaded.page_count,
        "image_count": len(image_meta),
        "images": image_meta,
        "warnings": loaded.warnings,
        "blocks": loaded.blocks or [],
        "sections": loaded.sections or [],
        "source_type": loaded.source_type,
        **preserved,
    }


@router.post(
    "/{req_id}/reparse-document",
    summary="重新解析文档结构",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def reparse_requirement_document(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    """从已保存的源文件重新解析章节/块/图片（无需重新上传）"""
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    file_name = meta.get("file_name") or "requirement.docx"
    try:
        content, file_name = load_requirement_source(meta)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="源文件不存在，请重新上传需求文档")
    if not content:
        raise HTTPException(status_code=400, detail="源文件为空")

    try:
        loaded = load_document(content, file_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[requirements] 重新解析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重新解析失败: {str(e)}")

    storage_meta = meta.get("storage") if isinstance(meta.get("storage"), dict) else {}
    storage_payload = {
        "storage": storage_meta,
        "file_path": meta.get("file_path") or storage_meta.get("source_key", ""),
    }
    _apply_parsed_document(req, loaded, file_name, storage_payload)
    await req.save()

    data = _requirement_to_dict(req)
    data["zentao_effective"] = await _effective_zentao_bindings(project_id, req)
    return StandardResponse(
        message=f"重新解析成功：{len(loaded.sections or [])} 个章节，{len(loaded.images)} 张图片",
        data=data,
    )


@router.get("", summary="需求列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_requirements(
    page: int = 1,
    size: int = 20,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)

    query = AiRequirement.filter(project_id=project_id, is_del=False).order_by("-id")
    total = await query.count()
    items = await query.offset((page - 1) * size).limit(size)

    case_counts: dict[int, int] = {}
    if items:
        req_ids = [r.id for r in items]
        rid_list = await AiRequirementCase.filter(
            requirement_id__in=req_ids, is_del=False
        ).values_list("requirement_id", flat=True)
        for rid in rid_list:
            case_counts[rid] = case_counts.get(rid, 0) + 1

    rows = []
    for req in items:
        row = _requirement_to_dict(req)
        row["case_count"] = case_counts.get(req.id, 0)
        rows.append(row)

    return StandardResponse(data={"list": rows, "total": total, "page": page, "size": size})


@router.get("/export-template", summary="禅道用例导出列模板", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_export_template(user_info: dict = Depends(is_authenticated)):
    """返回默认禅道导入列（后续可扩展为可配置模板）"""
    from app.modules.ai.zentao_bindings import DEFAULT_BINDINGS

    return StandardResponse(
        data={
            "name": "禅道默认模板",
            "columns": ZENTAO_DEFAULT_COLUMNS,
            "defaults": DEFAULT_BINDINGS,
            "stage_options": list(STAGE_OPTIONS),
            "stage_rule": "优先级 1 → 冒烟测试阶段，其余 → 系统测试阶段（代码自动映射，无需 AI 生成）",
        }
    )


@router.get("/zentao-bindings", summary="获取禅道绑定配置", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_zentao_bindings(
    project_id: Optional[int] = Query(None, description="项目ID"),
    requirement_id: Optional[int] = Query(None, description="需求ID，传入则返回合并后的有效配置"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    project_b = await load_project_bindings(project_id)
    req_b = normalize_bindings(None)
    effective = project_b
    if requirement_id:
        req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
        if req:
            req_b = get_requirement_bindings(
                req.parsed_content if isinstance(req.parsed_content, dict) else None
            )
            effective = merge_bindings(project_b, req_b)
    export_profile = get_export_profile(effective)
    return StandardResponse(
        data={
            "project": project_b,
            "requirement": req_b,
            "effective": effective,
            "export_profile": export_profile,
            "export_profile_options": [
                {"value": k, "label": v} for k, v in EXPORT_PROFILE_LABELS.items()
            ],
            "stage_rule": "priority in [1] → 冒烟测试阶段，否则 → 系统测试阶段",
        }
    )


@router.put("/zentao-bindings", summary="保存项目级禅道绑定", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def put_project_zentao_bindings(
    body: ZentaoBindingsBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    try:
        saved = await save_project_bindings(project_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StandardResponse(message="项目禅道配置已保存", data=saved)


@router.get(
    "/case-naming",
    summary="获取项目用例命名配置",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_case_naming_config(
    project_id: Optional[int] = Query(None, description="项目ID"),
    requirement_id: Optional[int] = Query(None, description="需求ID，传入则返回匹配的生效模板"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    config = await load_naming_config(project_id)
    req_type, tpl_override = "default", None
    if requirement_id:
        req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
        if req:
            req_type, tpl_override = _requirement_naming_meta(req)
    project_b = await load_project_bindings(project_id)
    export_profile = get_export_profile(project_b)
    active = resolve_template(config, req_type, tpl_override, export_profile)
    return StandardResponse(
        data={
            "config": config,
            "active_template": active,
            "requirement_type": req_type,
            "naming_template_id": tpl_override,
            "export_profile": export_profile,
            "builtin_templates": BUILTIN_TEMPLATE_CATALOG,
            "suggested_template_id": suggest_template_id_for_profile(export_profile),
        }
    )


@router.put(
    "/case-naming",
    summary="保存项目用例命名配置（项目管理员）",
    dependencies=[Depends(require_permissions(PROJECT_EDIT))],
)
async def put_case_naming_config(
    body: CaseNamingConfigBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    try:
        saved = await save_naming_config(project_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    active = resolve_template(saved)
    return StandardResponse(message="用例命名配置已保存", data={"config": saved, "active_template": active})


@router.post(
    "/case-naming/preview",
    summary="预览用例标题组装结果",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def preview_case_naming(
    body: CaseNamingPreviewBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    requirement_id: Optional[int] = Query(None, description="需求ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    config = await load_naming_config(project_id)
    req_type, tpl_override = "default", body.template_id
    if requirement_id and not tpl_override:
        req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
        if req:
            req_type, tpl_override = _requirement_naming_meta(req)
    template = resolve_template(config, req_type, tpl_override)
    if body.title_template is not None:
        template = {**template, "title_template": body.title_template}
    result = preview_title(template, body.sample_slots or {})
    return StandardResponse(data={**result, "template_id": template.get("id"), "template_version": template.get("version")})


@router.put(
    "/{req_id}/naming-meta",
    summary="设置需求类型与命名模板",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def put_requirement_naming_meta(
    req_id: int,
    body: RequirementNamingMetaBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    meta["requirement_type"] = (body.requirement_type or "default").strip() or "default"
    if body.naming_template_id:
        meta["naming_template_id"] = body.naming_template_id.strip()
    else:
        meta.pop("naming_template_id", None)
    req.parsed_content = meta
    await req.save()
    config = await load_naming_config(project_id)
    active = resolve_template(config, meta["requirement_type"], meta.get("naming_template_id"))
    return StandardResponse(
        message="需求命名设置已保存",
        data={
            "requirement_type": meta["requirement_type"],
            "naming_template_id": meta.get("naming_template_id"),
            "active_template": active,
        },
    )


@router.put("/{req_id}/zentao-bindings", summary="保存需求级禅道绑定覆盖", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def put_requirement_zentao_bindings(
    req_id: int,
    body: ExportDefaultsBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    project_b = await load_project_bindings(project_id)
    req_b = normalize_bindings(body.model_dump())
    effective = merge_bindings(project_b, req_b)
    _persist_requirement_bindings(req, req_b, effective)
    await req.save()
    return StandardResponse(message="需求禅道配置已保存", data={"effective": effective})


@router.post(
    "/{req_id}/cases/reapply-bindings",
    summary="按当前绑定刷新全部用例禅道字段与适用阶段",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def reapply_case_bindings(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    effective = await _effective_zentao_bindings(project_id, req)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"禅道配置不完整，缺少：{', '.join(missing)}",
        )
    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False)
    updated = 0
    for case in cases:
        data = apply_bindings_to_case_fields(
            {"priority": case.priority},
            effective,
        )
        case.product = data["product"]
        case.related_story = data["related_story"]
        case.stage = data["stage"]
        extra = case.extra if isinstance(case.extra, dict) else {}
        case.extra = build_requirement_case_extra(effective, existing=extra)
        await case.save(update_fields=["product", "related_story", "stage", "extra"])
        updated += 1
    return StandardResponse(message=f"已刷新 {updated} 条用例的禅道字段与适用阶段", data={"count": updated})


@router.get("/{req_id}/document-structure", summary="文档章节结构", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_document_structure(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    sections = meta.get("sections") or []
    if not sections and req.original_content:
        sections = [{
            "id": "sec-1",
            "title": "全文",
            "level": 1,
            "char_count": len(req.original_content or ""),
            "image_indices": list(range(meta.get("image_count", 0))),
        }]
    else:
        sections = attach_section_parents([dict(s) for s in sections])
    scoped = resolve_sections(sections, None)
    blocks = meta.get("blocks") or []
    est = estimate_scope(
        build_interleaved_content(blocks, scoped, {}),
        len(collect_image_indices(scoped, blocks)),
        section_count=len(scoped),
    )
    rc = await load_requirement_case_settings(project_id)
    soft = resolve_soft_count_range(est.get("recommended_count") or 4, rc)
    est.update(soft)
    return StandardResponse(
        data={
            "sections": sections,
            "source_type": meta.get("source_type", req.source_type),
            "image_count": meta.get("image_count", 0),
            "text_length": len(req.original_content or ""),
            "estimate_all": est,
            "requirement_case_settings": rc,
        }
    )


@router.post("/{req_id}/estimate-scope", summary="预估生成范围 Token", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def estimate_generate_scope(
    req_id: int,
    body: ScopeEstimateRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    sections = meta.get("sections") or []
    blocks = meta.get("blocks") or []
    selected = resolve_sections(sections, body.scope_section_ids)
    if not selected:
        raise HTTPException(status_code=400, detail="请至少选择一个章节")
    img_n = len(collect_image_indices(selected, blocks))
    text = build_interleaved_content(blocks, selected, {})
    text, _ = truncate_scope_text(text)
    est = estimate_scope(text, img_n, section_count=len(selected))
    est["selected_section_count"] = len(selected)
    est["selected_section_ids"] = [s.get("id") for s in selected]
    rc = await load_requirement_case_settings(project_id)
    soft = resolve_soft_count_range(est.get("recommended_count") or 4, rc)
    est.update(soft)
    return StandardResponse(data=est)


@router.get(
    "/{req_id}/section-coverage",
    summary="章节覆盖检查",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_section_coverage(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    pending_section_ids: Optional[str] = Query(
        None,
        description="待生成章节ID，逗号分隔（队列预览）",
    ),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    sections = meta.get("sections") or []
    if sections:
        sections = attach_section_parents([dict(s) for s in sections])
    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False)
    coverage = compute_section_coverage(sections, [_case_to_dict(c) for c in cases])
    pending: set[str] = set()
    if pending_section_ids:
        pending = {x.strip() for x in pending_section_ids.split(",") if x.strip()}
    if pending:
        all_ids = {s.get("id") for s in sections if s.get("id")}
        projected = set(coverage["covered_section_ids"]) | (pending & all_ids)
        coverage["pending_section_ids"] = sorted(pending & all_ids)
        coverage["projected_covered_count"] = len(projected)
        coverage["projected_uncovered_count"] = len(all_ids) - len(projected)
    return StandardResponse(data=coverage)


@router.get("/{req_id}", summary="需求详情", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_requirement(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    data = _requirement_to_dict(req)
    data["zentao_effective"] = await _effective_zentao_bindings(project_id, req)
    data["original_content"] = req.original_content[:5000] + (
        "..." if len(req.original_content or "") > 5000 else ""
    )
    return StandardResponse(data=data)


@router.put("/{req_id}", summary="更新需求基本信息", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_requirement(
    req_id: int,
    body: UpdateRequirementBody,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="需求名称不能为空")
    req.name = name
    await req.save()
    return StandardResponse(message="需求名称已更新", data=_requirement_to_dict(req))


@router.delete("/{req_id}", summary="删除需求", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_requirement(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    req.is_del = True
    await req.save()
    await AiRequirementCase.filter(requirement_id=req_id).update(is_del=True)
    await AiRequirementTestPoint.filter(requirement_id=req_id).update(is_del=True)
    await AiRequirementTestScheme.filter(requirement_id=req_id).update(is_del=True)
    await AiRequirementGenerateJob.filter(
        requirement_id=req_id,
        status__in=["pending", "running"],
    ).update(status="cancelled")
    return StandardResponse(message="删除成功（已复制到功能用例库的用例不受影响）")


async def _execute_generate_cases(
    req: AiRequirement,
    project_id: int,
    user_info: dict,
    body: GenerateCasesRequest,
    *,
    batch_name: str = "",
    replace_existing: Optional[bool] = None,
    zentao_effective_override: Optional[dict] = None,
    persist_job_record: bool = False,
) -> dict:
    """单次范围生成用例，返回 cases / generate_report / tokens / duration_ms"""
    start_time = time.time()
    username = user_info.get("username", "")
    supplement_name = (body.supplement_batch_name or "").strip()
    is_supplement = bool(supplement_name)
    if body.supplement_batch_name is not None and body.supplement_batch_name.strip() == "":
        raise HTTPException(status_code=400, detail="补充生成须填写有效的批次名称")
    if is_supplement and body.replace_existing:
        raise HTTPException(status_code=400, detail="「补充」与「替换已有」不能同时开启")
    do_replace = False if is_supplement else (
        body.replace_existing if replace_existing is None else replace_existing
    )
    if is_supplement and not batch_name:
        batch_name = supplement_name

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
    selected_sections = resolve_sections(all_sections, body.scope_section_ids)
    if not selected_sections:
        raise HTTPException(status_code=400, detail="请至少选择一个章节/范围")

    scoped_image_indices = collect_image_indices(selected_sections)
    image_count = len(scoped_image_indices)

    project_b = await load_project_bindings(project_id)
    if body.export_defaults and zentao_effective_override is None:
        req_b = normalize_bindings(body.export_defaults.model_dump())
        _persist_requirement_bindings(req, req_b, merge_bindings(project_b, req_b))
        await req.save()
        meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}

    effective = zentao_effective_override or await _effective_zentao_bindings(project_id, req)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"请先在「禅道导入配置」中填写：{', '.join(missing)}。"
                "（可在项目级保存默认值，本需求可覆盖）"
            ),
        )

    gen_config = await _get_ai_config(body.case_gen_config_id)

    vision_text_by_index: dict[int, str] = {}
    total_tokens = 0
    vision_config_id = body.vision_config_id
    vision_report: dict = {"skipped": True, "message": "当前范围内无图片，已跳过读图"}

    if image_count > 0:
        if not vision_config_id:
            raise HTTPException(
                status_code=400,
                detail=f"选中范围包含 {image_count} 张图片，请选择 Vision 模型配置（如通义 qwen-vl）",
            )
        from app.modules.ai.ai_scene_config import resolve_vision_config
        vision_config = await resolve_vision_config(vision_config_id)
        if not vision_config:
            raise HTTPException(status_code=400, detail="未配置 Vision 模型，请在场景绑定或模型配置中设置")
        vision_report = {
            "skipped": False,
            "config_name": vision_config.name,
            "model": vision_config.model,
            "provider": vision_config.provider,
            "likely_vision": LLMClientFactory.is_likely_vision_model(vision_config.model),
        }
        if not vision_report["likely_vision"]:
            logger.warning(
                f"[requirements] 配置 {vision_config.model} 可能不支持 Vision，仍尝试调用"
            )
            vision_report["warning"] = (
                f"模型 {vision_config.model} 可能不支持读图，建议使用 qwen-vl-max 等 VL 模型"
            )
        images = load_images_from_meta(meta)
        vision_report["image_count_doc"] = image_count
        vision_report["scope_section_ids"] = body.scope_section_ids
        vision_text_by_index, v_tokens, vision_detail = await _analyze_images_with_vision(
            vision_config,
            images,
            blocks,
            selected_sections,
            scoped_image_indices,
            project_id=project_id,
            username=username,
            requirement_id=req.id,
        )
        vision_report.update(vision_detail)
        total_tokens += v_tokens

    scoped_content = build_interleaved_content(
        blocks, selected_sections, vision_text_by_index
    )
    if not scoped_content.strip():
        scoped_content = (req.original_content or "")[:8000]
    scoped_content, truncated = truncate_scope_text(scoped_content)
    scope_est = estimate_scope(
        scoped_content,
        image_count,
        section_count=len(selected_sections),
    )
    if scope_est["level"] == "block":
        raise HTTPException(
            status_code=400,
            detail=scope_est["message"] + "；请减少勾选的章节后重试",
        )

    if not scoped_content.strip():
        raise HTTPException(status_code=400, detail="选中范围内无有效文字或图片内容")

    # 条数模式：fixed=参考条数；auto=AI 自定（仅软区间）
    count_mode = _normalize_count_mode(getattr(body, "count_mode", None))
    rc_settings = await load_requirement_case_settings(project_id)
    hard_max = int(rc_settings.get("fixed_count_hard_max") or 50)
    base_recommended = int(scope_est.get("recommended_count") or 4)
    soft = resolve_soft_count_range(base_recommended, rc_settings)
    soft_min = int(soft["soft_min_count"])
    soft_max = int(soft["soft_max_count"])
    range_explain = soft["range_explain"]
    max_cap = int(soft["auto_count_max_cap"])

    if count_mode == "auto":
        requested_count = None
        prompt_count = soft_max  # 模板仍需 {{count}}，以软上限作参考锚点
    else:
        requested_count = int(body.count) if body.count is not None else 15
        if requested_count > hard_max:
            raise HTTPException(
                status_code=400,
                detail=f"参考条数不能超过项目上限 {hard_max}（可在 AI 模型配置 → 功能用例生成中调整）",
            )
        prompt_count = requested_count

    existing_cases_text = ""
    existing_count = 0
    existing_feature_points = ""
    if is_supplement:
        existing_rows = await _load_existing_cases_for_batch(req.id, supplement_name)
        existing_cases_text, existing_count = _format_existing_cases_for_prompt(existing_rows)
        existing_feature_points = _format_existing_feature_points(existing_rows)

    naming_config, naming_template = await _resolve_naming_template(project_id, req)
    naming_rules = format_naming_rules_for_prompt(naming_template)
    section_ctx = build_section_context(selected_sections, all_sections)
    count_hint = _case_count_quality_hint(
        requested_count,
        scope_est.get("char_count", len(scoped_content)),
        len(selected_sections),
        scope_est.get("image_count", image_count),
        count_mode=count_mode,
        soft_min=soft_min,
        soft_max=soft_max,
        range_explain=range_explain,
    )

    try:
        if is_supplement:
            system_prompt, user_prompt = await PromptManager.render(
                "requirement_doc_supplement_cases",
                {
                    "requirement_name": req.name,
                    "batch_name": supplement_name,
                    "scoped_content": scoped_content,
                    "count": prompt_count,
                    "existing_cases": existing_cases_text,
                    "existing_count": existing_count,
                    "existing_feature_points": existing_feature_points,
                    "naming_rules": naming_rules,
                },
            )
            user_prompt = f"{count_hint}\n\n{user_prompt}"
        else:
            system_prompt, user_prompt = await PromptManager.render("requirement_doc_to_cases", {
                "requirement_name": req.name,
                "scoped_content": scoped_content,
                "doc_text": scoped_content,
                "vision_summary": "（已合并至下方结构化需求内容，请直接阅读 scoped_content）",
                "count": prompt_count,
                "naming_rules": naming_rules,
                "scope_section_titles": _format_scope_section_titles(selected_sections),
                "count_quality_hint": count_hint,
            })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    extra_instructions = (body.extra_instructions or "").strip()
    user_prompt = append_extra_instructions(user_prompt, extra_instructions)

    from app.modules.knowledge.knowledge_context import build_knowledge_context
    from app.modules.knowledge.knowledge_refs_resolve import resolve_knowledge_refs_for_scene

    k_folder_ids, k_doc_ids = await resolve_knowledge_refs_for_scene(
        project_id,
        "case_generate",
        folder_ids=body.knowledge_folder_ids,
        document_ids=body.knowledge_document_ids,
    )
    knowledge_meta: dict = {}
    if k_folder_ids or k_doc_ids:
        kctx = await build_knowledge_context(
            project_id,
            folder_ids=k_folder_ids,
            document_ids=k_doc_ids,
        )
        knowledge_meta = {
            "refs": kctx.get("refs") or [],
            "resolved_folder_ids": k_folder_ids or [],
            "resolved_document_ids": k_doc_ids or [],
        }
        ktext = (kctx.get("knowledge_context") or "").strip()
        if ktext:
            user_prompt += (
                "\n\n## 迭代测试资料库参考\n"
                "以下材料来自项目资料库，生成用例时可参考历史 Bug、测试范围与计划，"
                "但须以当前需求文档为准；可针对高频缺陷模块补充回归用例。\n\n"
                f"{ktext}"
            )
        if kctx.get("bug_export_summary"):
            user_prompt += f"\n\n## Bug 导出摘要\n{kctx['bug_export_summary']}"
        from app.modules.knowledge.knowledge_bug_hints import summarize_bug_modules

        bug_hints = await summarize_bug_modules(
            project_id,
            folder_ids=k_folder_ids,
            document_ids=k_doc_ids,
        )
        if bug_hints.get("hint_text"):
            user_prompt += f"\n\n## Bug 模块覆盖提示\n{bug_hints['hint_text']}"
            knowledge_meta["bug_hints"] = bug_hints

    prompt_len = len(user_prompt or "")
    logger.info(
        "[requirements] 用例生成 LLM 调用 model=%s batch=%s prompt_len=%s mode=%s count=%s soft=%s~%s extra=%s",
        gen_config.model,
        batch_name or supplement_name or "-",
        prompt_len,
        count_mode,
        requested_count,
        soft_min,
        soft_max,
        bool(extra_instructions),
    )
    try:
        resp = await _call_llm(
            system_prompt,
            user_prompt,
            gen_config,
            min_timeout=600,
            max_retries=2,
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            gen_config,
            "requirement_case",
            user_info=user_info,
            project_id=project_id,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"需求#{req.id} {req.name}"[:500],
            output_summary=str(e)[:500],
            requirement_id=req.id,
            batch_name=batch_name or supplement_name or None,
        )
        logger.error(
            "[requirements] 用例生成 LLM 失败 model=%s prompt_len=%s: %s",
            gen_config.model,
            prompt_len,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"AI 生成失败: {str(e)}"
                "（多为模型服务超时；可缩小本批章节、减少参考条数，或在 AI 配置中增大 timeout 后重试该批）"
            ),
        )

    raw_response = resp.get("content", "") or ""
    case_gen_tokens = resp.get("tokens", 0)
    total_tokens += case_gen_tokens
    raw_cases = _extract_json_array(raw_response)
    normalized = _normalize_cases(raw_cases)
    named_cases, naming_warnings = apply_naming_to_cases(
        normalized,
        naming_template,
        effective,
        section_ctx,
        batch_name=batch_name or supplement_name,
        requirement_name=req.name,
        requirement_id=req.id,
        story_code=_requirement_story_code(req),
    )
    cases_data = [
        apply_bindings_to_case_fields(c, effective)
        for c in named_cases
    ]

    parsed_raw_n = len(cases_data)
    partial_truncated = False
    # 超绝对上限：保留前 N 条 + 强告警（避免静默丢数据或半截 JSON）
    if parsed_raw_n > max_cap:
        cases_data = cases_data[:max_cap]
        partial_truncated = True
        logger.warning(
            "[requirements] 用例条数 %s 超过上限 %s，已截断入库",
            parsed_raw_n,
            max_cap,
        )

    parsed_n = len(cases_data)
    count_note = _case_count_expectation_note_v2(
        count_mode=count_mode,
        requested=requested_count,
        parsed=parsed_n,
        soft_min=soft_min,
        soft_max=soft_max,
        truncated=partial_truncated,
    )
    if is_supplement:
        count_note = (
            f"补充批次「{supplement_name}」：已有 {existing_count} 条，本次新增入库 {parsed_n} 条。"
            + count_note
        )
    case_gen_report = {
        "success": bool(cases_data),
        "config_name": gen_config.name,
        "model": gen_config.model,
        "provider": gen_config.provider,
        "tokens": case_gen_tokens,
        "count_mode": count_mode,
        "requested_count": requested_count,
        "base_recommended_count": base_recommended,
        "soft_min_count": soft_min,
        "soft_max_count": soft_max,
        "range_explain": range_explain,
        "parsed_count": parsed_n,
        "parsed_raw_count": parsed_raw_n,
        "actual_created_count": parsed_n,
        "partial_truncated": partial_truncated,
        "count_note": count_note,
        "supplement_mode": is_supplement,
        "supplement_batch_name": supplement_name if is_supplement else None,
        "existing_cases_count": existing_count if is_supplement else 0,
        "extra_instructions": extra_instructions[:500] if extra_instructions else None,
        "naming_warnings": naming_warnings[:20],
        "naming_template_id": naming_template.get("id"),
        "naming_template_version": naming_template.get("version"),
        "raw_response": raw_response[:15000],
    }
    generate_report = {
        "vision": vision_report,
        "case_gen": case_gen_report,
        "naming_warnings": naming_warnings[:20],
        "scope": {
            "section_ids": [s.get("id") for s in selected_sections],
            "section_titles": [s.get("title") for s in selected_sections],
            "truncated": truncated,
            "estimate": scope_est,
        },
        "duration_ms": 0,
        "tokens_used": total_tokens,
    }
    if knowledge_meta.get("refs"):
        generate_report["knowledge_sources"] = knowledge_meta

    if not cases_data:
        duration_ms = int((time.time() - start_time) * 1000)
        await AiGenerateRecord.create(
            project_id=project_id,
            generate_type="requirement_case",
            input_summary={"requirement_id": req.id, "name": req.name, "batch_name": batch_name or None},
            output_content={"raw_response": raw_response, "cases": []},
            status="rejected",
            ai_config_id=gen_config.id,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
            create_by=user_info.get("username", ""),
        )
        await log_ai_usage(
            gen_config,
            "requirement_case",
            user_info=user_info,
            project_id=project_id,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
            input_summary=f"需求#{req.id} {req.name}"[:500],
            output_summary="JSON 解析失败",
            requirement_id=req.id,
            batch_name=batch_name or supplement_name or None,
            parse_ok=False,
        )
        raise HTTPException(
            status_code=500,
            detail="AI 返回内容无法解析为用例 JSON，请重试或调整模型/Prompt",
        )

    if do_replace:
        await AiRequirementCase.filter(requirement_id=req.id).update(is_del=True)

    created = []
    username = user_info.get("username", "")
    source_ref = f"batch:{batch_name}" if batch_name else None
    batch_section_ids = [s.get("id") for s in selected_sections if s.get("id")]
    for item in cases_data:
        case = await AiRequirementCase.create(
            requirement_id=req.id,
            project_id=project_id,
            product=item.get("product", ""),
            module=item["module"],
            related_story=item.get("related_story", ""),
            title=item["title"],
            naming_template_id=item.get("naming_template_id"),
            naming_template_version=item.get("naming_template_version"),
            naming_slots=item.get("naming_slots") or {},
            precondition=item["precondition"],
            steps=item["steps"],
            priority=item["priority"],
            type=item["type"],
            stage=item.get("stage", "系统测试阶段"),
            keywords=item["keywords"],
            status="draft",
            source_ref=source_ref,
            section_ids=batch_section_ids,
            extra=build_requirement_case_extra(
                effective,
                existing={"test_design": item["test_design"]} if item.get("test_design") else None,
            ),
            create_by=username,
        )
        created.append(_case_to_dict(case))

    created_case_ids = [c["id"] for c in created if c.get("id")]
    generate_report["created_case_ids"] = created_case_ids
    case_gen_report["actual_created_count"] = len(created)

    duration_ms = int((time.time() - start_time) * 1000)
    generate_report["duration_ms"] = duration_ms
    if batch_name:
        generate_report["batch_name"] = batch_name
    await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="requirement_case",
        input_summary={
            "requirement_id": req.id,
            "name": req.name,
            "count_mode": count_mode,
            "count": requested_count,
            "soft_min_count": soft_min,
            "soft_max_count": soft_max,
            "batch_name": batch_name or None,
        },
        output_content={
            "cases": cases_data,
            "raw_response": raw_response[:10000],
            "generate_report": generate_report,
        },
        status="imported",
        ai_config_id=gen_config.id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        create_by=username,
    )

    await log_ai_usage(
        gen_config,
        "requirement_case",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=f"需求#{req.id} {req.name}, mode={count_mode}, count={requested_count}"[:500],
        output_summary=f"生成 {len(created)} 条用例",
        requirement_id=req.id,
        batch_name=batch_name or supplement_name or None,
        vision_used=not vision_report.get("skipped", True),
    )

    req.parse_status = "parsed"
    req.parse_error = None
    meta["last_generate"] = {
        "case_count": len(created),
        "created_case_ids": created_case_ids,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "generate_report": generate_report,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta["zentao_effective"] = effective
    req.parsed_content = meta
    await req.save()

    result = {
        "cases": created,
        "created_count": len(created),
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "generate_report": generate_report,
    }
    if persist_job_record:
        username = user_info.get("username", "")
        job = await _persist_single_generate_job(
            req=req,
            project_id=project_id,
            username=username,
            body=body,
            data=result,
            batch_name=batch_name,
        )
        result["job_id"] = job.id
    return result


def _job_to_dict(job: AiRequirementGenerateJob) -> dict:
    total = job.total_batches or 0
    done = job.done_batches or 0
    pct = int(done / total * 100) if total else 0
    gr = job.generate_report if isinstance(job.generate_report, dict) else {}
    created_ids = gr.get("created_case_ids") or []
    return {
        "id": job.id,
        "requirement_id": job.requirement_id,
        "project_id": job.project_id,
        "status": job.status,
        "total_batches": total,
        "done_batches": done,
        "current_batch_name": job.current_batch_name or "",
        "progress_percent": pct,
        "batch_results": job.batch_results or [],
        "generate_report": gr,
        "payload": job.payload if isinstance(job.payload, dict) else {},
        "error": job.error,
        "tokens_used": job.tokens_used,
        "duration_ms": job.duration_ms,
        "case_count": len(created_ids),
        "create_by": job.create_by,
        "create_time": job.create_time.isoformat() if job.create_time else None,
        "finish_time": job.finish_time.isoformat() if job.finish_time else None,
    }


async def _persist_single_generate_job(
    *,
    req: AiRequirement,
    project_id: int,
    username: str,
    body: GenerateCasesRequest,
    data: dict,
    batch_name: str,
) -> AiRequirementGenerateJob:
    """单次同步生成写入任务表，便于历史记录查看"""
    gr = data.get("generate_report") or {}
    cg = gr.get("case_gen") or {}
    batch_results = [
        {
            "name": batch_name or "单批生成",
            "success": True,
            "supplement": bool((body.supplement_batch_name or "").strip()),
            "replace": bool(body.replace_existing and not (body.supplement_batch_name or "").strip()),
            "count_mode": cg.get("count_mode") or _normalize_count_mode(getattr(body, "count_mode", None)),
            "requested_count": cg.get("requested_count"),
            "base_recommended_count": cg.get("base_recommended_count"),
            "soft_min_count": cg.get("soft_min_count"),
            "soft_max_count": cg.get("soft_max_count"),
            "range_explain": cg.get("range_explain"),
            "partial_truncated": bool(cg.get("partial_truncated")),
            "created_count": data.get("created_count", 0),
            "parsed_count": data.get("created_count", 0),
            "generate_report": gr,
            "tokens_used": data.get("tokens_used", 0),
            "count_note": cg.get("count_note"),
            **_batch_scope_fields(req, body.scope_section_ids, gr),
        }
    ]
    return await AiRequirementGenerateJob.create(
        requirement_id=req.id,
        project_id=project_id,
        status="completed",
        total_batches=1,
        done_batches=1,
        current_batch_name="",
        payload=body.model_dump(),
        batch_results=batch_results,
        generate_report=gr,
        tokens_used=int(data.get("tokens_used") or 0),
        duration_ms=int(data.get("duration_ms") or 0),
        create_by=username,
        finish_time=datetime.now(),
    )


async def _run_batch_generate_core(
    req: AiRequirement,
    project_id: int,
    body: GenerateCasesBatchRequest,
    username: str,
    *,
    job: Optional[AiRequirementGenerateJob] = None,
) -> dict:
    """按批次队列生成用例；可选 job 参数用于异步任务进度回写。"""
    user_info = {"username": username}
    req_id = req.id

    project_b = await load_project_bindings(project_id)
    effective = await _effective_zentao_bindings(project_id, req)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"请先在「禅道导入配置」中填写：{', '.join(missing)}。"
                "（可在项目级保存默认值，本需求可覆盖）"
            ),
        )

    if body.replace_existing:
        await AiRequirementCase.filter(requirement_id=req_id).update(is_del=True)

    if job:
        job.status = "running"
        job.total_batches = len(body.batches)
        job.done_batches = 0
        job.current_batch_name = ""
        job.batch_results = []
        await job.save()

    batch_start = time.time()
    batch_results: list[dict] = []
    all_created_case_ids: list[int] = []
    total_tokens = 0
    last_report: dict = {}
    vision_reports: list[dict] = []

    for idx, item in enumerate(body.batches):
        batch_name = (item.name or "").strip() or f"批次{idx + 1}"
        if job:
            job.current_batch_name = batch_name
            await job.save(update_fields=["current_batch_name", "update_time"])

        item_effective = effective
        if item.export_defaults:
            req_b = normalize_bindings(item.export_defaults.model_dump())
            item_effective = merge_bindings(project_b, req_b)
            miss = validate_bindings(item_effective)
            if miss:
                fail_mode = _normalize_count_mode(getattr(item, "count_mode", None))
                batch_results.append({
                    "index": idx,
                    "name": batch_name,
                    "success": False,
                    "supplement": bool(item.supplement),
                    "replace": bool(item.replace),
                    "count_mode": fail_mode,
                    "requested_count": item.count if fail_mode == "fixed" else None,
                    "created_count": 0,
                    "error": f"禅道配置不完整：{', '.join(miss)}",
                    **_batch_scope_fields(req, item.scope_section_ids),
                })
                if job:
                    job.done_batches = idx + 1
                    job.batch_results = batch_results
                    await job.save(update_fields=["done_batches", "batch_results", "update_time"])
                continue

        use_supplement = bool(item.supplement)
        use_replace = bool(item.replace)
        if use_supplement and use_replace:
            fail_mode = _normalize_count_mode(getattr(item, "count_mode", None))
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": False,
                "supplement": False,
                "replace": False,
                "count_mode": fail_mode,
                "requested_count": item.count if fail_mode == "fixed" else None,
                "created_count": 0,
                "error": "「补充」与「替换本批」不能同时开启",
                **_batch_scope_fields(req, item.scope_section_ids),
            })
            if job:
                job.done_batches = idx + 1
                job.batch_results = batch_results
                await job.save(update_fields=["done_batches", "batch_results", "update_time"])
            continue
        if use_supplement:
            batch_name = (item.name or "").strip() or batch_name
        if use_replace:
            await _delete_cases_for_batch(req_id, batch_name)

        batch_extra = (body.extra_instructions or "").strip()
        item_extra = (item.extra_instructions or "").strip()
        item_count_mode = _normalize_count_mode(getattr(item, "count_mode", None))
        single_body = GenerateCasesRequest(
            vision_config_id=body.vision_config_id,
            case_gen_config_id=body.case_gen_config_id,
            count_mode=item_count_mode,
            count=item.count if item_count_mode == "fixed" else None,
            replace_existing=False,
            export_defaults=None,
            scope_section_ids=item.scope_section_ids,
            supplement_batch_name=batch_name if use_supplement else None,
            extra_instructions=item_extra or batch_extra or None,
            knowledge_folder_ids=body.knowledge_folder_ids,
            knowledge_document_ids=body.knowledge_document_ids,
        )
        zentao_override = item_effective if item.export_defaults else None
        try:
            data = await _execute_generate_cases(
                req,
                project_id,
                user_info,
                single_body,
                batch_name=batch_name,
                replace_existing=False,
                zentao_effective_override=zentao_override,
            )
            total_tokens += data["tokens_used"]
            last_report = data["generate_report"]
            gr = data.get("generate_report") or {}
            if gr.get("vision"):
                vision_reports.append(gr["vision"])
            cg = gr.get("case_gen") or {}
            batch_created_ids = (
                (data.get("generate_report") or {}).get("created_case_ids")
                or [c.get("id") for c in data.get("cases", []) if c.get("id")]
            )
            all_created_case_ids.extend(batch_created_ids)
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": True,
                "supplement": use_supplement,
                "replace": use_replace,
                "count_mode": cg.get("count_mode") or item_count_mode,
                "requested_count": cg.get("requested_count"),
                "base_recommended_count": cg.get("base_recommended_count"),
                "soft_min_count": cg.get("soft_min_count"),
                "soft_max_count": cg.get("soft_max_count"),
                "range_explain": cg.get("range_explain"),
                "partial_truncated": bool(cg.get("partial_truncated")),
                "created_count": data["created_count"],
                "created_case_ids": batch_created_ids,
                "parsed_count": cg.get("parsed_count", data["created_count"]),
                "existing_cases_count": cg.get("existing_cases_count", 0),
                "count_note": cg.get("count_note"),
                "tokens_used": data["tokens_used"],
                "duration_ms": data["duration_ms"],
                "generate_report": data["generate_report"],
                "error": None,
                **_batch_scope_fields(req, item.scope_section_ids, gr),
            })
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": False,
                "supplement": use_supplement,
                "replace": use_replace,
                "count_mode": item_count_mode,
                "requested_count": item.count if item_count_mode == "fixed" else None,
                "created_count": 0,
                "error": detail,
                **_batch_scope_fields(req, item.scope_section_ids),
            })
        except Exception as e:
            logger.error(f"[requirements] 批次 {batch_name} 失败: {e}", exc_info=True)
            batch_results.append({
                "index": idx,
                "name": batch_name,
                "success": False,
                "supplement": use_supplement,
                "replace": use_replace,
                "count_mode": item_count_mode,
                "requested_count": item.count if item_count_mode == "fixed" else None,
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

    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False).order_by("id")
    all_case_dicts = [_case_to_dict(c) for c in cases]

    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    combined_report = {
        "batch_mode": True,
        "batch_results": batch_results,
        "created_case_ids": all_created_case_ids,
        "vision": _merge_vision_reports(vision_reports)
        if vision_reports
        else (last_report.get("vision") if last_report else None),
        "case_gen": _aggregate_batch_case_gen(batch_results),
        "duration_ms": duration_ms,
        "tokens_used": total_tokens,
    }
    meta["last_generate"] = {
        "case_count": len(all_case_dicts),
        "created_case_ids": all_created_case_ids,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "generate_report": combined_report,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    req.parsed_content = meta
    await req.save()

    result = {
        "cases": all_case_dicts,
        "created_count": created_total,
        "tokens_used": total_tokens,
        "duration_ms": duration_ms,
        "generate_report": combined_report,
        "batch_results": batch_results,
        "success_count": success_count,
        "total_batches": len(body.batches),
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

    return result


async def _sync_job_report_from_batch_results(
    job: AiRequirementGenerateJob,
    req: AiRequirement,
    batch_results: list[dict],
    *,
    extra_duration_ms: int = 0,
) -> None:
    """根据 batch_results 回写任务状态与汇总报告。"""
    req_id = req.id
    success_count = sum(1 for b in batch_results if b.get("success"))
    all_created_ids: list[int] = []
    vision_reports: list[dict] = []
    for b in batch_results:
        if b.get("success"):
            all_created_ids.extend(b.get("created_case_ids") or [])
            gr = b.get("generate_report") or {}
            if gr.get("vision"):
                vision_reports.append(gr["vision"])
    total_tokens = sum(int(b.get("tokens_used") or 0) for b in batch_results)
    last_success = next((b for b in reversed(batch_results) if b.get("success")), None)
    last_report = (last_success or {}).get("generate_report") or {}

    combined_report = {
        "batch_mode": True,
        "batch_results": batch_results,
        "created_case_ids": all_created_ids,
        "vision": _merge_vision_reports(vision_reports)
        if vision_reports
        else last_report.get("vision"),
        "case_gen": _aggregate_batch_case_gen(batch_results),
        "duration_ms": int((job.duration_ms or 0) + extra_duration_ms),
        "tokens_used": total_tokens,
    }

    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False).order_by("id")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    meta["last_generate"] = {
        "case_count": len(cases),
        "created_case_ids": all_created_ids,
        "tokens_used": total_tokens,
        "duration_ms": combined_report["duration_ms"],
        "generate_report": combined_report,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    req.parsed_content = meta
    await req.save()

    job.batch_results = batch_results
    job.tokens_used = total_tokens
    job.duration_ms = combined_report["duration_ms"]
    job.generate_report = combined_report
    job.finish_time = datetime.now()
    if success_count == 0:
        first_err = next((b["error"] for b in batch_results if b.get("error")), "全部批次失败")
        job.status = "failed"
        job.error = first_err
    else:
        job.status = "completed"
        if success_count < len(batch_results):
            job.error = f"部分批次失败（{success_count}/{len(batch_results)} 批成功）"
        else:
            job.error = None
    await job.save()


async def _execute_generate_job(job_id: int) -> None:
    job = await AiRequirementGenerateJob.get_or_none(id=job_id)
    if not job:
        return
    if job.status not in ("pending", "running"):
        return

    payload = job.payload if isinstance(job.payload, dict) else {}
    if payload.get("job_kind") == "test_points":
        from app.modules.ai.test_point_batch import execute_test_points_generate_job

        await execute_test_points_generate_job(job)
        return

    body = GenerateCasesBatchRequest.model_validate(job.payload)
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
        await _run_batch_generate_core(req, job.project_id, body, job.create_by, job=job)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        if job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error = detail
            job.finish_time = datetime.now()
            await job.save()
    except Exception as e:
        logger.error(f"[requirements] 异步生成任务 {job_id} 失败: {e}", exc_info=True)
        if job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error = str(e)
            job.finish_time = datetime.now()
            await job.save()


async def _run_generate_job_task(job_id: int) -> None:
    try:
        await _execute_generate_job(job_id)
    except Exception as e:
        logger.exception(f"[requirements] generate job task {job_id} 异常: {e}")
        job = await AiRequirementGenerateJob.get_or_none(id=job_id)
        if job and job.status in ("pending", "running"):
            job.status = "failed"
            job.error = str(e)
            job.finish_time = datetime.now()
            await job.save()


async def _create_generate_job(
    req_id: int,
    body: GenerateCasesBatchRequest,
    project_id: int,
    user_info: dict,
) -> StandardResponse:
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    effective = await _effective_zentao_bindings(project_id, req)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"请先在「禅道导入配置」中填写：{', '.join(missing)}。"
                "（可在项目级保存默认值，本需求可覆盖）"
            ),
        )

    running = await AiRequirementGenerateJob.filter(
        requirement_id=req_id,
        project_id=project_id,
        status__in=["pending", "running"],
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"该需求已有进行中的生成任务（#{running.id}），请等待完成后再试",
        )

    username = user_info.get("username", "")
    job = await AiRequirementGenerateJob.create(
        requirement_id=req_id,
        project_id=project_id,
        status="pending",
        total_batches=len(body.batches),
        payload=body.model_dump(),
        create_by=username,
    )
    asyncio.create_task(_run_generate_job_task(job.id))
    return StandardResponse(
        message=f"生成任务已提交，共 {len(body.batches)} 批",
        data=_job_to_dict(job),
    )


@router.post("/{req_id}/generate-cases", summary="AI 生成功能测试用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def generate_cases(
    req_id: int,
    body: GenerateCasesRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    data = await _execute_generate_cases(
        req,
        project_id,
        user_info,
        body,
        batch_name=(body.batch_name or "").strip(),
        persist_job_record=True,
    )
    return StandardResponse(
        message=f"成功生成 {data['created_count']} 条用例",
        data=data,
    )


@router.post(
    "/{req_id}/generate-cases-batch",
    summary="按批次队列生成功能测试用例（异步任务）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_cases_batch(
    req_id: int,
    body: GenerateCasesBatchRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    return await _create_generate_job(req_id, body, project_id, user_info)


@router.post(
    "/{req_id}/generate-jobs",
    summary="提交批量生成异步任务",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def create_generate_job(
    req_id: int,
    body: GenerateCasesBatchRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    return await _create_generate_job(req_id, body, project_id, user_info)


@router.get(
    "/generate-jobs/{job_id}",
    summary="查询批量生成任务进度",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_generate_job(
    job_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    job = await AiRequirementGenerateJob.get_or_none(
        id=job_id, project_id=project_id, is_del=False
    )
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StandardResponse(data=_job_to_dict(job))


@router.get(
    "/{req_id}/generate-jobs/latest",
    summary="查询需求最近一次批量生成任务",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_latest_generate_job(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    job = await AiRequirementGenerateJob.filter(
        requirement_id=req_id, project_id=project_id, is_del=False
    ).order_by("-id").first()
    if not job:
        return StandardResponse(data=None, message="暂无生成任务")
    return StandardResponse(data=_job_to_dict(job))


@router.get(
    "/{req_id}/generate-jobs",
    summary="需求生成记录列表",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_generate_jobs(
    req_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    q = AiRequirementGenerateJob.filter(
        requirement_id=req_id, project_id=project_id, is_del=False
    ).order_by("-id")
    total = await q.count()
    jobs = await q.offset((page - 1) * size).limit(size).all()
    return StandardResponse(
        data={
            "list": [_job_to_dict(j) for j in jobs],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.post(
    "/generate-jobs/{job_id}/retry-batch",
    summary="重新生成批量任务中失败的批次",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def retry_generate_batch(
    job_id: int,
    body: RetryGenerateBatchRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    job = await AiRequirementGenerateJob.get_or_none(
        id=job_id, project_id=project_id, is_del=False
    )
    if not job:
        raise HTTPException(status_code=404, detail="生成记录不存在")
    if job.status in ("pending", "running"):
        raise HTTPException(status_code=409, detail="任务执行中，请等待完成后再重试失败批次")

    batch_results = list(job.batch_results or [])
    if body.batch_index >= len(batch_results):
        raise HTTPException(status_code=400, detail="批次序号无效")
    item = batch_results[body.batch_index]
    if item.get("success"):
        raise HTTPException(status_code=400, detail="该批次已成功，无需重新生成")

    req = await AiRequirement.get_or_none(
        id=job.requirement_id, project_id=project_id, is_del=False
    )
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    running = await AiRequirementGenerateJob.filter(
        requirement_id=job.requirement_id,
        project_id=project_id,
        status__in=["pending", "running"],
        is_del=False,
    ).first()
    if running and running.id != job_id:
        raise HTTPException(
            status_code=409,
            detail=f"该需求已有进行中的生成任务（#{running.id}），请等待完成后再试",
        )

    batch_name = (item.get("name") or "").strip() or f"批次{body.batch_index + 1}"
    scope_ids = list(item.get("scope_section_ids") or [])
    if not scope_ids:
        raise HTTPException(status_code=400, detail="该批次缺少章节范围，无法重新生成")

    payload = job.payload if isinstance(job.payload, dict) else {}
    if payload.get("job_kind") == "test_points":
        raise HTTPException(status_code=400, detail="该记录为测试点批量任务，请在使用例生成报告中重试")

    count_mode = _normalize_count_mode(
        body.count_mode if body.count_mode is not None else item.get("count_mode")
    )
    count = body.count if body.count is not None else item.get("requested_count")
    if count_mode == "fixed" and not count:
        count = 10

    # 重试必须保留原批次写入策略，禁止「有旧用例就强制补充」
    use_supplement = bool(item.get("supplement"))
    use_replace = bool(item.get("replace"))
    if use_supplement and use_replace:
        raise HTTPException(status_code=400, detail="原批次「补充」与「替换本批」标记冲突，无法重试")
    existing_rows = await _load_existing_cases_for_batch(req.id, batch_name)
    if not use_supplement and not use_replace and len(existing_rows) > 0:
        # 原新建批次残留用例：清空后重生，避免重复入库
        use_replace = True
    if use_replace:
        await _delete_cases_for_batch(req.id, batch_name)

    single_body = GenerateCasesRequest(
        vision_config_id=body.vision_config_id or payload.get("vision_config_id"),
        case_gen_config_id=body.case_gen_config_id or payload.get("case_gen_config_id"),
        count_mode=count_mode,
        count=count if count_mode == "fixed" else None,
        replace_existing=False,
        export_defaults=None,
        scope_section_ids=scope_ids,
        supplement_batch_name=batch_name if use_supplement else None,
        batch_name=batch_name,
        extra_instructions=(body.extra_instructions or payload.get("extra_instructions") or None),
        knowledge_folder_ids=payload.get("knowledge_folder_ids"),
        knowledge_document_ids=payload.get("knowledge_document_ids"),
    )

    try:
        data = await _execute_generate_cases(
            req,
            project_id,
            user_info,
            single_body,
            batch_name=batch_name,
            replace_existing=False,
        )
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        batch_results[body.batch_index] = {
            "index": body.batch_index,
            "name": batch_name,
            "success": False,
            "supplement": use_supplement,
            "replace": use_replace,
            "count_mode": count_mode,
            "requested_count": count if count_mode == "fixed" else None,
            "created_count": 0,
            "error": detail,
            **_batch_scope_fields(req, scope_ids),
        }
        await _sync_job_report_from_batch_results(job, req, batch_results)
        raise HTTPException(status_code=e.status_code, detail=detail) from e
    except Exception as e:
        logger.error("[requirements] 重试批次 %s 失败: %s", batch_name, e, exc_info=True)
        detail = f"重新生成失败: {e}"
        batch_results[body.batch_index] = {
            "index": body.batch_index,
            "name": batch_name,
            "success": False,
            "supplement": use_supplement,
            "replace": use_replace,
            "count_mode": count_mode,
            "requested_count": count if count_mode == "fixed" else None,
            "created_count": 0,
            "error": detail,
            **_batch_scope_fields(req, scope_ids),
        }
        await _sync_job_report_from_batch_results(job, req, batch_results)
        raise HTTPException(status_code=500, detail=detail) from e

    gr = data.get("generate_report") or {}
    cg = gr.get("case_gen") or {}
    batch_created_ids = (
        gr.get("created_case_ids")
        or [c.get("id") for c in data.get("cases", []) if c.get("id")]
    )
    batch_results[body.batch_index] = {
        "index": body.batch_index,
        "name": batch_name,
        "success": True,
        "supplement": use_supplement,
        "replace": use_replace,
        "count_mode": cg.get("count_mode") or count_mode,
        "requested_count": cg.get("requested_count"),
        "base_recommended_count": cg.get("base_recommended_count"),
        "soft_min_count": cg.get("soft_min_count"),
        "soft_max_count": cg.get("soft_max_count"),
        "range_explain": cg.get("range_explain"),
        "partial_truncated": bool(cg.get("partial_truncated")),
        "created_count": data["created_count"],
        "created_case_ids": batch_created_ids,
        "parsed_count": cg.get("parsed_count", data["created_count"]),
        "existing_cases_count": cg.get("existing_cases_count", 0),
        "count_note": cg.get("count_note"),
        "tokens_used": data["tokens_used"],
        "duration_ms": data["duration_ms"],
        "generate_report": gr,
        "error": None,
        **_batch_scope_fields(req, scope_ids, gr),
    }

    await _sync_job_report_from_batch_results(
        job,
        req,
        batch_results,
        extra_duration_ms=int(data.get("duration_ms") or 0),
    )

    cases = await AiRequirementCase.filter(requirement_id=req.id, is_del=False).order_by("id")
    return StandardResponse(
        message=f"批次「{batch_name}」重新生成成功，入库 {data['created_count']} 条",
        data={
            "job": _job_to_dict(job),
            "batch_result": batch_results[body.batch_index],
            "cases": [_case_to_dict(c) for c in cases],
            "created_count": data["created_count"],
        },
    )


@router.delete(
    "/generate-jobs/{job_id}",
    summary="删除生成记录（软删）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def delete_generate_job(
    job_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    job = await AiRequirementGenerateJob.get_or_none(
        id=job_id, project_id=project_id, is_del=False
    )
    if not job:
        raise HTTPException(status_code=404, detail="生成记录不存在")
    if job.status in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务执行中，无法删除")
    job.is_del = True
    await job.save(update_fields=["is_del", "update_time"])
    return StandardResponse(message="已删除生成记录")


@router.get("/{req_id}/cases", summary="用例列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_cases(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False).order_by("id")
    return StandardResponse(data={"list": [_case_to_dict(c) for c in cases], "total": len(cases)})


@router.put("/{req_id}/cases/{case_id}", summary="编辑用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_case(
    req_id: int,
    case_id: int,
    body: UpdateCaseRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    case = await AiRequirementCase.get_or_none(
        id=case_id, requirement_id=req_id, project_id=project_id, is_del=False
    )
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    updates = body.model_dump(exclude_unset=True)
    if "steps" in updates and updates["steps"] is not None:
        updates["steps"] = align_steps_expects(updates["steps"])
    if "precondition" in updates and updates["precondition"] is not None:
        updates["precondition"] = normalize_corner_quotes(str(updates["precondition"]).strip())
    for k, v in updates.items():
        setattr(case, k, v)

    effective = await _effective_zentao_bindings(project_id, req)
    bound = apply_bindings_to_case_fields({"priority": case.priority}, effective)
    case.product = bound["product"]
    case.related_story = bound["related_story"]
    case.stage = bound["stage"]

    await case.save()
    return StandardResponse(data=_case_to_dict(case))


@router.post(
    "/{req_id}/cases/import-to-library",
    summary="复制工作区用例到功能用例库",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def import_cases_to_library(
    req_id: int,
    body: ImportToLibraryRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")
    from app.routers.ai.functional_cases import import_requirement_cases_to_library_handler

    data = await import_requirement_cases_to_library_handler(
        req_id,
        body.case_ids,
        project_id,
        username,
        duplicate_title_mode=body.duplicate_title_mode,
    )
    msg_parts = [f"已复制 {data['copied_count']} 条到功能用例库"]
    if data.get("overwritten_count"):
        msg_parts.append(f"已覆盖 {data['overwritten_count']} 条")
    if data.get("skipped_count"):
        msg_parts.append(f"已跳过 {data['skipped_count']} 条（标题重复或已在库中）")
    if data.get("not_found_count"):
        msg_parts.append(f"{data['not_found_count']} 条未找到")
    return StandardResponse(
        data=data,
        message="，".join(msg_parts),
    )


@router.delete("/{req_id}/cases", summary="批量删除用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def batch_delete_cases(
    req_id: int,
    body: BatchDeleteCasesRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    if not body.case_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的用例")
    await AiRequirementCase.filter(
        id__in=body.case_ids,
        requirement_id=req_id,
        project_id=project_id,
    ).update(is_del=True)
    return StandardResponse(message="删除成功")


@router.post(
    "/{req_id}/cases/recalc-titles",
    summary="按当前模板重算草稿用例标题",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def recalc_case_titles(
    req_id: int,
    body: RecalcTitlesRequest,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    _, template = await _resolve_naming_template(project_id, req)
    effective = await _effective_zentao_bindings(project_id, req)
    q = AiRequirementCase.filter(requirement_id=req_id, project_id=project_id, is_del=False, status="draft")
    if body.case_ids:
        q = q.filter(id__in=body.case_ids)
    cases = await q.order_by("id")
    if not cases:
        raise HTTPException(status_code=400, detail="没有可重算的草稿用例")

    updated = 0
    warnings: list[str] = []
    for case in cases:
        slots = case.naming_slots if isinstance(case.naming_slots, dict) else {}
        item = {
            "module": case.module,
            "naming_slots": slots,
            "main_module": slots.get("main_module") or case.module,
            "sub_module": slots.get("sub_module", ""),
            "feature_point": slots.get("feature_point", ""),
            "case_description": slots.get("case_description", ""),
            "title": case.title,
        }
        new_title, ws = recalc_title_from_stored_slots(
            item,
            template,
            effective,
            requirement_id=req.id,
            story_code=_requirement_story_code(req),
        )
        if not new_title:
            continue
        case.title = new_title
        case.naming_template_id = template.get("id")
        case.naming_template_version = template.get("version", 1)
        llm = {
            "main_module": item["main_module"],
            "sub_module": item["sub_module"],
            "feature_point": item["feature_point"],
            "case_description": item["case_description"],
        }
        section_ctx = {
            "level1_title": llm["main_module"],
            "level2_title": llm["sub_module"],
            "leaf_title": llm["sub_module"],
            "path_titles": [],
        }
        resolved, ws2 = resolve_all_slots(
            template,
            {"llm": llm, "bindings": effective, "section": section_ctx, "context": {}},
        )
        for k in llm:
            if llm[k]:
                resolved[k] = llm[k]
        case.naming_slots = resolved
        warnings.extend(ws)
        warnings.extend(ws2)
        await case.save()
        updated += 1

    return StandardResponse(
        message=f"已重算 {updated} 条草稿用例标题",
        data={"updated": updated, "warnings": list(dict.fromkeys(warnings))[:30]},
    )


@router.get("/{req_id}/cases/export", summary="导出用例 XLSX", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def export_cases_xlsx(
    req_id: int,
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    cases = await AiRequirementCase.filter(requirement_id=req_id, is_del=False).order_by("id")
    if not cases:
        raise HTTPException(status_code=400, detail="暂无用例可导出")

    effective = await _effective_zentao_bindings(project_id, req)
    export_profile = get_export_profile(effective)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"导出前请完善禅道配置，缺少：{', '.join(missing)}",
        )
    export_defaults = bindings_for_export(effective)
    _, template = await _resolve_naming_template(project_id, req)
    export_columns = template.get("export_columns") or []
    columns = get_export_columns_for_template(template) or ZENTAO_DEFAULT_COLUMNS

    from app.modules.ai.zentao_bindings import resolve_stage

    rows = []
    for case in cases:
        case_dict = _case_to_dict(case)
        steps = align_steps_expects(case_dict.get("steps") or [])
        priority = str(case_dict.get("priority") or "2")
        stage_resolved = (case_dict.get("stage") or "").strip() or resolve_stage(priority, effective)
        if export_columns:
            row = render_export_row(
                case_dict,
                export_defaults,
                export_columns,
                steps_text=format_numbered_cell(steps, "step"),
                expects_text=format_numbered_cell(steps, "expect"),
                stage_resolved=stage_resolved,
            )
        else:
            row = case_to_export_row(case_dict, export_defaults)
        rows.append(row)

    xlsx_bytes = build_xlsx_bytes(rows, columns=columns)
    suffix = "cases" if export_profile == EXPORT_PROFILE_GENERIC else "zentao_cases"
    filename = f"requirement_{req_id}_{suffix}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
