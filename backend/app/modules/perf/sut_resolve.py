"""被测应用 × 环境 → 采集器解析（供 M3 压测复用）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.platform.datetime_utils import now_app
from app.models.perf import SutAppEnvBinding, SutApplication, SutServer
from app.models.sys import Environment
from app.modules.perf.sut_schedule import is_monitoring_allowed

HEARTBEAT_ONLINE_SEC = 90
MAX_ROLES = 50
MAX_SERVERS_PER_ROLE = 100
MAX_TOTAL_SERVER_REFS = 500
MAX_ROLE_LEN = 64


def _normalize_roles(roles: Optional[list[Any]]) -> Optional[list[str]]:
    if roles is None:
        return None
    out: list[str] = []
    for r in roles:
        s = str(r or "").strip()[:MAX_ROLE_LEN]
        if s and s not in out:
            out.append(s)
        if len(out) >= MAX_ROLES:
            break
    return out


def _normalize_bindings(raw: Any) -> list[dict[str, Any]]:
    """bindings_json → [{role, server_ids: [int,...]}]，同 role 合并去重。"""
    if not isinstance(raw, list):
        return []
    by_role: dict[str, list[int]] = {}
    order: list[str] = []
    total_refs = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()[:MAX_ROLE_LEN]
        if not role:
            continue
        if role not in by_role:
            if len(order) >= MAX_ROLES:
                continue
            by_role[role] = []
            order.append(role)
        seen = set(by_role[role])
        for sid in item.get("server_ids") or []:
            if len(by_role[role]) >= MAX_SERVERS_PER_ROLE:
                break
            if total_refs >= MAX_TOTAL_SERVER_REFS:
                break
            try:
                i = int(sid)
            except (TypeError, ValueError):
                continue
            if i not in seen:
                seen.add(i)
                by_role[role].append(i)
                total_refs += 1
    return [{"role": r, "server_ids": by_role[r]} for r in order]


def _server_online(row: SutServer) -> bool:
    if not row.last_heartbeat_at:
        return False
    hb = row.last_heartbeat_at
    if hb.tzinfo is not None:
        hb = hb.replace(tzinfo=None)
    now = now_app()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return (now - hb).total_seconds() <= HEARTBEAT_ONLINE_SEC


async def resolve_servers(
    *,
    application_id: int,
    environment_id: int,
    roles: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    按应用 × 环境 × 角色子集解析采集器。

    roles=None → 使用应用 roles_json；应用未声明角色时回退绑定内全部角色。
    """
    empty = {
        "application_id": application_id,
        "environment_id": environment_id,
        "server_ids": [],
        "by_role": {},
        "servers": [],
        "missing_roles": [],
        "role_results": [],
        "error": None,
    }

    app = await SutApplication.get_or_none(id=application_id, is_del=False)
    if not app:
        return {**empty, "error": "application_not_found"}

    env = await Environment.get_or_none(id=environment_id, is_del=False)
    if not env:
        return {
            **empty,
            "application_name": app.name,
            "error": "env_not_found",
        }
    if env.project_id != app.project_id:
        return {
            **empty,
            "application_name": app.name,
            "error": "env_project_mismatch",
        }

    binding = await SutAppEnvBinding.get_or_none(
        application_id=application_id,
        environment_id=environment_id,
    )
    if not binding:
        return {
            **empty,
            "application_name": app.name,
            "environment_name": env.name or "",
            "error": "binding_not_found",
        }

    want = _normalize_roles(roles)
    # None 或空列表均表示「应用全部角色 / 绑定内全部角色」
    if not want:
        app_roles = _normalize_roles(app.roles_json) or []
        want = app_roles if app_roles else None

    rows = _normalize_bindings(binding.bindings_json)
    bound_map = {row["role"]: list(row["server_ids"]) for row in rows}
    missing_roles: list[str] = []
    if want is not None:
        missing_roles = [r for r in want if r not in bound_map]

    # 收集全部候选 id（含可能已删）
    candidate_ids: list[int] = []
    for role, sids in bound_map.items():
        if want is not None and role not in want:
            continue
        candidate_ids.extend(sids)
    found = {}
    if candidate_ids:
        for s in await SutServer.filter(id__in=list(set(candidate_ids))):
            found[s.id] = s

    role_results: list[dict[str, Any]] = []
    by_role: dict[str, list[int]] = {}
    ordered_ids: list[int] = []
    seen: set[int] = set()
    servers: list[dict[str, Any]] = []

    roles_to_report = want if want is not None else list(bound_map.keys())
    for role in roles_to_report:
        if role not in bound_map:
            role_results.append(
                {"role": role, "server_ids": [], "status": "missing", "servers": []}
            )
            continue
        raw_ids = bound_map[role]
        if not raw_ids:
            role_results.append(
                {"role": role, "server_ids": [], "status": "unbound", "servers": []}
            )
            by_role[role] = []
            continue

        ok_ids: list[int] = []
        role_servers: list[dict[str, Any]] = []
        statuses: set[str] = set()
        for sid in raw_ids:
            s = found.get(sid)
            if not s or s.is_del:
                statuses.add("server_deleted")
                continue
            if s.project_id != app.project_id:
                statuses.add("server_project_mismatch")
                continue
            sample_ok = is_monitoring_allowed(
                monitoring_enabled=bool(s.monitoring_enabled),
                schedule=s.schedule_json if isinstance(s.schedule_json, dict) else None,
                force_until_ms=getattr(s, "force_until_ms", None),
                force_from_ms=getattr(s, "force_from_ms", None),
            )
            st = "ok"
            if not s.monitoring_enabled:
                st = "monitoring_disabled"
            elif not sample_ok:
                # 日常暂停，但压测启动后会 force；预览区分文案
                st = "schedule_paused_will_force"
            elif not _server_online(s):
                st = "offline"
            statuses.add(st)
            ok_ids.append(sid)
            info = {
                "id": s.id,
                "name": s.name,
                "hostname": s.hostname or "",
                "role": s.role or "",
                "monitoring_enabled": bool(s.monitoring_enabled),
                "status": st,
                "online": _server_online(s),
            }
            role_servers.append(info)
            if sid not in seen:
                seen.add(sid)
                ordered_ids.append(sid)
                servers.append(
                    {
                        "id": s.id,
                        "name": s.name,
                        "hostname": s.hostname or "",
                        "role": s.role or "",
                        "monitoring_enabled": bool(s.monitoring_enabled),
                        "status": st,
                        "online": info["online"],
                    }
                )

        if not ok_ids:
            # 全部无效
            status = "server_deleted"
            if "server_project_mismatch" in statuses and "server_deleted" not in statuses:
                status = "server_project_mismatch"
            elif statuses == {"server_project_mismatch"}:
                status = "server_project_mismatch"
            role_results.append(
                {"role": role, "server_ids": [], "status": status, "servers": []}
            )
            by_role[role] = []
            continue

        # 角色级状态：有可用机优先 ok；否则取最严重提示
        if "ok" in statuses:
            role_status = "ok"
        elif "offline" in statuses:
            role_status = "offline"
        elif "schedule_paused" in statuses:
            role_status = "schedule_paused"
        elif "monitoring_disabled" in statuses:
            role_status = "monitoring_disabled"
        else:
            role_status = "ok"
        by_role[role] = ok_ids
        role_results.append(
            {
                "role": role,
                "server_ids": ok_ids,
                "status": role_status,
                "servers": role_servers,
            }
        )

    return {
        "application_id": application_id,
        "environment_id": environment_id,
        "application_name": app.name,
        "environment_name": env.name or "",
        "server_ids": ordered_ids,
        "by_role": by_role,
        "servers": servers,
        "missing_roles": missing_roles,
        "role_results": role_results,
        "error": None,
    }


def validate_bindings_payload(
    raw: Any,
    *,
    allowed_server_ids: set[int],
    allowed_roles: Optional[set[str]] = None,
) -> tuple[list[dict[str, Any]], list[int], list[str]]:
    """
    校验并规范化写入 bindings。
    返回 (cleaned, rejected_ids, invalid_roles)。
    allowed_roles 非空时，role 必须属于该集合。
    """
    if isinstance(raw, list) and len(raw) > MAX_ROLES:
        raise ValueError(f"角色绑定不能超过 {MAX_ROLES} 条")
    rows = _normalize_bindings(raw)
    rejected: list[int] = []
    invalid_roles: list[str] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        role = row["role"]
        if allowed_roles is not None and role not in allowed_roles:
            invalid_roles.append(role)
            continue
        ok: list[int] = []
        for i in row["server_ids"]:
            if i in allowed_server_ids:
                ok.append(i)
            else:
                rejected.append(i)
        cleaned.append({"role": role, "server_ids": ok})
    rejected = list(dict.fromkeys(rejected))
    invalid_roles = list(dict.fromkeys(invalid_roles))
    return cleaned, rejected, invalid_roles
