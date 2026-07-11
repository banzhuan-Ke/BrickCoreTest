"""App 元素库 locator_ref 引用扫描"""

from __future__ import annotations



from typing import Any



from app.modules.app.app_locator_service import _collect_locator_refs

from app.models.app import AppCase, AppElement, AppStepFragment, AppSuite





async def collect_element_references(project_id: int, element_name: str) -> dict[str, Any]:

    name = (element_name or "").strip()

    if not name:

        return {

            "case_count": 0,

            "suite_count": 0,

            "fragment_count": 0,

            "total": 0,

            "cases": [],

            "suites": [],

            "fragments": [],

        }



    cases: list[dict[str, Any]] = []

    suites: list[dict[str, Any]] = []

    fragments: list[dict[str, Any]] = []



    async for case in AppCase.filter(project_id=project_id, is_del=False):

        refs: set[str] = set()

        _collect_locator_refs(case.steps or [], refs)

        if name in refs:

            cases.append({"id": case.id, "name": case.name})



    async for suite in AppSuite.filter(project_id=project_id, is_del=False):

        refs: set[str] = set()

        _collect_locator_refs(suite.pre_actions or [], refs)

        if name in refs:

            suites.append({"id": suite.id, "name": suite.name, "location": "pre_actions"})



    async for fragment in AppStepFragment.filter(project_id=project_id, is_del=False):

        refs: set[str] = set()

        _collect_locator_refs(fragment.steps or [], refs)

        if name in refs:

            fragments.append({"id": fragment.id, "name": fragment.name})



    total = len(cases) + len(suites) + len(fragments)

    return {

        "case_count": len(cases),

        "suite_count": len(suites),

        "fragment_count": len(fragments),

        "total": total,

        "cases": cases[:50],

        "suites": suites[:50],

        "fragments": fragments[:50],

    }





async def ensure_element_deletable(row: AppElement) -> None:

    from fastapi import HTTPException



    refs = await collect_element_references(row.project_id, row.name)

    if refs["total"] > 0:

        sample = (refs["cases"][:2] + refs["suites"][:1] + refs["fragments"][:1])[:3]

        names = "、".join(item["name"] for item in sample if item.get("name"))

        extra = f" 等 {refs['total']} 处" if refs["total"] > len(sample) else ""

        raise HTTPException(

            status_code=422,

            detail=f"元素「{row.name}」仍被 {refs['total']} 处引用（用例/套件/片段步骤 locator_ref），请先移除引用再删除。例如：{names}{extra}",

        )

