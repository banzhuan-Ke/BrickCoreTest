"""迭代测试资料库 API"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.platform.auth import is_authenticated, require_any_permissions, require_permissions
from app.core.platform.config import KNOWLEDGE_MAX_FILE_MB
from app.modules.knowledge.knowledge_embed_config import platform_vector_embed_allowed
from app.core.platform.edition import is_community_edition, knowledge_digitech_pack_enabled
from app.core.platform.permissions import KNOWLEDGE_EDIT, KNOWLEDGE_EXECUTE, KNOWLEDGE_VIEW
from app.modules.knowledge.constants import DOC_TYPES
from app.modules.knowledge import knowledge_service as svc
from urllib.parse import quote

from app.modules.knowledge.default_templates import (
    ensure_builtin_templates_on_disk,
    is_pptx_builtin_kind,
    list_builtin_templates,
    load_builtin_template_bytes,
)
from app.modules.knowledge.exec_records import list_recent_exec_records
from app.modules.knowledge import iteration_report as report_svc
from app.modules.knowledge.knowledge_audit import log_knowledge_operation
from app.modules.knowledge import template_variable_service as var_svc
from app.modules.knowledge.template_registry import list_template_variables
from app.schemas.ai import StandardResponse
from fastapi.responses import Response

router = APIRouter(prefix="/knowledge", tags=["迭代测试资料库"])


class FolderBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    iteration_label: Optional[str] = Field(None, max_length=50)
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    sort: int = 0


class FolderUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    iteration_label: Optional[str] = Field(None, max_length=50)
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    sort: Optional[int] = None


class ExecRecordRef(BaseModel):
    report_type: str = Field(..., description="api_suite|api_plan|ui_suite|ui_task|app_suite|app_plan")
    record_id: int


class IterationReportBody(BaseModel):
    folder_id: Optional[int] = None
    template_doc_id: Optional[int] = None
    document_ids: Optional[list[int]] = None
    input_docs: Optional[dict[str, Any]] = Field(
        None,
        description="按文件类型指定输入文档；值可为文档 id 或 id 列表（需求文档可多选）",
    )
    exec_records: Optional[list[ExecRecordRef]] = None
    ai_config_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=200)
    author: Optional[str] = Field(None, max_length=50)
    user_vars: Optional[dict[str, Any]] = None
    report_kind: Optional[str] = Field(
        "iteration_report",
        description="iteration_report|functional_report|performance_report|test_plan|test_scheme",
    )


class IterationReportPreviewBody(BaseModel):
    folder_id: Optional[int] = None
    template_doc_id: Optional[int] = None
    document_ids: Optional[list[int]] = None
    input_docs: Optional[dict[str, Any]] = Field(
        None,
        description="按文件类型指定输入文档；值可为文档 id 或 id 列表（需求文档可多选）",
    )
    exec_records: Optional[list[ExecRecordRef]] = None
    report_kind: Optional[str] = Field("iteration_report")


class CustomVariableBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=100)
    category: str = Field("custom", max_length=32)
    value_type: str = Field("text", max_length=20)
    value_schema: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    sort: int = 0


class CustomVariableUpdateBody(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=32)
    value_type: Optional[str] = Field(None, max_length=20)
    value_schema: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    sort: Optional[int] = None


class DocumentEmbedModeBody(BaseModel):
    embed_mode: str = Field(..., description="inherit|lexical_only|vector|none")


class TemplateDefaultsBody(BaseModel):
    mappings: dict[str, Any] = Field(
        ...,
        description="report_kind → template_doc_id；null 表示使用内置模板",
    )


class ArchiveFromRequirementBody(BaseModel):
    requirement_id: int
    folder_id: Optional[int] = None
    doc_type: str = Field(default="requirement", description="文档类型")
    title: Optional[str] = Field(None, max_length=200)
    replace_if_exists: bool = False


class ArchiveFromTextBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=200000)
    folder_id: Optional[int] = None
    doc_type: str = Field(default="summary")
    source_key: Optional[str] = Field(None, max_length=120, description="去重键，同键可替换")
    replace_if_exists: bool = False


class KnowledgeRefsEstimateBody(BaseModel):
    folder_ids: Optional[list[int]] = None
    document_ids: Optional[list[int]] = None


class KnowledgeRetrieveBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="检索问题或关键词")
    folder_ids: Optional[list[int]] = None
    document_ids: Optional[list[int]] = None
    top_k: int = Field(default=12, ge=1, le=30)
    max_chars: int = Field(default=32000, ge=500, le=64000)
    strategy: Optional[str] = Field(None, description="lexical|vector|hybrid，默认跟随项目配置")


class KnowledgeQaBody(BaseModel):
    mode: str = Field(default="retrieve", description="retrieve=仅检索 | smart=检索+LLM")
    query: str = Field(..., min_length=1, max_length=500, description="问题")
    folder_ids: Optional[list[int]] = None
    document_ids: Optional[list[int]] = None
    top_k: int = Field(default=12, ge=1, le=30)
    max_chars: int = Field(default=48000, ge=500, le=64000)
    strategy: Optional[str] = Field(None, description="lexical|vector|hybrid")
    ai_config_id: Optional[int] = Field(None, description="智能模式 LLM 配置，默认项目 knowledge_qa 或场景绑定")


class QaRecordsBatchDeleteBody(BaseModel):
    record_ids: list[int] = Field(..., min_length=1, description="待删除记录 ID")


def _resolve_project_id(user_info: dict, project_id: Optional[int]) -> int:
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    if not pid:
        raise HTTPException(status_code=400, detail="请先选择项目")
    return int(pid)


@router.get("/meta", summary="资料库能力元信息", dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))])
async def knowledge_meta(user_info: dict = Depends(is_authenticated)):
    from app.core.platform.platform_settings_service import get_knowledge_report_delete_mode
    from app.modules.knowledge.knowledge_embed_config import embed_capabilities_payload

    return StandardResponse(
        data={
            "community_edition": is_community_edition(),
            "knowledge_pack_enabled": knowledge_digitech_pack_enabled(),
            "max_file_mb": KNOWLEDGE_MAX_FILE_MB,
            "platform_vector_embed_enabled": platform_vector_embed_allowed(),
            "knowledge_delete_mode": await get_knowledge_report_delete_mode(),
            "doc_types": [{"value": k, "label": v} for k, v in DOC_TYPES.items()],
            "embed_capabilities": embed_capabilities_payload(),
            "report_kinds": [
                {
                    "value": k,
                    "label": v["title_suffix"],
                    "description": v.get("description", ""),
                }
                for k, v in report_svc.REPORT_KINDS.items()
            ],
        }
    )


@router.get(
    "/settings/schema",
    summary="资料库生成配置项说明",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def knowledge_settings_schema(user_info: dict = Depends(is_authenticated)):
    from app.modules.knowledge.knowledge_project_settings import settings_schema_payload

    return StandardResponse(data=settings_schema_payload())


@router.get(
    "/settings",
    summary="获取项目资料库生成配置",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def get_knowledge_settings(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_project_settings import (
        load_knowledge_project_settings,
        settings_schema_payload,
    )

    pid = _resolve_project_id(user_info, project_id)
    values = await load_knowledge_project_settings(pid)
    return StandardResponse(
        data={
            "project_id": pid,
            "values": values,
            "schema": settings_schema_payload(),
        }
    )


@router.put(
    "/settings",
    summary="保存项目资料库生成配置",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def update_knowledge_settings(
    body: dict[str, Any] = Body(...),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_project_settings import (
        extract_knowledge_settings_updates,
        save_knowledge_project_settings,
    )

    pid = _resolve_project_id(user_info, project_id)
    updates = extract_knowledge_settings_updates(body)
    try:
        values = await save_knowledge_project_settings(pid, updates)
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
    return StandardResponse(data={"project_id": pid, "values": values}, message="配置已保存")


@router.get("/folders", summary="文件夹列表", dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))])
async def list_folders(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    items = await svc.list_folders(pid)
    return StandardResponse(data={"items": items})


@router.get(
    "/folders/{folder_id}/report-input-slots",
    summary="迭代报告输入文档槽位（按文件类型）",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def folder_report_input_slots(
    folder_id: int,
    report_kind: str = Query("iteration_report"),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.input_doc_slots import GENERIC_REPORT_SLOT_PROFILES, build_folder_slot_preview

    pid = _resolve_project_id(user_info, project_id)
    profile = GENERIC_REPORT_SLOT_PROFILES.get(report_kind, GENERIC_REPORT_SLOT_PROFILES["iteration_report"])
    data = await build_folder_slot_preview(pid, folder_id, profile)
    return StandardResponse(data=data)


@router.post("/folders", summary="创建文件夹", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def create_folder(
    body: FolderBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.create_folder(
        pid,
        body.name,
        user_info.get("username", ""),
        description=body.description,
        iteration_label=body.iteration_label,
        date_start=body.date_start,
        date_end=body.date_end,
        sort=body.sort,
    )
    return StandardResponse(data=data, message="创建成功")


@router.put("/folders/{folder_id}", summary="更新文件夹", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def update_folder(
    folder_id: int,
    body: FolderUpdateBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    payload = body.model_dump(exclude_unset=True)
    data = await svc.update_folder(folder_id, pid, payload)
    return StandardResponse(data=data, message="更新成功")


@router.delete("/folders/{folder_id}", summary="删除文件夹", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def delete_folder(
    folder_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    await svc.delete_folder(folder_id, pid)
    await log_knowledge_operation(
        user_info,
        action="删除文件夹",
        path_name="资料库-删除文件夹",
        path=f"/ai/knowledge/folders/{folder_id}",
        method="DELETE",
        params={"folder_id": folder_id},
    )
    return StandardResponse(message="删除成功")


@router.get("/documents", summary="文档列表", dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))])
async def list_documents(
    project_id: Optional[int] = Query(None),
    folder_id: Optional[int] = Query(None),
    doc_type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.list_documents(
        pid,
        folder_id=folder_id,
        doc_type=doc_type,
        keyword=keyword,
        page=page,
        size=size,
    )
    return StandardResponse(data=data)


@router.post("/documents/upload", summary="上传文档", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    folder_id: Optional[int] = Form(None),
    title: Optional[str] = Form(None),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    file_name = file.filename or "upload.bin"
    data = await svc.upload_document(
        pid,
        file_name,
        raw,
        doc_type,
        user_info.get("username", ""),
        folder_id=folder_id,
        title=title,
    )
    msg = data.pop("template_warning", None) or "上传成功，正在后台解析"
    await log_knowledge_operation(
        user_info,
        action="上传文档",
        path_name="资料库-上传文档",
        path="/ai/knowledge/documents/upload",
        params={
            "document_id": data.get("id"),
            "doc_type": doc_type,
            "folder_id": folder_id,
            "file_name": file_name,
        },
    )
    return StandardResponse(data=data, message=msg)


@router.post(
    "/documents/archive-from-requirement",
    summary="需求归档到资料库",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def archive_from_requirement(
    body: ArchiveFromRequirementBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.archive_document_from_requirement(
        pid,
        user_info.get("username", ""),
        requirement_id=body.requirement_id,
        folder_id=body.folder_id,
        doc_type=body.doc_type,
        title=body.title,
        replace_if_exists=body.replace_if_exists,
    )
    msg = "已更新归档" if data.get("replaced") else "归档成功"
    await log_knowledge_operation(
        user_info,
        action="需求归档",
        path_name="资料库-需求归档",
        path="/ai/knowledge/documents/archive-from-requirement",
        params={
            "requirement_id": body.requirement_id,
            "folder_id": body.folder_id,
            "document_id": data.get("id"),
            "replaced": data.get("replaced"),
        },
    )
    return StandardResponse(data=data, message=msg)


@router.post(
    "/documents/archive-from-text",
    summary="文本归档到资料库",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def archive_from_text(
    body: ArchiveFromTextBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.archive_document_from_text(
        pid,
        user_info.get("username", ""),
        title=body.title,
        content=body.content,
        folder_id=body.folder_id,
        doc_type=body.doc_type,
        source_key=body.source_key,
        replace_if_exists=body.replace_if_exists,
    )
    msg = "已更新归档" if data.get("replaced") else "归档成功"
    await log_knowledge_operation(
        user_info,
        action="文本归档",
        path_name="资料库-文本归档",
        path="/ai/knowledge/documents/archive-from-text",
        params={
            "folder_id": body.folder_id,
            "document_id": data.get("id"),
            "source_key": body.source_key,
            "replaced": data.get("replaced"),
        },
    )
    return StandardResponse(data=data, message=msg)


@router.post(
    "/refs/estimate",
    summary="估算资料引用规模",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def estimate_knowledge_refs(
    body: KnowledgeRefsEstimateBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_context import estimate_knowledge_refs as _estimate

    pid = _resolve_project_id(user_info, project_id)
    data = await _estimate(
        pid,
        folder_ids=body.folder_ids,
        document_ids=body.document_ids,
    )
    return StandardResponse(data=data)


@router.post(
    "/retrieve",
    summary="RAG 检索资料库",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def retrieve_knowledge_refs(
    body: KnowledgeRetrieveBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_retrieve import retrieve_knowledge

    pid = _resolve_project_id(user_info, project_id)
    data = await retrieve_knowledge(
        pid,
        query=body.query,
        folder_ids=body.folder_ids,
        document_ids=body.document_ids,
        top_k=body.top_k,
        max_chars=body.max_chars,
        strategy=body.strategy,
    )
    return StandardResponse(data=data)


@router.get(
    "/qa/records",
    summary="资料问答历史列表",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def list_knowledge_qa_records(
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    mode: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_qa_history import list_qa_records

    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or ""
    data = await list_qa_records(pid, username=username, page=page, size=size, mode=mode)
    return StandardResponse(data=data)


@router.post(
    "/qa/records/batch-delete",
    summary="批量删除资料问答历史",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def batch_delete_knowledge_qa_records(
    body: QaRecordsBatchDeleteBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_qa_history import batch_delete_qa_records

    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or ""
    data = await batch_delete_qa_records(pid, username=username, record_ids=body.record_ids)
    return StandardResponse(data=data, message=f"已删除 {data['deleted_count']} 条")


@router.get(
    "/qa/records/{record_id}",
    summary="资料问答历史详情",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def get_knowledge_qa_record(
    record_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_qa_history import get_qa_record

    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or ""
    data = await get_qa_record(record_id, pid, username=username)
    return StandardResponse(data=data)


@router.delete(
    "/qa/records/{record_id}",
    summary="删除资料问答历史",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def delete_knowledge_qa_record(
    record_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.knowledge_qa_history import delete_qa_record

    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or ""
    await delete_qa_record(record_id, pid, username=username)
    return StandardResponse(message="已删除")


@router.post(
    "/qa",
    summary="资料问答（检索 / 智能）",
    dependencies=[Depends(require_any_permissions(KNOWLEDGE_VIEW, KNOWLEDGE_EXECUTE))],
)
async def knowledge_qa(
    body: KnowledgeQaBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.core.platform.permissions import get_user_permissions
    from app.models.sys import User
    from app.modules.knowledge.knowledge_qa import ask_knowledge, normalize_qa_mode
    from app.modules.knowledge.knowledge_qa_history import save_qa_record

    pid = _resolve_project_id(user_info, project_id)
    mode = normalize_qa_mode(body.mode)
    user = await User.get_or_none(id=user_info.get("id"), is_del=False).prefetch_related("roles")
    if not (user and user.is_superuser):
        if not user:
            raise HTTPException(status_code=403, detail="用户不存在或已禁用")
        allowed = set(await get_user_permissions(user))
        need = KNOWLEDGE_EXECUTE if mode == "smart" else KNOWLEDGE_VIEW
        if need not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"权限不足: {'智能问答' if mode == 'smart' else '资料检索'}需要 {need}",
            )
    data = await ask_knowledge(
        pid,
        mode=mode,
        query=body.query,
        folder_ids=body.folder_ids,
        document_ids=body.document_ids,
        top_k=body.top_k,
        max_chars=body.max_chars,
        strategy=body.strategy,
        ai_config_id=body.ai_config_id,
        username=user_info.get("username") or "",
    )
    record_id = await save_qa_record(
        pid,
        user_info.get("username") or "",
        mode=mode,
        query=body.query,
        result=data,
        folder_ids=body.folder_ids,
        document_ids=body.document_ids,
        top_k=body.top_k or 12,
    )
    data["record_id"] = record_id
    if mode == "smart":
        await log_knowledge_operation(
            user_info,
            action="资料智能问答",
            path_name="资料库-智能问答",
            path="/ai/knowledge/qa",
            params={"mode": mode, "query": body.query[:120], "hit_count": data.get("hit_count"), "record_id": record_id},
        )
    return StandardResponse(data=data)


@router.get("/documents/{doc_id}", summary="文档详情", dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))])
async def get_document(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.get_document_detail(doc_id, pid)
    return StandardResponse(data=data)


@router.get(
    "/documents/{doc_id}/preview",
    summary="文档解析预览",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def preview_document(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.get_document_preview(doc_id, pid)
    return StandardResponse(data=data)


@router.get(
    "/documents/{doc_id}/image-thumbnails",
    summary="文档嵌入图片缩略图",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def document_image_thumbnails(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    max_edge: int = Query(320, ge=64, le=960),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.get_document_image_thumbnails(doc_id, pid, max_edge=max_edge)
    return StandardResponse(data=data)


@router.get(
    "/documents/{doc_id}/chunks",
    summary="文档 RAG 分块列表",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def list_document_chunks(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.list_document_chunks(doc_id, pid, page=page, size=size)
    return StandardResponse(data=data)


@router.get(
    "/documents/{doc_id}/download",
    summary="下载原始文档",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def download_document(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    import mimetypes

    pid = _resolve_project_id(user_info, project_id)
    content, file_name = await svc.get_document_download_bytes(doc_id, pid)
    media = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    encoded = quote(file_name)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.delete("/documents/{doc_id}", summary="删除文档", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def delete_document(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    await svc.delete_document(doc_id, pid)
    await log_knowledge_operation(
        user_info,
        action="删除文档",
        path_name="资料库-删除文档",
        path=f"/ai/knowledge/documents/{doc_id}",
        method="DELETE",
        params={"document_id": doc_id},
    )
    return StandardResponse(message="删除成功")


@router.post(
    "/documents/{doc_id}/image-parse/stop",
    summary="停止识图任务",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def stop_document_image_parse(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    from app.modules.knowledge.knowledge_image_parse import request_stop_image_parse

    data = await request_stop_image_parse(doc_id, pid)
    return StandardResponse(data=data, message="已请求停止识图")


@router.post(
    "/documents/{doc_id}/images/{image_index}/reparse",
    summary="单张图片重新识图",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def reparse_document_image(
    doc_id: int,
    image_index: int,
    project_id: Optional[int] = Query(None),
    scope: str = Query("auto", description="auto | ocr | vision | all"),
    user_info: dict = Depends(is_authenticated),
):
    from fastapi import HTTPException

    from app.models.knowledge import AiKnowledgeDocument
    from app.modules.knowledge.knowledge_image_parse import (
        IMAGE_PARSE_STATUS_PARSING,
        get_image_parse_summary,
        schedule_reparse_document_image,
    )

    pid = _resolve_project_id(user_info, project_id)
    row = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=pid, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    ip = get_image_parse_summary(row.sections_json)
    if ip.get("status") == IMAGE_PARSE_STATUS_PARSING and not ip.get("single_reparse_index"):
        raise HTTPException(status_code=409, detail="文档批量识图进行中，请先停止或等待完成")
    schedule_reparse_document_image(
        doc_id,
        pid,
        image_index,
        username=user_info.get("username", ""),
        scope=scope,
    )
    return StandardResponse(message="已提交单张识图")


@router.post("/documents/{doc_id}/reparse", summary="重新解析", dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))])
async def reparse_document(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    image_mode: Optional[str] = Query(
        None,
        description="图片解析：default 按项目配置；enhanced 加强 Vision；off 跳过识图",
    ),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.reparse_document(
        doc_id,
        pid,
        image_mode=image_mode,
        username=user_info.get("username", ""),
    )
    return StandardResponse(data=data, message="已提交重新解析")


class ReparseDocumentsBody(BaseModel):
    folder_id: Optional[int] = Field(None, description="文件夹 ID；可与 document_ids 组合（取交集）")
    document_ids: Optional[list[int]] = Field(None, description="文档 ID 列表；可与 folder_id 组合（取交集）")
    image_mode: Optional[str] = Field(
        None,
        description="图片解析：default | enhanced | off",
    )


@router.post(
    "/documents/reparse",
    summary="批量重新解析（v2 回填）",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def reparse_documents_batch(
    body: ReparseDocumentsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.reparse_documents_batch(
        pid,
        folder_id=body.folder_id,
        document_ids=body.document_ids,
        image_mode=body.image_mode,
        username=user_info.get("username", ""),
    )
    await log_knowledge_operation(
        user_info,
        action="批量重新解析文档",
        path_name="资料库-批量重新解析",
        path="/ai/knowledge/documents/reparse",
        params={
            "folder_id": body.folder_id,
            "document_ids": body.document_ids,
            "scheduled_count": data.get("scheduled_count"),
        },
    )
    return StandardResponse(
        data=data,
        message=f"已提交 {data.get('scheduled_count', 0)} 份文档重新解析",
    )


@router.put(
    "/documents/{doc_id}/embed-mode",
    summary="设置文档 Embedding 策略",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def set_document_embed_mode(
    doc_id: int,
    body: DocumentEmbedModeBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.update_document_embed_mode(doc_id, pid, body.embed_mode)
    await log_knowledge_operation(
        user_info,
        action="设置Embedding策略",
        path_name="资料库-文档Embedding策略",
        path=f"/ai/knowledge/documents/{doc_id}/embed-mode",
        params={"document_id": doc_id, "embed_mode": body.embed_mode},
    )
    return StandardResponse(data=data, message="Embedding 策略已更新")


@router.post(
    "/documents/{doc_id}/reindex-rag",
    summary="重建文档词法分块索引",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def reindex_document_rag(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.knowledge import AiKnowledgeDocument
    from app.modules.knowledge.constants import PARSE_STATUS_READY
    from app.modules.knowledge.knowledge_embed import will_chain_vector_index
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings
    from app.modules.knowledge.knowledge_rag import schedule_reindex_document_rag
    from app.modules.knowledge.knowledge_service import document_to_dict

    pid = _resolve_project_id(user_info, project_id)
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=pid, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.parse_status != PARSE_STATUS_READY:
        raise HTTPException(status_code=400, detail="文档尚未解析完成，请稍候或点击「重新解析」")
    if doc.embed_status == "indexing":
        return StandardResponse(
            data=document_to_dict(doc),
            message="词法索引正在后台处理，请稍候刷新列表",
        )
    settings = await load_knowledge_project_settings(pid)
    username = user_info.get("username") or ""
    vector_queued = will_chain_vector_index(doc, settings)
    doc.embed_status = "indexing"
    doc.vector_status = "none"
    doc.vector_model = None
    doc.vector_error = None
    await doc.save()
    schedule_reindex_document_rag(
        doc.id,
        pid,
        username=username,
        settings=settings,
    )
    await log_knowledge_operation(
        user_info,
        action="重建RAG索引",
        path_name="资料库-重建RAG索引",
        path=f"/ai/knowledge/documents/{doc_id}/reindex-rag",
        params={"document_id": doc_id, "vector_queued": vector_queued, "lexical_queued": True},
    )
    msg = "词法索引已在后台处理"
    if vector_queued:
        msg += "，向量索引将随后自动重建"
    data = document_to_dict(doc)
    data.update(
        {
            "lexical_queued": True,
            "vector_queued": vector_queued,
            "vector_chained": vector_queued,
        }
    )
    return StandardResponse(data=data, message=msg)


@router.post(
    "/documents/{doc_id}/reindex-vector",
    summary="重建文档向量索引",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def reindex_document_vector(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.knowledge import AiKnowledgeDocument
    from app.modules.knowledge.knowledge_embed import schedule_index_document_vectors
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

    pid = _resolve_project_id(user_info, project_id)
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=pid, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.embed_status != "ready":
        raise HTTPException(status_code=400, detail="请先建立词法分块索引")
    if getattr(doc, "vector_status", None) == "indexing":
        from app.modules.knowledge.knowledge_service import document_to_dict

        return StandardResponse(
            data=document_to_dict(doc),
            message="向量索引正在后台处理，请稍候刷新列表",
        )
    settings = await load_knowledge_project_settings(pid)
    doc.vector_status = "indexing"
    doc.vector_error = None
    await doc.save()
    schedule_index_document_vectors(
        doc.id,
        pid,
        username=user_info.get("username") or "",
        settings=settings,
        force=True,
    )
    await log_knowledge_operation(
        user_info,
        action="重建向量索引",
        path_name="资料库-重建向量索引",
        path=f"/ai/knowledge/documents/{doc_id}/reindex-vector",
        params={"document_id": doc_id, "vector_queued": True},
    )
    return StandardResponse(
        data={
            "chunk_count": doc.chunk_count or 0,
            "vector_status": doc.vector_status,
            "vector_model": doc.vector_model,
            "vector_queued": True,
        },
        message="向量索引已在后台处理，请稍候刷新列表",
    )


@router.post(
    "/documents/{doc_id}/reindex-all",
    summary="重建文档词法+向量索引",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def reindex_document_all(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.knowledge import AiKnowledgeDocument
    from app.modules.knowledge.constants import PARSE_STATUS_READY
    from app.modules.knowledge.knowledge_embed import will_chain_vector_index
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings
    from app.modules.knowledge.knowledge_rag import schedule_reindex_document_all
    from app.modules.knowledge.knowledge_service import document_to_dict

    pid = _resolve_project_id(user_info, project_id)
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=pid, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.parse_status != PARSE_STATUS_READY:
        raise HTTPException(status_code=400, detail="文档尚未解析完成，请稍候或点击「重新解析」")
    if doc.embed_status == "indexing":
        return StandardResponse(
            data=document_to_dict(doc),
            message="词法索引正在后台处理，请稍候刷新列表",
        )
    settings = await load_knowledge_project_settings(pid)
    username = user_info.get("username") or ""
    vector_queued = will_chain_vector_index(doc, settings)
    doc.embed_status = "indexing"
    doc.vector_status = "none"
    doc.vector_model = None
    doc.vector_error = None
    await doc.save()
    schedule_reindex_document_all(
        doc.id,
        pid,
        username=username,
        settings=settings,
    )
    await log_knowledge_operation(
        user_info,
        action="重建全部索引",
        path_name="资料库-重建全部索引",
        path=f"/ai/knowledge/documents/{doc_id}/reindex-all",
        params={
            "document_id": doc_id,
            "vector_queued": vector_queued,
            "lexical_queued": True,
        },
    )
    msg = "词法索引已在后台处理"
    if vector_queued:
        msg += "，向量索引将随后自动重建"
    data = document_to_dict(doc)
    data.update(
        {
            "lexical_queued": True,
            "vector_queued": vector_queued,
            "vector_chained": vector_queued,
        }
    )
    return StandardResponse(data=data, message=msg)


@router.post(
    "/documents/{doc_id}/rebuild-digest",
    summary="重建文档 AI 摘要缓存",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EXECUTE))],
)
async def rebuild_document_digest(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    ai_config_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.knowledge import AiKnowledgeDocument
    from app.modules.knowledge.constants import PARSE_STATUS_FAILED, PARSE_STATUS_READY
    from app.modules.knowledge.knowledge_digest_cache import schedule_rebuild_document_digest
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings
    from app.modules.knowledge.knowledge_service import document_to_dict

    pid = _resolve_project_id(user_info, project_id)
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=pid, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.parse_status == PARSE_STATUS_FAILED:
        err = (doc.parse_error or "").strip()
        raise HTTPException(
            status_code=400,
            detail=f"文档解析失败{('：' + err) if err else ''}，请先「重新解析」",
        )
    if doc.parse_status != PARSE_STATUS_READY:
        raise HTTPException(status_code=400, detail="文档尚未解析完成，请稍候或点击「重新解析」")
    if getattr(doc, "digest_status", None) == "indexing":
        return StandardResponse(
            data=document_to_dict(doc),
            message="摘要正在后台生成，请稍候刷新列表",
        )
    settings = await load_knowledge_project_settings(pid)
    doc.digest_status = "indexing"
    doc.digest_error = None
    await doc.save()
    schedule_rebuild_document_digest(
        doc_id,
        pid,
        ai_config_id=ai_config_id,
        settings=settings,
    )
    await log_knowledge_operation(
        user_info,
        action="重建摘要缓存",
        path_name="资料库-重建摘要缓存",
        path=f"/ai/knowledge/documents/{doc_id}/rebuild-digest",
        params={"document_id": doc_id, "ai_config_id": ai_config_id, "digest_queued": True},
    )
    data = document_to_dict(doc)
    data["digest_queued"] = True
    return StandardResponse(data=data, message="摘要已在后台生成，请稍候刷新列表")


@router.get(
    "/templates/defaults",
    summary="按报告类型的默认模板映射",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def get_template_defaults(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.template_defaults import list_default_template_mappings

    pid = _resolve_project_id(user_info, project_id)
    data = await list_default_template_mappings(pid)
    return StandardResponse(data=data)


@router.put(
    "/templates/defaults",
    summary="保存按报告类型的默认模板映射",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def update_template_defaults(
    body: TemplateDefaultsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.knowledge.template_defaults import (
        list_default_template_mappings,
        save_default_template_mappings,
    )

    pid = _resolve_project_id(user_info, project_id)
    await save_default_template_mappings(pid, body.mappings)
    data = await list_default_template_mappings(pid)
    return StandardResponse(data=data, message="默认模板映射已保存")


@router.post(
    "/templates/{doc_id}/set-default",
    summary="设为默认输出模板",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def set_default_template(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await svc.set_default_template(doc_id, pid)
    return StandardResponse(data=data, message="已设为默认模板")


@router.get("/templates/variables", summary="模板变量说明", dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))])
async def template_variables(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    items = await list_template_variables(pid)
    return StandardResponse(data={"items": items})


@router.post(
    "/templates/variables",
    summary="新增自定义模板变量",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def create_template_variable(
    body: CustomVariableBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await var_svc.create_custom_variable(
        pid,
        user_info.get("username", ""),
        name=body.name,
        label=body.label,
        category=body.category,
        value_type=body.value_type,
        value_schema=body.value_schema,
        description=body.description,
        default_value=body.default_value,
        sort=body.sort,
    )
    return StandardResponse(data=data, message="已添加自定义变量")


@router.put(
    "/templates/variables/{var_id}",
    summary="更新自定义模板变量",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def update_template_variable(
    var_id: int,
    body: CustomVariableUpdateBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await var_svc.update_custom_variable(
        var_id,
        pid,
        label=body.label,
        category=body.category,
        value_type=body.value_type,
        value_schema=body.value_schema,
        description=body.description,
        default_value=body.default_value,
        sort=body.sort,
    )
    return StandardResponse(data=data, message="已更新")


@router.delete(
    "/templates/variables/{var_id}",
    summary="删除自定义模板变量",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def delete_template_variable(
    var_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    await var_svc.delete_custom_variable(var_id, pid)
    return StandardResponse(message="已删除")


@router.get(
    "/templates/default/list",
    summary="内置通用模板列表",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def list_default_templates():
    return StandardResponse(data={"items": list_builtin_templates()})


@router.get(
    "/templates/default/download",
    summary="下载内置通用模板",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def download_default_template(kind: str = Query("iteration_report", description="模板类型")):
    ensure_builtin_templates_on_disk()
    if is_pptx_builtin_kind(kind) and not knowledge_digitech_pack_enabled():
        raise HTTPException(status_code=400, detail="行业定制模板未开通，请联系管理员")
    try:
        content, filename = load_builtin_template_bytes(kind)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    encoded = quote(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pptx":
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post(
    "/documents/{doc_id}/validate-template",
    summary="校验模板占位符",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def validate_template(
    doc_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.validate_document_template(doc_id, pid)
    msg = "校验通过" if not data.get("has_unknown") else f"发现未知占位符: {', '.join(data.get('unknown', []))}"
    return StandardResponse(data=data, message=msg)


@router.get(
    "/exec-records/recent",
    summary="最近执行记录（报告向导）",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def recent_exec_records(
    project_id: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    items = await list_recent_exec_records(pid, limit=limit)
    return StandardResponse(data={"items": items})


@router.get(
    "/iteration-reports",
    summary="生成记录列表",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def list_iteration_reports(
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.list_iteration_reports(pid, page=page, size=size)
    return StandardResponse(data=data)


@router.get(
    "/iteration-reports/template-inspect",
    summary="检查报告模板占位符",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def inspect_iteration_report_template(
    project_id: Optional[int] = Query(None),
    template_doc_id: Optional[int] = Query(None),
    report_kind: str = Query("iteration_report"),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.inspect_report_template(pid, template_doc_id, report_kind=report_kind)
    return StandardResponse(data=data)


@router.post(
    "/iteration-reports/preview",
    summary="生成前预览（占位符与统计摘要，不调用 LLM）",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def preview_iteration_report(
    body: IterationReportPreviewBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    exec_refs = [r.model_dump() for r in (body.exec_records or [])]
    data = await report_svc.preview_report_inputs(
        pid,
        folder_id=body.folder_id,
        template_doc_id=body.template_doc_id,
        document_ids=body.document_ids,
        input_docs=body.input_docs,
        exec_records=exec_refs,
        report_kind=body.report_kind or "iteration_report",
    )
    return StandardResponse(data=data)


@router.post(
    "/iteration-reports",
    summary="生成迭代测试报告",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EXECUTE))],
)
async def create_iteration_report(
    body: IterationReportBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    exec_refs = [r.model_dump() for r in (body.exec_records or [])]
    data = await report_svc.start_iteration_report(
        pid,
        user_info.get("username", ""),
        folder_id=body.folder_id,
        template_doc_id=body.template_doc_id,
        document_ids=body.document_ids,
        input_docs=body.input_docs,
        exec_records=exec_refs,
        ai_config_id=body.ai_config_id,
        title=body.title,
        author=body.author,
        user_vars=body.user_vars,
        report_kind=body.report_kind,
    )
    return StandardResponse(data=data, message="报告生成任务已提交")


@router.get(
    "/iteration-reports/{report_id}",
    summary="查询报告生成状态",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def get_iteration_report(
    report_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.get_iteration_report_detail(report_id, pid)
    return StandardResponse(data=data)


@router.post(
    "/iteration-reports/{report_id}/retry",
    summary="重试失败的报告生成",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EXECUTE))],
)
async def retry_iteration_report(
    report_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.retry_iteration_report(report_id, pid)
    await log_knowledge_operation(
        user_info,
        action="重试报告生成",
        path_name="资料库-重试报告生成",
        path=f"/ai/knowledge/iteration-reports/{report_id}/retry",
        params={"report_id": report_id, "status": data.get("status")},
    )
    return StandardResponse(data=data, message="已重新提交生成任务")


@router.delete(
    "/iteration-reports/{report_id}",
    summary="删除生成记录",
    dependencies=[Depends(require_permissions(KNOWLEDGE_EDIT))],
)
async def delete_iteration_report(
    report_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    data = await report_svc.delete_iteration_report(report_id, pid)
    await log_knowledge_operation(
        user_info,
        action="删除生成记录",
        path_name="资料库-删除生成记录",
        path=f"/ai/knowledge/iteration-reports/{report_id}",
        params={"report_id": report_id, "delete_result": data.get("delete_result")},
    )
    return StandardResponse(data=data, message="已删除")


@router.get(
    "/iteration-reports/{report_id}/download",
    summary="下载迭代报告",
    dependencies=[Depends(require_permissions(KNOWLEDGE_VIEW))],
)
async def download_iteration_report(
    report_id: int,
    project_id: Optional[int] = Query(None),
    attachment: str = Query("main", description="main|bug_workbook"),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    content, file_name = await report_svc.get_report_download_bytes(
        report_id, pid, attachment=attachment
    )
    if file_name.endswith(".xlsx"):
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif file_name.endswith(".pptx"):
        media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    from urllib.parse import quote

    encoded = quote(file_name)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
