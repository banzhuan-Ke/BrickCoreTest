import re
from typing import Any, Optional

from app.core.platform import auth
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import USER_VIEW, USER_EDIT
from app.models.sys import Role
from app.models.sys import User
from app.schemas.sys import RegisterForm, UserSchemas, LoginForm, LoginSchemas, TokenForm, Token, UserListSchemas, \
    UserUpdateForm, RegisterSchemas, ProfileUpdateForm, PasswordChangeForm

router = APIRouter(prefix="/users", tags=["用户管理"])

_USER_VALUE_FIELDS = (
    "id",
    "username",
    "nickname",
    "email",
    "mobile",
    "avatar",
    "is_active",
    "is_superuser",
    "is_del",
    "created_at",
    "update_time",
    "default_project_id",
)


async def _get_user_permissions(user_or_id) -> list:
    from app.core.platform.permissions import get_user_permissions
    return await get_user_permissions(user_or_id)


async def _load_user_role_list(user_id: int) -> list[dict]:
    rows = await Role.filter(users__id=user_id, is_del=False).values("id", "name")
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _schemas_from_row(
    row: dict[str, Any],
    *,
    roles: Optional[list] = None,
    permissions: Optional[list] = None,
) -> UserSchemas:
    return UserSchemas(
        id=row["id"],
        username=row.get("username") or "",
        nickname=row.get("nickname") or "",
        email=row.get("email") or "",
        mobile=row.get("mobile") or "",
        avatar=row.get("avatar") or "",
        is_active=bool(row.get("is_active", True)),
        is_superuser=bool(row.get("is_superuser")),
        is_del=bool(row.get("is_del")),
        created_at=row.get("created_at"),
        update_time=row.get("update_time"),
        roles=roles or [],
        permissions=permissions or [],
        default_project_id=row.get("default_project_id"),
    )


async def _user_schemas_by_id(user_id: int, *, with_roles: bool = True) -> UserSchemas:
    rows = await User.filter(id=user_id, is_del=False).values(*_USER_VALUE_FIELDS)
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    roles = await _load_user_role_list(user_id) if with_roles else []
    perms = await _get_user_permissions(user_id)
    return _schemas_from_row(rows[0], roles=roles, permissions=perms)


@router.post("/register", summary="用户注册", response_model=RegisterSchemas, status_code=status.HTTP_201_CREATED)
async def register(item: RegisterForm):
    from app.core.platform.invite_code_service import validate_and_consume_invite_code

    role_ids = await validate_and_consume_invite_code(item.invite_code)
    item.roles = role_ids
    return await _do_register(item)


@router.post("", summary="创建用户", response_model=RegisterSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(USER_EDIT))])
async def create_user(item: RegisterForm):
    return await _do_register(item)


async def _do_register(item: RegisterForm):
    if item.password != item.password_confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="两次密码不一致！")
    if await User.filter(username=item.username, is_del=False).exists():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名已存在！")
    if await User.filter(email=item.email, is_del=False).exists():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已存在！")
    if not re.fullmatch(r"^[^@]+@[^@]+\.[^@]+", item.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确！")
    if await User.filter(mobile=item.mobile, is_del=False).exists():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号已存在！")
    if not re.fullmatch(r"^1[3-9]\d{9}$", item.mobile):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号格式不正确！")

    password = auth.get_password_hash(item.password)
    user = await User.create(
        username=item.username,
        password=password,
        email=item.email,
        mobile=item.mobile,
        nickname=item.nickname,
        is_superuser=False,
        is_active=True,
        is_del=False,
    )
    if item.roles:
        roles_to_add = await Role.filter(id__in=item.roles)
        await user.roles.add(*roles_to_add)
    schemas = await _user_schemas_by_id(user.id)
    return RegisterSchemas(**schemas.model_dump())


@router.post("/login", summary="用户登录", response_model=LoginSchemas, status_code=status.HTTP_200_OK)
async def login(item: LoginForm):
    """用户账号登录"""
    rows = await User.filter(username=item.username, is_del=False).values(
        *_USER_VALUE_FIELDS, "password"
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    row = rows[0]
    if not auth.verify_password(item.password, row.get("password") or ""):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    if not row.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用，请联系管理员")

    roles = await _load_user_role_list(row["id"])
    perms = await _get_user_permissions(row["id"])
    userinfo = _schemas_from_row(row, roles=roles, permissions=perms)
    token_payload = userinfo.model_dump(exclude={"created_at", "update_time", "permissions"})
    token = auth.create_token(token_payload)
    return LoginSchemas(token=token, user=userinfo)


@router.post("/verify", summary="校验token", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def verify_token(item: TokenForm):
    """校验token"""
    userinfo = auth.verify_token(item.token)
    return await _user_schemas_by_id(userinfo.get("id"))


@router.post("/refresh", summary="刷新token", response_model=TokenForm, status_code=status.HTTP_200_OK)
async def refresh_token(item: TokenForm):
    userinfo = auth.verify_token(item.token)
    fresh = await _user_schemas_by_id(userinfo.get("id"))
    token_payload = fresh.model_dump(exclude={"created_at", "update_time", "permissions"})
    return {"token": auth.create_token(token_payload)}


@router.post("/token", summary="模拟登录", response_model=Token, status_code=status.HTTP_200_OK)
async def access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """给接口文档登录生成token"""
    rows = await User.filter(username=form_data.username, is_del=False).values(
        *_USER_VALUE_FIELDS, "password"
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    row = rows[0]
    if not auth.verify_password(form_data.password, row.get("password") or ""):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    if not row.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用，请联系管理员")

    roles = await _load_user_role_list(row["id"])
    perms = await _get_user_permissions(row["id"])
    uinfo = _schemas_from_row(row, roles=roles, permissions=perms)
    token_payload = uinfo.model_dump(exclude={"created_at", "update_time", "permissions"})
    token = auth.create_token(token_payload)
    return Token(access_token=token, token_type="bearer")


@router.get("/profile", summary="获取当前用户信息", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def get_profile(user_info: dict = Depends(is_authenticated)):
    """获取当前登录用户的完整信息"""
    return await _user_schemas_by_id(user_info.get("id"))


@router.put("/profile", summary="更新个人资料", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def update_profile(data: ProfileUpdateForm, user_info: dict = Depends(is_authenticated)):
    """当前登录用户更新自己的资料（昵称、邮箱、手机、头像）"""
    uid = user_info.get("id")
    rows = await User.filter(id=uid, is_del=False).values("id", "email", "mobile")
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    row = rows[0]

    if data.email and not re.fullmatch(r"^[^@]+@[^@]+\.[^@]+$", data.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确！")
    if data.mobile and not re.fullmatch(r"^1[3-9]\d{9}$", data.mobile):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号格式不正确！")
    if data.email and data.email != row.get("email"):
        if await User.filter(email=data.email, is_del=False).exclude(id=uid).exists():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已被其他用户使用")
    if data.mobile and data.mobile != row.get("mobile"):
        if await User.filter(mobile=data.mobile, is_del=False).exclude(id=uid).exists():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号已被其他用户使用")

    await User.filter(id=uid).update(
        nickname=data.nickname,
        email=data.email,
        mobile=data.mobile,
        avatar=data.avatar,
    )
    return await _user_schemas_by_id(uid)


@router.put("/profile/password", summary="修改密码", status_code=status.HTTP_200_OK)
async def change_password(data: PasswordChangeForm, user_info: dict = Depends(is_authenticated)):
    """当前登录用户修改自己的密码"""
    uid = user_info.get("id")
    rows = await User.filter(id=uid, is_del=False).values("id", "password")
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")

    if not auth.verify_password(data.old_password, rows[0].get("password") or ""):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="原密码不正确")
    if data.new_password != data.new_password_confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="两次新密码不一致")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="新密码长度不能少于6位")

    await User.filter(id=uid).update(password=auth.get_password_hash(data.new_password))
    return {"detail": "密码修改成功，请使用新密码重新登录"}


@router.put("/{user_id}", summary='更新用户', response_model=UserSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(USER_EDIT))])
async def update_user(user_id, user: UserUpdateForm, user_info: dict = Depends(is_authenticated)):
    """更新用户信息"""
    current_rows = await User.filter(id=user_info.get("id"), is_del=False).values(
        "id", "is_superuser"
    )
    if not current_rows:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户不存在或已被停用")
    current = current_rows[0]
    current_is_super = bool(current.get("is_superuser") or user_info.get("is_superuser"))

    target_rows = await User.filter(id=user_id, is_del=False).values(*_USER_VALUE_FIELDS)
    if not target_rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")
    target = target_rows[0]

    if not current_is_super and int(current["id"]) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他用户信息")

    if not current_is_super:
        if user.is_superuser != bool(target.get("is_superuser")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改管理员权限")
        if user.is_active != bool(target.get("is_active", True)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改用户状态")
        if user.is_del is not None and user.is_del != bool(target.get("is_del")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除用户")
        if user.roles is not None:
            current_roles = {r["id"] for r in await _load_user_role_list(int(user_id))}
            if set(user.roles) != current_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改用户角色")

    if user.username != target.get("username"):
        if await User.filter(username=user.username, is_del=False).exclude(id=user_id).exists():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名已存在")
    if user.email != target.get("email"):
        if await User.filter(email=user.email, is_del=False).exclude(id=user_id).exists():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已存在")

    await User.filter(id=user_id).update(
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        mobile=user.mobile,
        is_superuser=user.is_superuser,
        is_active=user.is_active,
        is_del=user.is_del if user.is_del is not None else bool(target.get("is_del")),
    )

    if user.roles is not None:
        user_obj = await User.filter(id=user_id).first()
        if user_obj:
            await user_obj.roles.clear()
            roles_to_add = await Role.filter(id__in=user.roles)
            await user_obj.roles.add(*roles_to_add)

    return await _user_schemas_by_id(int(user_id))


@router.get("", summary='查询用户', response_model=UserListSchemas, status_code=status.HTTP_200_OK,
           dependencies=[Depends(require_permissions(USER_VIEW))])
async def get_user(page: int = 1, size: int = 10, user_info: dict = Depends(is_authenticated)):
    """查询用户（只返回未删除的）"""
    query = User.filter(is_del=False).order_by("-id")
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size).values(*_USER_VALUE_FIELDS)
    result = []
    for row in rows:
        roles = await _load_user_role_list(row["id"])
        perms = await _get_user_permissions(row["id"])
        result.append(_schemas_from_row(row, roles=roles, permissions=perms))
    return {"total": total, "data": result}


@router.delete("/{user_id}", summary='删除用户（逻辑删除）', status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(USER_EDIT))])
async def delete_user(user_id: int, user_info: dict = Depends(is_authenticated)):
    """删除用户（改为逻辑删除）"""
    updated = await User.filter(id=user_id, is_del=False).update(is_del=True)
    if not updated:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")


@router.put("/{user_id}/active", summary='启用/停用用户', status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_permissions(USER_EDIT))])
async def toggle_user_active(user_id: int, user_info: dict = Depends(is_authenticated)):
    """切换用户启用/停用状态"""
    current_rows = await User.filter(id=user_info.get("id"), is_del=False).values(
        "id", "is_superuser"
    )
    if not current_rows or not (
        bool(current_rows[0].get("is_superuser")) or user_info.get("is_superuser")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员才能启用/停用用户")

    target_rows = await User.filter(id=user_id, is_del=False).values("id", "username", "is_active")
    if not target_rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")
    target = target_rows[0]

    if int(target["id"]) == int(current_rows[0]["id"]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能停用当前登录用户")

    new_active = not bool(target.get("is_active", True))
    await User.filter(id=user_id).update(is_active=new_active)
    status_text = "启用" if new_active else "停用"
    return {"detail": f"用户 {target.get('username') or ''} 已{status_text}", "is_active": new_active}
