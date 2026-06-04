from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import OPERATION_LOG_VIEW, OPERATION_LOG_EDIT
from app.core.operation_log import resolve_route_info
from app.models.sys import OperationLog

router = APIRouter(
    prefix="/operation-logs",
    tags=["操作日志"],
    dependencies=[Depends(is_authenticated)]
)


@router.get("", summary="操作日志列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(OPERATION_LOG_VIEW))])
async def get_operation_logs(
    page: int = 1,
    size: int = 20,
    username: str | None = None,
    module: str | None = None,
    action: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None
):
    """查询操作日志列表"""
    query = OperationLog.all().order_by("-id")
    if username:
        query = query.filter(username__icontains=username)
    if module:
        query = query.filter(module=module)
    if action:
        query = query.filter(action__icontains=action)
    if start_date:
        query = query.filter(create_time__gte=start_date)
    if end_date:
        query = query.filter(create_time__lte=f"{end_date} 23:59:59")

    total = await query.count()
    data = await query.offset((page - 1) * size).limit(size)

    result = []
    for item in data:
        path_name = (item.path_name or "").strip()
        if not path_name:
            _, _, path_name = resolve_route_info(item.method, item.path)
        result.append({
            "id": item.id,
            "user_id": item.user_id,
            "username": item.username,
            "action": item.action,
            "module": item.module,
            "method": item.method,
            "path": item.path,
            "path_name": path_name,
            "params": item.params,
            "ip": item.ip,
            "status_code": item.status_code,
            "create_time": item.create_time.strftime("%Y-%m-%d %H:%M:%S") if item.create_time else ""
        })

    return {"total": total, "data": result}


class BatchDeleteForm(BaseModel):
    ids: list[int]


@router.delete("", summary="批量删除操作日志", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(OPERATION_LOG_EDIT))])
async def batch_delete_operation_logs(item: BatchDeleteForm):
    """批量删除操作日志"""
    if item.ids:
        await OperationLog.filter(id__in=item.ids).delete()
