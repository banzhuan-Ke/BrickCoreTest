"""项目内全局搜索"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_username
from app.models.http import ApiDefinition, ApiTestCase, ApiTestPlan, ApiTestSuite
from app.models.app import AppCase, AppElement, AppPlan, AppSuite
from app.models.sys import Project
from app.models.ui import Case, Suite, Task
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/search", tags=["全局搜索"])


def _match(keyword: str, *texts: Optional[str]) -> bool:
    kw = keyword.lower()
    return any(kw in (t or "").lower() for t in texts if t)


def _match_fields(keyword: str, row, *field_names: str) -> bool:
    """按模型字段名匹配，缺失字段自动跳过（避免 Suite/Task 等无 description 报错）"""
    texts = [getattr(row, name, None) for name in field_names]
    return _match(keyword, *texts)


@router.get("", summary="项目内全局搜索")
async def project_search(
    project_id: int = Query(...),
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=30),
    username: str = Depends(get_current_username),
):
    if not await Project.get_or_none(id=project_id, is_del=False):
        raise HTTPException(status_code=404, detail="项目不存在")

    keyword = q.strip()
    if not keyword:
        return StandardResponse(data={"groups": [], "total": 0})

    groups: list[dict[str, Any]] = []
    total = 0

    async def add_group(key: str, label: str, route: str, items: list[dict]):
        nonlocal total
        if not items:
            return
        total += len(items)
        groups.append({"key": key, "label": label, "route": route, "items": items})

    ui_cases = []
    async for row in Case.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "description"):
            ui_cases.append({"id": row.id, "name": row.name, "subtitle": row.level or ""})
        if len(ui_cases) >= limit:
            break
    await add_group("ui_case", "Web 用例", "/case", ui_cases)

    ui_suites = []
    async for row in Suite.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name"):
            ui_suites.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(ui_suites) >= limit:
            break
    await add_group("ui_suite", "Web 套件", "/suite", ui_suites)

    ui_tasks = []
    async for row in Task.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name"):
            ui_tasks.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(ui_tasks) >= limit:
            break
    await add_group("ui_task", "Web 计划", "/task", ui_tasks)

    apis = []
    async for row in ApiDefinition.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "path", "description"):
            apis.append({"id": row.id, "name": row.name, "subtitle": f"{row.method} {row.path}"})
        if len(apis) >= limit:
            break
    await add_group("api", "接口", "/api-module", apis)

    api_cases = []
    async for row in ApiTestCase.filter(project_id=project_id, is_del=False).prefetch_related("api").order_by("-id").limit(200):
        api = await row.api
        if _match(keyword, row.name, api.name if api else "", api.path if api else ""):
            api_cases.append({
                "id": row.id,
                "name": row.name,
                "subtitle": api.name if api else "",
                "api_id": row.api_id,
            })
        if len(api_cases) >= limit:
            break
    await add_group("api_case", "接口用例", "/api-case", api_cases)

    api_suites = []
    async for row in ApiTestSuite.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "description"):
            api_suites.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(api_suites) >= limit:
            break
    await add_group("api_suite", "接口套件", "/api-suite", api_suites)

    api_plans = []
    async for row in ApiTestPlan.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "description"):
            api_plans.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(api_plans) >= limit:
            break
    await add_group("api_plan", "接口计划", "/api-plan", api_plans)

    app_cases = []
    async for row in AppCase.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "description"):
            app_cases.append({"id": row.id, "name": row.name, "subtitle": row.driver_mode or ""})
        if len(app_cases) >= limit:
            break
    await add_group("app_case", "App 用例", "/app-case", app_cases)

    app_suites = []
    async for row in AppSuite.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name"):
            app_suites.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(app_suites) >= limit:
            break
    await add_group("app_suite", "App 套件", "/app-suite", app_suites)

    app_plans = []
    async for row in AppPlan.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name"):
            app_plans.append({"id": row.id, "name": row.name, "subtitle": ""})
        if len(app_plans) >= limit:
            break
    await add_group("app_plan", "App 计划", "/app-plan", app_plans)

    app_elements = []
    async for row in AppElement.filter(project_id=project_id, is_del=False).order_by("-id").limit(200):
        if _match_fields(keyword, row, "name", "remark", "element_type"):
            app_elements.append({
                "id": row.id,
                "name": row.name,
                "subtitle": row.element_type or "",
            })
        if len(app_elements) >= limit:
            break
    await add_group("app_element", "App 元素", "/app-elements", app_elements)

    return StandardResponse(data={"groups": groups, "total": total, "keyword": keyword})
