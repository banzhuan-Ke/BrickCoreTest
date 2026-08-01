"""项目级默认资料引用解析"""
from __future__ import annotations

from typing import Any, Optional

from app.models.knowledge import AiKnowledgeFolder
from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

SCENE_SETTING_KEYS: dict[str, str] = {
    "case_generate": "default_knowledge_enable_case_generate",
    "test_points": "default_knowledge_enable_test_points",
    "test_scheme": "default_knowledge_enable_test_scheme",
    "failure_analysis": "default_knowledge_enable_failure_analysis",
}


async def resolve_knowledge_refs_for_scene(
    project_id: int,
    scene: str,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> tuple[Optional[list[int]], Optional[list[int]]]:
    """
    用户显式传入 folder/document 时原样返回；
    均为空时按项目配置自动选取最近迭代文件夹。
    """
    if folder_ids or document_ids:
        return folder_ids, document_ids

    settings = await load_knowledge_project_settings(project_id)
    if not settings.get("default_knowledge_refs_enabled"):
        return None, None

    scene_key = SCENE_SETTING_KEYS.get(scene)
    if scene_key and not settings.get(scene_key, True):
        return None, None

    explicit = settings.get("default_knowledge_folder_ids") or []
    if isinstance(explicit, list) and explicit:
        ids = []
        for x in explicit:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if n > 0:
                ids.append(n)
        if ids:
            return ids, None

    try:
        n = int(settings.get("default_knowledge_auto_folders") or 2)
    except (TypeError, ValueError):
        n = 2
    n = max(1, min(n, 10))

    rows = await AiKnowledgeFolder.filter(project_id=project_id, is_del=False).order_by("-id").limit(n)
    auto_ids = [f.id for f in rows]
    return (auto_ids, None) if auto_ids else (None, None)


def knowledge_refs_settings_fields() -> list[dict[str, Any]]:
    return [
        {
            "key": "default_knowledge_refs_enabled",
            "label": "默认引用资料库",
            "type": "bool",
            "group": "refs",
            "recommended": "按需开启",
            "description": "生成用例/测试点/方案或失败分析未手动选资料时，自动引用项目默认迭代文件夹。",
            "tip": "仍可在各弹窗中手动勾选或清空资料。",
        },
        {
            "key": "default_knowledge_auto_folders",
            "label": "自动引用最近迭代数",
            "type": "int",
            "group": "refs",
            "min": 1,
            "max": 10,
            "step": 1,
            "recommended": "2",
            "description": "未指定文件夹 ID 时，取最近 N 个迭代文件夹。",
            "tip": "与「指定默认文件夹」二选一；指定 ID 优先。",
        },
        {
            "key": "default_knowledge_folder_ids",
            "label": "指定默认文件夹",
            "type": "folder_ids",
            "group": "refs",
            "recommended": "留空则按最近迭代数",
            "description": "固定引用若干迭代文件夹；填写后优先于「最近迭代数」。",
        },
        {
            "key": "default_knowledge_enable_case_generate",
            "label": "用例生成默认引用",
            "type": "bool",
            "group": "refs",
            "recommended": "开启",
            "description": "需求测试中心生成用例时应用默认资料引用。",
        },
        {
            "key": "default_knowledge_enable_test_points",
            "label": "测试点生成默认引用",
            "type": "bool",
            "group": "refs",
            "recommended": "开启",
            "description": "生成测试点时应用默认资料引用。",
        },
        {
            "key": "default_knowledge_enable_test_scheme",
            "label": "测试方案生成默认引用",
            "type": "bool",
            "group": "refs",
            "recommended": "开启",
            "description": "生成测试方案时应用默认资料引用。",
        },
        {
            "key": "default_knowledge_enable_failure_analysis",
            "label": "失败分析默认引用",
            "type": "bool",
            "group": "refs",
            "recommended": "开启",
            "description": "AI 失败分析未选手动资料时自动检索资料库。",
        },
    ]
