"""通用数据工厂工具执行器"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import string
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

from jsonpath_ng import parse as jsonpath_parse

try:
    from faker import Faker
except ImportError:
    Faker = None

from app.core.data_tools.errors import ToolExecutionError
from app.core.data_tools.json_utils import parse_json_text
from app.core.data_tools.registry import get_tool_definition
from app.core.data_tools.extended_tools import build_extended_handlers

_faker = Faker("zh_CN") if Faker else None


def _output(value: Any) -> dict[str, Any]:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = "" if value is None else str(value)
    return {"output": value, "output_text": text}


def execute_tool(tool_id: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    definition = get_tool_definition(tool_id)
    if not definition:
        raise ToolExecutionError(f"未知工具: {tool_id}")

    data = dict(inputs or {})
    for field in definition.get("inputs") or []:
        key = field["key"]
        if field.get("required") and (data.get(key) in (None, "")):
            raise ToolExecutionError(f"请填写{field.get('label') or key}")

    handler = _HANDLERS.get(tool_id)
    if not handler:
        raise ToolExecutionError(f"工具未实现: {tool_id}")
    try:
        return handler(data)
    except ToolExecutionError:
        raise
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ToolExecutionError(str(exc)) from exc


def _random_int(data: dict) -> dict:
    min_v = int(data.get("min", 1))
    max_v = int(data.get("max", 9999))
    if min_v > max_v:
        min_v, max_v = max_v, min_v
    return _output(random.randint(min_v, max_v))


def _random_string(data: dict) -> dict:
    length = max(1, min(int(data.get("length", 8)), 256))
    chars = string.ascii_letters + string.digits
    return _output("".join(random.choice(chars) for _ in range(length)))


def _random_phone(_: dict) -> dict:
    if _faker:
        return _output(_faker.phone_number())
    prefix = random.choice(["130", "131", "132", "133", "135", "136", "137", "138", "139", "150", "151", "152", "157", "158", "159", "186", "187", "188"])
    return _output(prefix + "".join(str(random.randint(0, 9)) for _ in range(8)))


def _base64_encode(data: dict) -> dict:
    text = str(data.get("text", ""))
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return _output(encoded)


def _base64_decode(data: dict) -> dict:
    text = str(data.get("text", "")).strip()
    try:
        decoded = base64.b64decode(text).decode("utf-8")
    except Exception as exc:
        raise ToolExecutionError(f"Base64 解码失败: {exc}") from exc
    return _output(decoded)


def _url_encode(data: dict) -> dict:
    return _output(quote(str(data.get("text", "")), safe=""))


def _url_decode(data: dict) -> dict:
    return _output(unquote(str(data.get("text", ""))))


def _timestamp_to_date(data: dict) -> dict:
    try:
        ts = float(data.get("timestamp"))
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError("时间戳格式无效") from exc
    if ts > 1e12:
        ts = ts / 1000.0
    return _output(datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"))


def _date_to_timestamp(data: dict) -> dict:
    raw = str(data.get("datetime", "")).strip()
    if not raw:
        raw = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return _output(int(datetime.strptime(raw, fmt).timestamp()))
        except ValueError:
            continue
    raise ToolExecutionError("日期格式无效，示例：2026-06-04 12:00:00")


def _md5(data: dict) -> dict:
    text = str(data.get("text", ""))
    return _output(hashlib.md5(text.encode("utf-8")).hexdigest())


def _sha256(data: dict) -> dict:
    text = str(data.get("text", ""))
    return _output(hashlib.sha256(text.encode("utf-8")).hexdigest())


def _json_format(data: dict) -> dict:
    obj = parse_json_text(str(data.get("text", "")))
    return _output(json.dumps(obj, ensure_ascii=False, indent=2))


def _json_compress(data: dict) -> dict:
    obj = parse_json_text(str(data.get("text", "")))
    return _output(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def _json_path(data: dict) -> dict:
    path = str(data.get("path", "")).strip()
    if not path:
        raise ToolExecutionError("请填写 JSONPath")
    obj = parse_json_text(str(data.get("text", "")))
    try:
        matches = [m.value for m in jsonpath_parse(path).find(obj)]
    except Exception as exc:
        raise ToolExecutionError(f"JSONPath 无效: {exc}") from exc
    if not matches:
        return _output(None)
    if len(matches) == 1:
        return _output(matches[0])
    return _output(matches)


def _chinese_name(_: dict) -> dict:
    if _faker:
        return _output(_faker.name())
    return _output("测试用户")


def _email(_: dict) -> dict:
    if _faker:
        return _output(_faker.email())
    return _output(f"test{random.randint(1000, 9999)}@example.com")


def _chinese_mobile(_: dict) -> dict:
    return _random_phone(_)


_HANDLERS = {
    "uuid": lambda _: _output(str(uuid.uuid4())),
    "random_int": _random_int,
    "random_string": _random_string,
    "random_phone": _random_phone,
    "base64_encode": _base64_encode,
    "base64_decode": _base64_decode,
    "url_encode": _url_encode,
    "url_decode": _url_decode,
    "timestamp_to_date": _timestamp_to_date,
    "date_to_timestamp": _date_to_timestamp,
    "md5": _md5,
    "sha256": _sha256,
    "json_format": _json_format,
    "json_compress": _json_compress,
    "json_path": _json_path,
    "chinese_name": _chinese_name,
    "email": _email,
    "chinese_mobile": _chinese_mobile,
    **build_extended_handlers(),
}
