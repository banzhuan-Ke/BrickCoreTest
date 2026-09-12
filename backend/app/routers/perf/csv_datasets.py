"""项目级 CSV 数据集 API"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_SCENE_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.models.perf import CsvDataset, PerfScene
from app.models.sys import Project
from app.modules.perf.csv_dataset import (
    dataset_summary,
    get_dataset_or_404,
    migrate_project_legacy_csv,
    parse_csv_bytes,
    write_dataset_rows,
)

router = APIRouter(
    prefix="/csv-datasets",
    tags=["性能测试 CSV 数据集"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_VIEW))],
)


class CsvDatasetCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CsvDatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


@router.get("", summary="CSV 数据集列表")
async def list_datasets(
    project_id: int = Query(...),
    keyword: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    qs = CsvDataset.filter(project_id=project_id, is_del=False)
    if keyword and keyword.strip():
        qs = qs.filter(name__icontains=keyword.strip())
    rows = await qs.order_by("-id").all()
    # 绑定场景数
    scenes = await PerfScene.filter(project_id=project_id, is_del=False).all()
    bind_count: dict[int, int] = {}
    for sc in scenes:
        if sc.csv_dataset_id:
            bind_count[int(sc.csv_dataset_id)] = bind_count.get(int(sc.csv_dataset_id), 0) + 1
    data = []
    for r in rows:
        item = dataset_summary(r, preview_limit=0)
        item.pop("preview", None)
        item["bound_scene_count"] = bind_count.get(r.id, 0)
        data.append(item)
    return {"data": data, "total": len(data)}


@router.post(
    "",
    summary="创建 CSV 数据集",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def create_dataset(
    body: CsvDatasetCreate,
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="名称不能为空")
    dup = await CsvDataset.filter(project_id=body.project_id, name=name, is_del=False).exists()
    if dup:
        raise HTTPException(status_code=409, detail="同名数据集已存在")
    ds = await CsvDataset.create(
        project_id=body.project_id,
        name=name,
        description=body.description,
        row_data=[],
        columns=[],
        file_name="",
        row_count=0,
        create_by=username or "",
    )
    return dataset_summary(ds)


@router.post(
    "/migrate-legacy",
    summary="迁出项目内场景遗留 CSV 为数据集",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def migrate_legacy(
    project_id: int = Query(...),
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    """历史兼容：将仍写在场景 csv_data 且未绑定数据集的行迁出。"""
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MEMBER)
    return await migrate_project_legacy_csv(project_id, username=username or "system")


@router.get("/{dataset_id}", summary="CSV 数据集详情")
async def get_dataset(
    dataset_id: int,
    preview_limit: int = Query(20, ge=0, le=100),
    user_info: dict = Depends(is_authenticated),
):
    ds = await get_dataset_or_404(dataset_id)
    await assert_project_access(user_info, ds.project_id, min_role=PROJECT_ROLE_VIEWER)
    item = dataset_summary(ds, preview_limit=preview_limit)
    bound = await PerfScene.filter(csv_dataset_id=ds.id, is_del=False).count()
    item["bound_scene_count"] = bound
    return item


@router.put(
    "/{dataset_id}",
    summary="更新 CSV 数据集元信息",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def update_dataset(
    dataset_id: int,
    body: CsvDatasetUpdate,
    user_info: dict = Depends(is_authenticated),
):
    ds = await get_dataset_or_404(dataset_id)
    await assert_project_access(user_info, ds.project_id, min_role=PROJECT_ROLE_MEMBER)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="名称不能为空")
        dup = await CsvDataset.filter(
            project_id=ds.project_id, name=name, is_del=False
        ).exclude(id=ds.id).exists()
        if dup:
            raise HTTPException(status_code=409, detail="同名数据集已存在")
        ds.name = name
    if body.description is not None:
        ds.description = body.description
    await ds.save()
    return dataset_summary(ds)


@router.delete(
    "/{dataset_id}",
    summary="删除 CSV 数据集",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_dataset(
    dataset_id: int,
    user_info: dict = Depends(is_authenticated),
):
    ds = await get_dataset_or_404(dataset_id)
    await assert_project_access(user_info, ds.project_id, min_role=PROJECT_ROLE_MEMBER)
    bound = await PerfScene.filter(csv_dataset_id=ds.id, is_del=False).count()
    if bound:
        raise HTTPException(
            status_code=409,
            detail=f"仍有 {bound} 个压测场景绑定此数据集，请先在场景中解绑",
        )
    ds.is_del = True
    await ds.save()
    return None


@router.post(
    "/{dataset_id}/upload",
    summary="上传/替换数据集 CSV 内容",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def upload_dataset_csv(
    dataset_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="仅解析预览，不写入"),
    user_info: dict = Depends(is_authenticated),
):
    ds = await get_dataset_or_404(dataset_id)
    await assert_project_access(user_info, ds.project_id, min_role=PROJECT_ROLE_MEMBER)
    content = await file.read()
    rows, columns = parse_csv_bytes(content, filename=file.filename or "")
    if dry_run:
        return {
            "message": "解析成功（未写入）",
            "dry_run": True,
            "file_name": file.filename,
            "row_count": len(rows),
            "columns": columns,
            "preview": rows[:5],
        }
    await write_dataset_rows(ds, rows, columns, file_name=file.filename or "")
    # 同步已绑定场景的 csv_config 元信息
    scenes = await PerfScene.filter(csv_dataset_id=ds.id, is_del=False).all()
    for scene in scenes:
        cfg = dict(scene.csv_config) if isinstance(scene.csv_config, dict) else {}
        cfg["file_name"] = ds.file_name
        cfg["columns"] = columns
        cfg["row_count"] = len(rows)
        scene.csv_config = cfg
        scene.csv_data = None
        await scene.save()
    return {
        "message": "上传成功",
        "dry_run": False,
        **dataset_summary(ds),
    }


@router.get("/{dataset_id}/preview", summary="预览数据集行")
async def preview_dataset(
    dataset_id: int,
    limit: int = Query(20, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    ds = await get_dataset_or_404(dataset_id)
    await assert_project_access(user_info, ds.project_id, min_role=PROJECT_ROLE_VIEWER)
    return dataset_summary(ds, preview_limit=limit)
