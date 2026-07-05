"""App 步骤片段引用扫描"""
from __future__ import annotations

from typing import Any

from app.core.app_step_expand import FRAGMENT_REF_METHOD
from app.models.app import AppCase, AppSuite


def steps_contain_fragment(steps: list | None, fragment_id: int) -> bool:
    if not steps:
        return False
    target = int(fragment_id)
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("method") == FRAGMENT_REF_METHOD:
            params = step.get("params") or {}
            fid = params.get("fragment_id")
            if fid is not None and int(fid) == target:
                return True
        branches = step.get("branches") or (step.get("params") or {}).get("branches")
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict) and steps_contain_fragment(branch.get("steps"), target):
                    return True
    return False


async def collect_fragment_references(project_id: int, fragment_id: int) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    suites: list[dict[str, Any]] = []

    async for case in AppCase.filter(project_id=project_id, is_del=False):
        if steps_contain_fragment(case.steps, fragment_id):
            cases.append({"id": case.id, "name": case.name})

    async for suite in AppSuite.filter(project_id=project_id, is_del=False):
        if steps_contain_fragment(suite.pre_actions, fragment_id):
            suites.append({"id": suite.id, "name": suite.name, "location": "pre_actions"})

    return {
        "case_count": len(cases),
        "suite_count": len(suites),
        "total": len(cases) + len(suites),
        "cases": cases[:50],
        "suites": suites[:50],
    }
