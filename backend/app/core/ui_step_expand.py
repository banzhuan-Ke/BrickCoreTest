"""UI 步骤片段引用展开"""
from __future__ import annotations

import copy
import re
from typing import Any

from app.models.ui import UiStepFragment

FRAGMENT_REF_METHOD = "fragment_ref"
MAX_FRAGMENT_DEPTH = 10
_FRAGMENT_VAR_PATTERN = re.compile(r"\$\{\{fragment\.([^}]+)\}\}")


class FragmentExpandError(ValueError):
    pass


def _apply_fragment_variables(steps: list, variables: dict[str, Any]) -> list:
    """将片段内 ${{fragment.xxx}} 替换为引用时传入的变量值。"""
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


def _clone_steps_with_provenance(
    steps: list,
    fragment: UiStepFragment,
    ref_step_id: str | None,
) -> list:
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


async def _expand_single_ref(
    ref_step: dict,
    project_id: int,
    depth: int,
) -> list:
    params = ref_step.get("params") or {}
    fragment_id = params.get("fragment_id")
    if not fragment_id:
        raise FragmentExpandError("片段引用缺少 fragment_id")

    fragment = await UiStepFragment.get_or_none(
        id=int(fragment_id),
        project_id=project_id,
        is_del=False,
    )
    if not fragment:
        name = params.get("fragment_name") or fragment_id
        raise FragmentExpandError(f"片段不存在或已删除: {name}")

    variables = params.get("variables") or params.get("overrides") or {}
    frag_steps = _apply_fragment_variables(fragment.steps or [], variables)
    frag_steps = _clone_steps_with_provenance(frag_steps, fragment, ref_step.get("id"))
    return await expand_fragment_refs(frag_steps, project_id, depth + 1)


async def expand_fragment_refs(
    steps: list | None,
    project_id: int,
    depth: int = 0,
) -> list:
    """
    递归展开 fragment_ref 节点；condition_branch 内嵌步骤同样处理。
    Runner 不应收到 fragment_ref，仅接收展开后的可执行步骤。
    """
    if depth > MAX_FRAGMENT_DEPTH:
        raise FragmentExpandError("片段引用嵌套层级过深（超过 10 层）")
    if not steps:
        return []

    result: list = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        method = step.get("method")
        if method == FRAGMENT_REF_METHOD:
            expanded = await _expand_single_ref(step, project_id, depth)
            result.extend(expanded)
            continue
        if method == "condition_branch":
            new_step = copy.deepcopy(step)
            new_branches = []
            for branch in new_step.get("branches") or []:
                if not isinstance(branch, dict):
                    continue
                new_branch = copy.deepcopy(branch)
                new_branch["steps"] = await expand_fragment_refs(
                    branch.get("steps") or [],
                    project_id,
                    depth,
                )
                new_branches.append(new_branch)
            new_step["branches"] = new_branches
            result.append(new_step)
            continue
        result.append(copy.deepcopy(step))
    return result
