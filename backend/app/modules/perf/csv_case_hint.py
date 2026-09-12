"""接口侧 CSV 提示与调试试跑一行：关联压测场景 / 项目数据集。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.http import ApiTestCase
from app.models.perf import CsvDataset, PerfScene
from app.modules.perf.csv_dataset import resolve_scene_csv
from app.modules.perf.perf_journey import collect_journey_case_ids, is_journey_mode


def expand_csv_row_as_vars(csv_row: Optional[dict]) -> dict[str, Any]:
    """与 Runner 对齐：列名 + csv.列名。"""
    if not csv_row or not isinstance(csv_row, dict):
        return {}
    out: dict[str, Any] = {}
    for raw_key, value in csv_row.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        if key.startswith("\ufeff"):
            key = key.lstrip("\ufeff")
        out[key] = value
        out[f"csv.{key}"] = value
    return out


def _scene_case_ids(scene: PerfScene) -> set[int]:
    ids: set[int] = set()
    for item in scene.scene_items or []:
        if not isinstance(item, dict):
            continue
        try:
            ids.add(int(item.get("case_id")))
        except (TypeError, ValueError):
            continue
    cfg = scene.config or {}
    if isinstance(cfg, dict) and is_journey_mode(cfg.get("mode")):
        for cid in collect_journey_case_ids(cfg):
            try:
                ids.add(int(cid))
            except (TypeError, ValueError):
                continue
    return ids


def _scene_has_csv_from_resolved(resolved: dict) -> bool:
    return bool(resolved.get("row_count"))


async def list_csv_contexts_for_case(
    *,
    project_id: int,
    case_id: Optional[int] = None,
    api_id: Optional[int] = None,
    preview_limit: int = 5,
) -> dict[str, Any]:
    """列出关联场景 CSV + 项目级数据集（供提示、试跑、插入变量）。"""
    if not project_id:
        raise HTTPException(status_code=422, detail="缺少 project_id")

    target_case_ids: set[int] = set()
    if case_id:
        case = await ApiTestCase.get_or_none(id=case_id, project_id=project_id, is_del=False)
        if not case:
            raise HTTPException(status_code=404, detail="用例不存在")
        target_case_ids.add(int(case_id))
    if api_id:
        rows = await ApiTestCase.filter(
            project_id=project_id, api_id=api_id, is_del=False
        ).values_list("id", flat=True)
        target_case_ids.update(int(x) for x in rows)

    matched: list[dict] = []
    with_csv: list[dict] = []
    if target_case_ids:
        scenes = await PerfScene.filter(project_id=project_id, is_del=False).order_by("-id")
        for scene in scenes:
            linked = _scene_case_ids(scene)
            if not (linked & target_case_ids):
                continue
            resolved = await resolve_scene_csv(scene, preview_limit=preview_limit)
            summary = {
                "id": scene.id,
                "name": scene.name,
                "has_csv": _scene_has_csv_from_resolved(resolved),
                "row_count": resolved.get("row_count") or 0,
                "columns": resolved.get("columns") or [],
                "strategy": resolved.get("strategy") or "round_robin",
                "file_name": resolved.get("file_name") or "",
                "preview_rows": resolved.get("preview") or [],
                "dataset_id": resolved.get("dataset_id"),
                "dataset_name": resolved.get("dataset_name"),
                "source": resolved.get("source"),
                "via_case_ids": sorted(linked & target_case_ids)[:20],
            }
            matched.append(summary)
            if summary["has_csv"]:
                with_csv.append(summary)

    datasets = await CsvDataset.filter(project_id=project_id, is_del=False).order_by("-id")
    dataset_list = []
    for ds in datasets:
        data = ds.row_data if isinstance(ds.row_data, list) else []
        columns = ds.columns if isinstance(ds.columns, list) else []
        if not columns and data and isinstance(data[0], dict):
            columns = list(data[0].keys())
        if not data:
            continue
        dataset_list.append({
            "id": ds.id,
            "name": ds.name,
            "file_name": ds.file_name or "",
            "columns": columns,
            "row_count": len(data),
            "preview_rows": data[:preview_limit],
        })

    return {
        "case_id": case_id,
        "api_id": api_id,
        "scene_count": len(matched),
        "csv_scene_count": len(with_csv),
        "scenes": matched[:50],
        "csv_scenes": with_csv[:50],
        "datasets": dataset_list[:50],
        "dataset_count": len(dataset_list),
    }


async def load_csv_row_vars(
    *,
    project_id: int,
    scene_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    row_index: int = 0,
) -> dict[str, Any]:
    """加载场景或数据集 CSV 指定行并展开为变量。"""
    if dataset_id is not None:
        ds = await CsvDataset.get_or_none(id=int(dataset_id), project_id=project_id, is_del=False)
        if not ds:
            raise HTTPException(status_code=404, detail="CSV 数据集不存在或不属于当前项目")
        data = ds.row_data if isinstance(ds.row_data, list) else []
        label = f"数据集「{ds.name}」"
    elif scene_id is not None:
        scene = await PerfScene.get_or_none(id=scene_id, project_id=project_id, is_del=False)
        if not scene:
            raise HTTPException(status_code=404, detail="压测场景不存在或不属于当前项目")
        resolved = await resolve_scene_csv(scene, preview_limit=0)
        data = resolved.get("data") or []
        label = f"场景「{scene.name}」"
    else:
        raise HTTPException(status_code=422, detail="请提供 csv_scene_id 或 csv_dataset_id")

    if not data:
        raise HTTPException(
            status_code=422,
            detail=f"{label}未绑定 CSV，请先在「CSV 数据集」或场景编辑页上传并保存",
        )
    if row_index < 0 or row_index >= len(data):
        raise HTTPException(
            status_code=422,
            detail=f"CSV 行号无效：共 {len(data)} 行，row_index 应为 0～{len(data) - 1}",
        )
    row = data[row_index]
    if not isinstance(row, dict):
        raise HTTPException(status_code=422, detail="CSV 行数据格式无效")
    return expand_csv_row_as_vars(row)
