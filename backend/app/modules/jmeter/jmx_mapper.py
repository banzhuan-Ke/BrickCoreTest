"""Map JMeter IR to platform preview drafts (API / Case / Suite / PerfScene)."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Optional

from app.modules.perf.perf_journey import JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE

# ${token} or ${__time()} etc.
_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Controllers / timers that block auto PerfScene generation for a Thread Group.
# Scripts/CSV still import as HTTP-only with todos/warnings, but do not block scene draft.
PERF_BLOCKING_TYPES = frozenset({
    "IfController",
    "WhileController",
    "ForeachController",
    "ForEachController",
    "RuntimeController",
    "ThroughputController",
    "InterleaveControl",
    "SwitchController",
    "ConstantTimer",
    "UniformRandomTimer",
    "GaussianRandomTimer",
})


def convert_jmeter_variables(text: str) -> tuple[str, list[str]]:
    """Convert literal ${name} → ${{name}}; warn on JMeter functions (${__...})."""
    if not text or not isinstance(text, str):
        return text, []
    warnings: list[str] = []

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        if inner.startswith("__"):
            warnings.append(f"JMeter 函数不自动转换: ${{{inner}}}")
            return m.group(0)
        if inner.startswith("{") and inner.endswith("}"):
            return m.group(0)
        return "${{" + inner + "}}"

    out = _VAR_PATTERN.sub(repl, text)
    return out, warnings


def apply_variables_to_value(value: Any) -> tuple[Any, list[str]]:
    warns: list[str] = []
    if isinstance(value, str):
        return convert_jmeter_variables(value)
    if isinstance(value, dict):
        new_d = {}
        for k, v in value.items():
            nv, w = apply_variables_to_value(v)
            new_d[k] = nv
            warns.extend(w)
        return new_d, warns
    if isinstance(value, list):
        new_l = []
        for item in value:
            nv, w = apply_variables_to_value(item)
            new_l.append(nv)
            warns.extend(w)
        return new_l, warns
    return value, warns


def build_perf_config_from_thread_group(tg: dict[str, Any]) -> dict[str, Any]:
    """Map Thread Group load settings to platform PerfConfig (journey modes)."""
    users = tg.get("threads") or 1
    try:
        users = max(1, min(1000, int(users)))
    except (TypeError, ValueError):
        users = 1
    ramp = tg.get("ramp_up_seconds") or 0
    try:
        ramp = max(0, min(600, int(ramp)))
    except (TypeError, ValueError):
        ramp = 0

    duration = tg.get("duration_seconds")
    loop_count = tg.get("loop_count")

    if duration is not None:
        try:
            duration = max(1, min(86400, int(duration)))
        except (TypeError, ValueError):
            duration = None

    if loop_count is not None:
        try:
            loop_count = max(1, min(100000, int(loop_count)))
        except (TypeError, ValueError):
            loop_count = None

    # Prefer scheduler duration → journey_fixed; else fixed loops → journey_loop; else 1 loop
    if duration:
        return {
            "mode": JOURNEY_FIXED_MODE,
            "concurrent_users": users,
            "ramp_up_seconds": ramp,
            "duration_seconds": duration,
            "distribution_mode": "weighted_random",
            "error_rate_threshold": 0,
        }
    return {
        "mode": JOURNEY_LOOP_MODE,
        "concurrent_users": users,
        "ramp_up_seconds": ramp,
        "loop_count": loop_count or 1,
        "distribution_mode": "weighted_random",
        "error_rate_threshold": 0,
    }


def assess_thread_group_perf_eligibility(
    tg: dict[str, Any],
    unsupported_nodes: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Return (eligible, block_reasons) for generating a PerfScene from this Thread Group."""
    reasons: list[str] = []
    samplers = tg.get("samplers") or []
    if not samplers:
        reasons.append("无 HTTP 采样器，无法生成压测场景")

    tg_path = (tg.get("source_path") or "").rstrip("/")
    tg_name = tg.get("name") or ""

    for un in unsupported_nodes or []:
        typ = un.get("type") or ""
        if typ not in PERF_BLOCKING_TYPES:
            continue
        path = un.get("source_path") or ""
        under_tg = False
        if tg_path and (path == tg_path or path.startswith(tg_path + "/")):
            under_tg = True
        elif tg_name and f"/{tg_name}/" in path:
            under_tg = True
        if under_tg:
            reasons.append(f"{typ}: {un.get('reason') or '不支持自动生成压测场景'}")

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return (len(uniq) == 0 and bool(samplers)), uniq


def map_ir_to_preview(ir: dict[str, Any]) -> dict[str, Any]:
    """
    Build preview structure from IR.
    Includes optional perf_scenes drafts for Phase 2.
    """
    ir = deepcopy(ir)
    apis: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    suites: list[dict[str, Any]] = []
    perf_scenes: list[dict[str, Any]] = []
    all_warnings: list[str] = list(ir.get("warnings") or [])
    todos: list[str] = []
    unsupported = list(ir.get("unsupported_nodes") or [])

    for un in unsupported:
        if "CSV" in (un.get("reason") or "") or un.get("type") == "CSVDataSet":
            todos.append(f"CSV 待绑定: {un.get('source_path')}")

    for tg in ir.get("thread_groups") or []:
        suite_case_paths: list[str] = []
        for sampler in tg.get("samplers") or []:
            sampler, sw = _finalize_sampler(sampler)
            all_warnings.extend(sw)
            all_warnings.extend(sampler.get("warnings") or [])

            source_path = sampler["source_path"]
            headers_list = [{"key": k, "value": v, "description": ""} for k, v in (sampler.get("headers") or {}).items()]
            api_draft = {
                "source_path": source_path,
                "name": sampler.get("name") or "HTTP Request",
                "method": sampler.get("method") or "GET",
                "path": sampler.get("path") or "/",
                "base_url": sampler.get("base_url"),
                "headers": headers_list,
                "params": sampler.get("params") or [],
                "body": sampler.get("body"),
                "body_type": sampler.get("body_type") or "none",
                "description": f"从 JMeter 导入: {source_path}",
            }
            case_draft = {
                "source_path": source_path,
                "name": sampler.get("name") or "HTTP Request",
                "request_headers": dict(sampler.get("headers") or {}),
                "request_params": sampler.get("params") or [],
                "request_body": sampler.get("body") if sampler.get("body") is not None else {},
                "request_body_type": sampler.get("body_type") or "json",
                "timeout": sampler.get("timeout") or 30,
                "assertions": sampler.get("assertions") or [],
                "extractors": sampler.get("extractors") or [],
                "tags": ["jmeter"],
            }
            apis.append(api_draft)
            cases.append(case_draft)
            suite_case_paths.append(source_path)

        if not suite_case_paths:
            continue

        eligible, block_reasons = assess_thread_group_perf_eligibility(tg, unsupported)
        perf_config = build_perf_config_from_thread_group(tg) if eligible else None

        suite_draft = {
            "name": tg.get("name") or "Thread Group",
            "source_path": tg.get("source_path") or "",
            "sampler_paths": suite_case_paths,
            "threads": tg.get("threads"),
            "ramp_up_seconds": tg.get("ramp_up_seconds"),
            "duration_seconds": tg.get("duration_seconds"),
            "loop_count": tg.get("loop_count"),
            "warnings": list(tg.get("warnings") or []),
            "perf_eligible": eligible,
            "perf_block_reasons": block_reasons,
            "perf_config": perf_config,
        }
        suites.append(suite_draft)
        all_warnings.extend(tg.get("warnings") or [])

        if eligible and perf_config:
            perf_scenes.append(
                {
                    "name": f"{suite_draft['name']}（JMeter）"[:100],
                    "suite_name": suite_draft["name"],
                    "source_path": suite_draft["source_path"],
                    "sampler_paths": list(suite_case_paths),
                    "config": perf_config,
                }
            )
        elif block_reasons:
            for br in block_reasons[:3]:
                all_warnings.append(f"[{suite_draft['name']}] 不生成压测场景: {br}")

    seen = set()
    uniq_warnings = []
    for w in all_warnings:
        if w and w not in seen:
            seen.add(w)
            uniq_warnings.append(w)

    return {
        "test_plan_name": ir.get("test_plan_name") or "JMeter Import",
        "apis": apis,
        "cases": cases,
        "suites": suites,
        "perf_scenes": perf_scenes,
        "unsupported_nodes": unsupported,
        "warnings": uniq_warnings,
        "todos": todos,
        "counts": {
            "apis": len(apis),
            "cases": len(cases),
            "suites": len(suites),
            "perf_scenes": len(perf_scenes),
            "unsupported": len(unsupported),
            "warnings": len(uniq_warnings),
        },
    }


def _finalize_sampler(sampler: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Ensure variables converted (idempotent if already done in normalizer)."""
    s = deepcopy(sampler)
    warns: list[str] = []
    for key in ("path", "base_url", "body"):
        if key in s and s[key] is not None:
            s[key], w = apply_variables_to_value(s[key])
            warns.extend(w)
    if s.get("headers"):
        nh, w = apply_variables_to_value(s["headers"])
        s["headers"] = nh
        warns.extend(w)
    if s.get("params"):
        np, w = apply_variables_to_value(s["params"])
        s["params"] = np
        warns.extend(w)
    return s, warns
