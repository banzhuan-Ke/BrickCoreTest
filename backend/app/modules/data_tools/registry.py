"""通用数据工厂工具注册表"""
from __future__ import annotations

from typing import Any

from app.modules.data_tools.extended_tools import (
    EXTENDED_CATEGORIES,
    EXTENDED_DEFINITIONS,
    build_extended_handlers,
)

TOOL_CATEGORIES: list[dict[str, str]] = [
    {"id": "random", "label": "随机工具"},
    {"id": "encoding", "label": "编码工具"},
    {"id": "encryption", "label": "加密工具"},
    {"id": "json", "label": "JSON 工具"},
    {"id": "test_data", "label": "测试数据"},
    *EXTENDED_CATEGORIES,
]

# input type: string | number | textarea | select
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "uuid",
        "name": "UUID",
        "category": "random",
        "description": "生成 UUID v4",
        "inputs": [],
    },
    {
        "id": "random_int",
        "name": "随机整数",
        "category": "random",
        "description": "指定范围内随机整数",
        "inputs": [
            {"key": "min", "label": "最小值", "type": "number", "default": 1},
            {"key": "max", "label": "最大值", "type": "number", "default": 9999},
        ],
    },
    {
        "id": "random_string",
        "name": "随机字符串",
        "category": "random",
        "description": "生成指定长度随机字母数字串",
        "inputs": [
            {"key": "length", "label": "长度", "type": "number", "default": 8},
        ],
    },
    {
        "id": "random_phone",
        "name": "随机手机号",
        "category": "random",
        "description": "生成中国大陆 11 位手机号",
        "inputs": [],
    },
    {
        "id": "base64_encode",
        "name": "Base64 编码",
        "category": "encoding",
        "description": "文本 Base64 编码",
        "inputs": [
            {"key": "text", "label": "原文", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "base64_decode",
        "name": "Base64 解码",
        "category": "encoding",
        "description": "Base64 解码为文本",
        "inputs": [
            {"key": "text", "label": "Base64", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "url_encode",
        "name": "URL 编码",
        "category": "encoding",
        "description": "URL 百分号编码",
        "inputs": [
            {"key": "text", "label": "原文", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "url_decode",
        "name": "URL 解码",
        "category": "encoding",
        "description": "URL 百分号解码",
        "inputs": [
            {"key": "text", "label": "编码文本", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "timestamp_to_date",
        "name": "时间戳转日期",
        "category": "encoding",
        "description": "Unix 时间戳转可读时间",
        "inputs": [
            {"key": "timestamp", "label": "时间戳(秒)", "type": "number", "required": True},
        ],
    },
    {
        "id": "date_to_timestamp",
        "name": "日期转时间戳",
        "category": "encoding",
        "description": "日期字符串转 Unix 秒级时间戳",
        "inputs": [
            {"key": "datetime", "label": "日期时间", "type": "string", "default": "", "placeholder": "2026-06-04 12:00:00"},
        ],
    },
    {
        "id": "md5",
        "name": "MD5",
        "category": "encryption",
        "description": "计算 MD5 哈希（hex）",
        "inputs": [
            {"key": "text", "label": "原文", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "sha256",
        "name": "SHA256",
        "category": "encryption",
        "description": "计算 SHA256 哈希（hex）",
        "inputs": [
            {"key": "text", "label": "原文", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "json_format",
        "name": "JSON 格式化",
        "category": "json",
        "description": "格式化 JSON 字符串",
        "inputs": [
            {"key": "text", "label": "JSON", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "json_compress",
        "name": "JSON 压缩",
        "category": "json",
        "description": "压缩 JSON 为单行",
        "inputs": [
            {"key": "text", "label": "JSON", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "json_path",
        "name": "JSONPath 查询",
        "category": "json",
        "description": "按 JSONPath 提取值",
        "inputs": [
            {"key": "text", "label": "JSON", "type": "textarea", "required": True},
            {"key": "path", "label": "JSONPath", "type": "string", "default": "$.data", "required": True},
        ],
    },
    {
        "id": "chinese_name",
        "name": "中文姓名",
        "category": "test_data",
        "description": "随机中文姓名",
        "inputs": [],
    },
    {
        "id": "email",
        "name": "随机邮箱",
        "category": "test_data",
        "description": "随机邮箱地址",
        "inputs": [],
    },
    {
        "id": "chinese_mobile",
        "name": "中国手机号",
        "category": "test_data",
        "description": "随机中国手机号",
        "inputs": [],
    },
    *EXTENDED_DEFINITIONS,
]

_TOOL_MAP = {t["id"]: t for t in TOOL_DEFINITIONS}


def get_tool_definition(tool_id: str) -> dict[str, Any] | None:
    return _TOOL_MAP.get(tool_id)


def list_tools(category: str | None = None) -> list[dict[str, Any]]:
    if category:
        return [t for t in TOOL_DEFINITIONS if t["category"] == category]
    return list(TOOL_DEFINITIONS)
