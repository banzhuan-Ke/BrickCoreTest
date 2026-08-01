"""登录页配置 API"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.config import LOGIN_BG_DIR
from app.core.platform.login_page_config_service import (
    get_login_page_config,
    get_login_page_public_config,
    save_login_page_config,
)
from app.core.platform.permissions import LOGIN_PAGE_CONFIG_EDIT, LOGIN_PAGE_CONFIG_VIEW

router = APIRouter(prefix="/login-page", tags=["登录页配置"])

os.makedirs(LOGIN_BG_DIR, exist_ok=True)


class LoginPageConfigForm(BaseModel):
    pro_bg_key: str = Field(default="opt3", description="清新 Pro：opt1~opt4 或 custom")
    classic_bg_key: str = Field(default="classic1", description="经典背景：classic1~classic4、legacy 或 custom")
    pro_bg_url: str | None = Field(default=None, description="Pro 自定义背景 URL（key=custom 时）")
    classic_bg_url: str | None = Field(default=None, description="经典自定义背景 URL（key=custom 时）")
    welcome_title: str = Field(default="欢迎登录 BrickCore", max_length=200)
    footer_text: str = Field(default="© 2025-2026 BrickCore v1.5.0. All Rights Reserved.", max_length=500)
    show_register: bool = True
    bg_brick_count: int = Field(default=30, ge=0, le=60, description="漂浮积木数量")
    bg_star_count: int = Field(default=15, ge=0, le=40, description="四角星数量")
    bg_dot_count: int = Field(default=15, ge=0, le=40, description="半透明光点数量")
    bg_motion_enabled: bool = Field(default=True, description="是否启用漂浮动效")


@router.get("/public", summary="登录页公开配置（无需登录）")
async def get_public_login_page_config():
    return await get_login_page_public_config()


@router.get(
    "/config",
    summary="获取登录页配置（管理）",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(LOGIN_PAGE_CONFIG_VIEW))],
)
async def get_admin_login_page_config():
    return await get_login_page_config()


@router.put(
    "/config",
    summary="保存登录页配置",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(LOGIN_PAGE_CONFIG_EDIT))],
)
async def update_login_page_config(
    item: LoginPageConfigForm,
    username: str = Depends(get_current_username),
):
    return await save_login_page_config(
        pro_bg_key=item.pro_bg_key,
        classic_bg_key=item.classic_bg_key,
        pro_bg_url=item.pro_bg_url,
        classic_bg_url=item.classic_bg_url,
        welcome_title=item.welcome_title,
        footer_text=item.footer_text,
        show_register=item.show_register,
        bg_brick_count=item.bg_brick_count,
        bg_star_count=item.bg_star_count,
        bg_dot_count=item.bg_dot_count,
        bg_motion_enabled=item.bg_motion_enabled,
        username=username,
    )


@router.post(
    "/upload-background",
    summary="上传登录页背景图",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(LOGIN_PAGE_CONFIG_EDIT))],
)
async def upload_login_background(
    file: UploadFile = File(...),
    theme: str = Query(..., description="pro 或 classic"),
):
    if theme not in {"pro", "classic"}:
        raise HTTPException(status_code=400, detail="theme 仅支持 pro 或 classic")

    allowed = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    content_type = (file.content_type or "").lower()
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp 格式")

    max_size = 5 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg" if "jpeg" in content_type else ".png"

    unique_name = f"login_{theme}_{uuid.uuid4().hex[:10]}{ext}"
    file_path = os.path.join(LOGIN_BG_DIR, unique_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    url = f"/static/login-bg/{unique_name}"
    return {"url": url, "theme": theme}
