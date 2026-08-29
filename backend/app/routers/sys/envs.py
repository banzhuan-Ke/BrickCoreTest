from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from tortoise.transactions import in_transaction

from app.schemas.sys import EnvironmentSchemas, AddEnvironmentForm, UpdateEnvironmentForm
from app.models.sys import Environment
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import ENVIRONMENT_VIEW, ENVIRONMENT_EDIT
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, assert_project_access
from app.models.sys import Project
from app.core.shared.global_vars_validate import normalize_global_vars
from app.core.shared.default_headers_validate import normalize_default_headers
from app.modules.sys.env_vars_batch import apply_batch_to_global_vars

# 创建路由对象
router = APIRouter(prefix="/envs", tags=['测试环境'], dependencies=[Depends(is_authenticated)])


class EnvBatchVarsBody(BaseModel):
    project_id: int = Field(..., description="项目 ID")
    mode: Literal["add_keys", "delete_keys", "sync_values"] = Field(..., description="操作模式")
    keys: list[str] = Field(..., min_length=1, description="变量名列表")
    target_env_ids: list[int] = Field(default_factory=list, description="目标环境；空=项目下全部")
    source_env_id: Optional[int] = Field(default=None, description="sync_values 时的源环境")
    default_values: Optional[dict] = Field(default=None, description="add_keys 时缺省值（可扩展格式）")
    overwrite: bool = Field(default=True, description="sync_values 是否覆盖已有键")


def _environment_dict(environment: Environment) -> dict:
    return {
        "id": environment.id,
        "name": environment.name,
        "host": environment.host,
        "global_vars": environment.global_vars or {},
        "default_headers": environment.default_headers or [],
        "create_time": environment.create_time,
        "update_time": environment.update_time,
        "project_id": environment.project_id,
        "username": environment.username,
        "is_del": environment.is_del,
    }


# 创建测试环境
@router.post('', summary='创建环境', status_code=status.HTTP_201_CREATED, response_model=EnvironmentSchemas,
             dependencies=[Depends(require_permissions(ENVIRONMENT_EDIT))])
async def create_environment(item: AddEnvironmentForm, username: str = Depends(get_current_username)):
    if not item.project_id or item.project_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择有效项目")
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在或已被删除")
    try:
        global_vars = normalize_global_vars(item.global_vars)
        default_headers = normalize_default_headers(getattr(item, "default_headers", None))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    environment = await Environment.create(
        name=item.name,
        host=item.host,
        global_vars=global_vars,
        default_headers=default_headers,
        project=project,
        username=item.username or username,
        is_del=False
    )
    return EnvironmentSchemas(**_environment_dict(environment))


@router.post(
    "/batch-vars",
    summary="跨环境批量增删/同步变量",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(ENVIRONMENT_EDIT))],
)
async def batch_env_vars(
    body: EnvBatchVarsBody,
    user_info: dict = Depends(is_authenticated),
):
    """
    - add_keys: 目标环境缺少该键时补上（可用 default_values，默认空值）
    - delete_keys: 删除目标环境中的键（不碰系统保留键）
    - sync_values: 从 source_env 复制勾选键的值到目标环境
    """
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在或已被删除")

    envs = await Environment.filter(project_id=body.project_id, is_del=False)
    if not envs:
        raise HTTPException(status_code=422, detail="项目下暂无环境")

    target_ids = set(body.target_env_ids or [])
    if target_ids:
        unknown = target_ids - {e.id for e in envs}
        if unknown:
            raise HTTPException(status_code=422, detail=f"目标环境不属于该项目：{sorted(unknown)}")
    targets = [e for e in envs if not target_ids or e.id in target_ids]
    if not targets:
        raise HTTPException(status_code=422, detail="未匹配到目标环境")

    source_vars = None
    if body.mode == "sync_values":
        if not body.source_env_id:
            raise HTTPException(status_code=422, detail="同步值时请指定源环境")
        source = next((e for e in envs if e.id == body.source_env_id), None)
        if not source:
            raise HTTPException(status_code=422, detail="源环境不存在或不属于该项目")
        source_vars = source.global_vars or {}

    # 先全部算完再写入，避免中途校验失败留下半成品
    prepared: list[tuple[Environment, dict]] = []
    try:
        for env in targets:
            if body.mode == "sync_values" and env.id == body.source_env_id:
                continue
            new_vars = apply_batch_to_global_vars(
                env.global_vars,
                mode=body.mode,
                keys=body.keys,
                source_vars=source_vars,
                default_values=body.default_values,
                overwrite=body.overwrite,
            )
            prepared.append((env, new_vars))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    updated = []
    async with in_transaction():
        for env, new_vars in prepared:
            env.global_vars = new_vars
            await env.save()
            updated.append({"id": env.id, "name": env.name})

    return {
        "mode": body.mode,
        "keys": body.keys,
        "updated_count": len(updated),
        "updated": updated,
    }


# 获取测试环境列表
@router.get('', summary='环境列表', status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(ENVIRONMENT_VIEW))])
async def get_environments(project_id: int | None = None):
    # 只查询未删除的环境
    query = Environment.filter(is_del=False).prefetch_related('project').order_by("-id")
    # 若指定项目，校验项目是否存在且未删除
    if project_id:
        project = await Project.get_or_none(id=project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在或已被删除")
        query = query.filter(project=project)
    # 构造返回数据
    data = []
    for environment in await query:
        data.append({
            "id": environment.id,
            "name": environment.name,
            "username": environment.username,
            "project": environment.project.name,
            "host": environment.host,
            "global_vars": environment.global_vars,
            "default_headers": environment.default_headers or [],
            "create_time": environment.create_time,
            "update_time": environment.update_time,
            "is_del": environment.is_del  # 新增：返回删除状态
        })
    return data


# 获取单个测试环境详情
@router.get('/{environment_id}', summary='环境详情', response_model=EnvironmentSchemas,
            status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(ENVIRONMENT_VIEW))])
async def get_environment(environment_id: int):
    # 只查询未删除的环境
    environment = await Environment.get_or_none(id=environment_id, is_del=False)
    if not environment:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="环境不存在或已被删除")
    return EnvironmentSchemas(**_environment_dict(environment))


# 删除测试环境（逻辑删除）
@router.delete('/{environment_id}', summary='删除环境', status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(ENVIRONMENT_EDIT))])
async def delete_environment(environment_id: int):
    environment = await Environment.get_or_none(id=environment_id, is_del=False)
    if not environment:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="环境不存在或已被删除")
    # 逻辑删除：设置is_del=True
    environment.is_del = True
    await environment.save()


# 修改测试环境
@router.put('/{environment_id}', summary='修改环境', response_model=EnvironmentSchemas,
            status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(ENVIRONMENT_EDIT))])
async def update_environment(environment_id: int, item: UpdateEnvironmentForm):
    # 只更新未删除的环境
    environment = await Environment.get_or_none(id=environment_id, is_del=False)
    if not environment:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="环境不存在或已被删除")
    # 若更新项目ID，需校验新项目是否存在且未删除
    if item.project_id is not None:  # 假设UpdateForm新增了project_id字段（见下方schemas）
        project = await Project.get_or_none(id=item.project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目标项目不存在或已被删除")
    payload = item.model_dump(exclude_unset=True)
    if "global_vars" in payload:
        try:
            payload["global_vars"] = normalize_global_vars(payload["global_vars"])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if "default_headers" in payload:
        try:
            payload["default_headers"] = normalize_default_headers(payload["default_headers"])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    # 更新环境信息
    await environment.update_from_dict(payload)
    await environment.save()
    return EnvironmentSchemas(**_environment_dict(environment))


__all__ = ["router"]
