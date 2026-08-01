"""Commit JMeter preview drafts into ApiDefinition / ApiTestCase / ApiTestSuite / PerfScene."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from tortoise import transactions

from app.models.http import ApiDefinition, ApiSuiteCase, ApiTestCase, ApiTestSuite
from app.models.perf import PerfScene
from app.modules.jmeter.jmx_mapper import map_ir_to_preview
from app.modules.jmeter.models import (
    JmeterCommitItemResult,
    JmeterCommitRequest,
    JmeterCommitResponse,
)
from app.modules.perf.perf_journey import (
    LAYOUT_SINGLE_PHASE,
    journey_to_scene_items,
    suite_cases_to_journey,
)


async def commit_jmeter_import(
    *,
    ir: dict[str, Any],
    preview: Optional[dict[str, Any]],
    req: JmeterCommitRequest,
    username: str,
) -> JmeterCommitResponse:
    preview = preview or map_ir_to_preview(ir)
    selected = set(req.selected_sampler_paths) if req.selected_sampler_paths else None

    apis_by_path = {a["source_path"]: a for a in preview.get("apis") or []}
    cases_by_path = {c["source_path"]: c for c in preview.get("cases") or []}
    paths_in_order = [a["source_path"] for a in preview.get("apis") or []]
    if selected is not None:
        paths_in_order = [p for p in paths_in_order if p in selected]

    items: list[JmeterCommitItemResult] = []
    path_to_case_id: dict[str, int] = {}
    created_apis = created_cases = merged_cases = skipped = failed = 0

    async with transactions.in_transaction():
        for source_path in paths_in_order:
            api_draft = apis_by_path.get(source_path)
            case_draft = cases_by_path.get(source_path)
            if not api_draft or not case_draft:
                failed += 1
                items.append(
                    JmeterCommitItemResult(
                        source_path=source_path,
                        action="failed",
                        message="预览中缺少对应草稿",
                    )
                )
                continue
            result = await _import_one_sampler(
                project_id=req.project_id,
                catalog_id=req.catalog_id,
                api_draft=api_draft,
                case_draft=case_draft,
                strategy=req.conflict_strategy,
                username=username,
            )
            items.append(result)
            if result.action == "created":
                created_apis += 1
                created_cases += 1
            elif result.action == "merged":
                merged_cases += 1
            elif result.action == "skipped":
                skipped += 1
            elif result.action == "failed":
                failed += 1
            if result.case_id:
                path_to_case_id[source_path] = result.case_id

        suite_ids: list[int] = []
        suite_id_by_source: dict[str, int] = {}
        created_suites = 0
        create_suites = req.create_suites or req.create_perf_scenes
        if create_suites:
            for suite_draft in preview.get("suites") or []:
                case_ids = []
                case_metas = []
                for sp in suite_draft.get("sampler_paths") or []:
                    if selected is not None and sp not in selected:
                        continue
                    cid = path_to_case_id.get(sp)
                    if cid:
                        case_ids.append(cid)
                        case_metas.append({"case_id": cid, "case_name": (cases_by_path.get(sp) or {}).get("name") or ""})
                if not case_ids:
                    continue
                suite = await ApiTestSuite.create(
                    name=(suite_draft.get("name") or "JMeter Suite")[:100],
                    project_id=req.project_id,
                    catalog_id=req.catalog_id,
                    description=f"从 JMeter Thread Group 导入: {preview.get('test_plan_name')}",
                    create_by=username,
                    update_by=username,
                )
                for idx, case_id in enumerate(case_ids):
                    await ApiSuiteCase.create(suite_id=suite.id, case_id=case_id, sort=idx)
                suite_ids.append(suite.id)
                src = suite_draft.get("source_path") or suite_draft.get("name") or str(suite.id)
                suite_id_by_source[src] = suite.id
                suite_draft["_created_suite_id"] = suite.id
                suite_draft["_case_metas"] = case_metas
                created_suites += 1

        scene_ids: list[int] = []
        created_scenes = 0
        if req.create_perf_scenes:
            for scene_draft in preview.get("perf_scenes") or []:
                sampler_paths = [
                    sp
                    for sp in (scene_draft.get("sampler_paths") or [])
                    if selected is None or sp in selected
                ]
                case_metas = []
                for sp in sampler_paths:
                    cid = path_to_case_id.get(sp)
                    if cid:
                        case_metas.append({
                            "case_id": cid,
                            "case_name": (cases_by_path.get(sp) or {}).get("name") or "",
                        })
                if not case_metas:
                    continue
                cfg = dict(scene_draft.get("config") or {})
                journey = suite_cases_to_journey(
                    case_metas,
                    layout=LAYOUT_SINGLE_PHASE,
                    suite_name=scene_draft.get("suite_name") or scene_draft.get("name") or "业务链路",
                )
                cfg["journey"] = journey
                suite_key = scene_draft.get("source_path") or scene_draft.get("suite_name") or ""
                suite_id = suite_id_by_source.get(suite_key)
                if suite_id:
                    cfg["journey_source"] = {
                        "suite_id": suite_id,
                        "suite_name": scene_draft.get("suite_name") or "",
                        "layout": LAYOUT_SINGLE_PHASE,
                        "case_ids": [c["case_id"] for c in case_metas],
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                        "from_jmeter": True,
                    }
                scene_items = journey_to_scene_items({"journey": journey})
                scene = await PerfScene.create(
                    name=(scene_draft.get("name") or "JMeter Perf")[:100],
                    description=f"从 JMeter 导入: {preview.get('test_plan_name')}",
                    project_id=req.project_id,
                    catalog_id=req.catalog_id,
                    scene_items=scene_items,
                    config=cfg,
                    create_by=username,
                )
                scene_ids.append(scene.id)
                created_scenes += 1

    return JmeterCommitResponse(
        test_plan_name=preview.get("test_plan_name") or "JMeter Import",
        created_apis=created_apis,
        created_cases=created_cases,
        merged_cases=merged_cases,
        skipped=skipped,
        failed=failed,
        created_suites=created_suites,
        suite_ids=suite_ids,
        created_scenes=created_scenes,
        scene_ids=scene_ids,
        items=items,
        warnings=list(preview.get("warnings") or []),
        todos=list(preview.get("todos") or []),
    )


async def _import_one_sampler(
    *,
    project_id: int,
    catalog_id: Optional[int],
    api_draft: dict[str, Any],
    case_draft: dict[str, Any],
    strategy: str,
    username: str,
) -> JmeterCommitItemResult:
    method = (api_draft.get("method") or "GET").upper()
    path = api_draft.get("path") or "/"
    source_path = api_draft.get("source_path") or ""

    existing = await ApiDefinition.filter(
        project_id=project_id,
        method=method,
        path=path,
        is_del=False,
    ).first()

    if strategy == "skip_existing" and existing:
        return JmeterCommitItemResult(
            source_path=source_path,
            action="skipped",
            api_id=existing.id,
            message="同 method+path 已存在，已跳过",
        )

    if strategy == "merge_case" and existing:
        case = await _create_case(
            api=existing,
            project_id=project_id,
            catalog_id=catalog_id or existing.catalog_id,
            case_draft=case_draft,
            username=username,
        )
        return JmeterCommitItemResult(
            source_path=source_path,
            action="merged",
            api_id=existing.id,
            case_id=case.id,
            message="复用已有接口，新建用例",
        )

    api = await ApiDefinition.create(
        name=(api_draft.get("name") or "HTTP Request")[:100],
        project_id=project_id,
        catalog_id=catalog_id,
        method=method,
        path=path,
        description=api_draft.get("description") or "",
        base_url=api_draft.get("base_url"),
        headers=api_draft.get("headers") or [],
        params=api_draft.get("params") or [],
        body=api_draft.get("body") if api_draft.get("body") is not None else {},
        body_type=(api_draft.get("body_type") if api_draft.get("body_type") not in (None, "none") else "json"),
        source="jmeter",
        source_id=source_path[:200],
        create_by=username,
        update_by=username,
        version=1,
    )
    case = await _create_case(
        api=api,
        project_id=project_id,
        catalog_id=catalog_id or api.catalog_id,
        case_draft=case_draft,
        username=username,
    )
    return JmeterCommitItemResult(
        source_path=source_path,
        action="created",
        api_id=api.id,
        case_id=case.id,
        message="已创建接口与用例",
    )


async def _create_case(
    *,
    api: ApiDefinition,
    project_id: int,
    catalog_id: Optional[int],
    case_draft: dict[str, Any],
    username: str,
) -> ApiTestCase:
    body = case_draft.get("request_body")
    if body is None:
        body = {}
    return await ApiTestCase.create(
        name=(case_draft.get("name") or api.name or "用例")[:100],
        api_id=api.id,
        project_id=project_id,
        catalog_id=catalog_id,
        request_headers=case_draft.get("request_headers") or {},
        request_params=case_draft.get("request_params") or [],
        request_body=body,
        request_body_type=(
            case_draft.get("request_body_type")
            if case_draft.get("request_body_type") not in (None, "none")
            else "json"
        ),
        assertions=case_draft.get("assertions") or [],
        extractors=case_draft.get("extractors") or [],
        timeout=case_draft.get("timeout") or 30,
        tags=case_draft.get("tags") or ["jmeter"],
        priority="P2",
        api_version_snapshot=api.version,
        create_by=username,
        update_by=username,
    )


def resolve_conflict_action(strategy: str, has_existing: bool) -> str:
    """Pure helper for unit tests."""
    if strategy == "skip_existing" and has_existing:
        return "skipped"
    if strategy == "merge_case" and has_existing:
        return "merged"
    return "created"
