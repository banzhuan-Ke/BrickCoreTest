"""App 元素库 CRUD"""
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status

from app.core.platform.auth import get_current_username, is_authenticated, require_any_permissions, require_permissions
from app.core.infra.minio_client import is_minio_storage, minio_client
from app.modules.app.app_locator_validate import validate_element_payload
from app.modules.app.app_element_refs import collect_element_references, ensure_element_deletable
from app.core.platform.permissions import APP_CASE_EDIT, APP_ELEMENT_EDIT, APP_ELEMENT_VIEW
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.app import AppElement
from app.models.sys import Project
from app.schemas.app import AddAppElementForm, AppElementSchemas, AppTemplatePresignForm, UpdateAppElementForm

router = APIRouter(prefix="/elements", dependencies=[Depends(is_authenticated)], tags=["App元素库"])

APP_ELEMENT_WRITE_PERMS = (APP_ELEMENT_EDIT, APP_CASE_EDIT)
APP_TEMPLATE_MAX_BYTES = 2 * 1024 * 1024
PRESIGN_EXPIRES = 7200
APP_TEMPLATE_ALLOWED = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp"})


def _build_template_object_key(project_id: int, filename: str) -> str:
    safe = (filename or "template.png").replace("\\", "/").split("/")[-1].strip()
    if not safe or ".." in safe:
        safe = "template.png"
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else "png"
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"
    return f"app-elements/{project_id}/{uuid.uuid4().hex[:12]}.{ext}"


async def _ensure_unique_name(project_id: int, name: str, exclude_id: int | None = None) -> None:
    query = AppElement.filter(project_id=project_id, name=name, is_del=False)
    if exclude_id:
        query = query.exclude(id=exclude_id)
    if await query.exists():
        raise HTTPException(status_code=422, detail=f"元素名「{name}」已存在")


@router.post(
    "/upload-template",
    summary="上传图像模板（App 元素库 image 类型）",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_permissions(*APP_ELEMENT_WRITE_PERMS))],
)
async def upload_template_image(
    project_id: int = Query(..., description="项目ID"),
    file: UploadFile = File(...),
    user_info: dict = Depends(require_any_permissions(*APP_ELEMENT_WRITE_PERMS)),
):
    await assert_user_project_member(user_info, project_id)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法上传图像模板")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(content) > APP_TEMPLATE_MAX_BYTES:
        raise HTTPException(status_code=422, detail="模板图不能超过 2MB")

    content_type = (file.content_type or "").lower()
    if content_type not in APP_TEMPLATE_ALLOWED:
        raise HTTPException(status_code=422, detail="仅支持 png/jpg/webp 格式")

    object_key = _build_template_object_key(project_id, file.filename or "template.png")
    # 与 Runner 截图/预签名一致，使用主 bucket（test-results）；勿用 api_file_bucket
    ok = minio_client.upload_bytes(
        object_name=object_key,
        data=content,
        content_type=content_type,
        bucket_name=minio_client.bucket_name,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="模板上传失败")

    preview_url = minio_client.get_presigned_url_for_app_element(object_key, expires=PRESIGN_EXPIRES) or ""
    return {
        "data": {
            "object_key": object_key,
            "access_url": preview_url or minio_client.build_public_object_url(object_key),
            "size": len(content),
        }
    }


@router.post(
    "/template-presign",
    summary="批量获取图像模板预签名预览 URL",
    dependencies=[Depends(require_permissions(APP_ELEMENT_VIEW))],
)
async def presign_template_images(
    project_id: int = Query(..., description="项目ID"),
    item: AppTemplatePresignForm = Body(default_factory=AppTemplatePresignForm),
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    keys = (item.object_keys if item else []) or []
    if not is_minio_storage():
        return {"data": {k: k for k in keys if k}}
    valid = []
    prefix = f"app-elements/{project_id}/"
    for key in keys:
        name = str(key or "").strip().lstrip("/")
        if name.startswith(prefix) and ".." not in name:
            valid.append(name)
    if not valid:
        return {"data": {}}
    import asyncio

    loop = asyncio.get_running_loop()

    def _batch_urls(keys: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in keys:
            url = minio_client.get_presigned_url_for_app_element(key, PRESIGN_EXPIRES)
            if url:
                out[key] = url
        return out

    urls = await loop.run_in_executor(None, _batch_urls, valid)
    return {"data": urls or {}}


@router.post("", summary="创建元素", status_code=status.HTTP_201_CREATED, response_model=AppElementSchemas,
             dependencies=[Depends(require_any_permissions(*APP_ELEMENT_WRITE_PERMS))])
async def create_element(
    item: AddAppElementForm,
    user_info: dict = Depends(require_any_permissions(*APP_ELEMENT_WRITE_PERMS)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, item.project_id)
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    await _ensure_unique_name(item.project_id, item.name.strip())
    validate_element_payload(item.element_type, item.locator)
    payload = item.model_dump()
    payload["username"] = username
    return await AppElement.create(**payload, is_del=False, update_by=username)


@router.get("", summary="元素列表")
async def list_elements(
    project_id: int,
    page: int = 1,
    size: int = 20,
    name: str | None = None,
    element_type: str | None = None,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppElement.filter(project_id=project_id, is_del=False).order_by("-id")
    if name:
        query = query.filter(name__icontains=name)
    if element_type:
        query = query.filter(element_type=element_type)
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size)
    return {"data": [AppElementSchemas.model_validate(r) for r in rows], "total": total}


@router.get("/options", summary="元素名下拉（供步骤 locator_ref 选择）")
async def element_options(
    project_id: int,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    rows = await AppElement.filter(project_id=project_id, is_del=False).order_by("name").all()
    return {
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "element_type": r.element_type,
                "locator": r.locator,
                "remark": r.remark,
            }
            for r in rows
        ]
    }


@router.get("/{element_id}", response_model=AppElementSchemas,
            dependencies=[Depends(require_permissions(APP_ELEMENT_VIEW))])
async def get_element(element_id: int, user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW))):
    row = await AppElement.get_or_none(id=element_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="元素不存在")
    await assert_user_project_viewer(user_info, row.project_id)
    return row


@router.put("/{element_id}", response_model=AppElementSchemas,
            dependencies=[Depends(require_permissions(APP_ELEMENT_EDIT))])
async def update_element(
    element_id: int,
    item: UpdateAppElementForm,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_EDIT)),
    username: str = Depends(get_current_username),
):
    row = await AppElement.get_or_none(id=element_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="元素不存在")
    await assert_user_project_member(user_info, row.project_id)
    data = item.model_dump(exclude_unset=True)
    if data.get("name"):
        await _ensure_unique_name(row.project_id, data["name"].strip(), exclude_id=element_id)
    element_type = data.get("element_type", row.element_type)
    locator = data.get("locator", row.locator)
    if data.get("element_type") is not None or data.get("locator") is not None:
        validate_element_payload(element_type, locator if isinstance(locator, dict) else {})
    await row.update_from_dict(data)
    row.update_by = username
    await row.save()
    return row


@router.get(
    "/{element_id}/references",
    summary="查询元素库引用",
    dependencies=[Depends(require_permissions(APP_ELEMENT_VIEW))],
)
async def element_references(
    element_id: int,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    row = await AppElement.get_or_none(id=element_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="元素不存在")
    await assert_user_project_viewer(user_info, row.project_id)
    refs = await collect_element_references(row.project_id, row.name)
    return {"data": refs}


@router.delete("/{element_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(APP_ELEMENT_EDIT))])
async def delete_element(element_id: int, user_info: dict = Depends(require_permissions(APP_ELEMENT_EDIT))):
    row = await AppElement.get_or_none(id=element_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="元素不存在")
    await assert_user_project_member(user_info, row.project_id)
    await ensure_element_deletable(row)
    row.is_del = True
    await row.save()
