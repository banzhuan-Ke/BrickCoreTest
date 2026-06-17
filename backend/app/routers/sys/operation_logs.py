from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from tortoise import connections

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
    rows = await query.offset((page - 1) * size).limit(size).values(
        "id",
        "user_id",
        "username",
        "action",
        "module",
        "method",
        "path",
        "path_name",
        "ip",
        "status_code",
        "create_time",
    )

    result = []
    for item in rows:
        path_name = (item.get("path_name") or "").strip()
        if not path_name:
            _, _, path_name = resolve_route_info(item["method"], item["path"])
        create_time = item.get("create_time")
        result.append({
            "id": item["id"],
            "user_id": item["user_id"],
            "username": item["username"],
            "action": item["action"],
            "module": item["module"],
            "method": item["method"],
            "path": item["path"],
            "path_name": path_name,
            # 列表不加载 params（Runner 屏幕上报等可能含超大 base64，会导致接口/页面卡死）
            "params": {},
            "ip": item["ip"],
            "status_code": item["status_code"],
            "create_time": create_time.strftime("%Y-%m-%d %H:%M:%S") if create_time else "",
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


NOISE_LOG_PATHS = (
    "/runner/device-screen",
    "/runner/device-log",
    "/runner/device-log/batch",
    "/perf/workers/heartbeat",
)

# 历史遗留：压测秒级上报（已改为不再写入，但需清理旧数据）
NOISE_LOG_PATH_LIKE = (
    "/perf/workers/%/report",
)


async def _purge_noise_batch(batch_size: int) -> int:
    """按批删除噪音日志（单条 SQL，避免一次加载超大 JSON 行）。"""
    conn = connections.get("default")
    placeholders = ",".join(["%s"] * len(NOISE_LOG_PATHS))
    like_clause = " OR ".join(["path LIKE %s"] * len(NOISE_LOG_PATH_LIKE))
    sql = (
        f"DELETE FROM operation_log WHERE (path IN ({placeholders})"
        f"{(' OR ' + like_clause) if like_clause else ''}) LIMIT %s"
    )
    params = [*NOISE_LOG_PATHS, *NOISE_LOG_PATH_LIKE, batch_size]
    rowcount, _ = await conn.execute_query(sql, params)
    return int(rowcount or 0)


@router.delete(
    "/noise",
    summary="清理机器高频噪音日志（分批）",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(OPERATION_LOG_EDIT))],
)
async def purge_noise_operation_logs(
    batch_size: int = Query(500, ge=100, le=2000, description="每批删除条数"),
):
    """
    分批删除 Runner 屏幕/日志上报、压测 Worker 心跳/秒级上报等历史噪音日志。
    前端可循环调用直至 deleted=0，避免单次删除数万条导致超时。
    """
    deleted = await _purge_noise_batch(batch_size)
    return {
        "deleted": deleted,
        "done": deleted == 0,
        "paths": list(NOISE_LOG_PATHS),
        "path_like": list(NOISE_LOG_PATH_LIKE),
    }
