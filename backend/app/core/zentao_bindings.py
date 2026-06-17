"""
禅道导入字段绑定（无禅道 API，项目/需求级手工配置 + 规则引擎）
"""
from typing import Any, Optional

from app.core.export_profile import (
    EXPORT_PROFILE_GENERIC,
    EXPORT_PROFILE_ZENTAO,
    get_export_profile_from_bindings,
    normalize_export_profile,
)
from app.models.sys import Project

# 存在 project.global_vars 中的键
ZENTAO_GLOBAL_VARS_KEY = "zentao_export"

DEFAULT_BINDINGS = {
    "export_profile": EXPORT_PROFILE_ZENTAO,
    "product": "",
    "module": "",
    "related_story": "",
    "default_stage": "系统测试阶段",
    "smoke_stage": "冒烟测试阶段",
    "priority_smoke_values": ["1"],
}

BINDING_FIELD_LABELS = {
    "product": "所属产品",
    "module": "所属模块",
    "related_story": "相关研发需求",
}


def normalize_bindings(raw: Optional[dict]) -> dict:
    base = {**DEFAULT_BINDINGS}
    if not raw or not isinstance(raw, dict):
        return base
    for key in DEFAULT_BINDINGS:
        if key in raw and raw[key] is not None:
            if key == "priority_smoke_values":
                val = raw[key]
                base[key] = list(val) if isinstance(val, list) else ["1"]
            elif key == "export_profile":
                base[key] = normalize_export_profile(raw[key])
            else:
                base[key] = str(raw[key]).strip() if key != "priority_smoke_values" else base[key]
    if isinstance(raw.get("priority_smoke_values"), list):
        base["priority_smoke_values"] = [str(x) for x in raw["priority_smoke_values"]]
    return base


def get_export_profile(bindings: Optional[dict]) -> str:
    return get_export_profile_from_bindings(bindings)


def get_project_bindings(project: Project) -> dict:
    gv = project.global_vars if isinstance(project.global_vars, dict) else {}
    return normalize_bindings(gv.get(ZENTAO_GLOBAL_VARS_KEY))


async def load_project_bindings(project_id: int) -> dict:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return normalize_bindings(None)
    return get_project_bindings(project)


def get_requirement_bindings(meta: Optional[dict]) -> dict:
    if not meta or not isinstance(meta, dict):
        return normalize_bindings(None)
    return normalize_bindings(meta.get("export_defaults"))


def merge_bindings(project_bindings: dict, requirement_bindings: dict) -> dict:
    """需求级非空字段覆盖项目级"""
    merged = normalize_bindings(project_bindings)
    req = normalize_bindings(requirement_bindings)
    for key in ("product", "module", "related_story", "default_stage", "smoke_stage"):
        if req.get(key):
            merged[key] = req[key]
    if req.get("priority_smoke_values"):
        merged["priority_smoke_values"] = req["priority_smoke_values"]
    return merged


def resolve_stage(priority: str, bindings: Optional[dict] = None) -> str:
    """优先级 1（可配置）→ 冒烟测试阶段，其余 → 系统测试阶段"""
    b = normalize_bindings(bindings)
    p = str(priority or "2").strip()
    smoke_values = b.get("priority_smoke_values") or ["1"]
    if p in smoke_values:
        return b.get("smoke_stage") or "冒烟测试阶段"
    return b.get("default_stage") or "系统测试阶段"


def validate_bindings(bindings: dict, *, for_action: str = "操作") -> list[str]:
    """返回缺失字段中文名列表；空列表表示通过"""
    b = normalize_bindings(bindings)
    if get_export_profile(b) == EXPORT_PROFILE_GENERIC:
        return []
    missing = []
    for key, label in BINDING_FIELD_LABELS.items():
        if not (b.get(key) or "").strip():
            missing.append(label)
    return missing


def validate_bindings_for_export(bindings: dict) -> list[str]:
    """按导出目标校验绑定：通用模式不要求禅道三项。"""
    return validate_bindings(bindings)


def bindings_for_export(bindings: dict) -> dict:
    """导出用 defaults 结构（兼容 zentao_case_export）"""
    b = normalize_bindings(bindings)
    return {
        "product": b["product"],
        "module": b["module"],
        "related_story": b["related_story"],
        "default_stage": b["default_stage"],
    }


def apply_bindings_to_case_fields(case_item: dict, bindings: dict) -> dict:
    """将绑定写入用例：禅道三项 + 按优先级计算适用阶段；module 保留为功能模块"""
    b = normalize_bindings(bindings)
    priority = str(case_item.get("priority") or "2")
    return {
        **case_item,
        "product": b["product"],
        "related_story": b["related_story"],
        "stage": resolve_stage(priority, b),
    }


def build_requirement_case_extra(
    bindings: dict,
    *,
    existing: Optional[dict] = None,
) -> dict:
    """入库 extra：保存禅道所属模块快照，与 AI 功能模块（case.module）区分"""
    extra = dict(existing) if isinstance(existing, dict) else {}
    b = normalize_bindings(bindings)
    if (b.get("module") or "").strip():
        extra["zentao_module"] = b["module"].strip()
    return extra


async def save_project_bindings(project_id: int, bindings: dict) -> dict:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    gv = dict(project.global_vars or {})
    gv[ZENTAO_GLOBAL_VARS_KEY] = normalize_bindings(bindings)
    project.global_vars = gv
    await project.save()
    return get_project_bindings(project)
