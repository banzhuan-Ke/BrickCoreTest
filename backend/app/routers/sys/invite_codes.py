import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import USER_EDIT, USER_VIEW
from app.models.sys import InviteCode, Role
from app.schemas.sys import (
    CreateInviteCodeForm,
    InviteCodeListSchemas,
    InviteCodeSchemas,
    UpdateInviteCodeForm,
)

router = APIRouter(prefix="/invite-codes", tags=["邀请码管理"])


def _gen_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _invite_dict(invite: InviteCode) -> dict:
    d = invite.__dict__.copy()
    d.pop("_partial", None)
    d.pop("_saved_in_db", None)
    d.pop("_custom_generated_pk", None)
    return d


@router.get(
    "",
    summary="邀请码列表",
    response_model=InviteCodeListSchemas,
    dependencies=[Depends(require_permissions(USER_VIEW))],
)
async def list_invite_codes(page: int = 1, size: int = 10):
    page = max(page, 1)
    size = max(size, 1)
    query = InviteCode.filter(is_del=False).order_by("-id")
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size)
    return {"total": total, "data": [InviteCodeSchemas(**_invite_dict(r)) for r in rows]}


@router.post(
    "",
    summary="生成邀请码",
    response_model=InviteCodeSchemas,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(USER_EDIT))],
)
async def create_invite_code(item: CreateInviteCodeForm, user_info: dict = Depends(is_authenticated)):
    role_ids = item.role_ids or []
    if role_ids:
        valid_count = await Role.filter(id__in=role_ids, is_del=False).count()
        if valid_count != len(set(role_ids)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="存在无效的角色ID")

    code = (item.code or "").strip().upper()
    if not code:
        for _ in range(10):
            candidate = _gen_code()
            if not await InviteCode.filter(code=candidate).exists():
                code = candidate
                break
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="生成邀请码失败，请重试")
    elif await InviteCode.filter(code=code, is_del=False).exists():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邀请码已存在")

    invite = await InviteCode.create(
        code=code,
        role_ids=role_ids,
        max_uses=item.max_uses,
        expires_at=item.expires_at,
        note=item.note or "",
        created_by_id=user_info.get("id"),
        created_by_username=user_info.get("username") or "",
        is_active=True,
        is_del=False,
    )
    return InviteCodeSchemas(**_invite_dict(invite))


@router.put(
    "/{invite_id}",
    summary="更新邀请码",
    response_model=InviteCodeSchemas,
    dependencies=[Depends(require_permissions(USER_EDIT))],
)
async def update_invite_code(invite_id: int, item: UpdateInviteCodeForm):
    invite = await InviteCode.get_or_none(id=invite_id, is_del=False)
    if not invite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邀请码不存在")

    data = item.model_dump(exclude_unset=True)
    if "role_ids" in data and data["role_ids"] is not None:
        role_ids = data["role_ids"]
        if role_ids:
            valid_count = await Role.filter(id__in=role_ids, is_del=False).count()
            if valid_count != len(set(role_ids)):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="存在无效的角色ID")

    await invite.update_from_dict(data)
    await invite.save()
    return InviteCodeSchemas(**_invite_dict(invite))


@router.delete(
    "/{invite_id}",
    summary="删除邀请码",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(USER_EDIT))],
)
async def delete_invite_code(invite_id: int):
    invite = await InviteCode.get_or_none(id=invite_id, is_del=False)
    if not invite:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邀请码不存在")
    invite.is_del = True
    await invite.save()
