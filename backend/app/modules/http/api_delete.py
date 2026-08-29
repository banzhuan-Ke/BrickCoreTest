"""接口删除：关联用例护栏与 cascade 清理。"""
from __future__ import annotations

from typing import Any

from app.models.http import ApiSuiteCase, ApiTestCase
from app.models.perf import PerfScene
from app.modules.perf.perf_journey import collect_journey_case_ids, normalize_journey_config


async def list_active_cases_for_api(api_id: int) -> list[ApiTestCase]:
    return await ApiTestCase.filter(api_id=api_id, is_del=False).all()


def summarize_cases(cases: list[ApiTestCase], limit: int = 20) -> list[dict[str, Any]]:
    return [{"id": c.id, "name": c.name} for c in cases[:limit]]


def strip_case_ids_from_scene_items(scene_items: list | None, case_ids: set[int]) -> list:
    out = []
    for item in scene_items or []:
        if not isinstance(item, dict):
            out.append(item)
            continue
        try:
            cid = int(item.get("case_id"))
        except (TypeError, ValueError):
            out.append(item)
            continue
        if cid in case_ids:
            continue
        out.append(item)
    return out


def strip_case_ids_from_journey(config: dict | None, case_ids: set[int]) -> dict:
    """从 config.journey 中移除指定 case_id 的步骤；返回更新后的 config 副本。"""
    cfg = dict(config or {})
    if not cfg.get("journey"):
        return cfg
    journey = normalize_journey_config(cfg)
    phases = []
    for phase in journey.get("phases") or []:
        steps = []
        for s in phase.get("steps") or []:
            if not isinstance(s, dict):
                steps.append(s)
                continue
            try:
                cid = int(s.get("case_id"))
            except (TypeError, ValueError):
                steps.append(s)
                continue
            if cid in case_ids:
                continue
            steps.append(s)
        if not steps:
            continue
        new_phase = dict(phase)
        new_phase["steps"] = steps
        phases.append(new_phase)
    new_journey = dict(journey)
    new_journey["phases"] = phases
    cfg["journey"] = new_journey
    return cfg


def scene_references_any_case(scene: PerfScene, case_ids: set[int]) -> bool:
    for item in scene.scene_items or []:
        if not isinstance(item, dict):
            continue
        try:
            if int(item.get("case_id")) in case_ids:
                return True
        except (TypeError, ValueError):
            continue
    journey_ids = set(collect_journey_case_ids(scene.config or {}))
    return bool(journey_ids & case_ids)


async def purge_case_references(*, project_id: int, case_ids: list[int], using_db=None) -> dict[str, int]:
    """删除套件关联，并从压测场景 scene_items / journey 中移除用例引用。"""
    ids = list(dict.fromkeys(int(x) for x in case_ids))
    if not ids:
        return {"suite_links_removed": 0, "scenes_updated": 0}

    id_set = set(ids)
    suite_qs = ApiSuiteCase.filter(case_id__in=ids)
    if using_db is not None:
        suite_qs = suite_qs.using_db(using_db)
    suite_deleted = await suite_qs.delete()

    scenes_updated = 0
    scene_qs = PerfScene.filter(project_id=project_id, is_del=False)
    if using_db is not None:
        scene_qs = scene_qs.using_db(using_db)
    scenes = await scene_qs.all()
    for scene in scenes:
        if not scene_references_any_case(scene, id_set):
            continue
        scene.scene_items = strip_case_ids_from_scene_items(scene.scene_items, id_set)
        scene.config = strip_case_ids_from_journey(scene.config, id_set)
        await scene.save(using_db=using_db)
        scenes_updated += 1

    return {"suite_links_removed": int(suite_deleted or 0), "scenes_updated": scenes_updated}


async def soft_delete_cases(cases: list[ApiTestCase], *, using_db=None) -> int:
    n = 0
    for case in cases:
        if case.is_del:
            continue
        case.is_del = True
        await case.save(using_db=using_db)
        n += 1
    return n
