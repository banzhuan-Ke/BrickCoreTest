"""
Curl 命令解析器
支持解析标准 curl 命令（含 Apifox / Postman 导出的长选项），提取接口信息
"""
import base64
import json
import re
import shlex
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


# 跟随重定向等与接口定义无关的选项（可带值 / 不带值）
_FLAG_ONLY = {
    "-L",
    "--location",
    "-i",
    "--include",
    "-I",
    "--head",
    "-v",
    "--verbose",
    "-s",
    "--silent",
    "-S",
    "--show-error",
    "-k",
    "--insecure",
    "-f",
    "--fail",
    "-g",
    "--globoff",
    "-N",
    "--no-buffer",
    "--compressed",
    "--http1.0",
    "--http1.1",
    "--http2",
    "--http2-prior-knowledge",
}

_OPTS_WITH_VALUE = {
    "-X",
    "--request",
    "-H",
    "--header",
    "-d",
    "--data",
    "--data-raw",
    "--data-binary",
    "--data-ascii",
    "--data-urlencode",
    "-u",
    "--user",
    "--url",
    "-A",
    "--user-agent",
    "-b",
    "--cookie",
    "-e",
    "--referer",
    "-o",
    "--output",
    "-w",
    "--write-out",
    "--connect-timeout",
    "--max-time",
    "-m",
    "--proxy",
    "-x",
    "--max-redirs",
}


def _normalize_curl_text(curl_command: str) -> str:
    """合并续行、统一空白。"""
    text = curl_command.replace("\r\n", "\n").replace("\r", "\n")
    # bash 风格续行：反斜杠 + 换行
    text = re.sub(r"\\\s*\n", " ", text)
    # 去掉首尾空白，压缩多空格但保留引号内内容由 shlex 处理
    return text.strip()


def _tokenize(curl_command: str) -> List[str]:
    text = _normalize_curl_text(curl_command)
    if not text:
        return []
    # Windows 粘贴可能用双引号包裹整段；优先 POSIX 风格（单引号常见于 Apifox）
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        # 未闭合引号等：退化为粗略按空白切分
        return text.split()


def _looks_like_url(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    lower = token.lower()
    return lower.startswith("http://") or lower.startswith("https://") or lower.startswith("{{")


def parse_curl(curl_command: str) -> Dict[str, Any]:
    """
    解析 curl 命令，返回接口信息

    支持的 curl 选项：
    - -X, --request: HTTP 方法
    - -H, --header: 请求头
    - -d, --data / --data-raw / --data-binary / --data-urlencode: 请求体
    - -u, --user: 用户名密码
    - -L, --location: 跟随重定向（忽略，不影响解析）
    - --url: URL
    - Apifox 常见：curl --location --request POST 'https://...' --header '...' --data-raw '...'

    Returns:
        {
            "name": str,
            "method": str,
            "path": str,
            "base_url": str,
            "headers": dict,
            "params": list,
            "body": any,
            "body_type": str
        }
    """
    result: Dict[str, Any] = {
        "name": "",
        "method": "GET",
        "path": "",
        "base_url": "",
        "headers": {},
        "params": [],
        "body": None,
        "body_type": "none",
    }

    tokens = _tokenize(curl_command)
    if not tokens:
        raise ValueError("无法从 curl 命令中提取 URL")

    # 去掉开头的 curl / curl.exe
    if tokens and re.match(r"(?i)^curl(\.exe)?$", tokens[0]):
        tokens = tokens[1:]

    url: Optional[str] = None
    method: Optional[str] = None
    headers: Dict[str, str] = {}
    body_parts: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in _FLAG_ONLY:
            i += 1
            continue

        # --opt=value
        if tok.startswith("--") and "=" in tok:
            opt_name, val = tok.split("=", 1)
            if opt_name in _OPTS_WITH_VALUE:
                if opt_name in ("-X", "--request"):
                    method = val.upper()
                elif opt_name in ("-H", "--header"):
                    if ":" in val:
                        key, value = val.split(":", 1)
                        key, value = key.strip(), value.strip()
                        if key:
                            headers[key] = value
                elif opt_name in (
                    "-d",
                    "--data",
                    "--data-raw",
                    "--data-binary",
                    "--data-ascii",
                    "--data-urlencode",
                ):
                    body_parts.append(val)
                elif opt_name == "--url":
                    url = val
                elif opt_name in ("-A", "--user-agent"):
                    headers["User-Agent"] = val
                elif opt_name in ("-b", "--cookie"):
                    headers["Cookie"] = val
                elif opt_name in ("-e", "--referer"):
                    headers["Referer"] = val
                elif opt_name in ("-u", "--user"):
                    encoded = base64.b64encode(val.encode("utf-8")).decode("ascii")
                    headers["Authorization"] = f"Basic {encoded}"
            i += 1
            continue

        if tok in _OPTS_WITH_VALUE:
            if i + 1 >= len(tokens):
                i += 1
                continue
            val = tokens[i + 1]
            i += 2
            opt_name = tok

            if opt_name in ("-X", "--request"):
                method = val.upper()
            elif opt_name in ("-H", "--header"):
                if ":" in val:
                    key, value = val.split(":", 1)
                    key, value = key.strip(), value.strip()
                    if key:
                        headers[key] = value
            elif opt_name in (
                "-d",
                "--data",
                "--data-raw",
                "--data-binary",
                "--data-ascii",
                "--data-urlencode",
            ):
                body_parts.append(val)
            elif opt_name == "--url":
                url = val
            elif opt_name in ("-A", "--user-agent"):
                headers["User-Agent"] = val
            elif opt_name in ("-b", "--cookie"):
                headers["Cookie"] = val
            elif opt_name in ("-e", "--referer"):
                headers["Referer"] = val
            elif opt_name in ("-u", "--user"):
                encoded = base64.b64encode(val.encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"Basic {encoded}"
            continue

        # 未知长选项：若下一项不是 URL，跳过一对；否则只跳过选项本身
        if tok.startswith("--"):
            if i + 1 < len(tokens) and not _looks_like_url(tokens[i + 1]) and not tokens[i + 1].startswith("-"):
                i += 2
            else:
                i += 1
            continue

        # 短选项连写如 -sL
        if tok.startswith("-") and not tok.startswith("--") and len(tok) > 2 and "=" not in tok:
            letters = tok[1:]
            if all(f"-{c}" in _FLAG_ONLY or c in "LsivkfgNS" for c in letters):
                i += 1
                continue

        # 位置参数：URL
        if _looks_like_url(tok):
            if url is None:
                url = tok
            i += 1
            continue

        i += 1

    # 兜底：整段文本里搜第一个 http(s) URL（应对极端粘贴）
    if not url:
        m = re.search(r"https?://[^\s'\"\\]+", curl_command)
        if m:
            url = m.group(0).rstrip("\\\"'")

    if not url:
        raise ValueError("无法从 curl 命令中提取 URL")

    parsed_url = urlparse(url)
    result["base_url"] = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme and parsed_url.netloc else ""
    result["path"] = parsed_url.path or "/"

    path_parts = [p for p in result["path"].split("/") if p]
    if path_parts:
        result["name"] = path_parts[-1].replace("-", "_").replace(".", "_")
    else:
        result["name"] = "api"

    if parsed_url.query:
        query_params = parse_qs(parsed_url.query)
        for key, values in query_params.items():
            result["params"].append(
                {
                    "name": key,
                    "value": values[0] if values else "",
                    "type": "string",
                    "description": "",
                }
            )

    if method:
        result["method"] = method
    elif body_parts:
        result["method"] = "POST"

    result["headers"] = headers

    body = "&".join(body_parts) if body_parts else None
    if body:
        try:
            json_body = json.loads(body)
            result["body"] = json_body
            result["body_type"] = "json"
        except json.JSONDecodeError:
            if "&" in body or "=" in body:
                form_data: Dict[str, str] = {}
                for pair in body.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        form_data[key] = value
                result["body"] = form_data
                result["body_type"] = "x-www-form-urlencoded"
            else:
                result["body"] = body
                result["body_type"] = "raw"

    content_type = result["headers"].get("Content-Type", "") or result["headers"].get("content-type", "")
    if "application/json" in content_type:
        result["body_type"] = "json"
    elif "application/x-www-form-urlencoded" in content_type:
        result["body_type"] = "x-www-form-urlencoded"
    elif "multipart/form-data" in content_type:
        result["body_type"] = "form-data"
    elif "text/xml" in content_type or "application/xml" in content_type:
        result["body_type"] = "xml"

    return result


def curl_to_api_definition(curl_command: str, project_id: int) -> Dict[str, Any]:
    """
    将 curl 命令转换为 API 定义格式
    """
    parsed = parse_curl(curl_command)

    headers = []
    for key, value in parsed["headers"].items():
        headers.append({"key": key, "value": value, "description": ""})

    params = []
    for param in parsed["params"]:
        params.append(
            {
                "name": param["name"],
                "value": param["value"],
                "type": "string",
                "description": "",
            }
        )

    body = parsed["body"] if parsed["body"] else {}

    return {
        "name": parsed["name"],
        "path": parsed["path"],
        "method": parsed["method"],
        "base_url": parsed["base_url"],
        "headers": headers,
        "params": params,
        "body": body,
        "body_type": parsed["body_type"],
        "project_id": project_id,
        "description": f"从 curl 命令导入: {parsed['method']} {parsed['path']}",
    }
