"""接口自动化模块工具函数"""
import json
import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from app.core.case.variable_resolver import VariableResolver


_UNRESOLVED_VAR_RE = re.compile(r"\$\{\{([^}]+)\}\}|\$\{([^}]+)\}|\{\{([^}]+)\}\}")


def collect_unresolved_placeholders(data: Any, parent_key: str = "") -> List[Dict[str, str]]:
    """收集替换后仍残留的 ${{var}} / ${var} / {{var}} 占位符。"""
    found: List[Dict[str, str]] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, str):
            for match in _UNRESOLVED_VAR_RE.finditer(node):
                name = (match.group(1) or match.group(2) or match.group(3) or "").strip()
                found.append({
                    "path": path or "(root)",
                    "placeholder": match.group(0),
                    "name": name,
                })
            return
        if isinstance(node, dict):
            for k, v in node.items():
                child = f"{path}.{k}" if path else str(k)
                _walk(v, child)
            return
        if isinstance(node, list):
            for i, item in enumerate(node):
                child = f"{path}[{i}]" if path else f"[{i}]"
                _walk(item, child)

    _walk(data, parent_key)
    return found


def format_unresolved_variables_error(
    unresolved: List[Dict[str, str]],
    *,
    env_name: str = "",
    auth_injected_keys: Optional[List[str]] = None,
) -> str:
    """生成未解析变量的友好错误文案。"""
    if not unresolved:
        return ""
    names = []
    for item in unresolved:
        n = item.get("name") or ""
        if n and n not in names:
            names.append(n)
    samples = []
    for item in unresolved[:5]:
        samples.append(f"{item.get('path')}: {item.get('placeholder')}")
    name_text = "、".join(names[:8]) if names else "未知变量"
    lines = [
        f"存在未解析变量（{name_text}），已中止发送请求，避免带占位符请求下游。",
        "位置：" + "；".join(samples),
    ]
    tips = [
        "请确认执行环境与 Token 授权绑定的环境一致，且授权已启用、缓存有效",
        "Header/Body 中的 ${{变量名}} 须与授权「提取器变量名」一致（不是授权名称）",
        "不要把环境变量写成自引用，例如 cookie=${{cookie}}",
    ]
    if env_name:
        tips.insert(0, f"当前执行环境：{env_name}")
    if auth_injected_keys is not None:
        if auth_injected_keys:
            tips.append("本次已注入授权变量：" + "、".join(auth_injected_keys[:12]))
        else:
            tips.append("本次未注入任何 Token 授权变量（该环境可能未配置/未启用授权）")
    lines.append("建议：" + "；".join(tips) + "。")
    return "\n".join(lines)


def build_api_url(base_url: str, path: str, protocol: str = "http") -> str:
    """
    拼接基础URL和接口路径，处理斜杠边界和绝对路径
    - 如果 path 本身是绝对路径（含 http/https/ws/wss），直接返回 path
    - WebSocket 协议时自动将 http(s) 转为 ws(s)
    """
    if path and path.startswith(("http://", "https://", "ws://", "wss://")):
        url = path
    elif not base_url:
        raise ValueError("缺少基础URL，请配置接口基础URL或选择执行环境")
    else:
        base_url = base_url.rstrip("/")
        path = path if path.startswith("/") else "/" + path
        url = base_url + path

    if protocol == "websocket":
        from app.modules.http.ws_executor import ensure_ws_url
        return ensure_ws_url(url)
    if protocol == "grpc":
        host = url
        for prefix in ("grpc://", "grpcs://", "http://", "https://"):
            if host.startswith(prefix):
                host = host[len(prefix):]
                break
        return host.rstrip("/")
    return url


def replace_variables(data, variables, resolver: Optional[VariableResolver] = None):
    """递归替换数据中的变量引用
    
    支持格式: ${{var_name}}；内置动态变量 random_int / now_time / today 等；
    环境变量值支持 Faker 表达式（如 faker.random_int(min=100,max=100000)）及嵌套引用。
    """
    result, _ = replace_variables_with_detail(data, variables, resolver=resolver)
    return result


def replace_variables_with_detail(
    data,
    variables=None,
    parent_key="",
    resolver: Optional[VariableResolver] = None,
):
    """递归替换数据中的变量引用，并返回替换详情。"""
    details = []

    if resolver is None and variables:
        resolver = VariableResolver(variables)
    if resolver is None:
        return data, details

    if isinstance(data, str):
        original_data = data
        result = resolver.replace_in_string(data)

        if result != original_data:
            for match in re.finditer(r"\$\{\{([^}]+)\}\}|\$\{([^}]+)\}|\{\{([^}]+)\}\}", original_data):
                var_name = (match.group(1) or match.group(2) or match.group(3) or "").strip()
                if not var_name:
                    continue
                resolved = resolver.get(var_name)
                if resolved is not None:
                    details.append({
                        "key": var_name,
                        "original": match.group(0),
                        "replaced": str(resolved),
                        "path": parent_key,
                    })
        return result, details

    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            current_path = f"{parent_key}.{k}" if parent_key else k
            replaced_v, sub_details = replace_variables_with_detail(
                v, variables, current_path, resolver=resolver
            )
            result[k] = replaced_v
            details.extend(sub_details)
        return result, details

    if isinstance(data, list):
        result = []
        for i, item in enumerate(data):
            current_path = f"{parent_key}[{i}]"
            replaced_item, sub_details = replace_variables_with_detail(
                item, variables, current_path, resolver=resolver
            )
            result.append(replaced_item)
            details.extend(sub_details)
        return result, details

    return data, details


def prepare_httpx_headers(headers: Optional[Union[Dict[str, Any], httpx.Headers]]) -> httpx.Headers:
    """将请求头转为 httpx.Headers，支持中文等非 ASCII 字符（UTF-8 编码）。"""
    if not headers:
        return httpx.Headers(encoding="utf-8")
    if isinstance(headers, httpx.Headers):
        return headers
    cleaned: Dict[str, Any] = {}
    for key, value in headers.items():
        if not key or value is None:
            continue
        # h11 拒绝首尾空白；变量未替掉时也会更早被业务校验拦住
        cleaned[str(key)] = value.strip() if isinstance(value, str) else value
    return httpx.Headers(cleaned, encoding="utf-8")


def resolve_body_fields(case_fields: Optional[List], api_fields: Optional[List]) -> List[Dict[str, Any]]:
    """用例 form-data 字段优先；未配置时继承接口定义。"""
    if case_fields:
        return list(case_fields)
    return list(api_fields or [])


def replace_body_fields_with_detail(
    body_fields: List[Dict[str, Any]],
    variables: dict,
    resolver: Optional[VariableResolver] = None,
) -> Tuple[List[Dict[str, Any]], list]:
    """对 form-data 字段中的字符串属性做变量替换。"""
    if not body_fields:
        return [], []

    if resolver is None and variables:
        resolver = VariableResolver(variables)
    if resolver is None:
        return list(body_fields), []

    result = []
    details = []
    string_keys = ("name", "value", "file_name", "file_key", "file_bucket", "mime_type", "description")

    for i, field in enumerate(body_fields):
        if not isinstance(field, dict):
            result.append(field)
            continue
        new_field = dict(field)
        for key in string_keys:
            val = new_field.get(key)
            if isinstance(val, str) and val:
                replaced, sub_details = replace_variables_with_detail(
                    val, variables, f"body_fields[{i}].{key}", resolver=resolver
                )
                new_field[key] = replaced
                details.extend(sub_details)
        result.append(new_field)

    return result, details


def build_form_data_multipart(
    body_fields: List[Dict[str, Any]],
    default_bucket: Optional[str] = None,
    *,
    use_bytes_io: bool = True,
) -> List[tuple]:
    """
    根据 body_fields 构建 httpx multipart files 列表。

    Raises:
        ValueError: 文件字段缺少引用或 MinIO 读取失败
    """
    from app.core.platform.config import API_FILE_BUCKET
    from app.core.infra.minio_client import minio_client

    bucket_default = default_bucket or API_FILE_BUCKET
    multipart_data = []

    for field in body_fields or []:
        if not isinstance(field, dict):
            continue
        field_name = field.get("name")
        if not field_name:
            continue

        if field.get("field_type") == "file":
            file_key = field.get("file_key")
            file_bucket = field.get("file_bucket") or bucket_default
            if not file_key:
                raise ValueError(f"文件字段「{field_name}」缺少文件引用，请先上传文件")
            file_bytes = minio_client.download_object(file_key, file_bucket)
            if file_bytes is None:
                raise ValueError(f"无法从存储中读取文件字段「{field_name}」")
            file_name = field.get("file_name") or file_key.split("/")[-1]
            mime_type = field.get("mime_type") or "application/octet-stream"
            payload = BytesIO(file_bytes) if use_bytes_io else file_bytes
            multipart_data.append((field_name, (file_name, payload, mime_type)))
        else:
            multipart_data.append((field_name, (None, str(field.get("value") or ""))))

    return multipart_data


def assert_values_equal(actual, expected) -> bool:
    """断言值相等比较，兼容 UI 字符串与 JSON 解析后的 bool/number 类型差异。"""
    if actual == expected:
        return True
    if actual is None or expected is None:
        return actual is None and expected is None

    if isinstance(actual, bool) or isinstance(expected, bool):
        def to_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            if isinstance(value, str):
                s = value.strip().lower()
                if s in ("true", "1", "yes", "on"):
                    return True
                if s in ("false", "0", "no", "off"):
                    return False
            return None

        actual_bool = to_bool(actual)
        expected_bool = to_bool(expected)
        if actual_bool is not None and expected_bool is not None:
            return actual_bool == expected_bool

    try:
        if float(actual) == float(expected):
            return True
    except (TypeError, ValueError):
        pass

    return str(actual) == str(expected)


def evaluate_assertion(response, response_body, assertion):
    """执行断言
    
    Args:
        response: HTTP 响应对象
        response_body: 解析后的响应体
        assertion: 断言配置
        
    Returns:
        (passed, actual_value): 是否通过断言，实际值
    """
    assertion_type = assertion.get("type")
    target = assertion.get("target")
    operator = assertion.get("operator")
    expected = assertion.get("expected")
    
    if assertion_type == "status_code":
        actual = response.status_code
    elif assertion_type == "json_path":
        actual = get_json_path_value(response_body, target)
    elif assertion_type == "header":
        # 与变量提取一致：Header 名大小写不敏感
        headers = response.headers
        if isinstance(headers, list):
            headers = {h.get("key", ""): h.get("value", "") for h in headers if h.get("key")}
        elif headers is not None and not isinstance(headers, dict):
            try:
                headers = dict(headers)
            except Exception:
                headers = {}
        actual = _header_lookup(_headers_to_dict(headers), target) if headers else None
    elif assertion_type == "contains":
        actual = json.dumps(response_body, ensure_ascii=False) if isinstance(response_body, dict) else str(response_body)
        expected = str(expected)
        return expected in actual, actual
    elif assertion_type == "not_contains":
        actual = json.dumps(response_body, ensure_ascii=False) if isinstance(response_body, dict) else str(response_body)
        expected = str(expected)
        return expected not in actual, actual
    else:
        return False, None
    
    if operator == "equals":
        return assert_values_equal(actual, expected), actual
    elif operator == "not_equals":
        return not assert_values_equal(actual, expected), actual
    elif operator == "contains":
        return str(expected) in str(actual), actual
    elif operator == "not_contains":
        return str(expected) not in str(actual), actual
    elif operator == "gt":
        try:
            return float(actual) > float(expected), actual
        except:
            return False, actual
    elif operator == "lt":
        try:
            return float(actual) < float(expected), actual
        except:
            return False, actual
    elif operator == "gte":
        try:
            return float(actual) >= float(expected), actual
        except:
            return False, actual
    elif operator == "lte":
        try:
            return float(actual) <= float(expected), actual
        except:
            return False, actual
    elif operator == "in":
        return actual in expected if isinstance(expected, (list, tuple, set, dict)) else str(actual) in str(expected), actual
    elif operator == "not_in":
        return actual not in expected if isinstance(expected, (list, tuple, set, dict)) else str(actual) not in str(expected), actual
    elif operator == "regex":
        try:
            import re
            return bool(re.search(str(expected), str(actual))), actual
        except:
            return False, actual
    
    return False, actual


def evaluate_condition(response, response_body, condition: dict) -> bool:
    """判断条件表达式是否成立（结构与断言规则相同）"""
    if not condition:
        return False
    passed, _ = evaluate_assertion(response, response_body, condition)
    return passed


def run_case_assertions(response, response_body, case) -> tuple:
    """执行用例断言（支持 flat assertions 与 assertion_groups 条件分支）

    Returns:
        (all_passed, results_list, matched_group_name)
        results_list: list of dicts with type/target/operator/expected/actual/passed/group_name
    """
    groups = getattr(case, "assertion_groups", None)
    if groups is None and isinstance(case, dict):
        groups = case.get("assertion_groups") or []
    else:
        groups = groups or []

    if groups:
        return _evaluate_assertion_groups(response, response_body, groups)

    assertions = getattr(case, "assertions", None)
    if assertions is None and isinstance(case, dict):
        assertions = case.get("assertions") or []
    else:
        assertions = assertions or []

    results = []
    all_passed = True
    for assertion in assertions:
        passed, actual = evaluate_assertion(response, response_body, assertion)
        results.append({
            "type": assertion.get("type"),
            "target": assertion.get("target"),
            "operator": assertion.get("operator"),
            "expected": assertion.get("expected"),
            "actual": actual,
            "passed": passed,
            "group_name": None,
            "description": assertion.get("description"),
        })
        if not passed:
            all_passed = False
    return all_passed, results, None


def _evaluate_assertion_groups(response, response_body, groups: list) -> tuple:
    """按顺序匹配条件分支，命中一组后仅执行该组断言"""
    matched_any = False
    for group in groups:
        if not isinstance(group, dict):
            continue
        is_else = bool(group.get("is_else"))
        condition = group.get("condition")

        if is_else:
            if matched_any:
                continue
        elif condition:
            if not evaluate_condition(response, response_body, condition):
                continue
            matched_any = True
        else:
            matched_any = True

        group_name = group.get("name") or ("Else" if is_else else "默认分支")
        results = []
        all_passed = True
        for assertion in group.get("assertions") or []:
            passed, actual = evaluate_assertion(response, response_body, assertion)
            results.append({
                "type": assertion.get("type"),
                "target": assertion.get("target"),
                "operator": assertion.get("operator"),
                "expected": assertion.get("expected"),
                "actual": actual,
                "passed": passed,
                "group_name": group_name,
                "description": assertion.get("description"),
            })
            if not passed:
                all_passed = False
        return all_passed, results, group_name

    return True, [], None


def get_json_path_value(data, path):
    """获取 JSON Path 值 (基于 jsonpath-ng，支持 $.a.b、$..name、$[?(@.id==1)] 等)
    
    Args:
        data: JSON 数据
        path: JSON Path 表达式
        
    Returns:
        路径对应的值。单条匹配返回单个值，多条匹配返回列表，不存在返回 None
    """
    if not path:
        return data
    
    try:
        from jsonpath_ng.ext import parse
        jsonpath_expr = parse(path)
        matches = jsonpath_expr.find(data)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0].value
        return [m.value for m in matches]
    except Exception:
        # 回退到简化版逻辑（兼容旧格式 $.a.b 及纯点号路径）
        if path.startswith("$."):
            path = path[2:]
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                idx = int(key)
                if idx < len(value):
                    value = value[idx]
                else:
                    return None
            else:
                return None
        return value


def validate_response_schema(response_body, schema):
    """基于 JSON Schema 自动校验响应体，返回断言结果列表
    
    Args:
        response_body: 实际响应体
        schema: JSON Schema 对象
        
    Returns:
        list[dict]: 断言结果列表
    """
    results = []
    if not schema or not isinstance(schema, dict):
        return results
    
    try:
        from jsonschema import Draft7Validator
        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(response_body))
        if not errors:
            results.append({
                "type": "schema",
                "target": "",
                "operator": "equals",
                "expected": "响应结构符合 Schema",
                "actual": "响应结构符合 Schema",
                "passed": True,
                "description": "JSON Schema 自动校验通过"
            })
        else:
            for error in errors[:5]:  # 最多报5条
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                results.append({
                    "type": "schema",
                    "target": path,
                    "operator": "equals",
                    "expected": "符合 Schema 定义",
                    "actual": error.message,
                    "passed": False,
                    "description": f"Schema 校验: {error.message}"
                })
    except Exception as e:
        results.append({
            "type": "schema",
            "target": "",
            "operator": "equals",
            "expected": "响应结构符合 Schema",
            "actual": f"校验异常: {str(e)}",
            "passed": False,
            "description": "JSON Schema 校验异常"
        })
    
    return results


def normalize_extractor(extractor: dict) -> dict:
    """统一提取器字段（兼容 property / type+expression 等历史格式）。"""
    if not isinstance(extractor, dict):
        return {}
    source = extractor.get("source") or extractor.get("type") or "json"
    if source in ("json_path", "jsonpath"):
        source = "json"
    path = (
        extractor.get("path")
        or extractor.get("property")
        or extractor.get("expression")
        or ""
    )
    return {
        "name": extractor.get("name", ""),
        "source": source,
        "path": str(path).strip() if path is not None else "",
        "description": extractor.get("description", ""),
    }


def _headers_to_dict(headers) -> Dict[str, str]:
    if not headers:
        return {}
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    try:
        return {str(k): str(v) for k, v in dict(headers).items()}
    except Exception:
        return {}


def _header_lookup(headers: Dict[str, str], name: str) -> Optional[str]:
    if not headers or not name:
        return None
    if name in headers:
        return headers[name]
    name_lower = name.lower()
    for key, value in headers.items():
        if key.lower() == name_lower:
            return value
    return None


def extract_value(response_body, extractor, headers=None):
    """从响应中提取变量值

    Args:
        response_body: 解析后的响应体
        extractor: 提取器配置
        headers: 响应头（source=header 时必填）

    Returns:
        提取的值，失败返回 None
    """
    ext = normalize_extractor(extractor)
    source = ext.get("source", "json")
    path = ext.get("path")

    if source == "json":
        return get_json_path_value(response_body, path)
    if source == "header":
        return _header_lookup(_headers_to_dict(headers), path)
    if source == "regex" and path:
        text = (
            json.dumps(response_body, ensure_ascii=False)
            if isinstance(response_body, (dict, list))
            else str(response_body or "")
        )
        try:
            match = re.search(path, text)
            if match:
                return match.group(1) if match.groups() else match.group(0)
        except re.error:
            return None
    return None


def _extract_failure_reason(ext: dict, response_body, headers) -> str:
    source = ext.get("source", "json")
    path = ext.get("path", "")
    if not ext.get("name"):
        return "变量名为空"
    if not path:
        return "提取路径为空"
    if source == "header":
        if not headers:
            return "响应头为空"
        return f"Header「{path}」未找到"
    if source == "regex":
        return f"正则「{path}」未匹配"
    return f"JSONPath「{path}」未匹配"


def extract_variables(response_body, extractors, headers=None):
    """批量提取变量，返回 (extracted_vars, extractor_results)。"""
    extracted: Dict[str, Any] = {}
    results: List[Dict[str, Any]] = []
    for raw in extractors or []:
        ext = normalize_extractor(raw)
        name = ext.get("name", "")
        value = extract_value(response_body, ext, headers=headers) if name else None
        success = value is not None
        results.append({
            "name": name,
            "source": ext.get("source", "json"),
            "path": ext.get("path", ""),
            "success": success,
            "value": value if success else None,
            "error": None if success else _extract_failure_reason(ext, response_body, headers),
        })
        if name and success:
            extracted[name] = value
    return extracted, results


def api_run_result_to_case_display(result: Any) -> Dict[str, Any]:
    """将 ApiRunResult 转为报告/CaseResultItem 可用的结构（补齐 response_body 等字段）"""
    if hasattr(result, "model_dump"):
        d = result.model_dump()
    elif isinstance(result, dict):
        d = dict(result)
    else:
        return {}

    response_detail = d.get("response_detail") or {}
    if d.get("response_body") is None and response_detail:
        d["response_body"] = response_detail.get("body")
    if d.get("response_headers") is None and response_detail:
        d["response_headers"] = response_detail.get("headers")
    if not d.get("retry_info"):
        request_detail = d.get("request_detail")
        if isinstance(request_detail, dict) and request_detail.get("retry_info"):
            d["retry_info"] = request_detail["retry_info"]
    if d.get("http_response_time") is None:
        from app.modules.http.api_report_export import resolve_http_response_time
        resolved = resolve_http_response_time(d)
        if resolved is not None:
            d["http_response_time"] = resolved
    return d


def normalize_plan_item_results(item_results: list) -> list:
    """规范化计划 item_results，补齐 http_response_time 等展示字段"""
    if not item_results:
        return []
    if not isinstance(item_results, list):
        return []
    normalized = []
    for item in item_results:
        if not isinstance(item, dict):
            continue
        item_copy = dict(item)
        case_rows = []
        for cr in (item.get("case_results") or []):
            try:
                case_rows.append(api_run_result_to_case_display(cr))
            except Exception:
                if isinstance(cr, dict):
                    case_rows.append(cr)
        item_copy["case_results"] = case_rows
        normalized.append(item_copy)
    return normalized
