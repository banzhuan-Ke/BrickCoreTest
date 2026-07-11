"""
禅道用例类型（导出 XLSX「用例类型」列须落在该枚举内）
"""
from typing import Optional

# 与禅道 Web 端下拉一致；变更频率低，以代码常量维护即可
ZENTAO_CASE_TYPES: tuple[str, ...] = (
    "场景测试",
    "功能测试",
    "性能测试",
    "配置相关",
    "安装部署",
    "安全相关",
    "接口测试",
    "其他",
    "自动化测试",
)

DEFAULT_ZENTAO_CASE_TYPE = "功能测试"

# 生成阶段「测试设计维度」，不写入禅道 type
TEST_DESIGN_TYPES: tuple[str, ...] = (
    "正向流程",
    "异常/反向",
    "边界值",
    "接口校验",
    "其他",
)

# AI 常把设计维度误写入 type 字段时的归一化
_DESIGN_TYPE_ALIASES: dict[str, str] = {
    "正向流程": "正向流程",
    "正向": "正向流程",
    "主路径": "正向流程",
    "异常/反向": "异常/反向",
    "异常": "异常/反向",
    "反向": "异常/反向",
    "边界值": "边界值",
    "边界": "边界值",
    "接口校验": "接口校验",
    "api": "接口校验",
    "API": "接口校验",
    "接口": "接口校验",
}


def normalize_test_design(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    if s in TEST_DESIGN_TYPES:
        return s
    return _DESIGN_TYPE_ALIASES.get(s) or _DESIGN_TYPE_ALIASES.get(s.replace(" ", ""))


def normalize_zentao_case_type(
    raw_type: Optional[str],
    *,
    test_design: Optional[str] = None,
    default: str = DEFAULT_ZENTAO_CASE_TYPE,
) -> str:
    """将 AI/手工输入归一为禅道支持的用例类型"""
    s = (raw_type or "").strip()
    design = normalize_test_design(test_design)

    if s in ZENTAO_CASE_TYPES:
        return s

    if s:
        design_from_type = normalize_test_design(s)
        if design_from_type:
            if design_from_type == "接口校验":
                return "接口测试"
            return default

        if "接口" in s or s.upper() == "API":
            return "接口测试"
        if "性能" in s:
            return "性能测试"
        if "场景" in s:
            return "场景测试"
        if "安全" in s:
            return "安全相关"
        if "配置" in s:
            return "配置相关"
        if "安装" in s or "部署" in s:
            return "安装部署"
        if "自动化" in s:
            return "自动化测试"

    if design == "接口校验":
        return "接口测试"

    return default or DEFAULT_ZENTAO_CASE_TYPE


def split_case_type_fields(
    item: dict,
    *,
    default_zentao: str = DEFAULT_ZENTAO_CASE_TYPE,
) -> tuple[str, Optional[str]]:
    """
    解析模型输出的 type / test_design。
    返回 (禅道 type, 测试设计维度)。
    """
    raw_type = (item.get("type") or "").strip()
    raw_design = (
        item.get("test_design")
        or item.get("design_category")
        or item.get("case_design")
        or ""
    ).strip()
    design = normalize_test_design(raw_design)

    if raw_type in ZENTAO_CASE_TYPES:
        zentao_type = raw_type
        if raw_type == default_zentao:
            inferred = normalize_test_design(raw_type)
            if inferred and inferred != raw_type:
                design = design or inferred
    elif raw_type:
        inferred = normalize_test_design(raw_type)
        if inferred:
            design = design or inferred
            zentao_type = normalize_zentao_case_type(None, test_design=inferred, default=default_zentao)
        else:
            zentao_type = normalize_zentao_case_type(raw_type, test_design=design, default=default_zentao)
    else:
        zentao_type = normalize_zentao_case_type(None, test_design=design, default=default_zentao)

    return zentao_type, design
