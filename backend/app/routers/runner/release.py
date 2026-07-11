"""Runner 客户端安装包下载与版本信息"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.core.platform.auth import is_authenticated_from_header_or_query
from app.core.runner.runner_release import (
    PACKAGE_FILENAME,
    build_client_release_info,
    runner_package_path,
)
from app.core.runner.runner_release_config_service import enrich_release_info
from app.schemas.runner import RunnerVersionResponse

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])


def _request_base_url(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    host = request.headers.get("host") or request.url.netloc
    scheme = forwarded or request.url.scheme
    return f"{scheme}://{host}"


@router.get(
    "/client-release",
    summary="Runner 客户端发布信息（版本 + 安装包是否可用）",
    response_model=RunnerVersionResponse,
)
async def runner_client_release(request: Request):
    """无需登录即可检查版本；安装包是否可用对所有人可见。"""
    base = _request_base_url(request)
    info = build_client_release_info(base)
    info = await enrich_release_info(info, base)
    return RunnerVersionResponse(**info)


@router.get(
    "/client-download",
    summary="下载 Runner 客户端安装包 zip",
)
async def runner_client_download(
    request: Request,
    _user_info: dict = Depends(is_authenticated_from_header_or_query),
):
    path = runner_package_path()
    if not path.is_file():
        hint = build_client_release_info(_request_base_url(request)).get("package_upload_hint", "")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"安装包尚未上传。请将 {PACKAGE_FILENAME} 放到服务器目录：{hint}",
        )
    return FileResponse(
        path,
        media_type="application/zip",
        filename=PACKAGE_FILENAME,
    )
