from typing import List
from fastapi import APIRouter, HTTPException, Depends, status, Query
from app.models.sys import Project, TestCatalog
from app.core.auth import is_authenticated, require_permissions, get_current_username
from app.core.permissions import UI_SUITE_VIEW, UI_SUITE_EDIT
from app.core.catalog_utils import apply_catalog_filter, resolve_catalog
from app.schemas.ui import AddSuiteForm, SuiteSchemas, UpdateSuiteForm, AddStepForm, StepSchemas, StepListSchemas, UpdateSuiteCaseSortForm
from app.core.ui_execution_stale import cleanup_stale_ui_executions
from app.models.ui import Suite, Step, Case, UiCaseExecution, UiSuiteExecution

# 创建路由对象
router = APIRouter(prefix="/suites", dependencies=[Depends(is_authenticated)])


async def _touch_suite_updated(suite: Suite, username: str) -> None:
    suite.update_by = username
    await suite.save(update_fields=["update_by", "update_time"])


# 创建测试套件
@router.post("", tags=["测试套件"], summary="创建套件", status_code=status.HTTP_201_CREATED,
             response_model=SuiteSchemas,
             dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def create_suite(item: AddSuiteForm):
    """创建测试套件的接口"""
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在或已被删除")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    suite = await Suite.create(**item.model_dump(exclude_unset=True), is_del=False, update_by=item.username)
    return suite


# 查询测试套件列表
@router.get("", tags=["测试套件"], summary="套件列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_SUITE_VIEW))])
async def get_suite(project: int | None = None, project_id: int | None = None,
                    catalog_id: int | None = None, modules: int | None = None,
                    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
                    page: int = 1, size: int = 10, name: str | None = None, suite_type: str | None = None,
                    status: str | None = None):
    """查询测试套件列表的接口"""
    await cleanup_stale_ui_executions()
    query = Suite.filter(is_del=False).order_by("-id")
    actual_project = project_id or project
    if actual_project:
        project_obj = await Project.get_or_none(id=actual_project, is_del=False)
        if not project_obj:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在或已被删除")
        query = query.filter(project=project_obj)
    filter_catalog_id = catalog_id if catalog_id is not None else modules
    if filter_catalog_id is not None:
        if actual_project:
            await resolve_catalog(actual_project, filter_catalog_id)
        query = await apply_catalog_filter(
            query, actual_project, filter_catalog_id, include_children=include_children
        )
    if name:
        query = query.filter(name__icontains=name)
    if suite_type:
        query = query.filter(suite_type=suite_type)
    all_suites = await query.prefetch_related("steps").all()
    result = []
    for suite in all_suites:
        catalog = await suite.catalog
        run_record = await UiSuiteExecution.filter(suite=suite.id, is_del=False).order_by("-id").first()
        latest_status = run_record.status if run_record else '等待执行'
        if status and latest_status != status:
            continue
        cases = await suite.steps.filter(is_del=False).all()
        result.append({
            "create_time": suite.create_time,
            "update_time": suite.update_time,
            "id": suite.id,
            "name": suite.name,
            "username": suite.username,
            "update_by": suite.update_by or suite.username,
            "status": latest_status,
            "suite_type": suite.suite_type,
            "case_count": len(cases),
            "suite_step_count": len(suite.pre_actions),
            "catalog": catalog.name if catalog else "",
            "catalog_id": suite.catalog_id,
            "module": catalog.name if catalog else "",
            "run_count": await UiSuiteExecution.filter(suite=suite.id, is_del=False).count(),
            "is_del": suite.is_del
        })
    total = len(result)
    data = result[(page - 1) * size: page * size]
    return {"data": data, "total": total}


# 获取单个套件详情
@router.get("/{suite_id}", tags=["测试套件"], summary="套件详情", response_model=SuiteSchemas,
            status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_SUITE_VIEW))])
async def get_suite_detail(suite_id: int):
    """获取单个套件详情的接口"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="套件不存在或已被删除")
    return suite


# 删除套件信息（逻辑删除）
@router.delete("/{suite_id}", tags=["测试套件"], summary="删除套件", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def delete_suite(suite_id: int):
    """删除套件信息的接口"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="套件不存在或已被删除")
    suite.is_del = True
    await suite.save()


# 更新套件信息
@router.put("/{suite_id}", tags=["测试套件"], summary="更新套件", response_model=SuiteSchemas,
            status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def update_suite(
    suite_id: int,
    item: UpdateSuiteForm,
    username: str = Depends(get_current_username),
):
    """更新套件信息的接口"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="套件不存在或已被删除")
    if item.catalog_id is not None:
        await resolve_catalog(suite.project_id, item.catalog_id)
    await suite.update_from_dict(item.model_dump(exclude_unset=True))
    suite.update_by = username
    await suite.save()
    return suite


# 往套件中添加用例
@router.post("/{suite_id}/cases", tags=["套件用例"], summary="套件中添加用例", status_code=status.HTTP_201_CREATED,
             response_model=StepSchemas,
             dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def add_step(
    suite_id: int,
    item: AddStepForm,
    username: str = Depends(get_current_username),
):
    """往套件中添加用例的接口"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的套件不存在或已被删除")
    case_ = await Case.get_or_none(id=item.cases_id, is_del=False)
    if not case_:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的用例不存在或已被删除")
    if case_.project_id != suite.project_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能添加同一项目下的用例到套件中")
    default_run_mode = "chain" if suite.suite_type == "2" else "standalone"
    step = await Step.create(
        suite=suite,
        cases=case_,
        sort=item.sort,
        run_mode=default_run_mode,
        is_del=False,
    )
    await _touch_suite_updated(suite, username)
    return step


# 删除套件中的用例（逻辑删除）
@router.delete("/{suite_id}/cases/{case_id}", tags=["套件用例"], summary="删除套件中的用例",
               status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def delete_step(
    case_id: int,
    suite_id: int,
    username: str = Depends(get_current_username),
):
    """删除套件中的用例的接口"""
    step = await Step.get_or_none(id=case_id, suite_id=suite_id, is_del=False)
    if not step:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的套件用例不存在或已被删除")
    step.is_del = True
    await step.save()
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if suite:
        await _touch_suite_updated(suite, username)


# 获取套件中的所有用例（只返回未删除的）
@router.get("/{suite_id}/cases", tags=["套件用例"], summary="获取套件中的用例", status_code=status.HTTP_200_OK,
            response_model=list[StepListSchemas],
            dependencies=[Depends(require_permissions(UI_SUITE_VIEW))])
async def get_step(suite_id: int):
    """获取套件中的所有用例的接口"""
    step = await Step.filter(suite_id=suite_id, is_del=False).prefetch_related("cases", 'suite').order_by('sort')
    result = []
    for i in step:
        item = {
            "id": i.id,
            "skip": i.skip,
            "sort": i.sort,
            "run_mode": i.run_mode or "standalone",
            "cases_id": i.cases.id,
            "suite_id": i.suite.id,
            "cases_name": i.cases.name,
            "suite_name": i.suite.name,
            "is_del": i.is_del
        }
        result.append(item)
    return result


# 套件中修改用例跳过执行
@router.put("/{suite_id}/cases/{case_id}", tags=["套件用例"], summary="修改是否跳过执行",
            status_code=status.HTTP_200_OK,
            response_model=StepSchemas,
            dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def update_step(
    case_id: int,
    suite_id: int,
    username: str = Depends(get_current_username),
):
    """套件中修改用例跳过执行"""
    step = await Step.get_or_none(id=case_id, suite_id=suite_id, is_del=False)
    if not step:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的套件用例不存在或已被删除")
    step.skip = not step.skip
    await step.save()
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if suite:
        await _touch_suite_updated(suite, username)
    return step


# 覆盖式更新套件中的所有用例
@router.put("/{suite_id}/cases", tags=["套件用例"], summary="覆盖式更新套件用例", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def update_suite_cases(
    suite_id: int,
    data: dict,
    username: str = Depends(get_current_username),
):
    """覆盖式更新套件中的用例列表"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的套件不存在或已被删除")
    case_ids = data.get("case_ids", [])
    default_run_mode = "chain" if suite.suite_type == "2" else "standalone"
    old_steps = {
        step.cases_id: (step.run_mode or default_run_mode)
        for step in await Step.filter(suite_id=suite_id, is_del=False).all()
    }
    await Step.filter(suite_id=suite_id, is_del=False).update(is_del=True)
    for idx, case_id in enumerate(case_ids):
        case_ = await Case.get_or_none(id=case_id, is_del=False)
        if case_ and case_.project_id == suite.project_id:
            await Step.create(
                suite=suite,
                cases=case_,
                sort=idx,
                is_del=False,
                run_mode=old_steps.get(case_id, default_run_mode),
            )
    await _touch_suite_updated(suite, username)
    return await get_step(suite_id)


# 批量复制用例到当前套件
@router.post("/{suite_id}/cases/copy", tags=["套件用例"], summary="批量复制用例到套件", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def batch_copy_cases(suite_id: int, data: dict):
    """批量复制用例到当前套件"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="操作的套件不存在或已被删除")
    source_suite_id = data.get("source_suite_id")
    case_ids = data.get("case_ids", [])
    if source_suite_id:
        source_suite = await Suite.get_or_none(id=source_suite_id, is_del=False)
        if not source_suite or source_suite.project_id != suite.project_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="源套件不存在或项目不匹配")
        steps = await Step.filter(suite_id=source_suite_id, cases_id__in=case_ids, is_del=False).order_by('sort')
    else:
        steps = []
    created = []
    start_sort = await Step.filter(suite_id=suite_id, is_del=False).count()
    for idx, step in enumerate(steps):
        new_step = await Step.create(
            suite=suite,
            cases=step.cases,
            sort=start_sort + idx,
            run_mode=step.run_mode or "standalone",
            is_del=False,
        )
        created.append(new_step)
    return created


# 修改用例执行的顺序
@router.post("/{suite_id}/cases/sort", tags=["套件用例"], summary="修改用例执行的顺序",
             status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_SUITE_EDIT))])
async def update_sort(
    suite_id: int,
    item: UpdateSuiteCaseSortForm,
    username: str = Depends(get_current_username),
):
    """修改用例执行的顺序"""
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    for i in item.case_orders:
        step = await Step.get_or_none(suite_id=suite_id, cases_id=i.cases_id, is_del=False)
        if step:
            step.sort = i.sort
            if i.skip is not None:
                step.skip = i.skip
            if i.run_mode is not None:
                run_mode = (i.run_mode or "standalone").strip().lower()
                if run_mode not in ("chain", "standalone"):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"无效的运行模式: {i.run_mode}",
                    )
                step.run_mode = run_mode
            await step.save()
    if suite:
        await _touch_suite_updated(suite, username)
    return await Step.filter(suite_id=suite_id, is_del=False).order_by('sort')
