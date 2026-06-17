import re
from app.core import auth
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import USER_VIEW, USER_EDIT
from app.models.sys import Role
from app.schemas.sys import UserRoleSchema
from app.models.sys import User
from app.schemas.sys import RegisterForm, UserSchemas, LoginForm, LoginSchemas, TokenForm, Token, UserListSchemas, \
    UserUpdateForm, RegisterSchemas, ProfileUpdateForm, PasswordChangeForm

# 创建一个路由对象
router = APIRouter(prefix="/users", tags=["用户管理"])


async def _get_user_permissions(user: User) -> list:
    """获取用户合并后的权限列表（admin/管理员自动拥有全部权限）"""
    from app.core.permissions import get_user_permissions
    return await get_user_permissions(user)


def _build_user_data(user: User, roles: list = None, permissions: list = None) -> dict:
    """构建统一的用户返回数据"""
    data = {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "email": user.email,
        "mobile": user.mobile,
        "avatar": getattr(user, 'avatar', '') or '',
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_del": user.is_del,
        "created_at": user.created_at,
        "update_time": user.update_time,
        "roles": roles or [],
        "permissions": permissions or [],
        "default_project_id": getattr(user, "default_project_id", None),
    }
    return data


@router.post("/register", summary="用户注册", response_model=RegisterSchemas, status_code=status.HTTP_201_CREATED)
async def register(item: RegisterForm):
    from app.core.invite_code_service import validate_and_consume_invite_code

    role_ids = await validate_and_consume_invite_code(item.invite_code)
    item.roles = role_ids
    return await _do_register(item)


@router.post("", summary="创建用户", response_model=RegisterSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(USER_EDIT))])
async def create_user(item: RegisterForm):
    return await _do_register(item)


async def _do_register(item: RegisterForm):
    # 校验两次密码是否一致
    if item.password != item.password_confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="两次密码不一致！")
    # 校验用户名是否已存在（排除已删除用户）
    if await User.get_or_none(username=item.username, is_del=False):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名已存在！")
    # 校验邮箱是否已存在（排除已删除用户）
    if await User.get_or_none(email=item.email, is_del=False):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已存在！")
    # 邮箱校验格式
    if not re.fullmatch(r"^[^@]+@[^@]+\.[^@]+", item.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确！")
    # 校验手机号是否已存在（排除已删除用户）
    if await User.get_or_none(mobile=item.mobile, is_del=False):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号已存在！")
    # 手机号校验格式
    if not re.fullmatch(r"^1[3-9]\d{9}$", item.mobile):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号格式不正确！")
    # 密码加密
    password = auth.get_password_hash(item.password)
    # 注册用户，显式设置 is_del=False
    user = await User.create(
        username=item.username,
        password=password,
        email=item.email,
        mobile=item.mobile,
        nickname=item.nickname,
        is_superuser=False,
        is_active=True,
        is_del=False  # 新增：默认未删除
    )
    # 通过管理器添加角色
    if item.roles:
        roles_to_add = await Role.filter(id__in=item.roles)
        await user.roles.add(*roles_to_add)
    # 返回前重新获取完整数据（包含角色）
    user_with_roles = await User.get(id=user.id, is_del=False).prefetch_related("roles")
    roles = [UserRoleSchema(id=r.id, name=r.name) for r in await user_with_roles.roles.all()]
    perms = await _get_user_permissions(user_with_roles)
    return RegisterSchemas(**_build_user_data(user_with_roles, roles=roles, permissions=perms))


@router.post("/login", summary="用户登录", response_model=LoginSchemas, status_code=status.HTTP_200_OK)
async def login(item: LoginForm):
    """用户账号登录"""
    # 只允许未删除的用户登录
    user = await User.get_or_none(username=item.username, is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    if not auth.verify_password(item.password, user.password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    # 检查用户是否被停用
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用，请联系管理员")
    # 用户信息
    perms = await _get_user_permissions(user)
    userinfo = UserSchemas(**_build_user_data(user, permissions=perms))
    # 排除datetime字段
    token_payload = userinfo.model_dump(exclude={"created_at", "update_time", "permissions"})
    # 账户名密码正确，生成token
    token = auth.create_token(token_payload)
    # 返回token和用户信息
    return LoginSchemas(token=token, user=userinfo)


# 校验token
@router.post("/verify", summary="校验token", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def verify_token(item: TokenForm):
    """校验token"""
    userinfo = auth.verify_token(item.token)
    # 从数据库获取完整用户信息（确保用户未被删除）
    user = await User.get_or_none(id=userinfo.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    perms = await _get_user_permissions(user)
    return UserSchemas(**_build_user_data(user, permissions=perms))


# 刷新token
@router.post("/refresh", summary="刷新token", response_model=TokenForm, status_code=status.HTTP_200_OK)
async def refresh_token(item: TokenForm):
    # 刷新token，获取token中的用户信息
    userinfo = auth.verify_token(item.token)
    # 校验用户是否存在且未被删除
    user = await User.get_or_none(id=userinfo.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    # 从数据库重建 payload，确保 username 等字段与当前用户一致
    perms = await _get_user_permissions(user)
    fresh = UserSchemas(**_build_user_data(user, permissions=perms))
    token_payload = fresh.model_dump(exclude={"created_at", "update_time", "permissions"})
    return {"token": auth.create_token(token_payload)}


@router.post("/token", summary="模拟登录", response_model=Token, status_code=status.HTTP_200_OK)
async def access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """给接口文档登录生成token"""
    # 只允许未删除的用户登录
    user = await User.get_or_none(username=form_data.username, is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    if not auth.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名或密码错误")
    # 检查用户是否被停用
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用，请联系管理员")
    perms = await _get_user_permissions(user)
    uinfo = UserSchemas(**_build_user_data(user, permissions=perms))
    # 排除datetime字段
    token_payload = uinfo.model_dump(exclude={"created_at", "update_time", "permissions"})
    token = auth.create_token(token_payload)
    return Token(access_token=token, token_type="bearer")


# ========== 个人中心接口（无需额外权限，登录即可访问）
# 注意：必须放在 /{user_id} 之前，否则 FastAPI 会把 "profile" 当成 user_id 参数 ==========

@router.get("/profile", summary="获取当前用户信息", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def get_profile(user_info: dict = Depends(is_authenticated)):
    """获取当前登录用户的完整信息"""
    user = await User.get_or_none(id=user_info.get("id"), is_del=False).prefetch_related("roles")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    roles = await user.roles.all()
    role_list = [{"id": role.id, "name": role.name} for role in roles]
    perms = await _get_user_permissions(user)
    return UserSchemas(**_build_user_data(user, roles=role_list, permissions=perms))


@router.put("/profile", summary="更新个人资料", response_model=UserSchemas, status_code=status.HTTP_200_OK)
async def update_profile(data: ProfileUpdateForm, user_info: dict = Depends(is_authenticated)):
    """当前登录用户更新自己的资料（昵称、邮箱、手机、头像）"""
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    
    # 校验邮箱格式
    if data.email and not re.fullmatch(r"^[^@]+@[^@]+\.[^@]+$", data.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确！")
    # 校验手机号格式
    if data.mobile and not re.fullmatch(r"^1[3-9]\d{9}$", data.mobile):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号格式不正确！")
    # 校验邮箱是否与其他用户冲突
    if data.email and data.email != user.email:
        existing = await User.get_or_none(email=data.email, is_del=False)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已被其他用户使用")
    # 校验手机号是否与其他用户冲突
    if data.mobile and data.mobile != user.mobile:
        existing = await User.get_or_none(mobile=data.mobile, is_del=False)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号已被其他用户使用")
    
    await User.filter(id=user.id).update(
        nickname=data.nickname,
        email=data.email,
        mobile=data.mobile,
        avatar=data.avatar
    )
    
    updated = await User.get(id=user.id, is_del=False).prefetch_related("roles")
    roles = await updated.roles.all()
    role_list = [{"id": role.id, "name": role.name} for role in roles]
    perms = await _get_user_permissions(updated)
    return UserSchemas(**_build_user_data(updated, roles=role_list, permissions=perms))


@router.put("/profile/password", summary="修改密码", status_code=status.HTTP_200_OK)
async def change_password(data: PasswordChangeForm, user_info: dict = Depends(is_authenticated)):
    """当前登录用户修改自己的密码"""
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    
    # 校验原密码
    if not auth.verify_password(data.old_password, user.password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="原密码不正确")
    
    # 校验两次新密码是否一致
    if data.new_password != data.new_password_confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="两次新密码不一致")
    
    # 校验新密码长度
    if len(data.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="新密码长度不能少于6位")
    
    # 更新密码
    user.password = auth.get_password_hash(data.new_password)
    await user.save()
    
    return {"detail": "密码修改成功，请使用新密码重新登录"}


@router.put("/{user_id}", summary='更新用户', response_model=UserSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(USER_EDIT))])
async def update_user(user_id, user: UserUpdateForm, user_info: dict = Depends(is_authenticated)):
    """更新用户信息"""
    # 获取当前操作用户
    current_user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户不存在或已被停用")
    
    # 获取目标用户对象（确保未被删除）
    user_obj = await User.get_or_none(id=user_id, is_del=False).prefetch_related("roles")
    if not user_obj:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")
    
    # 非超级管理员只能修改自己
    if not current_user.is_superuser and int(current_user.id) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他用户信息")
    
    # 非超级管理员禁止修改敏感字段
    if not current_user.is_superuser:
        if user.is_superuser != user_obj.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改管理员权限")
        if user.is_active != user_obj.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改用户状态")
        if user.is_del is not None and user.is_del != user_obj.is_del:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除用户")
        if user.roles is not None:
            current_roles = {r.id for r in await user_obj.roles.all()}
            if set(user.roles) != current_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改用户角色")
    
    # 校验更新的用户名是否与其他未删除用户冲突
    if user.username != user_obj.username:
        existing_user = await User.get_or_none(username=user.username, is_del=False)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名已存在")
    # 校验更新的邮箱是否与其他未删除用户冲突
    if user.email != user_obj.email:
        existing_email = await User.get_or_none(email=user.email, is_del=False)
        if existing_email:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱已存在")
    # 更新用户信息
    await User.filter(id=user_id).update(
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        mobile=user.mobile,
        is_superuser=user.is_superuser,
        is_active=user.is_active,
        # 支持通过更新接口修改is_del状态（如逻辑删除）
        is_del=user.is_del if user.is_del is not None else user_obj.is_del
    )
    # 更新角色关联
    if user.roles is not None:
        # 清除现有角色
        await user_obj.roles.clear()
        # 添加新角色
        roles_to_add = await Role.filter(id__in=user.roles)
        await user_obj.roles.add(*roles_to_add)
    # 重新获取更新后的用户数据（包含角色信息）
    updated_user = await User.get(id=user_id, is_del=False).prefetch_related("roles")
    roles = await updated_user.roles.all()
    role_list = [{"id": role.id, "name": role.name} for role in roles]
    perms = await _get_user_permissions(updated_user)
    return UserSchemas(**_build_user_data(updated_user, roles=role_list, permissions=perms))


@router.get("", summary='查询用户', response_model=UserListSchemas, status_code=status.HTTP_200_OK,
           dependencies=[Depends(require_permissions(USER_VIEW))])
async def get_user(page: int = 1, size: int = 10, user_info: dict = Depends(is_authenticated)):
    """查询用户（只返回未删除的）"""
    query = User.filter(is_del=False).prefetch_related("roles").order_by("-id")
    total = await query.count()
    users = await query.offset((page - 1) * size).limit(size)
    result = []
    for user in users:
        roles = await user.roles.all()
        role_list = [{"id": role.id, "name": role.name} for role in roles]
        perms = await _get_user_permissions(user)
        result.append(UserSchemas(**_build_user_data(user, roles=role_list, permissions=perms)))
    return {"total": total, "data": result}


@router.delete("/{user_id}", summary='删除用户（逻辑删除）', status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(USER_EDIT))])
async def delete_user(user_id: int, user_info: dict = Depends(is_authenticated)):
    """删除用户（改为逻辑删除）"""
    user = await User.get_or_none(id=user_id, is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")
    # 逻辑删除：设置is_del=True
    user.is_del = True
    await user.save()


@router.put("/{user_id}/active", summary='启用/停用用户', status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_permissions(USER_EDIT))])
async def toggle_user_active(user_id: int, user_info: dict = Depends(is_authenticated)):
    """切换用户启用/停用状态"""
    # 获取操作用户信息
    current_user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not current_user or not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员才能启用/停用用户")
    
    # 获取目标用户
    user = await User.get_or_none(id=user_id, is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在或已被删除")
    
    # 不能停用自己
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能停用当前登录用户")
    
    # 切换状态
    user.is_active = not user.is_active
    await user.save()
    
    status_text = "启用" if user.is_active else "停用"
    return {"detail": f"用户 {user.username} 已{status_text}", "is_active": user.is_active}


