"""项目内变量引用扫描（接口 / Web / App / SQL / 压测关联）。"""
from __future__ import annotations

from typing import Any

from tortoise.expressions import Q

from app.models.app import AppCase, AppSuite
from app.models.http import (
    ApiDefinition,
    ApiPlanItem,
    ApiSuiteCase,
    ApiTestCase,
    ApiTestPlan,
    ApiTestSuite,
    SqlTemplate,
)
from app.models.perf import PerfScene
from app.models.ui import Case, Suite, Task
from app.modules.sys.variable_refs import value_references_var

_LIMIT = 200


def _hit(name: str, *parts: Any) -> bool:
    return any(value_references_var(p, name) for p in parts)


def _cap(rows: list) -> list:
    return rows[:_LIMIT]


async def collect_variable_usages(project_id: int, name: str) -> dict[str, Any]:
    var_name = (name or "").strip()
    if not var_name:
        raise ValueError("变量名不能为空")

    api_cases: list[dict[str, Any]] = []
    api_defs: list[dict[str, Any]] = []
    ui_cases: list[dict[str, Any]] = []
    ui_suites: list[dict[str, Any]] = []
    app_cases: list[dict[str, Any]] = []
    app_suites: list[dict[str, Any]] = []
    sql_templates: list[dict[str, Any]] = []
    perf_scenes: list[dict[str, Any]] = []
    api_suites: list[dict[str, Any]] = []
    api_plans: list[dict[str, Any]] = []
    ui_plans: list[dict[str, Any]] = []

    async for api in ApiDefinition.filter(project_id=project_id, is_del=False):
        if _hit(var_name, api.path, api.base_url, api.headers, api.params, api.body, api.body_fields, api.ws_config):
            api_defs.append({"id": api.id, "name": api.name})

    async for case in ApiTestCase.filter(project_id=project_id, is_del=False).prefetch_related("api"):
        if _hit(
            var_name,
            case.request_headers,
            case.request_params,
            case.request_body,
            case.request_body_fields,
            case.ws_steps,
            case.assertions,
            case.assertion_groups,
            case.db_assertions,
            case.pre_script,
            case.post_script,
            case.data_set,
        ):
            api_cases.append(
                {
                    "id": case.id,
                    "name": case.name,
                    "api_id": case.api_id,
                    "api_name": getattr(case.api, "name", None),
                }
            )

    hit_api_case_ids = {c["id"] for c in api_cases}

    async for suite in ApiTestSuite.filter(project_id=project_id, is_del=False):
        if _hit(var_name, suite.db_assertions):
            api_suites.append({"id": suite.id, "name": suite.name, "via": "db_assertions"})

    if hit_api_case_ids:
        suite_ids = {s["id"] for s in api_suites}
        async for link in ApiSuiteCase.filter(case_id__in=list(hit_api_case_ids)).prefetch_related("suite"):
            suite = link.suite
            if (
                suite
                and not suite.is_del
                and suite.project_id == project_id
                and suite.id not in suite_ids
            ):
                suite_ids.add(suite.id)
                api_suites.append({"id": suite.id, "name": suite.name, "via": "cases"})

    related_suite_ids = {s["id"] for s in api_suites}
    plan_ids: set[int] = set()
    if hit_api_case_ids or related_suite_ids:
        q = Q()
        if hit_api_case_ids:
            q |= Q(case_id__in=list(hit_api_case_ids))
        if related_suite_ids:
            q |= Q(suite_id__in=list(related_suite_ids))
        async for item in ApiPlanItem.filter(q).prefetch_related("plan"):
            plan = item.plan
            if not plan or plan.is_del or plan.project_id != project_id or plan.id in plan_ids:
                continue
            plan_ids.add(plan.id)
            api_plans.append({"id": plan.id, "name": plan.name, "via": "items"})

    async for plan in ApiTestPlan.filter(project_id=project_id, is_del=False):
        if plan.id in plan_ids:
            continue
        if _hit(var_name, plan.variables):
            plan_ids.add(plan.id)
            api_plans.append({"id": plan.id, "name": plan.name, "via": "variables"})

    async for ui_case in Case.filter(project_id=project_id, is_del=False):
        if _hit(var_name, ui_case.steps):
            ui_cases.append({"id": ui_case.id, "name": ui_case.name})

    async for suite in Suite.filter(project_id=project_id, is_del=False):
        locs = []
        if value_references_var(suite.pre_actions, var_name):
            locs.append("pre_actions")
        if value_references_var(suite.db_assertions, var_name):
            locs.append("db_assertions")
        if locs:
            ui_suites.append({"id": suite.id, "name": suite.name, "via": "|".join(locs)})

    hit_ui_suite_ids = {s["id"] for s in ui_suites}
    if hit_ui_suite_ids:
        async for task in Task.filter(project_id=project_id, is_del=False).prefetch_related("suites"):
            suite_list = await task.suites.all()
            if any(s.id in hit_ui_suite_ids for s in suite_list):
                ui_plans.append({"id": task.id, "name": task.name, "via": "suites"})

    async for app_case in AppCase.filter(project_id=project_id, is_del=False):
        if _hit(var_name, app_case.steps):
            app_cases.append({"id": app_case.id, "name": app_case.name})

    async for app_suite in AppSuite.filter(project_id=project_id, is_del=False):
        locs = []
        if value_references_var(app_suite.pre_actions, var_name):
            locs.append("pre_actions")
        if value_references_var(app_suite.db_assertions, var_name):
            locs.append("db_assertions")
        if locs:
            app_suites.append({"id": app_suite.id, "name": app_suite.name, "via": "|".join(locs)})

    async for tpl in SqlTemplate.filter(project_id=project_id, is_del=False):
        if _hit(var_name, tpl.sql_text):
            sql_templates.append({"id": tpl.id, "name": tpl.name})

    async for scene in PerfScene.filter(project_id=project_id, is_del=False):
        via: list[int] = []
        for item in scene.scene_items or []:
            if not isinstance(item, dict):
                continue
            try:
                cid_int = int(item.get("case_id"))
            except (TypeError, ValueError):
                continue
            if cid_int in hit_api_case_ids:
                via.append(cid_int)
        if via or _hit(var_name, scene.config):
            perf_scenes.append({"id": scene.id, "name": scene.name, "via_case_ids": via[:20]})

    total = (
        len(api_cases)
        + len(api_defs)
        + len(api_suites)
        + len(api_plans)
        + len(ui_cases)
        + len(ui_suites)
        + len(ui_plans)
        + len(app_cases)
        + len(app_suites)
        + len(sql_templates)
        + len(perf_scenes)
    )

    return {
        "name": var_name,
        "total": total,
        "api_definitions": _cap(api_defs),
        "api_cases": _cap(api_cases),
        "api_suites": _cap(api_suites),
        "api_plans": _cap(api_plans),
        "ui_cases": _cap(ui_cases),
        "ui_suites": _cap(ui_suites),
        "ui_plans": _cap(ui_plans),
        "app_cases": _cap(app_cases),
        "app_suites": _cap(app_suites),
        "sql_templates": _cap(sql_templates),
        "perf_scenes": _cap(perf_scenes),
        "limit": _LIMIT,
        "truncated": any(
            len(x) > _LIMIT
            for x in (
                api_cases,
                api_defs,
                api_suites,
                api_plans,
                ui_cases,
                ui_suites,
                ui_plans,
                app_cases,
                app_suites,
                sql_templates,
                perf_scenes,
            )
        ),
    }
