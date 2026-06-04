"""
Curl 命令解析器
支持解析标准 curl 命令，提取接口信息
"""
import re
import json
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Optional, Any


def parse_curl(curl_command: str) -> Dict[str, Any]:
    """
    解析 curl 命令，返回接口信息
    
    支持的 curl 选项：
    - -X, --request: HTTP 方法
    - -H, --header: 请求头
    - -d, --data: 请求体数据
    - --data-raw: 原始请求体数据
    - -u, --user: 用户名密码
    - -L, --location: 跟随重定向
    - --url: URL
    
    Returns:
        {
            "name": str,           # 接口名称（从路径生成）
            "method": str,         # HTTP 方法
            "path": str,          # 接口路径
            "base_url": str,      # 基础 URL
            "headers": dict,      # 请求头
            "params": list,       # 查询参数
            "body": any,          # 请求体
            "body_type": str      # 请求体类型 (json/form/none)
        }
    """
    result = {
        "name": "",
        "method": "GET",
        "path": "",
        "base_url": "",
        "headers": {},
        "params": [],
        "body": None,
        "body_type": "none"
    }
    
    # 清理命令，处理换行和多余空格
    curl_command = curl_command.replace('\\\n', ' ').replace('\\r\\n', ' ')
    curl_command = re.sub(r'\s+', ' ', curl_command).strip()
    
    # 提取 URL
    url_patterns = [
        r'--url\s+["\']?([^"\'\s]+)["\']?',
        r'curl\s+["\']?([^"\'\s-][^"\'\s]*)["\']?',
        r'-X\s+\w+\s+["\']?([^"\'\s]+)["\']?',
    ]
    
    url = ""
    for pattern in url_patterns:
        match = re.search(pattern, curl_command, re.IGNORECASE)
        if match:
            url = match.group(1).strip('"\'')
            break
    
    if not url:
        raise ValueError("无法从 curl 命令中提取 URL")
    
    # 解析 URL
    parsed_url = urlparse(url)
    result["base_url"] = f"{parsed_url.scheme}://{parsed_url.netloc}"
    result["path"] = parsed_url.path or "/"
    
    # 从路径生成接口名称
    path_parts = [p for p in result["path"].split("/") if p]
    if path_parts:
        result["name"] = path_parts[-1].replace("-", "_").replace(".", "_")
    else:
        result["name"] = "api"
    
    # 解析查询参数
    if parsed_url.query:
        query_params = parse_qs(parsed_url.query)
        for key, values in query_params.items():
            result["params"].append({
                "name": key,
                "value": values[0] if values else "",
                "type": "string",
                "description": ""
            })
    
    # 提取 HTTP 方法（支持带引号和不带引号）
    method_match = re.search(r'-(?:X|request)\s+["\']?([A-Z]+)["\']?', curl_command, re.IGNORECASE)
    if method_match:
        result["method"] = method_match.group(1).upper()
    elif re.search(r'-(?:d|data|data-raw)\s+', curl_command, re.IGNORECASE):
        # 如果有 data 但没有指定方法，默认是 POST
        result["method"] = "POST"
    
    # 提取 Headers
    header_pattern = r'-(?:H|header)\s+["\']?([^"\']+)["\']?'
    headers = re.findall(header_pattern, curl_command, re.IGNORECASE)
    for header in headers:
        if ':' in header:
            key, value = header.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                result["headers"][key] = value
    
    # 提取 Body
    body_patterns = [
        r'-(?:d|data|data-raw)\s+[\'"]([\s\S]*?)[\'"]\s*(?:-|$)',
        r'-(?:d|data|data-raw)\s+([^\s-][^\s]*)',
    ]
    
    body = None
    for pattern in body_patterns:
        match = re.search(pattern, curl_command, re.IGNORECASE)
        if match:
            body = match.group(1).strip('"\'')
            break
    
    if body:
        # 尝试解析为 JSON
        try:
            json_body = json.loads(body)
            result["body"] = json_body
            result["body_type"] = "json"
        except json.JSONDecodeError:
            # 尝试解析为 x-www-form-urlencoded
            if '&' in body or '=' in body:
                form_data = {}
                pairs = body.split('&')
                for pair in pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        form_data[key] = value
                result["body"] = form_data
                result["body_type"] = "x-www-form-urlencoded"
            else:
                result["body"] = body
                result["body_type"] = "raw"
    
    # 根据 Content-Type 推断 body_type（优先级高于内容推断）
    content_type = result["headers"].get("Content-Type", "")
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
    
    Args:
        curl_command: curl 命令字符串
        project_id: 项目ID
        
    Returns:
        符合 ApiDefinitionCreate 格式的字典
    """
    parsed = parse_curl(curl_command)
    
    # 构建请求头列表
    headers = []
    for key, value in parsed["headers"].items():
        headers.append({
            "key": key,
            "value": value,
            "description": ""
        })
    
    # 构建请求参数
    params = []
    for param in parsed["params"]:
        params.append({
            "name": param["name"],
            "value": param["value"],
            "type": "string",
            "description": ""
        })
    
    # 构建 body
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
        "description": f"从 curl 命令导入: {parsed['method']} {parsed['path']}"
    }
