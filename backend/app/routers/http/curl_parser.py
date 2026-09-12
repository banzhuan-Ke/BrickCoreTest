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


_DATA_PLACEHOLDER_PREFIX = "__CURL_BODY_"


def _unescape_bash_ansi_c(inner: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch != "\\" or i + 1 >= len(inner):
            out.append(ch)
            i += 1
            continue
        nxt = inner[i + 1]
        if nxt == "n":
            out.append("\n")
            i += 2
        elif nxt == "r":
            out.append("\r")
            i += 2
        elif nxt == "t":
            out.append("\t")
            i += 2
        elif nxt == "\\":
            out.append("\\")
            i += 2
        elif nxt == "'":
            out.append("'")
            i += 2
        elif nxt == "a":
            out.append("\a")
            i += 2
        elif nxt == "b":
            out.append("\b")
            i += 2
        elif nxt in "01234567":
            j = i + 1
            while j < min(i + 4, len(inner)) and inner[j] in "01234567":
                j += 1
            try:
                out.append(chr(int(inner[i + 1 : j], 8)))
            except ValueError:
                out.append(nxt)
            i = j
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


def _protect_multiline_data_args(text: str) -> tuple[str, dict[str, str]]:
    """把 --data-raw / --data 的多行内容换成占位符，避免 shlex 拆碎 multipart。"""
    bodies: dict[str, str] = {}

    def stash(raw: str) -> str:
        key = f"{_DATA_PLACEHOLDER_PREFIX}{len(bodies)}__"
        bodies[key] = raw
        return key

    text = re.sub(
        r"--data-raw\s+\$'((?:\\.|[^'\\])*)'",
        lambda m: f"--data-raw {stash(_unescape_bash_ansi_c(m.group(1)))}",
        text,
    )
    text = re.sub(
        r"--data(?:-raw|-binary|-ascii)?\s+'([^']*)'",
        lambda m: f"--data-raw {stash(m.group(1))}",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'--data(?:-raw|-binary|-ascii)?\s+"([^"]*)"',
        lambda m: f"--data-raw {stash(m.group(1))}",
        text,
        flags=re.DOTALL,
    )
    return text, bodies


def _normalize_curl_text(curl_command: str) -> tuple[str, dict[str, str]]:
    """合并续行、统一空白。"""
    text = curl_command.replace("\r\n", "\n").replace("\r", "\n")
    # bash 风格续行：反斜杠 + 换行
    text = re.sub(r"\\\s*\n", " ", text)
    text, body_map = _protect_multiline_data_args(text)
    text = _expand_bash_dollar_quotes(text)
    return text.strip(), body_map


def _expand_bash_dollar_quotes(text: str) -> str:
    """展开 bash $'\\r\\n' 等 ANSI-C 引号，便于 shlex 解析 --data-raw。"""

    def repl(m: re.Match[str]) -> str:
        return _unescape_bash_ansi_c(m.group(1))

    return re.sub(r"\$'((?:\\.|[^'\\])*)'", repl, text)


def _extract_multipart_boundary(content_type: str) -> Optional[str]:
    if not content_type:
        return None
    m = re.search(r"boundary=([^;\s]+)", content_type, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().strip('"')


def _empty_body_field(
    *,
    name: str,
    value: str = "",
    field_type: str = "text",
    file_name: str = "",
    mime_type: str = "application/octet-stream",
) -> dict:
    return {
        "name": name,
        "value": value,
        "field_type": field_type,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_key": "",
        "file_bucket": "",
        "description": "",
    }


def _multipart_delimiter(boundary: str) -> str:
    """multipart body 分隔线 = '--' + Content-Type 里的 boundary 参数值。"""
    return "--" + boundary.strip().strip('"')


def _parse_multipart_form_data(body: str, boundary: str) -> list[dict]:
    """解析 multipart/form-data 原始 body 为 form-data 字段列表。"""
    if not body or not boundary:
        return []
    delim = _multipart_delimiter(boundary)
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    chunks = normalized.split(delim)
    fields: list[dict] = []
    for chunk in chunks:
        if not chunk or chunk.strip("- \r\n") == "":
            continue
        part = chunk.lstrip("\r\n")
        if part.endswith("--"):
            part = part[:-2].rstrip("\r\n")
        if "\n\n" not in part:
            continue
        header_block, content = part.split("\n\n", 1)
        content = content.rstrip("\r\n")
        name: Optional[str] = None
        filename: Optional[str] = None
        mime_type = "application/octet-stream"
        for line in header_block.split("\n"):
            line = line.strip()
            low = line.lower()
            if low.startswith("content-disposition:"):
                nm = re.search(r'name="([^"]*)"', line, flags=re.IGNORECASE)
                fn = re.search(r'filename="([^"]*)"', line, flags=re.IGNORECASE)
                if nm:
                    name = nm.group(1)
                if fn:
                    filename = fn.group(1)
            elif low.startswith("content-type:"):
                mime_type = line.split(":", 1)[1].strip() or mime_type
        if not name:
            continue
        if filename is not None:
            fields.append(_empty_body_field(
                name=name,
                field_type="file",
                file_name=filename,
                mime_type=mime_type,
            ))
        else:
            fields.append(_empty_body_field(
                name=name,
                value=content,
                field_type="text",
                mime_type=mime_type,
            ))
    return fields


def _tokenize(curl_command: str) -> tuple[list[str], dict[str, str]]:
    text, body_map = _normalize_curl_text(curl_command)
    if not text:
        return [], body_map
    # Windows 粘贴可能用双引号包裹整段；优先 POSIX 风格（单引号常见于 Apifox）
    try:
        return shlex.split(text, posix=True), body_map
    except ValueError:
        # 未闭合引号等：退化为粗略按空白切分
        return text.split(), body_map


def _resolve_body_token(val: str, body_map: dict[str, str]) -> str:
    if val in body_map:
        return body_map[val]
    return val


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
        "body_fields": [],
    }

    tokens, body_map = _tokenize(curl_command)
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
                    body_parts.append(_resolve_body_token(val, body_map))
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
                body_parts.append(_resolve_body_token(val, body_map))
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

    body = "&".join(body_parts) if len(body_parts) > 1 else (body_parts[0] if body_parts else None)
    content_type = headers.get("Content-Type", "") or headers.get("content-type", "")
    ct_lower = content_type.lower()

    if body and "multipart/form-data" in ct_lower:
        boundary = _extract_multipart_boundary(content_type)
        fields = _parse_multipart_form_data(body, boundary or "")
        if fields:
            result["body_fields"] = fields
            result["body"] = {}
            result["body_type"] = "form-data"
            return result

    if body:
        try:
            json_body = json.loads(body)
            result["body"] = json_body
            result["body_type"] = "json"
        except json.JSONDecodeError:
            if "&" in body:
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

    if "application/json" in ct_lower and result["body_type"] != "form-data":
        result["body_type"] = "json"
    elif "application/x-www-form-urlencoded" in ct_lower:
        result["body_type"] = "x-www-form-urlencoded"
    elif "multipart/form-data" in ct_lower:
        result["body_type"] = "form-data"
        if not result["body_fields"] and body:
            boundary = _extract_multipart_boundary(content_type)
            fields = _parse_multipart_form_data(body, boundary or "")
            if fields:
                result["body_fields"] = fields
                result["body"] = {}
    elif "text/xml" in ct_lower or "application/xml" in ct_lower:
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
    body_fields = parsed.get("body_fields") or []

    return {
        "name": parsed["name"],
        "path": parsed["path"],
        "method": parsed["method"],
        "base_url": parsed["base_url"],
        "headers": headers,
        "params": params,
        "body": body,
        "body_type": parsed["body_type"],
        "body_fields": body_fields,
        "project_id": project_id,
        "description": f"从 curl 命令导入: {parsed['method']} {parsed['path']}",
    }
