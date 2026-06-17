"""
系统预置角色种子（启动时幂等写入）
"""
import logging

from app.core.default_roles import DEFAULT_ROLES, MEMBER_CODE
from app.models.sys import Role

logger = logging.getLogger(__name__)

_role_seed_done = False


async def ensure_default_roles() -> None:
    """确保系统预置角色存在；已存在则按 code 同步 permissions（保留 id 供用户关联）。"""
    global _role_seed_done
    if _role_seed_done:
        return

    for spec in DEFAULT_ROLES:
        role = await Role.get_or_none(code=spec["code"], is_del=False)
        if not role:
            await Role.create(
                code=spec["code"],
                name=spec["name"],
                description=spec["description"],
                permissions=spec["permissions"],
                is_system=True,
                is_del=False,
            )
            logger.info("已创建系统角色: %s (%s)", spec["name"], spec["code"])
            continue

        changed = False
        if role.name != spec["name"]:
            role.name = spec["name"]
            changed = True
        if role.description != spec["description"]:
            role.description = spec["description"]
            changed = True
        if role.permissions != spec["permissions"]:
            role.permissions = spec["permissions"]
            changed = True
        if not role.is_system:
            role.is_system = True
            changed = True
        if changed:
            await role.save()
            logger.info("已同步系统角色: %s (%s)", spec["name"], spec["code"])

    _role_seed_done = True


async def get_role_id_by_code(code: str) -> int | None:
    """按 code 获取角色 id（需先 ensure_default_roles）。"""
    role = await Role.get_or_none(code=code, is_del=False)
    return role.id if role else None


async def get_default_member_role_ids() -> list[int]:
    """注册默认绑定的角色 id 列表。"""
    await ensure_default_roles()
    rid = await get_role_id_by_code(MEMBER_CODE)
    return [rid] if rid else []
