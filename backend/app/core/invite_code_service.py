"""
邀请码校验与消费
"""
from datetime import datetime

from fastapi import HTTPException, status

from app.core.role_seed import get_default_member_role_ids, ensure_default_roles
from app.models.sys import InviteCode, Role


async def validate_and_consume_invite_code(code: str) -> list[int]:
    """
    校验邀请码并返回应绑定的角色 id 列表（同时递增 used_count）。
    邀请码未指定角色时，回退为「普通成员」。
    """
    normalized = (code or "").strip().upper()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邀请码不能为空")

    invite = await InviteCode.get_or_none(code=normalized, is_del=False)
    if not invite:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码无效")
    if not invite.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码已停用")
    if invite.max_uses > 0 and invite.used_count >= invite.max_uses:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码已达使用上限")
    if invite.expires_at and invite.expires_at < datetime.now():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码已过期")

    await ensure_default_roles()
    role_ids = [int(r) for r in (invite.role_ids or []) if r]
    if role_ids:
        valid = await Role.filter(id__in=role_ids, is_del=False).values_list("id", flat=True)
        role_ids = list(valid)
    if not role_ids:
        role_ids = await get_default_member_role_ids()
    if not role_ids:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="系统未配置默认注册角色")

    invite.used_count += 1
    await invite.save(update_fields=["used_count", "update_time"])
    return role_ids
