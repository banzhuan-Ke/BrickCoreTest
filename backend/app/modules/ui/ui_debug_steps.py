"""UI 交互调试：步骤指纹与初始 URL 解析。"""
from __future__ import annotations

import hashlib
import json
import re
from typing import List, Optional

_VAR_PATTERN = re.compile(r"\$\{\{([^}]+)\}\}")

# 环境 global_vars 中存 Web 默认起始 URL 的保留键（勿与用户变量同名）
ENV_DEFAULT_START_URL_KEY = "__default_start_url"


def get_env_default_start_url(global_vars: dict | None) -> str:
    gv = global_vars if isinstance(global_vars, dict) else {}
    raw = gv.get(ENV_DEFAULT_START_URL_KEY)
    if isinstance(raw, dict) and "value" in raw:
        return str(raw.get("value") or "").strip()
    return str(raw or "").strip()


def compute_steps_fingerprint(steps: list) -> str:
    """对步骤快照计算稳定指纹（展开后的步骤列表）。"""
    payload = json.dumps(steps or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalize_url(url: str) -> str:
    return str(url or "").strip()


def resolve_debug_initial_url(
    env_config: dict,
    steps: list,
    *,
    env_default_start_url: str | None = None,
    project_default_start_url: str | None = None,
) -> Optional[str]:
    """
    解析调试浏览器打开后可选的初始导航地址。
    优先：步骤 open_url → 环境 default_start_url → 项目 default_start_url → 环境 target_host。
    """
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        if step.get("method") == "open_url":
            url = (step.get("params") or {}).get("url") or step.get("url")
            url = _normalize_url(url)
            if url:
                return url

    env_url = _normalize_url(
        env_default_start_url
        if env_default_start_url is not None
        else (env_config or {}).get("env_default_start_url")
    )
    if env_url:
        return env_url

    project_url = _normalize_url(
        project_default_start_url
        if project_default_start_url is not None
        else (env_config or {}).get("project_default_start_url")
    )
    if project_url:
        return project_url

    host = _normalize_url((env_config or {}).get("target_host"))
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return host
    return f"https://{host}"


def substitute_variables_in_text(text: str, variables: dict) -> str:
    """将 ${{var}} 替换为环境变量（与 Runner VariableManager 语法一致）。"""
    if not text or "${{" not in text:
        return text

    def repl(match: re.Match) -> str:
        key = (match.group(1) or "").strip()
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _VAR_PATTERN.sub(repl, text)


def contains_unresolved_template(text: str) -> bool:
    return bool(text and ("${{" in text or "${" in text))


def resolve_debug_initial_url_with_variables(env_config: dict, steps: list) -> Optional[str]:
    """解析初始 URL，并尽量用 env.variables 替换 ${{var}}。"""
    raw = resolve_debug_initial_url(env_config, steps)
    if not raw:
        return None
    variables = (env_config or {}).get("variables") or {}
    if not isinstance(variables, dict):
        variables = {}
    resolved = substitute_variables_in_text(raw, variables)
    if contains_unresolved_template(resolved):
        return None
    return resolved
