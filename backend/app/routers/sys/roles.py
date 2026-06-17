from fastapi import APIRouter, HTTPException, Depends, status
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import PERMISSIONS, ROLE_VIEW, ROLE_EDIT
from app.models.sys import User
from app.models.sys import Role
from app.schemas.sys import RoleSchemas, RoleListSchemas, AddRoleForm, UpdateRoleForm

# 创建一个路由对象
router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("/permissions", summary="权限列表", status_code=status.HTTP_200_OK)
async def get_permissions(user_info: dict = Depends(is_authenticated)):
    """获取系统定义的所有权限分组"""
    return PERMISSIONS


@router.post("", summary='添加角色', response_model=RoleSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(ROLE_EDIT))])
async def add_role(item: AddRoleForm, user_info: dict = Depends(is_authenticated)):
    """添加角色"""
    # 显式设置 is_del=False（与模型默认值一致，增强可读性）
    role = await Role.create(**item.model_dump(), is_del=False)
    return role


@router.put("/{role_id}", summary='修改角色', response_model=RoleSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(ROLE_EDIT))])
async def update_role(role_id: int, item: UpdateRoleForm, user_info: dict = Depends(is_authenticated)):
    """修改角色"""
    role = await Role.get_or_none(id=role_id, is_del=False)
    if not role:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="角色不存在或已被删除")
    if role.is_system:
        if item.name is not None and item.name != role.name:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统预置角色不可修改名称")
        if item.is_del is not None and item.is_del:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统预置角色不可删除")
    data = item.model_dump(exclude_unset=True)
    if role.code == "system_admin" and "permissions" in data:
        from app.core.default_roles import sanitize_system_admin_permissions

        data["permissions"] = sanitize_system_admin_permissions(data["permissions"])
    await role.update_from_dict(data)
    await role.save()
    return role


@router.get("", summary="角色列表", response_model=RoleListSchemas, status_code=status.HTTP_200_OK,
           dependencies=[Depends(require_permissions(ROLE_VIEW))])
async def get_role(page: int = 1, size: int = 10, user_info: dict = Depends(is_authenticated)):
    """获取角色列表（只返回未删除的角色）"""
    query = Role.filter(is_del=False).order_by("-id")
    total = await query.count()
    roles = await query.offset((page - 1) * size).limit(size)
    result = []
    for role in roles:
        result.append(RoleSchemas(**role.__dict__))
    return {"total": total, "data": result}


@router.delete("/{role_id}", summary="删除角色（逻辑删除）", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(ROLE_EDIT))])
async def delete_role(role_id: int, user_info: dict = Depends(is_authenticated)):
    """删除角色"""
    role = await Role.get_or_none(id=role_id, is_del=False)
    if not role:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="角色不存在或已被删除")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统预置角色不可删除")
    # 检查角色是否被未删除的用户关联
    user_role_count = await User.filter(roles__id=role_id, is_del=False).count()
    if user_role_count > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该角色已被用户关联，无法删除！")
    # 逻辑删除：设置is_del=True
    role.is_del = True
    await role.save()
