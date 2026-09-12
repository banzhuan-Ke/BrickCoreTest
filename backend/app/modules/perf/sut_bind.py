"""压测启动：解析被测应用绑定并写入 config_snapshot。"""
from __future__ import annotations

from typing import Any, Optional

from app.models.perf import SutServer
from app.modules.perf.sut_force import apply_force_until, estimate_force_until_ms
from app.modules.perf.sut_resolve import resolve_servers
from app.core.platform.datetime_utils import now_epoch_ms


def _norm_int_list(raw: Any, *, limit: int = 200) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    seen: set[int] = set()
    for x in raw:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
        if len(out) >= limit:
            break
    return out


def _norm_roles(raw: Any) -> Optional[list[str]]:
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for r in raw:
        s = str(r or "").strip()[:64]
        if s and s not in out:
            out.append(s)
        if len(out) >= 50:
            break
    return out


def _finalize_none(cfg: dict[str, Any], binding_snapshot: dict[str, Any]) -> dict[str, Any]:
    cfg["sut_binding_snapshot"] = binding_snapshot
    cfg.pop("sut_server_ids", None)
    cfg["sut_metrics_status"] = "none"
    cfg.pop("sut_force_until_ms", None)
    return cfg


async def apply_sut_binding_to_config(
    config: dict[str, Any],
    *,
    project_id: int,
    env_id: Optional[int] = None,
    override_application_id: Optional[int] = None,
    override_roles: Optional[list[str]] = None,
    override_server_ids: Optional[list[int]] = None,
    apply_force: bool = False,
) -> dict[str, Any]:
    """
    解析顺序（SoT §8.3）：
    1. 显式 server_ids（启动覆盖或场景写死；空列表=显式解绑）
    2. application_id × env_id × roles
    3. 皆空 → sut_metrics_status=none

    默认 apply_force=False：等 PerfRecord 创建成功后再 activate_sut_force_for_record，
    避免 create 失败留下 force。
    """
    cfg = dict(config or {})
    env_id = int(env_id or cfg.get("env_id") or 0) or None

    app_id = override_application_id
    if app_id is None and cfg.get("sut_application_id") is not None:
        try:
            app_id = int(cfg.get("sut_application_id"))
        except (TypeError, ValueError):
            app_id = None

    roles = override_roles if override_roles is not None else _norm_roles(cfg.get("sut_roles"))
    # override_server_ids is not None（含 []）视为显式；否则读场景配置
    explicit_override = override_server_ids is not None
    explicit = (
        _norm_int_list(override_server_ids)
        if explicit_override
        else _norm_int_list(cfg.get("sut_server_ids"))
    )
    grafana_tpl = (cfg.get("sut_grafana_url_template") or "").strip() or None

    binding_snapshot: dict[str, Any] = {
        "application_id": app_id,
        "environment_id": env_id,
        "roles": roles,
        "resolve_error": None,
        "by_role": {},
        "servers": [],
        "missing_server_ids": [],
        "grafana_url_template": grafana_tpl,
        "source": None,
    }

    server_ids: list[int] = []

    if explicit_override or explicit:
        binding_snapshot["source"] = "explicit"
        if explicit_override and not explicit:
            binding_snapshot["resolve_error"] = "explicit_empty"
            if app_id is not None:
                cfg["sut_application_id"] = app_id
            else:
                cfg.pop("sut_application_id", None)
            if roles is not None:
                cfg["sut_roles"] = roles
            else:
                cfg.pop("sut_roles", None)
            if grafana_tpl:
                cfg["sut_grafana_url_template"] = grafana_tpl
            else:
                cfg.pop("sut_grafana_url_template", None)
            return _finalize_none(cfg, binding_snapshot)

        rows = await SutServer.filter(id__in=explicit, project_id=project_id, is_del=False).all()
        found = {r.id: r for r in rows}
        servers = []
        missing: list[int] = []
        for sid in explicit:
            row = found.get(sid)
            if not row:
                missing.append(sid)
                continue
            server_ids.append(sid)
            servers.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "hostname": row.hostname or "",
                    "role": row.role or "",
                    "monitoring_enabled": bool(row.monitoring_enabled),
                }
            )
        binding_snapshot["servers"] = servers
        binding_snapshot["missing_server_ids"] = missing
        if missing and not server_ids:
            binding_snapshot["resolve_error"] = "servers_not_found"
        elif missing:
            binding_snapshot["resolve_error"] = "partial_servers_missing"
    elif app_id and env_id:
        binding_snapshot["source"] = "application"
        resolved = await resolve_servers(
            application_id=app_id,
            environment_id=env_id,
            roles=roles,
        )
        binding_snapshot["resolve_error"] = resolved.get("error")
        binding_snapshot["application_name"] = resolved.get("application_name")
        binding_snapshot["environment_name"] = resolved.get("environment_name")
        binding_snapshot["by_role"] = resolved.get("by_role") or {}
        binding_snapshot["role_results"] = resolved.get("role_results") or []
        binding_snapshot["missing_roles"] = resolved.get("missing_roles") or []
        role_of: dict[int, str] = {}
        for role, ids in (resolved.get("by_role") or {}).items():
            for sid in ids or []:
                role_of[int(sid)] = str(role)
        servers = []
        for s in resolved.get("servers") or []:
            sid = int(s["id"])
            server_ids.append(sid)
            servers.append(
                {
                    **s,
                    "bound_role": role_of.get(sid) or s.get("role") or "",
                    "role": role_of.get(sid) or s.get("role") or "",
                }
            )
        binding_snapshot["servers"] = servers
    else:
        binding_snapshot["source"] = "none"

    seen: set[int] = set()
    ordered: list[int] = []
    for sid in server_ids:
        if sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    server_ids = ordered

    if app_id is not None:
        cfg["sut_application_id"] = app_id
    else:
        cfg.pop("sut_application_id", None)

    if roles is not None:
        cfg["sut_roles"] = roles
    else:
        cfg.pop("sut_roles", None)

    if grafana_tpl:
        cfg["sut_grafana_url_template"] = grafana_tpl
    else:
        cfg.pop("sut_grafana_url_template", None)

    cfg["sut_binding_snapshot"] = binding_snapshot

    if not server_ids:
        return _finalize_none(cfg, binding_snapshot)

    cfg["sut_server_ids"] = server_ids
    cfg["sut_metrics_status"] = "pending"

    if apply_force:
        from_ms = now_epoch_ms()
        until_ms = estimate_force_until_ms(config=cfg, now_ms=from_ms)
        cfg["sut_force_from_ms"] = from_ms
        cfg["sut_force_until_ms"] = until_ms
        await apply_force_until(server_ids, until_ms=until_ms, from_ms=from_ms)

    return cfg
