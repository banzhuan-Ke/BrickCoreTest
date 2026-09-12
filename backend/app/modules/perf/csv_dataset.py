"""项目级 CSV 数据集：解析、场景解析（含历史兼容）、遗留迁出。"""
from __future__ import annotations

import csv
import io
from typing import Any, Optional

from fastapi import HTTPException

from app.models.perf import CsvDataset, PerfScene

VALID_STRATEGIES = ("round_robin", "unique", "random")
MAX_CSV_ROWS = 10000


def parse_csv_bytes(content: bytes, filename: str = "") -> tuple[list[dict], list[str]]:
    """解析 CSV 字节 → (rows, columns)。"""
    if filename and not str(filename).lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="文件编码不支持，请使用 UTF-8 或 GBK 编码") from exc

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows: list[dict] = []
        columns: list[str] = []
        for i, row in enumerate(reader):
            cleaned: dict[str, Any] = {}
            for k, v in row.items():
                key = str(k or "").strip().lstrip("\ufeff")
                if not key:
                    continue
                cleaned[key] = v.strip() if v else ""
            if i == 0:
                columns = list(cleaned.keys())
            rows.append(cleaned)
            if i >= MAX_CSV_ROWS - 1:
                break
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=400, detail="CSV 文件为空或格式错误")
    return rows, columns


def normalize_strategy(strategy: Optional[str], default: str = "round_robin") -> str:
    s = (strategy or default or "round_robin").strip()
    return s if s in VALID_STRATEGIES else default


def dataset_summary(ds: CsvDataset, *, preview_limit: int = 5) -> dict[str, Any]:
    data = ds.row_data if isinstance(ds.row_data, list) else []
    columns = ds.columns if isinstance(ds.columns, list) else []
    if not columns and data and isinstance(data[0], dict):
        columns = list(data[0].keys())
    return {
        "id": ds.id,
        "project_id": ds.project_id,
        "name": ds.name,
        "description": ds.description,
        "file_name": ds.file_name or "",
        "columns": columns,
        "row_count": int(ds.row_count or len(data)),
        "source_scene_id": ds.source_scene_id,
        "create_by": ds.create_by,
        "create_time": ds.create_time.strftime("%Y-%m-%d %H:%M:%S") if ds.create_time else None,
        "update_time": ds.update_time.strftime("%Y-%m-%d %H:%M:%S") if ds.update_time else None,
        "preview": data[:preview_limit],
    }


async def get_dataset_or_404(dataset_id: int, project_id: Optional[int] = None) -> CsvDataset:
    qs = CsvDataset.filter(id=dataset_id, is_del=False)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    ds = await qs.first()
    if not ds:
        raise HTTPException(status_code=404, detail="CSV 数据集不存在")
    return ds


async def resolve_scene_csv(scene: PerfScene, *, preview_limit: int = 20) -> dict[str, Any]:
    """解析场景生效的 CSV：优先绑定数据集，否则回退遗留 csv_data。"""
    cfg = scene.csv_config if isinstance(scene.csv_config, dict) else {}
    strategy = normalize_strategy(cfg.get("strategy"))
    enabled = bool(cfg.get("enabled", False))

    dataset_id = getattr(scene, "csv_dataset_id", None)
    if dataset_id:
        ds = await CsvDataset.get_or_none(id=int(dataset_id), is_del=False)
        if ds and (ds.project_id == scene.project_id):
            data = ds.row_data if isinstance(ds.row_data, list) else []
            columns = ds.columns if isinstance(ds.columns, list) else []
            if not columns and data and isinstance(data[0], dict):
                columns = list(data[0].keys())
            # 有数据即视为可启用；enabled 默认 True（绑定即用）
            if "enabled" not in cfg:
                enabled = bool(data)
            return {
                "enabled": enabled and bool(data),
                "strategy": strategy,
                "file_name": ds.file_name or cfg.get("file_name") or "",
                "columns": columns,
                "row_count": len(data),
                "preview": data[:preview_limit],
                "data": data,
                "source": "dataset",
                "dataset_id": ds.id,
                "dataset_name": ds.name,
            }

    # 历史：场景内联 csv_data
    data = scene.csv_data if isinstance(scene.csv_data, list) else []
    columns = cfg.get("columns") or []
    if not columns and data and isinstance(data[0], dict):
        columns = list(data[0].keys())
    if data and "enabled" not in cfg:
        enabled = True
    return {
        "enabled": enabled and bool(data),
        "strategy": strategy,
        "file_name": cfg.get("file_name") or "",
        "columns": columns,
        "row_count": len(data),
        "preview": data[:preview_limit],
        "data": data,
        "source": "legacy" if data else "none",
        "dataset_id": None,
        "dataset_name": None,
    }


async def migrate_scene_legacy_csv(
    scene: PerfScene,
    *,
    username: str = "system",
    force: bool = False,
) -> Optional[CsvDataset]:
    """将场景遗留 csv_data 迁为项目数据集并绑定。已有绑定且非 force 则跳过。"""
    if scene.csv_dataset_id and not force:
        return await CsvDataset.get_or_none(id=scene.csv_dataset_id, is_del=False)

    data = scene.csv_data if isinstance(scene.csv_data, list) else []
    if not data:
        return None

    cfg = scene.csv_config if isinstance(scene.csv_config, dict) else {}
    columns = cfg.get("columns") or []
    if not columns and isinstance(data[0], dict):
        columns = list(data[0].keys())
    file_name = (cfg.get("file_name") or "").strip()
    base_name = (file_name.rsplit(".", 1)[0] if file_name else "") or f"{scene.name or '场景'}-CSV"
    name = base_name[:100]

    # 同名冲突追加后缀
    existing = await CsvDataset.filter(project_id=scene.project_id, name=name, is_del=False).first()
    suffix = 1
    candidate = name
    while existing:
        suffix += 1
        candidate = f"{name[:90]}-{suffix}"
        existing = await CsvDataset.filter(project_id=scene.project_id, name=candidate, is_del=False).first()
    name = candidate

    ds = await CsvDataset.create(
        project_id=scene.project_id,
        name=name,
        description=f"由场景「{scene.name}」历史 CSV 自动迁出",
        row_data=data,
        columns=columns,
        file_name=file_name,
        row_count=len(data),
        source_scene_id=scene.id,
        create_by=username or "system",
    )
    scene.csv_dataset_id = ds.id
    # 保留遗留字段作只读镜像，新写入走数据集；enabled 默认开
    new_cfg = dict(cfg)
    new_cfg.setdefault("enabled", True)
    new_cfg["strategy"] = normalize_strategy(new_cfg.get("strategy"))
    new_cfg["file_name"] = file_name
    new_cfg["columns"] = columns
    new_cfg["row_count"] = len(data)
    new_cfg["migrated_to_dataset_id"] = ds.id
    scene.csv_config = new_cfg
    await scene.save()
    return ds


async def migrate_project_legacy_csv(project_id: int, *, username: str = "system") -> dict[str, Any]:
    """批量迁出项目内仍仅有内联 CSV 的场景。"""
    scenes = await PerfScene.filter(project_id=project_id, is_del=False).all()
    migrated = []
    skipped = []
    for scene in scenes:
        data = scene.csv_data if isinstance(scene.csv_data, list) else []
        if scene.csv_dataset_id:
            skipped.append({"scene_id": scene.id, "reason": "already_bound"})
            continue
        if not data:
            skipped.append({"scene_id": scene.id, "reason": "no_legacy_csv"})
            continue
        ds = await migrate_scene_legacy_csv(scene, username=username)
        if ds:
            migrated.append({"scene_id": scene.id, "dataset_id": ds.id, "name": ds.name})
    return {"migrated": migrated, "skipped": skipped, "migrated_count": len(migrated)}


async def bind_scene_dataset(
    scene: PerfScene,
    dataset_id: Optional[int],
    *,
    strategy: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> dict[str, Any]:
    """绑定或解绑数据集；解绑不删除数据集。"""
    cfg = dict(scene.csv_config) if isinstance(scene.csv_config, dict) else {}
    if dataset_id is None:
        scene.csv_dataset_id = None
        # 解绑：清空启用，保留策略偏好
        cfg["enabled"] = False
        scene.csv_config = cfg
        await scene.save()
        return await resolve_scene_csv(scene)

    ds = await get_dataset_or_404(int(dataset_id), project_id=scene.project_id)
    scene.csv_dataset_id = ds.id
    if strategy is not None:
        cfg["strategy"] = normalize_strategy(strategy)
    elif "strategy" not in cfg:
        cfg["strategy"] = "round_robin"
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    else:
        cfg["enabled"] = True
    cfg["file_name"] = ds.file_name or ""
    cfg["columns"] = ds.columns or []
    cfg["row_count"] = int(ds.row_count or 0)
    scene.csv_config = cfg
    # 不再依赖内联数据
    scene.csv_data = None
    await scene.save()
    return await resolve_scene_csv(scene)


async def write_dataset_rows(
    ds: CsvDataset,
    rows: list[dict],
    columns: list[str],
    *,
    file_name: str = "",
) -> CsvDataset:
    ds.row_data = rows
    ds.columns = columns
    ds.file_name = file_name or ds.file_name or ""
    ds.row_count = len(rows)
    await ds.save()
    return ds


async def ensure_bound_dataset_for_upload(
    scene: PerfScene,
    *,
    username: str,
    file_name: str,
) -> CsvDataset:
    """场景上传 CSV：有绑定则更新该数据集，否则新建并绑定。"""
    if scene.csv_dataset_id:
        ds = await CsvDataset.get_or_none(id=scene.csv_dataset_id, is_del=False)
        if ds and ds.project_id == scene.project_id:
            return ds

    # 尝试先迁遗留
    legacy = await migrate_scene_legacy_csv(scene, username=username)
    if legacy:
        return legacy

    base = (file_name.rsplit(".", 1)[0] if file_name else "") or f"{scene.name or '场景'}-CSV"
    name = base[:100]
    existing = await CsvDataset.filter(project_id=scene.project_id, name=name, is_del=False).first()
    suffix = 1
    candidate = name
    while existing:
        suffix += 1
        candidate = f"{name[:90]}-{suffix}"
        existing = await CsvDataset.filter(project_id=scene.project_id, name=candidate, is_del=False).first()

    ds = await CsvDataset.create(
        project_id=scene.project_id,
        name=candidate,
        description=f"场景「{scene.name}」上传",
        row_data=[],
        columns=[],
        file_name=file_name or "",
        row_count=0,
        source_scene_id=scene.id,
        create_by=username or "",
    )
    scene.csv_dataset_id = ds.id
    await scene.save()
    return ds
