from typing import List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from app.models.sys import Project
from app.models.ui import UiPlanExecution
from app.models.ui import Suite
from app.core.catalog_utils import apply_catalog_filter, resolve_catalog
from app.schemas.ui import AddTaskForm, TaskSchemas, UpdateTaskForm, AddSuiteToTaskForm, TaskDetailSchemas
from app.models.ui import Task
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import UI_TASK_VIEW, UI_TASK_EDIT

router = APIRouter(prefix="/tasks", tags=['测试计划'], dependencies=[Depends(is_authenticated)])


class UpdateTaskSuitesForm(BaseModel):
    """更新任务中的套件列表"""
    suite_ids: List[int] = Field(default=[], description="套件ID列表")


# 创建测试计划
@router.post("", summary="创建任务", response_model=TaskSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def create_task(item: AddTaskForm):
    # 检查项目是否存在且未删除
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的项目ID不存在或已被删除")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    task = await Task.create(**item.model_dump(), is_del=False)
    return task


# 获取测试计划列表
@router.get("", summary="任务列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_TASK_VIEW))])
async def get_task(project_id: int, page: int = 1, size: int = 10,
                   name: str | None = None, status: str | None = None,
                   catalog_id: int | None = None, include_children: bool = True):
    # 检查项目是否存在且未删除
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的项目ID不存在或已被删除")
    # 查询未删除的任务并预加载套件
    query = Task.filter(project=project_id, is_del=False)
    if name:
        query = query.filter(name__icontains=name)
    if catalog_id is not None:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)
    all_tasks = await query.prefetch_related("suites").order_by("-id").all()
    result = []
    for task in all_tasks:
        # 获取最近一次执行状态（只考虑未删除的记录）
        run_record = await UiPlanExecution.filter(task=task.id, is_del=False).order_by("-id").first()
        state = run_record.status if run_record else '等待执行'
        if status and state != status:
            continue
        # 只统计未删除的关联套件
        valid_suites = [s for s in task.suites if not s.is_del]
        result.append({
            "id": task.id,
            "name": task.name,
            "username": task.username,
            "catalog_id": task.catalog_id,
            "status": state,
            'create_time': task.create_time,
            "update_time": task.update_time,
            "suites_count": len(valid_suites),
            "run_count": await UiPlanExecution.filter(task=task.id, is_del=False).count(),
            "is_del": task.is_del
        })
    total = len(result)
    data = result[(page - 1) * size: page * size]
    return {"total": total, "data": data}


# 删除测试计划（逻辑删除）
@router.delete("/{task_id}", summary="删除任务", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def delete_task(task_id: int):
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的任务ID不存在或已被删除")
    # 逻辑删除：设置is_del=True
    task.is_del = True
    await task.save()


# 修改测试计划名称
@router.put("/{task_id}", summary="修改任务", response_model=TaskSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def update_task(task_id: int, item: UpdateTaskForm):
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的任务ID不存在或已被删除")
    # 更新任务名称
    if item.name is not None:
        task.name = item.name
    if item.catalog_id is not None:
        await resolve_catalog(task.project_id, item.catalog_id)
        task.catalog_id = item.catalog_id
    await task.save()
    return task


# 往任务中添加套件
@router.post("/{task_id}/suites", tags=['测试计划'], summary="任务中添加套件", status_code=status.HTTP_201_CREATED,
             response_model=TaskSchemas,
             dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def add_step(task_id: int, item: AddSuiteToTaskForm):
    # 检查任务是否存在且未删除
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务不存在或已被删除")
    # 检查套件是否存在且未删除
    suite = await Suite.get_or_none(id=item.suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的套件ID不存在或已被删除")
    # 校验套件与任务属于同一项目
    if suite.project_id != task.project_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能添加同一项目下的套件到任务中")
    # 往多对多的关联字段中添加数据
    await task.suites.add(suite)
    return task


# 更新任务中的套件列表（覆盖式）
@router.put("/{task_id}/suites", summary="更新任务中的套件列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def update_task_suites(task_id: int, item: UpdateTaskSuitesForm):
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务不存在或已被删除")
    # 获取当前所有关联套件并清除
    current_suites = await task.suites.all()
    for s in current_suites:
        await task.suites.remove(s)
    # 重新添加指定套件（只添加同项目且未删除的）
    for suite_id in item.suite_ids:
        suite = await Suite.get_or_none(id=suite_id, is_del=False)
        if suite and suite.project_id == task.project_id:
            await task.suites.add(suite)
    return await get_task_detail(task_id)


# 删除任务中的套件
@router.delete("/{task_id}/suites/{suite_id}", summary="删除任务中套件", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_TASK_EDIT))])
async def delete_step(task_id: int, suite_id: int):
    # 检查任务是否存在且未删除
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务不存在或已被删除")
    # 检查套件是否存在（无论是否已删除都允许移除关联）
    suite = await Suite.get_or_none(id=suite_id)
    if not suite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的套件ID不存在")
    # 移除多对多关联
    await task.suites.remove(suite)


# 获取任务中的套件列表
@router.get("/{task_id}/suites", summary="任务中的套件", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_TASK_VIEW))])
async def get_task_suites(task_id: int):
    task = await Task.get_or_none(id=task_id, is_del=False).prefetch_related("suites")
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务不存在或已被删除")
    suite_list = []
    suites = await task.suites.filter(is_del=False).all()
    for su in suites:
        suite_list.append({
            "suite_id": su.id,
            "suite_name": su.name,
            "suite_type": su.suite_type,
            "create_time": su.create_time,
            "update_time": su.update_time,
            "is_del": su.is_del
        })
    return suite_list


# 获取测试计划详情(任务中所有的套件)
@router.get("/{task_id}", summary="任务详情", response_model=TaskDetailSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_TASK_VIEW))])
async def get_task_detail(task_id: int):
    # 获取未删除的任务并预加载套件
    task = await Task.get_or_none(id=task_id, is_del=False).prefetch_related("suites")
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务不存在或已被删除")
    suite_list = []
    # 查询测试计划中未删除的测试套件
    suites = await task.suites.filter(is_del=False).all()
    for su in suites:
        suite_list.append({
            "suite_id": su.id,
            "suite_name": su.name,
            "suite_type": su.suite_type,
            "create_time": su.create_time,
            "update_time": su.update_time,
            "is_del": su.is_del
        })
    # 准备返回的数据
    result = {
        "id": task.id,
        "name": task.name,
        "username": task.username,
        'create_time': task.create_time,
        "update_time": task.update_time,
        "suites": suite_list,
        "is_del": task.is_del  # 新增：返回任务删除状态
    }
    return result
