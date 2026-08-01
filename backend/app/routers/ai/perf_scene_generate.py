"""AI 一句话生成压测场景：generate 草稿 → import 落库。"""
from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_EXECUTE, PERF_SCENE_EDIT
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, assert_project_access
from app.core.shared.catalog_utils import resolve_catalog
from app.models.ai import AiGenerateRecord
from app.models.perf import PerfScene
from app.models.sys import Project
from app.modules.ai.ai_prompts import PromptManager, append_extra_instructions
from app.modules.perf.nl_scene_draft import (
    apply_selected_cases,
    build_case_catalog,
    format_catalog_for_prompt,
    parse_llm_intent,
    resolve_draft,
)
from app.modules.perf.perf_journey import journey_to_scene_items, is_journey_mode
from app.modules.stream_phase import normalize_perf_mode
from app.routers.ai.generate import _call_llm, _get_ai_config
from app.routers.perf.scenes import PerfConfig, SceneItem, validate_perf_config, validate_scene_items
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["AI生成"])


class GeneratePerfSceneRequest(BaseModel):
    project_id: int
    prompt: str = Field(..., min_length=1, max_length=2000, description="自然语言描述")
    suite_id: Optional[int] = None
    case_ids: Optional[List[int]] = Field(
        None,
        description="可选，限定候选用例；测单接口时传入一个 id",
        max_length=50,
    )
    tags: Optional[List[str]] = None
    ai_config_id: Optional[int] = None
    catalog_id: Optional[int] = None


class ImportPerfSceneRequest(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    catalog_id: Optional[int] = None
    scene_items: List[dict] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    record_id: Optional[int] = None
    selected_case_ids: Optional[List[int]] = Field(
        None,
        description="预览勾选的用例 ID；若提供则按勾选重建 scene_items/journey",
    )


@router.post(
    "/perf-scene",
    summary="一句话生成压测场景草稿",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_perf_scene(
    body: GeneratePerfSceneRequest,
    user_info: dict = Depends(is_authenticated),
):
    start_time = time.time()
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    prompt_text = (body.prompt or "").strip()
    if not prompt_text:
        raise HTTPException(status_code=422, detail="请填写自然语言描述")

    catalog = await build_case_catalog(
        body.project_id,
        suite_id=body.suite_id if not body.case_ids else None,
        tags=body.tags,
        case_ids=body.case_ids,
    )
    has_suite_cases = any(s.get("case_ids") for s in catalog.get("suites") or [])
    if not catalog.get("cases") and not has_suite_cases:
        detail = "项目内暂无可用接口用例，请先创建用例或导入套件后再生成"
        if body.case_ids:
            detail = "所选接口用例不可用（可能已删除或不属于当前项目），请重新选择"
        elif body.suite_id:
            detail = "所选套件没有可用用例（可能已删除或被标签过滤），请更换套件/标签"
        raise HTTPException(status_code=422, detail=detail)

    cases_json, suites_json = format_catalog_for_prompt(catalog)
    config = await _get_ai_config(body.ai_config_id, scene="perf_scene_generate")

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "perf_scene_generation",
            {
                "user_prompt": prompt_text,
                "cases_json": cases_json,
                "suites_json": suites_json,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Prompt 渲染失败: {e}") from e

    user_prompt = append_extra_instructions(user_prompt, None, scene="perf_scene")

    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "perf_scene_generate",
            user_info=user_info,
            project_id=body.project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=prompt_text[:500],
            output_summary=str(e)[:500],
        )
        logger.error("[generate_perf_scene] LLM 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e

    raw_response = resp.get("content", "") or ""
    tokens_used = int(resp.get("tokens") or 0)
    intent = parse_llm_intent(raw_response)
    if not intent:
        duration_ms = int((time.time() - start_time) * 1000)
        await AiGenerateRecord.create(
            project_id=body.project_id,
            generate_type="perf_scene",
            input_summary={"prompt": prompt_text, "suite_id": body.suite_id, "case_ids": body.case_ids, "tags": body.tags},
            output_content={"raw_response": raw_response, "errors": ["无法解析 JSON"]},
            status="rejected",
            ai_config_id=config.id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            create_by=user_info.get("username", ""),
        )
        await log_ai_usage(
            config,
            "perf_scene_generate",
            user_info=user_info,
            project_id=body.project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=prompt_text[:500],
            output_summary="无法解析 JSON",
            parse_ok=False,
        )
        raise HTTPException(status_code=500, detail="无法解析 AI 返回的 JSON，请重试或改写描述")

    if body.case_ids:
        intent = dict(intent)
        cleaned: list[int] = []
        seen: set[int] = set()
        for x in body.case_ids:
            try:
                cid = int(x)
            except (TypeError, ValueError):
                continue
            if cid in seen:
                continue
            seen.add(cid)
            cleaned.append(cid)
        if cleaned:
            intent["case_ids"] = cleaned
            intent.pop("suite_id", None)
            # 用户显式点选用例：单接口/混合加权，不默认走套件链路
            intent["prefer_journey"] = False
    elif body.suite_id:
        intent = dict(intent)
        intent["suite_id"] = body.suite_id

    draft = resolve_draft(
        intent=intent,
        catalog_cases=catalog.get("cases") or [],
        catalog_suites=catalog.get("suites") or [],
        user_prompt=prompt_text,
        project_id=body.project_id,
        catalog_id=body.catalog_id,
    )

    duration_ms = int((time.time() - start_time) * 1000)
    record = await AiGenerateRecord.create(
        project_id=body.project_id,
        generate_type="perf_scene",
        input_summary={
            "prompt": prompt_text,
            "suite_id": body.suite_id,
            "case_ids": body.case_ids,
            "tags": body.tags,
            "catalog_case_count": len(catalog.get("cases") or []),
        },
        output_content={"draft": draft, "intent": intent, "raw_response": raw_response},
        status="pending",
        ai_config_id=config.id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=user_info.get("username", ""),
    )
    await log_ai_usage(
        config,
        "perf_scene_generate",
        user_info=user_info,
        project_id=body.project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=prompt_text[:500],
        output_summary=f"importable={draft.get('importable')} cases={len(draft.get('matched_cases') or [])}",
        record_id=record.id,
    )

    return StandardResponse(
        data={
            "draft": draft,
            "record_id": record.id,
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
            "raw_response": raw_response,
            "catalog_case_count": len(catalog.get("cases") or []),
            "catalog_suite_count": len(catalog.get("suites") or []),
        }
    )


@router.post(
    "/perf-scene/import",
    summary="确认创建 AI 压测场景",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, PERF_SCENE_EDIT))],
)
async def import_perf_scene(
    body: ImportPerfSceneRequest,
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="场景名称不能为空")

    payload = {
        "name": name,
        "description": body.description,
        "catalog_id": body.catalog_id,
        "scene_items": list(body.scene_items or []),
        "config": dict(body.config or {}),
        "matched_cases": [],
        "warnings": [],
    }
    for raw in payload["scene_items"]:
        if isinstance(raw, dict) and raw.get("case_id") is not None:
            payload["matched_cases"].append({
                "id": raw["case_id"],
                "name": raw.get("name") or f"用例#{raw['case_id']}",
            })
    journey = (payload["config"] or {}).get("journey") or {}
    for phase in journey.get("phases") or []:
        for step in phase.get("steps") or []:
            cid = step.get("case_id")
            if cid is None:
                continue
            if not any(
                int(m["id"]) == int(cid)
                for m in payload["matched_cases"]
                if m.get("id") is not None
            ):
                payload["matched_cases"].append({"id": cid, "name": f"用例#{cid}"})

    if body.selected_case_ids is not None:
        sel = []
        for x in body.selected_case_ids:
            try:
                sel.append(int(x))
            except (TypeError, ValueError):
                continue
        existing_ids = {int(m["id"]) for m in payload["matched_cases"] if m.get("id") is not None}
        for cid in sel:
            if cid not in existing_ids:
                payload["matched_cases"].append({"id": cid, "name": f"用例#{cid}"})
        payload = apply_selected_cases(payload, sel)

    scene_items: list[SceneItem] = []
    for raw in payload.get("scene_items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            scene_items.append(SceneItem.model_validate(raw))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"scene_items 无效: {e}") from e

    try:
        config = PerfConfig.model_validate(payload.get("config") or {})
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"压测配置无效: {e}") from e

    # journey 模式：scene_items 一律由 journey 派生，避免客户端传入不一致/脏快照
    if is_journey_mode(normalize_perf_mode(config.mode or "fixed")):
        derived = journey_to_scene_items(config.model_dump())
        scene_items = []
        for raw in derived:
            try:
                scene_items.append(SceneItem.model_validate(raw))
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"journey 派生 scene_items 无效: {e}") from e

    if not scene_items:
        raise HTTPException(status_code=422, detail="请至少勾选一个用例后再创建")

    await validate_scene_items(scene_items, body.project_id, config)
    await validate_perf_config(config)
    if body.catalog_id is not None:
        await resolve_catalog(body.project_id, body.catalog_id)

    config_dump: dict[str, Any] = config.model_dump()
    scene = await PerfScene.create(
        name=name[:100],
        description=(body.description or "")[:2000] or None,
        project_id=body.project_id,
        catalog_id=body.catalog_id,
        scene_items=[si.model_dump() for si in scene_items],
        config=config_dump,
        create_by=username,
    )

    if body.record_id:
        record = await AiGenerateRecord.get_or_none(
            id=body.record_id,
            project_id=body.project_id,
            generate_type="perf_scene",
        )
        if record:
            out = dict(record.output_content or {})
            out["imported_scene_id"] = scene.id
            record.output_content = out
            record.status = "imported"
            await record.save()

    return StandardResponse(
        data={
            "id": scene.id,
            "name": scene.name,
            "project_id": scene.project_id,
        }
    )
