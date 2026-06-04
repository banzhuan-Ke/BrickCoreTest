"""
文件访问路由 - 提供 MinIO 预签名 URL 和头像上传
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from app.core.minio_client import minio_client, is_minio_storage
from app.core.auth import is_authenticated
from app.core.config import AVATAR_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["文件管理"])

# 确保头像目录存在
os.makedirs(AVATAR_DIR, exist_ok=True)


@router.post("/batch-presigned-urls")
async def get_batch_presigned_urls(request: Request):
    """
    批量获取预签名 URL
    请求体: {"filenames": ["a.png", "b.png"]}
    """
    try:
        print("[DEBUG] ===== Entering batch-presigned-urls =====")
        
        # 检查 Content-Type
        content_type = request.headers.get('content-type', '')
        print(f"[DEBUG] Content-Type: {content_type}")
        
        # 手动读取 body
        body_bytes = await request.body()
        print(f"[DEBUG] Body bytes length: {len(body_bytes)}")
        
        body_str = body_bytes.decode('utf-8') if body_bytes else "{}"
        print(f"[DEBUG] Body string: {body_str}")
        
        try:
            data = json.loads(body_str)
        except json.JSONDecodeError as e:
            print(f"[DEBUG] JSON parse error: {e}")
            return JSONResponse(
                status_code=400,
                content={"code": 400, "data": {}, "message": f"Invalid JSON: {str(e)}"}
            )
        
        filenames = data.get("filenames", [])
        print(f"[DEBUG] filenames: {filenames}")
        
        if not isinstance(filenames, list):
            return JSONResponse(
                status_code=400,
                content={"code": 400, "data": {}, "message": "filenames must be a list"}
            )
        
        if not is_minio_storage():
            result = {f: f for f in filenames if f}
            return {"code": 200, "data": result, "message": "Direct URLs"}
        
        # 过滤处理
        valid_filenames = []
        direct_urls = {}
        
        for f in filenames:
            if not f:
                continue
            if f.startswith('http'):
                direct_urls[f] = f
            else:
                valid_filenames.append(f)
        
        print(f"[DEBUG] valid_filenames: {valid_filenames}")
        
        # 生成预签名 URL（放到线程池执行，避免阻塞事件循环）
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, minio_client.get_batch_presigned_urls, valid_filenames, 7200
        )
        
        # 合并直接 URL
        result.update(direct_urls)
        
        print(f"[DEBUG] result count: {len(result)}")
        return {"code": 200, "data": result, "message": "success"}
        
    except Exception as e:
        print(f"[DEBUG] Exception: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"code": 500, "data": {}, "message": f"Server error: {str(e)}"}
        )


@router.post("/presigned-url")
async def get_presigned_url(request: Request):
    """获取单个文件的预签名 URL"""
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8') if body_bytes else "{}"
        data = json.loads(body_str)
        
        filename = data.get("filename", "")
        
        if not filename:
            return {"code": 400, "data": None, "message": "filename is required"}
        
        if not is_minio_storage():
            return {"code": 200, "data": filename, "message": "Direct URL"}
        
        loop = asyncio.get_running_loop()
        url = await loop.run_in_executor(
            None, minio_client.get_presigned_url, filename, 7200
        )
        if url:
            url = url.replace('https://', 'http://')
            return {"code": 200, "data": url, "message": "success"}
        return {"code": 500, "data": None, "message": "Failed to generate URL"}
    except Exception as e:
        print(f"[DEBUG] Exception: {e}")
        return {"code": 500, "data": None, "message": str(e)}


@router.get("/test")
async def test_endpoint():
    """测试接口是否正常"""
    return {
        "code": 200,
        "data": "OK",
        "message": "Files router is working",
        "storage_type": "minio" if is_minio_storage() else "aliyun"
    }


@router.post("/upload-avatar", summary="上传头像")
async def upload_avatar(file: UploadFile = File(...), user_info: dict = Depends(is_authenticated)):
    """
    上传用户头像，保存到本地 static/avatars 目录
    返回可访问的 URL 路径（如 /static/avatars/xxx.jpg）
    """
    # 校验文件类型
    allowed_content_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    content_type = file.content_type or ""
    if content_type not in allowed_content_types:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/gif/webp 格式的图片")
    
    # 校验文件大小（最大 2MB）
    max_size = 2 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=400, detail="图片大小不能超过 2MB")
    
    # 生成唯一文件名
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext or ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        ext = ".png"
    unique_name = f"avatar_{user_info.get('id')}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(AVATAR_DIR, unique_name)
    
    # 保存文件
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    
    # 返回可访问的 URL
    avatar_url = f"/static/avatars/{unique_name}"
    return {"code": 200, "data": avatar_url, "message": "上传成功"}
