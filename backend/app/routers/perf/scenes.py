"""性能测试场景管理 API"""
import csv
import io
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status, UploadFile, File
from tortoise import transactions
from pydantic import BaseModel, Field

from app.models.perf import PerfScene
from app.models.http import ApiTestCase
from app.models.sys import Project
from app.core.auth import require_permissions, get_current_username
from app.core.permissions import PERF_SCENE_EDIT, PERF_SCENE_EXECUTE

router = APIRouter(prefix="/scenes", tags=["性能测试场景"])


# ========== Pydantic Schemas ==========

class SceneItem(BaseModel):
    """场景用例项"""
    case_id: int = Field(..., description="用例ID")
    weight: int = Field(default=1, ge=1, le=100, description="权重")
    delay_ms: int = Field(default=0, ge=0, description="请求间隔(ms)")


class StepConfig(BaseModel):
    """梯度压测阶段配置"""
    users: int = Field(..., ge=1, le=200, description="该阶段并发用户数")
    duration: int = Field(..., ge=1, le=3600, description="该阶段持续时间(秒)")


class PerfConfig(BaseModel):
    """压测配置"""
    mode: str = Field(default="fixed", description="压测模式: fixed/stepping/loop")
    distribution_mode: str = Field(default="weighted_random", description="请求分配模式: weighted_random/fixed_ratio")
    concurrent_users: Optional[int] = Field(None, ge=1, le=200, description="并发用户数，fixed/loop模式必填")
    ramp_up_seconds: int = Field(default=0, ge=0, le=600, description="Ramp-up时间(秒)")
    duration_seconds: Optional[int] = Field(None, ge=1, le=3600, description="持续时间(秒)，fixed模式必填")
    loop_count: Optional[int] = Field(None, ge=1, le=100000, description="循环次数，loop模式必填")
    steps: Optional[List[StepConfig]] = Field(None, description="梯度阶段，stepping模式必填")
    target_host: Optional[str] = Field(None, description="目标Host(可选)")


class PerfSceneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    project_id: int = Field(..., description="项目ID")
    scene_items: List[SceneItem] = Field(..., description="场景用例列表")
    config: PerfConfig = Field(..., description="压测配置")


class PerfSceneUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    scene_items: Optional[List[SceneItem]] = None
    config: Optional[PerfConfig] = None


class PerfSceneOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    project_id: int
    scene_items: List[dict]
    config: dict
    create_by: str
    create_time: str
    update_time: str

    class Config:
        from_attributes = True


class PerfSceneListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    project_id: int
    scene_items: List[dict]
    config: dict
    case_count: int
    create_by: str
    create_time: str
    update_time: str


class PerfSceneListResponse(BaseModel):
    data: List[PerfSceneListItem]
    total: int
    page: int
    size: int


# ========== Helper Functions ==========

async def validate_perf_config(config: PerfConfig):
    """校验压测配置"""
    mode = config.mode or "fixed"
    if mode not in ("fixed", "stepping", "loop"):
        raise HTTPException(status_code=422, detail="压测模式必须是 fixed、stepping 或 loop")
    
    if mode in ("fixed", "loop"):
        if not config.concurrent_users:
            raise HTTPException(status_code=422, detail="固定模式和循环模式必须设置并发用户数")
    
    if mode == "fixed":
        if not config.duration_seconds:
            raise HTTPException(status_code=422, detail="固定模式必须设置持续时间")
    elif mode == "loop":
        if not config.loop_count:
            raise HTTPException(status_code=422, detail="循环模式必须设置循环次数")
    elif mode == "stepping":
        if not config.steps or len(config.steps) == 0:
            raise HTTPException(status_code=422, detail="梯度模式必须至少设置一个阶段")
        for i, step in enumerate(config.steps):
            if step.users < 1 or step.users > 200:
                raise HTTPException(status_code=422, detail=f"第{i+1}阶段并发用户数必须在1-200之间")
            if step.duration < 1 or step.duration > 3600:
                raise HTTPException(status_code=422, detail=f"第{i+1}阶段持续时间必须在1-3600秒之间")


async def validate_scene_items(scene_items: List[SceneItem], project_id: int):
    """校验场景用例项"""
    if not scene_items:
        raise HTTPException(status_code=422, detail="请至少选择一个用例")
    
    case_ids = [item.case_id for item in scene_items]
    cases = await ApiTestCase.filter(id__in=case_ids, is_del=False).all()
    found_ids = {c.id for c in cases}
    
    missing = set(case_ids) - found_ids
    if missing:
        raise HTTPException(status_code=422, detail=f"用例不存在: {missing}")
    
    # 检查用例是否属于当前项目（可选校验，放宽则注释掉）
    for case in cases:
        if case.project_id != project_id:
            raise HTTPException(status_code=422, detail=f"用例 {case.id} 不属于当前项目")


async def enrich_scene_items(scene_items: List[dict]) -> List[dict]:
    """为用例项补充用例名称和方法"""
    case_ids = [item["case_id"] for item in scene_items]
    cases = await ApiTestCase.filter(id__in=case_ids, is_del=False).all()
    case_map = {}
    for c in cases:
        api = await c.api
        case_map[c.id] = {
            "case_name": c.name,
            "api_method": api.method if api else ""
        }
    
    result = []
    for item in scene_items:
        enriched = dict(item)
        info = case_map.get(item["case_id"], {})
        enriched.update(info)
        result.append(enriched)
    return result


# ========== CRUD APIs ==========

@router.post("", summary="创建性能测试场景",
             dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def create_scene(item: PerfSceneCreate, username: str = Depends(get_current_username)):
    """创建性能测试场景"""
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    
    await validate_scene_items(item.scene_items, item.project_id)
    await validate_perf_config(item.config)
    
    scene = await PerfScene.create(
        name=item.name,
        description=item.description,
        project_id=item.project_id,
        scene_items=[si.model_dump() for si in item.scene_items],
        config=item.config.model_dump(),
        create_by=username
    )
    
    return await get_scene_detail(scene.id)


@router.get("", summary="性能测试场景列表", response_model=PerfSceneListResponse)
async def get_scenes(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None, description="关键字"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取性能测试场景列表"""
    query = PerfScene.filter(project_id=project_id, is_del=False)
    
    if keyword:
        query = query.filter(name__contains=keyword)
    
    total = await query.count()
    scenes = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for scene in scenes:
        result.append(PerfSceneListItem(
            id=scene.id,
            name=scene.name,
            description=scene.description,
            project_id=scene.project_id,
            scene_items=scene.scene_items,
            config=scene.config,
            case_count=len(scene.scene_items or []),
            create_by=scene.create_by,
            create_time=scene.create_time.strftime("%Y-%m-%d %H:%M:%S") if scene.create_time else "",
            update_time=scene.update_time.strftime("%Y-%m-%d %H:%M:%S") if scene.update_time else ""
        ))
    
    return PerfSceneListResponse(data=result, total=total, page=page, size=size)


@router.get("/{scene_id}", summary="场景详情")
async def get_scene_detail(scene_id: int):
    """获取性能测试场景详情"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    scene_items = await enrich_scene_items(scene.scene_items or [])
    
    return {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "project_id": scene.project_id,
        "scene_items": scene_items,
        "config": scene.config,
        "create_by": scene.create_by,
        "create_time": scene.create_time.strftime("%Y-%m-%d %H:%M:%S") if scene.create_time else "",
        "update_time": scene.update_time.strftime("%Y-%m-%d %H:%M:%S") if scene.update_time else ""
    }


@router.put("/{scene_id}", summary="更新性能测试场景",
            dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def update_scene(scene_id: int, item: PerfSceneUpdate, username: str = Depends(get_current_username)):
    """更新性能测试场景"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    if item.name is not None:
        scene.name = item.name
    if item.description is not None:
        scene.description = item.description
    if item.scene_items is not None:
        await validate_scene_items(item.scene_items, scene.project_id)
        scene.scene_items = [si.model_dump() for si in item.scene_items]
    if item.config is not None:
        await validate_perf_config(item.config)
        scene.config = item.config.model_dump()
    
    await scene.save()
    return await get_scene_detail(scene_id)


@router.delete("/{scene_id}", summary="删除性能测试场景", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def delete_scene(scene_id: int):
    """删除性能测试场景（软删除）"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    scene.is_del = True
    await scene.save()


@router.post("/{scene_id}/clone", summary="复制性能测试场景",
             dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def clone_scene(scene_id: int, username: str = Depends(get_current_username)):
    """复制性能测试场景（基于现有场景创建新场景，名称加'-副本'后缀）"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    original_name = scene.name or "未命名场景"
    new_name = f"{original_name}-副本"
    
    # 如果名称已存在，追加数字后缀
    existing = await PerfScene.filter(name=new_name, project_id=scene.project_id, is_del=False).first()
    suffix = 1
    base_name = new_name
    while existing:
        suffix += 1
        new_name = f"{base_name}{suffix}"
        existing = await PerfScene.filter(name=new_name, project_id=scene.project_id, is_del=False).first()
    
    new_scene = await PerfScene.create(
        name=new_name,
        description=scene.description,
        project_id=scene.project_id,
        scene_items=scene.scene_items,
        config=scene.config,
        create_by=username
    )
    
    return await get_scene_detail(new_scene.id)


# ========== CSV 参数化数据管理 ==========

@router.post("/{scene_id}/csv-upload", summary="上传 CSV 参数化数据")
async def upload_csv(scene_id: int, file: UploadFile = File(...)):
    """上传 CSV 文件，解析为 JSON 存储到场景"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    # 验证文件类型
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = content.decode('gbk')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文件编码不支持，请使用 UTF-8 或 GBK 编码")

    # 解析 CSV
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        columns = []
        for i, row in enumerate(reader):
            if i == 0:
                columns = list(row.keys())
            # 清理空值
            cleaned = {k: v.strip() if v else "" for k, v in row.items()}
            rows.append(cleaned)
            if i >= 9999:  # 最多 10000 行
                break
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {str(e)}")

    if not rows:
        raise HTTPException(status_code=400, detail="CSV 文件为空或格式错误")

    scene.csv_data = rows
    scene.csv_config = {
        "enabled": True,
        "strategy": "round_robin",
        "file_name": file.filename,
        "columns": columns,
        "row_count": len(rows)
    }
    await scene.save()

    return {
        "message": "上传成功",
        "file_name": file.filename,
        "row_count": len(rows),
        "columns": columns,
        "preview": rows[:5]
    }


@router.get("/{scene_id}/csv-preview", summary="预览 CSV 数据")
async def preview_csv(scene_id: int, limit: int = Query(20, ge=1, le=100)):
    """预览场景的 CSV 数据"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    csv_data = scene.csv_data or []
    config = scene.csv_config or {}

    return {
        "enabled": config.get("enabled", False),
        "strategy": config.get("strategy", "round_robin"),
        "file_name": config.get("file_name", ""),
        "columns": config.get("columns", []),
        "row_count": len(csv_data),
        "preview": csv_data[:limit]
    }


@router.delete("/{scene_id}/csv", summary="删除 CSV 参数化数据")
async def delete_csv(scene_id: int):
    """删除场景的 CSV 数据"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    scene.csv_data = None
    scene.csv_config = {}
    await scene.save()
    return {"message": "CSV 数据已删除"}


@router.put("/{scene_id}/csv-config", summary="更新 CSV 配置")
async def update_csv_config(scene_id: int, config: dict):
    """更新 CSV 分配策略等配置"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    if not scene.csv_data:
        raise HTTPException(status_code=400, detail="场景未绑定 CSV 数据")

    valid_strategies = ["round_robin", "unique", "random"]
    strategy = config.get("strategy", "round_robin")
    if strategy not in valid_strategies:
        raise HTTPException(status_code=400, detail=f"无效的策略，可选: {valid_strategies}")

    scene.csv_config["strategy"] = strategy
    scene.csv_config["enabled"] = config.get("enabled", True)
    await scene.save()

    return {"message": "配置更新成功", "config": scene.csv_config}
