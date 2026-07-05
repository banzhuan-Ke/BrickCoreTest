"""App 步骤片段引用展开"""
from __future__ import annotations

import copy
import re
from typing import Any

from app.models.app import AppStepFragment

FRAGMENT_REF_METHOD = "fragment_ref"
MAX_FRAGMENT_DEPTH = 10
_FRAGMENT_VAR_PATTERN = re.compile(r"\$\{\{fragment\.([^}]+)\}\}")


class FragmentExpandError(ValueError):
    pass


def _apply_fragment_variables(steps: list, variables: dict[str, Any]) -> list:
    if not variables:
        return steps

    def _replace_in_obj(obj: Any) -> Any:
        if isinstance(obj, str):
            result = obj
            for key, val in variables.items():
                result = result.replace(f"${{fragment.{key}}}", str(val))
            result = _FRAGMENT_VAR_PATTERN.sub(
                lambda m: str(variables.get(m.group(1), m.group(0))),
                result,
            )
            return result
        if isinstance(obj, list):
            return [_replace_in_obj(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _replace_in_obj(v) for k, v in obj.items()}
        return obj

    return _replace_in_obj(steps)


def _clone_steps_with_provenance(steps: list, fragment: AppStepFragment, ref_step_id: str | None) -> list:
    cloned = copy.deepcopy(steps or [])
    meta = {
        "id": fragment.id,
        "name": fragment.name,
        "version": fragment.version,
        "ref_step_id": ref_step_id,
    }
    for step in cloned:
        step["_from_fragment"] = meta
    return cloned


async def _expand_single_ref(ref_step: dict, project_id: int, depth: int) -> list:
    params = ref_step.get("params") or {}
    fragment_id = params.get("fragment_id")
    if not fragment_id:
        raise FragmentExpandError("片段引用缺少 fragment_id")

    fragment = await AppStepFragment.get_or_none(
        id=int(fragment_id),
        project_id=project_id,
        is_del=False,
    )
    if not fragment:
        name = params.get("fragment_name") or fragment_id
        raise FragmentExpandError(f"片段不存在或已删除: {name}")

    variables = params.get("variables") or params.get("overrides") or {}
    frag_steps = _apply_fragment_variables(fragment.steps or [], variables)
    cloned = _clone_steps_with_provenance(frag_steps, fragment, ref_step.get("id"))
    return await expand_fragment_refs(cloned, project_id, depth + 1)


async def expand_fragment_refs(steps: list, project_id: int, depth: int = 0) -> list:
    if depth > MAX_FRAGMENT_DEPTH:
        raise FragmentExpandError("片段嵌套层级过深")
    result: list = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        if (step.get("method") or "").strip() == FRAGMENT_REF_METHOD:
            result.extend(await _expand_single_ref(step, project_id, depth))
            continue
        item = copy.deepcopy(step)
        branches = item.get("branches") or (item.get("params") or {}).get("branches")
        if isinstance(branches, list):
            new_branches = []
            for branch in branches:
                if not isinstance(branch, dict):
                    new_branches.append(branch)
                    continue
                b = copy.deepcopy(branch)
                b["steps"] = await expand_fragment_refs(b.get("steps") or [], project_id, depth)
                new_branches.append(b)
            if item.get("branches") is not None:
                item["branches"] = new_branches
            elif isinstance(item.get("params"), dict):
                item["params"]["branches"] = new_branches
        result.append(item)
    return result
