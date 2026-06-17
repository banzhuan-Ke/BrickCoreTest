"""接口自动化测试计划 API"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Depends, Query, status, BackgroundTasks
from fastapi.responses import HTMLResponse
from tortoise import connections
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from app.models.http import (
    ApiTestPlan, ApiPlanItem, ApiTestSuite, ApiTestCase,
    ApiSuiteCase, ApiSuiteRunRecord, ApiPlanRunRecord, ApiCronJob,
)
from app.models.sys import TestCatalog
from app.schemas.http import (
    ApiPlanCreate, ApiPlanUpdate, ApiPlanOut, ApiPlanListResponse, ApiPlanListSummary,
    ApiPlanDetailOut, ApiPlanItemIn, ApiPlanItemOut,
    ApiPlanItemsUpdateRequest, ApiPlanAddSuiteRequest, ApiPlanAddCasesRequest,
    ApiPlanRunRequest, ApiPlanRunResult, ApiPlanItemRunResult,
    ApiPlanRunRecordOut, ApiPlanRunRecordDetail, ApiPlanRunRecordListResponse,
    ApiPlanAsyncRunResponse,
    ApiPlanSaveAsTemplateRequest, ApiPlanFromTemplateRequest,
)
from app.core.auth import is_authenticated, require_permissions, get_current_username
from app.core.permissions import API_PLAN_VIEW, API_PLAN_EDIT
from app.core.notification import NotificationService
from app.core.catalog_utils import apply_catalog_filter, resolve_catalog
from .utils import api_run_result_to_case_display, normalize_plan_item_results
from app.core.api_report_export import sum_plan_item_results_http_ms
from app.core.data_tools.inline_tools import ensure_dt_cache

router = APIRouter(
    tags=["接口测试计划"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(API_PLAN_VIEW))]
)


# ============ 辅助函数 ============

def _normalize_plan_variables(raw) -> dict:
    """兼容历史数据：variables 可能为 null 或非 dict"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _normalize_depends_on(raw) -> List[int]:
    """兼容历史数据：depends_on 可能含字符串或脏数据"""
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out: List[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _detect_cycle_by_sort(dep_by_sort: List[List[int]]) -> bool:
    """按 sort 序号检测 depends_on 是否存在循环"""
    n = len(dep_by_sort)
    visited: set = set()
    in_stack: set = set()

    def dfs(idx: int) -> bool:
        if idx in in_stack:
            return True
        if idx in visited:
            return False
        visited.add(idx)
        in_stack.add(idx)
        for dep in dep_by_sort[idx]:
            if 0 <= dep < n and dfs(dep):
                return True
        in_stack.discard(idx)
        return False

    return any(dfs(i) for i in range(n) if i not in visited)


def _depends_on_to_sort_indices(deps, self_idx: int, total: int) -> List[int]:
    """将 depends_on 规范为同次请求内的 sort 序号（0-based）"""
    out: List[int] = []
    for x in deps or []:
        try:
            v = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= v < total and v != self_idx and v not in out:
            out.append(v)
    return out


def _detect_cycle(items: list) -> bool:
    """DFS 检测 depends_on 是否存在循环，返回 True 表示有环"""
    id_map = {item.id: item for item in items}
    visited: set = set()
    in_stack: set = set()

    def dfs(node_id: int) -> bool:
        if node_id in in_stack:
            return True   # 发现环
        if node_id in visited:
            return False
        visited.add(node_id)
        in_stack.add(node_id)
        node = id_map.get(node_id)
        if node:
            for dep_id in _normalize_depends_on(node.depends_on):
                if dfs(dep_id):
                    return True
        in_stack.discard(node_id)
        return False

    return any(dfs(item.id) for item in items if item.id not in visited)

async def _build_items_out(plan_id: int) -> List[ApiPlanItemOut]:
    """构建计划 Items 输出列表"""
    items = await ApiPlanItem.filter(plan_id=plan_id).order_by("sort").all()
    result = []
    for item in items:
        item_out = ApiPlanItemOut(
            id=item.id,
            item_type=item.item_type,
            sort=item.sort,
            depends_on=_normalize_depends_on(item.depends_on),
        )
        if item.item_type == "suite" and item.suite_id:
            suite = await ApiTestSuite.get_or_none(id=item.suite_id)
            if suite:
                item_out.suite_id = suite.id
                item_out.suite_name = suite.name
        elif item.item_type == "case" and item.case_id:
            case = await ApiTestCase.get_or_none(id=item.case_id)
            if case:
                item_out.case_id = case.id
                item_out.case_name = case.name
                # 获取接口信息
                try:
                    api = await case.api
                    if api:
                        item_out.api_name = api.name
                        item_out.api_method = api.method
                except Exception:
                    pass
        result.append(item_out)
    return result


async def _get_plan_or_404(plan_id: int) -> ApiTestPlan:
    plan = await ApiTestPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    return plan


def _empty_item_stats(plan_ids: List[int]) -> Dict[int, Dict[str, int]]:
    return {pid: {"suite": 0, "case": 0, "total": 0} for pid in plan_ids}


async def _load_item_stats_by_plan(plan_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """按计划聚合条目数（仅拉取 plan_id、item_type 字段）。"""
    stats = _empty_item_stats(plan_ids)
    if not plan_ids:
        return stats
    rows = await ApiPlanItem.filter(plan_id__in=plan_ids).values("plan_id", "item_type")
    for row in rows:
        pid = row["plan_id"]
        if pid not in stats:
            stats[pid] = {"suite": 0, "case": 0, "total": 0}
        stats[pid]["total"] += 1
        if row["item_type"] == "suite":
            stats[pid]["suite"] += 1
        elif row["item_type"] == "case":
            stats[pid]["case"] += 1
    return stats


async def _load_run_count_by_plan(plan_ids: List[int]) -> Dict[int, int]:
    """按计划 COUNT 执行次数，避免全表排序。"""
    result = {pid: 0 for pid in plan_ids}
    if not plan_ids:
        return result
    rows = (
        await ApiPlanRunRecord.filter(plan_id__in=plan_ids)
        .annotate(cnt=Count("id"))
        .group_by("plan_id")
        .values("plan_id", "cnt")
    )
    for row in rows:
        result[row["plan_id"]] = int(row["cnt"])
    return result


async def _load_last_run_by_plan(plan_ids: List[int]) -> Dict[int, ApiPlanRunRecord]:
    """每个计划最近一条执行记录（按 id 取最新，避免 order_by 全表排序）。"""
    if not plan_ids:
        return {}
    conn = connections.get("default")
    placeholders = ",".join(["%s"] * len(plan_ids))
    sql = f"""
        SELECT r.id FROM api_plan_run_record r
        INNER JOIN (
            SELECT plan_id, MAX(id) AS max_id
            FROM api_plan_run_record
            WHERE plan_id IN ({placeholders})
            GROUP BY plan_id
        ) t ON r.id = t.max_id
    """
    _, rows = await conn.execute_query(sql, plan_ids)
    record_ids = []
    for row in rows:
        if isinstance(row, dict):
            record_ids.append(row.get("id") or next(iter(row.values()), None))
        elif isinstance(row, (list, tuple)):
            record_ids.append(row[0])
    record_ids = [rid for rid in record_ids if rid is not None]
    if not record_ids:
        return {}
    records = await ApiPlanRunRecord.filter(id__in=record_ids).all()
    return {r.plan_id: r for r in records}


async def _load_catalog_map_for_plans(plan_ids: List[int]) -> Dict[int, str]:
    catalog_ids: Set[int] = set()
    rows = await ApiTestPlan.filter(id__in=plan_ids).values("catalog_id")
    for row in rows:
        if row["catalog_id"]:
            catalog_ids.add(row["catalog_id"])
    if not catalog_ids:
        return {}
    catalogs = await TestCatalog.filter(id__in=list(catalog_ids)).all()
    return {c.id: c.name for c in catalogs}


async def _load_cron_stats_by_plan(plan_ids: List[int]) -> tuple:
    cron_count_map: Dict[int, int] = {pid: 0 for pid in plan_ids}
    cron_enabled_map: Dict[int, int] = {pid: 0 for pid in plan_ids}
    if not plan_ids:
        return cron_count_map, cron_enabled_map
    rows = await ApiCronJob.filter(plan_id__in=plan_ids, is_del=False).values("plan_id", "state")
    for row in rows:
        pid = row["plan_id"]
        if pid is None:
            continue
        cron_count_map[pid] = cron_count_map.get(pid, 0) + 1
        if row["state"]:
            cron_enabled_map[pid] = cron_enabled_map.get(pid, 0) + 1
    return cron_count_map, cron_enabled_map


async def _build_plan_list_context(plan_ids: List[int]):
    """批量加载列表行所需的目录名、条目分布、执行与定时任务统计。"""
    if not plan_ids:
        return {}, {}, {}, {}, {}, {}

    catalog_map = await _load_catalog_map_for_plans(plan_ids)
    item_stats = await _load_item_stats_by_plan(plan_ids)
    run_count_map = await _load_run_count_by_plan(plan_ids)
    last_run_map = await _load_last_run_by_plan(plan_ids)
    cron_count_map, cron_enabled_map = await _load_cron_stats_by_plan(plan_ids)

    return catalog_map, item_stats, run_count_map, last_run_map, cron_count_map, cron_enabled_map


def _plan_out_from_row(
    plan: ApiTestPlan,
    project_id: int,
    catalog_map: Dict[int, str],
    item_stats: Dict[int, Dict[str, int]],
    run_count_map: Dict[int, int],
    last_run_map: Dict[int, ApiPlanRunRecord],
    cron_count_map: Dict[int, int],
    cron_enabled_map: Dict[int, int],
) -> ApiPlanOut:
    stats = item_stats.get(plan.id, {"suite": 0, "case": 0, "total": 0})
    last_run = last_run_map.get(plan.id)
    return ApiPlanOut(
        id=plan.id,
        name=plan.name,
        project_id=project_id,
        description=plan.description,
        env_id=plan.env_id,
        variables=_normalize_plan_variables(plan.variables),
        parallel=plan.parallel,
        catalog_id=plan.catalog_id,
        catalog_name=catalog_map.get(plan.catalog_id) if plan.catalog_id else None,
        item_count=stats["total"],
        suite_item_count=stats["suite"],
        case_item_count=stats["case"],
        run_count=run_count_map.get(plan.id, 0),
        last_run_status=last_run.status if last_run else None,
        last_run_time=last_run.start_time if last_run else None,
        cron_job_count=cron_count_map.get(plan.id, 0),
        cron_enabled_count=cron_enabled_map.get(plan.id, 0),
        is_template=bool(getattr(plan, "is_template", False)),
        create_by=plan.create_by,
        update_by=plan.update_by,
        create_time=plan.create_time,
        update_time=plan.update_time,
    )


async def _build_plan_list_summary(qs, plan_ids: List[int]) -> ApiPlanListSummary:
    """按当前筛选范围汇总计划页统计（聚合查询，避免加载全部执行记录）。"""
    if not plan_ids:
        return ApiPlanListSummary()

    plan_count = len(plan_ids)
    parallel_plans = await qs.filter(parallel=True).count()
    uncataloged = await qs.filter(catalog_id__isnull=True).count()

    item_stats = await _load_item_stats_by_plan(plan_ids)
    total_items = sum(s["total"] for s in item_stats.values())
    suite_items = sum(s["suite"] for s in item_stats.values())
    case_items = sum(s["case"] for s in item_stats.values())

    run_count_map = await _load_run_count_by_plan(plan_ids)
    total_runs = sum(run_count_map.values())

    cron_count_map, cron_enabled_map = await _load_cron_stats_by_plan(plan_ids)
    cron_job_count = sum(cron_count_map.values())
    cron_enabled_count = sum(cron_enabled_map.values())

    since = datetime.now() - timedelta(days=7)
    runs_7d = await ApiPlanRunRecord.filter(plan_id__in=plan_ids, start_time__gte=since).count()

    run_finished_count = await ApiPlanRunRecord.filter(
        plan_id__in=plan_ids,
        status__in=["success", "failed"],
    ).count()
    run_success_count = await ApiPlanRunRecord.filter(
        plan_id__in=plan_ids,
        status="success",
    ).count()
    run_success_rate = None
    if run_finished_count > 0:
        run_success_rate = round(run_success_count * 100.0 / run_finished_count, 1)

    return ApiPlanListSummary(
        plan_count=plan_count,
        total_items=total_items,
        suite_items=suite_items,
        case_items=case_items,
        parallel_plans=parallel_plans,
        serial_plans=plan_count - parallel_plans,
        uncataloged_plans=uncataloged,
        total_runs=total_runs,
        runs_7d=runs_7d,
        run_success_count=run_success_count,
        run_finished_count=run_finished_count,
        run_success_rate=run_success_rate,
        cron_job_count=cron_job_count,
        cron_enabled_count=cron_enabled_count,
    )


async def _copy_plan_items(source_plan_id: int, target_plan_id: int) -> None:
    items = await ApiPlanItem.filter(plan_id=source_plan_id).order_by("sort")
    for i, it in enumerate(items):
        await ApiPlanItem.create(
            plan_id=target_plan_id,
            item_type=it.item_type,
            suite_id=it.suite_id,
            case_id=it.case_id,
            sort=i,
            depends_on=it.depends_on or [],
        )


# ============ 计划 CRUD ============

@router.post("/plan", summary="创建测试计划", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def create_plan(item: ApiPlanCreate, username: str = Depends(get_current_username)):
    """创建接口测试计划"""
    from app.models.sys import Project
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)

    plan = await ApiTestPlan.create(
        name=item.name,
        project_id=item.project_id,
        description=item.description,
        env_id=item.env_id,
        variables=item.variables,
        parallel=item.parallel,
        catalog_id=item.catalog_id,
        is_template=bool(getattr(item, "is_template", False)),
        create_by=username,
        update_by=username,
    )
    return ApiPlanOut(
        id=plan.id,
        name=plan.name,
        project_id=item.project_id,
        description=plan.description,
        env_id=plan.env_id,
        variables=_normalize_plan_variables(plan.variables),
        parallel=bool(plan.parallel),
        catalog_id=plan.catalog_id,
        is_template=bool(plan.is_template),
        item_count=0,
        create_by=plan.create_by,
        update_by=plan.update_by,
        create_time=plan.create_time,
        update_time=plan.update_time,
    )


@router.get("/plan", summary="计划列表", response_model=ApiPlanListResponse)
async def list_plans(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None, description="关键字搜索"),
    catalog_id: Optional[int] = Query(None, description="目录ID"),
    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
    templates_only: bool = Query(False, description="仅返回计划模板"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=5000, description="每页数量"),
):
    """获取测试计划列表（分页）；默认不含模板，templates_only=true 时仅返回模板"""
    filters = {"project_id": project_id, "is_del": False, "is_template": templates_only}
    qs = ApiTestPlan.filter(**filters)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    if catalog_id is not None:
        await resolve_catalog(project_id, catalog_id)
        qs = await apply_catalog_filter(qs, project_id, catalog_id, include_children=include_children)

    total = await qs.count()
    all_plan_ids = await qs.values_list("id", flat=True)
    summary = await _build_plan_list_summary(qs, list(all_plan_ids))

    plans = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    page_ids = [p.id for p in plans]
    catalog_map, item_stats, run_count_map, last_run_map, cron_count_map, cron_enabled_map = await _build_plan_list_context(page_ids)

    data = [
        _plan_out_from_row(
            plan, project_id, catalog_map, item_stats,
            run_count_map, last_run_map, cron_count_map, cron_enabled_map,
        )
        for plan in plans
    ]

    return ApiPlanListResponse(data=data, total=total, page=page, size=size, summary=summary)


@router.get("/plan/{plan_id}", summary="计划详情（含 items）", response_model=ApiPlanDetailOut)
async def get_plan_detail(plan_id: int):
    """获取测试计划详情，包含所有 items"""
    plan = await _get_plan_or_404(plan_id)
    project_id = (await plan.project).id
    items = await _build_items_out(plan_id)
    return ApiPlanDetailOut(
        id=plan.id,
        name=plan.name,
        project_id=project_id,
        description=plan.description,
        env_id=plan.env_id,
        variables=_normalize_plan_variables(plan.variables),
        parallel=bool(plan.parallel),
        catalog_id=plan.catalog_id,
        item_count=len(items),
        create_by=plan.create_by,
        update_by=plan.update_by,
        create_time=plan.create_time,
        update_time=plan.update_time,
        items=items,
    )


@router.put("/plan/{plan_id}", summary="更新测试计划",
            dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def update_plan(plan_id: int, item: ApiPlanUpdate, username: str = Depends(get_current_username)):
    """更新测试计划基本信息"""
    plan = await _get_plan_or_404(plan_id)
    plan.name = item.name
    plan.description = item.description
    plan.env_id = item.env_id
    plan.variables = item.variables
    plan.parallel = item.parallel
    if item.catalog_id is not None:
        await resolve_catalog((await plan.project).id, item.catalog_id)
        plan.catalog_id = item.catalog_id
    plan.update_by = username
    await plan.save()

    project_id = (await plan.project).id
    item_count = await ApiPlanItem.filter(plan_id=plan_id).count()
    return ApiPlanOut(
        id=plan.id,
        name=plan.name,
        project_id=project_id,
        description=plan.description,
        env_id=plan.env_id,
        variables=_normalize_plan_variables(plan.variables),
        parallel=bool(plan.parallel),
        catalog_id=plan.catalog_id,
        item_count=item_count,
        create_by=plan.create_by,
        update_by=plan.update_by,
        create_time=plan.create_time,
        update_time=plan.update_time,
    )


@router.delete("/plan/{plan_id}", summary="删除测试计划",
               dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def delete_plan(plan_id: int, username: str = Depends(get_current_username)):
    """软删除测试计划"""
    plan = await _get_plan_or_404(plan_id)
    plan.is_del = True
    plan.update_by = username
    await plan.save()
    return {"message": "删除成功"}


@router.post("/plan/batch-delete", summary="批量删除计划",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def batch_delete_plans(plan_ids: List[int], username: str = Depends(get_current_username)):
    """批量软删除测试计划"""
    await ApiTestPlan.filter(id__in=plan_ids, is_del=False).update(is_del=True, update_by=username)
    return {"message": f"已删除 {len(plan_ids)} 个计划"}


@router.post("/plan/{plan_id}/save-as-template", summary="另存为计划模板",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def save_plan_as_template(
    plan_id: int,
    req: ApiPlanSaveAsTemplateRequest,
    username: str = Depends(get_current_username),
):
    """复制当前计划为可复用模板（含 Items）"""
    source = await _get_plan_or_404(plan_id)
    if source.is_template:
        raise HTTPException(status_code=400, detail="该记录已是模板，请从模板创建新计划")

    template = await ApiTestPlan.create(
        name=req.name,
        project_id=source.project_id,
        description=source.description,
        env_id=source.env_id,
        variables=source.variables or {},
        parallel=source.parallel,
        catalog_id=source.catalog_id,
        is_template=True,
        create_by=username,
        update_by=username,
    )
    await _copy_plan_items(source.id, template.id)
    return {"id": template.id, "name": template.name, "message": "模板已保存"}


@router.post("/plan/from-template/{template_id}", summary="从模板创建计划",
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def create_plan_from_template(
    template_id: int,
    req: ApiPlanFromTemplateRequest,
    username: str = Depends(get_current_username),
):
    """基于模板快速创建测试计划"""
    from app.models.sys import Project

    template = await ApiTestPlan.get_or_none(id=template_id, is_del=False, is_template=True)
    if not template:
        raise HTTPException(status_code=404, detail="计划模板不存在")
    project = await Project.get_or_none(id=req.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if req.catalog_id is not None:
        await resolve_catalog(req.project_id, req.catalog_id)

    plan = await ApiTestPlan.create(
        name=req.name,
        project_id=req.project_id,
        description=template.description,
        env_id=req.env_id if req.env_id is not None else template.env_id,
        variables=template.variables or {},
        parallel=template.parallel,
        catalog_id=req.catalog_id if req.catalog_id is not None else template.catalog_id,
        is_template=False,
        create_by=username,
        update_by=username,
    )
    await _copy_plan_items(template.id, plan.id)
    return {"id": plan.id, "name": plan.name, "message": "已从模板创建计划"}


# ============ 计划内容（Items）管理 ============

@router.get("/plan/{plan_id}/items", summary="获取计划 Items")
async def get_plan_items(plan_id: int):
    """获取计划内容列表（按 sort 排序）"""
    await _get_plan_or_404(plan_id)
    items = await _build_items_out(plan_id)
    return {"data": items, "total": len(items)}


@router.put("/plan/{plan_id}/items", summary="全量更新计划 Items",
            dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def update_plan_items(plan_id: int, req: ApiPlanItemsUpdateRequest):
    """全量更新计划内容（先清空后重建）

    depends_on 传入同次请求 items 数组中的 sort 序号（0-based），保存时映射为新建 item 的数据库 ID。
    """
    await _get_plan_or_404(plan_id)
    total = len(req.items)
    dep_by_sort = [
        _depends_on_to_sort_indices(it.depends_on, i, total)
        for i, it in enumerate(req.items)
    ]
    if _detect_cycle_by_sort(dep_by_sort):
        raise HTTPException(status_code=422, detail="计划项依赖存在循环，请调整依赖关系")

    async with in_transaction():
        await ApiPlanItem.filter(plan_id=plan_id).delete()
        created: List[ApiPlanItem] = []
        for i, it in enumerate(req.items):
            item = await ApiPlanItem.create(
                plan_id=plan_id,
                item_type=it.item_type,
                suite_id=it.suite_id,
                case_id=it.case_id,
                sort=i,
                depends_on=[],
            )
            created.append(item)
        for i, item in enumerate(created):
            dep_ids = [created[j].id for j in dep_by_sort[i]]
            item.depends_on = dep_ids
            await item.save()
    items = await _build_items_out(plan_id)
    return {"data": items, "total": len(items)}


@router.post("/plan/{plan_id}/items/add-suite", summary="追加整套件",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def add_suite_to_plan(plan_id: int, req: ApiPlanAddSuiteRequest):
    """将整个套件追加到计划"""
    await _get_plan_or_404(plan_id)
    suite = await ApiTestSuite.get_or_none(id=req.suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")

    # 检查是否已存在
    exists = await ApiPlanItem.filter(plan_id=plan_id, item_type="suite", suite_id=req.suite_id).exists()
    if exists:
        raise HTTPException(status_code=400, detail="该套件已加入计划")

    # 计算 sort
    if req.sort is not None:
        sort_val = req.sort
    else:
        max_sort = await ApiPlanItem.filter(plan_id=plan_id).order_by("-sort").first()
        sort_val = (max_sort.sort + 1) if max_sort else 0

    item = await ApiPlanItem.create(
        plan_id=plan_id,
        item_type="suite",
        suite_id=req.suite_id,
        sort=sort_val,
    )
    return ApiPlanItemOut(
        id=item.id,
        item_type="suite",
        suite_id=suite.id,
        suite_name=suite.name,
        sort=sort_val,
    )


@router.post("/plan/{plan_id}/items/add-cases", summary="批量追加用例",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def add_cases_to_plan(plan_id: int, req: ApiPlanAddCasesRequest):
    """批量追加用例到计划"""
    await _get_plan_or_404(plan_id)

    # 当前已有的 case_id
    existing = await ApiPlanItem.filter(
        plan_id=plan_id, item_type="case"
    ).values_list("case_id", flat=True)
    existing_ids = set(existing)

    # 计算起始 sort
    if req.sort_start is not None:
        sort_start = req.sort_start
    else:
        max_item = await ApiPlanItem.filter(plan_id=plan_id).order_by("-sort").first()
        sort_start = (max_item.sort + 1) if max_item else 0

    added = []
    skipped = []
    offset = 0
    for case_id in req.case_ids:
        if case_id in existing_ids:
            skipped.append(case_id)
            continue
        case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
        if not case:
            skipped.append(case_id)
            continue
        item = await ApiPlanItem.create(
            plan_id=plan_id,
            item_type="case",
            case_id=case_id,
            sort=sort_start + offset,
        )
        existing_ids.add(case_id)
        added.append(item.id)
        offset += 1

    return {"added": len(added), "skipped": len(skipped), "message": f"成功加入 {len(added)} 个用例"}


@router.delete("/plan/{plan_id}/items/{item_id}", summary="删除计划中单个 Item",
               dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def remove_plan_item(plan_id: int, item_id: int):
    """删除计划中的单个 Item"""
    await _get_plan_or_404(plan_id)
    item = await ApiPlanItem.get_or_none(id=item_id, plan_id=plan_id)
    if not item:
        raise HTTPException(status_code=404, detail="计划项不存在")
    await item.delete()
    return {"message": "删除成功"}


# ============ 计划执行引擎（Phase 3.3 + 3.6.1 + 3.6.2 + 4.1）============

@router.post("/plan/{plan_id}/run", summary="执行测试计划",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def run_plan(plan_id: int, req: ApiPlanRunRequest, username: str = Depends(get_current_username)):
    """
    执行测试计划。
    - 遍历计划 items（按 sort 顺序）
    - item_type=suite：取套件下所有用例串行执行，套件维度记录 ApiSuiteRunRecord
    - item_type=case：直接执行单个用例（不创建套件记录）
    - 跨 item 之间传递 accumulated_vars，实现变量链式传递（串行模式）
    - stop_on_failure=True 时，任一用例失败即中止计划（串行模式）
    - parallel=True 时，所有 item 并发执行（变量不跨 item 传递）
    - 执行前检测 depends_on 循环依赖，串行时依赖失败则跳过当前 item
    变量优先级（低→高）：project_global_vars < env_vars < plan_vars < req_vars < pre_script < data_row
    """
    from app.routers.http.suites import run_single_case
    from app.models.sys import Environment, Project as ProjectModel

    plan = await _get_plan_or_404(plan_id)
    project_id = (await plan.project).id

    # 确定执行环境
    env_id = req.env_id or plan.env_id
    if not env_id:
        raise HTTPException(status_code=422, detail="请指定执行环境（计划未配置默认环境）")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="执行环境不存在")

    # 加载项目全局变量（优先级最低）
    project_obj = await ProjectModel.get_or_none(id=project_id)
    project_global_vars = (project_obj.global_vars or {}) if project_obj else {}

    # 合并变量：project_global_vars < plan_vars < req_vars
    accumulated_vars: dict = ensure_dt_cache({
        **project_global_vars,
        **(plan.variables or {}),
        **(req.variables or {}),
    })

    # 加载所有 items（按 sort 排序）
    items = await ApiPlanItem.filter(plan_id=plan_id).order_by("sort").all()
    if not items:
        raise HTTPException(status_code=422, detail="计划中没有任何 Item，请先添加套件或用例")

    # 依赖循环检测（Phase 3.6.1）
    if _detect_cycle(items):
        raise HTTPException(status_code=422, detail="计划 Item 存在循环依赖，无法执行")

    plan_start = time.time()
    total_count = 0
    success_count = 0
    failed_count = 0
    item_results: List[ApiPlanItemRunResult] = []

    # ============ 内部辅助：执行单个 item ============

    async def _execute_suite_item(item, variables: dict) -> ApiPlanItemRunResult:
        """执行套件类型的 item"""
        from app.core.api_suite_runner import execute_api_suite_cases

        item_start = time.time()
        suite = await ApiTestSuite.get_or_none(id=item.suite_id, is_del=False)
        if not suite:
            return ApiPlanItemRunResult(
                item_id=item.id, item_type="suite",
                name=f"套件#{item.suite_id}（已删除）",
                status="skipped", error="套件不存在或已删除",
            )

        suite_cases = await ApiSuiteCase.filter(suite_id=suite.id).order_by("sort").all()
        case_ids = [sc.case_id for sc in suite_cases]

        if not case_ids:
            return ApiPlanItemRunResult(
                item_id=item.id, item_type="suite",
                name=suite.name, status="skipped", error="套件中没有用例",
            )

        suite_record = await ApiSuiteRunRecord.create(
            suite_id=suite.id, project_id=project_id,
            status="running", trigger_type="plan",
            total_cases=len(case_ids),
            env_id=env_id, env_name=env.name, run_by=username,
        )

        run_result = await execute_api_suite_cases(
            suite=suite,
            env=env,
            case_ids=case_ids,
            suite_record=suite_record,
            username=username,
            variables=variables,
            project_global_vars=project_global_vars,
            auto_validate_schema=req.auto_validate_schema,
            stop_on_failure=suite.stop_on_failure or req.stop_on_failure,
        )
        case_results = run_result["case_results"]
        suite_success = run_result["success_count"]
        suite_failed = run_result["failed_count"]
        suite_total = len(case_results)
        hooks_result = run_result["hooks_result"]

        suite_record.status = "success" if suite_failed == 0 and hooks_result.get("success", True) else "failed"
        suite_record.success_cases = suite_success
        suite_record.failed_cases = suite_failed
        suite_record.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
        suite_record.duration = round((time.time() - item_start) * 1000, 2)
        suite_record.hooks_result = hooks_result
        await suite_record.save()

        return ApiPlanItemRunResult(
            item_id=item.id, item_type="suite", name=suite.name,
            status="success" if suite_failed == 0 and hooks_result.get("success", True) else "failed",
            total=suite_total, success=suite_success, failed=suite_failed,
            duration=round((time.time() - item_start) * 1000, 2),
            case_results=[api_run_result_to_case_display(r) for r in case_results],
        )

    async def _execute_case_item(item, variables: dict) -> ApiPlanItemRunResult:
        """执行单用例类型的 item"""
        item_start = time.time()
        result = await run_single_case(
            case_id=item.case_id, env_id=env_id,
            suite_record_id=None, username=username,
            variables=variables,
            auto_validate_schema=req.auto_validate_schema,
            project_global_vars=project_global_vars,
        )
        case_name = result.case_name or f"用例#{item.case_id}"
        return ApiPlanItemRunResult(
            item_id=item.id, item_type="case", name=case_name,
            status=result.status,
            total=1,
            success=1 if result.status == "success" else 0,
            failed=0 if result.status == "success" else 1,
            duration=round(result.response_time or 0, 2),
            case_results=[api_run_result_to_case_display(result)],
        )

    # ============ 并行执行分支（Phase 3.6.2）============
    if plan.parallel:
        initial_vars = dict(accumulated_vars)  # 每个 item 独立使用，不累积

        async def _run_item_parallel(item) -> ApiPlanItemRunResult:
            if item.item_type == "suite" and item.suite_id:
                return await _execute_suite_item(item, initial_vars)
            elif item.item_type == "case" and item.case_id:
                return await _execute_case_item(item, initial_vars)
            else:
                return ApiPlanItemRunResult(
                    item_id=item.id, item_type=item.item_type,
                    name="未知", status="skipped",
                    error="item 配置无效（缺少 suite_id 或 case_id）",
                )

        parallel_results = await asyncio.gather(
            *[_run_item_parallel(item) for item in items],
            return_exceptions=False,
        )
        item_results = list(parallel_results)
        for r in item_results:
            total_count += r.total
            success_count += r.success
            failed_count += r.failed

    # ============ 串行执行分支（Phase 3.6.1 依赖校验）============
    else:
        should_stop = False
        failed_item_ids: set = set()  # 已失败/跳过的 item ID

        for item in items:
            if should_stop:
                break

            # 依赖检查（Phase 3.6.1）
            dep_ids = item.depends_on or []
            unmet_deps = [d for d in dep_ids if d in failed_item_ids]
            if unmet_deps:
                item_results.append(ApiPlanItemRunResult(
                    item_id=item.id, item_type=item.item_type,
                    name=f"item#{item.id}",
                    status="skipped",
                    error=f"前置依赖 {unmet_deps} 失败，跳过执行",
                ))
                failed_item_ids.add(item.id)
                continue

            if item.item_type == "suite" and item.suite_id:
                r = await _execute_suite_item(item, accumulated_vars)
                item_results.append(r)
                total_count += r.total
                success_count += r.success
                failed_count += r.failed
                # 从 case_results 中累积提取变量
                for cr in (r.case_results or []):
                    if isinstance(cr, dict):
                        accumulated_vars.update(cr.get("extracted_vars") or {})
                if r.status != "success":
                    failed_item_ids.add(item.id)
                    if req.stop_on_failure:
                        should_stop = True

            elif item.item_type == "case" and item.case_id:
                r = await _execute_case_item(item, accumulated_vars)
                item_results.append(r)
                total_count += 1
                if r.status == "success":
                    success_count += 1
                else:
                    failed_count += 1
                    failed_item_ids.add(item.id)
                    if req.stop_on_failure:
                        should_stop = True
                # 累积提取变量
                for cr in (r.case_results or []):
                    if isinstance(cr, dict):
                        accumulated_vars.update(cr.get("extracted_vars") or {})

            else:
                item_results.append(ApiPlanItemRunResult(
                    item_id=item.id, item_type=item.item_type,
                    name="未知", status="skipped",
                    error="item 配置无效（缺少 suite_id 或 case_id）",
                ))

    plan_duration = round((time.time() - plan_start) * 1000, 2)
    overall_status = "success" if failed_count == 0 else "failed"

    # 持久化执行记录
    item_results_snapshot = [
        r.model_dump() if hasattr(r, 'model_dump') else r
        for r in item_results
    ]
    run_record = await ApiPlanRunRecord.create(
        plan_id=plan_id,
        project_id=project_id,
        status=overall_status,
        trigger_type="manual",
        total_cases=total_count,
        success_cases=success_count,
        failed_cases=failed_count,
        env_id=env_id,
        env_name=env.name,
        duration=plan_duration,
        item_results=item_results_snapshot,
        run_by=username,
        end_time=datetime.now(),
    )

    return ApiPlanRunResult(
        plan_id=plan_id,
        plan_name=plan.name,
        env_id=env_id,
        env_name=env.name,
        status=overall_status,
        total=total_count,
        success=success_count,
        failed=failed_count,
        duration=plan_duration,
        item_results=item_results,
        run_by=username,
        record_id=run_record.id,
    )


# ============ 计划异步执行（后台执行，立即返回 record_id）============

@router.post("/plan/{plan_id}/async-run", summary="异步执行测试计划（后台执行）",
             response_model=ApiPlanAsyncRunResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def run_plan_async(plan_id: int, req: ApiPlanRunRequest, background_tasks: BackgroundTasks, username: str = Depends(get_current_username)):
    """立即返回 record_id，后台执行计划，避免大量套件时请求超时"""
    from app.routers.http.suites import run_single_case
    from app.models.sys import Environment, Project as ProjectModel

    plan = await _get_plan_or_404(plan_id)
    project_id = (await plan.project).id

    env_id = req.env_id or plan.env_id
    if not env_id:
        raise HTTPException(status_code=422, detail="请指定执行环境（计划未配置默认环境）")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="执行环境不存在")

    items = await ApiPlanItem.filter(plan_id=plan_id).order_by("sort").all()
    if not items:
        raise HTTPException(status_code=422, detail="计划中没有任何 Item，请先添加套件或用例")

    if _detect_cycle(items):
        raise HTTPException(status_code=422, detail="计划 Item 存在循环依赖，无法执行")

    # 立即创建执行记录（status=running），返回 record_id
    run_record = await ApiPlanRunRecord.create(
        plan_id=plan_id,
        project_id=project_id,
        status="running",
        trigger_type=(req.trigger_type or "manual"),
        total_cases=0,
        success_cases=0,
        failed_cases=0,
        env_id=env_id,
        env_name=env.name,
        run_by=username,
        item_results=[],
    )

    async def _run_in_background():
        project_obj = await ProjectModel.get_or_none(id=project_id)
        project_global_vars = (project_obj.global_vars or {}) if project_obj else {}

        accumulated_vars: dict = ensure_dt_cache({
            **project_global_vars,
            **(plan.variables or {}),
            **(req.variables or {}),
        })

        plan_start = time.time()
        total_count = 0
        success_count = 0
        failed_count = 0
        bg_item_results: List[ApiPlanItemRunResult] = []

        async def _execute_suite_item(item, variables: dict) -> ApiPlanItemRunResult:
            from app.core.api_suite_runner import execute_api_suite_cases

            item_start = time.time()
            suite = await ApiTestSuite.get_or_none(id=item.suite_id, is_del=False)
            if not suite:
                return ApiPlanItemRunResult(
                    item_id=item.id, item_type="suite",
                    name=f"套件#{item.suite_id}（已删除）",
                    status="skipped", error="套件不存在或已删除",
                )
            suite_cases = await ApiSuiteCase.filter(suite_id=suite.id).order_by("sort").all()
            case_ids = [sc.case_id for sc in suite_cases]
            if not case_ids:
                return ApiPlanItemRunResult(
                    item_id=item.id, item_type="suite",
                    name=suite.name, status="skipped", error="套件中没有用例",
                )
            suite_record = await ApiSuiteRunRecord.create(
                suite_id=suite.id, project_id=project_id,
                status="running", trigger_type="plan",
                total_cases=len(case_ids),
                env_id=env_id, env_name=env.name, run_by=username,
            )

            run_result = await execute_api_suite_cases(
                suite=suite,
                env=env,
                case_ids=case_ids,
                suite_record=suite_record,
                username=username,
                variables=variables,
                project_global_vars=project_global_vars,
                auto_validate_schema=req.auto_validate_schema,
                stop_on_failure=suite.stop_on_failure or req.stop_on_failure,
            )
            case_results = run_result["case_results"]
            suite_success = run_result["success_count"]
            suite_failed = run_result["failed_count"]
            suite_total = len(case_results)
            hooks_result = run_result["hooks_result"]

            suite_record.status = "success" if suite_failed == 0 and hooks_result.get("success", True) else "failed"
            suite_record.success_cases = suite_success
            suite_record.failed_cases = suite_failed
            suite_record.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
            suite_record.duration = round((time.time() - item_start) * 1000, 2)
            suite_record.hooks_result = hooks_result
            await suite_record.save()
            return ApiPlanItemRunResult(
                item_id=item.id, item_type="suite", name=suite.name,
                status="success" if suite_failed == 0 and hooks_result.get("success", True) else "failed",
                total=suite_total, success=suite_success, failed=suite_failed,
                duration=round((time.time() - item_start) * 1000, 2),
                case_results=[api_run_result_to_case_display(r) for r in case_results],
            )

        async def _execute_case_item(item, variables: dict) -> ApiPlanItemRunResult:
            item_start = time.time()
            result = await run_single_case(
                case_id=item.case_id, env_id=env_id,
                suite_record_id=None, username=username,
                variables=variables,
                auto_validate_schema=req.auto_validate_schema,
                project_global_vars=project_global_vars,
            )
            case_name = result.case_name or f"用例#{item.case_id}"
            return ApiPlanItemRunResult(
                item_id=item.id, item_type="case", name=case_name,
                status=result.status, total=1,
                success=1 if result.status == "success" else 0,
                failed=0 if result.status == "success" else 1,
                duration=round(result.response_time or 0, 2),
                case_results=[api_run_result_to_case_display(result)],
            )

        try:
            if plan.parallel:
                initial_vars = dict(accumulated_vars)

                async def _run_item_parallel(item) -> ApiPlanItemRunResult:
                    if item.item_type == "suite" and item.suite_id:
                        return await _execute_suite_item(item, initial_vars)
                    elif item.item_type == "case" and item.case_id:
                        return await _execute_case_item(item, initial_vars)
                    return ApiPlanItemRunResult(
                        item_id=item.id, item_type=item.item_type,
                        name="未知", status="skipped",
                        error="item 配置无效（缺少 suite_id 或 case_id）",
                    )

                parallel_results = await asyncio.gather(
                    *[_run_item_parallel(item) for item in items],
                    return_exceptions=False,
                )
                bg_item_results = list(parallel_results)
                for r in bg_item_results:
                    total_count += r.total
                    success_count += r.success
                    failed_count += r.failed
            else:
                should_stop = False
                failed_item_ids: set = set()
                for item in items:
                    if should_stop:
                        break
                    dep_ids = item.depends_on or []
                    unmet_deps = [d for d in dep_ids if d in failed_item_ids]
                    if unmet_deps:
                        bg_item_results.append(ApiPlanItemRunResult(
                            item_id=item.id, item_type=item.item_type,
                            name=f"item#{item.id}", status="skipped",
                            error=f"前置依赖 {unmet_deps} 失败，跳过执行",
                        ))
                        failed_item_ids.add(item.id)
                        continue
                    if item.item_type == "suite" and item.suite_id:
                        r = await _execute_suite_item(item, accumulated_vars)
                        bg_item_results.append(r)
                        total_count += r.total
                        success_count += r.success
                        failed_count += r.failed
                        for cr in (r.case_results or []):
                            if isinstance(cr, dict):
                                accumulated_vars.update(cr.get("extracted_vars") or {})
                        if r.status != "success":
                            failed_item_ids.add(item.id)
                            if req.stop_on_failure:
                                should_stop = True
                    elif item.item_type == "case" and item.case_id:
                        r = await _execute_case_item(item, accumulated_vars)
                        bg_item_results.append(r)
                        total_count += 1
                        if r.status == "success":
                            success_count += 1
                        else:
                            failed_count += 1
                            failed_item_ids.add(item.id)
                            if req.stop_on_failure:
                                should_stop = True
                        for cr in (r.case_results or []):
                            if isinstance(cr, dict):
                                accumulated_vars.update(cr.get("extracted_vars") or {})
                    else:
                        bg_item_results.append(ApiPlanItemRunResult(
                            item_id=item.id, item_type=item.item_type,
                            name="未知", status="skipped",
                            error="item 配置无效（缺少 suite_id 或 case_id）",
                        ))

            plan_duration = round((time.time() - plan_start) * 1000, 2)
            overall_status = "success" if failed_count == 0 else "failed"
            run_record.status = overall_status
            run_record.total_cases = total_count
            run_record.success_cases = success_count
            run_record.failed_cases = failed_count
            run_record.duration = plan_duration
            run_record.end_time = datetime.now()
            run_record.item_results = [
                r.model_dump() if hasattr(r, 'model_dump') else r for r in bg_item_results
            ]
            await run_record.save()
        except Exception as e:
            run_record.status = "failed"
            run_record.end_time = datetime.now()
            await run_record.save()
            print(f"[PlanAsyncRun] 计划 {plan_id} 后台执行异常: {e}")

    background_tasks.add_task(_run_in_background)
    return ApiPlanAsyncRunResponse(record_id=run_record.id)


# ============ 计划执行记录（报告）============

@router.get("/plan/{plan_id}/records", summary="计划执行记录列表")
async def list_plan_records(
    plan_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="状态筛选: success/failed"),
):
    """获取测试计划的执行历史记录列表"""
    await _get_plan_or_404(plan_id)
    qs = ApiPlanRunRecord.filter(plan_id=plan_id)
    if status:
        qs = qs.filter(status=status)
    total = await qs.count()
    records = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    data = [
        ApiPlanRunRecordOut(
            id=r.id,
            plan_id=r.plan_id,
            project_id=r.project_id,
            status=r.status,
            trigger_type=r.trigger_type,
            total_cases=r.total_cases,
            success_cases=r.success_cases,
            failed_cases=r.failed_cases,
            env_id=r.env_id,
            env_name=r.env_name,
            duration=r.duration,
            http_duration=sum_plan_item_results_http_ms(r.item_results) or None,
            run_by=r.run_by,
            start_time=r.start_time,
            end_time=r.end_time,
        )
        for r in records
    ]
    return ApiPlanRunRecordListResponse(data=data, total=total, page=page, size=size)


@router.get("/plan/{plan_id}/records/{record_id}", summary="计划执行记录详情")
async def get_plan_record_detail(plan_id: int, record_id: int):
    """获取测试计划单次执行的详情（含各 item 结果）"""
    await _get_plan_or_404(plan_id)
    record = await ApiPlanRunRecord.get_or_none(id=record_id, plan_id=plan_id)
    if not record:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    plan = await record.plan
    normalized_items = normalize_plan_item_results(record.item_results)
    return ApiPlanRunRecordDetail(
        id=record.id,
        plan_id=record.plan_id,
        plan_name=plan.name if plan else "未知计划",
        project_id=record.project_id,
        status=record.status,
        trigger_type=record.trigger_type,
        total_cases=record.total_cases,
        success_cases=record.success_cases,
        failed_cases=record.failed_cases,
        env_id=record.env_id,
        env_name=record.env_name,
        duration=record.duration,
        http_duration=sum_plan_item_results_http_ms(normalized_items) or None,
        run_by=record.run_by,
        start_time=record.start_time,
        end_time=record.end_time,
        item_results=normalized_items,
    )


@router.get("/plan-records/{record_id}", summary="计划执行记录详情(通过record_id)")
async def get_plan_record_by_id(record_id: int):
    """通过 record_id 直接获取计划执行记录详情（无需 plan_id，用于报告页）"""
    record = await ApiPlanRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    plan = await record.plan
    normalized_items = normalize_plan_item_results(record.item_results)
    return ApiPlanRunRecordDetail(
        id=record.id,
        plan_id=record.plan_id,
        plan_name=plan.name if plan else "未知计划",
        project_id=record.project_id,
        status=record.status,
        trigger_type=record.trigger_type,
        total_cases=record.total_cases,
        success_cases=record.success_cases,
        failed_cases=record.failed_cases,
        env_id=record.env_id,
        env_name=record.env_name,
        duration=record.duration,
        http_duration=sum_plan_item_results_http_ms(normalized_items) or None,
        run_by=record.run_by,
        start_time=record.start_time,
        end_time=record.end_time,
        item_results=normalized_items,
    )


@router.post("/plan-records/batch-delete", summary="批量删除计划执行记录",
             dependencies=[Depends(require_permissions(API_PLAN_EDIT))])
async def batch_delete_plan_records(record_ids: List[int]):
    """批量删除计划执行记录"""
    if not record_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    deleted = 0
    for rid in record_ids:
        record = await ApiPlanRunRecord.get_or_none(id=rid)
        if record:
            await record.delete()
            deleted += 1
    return {"detail": f"已删除 {deleted} 条计划执行记录"}


@router.get("/plan-records/{record_id}/report", summary="导出计划执行报告(HTML)")
async def export_plan_report(record_id: int):
    """导出计划执行记录为 HTML 报告"""
    from app.core.api_report_export import generate_api_html_report
    record = await ApiPlanRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    plan = await record.plan
    # 规范化 item_results（补齐 response_body，兼容旧数据）
    normalized_items = normalize_plan_item_results(record.item_results)
    all_case_results = []
    for item in normalized_items:
        all_case_results.extend(item.get("case_results") or [])
    plan_record = {
        "id": record.id,
        "suite_name": plan.name if plan else "未知计划",
        "status": record.status,
        "trigger_type": record.trigger_type,
        "total_cases": record.total_cases,
        "success_cases": record.success_cases,
        "failed_cases": record.failed_cases,
        "skipped_cases": 0,
        "error_cases": 0,
        "start_time": record.start_time,
        "end_time": record.end_time,
        "duration": record.duration or 0,
        "http_duration": sum_plan_item_results_http_ms(normalized_items) or None,
        "env_name": record.env_name,
        "run_by": record.run_by
    }
    html_content = generate_api_html_report(plan_record, all_case_results, plan_items=normalized_items, report_type="plan")
    filename = f"api_plan_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/plan-records/{record_id}/send-report", summary="发送计划测试报告邮件")
async def send_plan_report(record_id: int):
    """手动发送计划测试报告邮件"""
    record = await ApiPlanRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    try:
        await NotificationService.send_api_report(
            project_id=record.project_id,
            record_id=record_id,
            record_type="plan",
        )
        return {"detail": "报告邮件已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")
