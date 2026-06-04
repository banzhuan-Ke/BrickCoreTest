"""Runner 上传预签名 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import verify_runner_token
from app.core.minio_client import is_minio_storage, minio_client
from app.schemas.runner import RunnerUploadPresignRequest, RunnerUploadPresignResponse

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])

PRESIGN_EXPIRES = 3600


@router.post(
    "/upload/presign",
    summary="获取 MinIO 预签名上传 URL",
    response_model=RunnerUploadPresignResponse,
    status_code=status.HTTP_200_OK,
)
async def runner_upload_presign(
    item: RunnerUploadPresignRequest,
    _ctx: dict = Depends(verify_runner_token),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，请使用 RUNNER_LEGACY 模式")

    upload_url = minio_client.get_presigned_put_url(
        item.filename,
        expires=PRESIGN_EXPIRES,
        content_type=item.content_type,
    )
    if not upload_url:
        raise HTTPException(status_code=500, detail="生成预签名上传 URL 失败")

    access_url = minio_client.build_public_object_url(item.filename)
    return RunnerUploadPresignResponse(
        upload_url=upload_url,
        object_key=item.filename,
        access_url=access_url,
        expires_in=PRESIGN_EXPIRES,
    )
