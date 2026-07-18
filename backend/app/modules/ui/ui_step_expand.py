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


def _parse_fragment_id(raw: Any, *, step_label: str = "") -> int:
    prefix = f"{step_label}：" if step_label else ""
    try:
        fragment_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise FragmentExpandError(f"{prefix}片段引用 fragment_id 无效: {raw!r}") from exc
    if fragment_id <= 0:
        raise FragmentExpandError(f"{prefix}片段引用 fragment_id 必须为正整数")
    return fragment_id


async def _expand_single_ref(
    ref_step: dict,
    project_id: int,
    depth: int,
    ref_stack: list[int] | None = None,
) -> list:
    params = ref_step.get("params") or {}
    if not isinstance(params, dict):
        raise FragmentExpandError("片段引用 params 必须是对象")
    fragment_id = params.get("fragment_id")
    if fragment_id is None or fragment_id == "":
        raise FragmentExpandError("片段引用缺少 fragment_id")

    fragment_id = _parse_fragment_id(fragment_id, step_label=ref_step.get("desc") or ref_step.get("id") or "")
    stack = list(ref_stack or [])
    if fragment_id in stack:
        chain = " -> ".join(str(i) for i in stack + [fragment_id])
        raise FragmentExpandError(f"片段引用存在循环: {chain}")

    fragment = await UiStepFragment.get_or_none(
        id=fragment_id,
        project_id=project_id,
        is_del=False,
    )
    if not fragment:
        name = params.get("fragment_name") or fragment_id
        raise FragmentExpandError(f"片段不存在或已删除: {name}")

    variables = params.get("variables") or params.get("overrides") or {}
    if variables is not None and not isinstance(variables, dict):
        raise FragmentExpandError("片段引用 variables/overrides 必须是对象")

    frag_steps = _apply_fragment_variables(fragment.steps or [], variables)
    frag_steps = _clone_steps_with_provenance(frag_steps, fragment, ref_step.get("id"))
    return await expand_fragment_refs(
        frag_steps,
        project_id,
        depth + 1,
        ref_stack=stack + [fragment_id],
    )


async def expand_fragment_refs(
    steps: list | None,
    project_id: int,
    depth: int = 0,
    ref_stack: list[int] | None = None,
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
    for idx, step in enumerate(steps):
        step_no = idx + 1
        if not isinstance(step, dict):
            raise FragmentExpandError(f"步骤 #{step_no} 必须是对象")
        method = step.get("method")
        if method == FRAGMENT_REF_METHOD:
            expanded = await _expand_single_ref(step, project_id, depth, ref_stack=ref_stack)
            result.extend(expanded)
            continue
        if method == "condition_branch":
            new_step = copy.deepcopy(step)
            new_branches = []
            branches = new_step.get("branches") or []
            if not isinstance(branches, list):
                raise FragmentExpandError(f"步骤 #{step_no} condition_branch.branches 必须是数组")
            for branch_idx, branch in enumerate(branches):
                if not isinstance(branch, dict):
                    raise FragmentExpandError(
                        f"步骤 #{step_no} condition_branch 第 {branch_idx + 1} 个分支必须是对象"
                    )
                new_branch = copy.deepcopy(branch)
                new_branch["steps"] = await expand_fragment_refs(
                    branch.get("steps") or [],
                    project_id,
                    depth,
                    ref_stack=ref_stack,
                )
                new_branches.append(new_branch)
            new_step["branches"] = new_branches
            result.append(new_step)
            continue
        result.append(copy.deepcopy(step))
    return result
