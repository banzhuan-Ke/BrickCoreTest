"""数据工厂第二期扩展工具（定义 + 执行处理器）"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import math
import random
import re
import string
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote, unquote

from jsonpath_ng import parse as jsonpath_parse

try:
    from faker import Faker
except ImportError:
    Faker = None

try:
    import qrcode
    import qrcode.constants
except ImportError:
    qrcode = None

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from app.core.data_tools.errors import ToolExecutionError
from app.core.data_tools.json_utils import parse_json_text

_faker = Faker("zh_CN") if Faker else None


def _output(value: Any) -> dict[str, Any]:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = "" if value is None else str(value)
    return {"output": value, "output_text": text}

EXTENDED_CATEGORIES: list[dict[str, str]] = [
    {"id": "datetime", "label": "日期时间"},
    {"id": "text", "label": "文本处理"},
    {"id": "math", "label": "数学运算"},
    {"id": "cron", "label": "Cron 工具"},
    {"id": "barcode", "label": "条码/二维码"},
]

EXTENDED_DEFINITIONS: list[dict[str, Any]] = [
    # encryption extras
    {"id": "sha1", "name": "SHA1", "category": "encryption", "description": "SHA1 哈希（hex）",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "sha384", "name": "SHA384", "category": "encryption", "description": "SHA384 哈希（hex）",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "sha512", "name": "SHA512", "category": "encryption", "description": "SHA512 哈希（hex）",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "hmac_md5", "name": "HMAC-MD5", "category": "encryption", "description": "HMAC-MD5 签名（hex）",
     "inputs": [
         {"key": "text", "label": "原文", "type": "textarea", "required": True},
         {"key": "secret", "label": "密钥", "type": "string", "required": True},
     ]},
    {"id": "hmac_sha256", "name": "HMAC-SHA256", "category": "encryption", "description": "HMAC-SHA256 签名（hex）",
     "inputs": [
         {"key": "text", "label": "原文", "type": "textarea", "required": True},
         {"key": "secret", "label": "密钥", "type": "string", "required": True},
     ]},
    {"id": "aes_encrypt", "name": "AES 加密", "category": "encryption", "description": "AES-256-CBC 加密，返回 base64(iv+ciphertext)",
     "inputs": [
         {"key": "text", "label": "原文", "type": "textarea", "required": True},
         {"key": "key", "label": "密钥", "type": "string", "required": True, "placeholder": "任意长度，内部 SHA256 派生"},
     ]},
    {"id": "aes_decrypt", "name": "AES 解密", "category": "encryption", "description": "解密 aes_encrypt 输出",
     "inputs": [
         {"key": "text", "label": "密文 Base64", "type": "textarea", "required": True},
         {"key": "key", "label": "密钥", "type": "string", "required": True},
     ]},
    # encoding extras
    {"id": "hex_encode", "name": "Hex 编码", "category": "encoding", "description": "文本转十六进制",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "hex_decode", "name": "Hex 解码", "category": "encoding", "description": "十六进制转文本",
     "inputs": [{"key": "text", "label": "Hex", "type": "textarea", "required": True}]},
    {"id": "html_encode", "name": "HTML 编码", "category": "encoding", "description": "HTML 实体编码",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "html_decode", "name": "HTML 解码", "category": "encoding", "description": "HTML 实体解码",
     "inputs": [{"key": "text", "label": "编码文本", "type": "textarea", "required": True}]},
    {"id": "unicode_escape", "name": "Unicode 转义", "category": "encoding", "description": "中文等转 \\uXXXX",
     "inputs": [{"key": "text", "label": "原文", "type": "textarea", "required": True}]},
    {"id": "unicode_unescape", "name": "Unicode 反转义", "category": "encoding", "description": "\\uXXXX 转字符",
     "inputs": [{"key": "text", "label": "转义文本", "type": "textarea", "required": True}]},
    # json extras
    {"id": "json_compare", "name": "JSON 对比", "category": "json", "description": "比较两段 JSON 是否等价",
     "inputs": [
         {"key": "left", "label": "JSON A", "type": "textarea", "required": True},
         {"key": "right", "label": "JSON B", "type": "textarea", "required": True},
     ]},
    {"id": "json_keys", "name": "JSON 键列表", "category": "json", "description": "提取对象顶层键名",
     "inputs": [{"key": "text", "label": "JSON 对象", "type": "textarea", "required": True}]},
    {"id": "json_get_type", "name": "JSON 值类型", "category": "json", "description": "JSONPath 取值并返回类型",
     "inputs": [
         {"key": "text", "label": "JSON", "type": "textarea", "required": True},
         {"key": "path", "label": "JSONPath", "type": "string", "default": "$", "required": True},
     ]},
    # datetime
    {"id": "now_timestamp", "name": "当前时间戳", "category": "datetime", "description": "当前 Unix 秒级时间戳", "inputs": []},
    {"id": "now_datetime", "name": "当前日期时间", "category": "datetime", "description": "当前本地日期时间字符串", "inputs": []},
    {"id": "date_format", "name": "日期格式化", "category": "datetime", "description": "按格式输出日期",
     "inputs": [
         {"key": "datetime", "label": "日期时间", "type": "string", "placeholder": "留空=当前时间"},
         {"key": "fmt", "label": "格式", "type": "string", "default": "%Y-%m-%d %H:%M:%S"},
     ]},
    {"id": "date_add", "name": "日期加减", "category": "datetime", "description": "在日期上加减天/小时/分钟",
     "inputs": [
         {"key": "datetime", "label": "基准日期", "type": "string", "placeholder": "2026-06-05 12:00:00"},
         {"key": "days", "label": "天数", "type": "number", "default": 0},
         {"key": "hours", "label": "小时", "type": "number", "default": 0},
         {"key": "minutes", "label": "分钟", "type": "number", "default": 0},
     ]},
    {"id": "date_diff_days", "name": "日期相差天数", "category": "datetime", "description": "两日期相差整天数",
     "inputs": [
         {"key": "start", "label": "开始日期", "type": "string", "required": True},
         {"key": "end", "label": "结束日期", "type": "string", "required": True},
     ]},
    # cron
    {"id": "cron_next", "name": "Cron 下次执行", "category": "cron", "description": "计算 Cron 表达式接下来 N 次执行时间",
     "inputs": [
         {"key": "expr", "label": "Cron 表达式", "type": "string", "default": "0 0 * * *", "required": True},
         {"key": "count", "label": "次数", "type": "number", "default": 3},
     ]},
    {"id": "cron_validate", "name": "Cron 校验", "category": "cron", "description": "校验 Cron 表达式是否合法",
     "inputs": [{"key": "expr", "label": "Cron 表达式", "type": "string", "required": True}]},
    # text
    {"id": "str_length", "name": "字符串长度", "category": "text", "description": "返回字符数",
     "inputs": [{"key": "text", "label": "文本", "type": "textarea", "required": True}]},
    {"id": "str_substring", "name": "字符串截取", "category": "text", "description": "按起始位置和长度截取",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "start", "label": "起始位置", "type": "number", "default": 0},
         {"key": "length", "label": "长度", "type": "number", "default": 10},
     ]},
    {"id": "str_replace", "name": "字符串替换", "category": "text", "description": "替换所有匹配子串",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "old", "label": "查找", "type": "string", "required": True},
         {"key": "new", "label": "替换为", "type": "string", "default": ""},
     ]},
    {"id": "str_trim", "name": "去首尾空白", "category": "text", "description": "strip 首尾空格",
     "inputs": [{"key": "text", "label": "文本", "type": "textarea", "required": True}]},
    {"id": "str_split", "name": "字符串分割", "category": "text", "description": "按分隔符拆分为数组",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "sep", "label": "分隔符", "type": "string", "default": ","},
     ]},
    {"id": "str_join", "name": "字符串拼接", "category": "text", "description": "用分隔符拼接多行文本",
     "inputs": [
         {"key": "text", "label": "多行文本", "type": "textarea", "required": True, "placeholder": "每行一项"},
         {"key": "sep", "label": "分隔符", "type": "string", "default": ","},
     ]},
    {"id": "regex_match", "name": "正则匹配", "category": "text", "description": "是否匹配正则",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "pattern", "label": "正则", "type": "string", "required": True},
     ]},
    {"id": "regex_replace", "name": "正则替换", "category": "text", "description": "正则替换",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "pattern", "label": "正则", "type": "string", "required": True},
         {"key": "repl", "label": "替换为", "type": "string", "default": ""},
     ]},
    {"id": "regex_findall", "name": "正则提取全部", "category": "text", "description": "findall 提取",
     "inputs": [
         {"key": "text", "label": "文本", "type": "textarea", "required": True},
         {"key": "pattern", "label": "正则", "type": "string", "required": True},
     ]},
    {"id": "pad_left", "name": "左填充", "category": "text", "description": "左侧填充至指定长度",
     "inputs": [
         {"key": "text", "label": "文本", "type": "string", "required": True},
         {"key": "length", "label": "目标长度", "type": "number", "default": 8},
         {"key": "char", "label": "填充字符", "type": "string", "default": "0"},
     ]},
    # math
    {"id": "math_add", "name": "加法", "category": "math", "description": "两数相加",
     "inputs": [
         {"key": "a", "label": "A", "type": "number", "required": True},
         {"key": "b", "label": "B", "type": "number", "required": True},
     ]},
    {"id": "math_sub", "name": "减法", "category": "math", "description": "A - B",
     "inputs": [
         {"key": "a", "label": "A", "type": "number", "required": True},
         {"key": "b", "label": "B", "type": "number", "required": True},
     ]},
    {"id": "math_mul", "name": "乘法", "category": "math", "description": "A × B",
     "inputs": [
         {"key": "a", "label": "A", "type": "number", "required": True},
         {"key": "b", "label": "B", "type": "number", "required": True},
     ]},
    {"id": "math_div", "name": "除法", "category": "math", "description": "A ÷ B",
     "inputs": [
         {"key": "a", "label": "A", "type": "number", "required": True},
         {"key": "b", "label": "B", "type": "number", "required": True},
     ]},
    {"id": "math_round", "name": "四舍五入", "category": "math", "description": "保留 N 位小数",
     "inputs": [
         {"key": "value", "label": "数值", "type": "number", "required": True},
         {"key": "digits", "label": "小数位", "type": "number", "default": 2},
     ]},
    # random extras
    {"id": "random_float", "name": "随机小数", "category": "random", "description": "范围内随机浮点数",
     "inputs": [
         {"key": "min", "label": "最小值", "type": "number", "default": 0},
         {"key": "max", "label": "最大值", "type": "number", "default": 1},
         {"key": "digits", "label": "小数位", "type": "number", "default": 2},
     ]},
    {"id": "random_bool", "name": "随机布尔", "category": "random", "description": "true / false", "inputs": []},
    {"id": "random_ipv4", "name": "随机 IPv4", "category": "random", "description": "随机 IPv4 地址", "inputs": []},
    {"id": "random_hex", "name": "随机 Hex", "category": "random", "description": "随机十六进制串",
     "inputs": [{"key": "length", "label": "字节数×2", "type": "number", "default": 16}]},
    {"id": "random_uuid_short", "name": "短 UUID", "category": "random", "description": "UUID 去横线", "inputs": []},
    # test_data extras
    {"id": "chinese_address", "name": "中文地址", "category": "test_data", "description": "随机中文地址", "inputs": []},
    {"id": "company_name", "name": "公司名称", "category": "test_data", "description": "随机公司名", "inputs": []},
    {"id": "id_card", "name": "身份证号", "category": "test_data", "description": "随机 18 位身份证号（测试用）", "inputs": []},
    {"id": "random_url", "name": "随机 URL", "category": "test_data", "description": "随机 http URL", "inputs": []},
    {"id": "random_password", "name": "随机密码", "category": "test_data", "description": "随机强密码",
     "inputs": [{"key": "length", "label": "长度", "type": "number", "default": 12}]},
    {"id": "username_gen", "name": "随机用户名", "category": "test_data", "description": "user_xxx 格式", "inputs": []},
    {"id": "ipv4", "name": "IPv4 地址", "category": "test_data", "description": "同 random_ipv4", "inputs": []},
    {"id": "credit_card", "name": "银行卡号", "category": "test_data", "description": "随机银行卡号（测试用）", "inputs": []},
    {"id": "timestamp_ms", "name": "毫秒时间戳", "category": "datetime", "description": "当前毫秒时间戳", "inputs": []},
    # barcode
    {"id": "qrcode_base64", "name": "二维码 Base64", "category": "barcode", "description": "生成 PNG 二维码的 data:image base64",
     "inputs": [
         {"key": "text", "label": "内容", "type": "textarea", "required": True},
         {"key": "size", "label": "尺寸(px)", "type": "number", "default": 200},
     ]},
    {"id": "code128_text", "name": "Code128 编码串", "category": "barcode", "description": "生成 Code128 可编码文本（含校验）",
     "inputs": [{"key": "text", "label": "内容", "type": "string", "required": True}]},
]


def _parse_datetime(raw: str) -> datetime:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ToolExecutionError("日期格式无效")


def _derive_aes_key(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()


def _aes_encrypt(data: dict) -> dict:
    text = str(data.get("text", ""))
    key = _derive_aes_key(str(data.get("key", "")))
    iv = random.randbytes(16)
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return _output(base64.b64encode(iv + ct).decode("ascii"))


def _aes_decrypt(data: dict) -> dict:
    key = _derive_aes_key(str(data.get("key", "")))
    try:
        raw = base64.b64decode(str(data.get("text", "")).strip())
        iv, ct = raw[:16], raw[16:]
    except Exception as exc:
        raise ToolExecutionError(f"密文无效: {exc}") from exc
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return _output(plain.decode("utf-8"))


def _json_compare(data: dict) -> dict:
    left = parse_json_text(str(data.get("left", "")), label="左侧 JSON")
    right = parse_json_text(str(data.get("right", "")), label="右侧 JSON")
    equal = left == right
    return _output({"equal": equal, "message": "相同" if equal else "不同"})


def _cron_next(data: dict) -> dict:
    expr = str(data.get("expr", "")).strip()
    count = max(1, min(int(data.get("count", 3)), 20))
    try:
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger.from_crontab(expr)
    except Exception as exc:
        raise ToolExecutionError(f"Cron 表达式无效: {exc}") from exc
    times = []
    dt = datetime.now()
    for _ in range(count):
        nxt = trigger.get_next_fire_time(None, dt)
        if nxt is None:
            break
        times.append(nxt.strftime("%Y-%m-%d %H:%M:%S"))
        dt = nxt + timedelta(seconds=1)
    return _output(times)


def _cron_validate(data: dict) -> dict:
    expr = str(data.get("expr", "")).strip()
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(expr)
        return _output({"valid": True, "message": "合法"})
    except Exception as exc:
        return _output({"valid": False, "message": str(exc)})


def _id_card(_: dict) -> dict:
    if _faker:
        return _output(_faker.ssn())
    area = "110101"
    birth = f"{random.randint(1970, 2005):04d}{random.randint(1, 12):02d}{random.randint(1, 28):02d}"
    seq = f"{random.randint(0, 999):03d}"
    body = area + birth + seq
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_map = "10X98765432"
    s = sum(int(body[i]) * weights[i] for i in range(17))
    return _output(body + check_map[s % 11])


def _code128_text(data: dict) -> dict:
    text = str(data.get("text", ""))
    if not text:
        raise ToolExecutionError("内容不能为空")
    # Code128B 简化：返回可打印内容 + 长度校验信息
    encoded = "".join(chr(ord(c)) for c in text if 32 <= ord(c) <= 126)
    checksum = sum(ord(c) for c in encoded) % 103
    return _output({"content": text, "printable": encoded, "checksum_mod103": checksum})


def _qrcode_base64(data: dict) -> dict:
    if not qrcode:
        raise ToolExecutionError("未安装 qrcode 库，请联系管理员")
    text = str(data.get("text", ""))
    size = max(80, min(int(data.get("size", 200)), 800))
    qr = qrcode.QRCode(version=None, box_size=10, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size))
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return _output(f"data:image/png;base64,{b64}")


def _hex_decode(data: dict) -> dict:
    try:
        return _output(bytes.fromhex(str(data.get("text", "")).strip()).decode("utf-8"))
    except Exception as exc:
        raise ToolExecutionError(f"Hex 解码失败: {exc}") from exc


def _json_keys(data: dict) -> dict:
    obj = parse_json_text(str(data.get("text", "")))
    if not isinstance(obj, dict):
        raise ToolExecutionError("需要 JSON 对象")
    return _output(list(obj.keys()))


def build_extended_handlers() -> dict[str, Any]:
    def _hash_algo(algo: str):
        def _fn(data: dict) -> dict:
            text = str(data.get("text", ""))
            h = hashlib.new(algo, text.encode("utf-8")).hexdigest()
            return _output(h)
        return _fn

    def _hmac_algo(algo: str):
        def _fn(data: dict) -> dict:
            text = str(data.get("text", "")).encode("utf-8")
            secret = str(data.get("secret", "")).encode("utf-8")
            return _output(hmac.new(secret, text, algo).hexdigest())
        return _fn

    return {
        "sha1": _hash_algo("sha1"),
        "sha384": _hash_algo("sha384"),
        "sha512": _hash_algo("sha512"),
        "hmac_md5": _hmac_algo("md5"),
        "hmac_sha256": _hmac_algo("sha256"),
        "aes_encrypt": _aes_encrypt,
        "aes_decrypt": _aes_decrypt,
        "hex_encode": lambda d: _output(str(d.get("text", "")).encode("utf-8").hex()),
        "hex_decode": lambda d: _hex_decode(d),
        "html_encode": lambda d: _output(html.escape(str(d.get("text", "")))),
        "html_decode": lambda d: _output(html.unescape(str(d.get("text", "")))),
        "unicode_escape": lambda d: _output(str(d.get("text", "")).encode("unicode_escape").decode("ascii")),
        "unicode_unescape": lambda d: _output(bytes(str(d.get("text", "")), "utf-8").decode("unicode_escape")),
        "json_compare": _json_compare,
        "json_keys": _json_keys,
        "json_get_type": lambda d: _output(_json_get_type(d)),
        "now_timestamp": lambda _: _output(int(datetime.now().timestamp())),
        "timestamp_ms": lambda _: _output(int(datetime.now().timestamp() * 1000)),
        "now_datetime": lambda _: _output(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "date_format": lambda d: _output(_parse_datetime(str(d.get("datetime", ""))).strftime(str(d.get("fmt") or "%Y-%m-%d %H:%M:%S"))),
        "date_add": lambda d: _output((_parse_datetime(str(d.get("datetime", ""))) + timedelta(days=int(d.get("days", 0)), hours=int(d.get("hours", 0)), minutes=int(d.get("minutes", 0)))).strftime("%Y-%m-%d %H:%M:%S")),
        "date_diff_days": lambda d: _output((_parse_datetime(str(d.get("end", ""))) - _parse_datetime(str(d.get("start", "")))).days),
        "cron_next": _cron_next,
        "cron_validate": _cron_validate,
        "str_length": lambda d: _output(len(str(d.get("text", "")))),
        "str_substring": lambda d: _output(str(d.get("text", ""))[int(d.get("start", 0)): int(d.get("start", 0)) + int(d.get("length", 10))]),
        "str_replace": lambda d: _output(str(d.get("text", "")).replace(str(d.get("old", "")), str(d.get("new", "")))),
        "str_trim": lambda d: _output(str(d.get("text", "")).strip()),
        "str_split": lambda d: _output(str(d.get("text", "")).split(str(d.get("sep", ",")))),
        "str_join": lambda d: _output(str(d.get("sep", ",")).join(line for line in str(d.get("text", "")).splitlines() if line.strip() != "")),
        "regex_match": lambda d: _output(bool(re.search(str(d.get("pattern", "")), str(d.get("text", ""))))),
        "regex_replace": lambda d: _output(re.sub(str(d.get("pattern", "")), str(d.get("repl", "")), str(d.get("text", "")))),
        "regex_findall": lambda d: _output(re.findall(str(d.get("pattern", "")), str(d.get("text", "")))),
        "pad_left": lambda d: _output(str(d.get("char", "0")) * max(0, int(d.get("length", 8)) - len(str(d.get("text", "")))) + str(d.get("text", ""))),
        "math_add": lambda d: _output(float(d.get("a", 0)) + float(d.get("b", 0))),
        "math_sub": lambda d: _output(float(d.get("a", 0)) - float(d.get("b", 0))),
        "math_mul": lambda d: _output(float(d.get("a", 0)) * float(d.get("b", 0))),
        "math_div": lambda d: _output(float(d.get("a", 0)) / float(d.get("b", 0)) if float(d.get("b", 0)) != 0 else math.inf),
        "math_round": lambda d: _output(round(float(d.get("value", 0)), int(d.get("digits", 2)))),
        "random_float": lambda d: _output(round(random.uniform(float(d.get("min", 0)), float(d.get("max", 1))), int(d.get("digits", 2)))),
        "random_bool": lambda _: _output(random.choice([True, False])),
        "random_ipv4": lambda _: _output(".".join(str(random.randint(1, 254)) for _ in range(4))),
        "random_hex": lambda d: _output("".join(f"{random.randint(0, 255):02x}" for _ in range(max(1, int(d.get("length", 16)) // 2)))),
        "random_uuid_short": lambda _: _output(uuid.uuid4().hex),
        "chinese_address": lambda _: _output(_faker.address() if _faker else "北京市朝阳区测试路1号"),
        "company_name": lambda _: _output(_faker.company() if _faker else "测试科技有限公司"),
        "id_card": _id_card,
        "random_url": lambda _: _output(_faker.url() if _faker else f"https://example.com/{random.randint(1000, 9999)}"),
        "random_password": lambda d: _output("".join(random.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(max(6, int(d.get("length", 12)))))),
        "username_gen": lambda _: _output(f"user_{random.randint(10000, 99999)}"),
        "ipv4": lambda _: _output(".".join(str(random.randint(1, 254)) for _ in range(4))),
        "credit_card": lambda _: _output(_faker.credit_card_number() if _faker else "622202" + "".join(str(random.randint(0, 9)) for _ in range(13))),
        "qrcode_base64": _qrcode_base64,
        "code128_text": _code128_text,
    }


def _json_get_type(data: dict) -> str:
    text = str(data.get("text", ""))
    path = str(data.get("path", "$")).strip()
    obj = parse_json_text(text)
    try:
        matches = [m.value for m in jsonpath_parse(path).find(obj)]
    except Exception as exc:
        raise ToolExecutionError(f"JSONPath 无效: {exc}") from exc
    if not matches:
        return "null"
    val = matches[0]
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, list):
        return "array"
    if isinstance(val, dict):
        return "object"
    return type(val).__name__
