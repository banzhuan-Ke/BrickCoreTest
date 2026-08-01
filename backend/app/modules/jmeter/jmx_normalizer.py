"""Normalize JMeter hashTree into a serializable intermediate representation (IR)."""
from __future__ import annotations

from typing import Any, Optional
from xml.etree.ElementTree import Element

from app.modules.jmeter.jmx_parser import _local_tag, parse_jmx_bytes

# Elements we convert or walk through
SUPPORTED_CONTAINERS = {
    "TestPlan",
    "ThreadGroup",
    "SetupThreadGroup",
    "PostThreadGroup",
    "GenericController",  # Simple Controller
    "hashTree",
}

HTTP_SAMPLER_TAGS = {"HTTPSamplerProxy", "HTTPSampler"}
HEADER_MANAGER_TAG = "HeaderManager"
HTTP_DEFAULTS_TAG = "ConfigTestElement"
JSON_EXTRACTOR_TAGS = {"JSONPostProcessor", "JSONPathExtractor"}
RESPONSE_ASSERTION_TAG = "ResponseAssertion"
CSV_DATASET_TAG = "CSVDataSet"
REGEX_EXTRACTOR_TAG = "RegexExtractor"

# Controllers / scripts that must warn, not convert
UNSUPPORTED_REASON = {
    "IfController": "条件控制器不自动转换",
    "WhileController": "循环控制器不自动转换",
    "ForeachController": "ForEach 控制器不自动转换",
    "ForEachController": "ForEach 控制器不自动转换",
    "LoopController": "独立 LoopController 不自动转换（Thread Group 循环除外）",
    "RuntimeController": "Runtime 控制器不自动转换",
    "ThroughputController": "Throughput 控制器不自动转换",
    "InterleaveControl": "Interleave 控制器不自动转换",
    "SwitchController": "Switch 控制器不自动转换",
    "TransactionController": "Transaction 控制器仅保留子 HTTP 请求顺序",
    "JSR223Sampler": "JSR223 脚本不执行、不转换",
    "JSR223PreProcessor": "JSR223 前置脚本不转换",
    "JSR223PostProcessor": "JSR223 后置脚本不转换",
    "BeanShellSampler": "BeanShell 脚本不转换",
    "BeanShellPreProcessor": "BeanShell 脚本不转换",
    "BeanShellPostProcessor": "BeanShell 脚本不转换",
    "JavaScript": "JavaScript 脚本不转换",
    "JDBCSampler": "非 HTTP 采样器不转换",
    "JDBCDataSet": "JDBC 不转换",
    "TCPSampler": "非 HTTP 采样器不转换",
    "FTPSampler": "非 HTTP 采样器不转换",
    "GraphQLHTTPSampler": "GraphQL 采样器暂不转换",
    "CookieManager": "Cookie 管理器运行时语义不还原",
    "CacheManager": "缓存管理器不转换",
    "DNSCacheManager": "DNS 管理器不转换",
    "ConstantTimer": "定时器不转换（可在平台用例间隔另行配置）",
    "UniformRandomTimer": "定时器不转换",
    "GaussianRandomTimer": "定时器不转换",
    "ResultCollector": "Listener 不导入",
    "Summariser": "Listener 不导入",
    "BackendListener": "Listener 不导入",
}


def normalize_jmx(content: bytes) -> dict[str, Any]:
    """Parse bytes and return IR dict."""
    root = parse_jmx_bytes(content)
    return normalize_root(root)


def normalize_root(root: Element) -> dict[str, Any]:
    plan_name = "JMeter Import"
    thread_groups: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    global_warnings: list[str] = []

    # Root is typically jmeterTestPlan > hashTree > TestPlan + hashTree
    children = _paired_children(root) if _local_tag(root.tag) == "jmeterTestPlan" else _as_pairs_from_hash(root)

    for el, subtree in children:
        tag = _local_tag(el.tag)
        if tag == "TestPlan":
            plan_name = el.attrib.get("testname") or plan_name
            # TestPlan children: thread groups, defaults, etc.
            tg_list, uns, warns = _walk_plan_hash(subtree, path=f"/{plan_name}")
            thread_groups.extend(tg_list)
            unsupported.extend(uns)
            global_warnings.extend(warns)
        elif tag == "hashTree":
            continue
        else:
            # Unusual top-level — walk sibling hashTree if present
            if subtree is not None:
                tg_list, uns, warns = _walk_plan_hash(subtree, path="/")
                thread_groups.extend(tg_list)
                unsupported.extend(uns)
                global_warnings.extend(warns)

    if not thread_groups and not unsupported:
        # Fallback: treat entire tree as plan content
        pairs = _paired_children(root)
        for el, subtree in pairs:
            if _local_tag(el.tag) == "TestPlan":
                plan_name = el.attrib.get("testname") or plan_name
                tg_list, uns, warns = _walk_plan_hash(subtree, path=f"/{plan_name}")
                thread_groups.extend(tg_list)
                unsupported.extend(uns)
                global_warnings.extend(warns)

    return {
        "test_plan_name": plan_name,
        "thread_groups": thread_groups,
        "unsupported_nodes": unsupported,
        "warnings": global_warnings,
    }


def _as_pairs_from_hash(root: Element) -> list[tuple[Element, Optional[Element]]]:
    return _paired_children(root)


def _paired_children(parent: Optional[Element]) -> list[tuple[Element, Optional[Element]]]:
    """JMeter hashTree children alternate: element, then its child hashTree."""
    if parent is None:
        return []
    kids = list(parent)
    pairs: list[tuple[Element, Optional[Element]]] = []
    i = 0
    while i < len(kids):
        el = kids[i]
        subtree = None
        if i + 1 < len(kids) and _local_tag(kids[i + 1].tag) == "hashTree":
            subtree = kids[i + 1]
            i += 2
        else:
            i += 1
        if _local_tag(el.tag) == "hashTree":
            # nested bare hashTree — flatten one level
            pairs.extend(_paired_children(el))
            continue
        pairs.append((el, subtree))
    return pairs


def _walk_plan_hash(
    subtree: Optional[Element],
    path: str,
    inherited_headers: Optional[dict[str, str]] = None,
    inherited_defaults: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    thread_groups: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    warnings: list[str] = []
    headers = dict(inherited_headers or {})
    defaults = dict(inherited_defaults or {})

    for el, child_tree in _paired_children(subtree):
        tag = _local_tag(el.tag)
        name = el.attrib.get("testname") or tag
        node_path = f"{path}/{name}"

        if tag in ("ThreadGroup", "SetupThreadGroup", "PostThreadGroup"):
            tg, uns, warns = _normalize_thread_group(el, child_tree, node_path, headers, defaults)
            thread_groups.append(tg)
            unsupported.extend(uns)
            warnings.extend(warns)
        elif tag == HEADER_MANAGER_TAG:
            headers = {**headers, **_parse_header_manager(el)}
        elif tag == HTTP_DEFAULTS_TAG and _is_http_defaults(el):
            defaults = {**defaults, **_parse_http_defaults(el)}
        elif tag == CSV_DATASET_TAG:
            unsupported.append(_unsupported(node_path, tag, "CSV Data Set 仅记录引用，需用户另行上传绑定"))
            warnings.append(f"{node_path}: CSV 需另行上传")
        elif tag in HTTP_SAMPLER_TAGS:
            # Sampler at plan level — wrap into synthetic group
            sampler, uns = _normalize_sampler(el, child_tree, node_path, headers, defaults, name_prefix="")
            unsupported.extend(uns)
            thread_groups.append(
                {
                    "name": "默认套件",
                    "threads": None,
                    "ramp_up_seconds": None,
                    "duration_seconds": None,
                    "loop_count": None,
                    "samplers": [sampler],
                    "warnings": [],
                }
            )
        elif tag == "GenericController":
            # Simple controller at plan level — walk children
            tg_list, uns, warns = _walk_plan_hash(child_tree, node_path, headers, defaults)
            thread_groups.extend(tg_list)
            unsupported.extend(uns)
            warnings.extend(warns)
        elif tag == "TransactionController":
            tg_list, uns, warns = _walk_plan_hash(child_tree, node_path, headers, defaults)
            thread_groups.extend(tg_list)
            unsupported.extend(uns)
            warnings.append(f"{node_path}: Transaction 控制器仅保留子请求顺序")
        elif tag in UNSUPPORTED_REASON:
            unsupported.append(_unsupported(node_path, tag, UNSUPPORTED_REASON[tag]))
            # Still walk children for HTTP parts under some controllers
            if child_tree is not None and tag in (
                "IfController",
                "WhileController",
                "ForeachController",
                "ForEachController",
                "ThroughputController",
                "InterleaveControl",
                "SwitchController",
                "RuntimeController",
                "TransactionController",
            ):
                tg_list, uns, warns = _walk_plan_hash(child_tree, node_path, headers, defaults)
                thread_groups.extend(tg_list)
                unsupported.extend(uns)
                warnings.extend(warns)
        elif tag in ("TestFragmentController", "ModuleController", "IncludeController"):
            unsupported.append(_unsupported(node_path, tag, "模块/片段控制器不自动展开"))
        elif tag.startswith("kg.") or "Plugin" in tag:
            unsupported.append(_unsupported(node_path, tag, "第三方插件不转换"))
        else:
            # Unknown config / listener etc.
            if tag not in ("Arguments", "elementProp", "stringProp", "boolProp", "intProp", "longProp", "collectionProp"):
                if el.attrib.get("testclass") or el.attrib.get("guiclass"):
                    unsupported.append(_unsupported(node_path, tag, "未识别节点，已跳过"))

    return thread_groups, unsupported, warnings


def _normalize_thread_group(
    el: Element,
    subtree: Optional[Element],
    path: str,
    inherited_headers: dict[str, str],
    inherited_defaults: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    name = el.attrib.get("testname") or "Thread Group"
    threads = _int_prop(el, "ThreadGroup.num_threads")
    ramp = _int_prop(el, "ThreadGroup.ramp_time")
    # loop: -1 forever; nested LoopController stringProp
    loop_count = None
    duration = None
    scheduler = _bool_prop(el, "ThreadGroup.scheduler")
    if scheduler:
        duration = _int_prop(el, "ThreadGroup.duration")
    # Loop from main controller child
    for child in list(el):
        if _local_tag(child.tag) == "elementProp" and child.attrib.get("name") == "ThreadGroup.main_controller":
            loops = _string_prop(child, "LoopController.loops")
            if loops is not None and str(loops).strip() not in ("", "-1"):
                try:
                    loop_count = int(str(loops).strip())
                except ValueError:
                    pass

    samplers: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    warnings: list[str] = []
    headers = dict(inherited_headers)
    defaults = dict(inherited_defaults)

    _collect_under_controller(
        subtree,
        path,
        headers,
        defaults,
        samplers,
        unsupported,
        warnings,
        name_prefix="",
    )

    tg = {
        "name": name,
        "source_path": path,
        "threads": threads,
        "ramp_up_seconds": ramp,
        "duration_seconds": duration,
        "loop_count": loop_count,
        "samplers": samplers,
        "warnings": warnings,
    }
    return tg, unsupported, warnings


def _collect_under_controller(
    subtree: Optional[Element],
    path: str,
    headers: dict[str, str],
    defaults: dict[str, Any],
    samplers: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
    warnings: list[str],
    name_prefix: str,
) -> None:
    """Mutates headers/defaults as scope configs appear; collects samplers in order."""
    local_headers = dict(headers)
    local_defaults = dict(defaults)

    for el, child_tree in _paired_children(subtree):
        tag = _local_tag(el.tag)
        name = el.attrib.get("testname") or tag
        node_path = f"{path}/{name}"

        if tag == HEADER_MANAGER_TAG:
            local_headers = {**local_headers, **_parse_header_manager(el)}
        elif tag == HTTP_DEFAULTS_TAG and _is_http_defaults(el):
            local_defaults = {**local_defaults, **_parse_http_defaults(el)}
        elif tag in HTTP_SAMPLER_TAGS:
            sampler, uns = _normalize_sampler(
                el, child_tree, node_path, local_headers, local_defaults, name_prefix
            )
            samplers.append(sampler)
            unsupported.extend(uns)
        elif tag == "GenericController":
            prefix = f"{name_prefix}{name}/" if name else name_prefix
            _collect_under_controller(
                child_tree, node_path, local_headers, local_defaults, samplers, unsupported, warnings, prefix
            )
        elif tag == "TransactionController":
            warnings.append(f"{node_path}: Transaction 控制器仅保留子请求顺序")
            _collect_under_controller(
                child_tree, node_path, local_headers, local_defaults, samplers, unsupported, warnings, name_prefix
            )
        elif tag == CSV_DATASET_TAG:
            filename = _string_prop(el, "filename") or ""
            varnames = _string_prop(el, "variableNames") or ""
            unsupported.append(
                _unsupported(
                    node_path,
                    tag,
                    f"CSV 不读取本地路径；变量名={varnames or '?'} 文件引用={filename or '?'}",
                )
            )
            warnings.append(f"{node_path}: 需另行上传并绑定 CSV")
        elif tag in UNSUPPORTED_REASON:
            unsupported.append(_unsupported(node_path, tag, UNSUPPORTED_REASON[tag]))
            if child_tree is not None and tag in (
                "IfController",
                "WhileController",
                "ForeachController",
                "ForEachController",
                "ThroughputController",
                "InterleaveControl",
                "SwitchController",
                "RuntimeController",
            ):
                warnings.append(f"{node_path}: 已跳过控制器逻辑，仍尝试收集子 HTTP 请求")
                _collect_under_controller(
                    child_tree, node_path, local_headers, local_defaults, samplers, unsupported, warnings, name_prefix
                )
        elif tag in ("Arguments",) or tag.endswith("Prop"):
            continue
        elif el.attrib.get("testclass") or el.attrib.get("guiclass"):
            # Nested samplers under unknown — try recurse for HTTP
            if child_tree is not None and tag not in ("ResultCollector",):
                if tag in JSON_EXTRACTOR_TAGS or tag == RESPONSE_ASSERTION_TAG or tag == REGEX_EXTRACTOR_TAG:
                    # Should be under sampler hashTree, not here
                    unsupported.append(_unsupported(node_path, tag, "提取器/断言应挂在 HTTP 请求下"))
                else:
                    unsupported.append(_unsupported(node_path, tag, UNSUPPORTED_REASON.get(tag, "未识别节点，已跳过")))
                    if child_tree is not None:
                        _collect_under_controller(
                            child_tree,
                            node_path,
                            local_headers,
                            local_defaults,
                            samplers,
                            unsupported,
                            warnings,
                            name_prefix,
                        )


def _normalize_sampler(
    el: Element,
    subtree: Optional[Element],
    path: str,
    headers: dict[str, str],
    defaults: dict[str, Any],
    name_prefix: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    unsupported: list[dict[str, Any]] = []
    warnings: list[str] = []
    name = el.attrib.get("testname") or "HTTP Request"
    if name_prefix:
        name = f"{name_prefix}{name}"

    method = (_string_prop(el, "HTTPSampler.method") or defaults.get("method") or "GET").upper()
    domain = _string_prop(el, "HTTPSampler.domain") or defaults.get("domain") or ""
    protocol = _string_prop(el, "HTTPSampler.protocol") or defaults.get("protocol") or ""
    port = _string_prop(el, "HTTPSampler.port") or defaults.get("port") or ""
    raw_path = _string_prop(el, "HTTPSampler.path") or defaults.get("path") or "/"
    path_str, query_params = _split_path_query(raw_path)
    content_encoding = _string_prop(el, "HTTPSampler.contentEncoding")

    # Arguments (query or body form)
    args = _parse_arguments(el)
    body_raw = _string_prop(el, "Argument.value")  # uncommon at top
    post_body_raw = None
    # HTTPSampler.POST_BODY_RAW
    use_raw = _bool_prop(el, "HTTPSampler.postBodyRaw")
    if use_raw or _has_raw_body(el):
        post_body_raw = _extract_raw_body(el)

    body: Any = None
    body_type = "none"
    params = list(query_params)

    if post_body_raw is not None:
        body = post_body_raw
        body_type = _guess_body_type(post_body_raw, headers)
        try:
            import json

            body = json.loads(post_body_raw)
            body_type = "json"
        except Exception:
            body = post_body_raw
            if body_type == "none":
                body_type = "raw"
    elif args:
        # If GET → params; if POST without raw → form
        if method in ("GET", "DELETE", "HEAD"):
            for a in args:
                params.append({"name": a["name"], "value": a["value"], "type": "string", "required": False})
        else:
            body_type = "form"
            body = {a["name"]: a["value"] for a in args if a.get("name")}

    base_url = None
    if protocol and domain:
        base_url = f"{protocol}://{domain}"
        if port and str(port) not in ("80", "443", ""):
            base_url = f"{base_url}:{port}"
    elif domain:
        base_url = domain

    timeout_ms = _string_prop(el, "HTTPSampler.connect_timeout") or _string_prop(el, "HTTPSampler.response_timeout")
    timeout_sec = 30
    if timeout_ms:
        try:
            timeout_sec = max(1, int(float(timeout_ms) / 1000))
        except ValueError:
            pass

    merged_headers = dict(headers)
    if content_encoding and "Content-Type" not in {k.lower(): k for k in merged_headers}:
        pass

    assertions: list[dict[str, Any]] = []
    extractors: list[dict[str, Any]] = []

    # Children under sampler: HeaderManager, assertions, extractors
    for child_el, _child_tree in _paired_children(subtree):
        ctag = _local_tag(child_el.tag)
        cname = child_el.attrib.get("testname") or ctag
        cpath = f"{path}/{cname}"
        if ctag == HEADER_MANAGER_TAG:
            merged_headers = {**merged_headers, **_parse_header_manager(child_el)}
        elif ctag == RESPONSE_ASSERTION_TAG:
            mapped, warn = _map_response_assertion(child_el)
            assertions.extend(mapped)
            if warn:
                warnings.append(f"{cpath}: {warn}")
                if not mapped:
                    unsupported.append(_unsupported(cpath, ctag, warn))
        elif ctag in JSON_EXTRACTOR_TAGS:
            ext, warn = _map_json_extractor(child_el)
            if ext:
                extractors.append(ext)
            if warn:
                warnings.append(f"{cpath}: {warn}")
                if not ext:
                    unsupported.append(_unsupported(cpath, ctag, warn))
        elif ctag == REGEX_EXTRACTOR_TAG:
            unsupported.append(_unsupported(cpath, ctag, "正则提取器暂不自动转换"))
            warnings.append(f"{cpath}: 正则提取器未转换")
        elif ctag in UNSUPPORTED_REASON:
            unsupported.append(_unsupported(cpath, ctag, UNSUPPORTED_REASON[ctag]))
            warnings.append(f"{cpath}: {UNSUPPORTED_REASON[ctag]}")
        elif ctag == CSV_DATASET_TAG:
            unsupported.append(_unsupported(cpath, ctag, "CSV 需另行上传绑定"))
        elif child_el.attrib.get("testclass"):
            unsupported.append(_unsupported(cpath, ctag, "采样器子节点未转换"))

    sampler = {
        "source_path": path,
        "name": name[:100],
        "method": method,
        "path": path_str if path_str.startswith("/") else f"/{path_str}",
        "base_url": base_url,
        "headers": merged_headers,
        "params": params,
        "body": body,
        "body_type": body_type if body is not None else "none",
        "timeout": timeout_sec,
        "assertions": assertions,
        "extractors": extractors,
        "warnings": warnings,
    }
    return sampler, unsupported


def _unsupported(path: str, node_type: str, reason: str) -> dict[str, Any]:
    return {"source_path": path, "type": node_type, "reason": reason}


def _is_http_defaults(el: Element) -> bool:
    gui = el.attrib.get("guiclass") or ""
    test = el.attrib.get("testclass") or ""
    return "HttpDefaults" in gui or test == "ConfigTestElement"


def _parse_http_defaults(el: Element) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, field in (
        ("HTTPSampler.domain", "domain"),
        ("HTTPSampler.protocol", "protocol"),
        ("HTTPSampler.port", "port"),
        ("HTTPSampler.path", "path"),
        ("HTTPSampler.method", "method"),
    ):
        val = _string_prop(el, key)
        if val:
            out[field] = val
    return out


def _parse_header_manager(el: Element) -> dict[str, str]:
    headers: dict[str, str] = {}
    for coll in el.iter():
        if _local_tag(coll.tag) == "collectionProp" and coll.attrib.get("name") == "HeaderManager.headers":
            for ep in coll:
                if _local_tag(ep.tag) != "elementProp":
                    continue
                name = _string_prop(ep, "Header.name")
                value = _string_prop(ep, "Header.value")
                if name:
                    headers[name] = value or ""
    return headers


def _parse_arguments(el: Element) -> list[dict[str, str]]:
    args: list[dict[str, str]] = []
    for coll in el.iter():
        if _local_tag(coll.tag) != "collectionProp":
            continue
        if coll.attrib.get("name") != "Arguments.arguments":
            continue
        for ep in coll:
            if _local_tag(ep.tag) != "elementProp":
                continue
            name = _string_prop(ep, "Argument.name")
            value = _string_prop(ep, "Argument.value")
            # Raw body arguments often omit Argument.name
            if name is None and value is None:
                continue
            args.append({"name": name or "", "value": value or ""})
    return args


def _has_raw_body(el: Element) -> bool:
    return _bool_prop(el, "HTTPSampler.postBodyRaw")


def _extract_raw_body(el: Element) -> Optional[str]:
    """Raw body is stored as first argument value when postBodyRaw is true."""
    args = _parse_arguments(el)
    if args:
        # Often a single unnamed or empty-name argument holds raw body
        if len(args) == 1:
            return args[0].get("value")
        for a in args:
            if not a.get("name"):
                return a.get("value")
        return args[0].get("value")
    return None


def _guess_body_type(raw: str, headers: dict[str, str]) -> str:
    ct = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            ct = (v or "").lower()
            break
    if "json" in ct:
        return "json"
    if "xml" in ct:
        return "xml"
    return "raw"


def _split_path_query(raw: str) -> tuple[str, list[dict[str, Any]]]:
    if not raw:
        return "/", []
    if "?" not in raw:
        return raw, []
    path, qs = raw.split("?", 1)
    params = []
    for part in qs.split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        params.append({"name": k, "value": v, "type": "string", "required": False})
    return path or "/", params


def _map_response_assertion(el: Element) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Map ResponseAssertion to platform assertions. Returns (list, warning)."""
    # test_type bitmask in JMeter: 1=contains, 2=matches, 4=equals, 8=substring, 16=not, 32=or
    # Also Response Assertion can use "Assertion.test_field" : Assertion.response_code / response_data
    field = _string_prop(el, "Assertion.test_field") or ""
    tt = _int_prop(el, "Assertion.test_type")
    if tt is None:
        test_type = _string_prop(el, "Assertion.test_type")
        try:
            tt = int(test_type) if test_type is not None else 2
        except ValueError:
            tt = 2

    strings: list[str] = []
    for coll in el.iter():
        if _local_tag(coll.tag) == "collectionProp" and coll.attrib.get("name") == "Asserion.test_strings":
            # typo in older JMeter: Asserion
            for sp in coll:
                if _local_tag(sp.tag) == "stringProp" and (sp.text or "").strip():
                    strings.append(sp.text.strip())
        if _local_tag(coll.tag) == "collectionProp" and coll.attrib.get("name") == "Assertion.test_strings":
            for sp in coll:
                if _local_tag(sp.tag) == "stringProp" and (sp.text or "").strip():
                    strings.append(sp.text.strip())

    is_not = bool(tt & 16)
    # equals vs contains
    use_equals = bool(tt & 8) or bool(tt & 4)  # substring often 8; equals 4 — map equals for response code
    results: list[dict[str, Any]] = []

    if "response_code" in field:
        for s in strings:
            results.append(
                {
                    "type": "status_code",
                    "target": None,
                    "operator": "not_equals" if is_not else "equals",
                    "expected": _maybe_int(s),
                    "description": "从 JMeter Response Assertion 导入",
                }
            )
        return results, None if results else "响应码断言无测试字符串"

    if "response_data" in field or field == "" or "response_message" in field:
        for s in strings:
            if use_equals and not is_not:
                results.append(
                    {
                        "type": "contains",
                        "target": None,
                        "operator": "equals",
                        "expected": s,
                        "description": "从 JMeter Response Assertion 导入",
                    }
                )
            else:
                results.append(
                    {
                        "type": "contains",
                        "target": None,
                        "operator": "not_equals" if is_not else "contains",
                        "expected": s,
                        "description": "从 JMeter Response Assertion 导入",
                    }
                )
        if results:
            return results, None
        return [], "响应体断言无测试字符串"

    return [], f"暂不支持的断言字段: {field or '?'}"


def _map_json_extractor(el: Element) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    ref = _string_prop(el, "JSONPostProcessor.referenceNames") or _string_prop(el, "JSONPathExtractor.referenceNames")
    expr = _string_prop(el, "JSONPostProcessor.jsonPathExprs") or _string_prop(el, "JSONPathExtractor.jsonPathExprs")
    if not ref or not expr:
        return None, "JSON Extractor 缺少变量名或表达式"
    # Multiple refs separated by ;
    name = ref.split(";")[0].strip()
    path = expr.split(";")[0].strip()
    if not name or not path:
        return None, "JSON Extractor 变量名或表达式为空"
    return {
        "name": name,
        "source": "json",
        "path": path,
        "description": "从 JMeter JSON Extractor 导入",
    }, None


def _string_prop(el: Element, name: str) -> Optional[str]:
    for child in el.iter():
        if _local_tag(child.tag) == "stringProp" and child.attrib.get("name") == name:
            return child.text if child.text is not None else ""
    return None


def _bool_prop(el: Element, name: str) -> bool:
    for child in el.iter():
        if _local_tag(child.tag) == "boolProp" and child.attrib.get("name") == name:
            return (child.text or "").strip().lower() in ("true", "1")
    return False


def _int_prop(el: Element, name: str) -> Optional[int]:
    raw = _string_prop(el, name)
    if raw is None:
        # intProp
        for child in el.iter():
            if _local_tag(child.tag) in ("intProp", "longProp") and child.attrib.get("name") == name:
                raw = child.text
                break
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        return None


def _maybe_int(s: str) -> Any:
    try:
        return int(s)
    except ValueError:
        return s
