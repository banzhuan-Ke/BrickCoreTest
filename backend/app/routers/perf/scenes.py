"""性能测试场景管理 API"""
import csv
import io
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status, UploadFile, File
from tortoise import transactions
from pydantic import BaseModel, Field, ConfigDict

from app.models.perf import PerfScene, PerfRecord
from app.modules.perf.metrics_accuracy import (
    DEFAULT_BASELINE_THRESHOLDS,
    normalize_baseline_thresholds,
)
from app.models.http import ApiTestCase, ApiTestSuite, ApiSuiteCase
from app.models.sys import Project, TestCatalog
from app.core.platform.auth import require_permissions, get_current_username, is_authenticated
from app.core.shared.catalog_utils import apply_catalog_filter, resolve_catalog, load_active_catalog_names
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_SCENE_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.routers.perf.access import get_scene_for_member, get_scene_for_viewer
from app.modules.stream_phase import (
    normalize_perf_mode,
    has_stream_profile_config,
    normalize_stream_profile,
)
from app.modules.stream_phase.registry import get_parser
from app.modules.perf.perf_journey import (
    JOURNEY_FIXED_MODE,
    JOURNEY_LOOP_MODE,
    LAYOUT_PER_CASE_PHASE,
    LAYOUT_SINGLE_PHASE,
    is_journey_mode,
    normalize_journey_config,
    collect_journey_case_ids,
    journey_has_sync_barrier,
    journey_to_scene_items,
    suite_cases_to_journey,
)
from app.modules.perf.perf_target_eval import normalize_perf_targets

router = APIRouter(
    prefix="/scenes",
    tags=["性能测试场景"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_VIEW))],
)


async def _build_journey_source_status(scene: PerfScene) -> Optional[dict]:
    """对比 config.journey_source 与当前套件用例顺序，供场景编辑黄条提示。"""
    cfg = scene.config or {}
    source = cfg.get("journey_source") if isinstance(cfg, dict) else None
    if not isinstance(source, dict) or not source.get("suite_id"):
        return None
    try:
        suite_id = int(source["suite_id"])
    except (TypeError, ValueError):
        return None
    stored_ids = []
    for x in (source.get("case_ids") or [] if isinstance(source.get("case_ids"), list) else []):
        try:
            stored_ids.append(int(x))
        except (TypeError, ValueError):
            continue

    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite or suite.project_id != scene.project_id:
        return {
            "suite_id": suite_id,
            "suite_name": source.get("suite_name"),
            "layout": source.get("layout"),
            "suite_exists": False,
            "changed": True,
            "stored_case_ids": stored_ids,
            "current_case_ids": [],
            "message": "源套件不存在或不属于当前项目",
        }

    suite_cases = await ApiSuiteCase.filter(suite_id=suite.id).order_by("sort").all()
    case_ids = [sc.case_id for sc in suite_cases]
    if not case_ids:
        current_ids: list[int] = []
    else:
        existing = await ApiTestCase.filter(
            id__in=case_ids, is_del=False, project_id=scene.project_id
        ).values_list("id", flat=True)
        existing_set = set(existing)
        current_ids = [cid for cid in case_ids if cid in existing_set]

    changed = current_ids != stored_ids
    msg = None
    if changed:
        msg = f"源套件已变更（导入时 {len(stored_ids)} 步 / 当前 {len(current_ids)} 步），可重新导入预览"
    return {
        "suite_id": suite.id,
        "suite_name": suite.name or source.get("suite_name"),
        "layout": source.get("layout"),
        "suite_exists": True,
        "changed": changed,
        "stored_case_ids": stored_ids,
        "current_case_ids": current_ids,
        "message": msg,
    }


# ========== Pydantic Schemas ==========

class SceneItem(BaseModel):
    """场景用例项"""
    case_id: int = Field(..., description="用例ID")
    weight: int = Field(default=1, ge=1, le=100, description="权重")
    delay_ms: int = Field(default=0, ge=0, description="固定请求间隔(ms)")
    delay_mode: str = Field(default="fixed", description="间隔模式: fixed | random")
    delay_ms_min: int = Field(default=0, ge=0, description="随机间隔下限(ms)")
    delay_ms_max: int = Field(default=0, ge=0, description="随机间隔上限(ms)")


class StepConfig(BaseModel):
    """梯度压测阶段配置"""
    users: int = Field(..., ge=1, le=200, description="该阶段并发用户数")
    duration: int = Field(..., ge=1, le=3600, description="该阶段持续时间(秒)")


class StreamProfileConfig(BaseModel):
    transport: str = Field(default="sse", description="传输类型: sse")
    parser_id: str = Field(default="qa_sse_v1", description="流式解析器 ID")
    parser_options: dict = Field(default_factory=dict, description="解析器选项")
    success_rule: dict = Field(default_factory=lambda: {"type": "phase_exists", "phase": "first_char"})
    timeout_seconds: int = Field(default=600, ge=1, le=3600, description="单次请求超时(秒)")
    sse_parser_config_id: Optional[int] = Field(
        None,
        description="溯源：选用的系统 SSE 解析配置 ID（执行机忽略，仅平台记录）",
    )
    report_highlight_phases: List[str] = Field(
        default_factory=list,
        description="报告摘要着重展示的阶段/派生指标 key（空=全部同等）",
    )


class JourneyStepConfig(BaseModel):
    case_id: int = Field(..., description="用例ID")
    delay_ms: int = Field(default=0, ge=0, description="步骤完成后固定延迟(ms)")
    delay_mode: str = Field(default="fixed", description="间隔模式: fixed | random")
    delay_ms_min: int = Field(default=0, ge=0, description="随机间隔下限(ms)")
    delay_ms_max: int = Field(default=0, ge=0, description="随机间隔上限(ms)")
    use_stream: bool = Field(default=False, description="该步骤是否使用流式引擎")
    order: int = Field(default=0, ge=0, description="步骤顺序")


class JourneyPhaseConfig(BaseModel):
    name: str = Field(default="", max_length=100, description="阶段名称")
    execution: str = Field(default="serial", description="serial/parallel")
    sync_before: bool = Field(default=False, description="阶段开始前同步屏障")
    max_parallel: int = Field(default=6, ge=1, le=50, description="并行阶段最大并发")
    steps: List[JourneyStepConfig] = Field(default_factory=list, description="阶段步骤")


class JourneyConfig(BaseModel):
    stop_on_step_fail: bool = Field(default=True, description="步骤失败是否中断链路")
    delay_between_journeys_ms: int = Field(default=0, ge=0, description="链路间隔(ms)")
    phases: List[JourneyPhaseConfig] = Field(default_factory=list, description="业务阶段")


class PerfConfig(BaseModel):
    """压测配置"""
    # 允许前端扩展字段（如未来新参数）一并落库，避免静默丢失
    model_config = ConfigDict(extra="allow")

    mode: str = Field(default="fixed", description="压测模式")
    distribution_mode: str = Field(default="weighted_random", description="请求分配模式: weighted_random/fixed_ratio")
    concurrent_users: Optional[int] = Field(None, ge=1, le=1000, description="并发用户数")
    ramp_up_seconds: int = Field(default=0, ge=0, le=600, description="Ramp-up时间(秒)")
    warmup_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        le=600,
        description="热身秒数；汇总延迟剔除此前样本。未填时跟随 ramp_up_seconds；显式 0 表示不剔除",
    )
    duration_seconds: Optional[int] = Field(
        None, ge=1, le=86400, description="持续时间(秒)，fixed/journey_fixed 必填；最长 24 小时"
    )
    loop_count: Optional[int] = Field(None, ge=1, le=100000, description="循环次数，loop/journey_loop必填")
    steps: Optional[List[StepConfig]] = Field(None, description="梯度阶段，stepping模式必填")
    target_host: Optional[str] = Field(None, description="目标Host(可选)")
    error_rate_threshold: Optional[float] = Field(
        default=0,
        ge=0,
        le=100,
        description="错误率阈值(%)，连续超限自动停止；0 表示不启用",
    )
    stream_profile: Optional[StreamProfileConfig] = Field(None, description="流式阶段压测配置")
    journey: Optional[JourneyConfig] = Field(None, description="业务链路配置")
    journey_source: Optional[dict] = Field(
        None,
        description="套件导入来源：suite_id/suite_name/layout/case_ids/imported_at",
    )
    perf_targets: Optional[dict] = Field(
        None,
        description="性能验收目标（绝对值 SLA）；与 error_rate_threshold / baseline_policy 无关",
    )

class PerfSceneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    project_id: int = Field(..., description="项目ID")
    catalog_id: Optional[int] = Field(None, description="所属目录ID")
    scene_items: List[SceneItem] = Field(..., description="场景用例列表")
    config: PerfConfig = Field(..., description="压测配置")


class PerfSceneUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    catalog_id: Optional[int] = Field(None, description="所属目录ID")
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
    catalog_id: Optional[int] = None
    catalog_name: Optional[str] = None
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
    if config.perf_targets is not None:
        config.perf_targets = normalize_perf_targets(config.perf_targets)

    mode = normalize_perf_mode(config.mode or "fixed")
    allowed = ("fixed", "stepping", "loop", "stream_burst", JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE)
    if mode not in allowed:
        raise HTTPException(status_code=422, detail="压测模式无效")

    if is_journey_mode(mode):
        await _validate_journey_config(config)
        return

    if mode not in ("fixed", "stepping", "loop", "stream_burst"):
        raise HTTPException(status_code=422, detail="压测模式必须是 fixed、stepping、loop 或 stream_burst")
    
    if mode in ("fixed", "loop", "stream_burst"):
        if not config.concurrent_users:
            raise HTTPException(status_code=422, detail="固定模式、循环模式和流式阶段压测必须设置并发用户数")
    
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

    if config.stream_profile and has_stream_profile_config({"stream_profile": config.stream_profile.model_dump()}):
        profile = normalize_stream_profile({"stream_profile": config.stream_profile.model_dump()})
        if not get_parser(profile.get("parser_id")):
            raise HTTPException(status_code=422, detail=f"未知流式解析器: {profile.get('parser_id')}")


async def _validate_journey_config(config: PerfConfig):
    """校验业务链路压测配置。"""
    if not config.concurrent_users:
        raise HTTPException(status_code=422, detail="链路压测必须设置并发用户数")
    mode = normalize_perf_mode(config.mode or JOURNEY_FIXED_MODE)
    if mode == JOURNEY_FIXED_MODE and not config.duration_seconds:
        raise HTTPException(status_code=422, detail="链路固定模式必须设置持续时间")
    if mode == JOURNEY_LOOP_MODE and not config.loop_count:
        raise HTTPException(status_code=422, detail="链路循环模式必须设置循环次数")

    journey = normalize_journey_config(config.model_dump())
    phases = journey.get("phases") or []
    if not phases:
        raise HTTPException(status_code=422, detail="链路压测至少配置一个阶段")
    total_steps = 0
    for i, phase in enumerate(phases):
        steps = phase.get("steps") or []
        if not steps:
            raise HTTPException(status_code=422, detail=f"链路第{i + 1}阶段至少包含一个有效步骤（需选用例）")
        total_steps += len(steps)
        if phase.get("execution") not in ("serial", "parallel"):
            raise HTTPException(status_code=422, detail=f"链路第{i + 1}阶段 execution 必须是 serial 或 parallel")
    if total_steps < 1:
        raise HTTPException(status_code=422, detail="链路压测至少包含一个有效步骤（需选用例）")

    if journey_has_sync_barrier(config.model_dump()) and (config.ramp_up_seconds or 0) > 0:
        raise HTTPException(
            status_code=422,
            detail="链路阶段同步与 Ramp-up 不能同时使用，请将 Ramp-up 设为 0 或关闭阶段前同步",
        )

    if config.stream_profile and has_stream_profile_config({"stream_profile": config.stream_profile.model_dump()}):
        profile = normalize_stream_profile({"stream_profile": config.stream_profile.model_dump()})
        if not get_parser(profile.get("parser_id")):
            raise HTTPException(status_code=422, detail=f"未知流式解析器: {profile.get('parser_id')}")


async def validate_scene_items(scene_items: List[SceneItem], project_id: int, config: Optional[PerfConfig] = None):
    """校验场景用例项"""
    if config and is_journey_mode(normalize_perf_mode(config.mode or "fixed")):
        case_ids = collect_journey_case_ids(config.model_dump())
        if not case_ids:
            raise HTTPException(status_code=422, detail="链路压测至少配置一个用例步骤")
    else:
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


async def _scene_detail_payload(scene: PerfScene) -> dict:
    """场景详情响应（含 enriched scene_items 与 journey 源套件状态）。"""
    scene_items = await enrich_scene_items(scene.scene_items or [])

    catalog_name = None
    if scene.catalog_id:
        catalog = await TestCatalog.get_or_none(id=scene.catalog_id, is_del=False)
        catalog_name = catalog.name if catalog else None

    journey_source_status = await _build_journey_source_status(scene)

    return {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "project_id": scene.project_id,
        "catalog_id": scene.catalog_id,
        "catalog_name": catalog_name,
        "scene_items": scene_items,
        "config": scene.config,
        "baseline_record_id": scene.baseline_record_id,
        "baseline_policy": scene.baseline_policy or {},
        "journey_source_status": journey_source_status,
        "create_by": scene.create_by,
        "create_time": scene.create_time.strftime("%Y-%m-%d %H:%M:%S") if scene.create_time else "",
        "update_time": scene.update_time.strftime("%Y-%m-%d %H:%M:%S") if scene.update_time else "",
    }


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
async def create_scene(
    item: PerfSceneCreate,
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    """创建性能测试场景"""
    await assert_project_access(user_info, item.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    
    await validate_scene_items(item.scene_items, item.project_id, item.config)
    await validate_perf_config(item.config)
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)

    scene = await PerfScene.create(
        name=item.name,
        description=item.description,
        project_id=item.project_id,
        catalog_id=item.catalog_id,
        scene_items=[si.model_dump() for si in item.scene_items],
        config=item.config.model_dump(),
        create_by=username
    )
    
    return await _scene_detail_payload(scene)


@router.get("", summary="性能测试场景列表", response_model=PerfSceneListResponse)
async def get_scenes(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None, description="关键字"),
    catalog_id: Optional[int] = Query(None, description="目录ID"),
    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000),
    user_info: dict = Depends(is_authenticated),
):
    """获取性能测试场景列表"""
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    query = PerfScene.filter(project_id=project_id, is_del=False)

    if catalog_id is not None:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)

    if keyword:
        query = query.filter(name__contains=keyword)
    
    total = await query.count()
    scenes = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for scene in scenes:
        catalog_name = None
        if scene.catalog_id:
            catalog = await TestCatalog.get_or_none(id=scene.catalog_id, is_del=False)
            catalog_name = catalog.name if catalog else None
        result.append(PerfSceneListItem(
            id=scene.id,
            name=scene.name,
            description=scene.description,
            project_id=scene.project_id,
            catalog_id=scene.catalog_id,
            catalog_name=catalog_name,
            scene_items=scene.scene_items,
            config=scene.config,
            case_count=len(scene.scene_items or []),
            create_by=scene.create_by,
            create_time=scene.create_time.strftime("%Y-%m-%d %H:%M:%S") if scene.create_time else "",
            update_time=scene.update_time.strftime("%Y-%m-%d %H:%M:%S") if scene.update_time else ""
        ))
    
    return PerfSceneListResponse(data=result, total=total, page=page, size=size)


class JourneyFromSuiteRequest(BaseModel):
    suite_id: int = Field(..., description="接口套件ID")
    project_id: int = Field(..., description="项目ID")
    layout: str = Field(
        default=LAYOUT_SINGLE_PHASE,
        description="single_phase=单阶段多步骤; per_case_phase=每用例一阶段",
    )


@router.post(
    "/journey-from-suite",
    summary="从接口套件生成业务链路配置",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def journey_from_suite(
    body: JourneyFromSuiteRequest,
    user_info: dict = Depends(is_authenticated),
):
    """预览：按套件用例顺序生成 journey，不落库。"""
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    suite = await ApiTestSuite.get_or_none(id=body.suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    if suite.project_id != body.project_id:
        raise HTTPException(status_code=400, detail="套件不属于当前项目")

    layout = (body.layout or LAYOUT_SINGLE_PHASE).strip()
    if layout not in (LAYOUT_SINGLE_PHASE, LAYOUT_PER_CASE_PHASE):
        raise HTTPException(status_code=422, detail="layout 须为 single_phase 或 per_case_phase")

    suite_cases = await ApiSuiteCase.filter(suite_id=suite.id).order_by("sort").all()
    cases: list[dict] = []
    skipped: list[dict] = []
    for sc in suite_cases:
        case = await ApiTestCase.get_or_none(id=sc.case_id, is_del=False, project_id=body.project_id)
        if not case:
            skipped.append({"case_id": sc.case_id, "reason": "用例不存在或不属于当前项目"})
            continue
        cases.append({"case_id": case.id, "case_name": case.name})

    if not cases:
        raise HTTPException(status_code=422, detail="套件无可用用例，无法生成链路")

    journey = suite_cases_to_journey(cases, layout=layout, suite_name=suite.name or "")
    scene_items = journey_to_scene_items({"journey": journey})
    return {
        "suite_id": suite.id,
        "suite_name": suite.name,
        "layout": layout,
        "journey": journey,
        "scene_items": scene_items,
        "cases": cases,
        "skipped": skipped,
    }


@router.get("/{scene_id}", summary="场景详情")
async def get_scene_detail(scene: PerfScene = Depends(get_scene_for_viewer)):
    """获取性能测试场景详情"""
    return await _scene_detail_payload(scene)


@router.put("/{scene_id}", summary="更新性能测试场景",
            dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def update_scene(
    item: PerfSceneUpdate,
    scene: PerfScene = Depends(get_scene_for_member),
):
    """更新性能测试场景"""
    if item.name is not None:
        scene.name = item.name
    if item.description is not None:
        scene.description = item.description
    if "catalog_id" in item.model_fields_set:
        if item.catalog_id is not None:
            await resolve_catalog(scene.project_id, item.catalog_id)
        scene.catalog_id = item.catalog_id
    if item.scene_items is not None:
        merged_config = item.config if item.config is not None else PerfConfig(**(scene.config or {}))
        await validate_scene_items(item.scene_items, scene.project_id, merged_config)
        scene.scene_items = [si.model_dump() for si in item.scene_items]
    if item.config is not None:
        await validate_perf_config(item.config)
        if is_journey_mode(normalize_perf_mode(item.config.mode or "fixed")):
            await validate_scene_items([], scene.project_id, item.config)
        scene.config = item.config.model_dump()
    
    await scene.save()
    return await _scene_detail_payload(scene)


@router.delete("/{scene_id}", summary="删除性能测试场景", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def delete_scene(scene: PerfScene = Depends(get_scene_for_member)):
    """删除性能测试场景（软删除）"""
    scene.is_del = True
    await scene.save()


@router.post("/{scene_id}/clone", summary="复制性能测试场景",
             dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def clone_scene(
    scene: PerfScene = Depends(get_scene_for_member),
    username: str = Depends(get_current_username),
):
    """复制性能测试场景（基于现有场景创建新场景，名称加'-副本'后缀）"""
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
        catalog_id=scene.catalog_id,
        scene_items=scene.scene_items,
        config=scene.config,
        create_by=username
    )
    
    return await _scene_detail_payload(new_scene)


# ========== CSV 参数化数据管理 ==========

@router.post(
    "/{scene_id}/csv-upload",
    summary="上传 CSV 参数化数据",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def upload_csv(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="仅解析预览，不写入场景（供编辑页选文件后暂存）"),
    strategy: Optional[str] = Query(None, description="落库时的分配策略；缺省 round_robin"),
    scene: PerfScene = Depends(get_scene_for_member),
):
    """上传 CSV 文件，解析为 JSON 存储到场景；dry_run=true 时只校验并返回预览。"""
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

    valid_strategies = ("round_robin", "unique", "random")
    resolved_strategy = strategy if strategy in valid_strategies else "round_robin"

    if not dry_run:
        scene.csv_data = rows
        scene.csv_config = {
            "enabled": True,
            "strategy": resolved_strategy,
            "file_name": file.filename,
            "columns": columns,
            "row_count": len(rows)
        }
        await scene.save()

    return {
        "message": "解析成功（未写入，请保存场景）" if dry_run else "上传成功",
        "dry_run": dry_run,
        "file_name": file.filename,
        "row_count": len(rows),
        "columns": columns,
        "preview": rows[:5],
        "strategy": resolved_strategy,
    }


@router.get("/{scene_id}/csv-preview", summary="预览 CSV 数据")
async def preview_csv(
    limit: int = Query(20, ge=1, le=100),
    scene: PerfScene = Depends(get_scene_for_viewer),
):
    """预览场景的 CSV 数据"""
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


@router.delete(
    "/{scene_id}/csv",
    summary="删除 CSV 参数化数据",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_csv(scene: PerfScene = Depends(get_scene_for_member)):
    """删除场景的 CSV 数据"""
    scene.csv_data = None
    scene.csv_config = {}
    await scene.save()
    return {"message": "CSV 数据已删除"}


@router.put(
    "/{scene_id}/csv-config",
    summary="更新 CSV 配置",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def update_csv_config(config: dict, scene: PerfScene = Depends(get_scene_for_member)):
    """更新 CSV 分配策略等配置"""
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


class BaselinePinRequest(BaseModel):
    record_id: int = Field(..., description="要钉选为基线的执行记录ID")
    thresholds: Optional[dict] = Field(
        None,
        description="可选阈值覆盖，默认 p95_degrade_pct/qps_degrade_pct/error_rate_increase",
    )


@router.put(
    "/{scene_id}/baseline",
    summary="钉选场景基线记录",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def pin_scene_baseline(body: BaselinePinRequest, scene: PerfScene = Depends(get_scene_for_member)):
    record = await PerfRecord.get_or_none(id=body.record_id, scene_id=scene.id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在或不属于该场景")
    if record.status not in ("success", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="仅可钉选已结束的执行记录")
    scene.baseline_record_id = record.id
    if body.thresholds is not None:
        scene.baseline_policy = normalize_baseline_thresholds(body.thresholds)
    elif not scene.baseline_policy:
        scene.baseline_policy = dict(DEFAULT_BASELINE_THRESHOLDS)
    await scene.save()
    return {
        "message": "基线已钉选",
        "baseline_record_id": scene.baseline_record_id,
        "baseline_policy": normalize_baseline_thresholds(scene.baseline_policy),
    }


@router.delete(
    "/{scene_id}/baseline",
    summary="清除场景基线",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def clear_scene_baseline(scene: PerfScene = Depends(get_scene_for_member)):
    scene.baseline_record_id = None
    await scene.save()
    return {"message": "基线已清除"}


@router.get("/{scene_id}/baseline", summary="查看场景基线")
async def get_scene_baseline(scene: PerfScene = Depends(get_scene_for_viewer)):
    baseline = None
    if scene.baseline_record_id:
        rec = await PerfRecord.get_or_none(id=scene.baseline_record_id)
        if rec:
            baseline = {
                "record_id": rec.id,
                "status": rec.status,
                "started_at": rec.started_at.strftime("%Y-%m-%d %H:%M:%S") if rec.started_at else None,
                "qps": rec.qps,
                "p95_response_time": rec.p95_response_time,
                "error_rate": rec.error_rate,
                "total_requests": rec.total_requests,
            }
    return {
        "baseline_record_id": scene.baseline_record_id,
        "baseline_policy": normalize_baseline_thresholds(scene.baseline_policy),
        "baseline": baseline,
        "default_thresholds": DEFAULT_BASELINE_THRESHOLDS,
    }


@router.get("/{scene_id}/baseline-trend", summary="场景相对基线的近期趋势")
async def get_scene_baseline_trend(
    limit: int = Query(20, ge=1, le=50, description="最近成功记录条数"),
    scene: PerfScene = Depends(get_scene_for_viewer),
):
    """返回同场景近期 success 记录的 QPS/P95/错误率点列，附钉选基线与阈值告警标记。"""
    from app.modules.perf.metrics_accuracy import evaluate_baseline_alerts

    scene_id = scene.id
    policy = normalize_baseline_thresholds(scene.baseline_policy)
    baseline_summary = None
    baseline_rec = None
    if scene.baseline_record_id:
        baseline_rec = await PerfRecord.get_or_none(id=scene.baseline_record_id)
        if baseline_rec:
            baseline_summary = {
                "record_id": baseline_rec.id,
                "started_at": baseline_rec.started_at.strftime("%Y-%m-%d %H:%M:%S") if baseline_rec.started_at else None,
                "qps": float(baseline_rec.qps or 0),
                "p95_response_time": float(baseline_rec.p95_response_time or 0),
                "error_rate": float(baseline_rec.error_rate or 0),
                "total_requests": int(baseline_rec.total_requests or 0),
            }

    # 取最近 N 条成功记录，再按时间升序返回（便于折线图）
    recent = await (
        PerfRecord.filter(scene_id=scene_id, status="success")
        .order_by("-id")
        .limit(limit)
        .only(
            "id", "started_at", "qps", "p95_response_time", "error_rate",
            "total_requests", "avg_response_time",
        )
        .all()
    )
    recent = list(reversed(recent))

    b_qps = float(baseline_rec.qps or 0) if baseline_rec else 0.0
    b_p95 = float(baseline_rec.p95_response_time or 0) if baseline_rec else 0.0
    b_err = float(baseline_rec.error_rate or 0) if baseline_rec else 0.0

    points = []
    for rec in recent:
        qps = float(rec.qps or 0)
        p95 = float(rec.p95_response_time or 0)
        err = float(rec.error_rate or 0)
        alerts = []
        if baseline_rec:
            alerts = evaluate_baseline_alerts(
                current_qps=qps,
                baseline_qps=b_qps,
                current_p95=p95,
                baseline_p95=b_p95,
                current_error_rate=err,
                baseline_error_rate=b_err,
                thresholds=policy,
            )
        points.append({
            "record_id": rec.id,
            "started_at": rec.started_at.strftime("%Y-%m-%d %H:%M:%S") if rec.started_at else None,
            "qps": qps,
            "p95_response_time": p95,
            "error_rate": err,
            "avg_response_time": float(rec.avg_response_time or 0),
            "total_requests": int(rec.total_requests or 0),
            "has_alert": bool(alerts),
            "alerts": alerts,
        })

    return {
        "scene_id": scene_id,
        "baseline": baseline_summary,
        "policy": policy,
        "points": points,
    }
