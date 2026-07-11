"""交互调试：编辑器步骤下标与会话（展开后）步骤下标的映射。"""
from __future__ import annotations

from typing import Iterable

from app.modules.ui.ui_step_expand import FRAGMENT_REF_METHOD, expand_fragment_refs


async def build_editor_to_session_index_map(
    editor_steps: list,
    project_id: int,
) -> dict[int, tuple[int, int]]:
    """
    返回 editor_index -> (session_from, session_through) 映射。
    会话步骤为 expand_fragment_refs 后的列表，与 UiDebugSession.steps 一致。
    """
    editor_map: dict[int, tuple[int, int]] = {}
    session_idx = 0
    for editor_idx, step in enumerate(editor_steps or []):
        if not isinstance(step, dict):
            continue
        method = step.get("method")
        if method == FRAGMENT_REF_METHOD:
            expanded = await expand_fragment_refs([step], project_id)
            count = len(expanded)
            if count <= 0:
                editor_map[editor_idx] = (session_idx, session_idx)
                session_idx += 1
            else:
                editor_map[editor_idx] = (session_idx, session_idx + count - 1)
                session_idx += count
            continue
        editor_map[editor_idx] = (session_idx, session_idx)
        session_idx += 1
    return editor_map


def _group_contiguous(indices: Iterable[int]) -> list[tuple[int, int]]:
    sorted_indices = sorted(set(indices))
    if not sorted_indices:
        return []
    segments: list[tuple[int, int]] = []
    start = end = sorted_indices[0]
    for idx in sorted_indices[1:]:
        if idx == end + 1:
            end = idx
        else:
            segments.append((start, end))
            start = end = idx
    segments.append((start, end))
    return segments


async def resolve_editor_indices_to_run_segments(
    editor_steps: list,
    editor_indices: list[int],
    project_id: int,
) -> tuple[list[tuple[int, int]], dict[int, tuple[int, int]], list[int]]:
    """
    将编辑器勾选的步骤下标解析为会话侧连续执行区间。

    Returns:
        segments: 会话 steps 上的 [from, through] 区间列表
        editor_map: 全量 editor -> session 映射
        invalid_indices: 无效或越界的 editor 下标
    """
    editor_map = await build_editor_to_session_index_map(editor_steps, project_id)
    max_editor = len(editor_steps or []) - 1
    session_indices: list[int] = []
    invalid: list[int] = []

    for raw in editor_indices or []:
        try:
            editor_idx = int(raw)
        except (TypeError, ValueError):
            invalid.append(raw)
            continue
        if editor_idx < 0 or editor_idx > max_editor:
            invalid.append(editor_idx)
            continue
        if editor_idx not in editor_map:
            invalid.append(editor_idx)
            continue
        session_from, session_through = editor_map[editor_idx]
        session_indices.extend(range(session_from, session_through + 1))

    segments = _group_contiguous(session_indices)
    return segments, editor_map, invalid


def map_session_step_results_to_editor(
    step_results: list[dict],
    editor_map: dict[int, tuple[int, int]],
) -> list[dict]:
    """将会话侧 step_index 映射回编辑器步骤下标，供前端步骤卡片展示。"""
    if not step_results or not editor_map:
        return step_results

    session_to_editor: dict[int, int] = {}
    for editor_idx, (session_from, session_through) in editor_map.items():
        for session_idx in range(session_from, session_through + 1):
            session_to_editor[session_idx] = editor_idx

    mapped: list[dict] = []
    for item in step_results:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        session_idx = int(row.get("step_index", -1))
        editor_idx = session_to_editor.get(session_idx, session_idx)
        row["session_step_index"] = session_idx
        row["step_index"] = editor_idx
        mapped.append(row)
    return mapped
