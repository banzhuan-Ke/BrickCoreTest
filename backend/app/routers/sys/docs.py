"""
平台文档中心：内置 Markdown + 自定义文档/视频/附件上传
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, require_permissions
from app.core.platform.edition import is_community_edition
from app.core.shared.docs_catalog import (
    BUILTIN_DOC_IDS,
    build_manage_builtin_items,
    get_builtin_doc_entries,
    get_builtin_doc_tree,
    is_builtin_doc,
    is_builtin_entry,
    is_builtin_group,
    merge_builtin_tree,
    read_builtin_markdown,
)
from app.core.infra.minio_client import minio_client, is_minio_storage
from app.core.platform.config import API_FILE_BUCKET
from app.core.platform.permissions import DOCS_EDIT, DOCS_VIEW
from app.models.sys import PlatformDoc
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/docs", tags=["文档中心"])

PLATFORM_DOCS_PREFIX = "platform-docs/"
ALLOWED_UPLOAD_EXT = {
    ".mp4", ".webm", ".mov", ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".zip",
}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB

_MD_DOC_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\((?:\./)?([a-zA-Z0-9_-]+)\.md([^)]*)\)",
)


def _rewrite_md_doc_links(md: str) -> str:
    """将 Markdown 内 .md 相对链接改写为文档中心路由，避免浏览器请求 /xxx.md 404。"""

    def repl(match: re.Match[str]) -> str:
        label, stem, tail = match.group(1), match.group(2).lower(), match.group(3) or ""
        doc_id = "home" if stem == "index" else stem
        if doc_id not in BUILTIN_DOC_IDS:
            return match.group(0)
        frag = tail if tail.startswith("#") else ""
        return f"[{label}](/docs?doc={doc_id}{frag})"

    return _MD_DOC_LINK_RE.sub(repl, md)


def _md_to_html(text: str) -> str:
    if not text:
        return ""
    text = _rewrite_md_doc_links(text)
    try:
        import markdown as md_lib
        return md_lib.markdown(
            text,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists", "attr_list"],
        )
    except Exception:
        return f"<pre>{text}</pre>"


def _doc_to_dict(doc: PlatformDoc, file_access_url: str = "") -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "parent_id": doc.parent_id,
        "builtin_id": doc.builtin_id or "",
        "doc_type": doc.doc_type,
        "content": doc.content or "",
        "file_key": doc.file_key or "",
        "file_access_url": file_access_url,
        "link_url": doc.link_url or "",
        "sort_order": doc.sort_order,
        "is_published": doc.is_published,
        "is_hidden": doc.is_hidden,
        "create_by": doc.create_by,
        "update_by": doc.update_by or "",
        "create_time": doc.create_time.strftime("%Y-%m-%d %H:%M:%S") if doc.create_time else "",
        "update_time": doc.update_time.strftime("%Y-%m-%d %H:%M:%S") if doc.update_time else "",
    }


async def _presigned(file_key: str) -> str:
    if not file_key:
        return ""
    if file_key.startswith("http://") or file_key.startswith("https://"):
        return file_key
    if not is_minio_storage():
        return file_key
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: minio_client.get_presigned_url(file_key, 7200, API_FILE_BUCKET)
    )


async def _load_builtin_overrides() -> dict[str, PlatformDoc]:
    rows = await PlatformDoc.filter(builtin_id__not_isnull=True, is_del=False)
    return {r.builtin_id: r for r in rows if r.builtin_id}


def _custom_doc_node(doc: PlatformDoc) -> dict[str, Any]:
    return {
        "id": f"custom-{doc.id}",
        "doc_id": doc.id,
        "title": doc.title,
        "type": "custom",
        "doc_type": doc.doc_type,
        "parent_id": doc.parent_id,
    }


def build_custom_tree(rows: list[PlatformDoc]) -> list[dict[str, Any]]:
    """构建自定义一级目录树（group + 其下文档；无目录的文档归入「团队文档」）。"""
    groups = [r for r in rows if r.doc_type == "group" and not r.parent_id]
    docs = [r for r in rows if r.doc_type != "group"]
    tree: list[dict[str, Any]] = []

    for g in sorted(groups, key=lambda x: (x.sort_order, x.id)):
        children = [
            _custom_doc_node(d)
            for d in sorted(docs, key=lambda x: (x.sort_order, x.id))
            if d.parent_id == g.id
        ]
        tree.append({
            "id": f"custom-group-{g.id}",
            "group_id": g.id,
            "title": g.title,
            "type": "group",
            "doc_type": "group",
            "is_custom_group": True,
            "sort_order": g.sort_order,
            "children": children,
        })

    orphans = [d for d in docs if not d.parent_id]
    if orphans:
        tree.append({
            "id": "group-custom-orphan",
            "title": "团队文档",
            "type": "group",
            "doc_type": "group",
            "is_custom_group": False,
            "is_orphan_group": True,
            "children": [_custom_doc_node(d) for d in sorted(orphans, key=lambda x: (x.sort_order, x.id))],
        })
    return tree


def _validate_doc_body(body: "PlatformDocBody") -> None:
    if body.doc_type == "group":
        if body.parent_id:
            raise HTTPException(status_code=400, detail="一级目录不支持设置父级")
        if body.content or body.file_key or body.link_url:
            raise HTTPException(status_code=400, detail="目录类型无需填写正文或附件")
        return
    if body.doc_type not in ("markdown", "video", "file", "link"):
        raise HTTPException(status_code=400, detail="doc_type 无效")


async def _validate_parent_id(parent_id: Optional[int]) -> None:
    if not parent_id:
        return
    parent = await PlatformDoc.get_or_none(
        id=parent_id, is_del=False, builtin_id__isnull=True, doc_type="group",
    )
    if not parent:
        raise HTTPException(status_code=400, detail="所属目录不存在")


class PlatformDocBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[int] = None
    doc_type: str = Field(default="markdown", description="markdown/video/file/link/group")
    content: Optional[str] = None
    file_key: Optional[str] = None
    link_url: Optional[str] = None
    sort_order: int = 0
    is_published: bool = True


class BuiltinDocBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    sort_order: int = 0


class BuiltinGroupBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    sort_order: int = 0


@router.get("/catalog", summary="文档目录树", dependencies=[Depends(require_permissions(DOCS_VIEW))])
async def get_docs_catalog():
    overrides = await _load_builtin_overrides()
    custom_rows = await PlatformDoc.filter(
        is_del=False, is_published=True, builtin_id__isnull=True,
    ).order_by("sort_order", "id")
    custom_tree = build_custom_tree(list(custom_rows))
    custom_folders = [
        {"id": g.id, "title": g.title, "sort_order": g.sort_order}
        for g in custom_rows if g.doc_type == "group" and not g.parent_id
    ]
    return StandardResponse(data={
        "builtin_tree": merge_builtin_tree(overrides),
        "custom_tree": custom_tree,
        "custom_folders": custom_folders,
    })


@router.get("/builtin/{doc_id}", summary="读取内置文档", dependencies=[Depends(require_permissions(DOCS_VIEW))])
async def get_builtin_doc(doc_id: str):
    if not is_builtin_doc(doc_id):
        raise HTTPException(status_code=404, detail="未知内置文档")
    override = await PlatformDoc.get_or_none(builtin_id=doc_id, is_del=False)
    if override and override.is_hidden:
        raise HTTPException(status_code=404, detail="文档已隐藏")
    try:
        default_title, md = read_builtin_markdown(doc_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if is_community_edition():
        title = default_title
        content = md
        has_override = bool(override and override.is_hidden)
    else:
        title = override.title if override and override.title else default_title
        content = override.content if override and override.content is not None else md
        has_override = bool(override)
    return StandardResponse(data={
        "id": doc_id,
        "builtin_id": doc_id,
        "title": title,
        "doc_type": "markdown",
        "content_md": content,
        "content_html": _md_to_html(content),
        "source": "builtin",
        "has_override": has_override,
        "is_hidden": bool(override and override.is_hidden),
    })


@router.post("/builtin/sync-from-files", summary="从 docs-site 同步内置文档（清除正文覆盖）", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def sync_builtin_from_files(username: str = Depends(get_current_username)):
    """
    将内置文档正文重置为仓库 docs-site 中的 Markdown 文件。
    清除 platform_doc 中 builtin 条目的 content 覆盖，保留标题/排序/隐藏设置。
    """
    entries = get_builtin_doc_entries()
    cleared = 0
    created = 0
    for doc_id in entries:
        doc = await PlatformDoc.get_or_none(builtin_id=doc_id, is_del=False)
        if doc:
            if doc.content:
                doc.content = None
                doc.update_by = username
                await doc.save(update_fields=["content", "update_by", "update_time"])
                cleared += 1
        else:
            default_title = entries[doc_id][1]
            await PlatformDoc.create(
                builtin_id=doc_id,
                title=default_title,
                doc_type="markdown",
                content=None,
                is_published=True,
                create_by=username,
                update_by=username,
            )
            created += 1
    return StandardResponse(
        data={"cleared": cleared, "created": created, "total": len(entries)},
        message=f"已同步 {len(entries)} 篇内置文档（清除 {cleared} 篇覆盖）",
    )


@router.put("/builtin/{entry_id}", summary="更新内置文档或分组", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def update_builtin_entry(
    entry_id: str,
    body: BuiltinDocBody,
    username: str = Depends(get_current_username),
):
    if not is_builtin_entry(entry_id):
        raise HTTPException(status_code=404, detail="未知内置条目")
    if is_builtin_group(entry_id):
        group_body = BuiltinGroupBody(title=body.title, sort_order=body.sort_order)
        return await _upsert_builtin_group(entry_id, group_body, username)
    if not is_builtin_doc(entry_id):
        raise HTTPException(status_code=400, detail="无效的内置文档")
    default_title = get_builtin_doc_entries()[entry_id][1]
    doc = await PlatformDoc.get_or_none(builtin_id=entry_id, is_del=False)
    if not doc:
        doc = PlatformDoc(
            builtin_id=entry_id,
            title=body.title or default_title,
            doc_type="markdown",
            create_by=username,
        )
    if is_community_edition():
        doc.title = default_title
        doc.content = None
    else:
        doc.title = body.title or default_title
        doc.content = body.content
    doc.sort_order = body.sort_order
    doc.is_hidden = False
    doc.is_published = True
    doc.update_by = username
    await doc.save()
    return StandardResponse(data=_doc_to_dict(doc), message="更新成功")


async def _upsert_builtin_group(
    group_id: str,
    body: BuiltinGroupBody,
    username: str,
) -> StandardResponse:
    doc = await PlatformDoc.get_or_none(builtin_id=group_id, is_del=False)
    if not doc:
        doc = PlatformDoc(
            builtin_id=group_id,
            title=body.title,
            doc_type="group",
            create_by=username,
        )
    doc.title = body.title
    doc.sort_order = body.sort_order
    doc.is_hidden = False
    doc.is_published = True
    doc.update_by = username
    await doc.save()
    return StandardResponse(data=_doc_to_dict(doc), message="更新成功")


@router.delete("/builtin/{entry_id}", summary="隐藏内置文档或分组", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def hide_builtin_entry(entry_id: str, username: str = Depends(get_current_username)):
    if not is_builtin_entry(entry_id):
        raise HTTPException(status_code=404, detail="未知内置条目")
    default_title = ""
    if is_builtin_doc(entry_id):
        default_title = get_builtin_doc_entries()[entry_id][1]
    elif is_builtin_group(entry_id):
        default_title = next((g["title"] for g in get_builtin_doc_tree() if g["id"] == entry_id), entry_id)
    doc = await PlatformDoc.get_or_none(builtin_id=entry_id, is_del=False)
    if not doc:
        doc = PlatformDoc(
            builtin_id=entry_id,
            title=default_title,
            doc_type="group" if is_builtin_group(entry_id) else "markdown",
            create_by=username,
        )
    doc.is_hidden = True
    doc.update_by = username
    await doc.save()
    return StandardResponse(message="已隐藏")


@router.post("/builtin/{entry_id}/restore", summary="恢复已隐藏的内置条目", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def restore_builtin_entry(entry_id: str, username: str = Depends(get_current_username)):
    if not is_builtin_entry(entry_id):
        raise HTTPException(status_code=404, detail="未知内置条目")
    doc = await PlatformDoc.get_or_none(builtin_id=entry_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="无覆盖记录，无需恢复")
    doc.is_hidden = False
    doc.update_by = username
    await doc.save()
    return StandardResponse(message="已恢复")


@router.get("/manage", summary="文档管理列表（内置+自定义）", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def list_manage_docs():
    overrides = await _load_builtin_overrides()
    builtin_items = build_manage_builtin_items(overrides)
    custom_rows = await PlatformDoc.filter(is_del=False, builtin_id__isnull=True).order_by("sort_order", "id")
    custom_items = []
    for r in custom_rows:
        url = await _presigned(r.file_key) if r.file_key else ""
        item_type = "custom_group" if r.doc_type == "group" else "custom"
        custom_items.append({
            **_doc_to_dict(r, url),
            "type": item_type,
            "doc_id": r.id,
        })
    return StandardResponse(data={"list": builtin_items + custom_items})


@router.get("/articles", summary="自定义文档列表（管理）", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def list_articles(include_unpublished: bool = Query(False)):
    qs = PlatformDoc.filter(is_del=False, builtin_id__isnull=True)
    if not include_unpublished:
        qs = qs.filter(is_published=True)
    rows = await qs.order_by("sort_order", "id")
    result = []
    for r in rows:
        url = await _presigned(r.file_key) if r.file_key else ""
        result.append(_doc_to_dict(r, url))
    return StandardResponse(data={"list": result})


@router.get("/articles/{doc_id}", summary="自定义文档详情", dependencies=[Depends(require_permissions(DOCS_VIEW))])
async def get_article(doc_id: int):
    doc = await PlatformDoc.get_or_none(id=doc_id, is_del=False, builtin_id__isnull=True)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.is_published:
        raise HTTPException(status_code=404, detail="文档未发布")
    file_url = await _presigned(doc.file_key) if doc.file_key else ""
    data = _doc_to_dict(doc, file_url)
    if doc.doc_type == "markdown" and doc.content:
        data["content_html"] = _md_to_html(doc.content)
    return StandardResponse(data=data)


@router.post("/articles", summary="新建自定义文档或目录", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def create_article(body: PlatformDocBody, username: str = Depends(get_current_username)):
    _validate_doc_body(body)
    if body.doc_type != "group":
        await _validate_parent_id(body.parent_id)
    doc = await PlatformDoc.create(
        title=body.title,
        parent_id=None if body.doc_type == "group" else body.parent_id,
        doc_type=body.doc_type,
        content=body.content if body.doc_type != "group" else None,
        file_key=body.file_key if body.doc_type != "group" else None,
        link_url=body.link_url if body.doc_type != "group" else None,
        sort_order=body.sort_order,
        is_published=body.is_published,
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=_doc_to_dict(doc), message="创建成功")


@router.put("/articles/{doc_id}", summary="更新自定义文档或目录", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def update_article(
    doc_id: int,
    body: PlatformDocBody,
    username: str = Depends(get_current_username),
):
    doc = await PlatformDoc.get_or_none(id=doc_id, is_del=False, builtin_id__isnull=True)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    _validate_doc_body(body)
    if body.doc_type != "group":
        await _validate_parent_id(body.parent_id)
    doc.title = body.title
    doc.parent_id = None if body.doc_type == "group" else body.parent_id
    doc.doc_type = body.doc_type
    if body.doc_type == "group":
        doc.content = None
        doc.file_key = None
        doc.link_url = None
    else:
        doc.content = body.content
        doc.file_key = body.file_key
        doc.link_url = body.link_url
    doc.sort_order = body.sort_order
    doc.is_published = body.is_published
    doc.update_by = username
    await doc.save()
    return StandardResponse(data=_doc_to_dict(doc), message="更新成功")


@router.delete("/articles/{doc_id}", summary="删除自定义文档或目录", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def delete_article(doc_id: int, username: str = Depends(get_current_username)):
    doc = await PlatformDoc.get_or_none(id=doc_id, is_del=False, builtin_id__isnull=True)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.doc_type == "group":
        children = await PlatformDoc.filter(parent_id=doc.id, is_del=False, builtin_id__isnull=True)
        for child in children:
            child.is_del = True
            child.update_by = username
            await child.save(update_fields=["is_del", "update_by", "update_time"])
    doc.is_del = True
    doc.update_by = username
    await doc.save(update_fields=["is_del", "update_by", "update_time"])
    return StandardResponse(message="删除成功")


@router.post("/upload", summary="上传文档附件/视频", dependencies=[Depends(require_permissions(DOCS_EDIT))])
async def upload_doc_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 200MB 限制")

    object_name = f"{PLATFORM_DOCS_PREFIX}{uuid.uuid4().hex}{ext}"
    content_type = file.content_type or "application/octet-stream"

    if is_minio_storage():
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(
            None,
            lambda: minio_client.upload_bytes(object_name, data, content_type, API_FILE_BUCKET),
        )
        if not ok:
            raise HTTPException(status_code=500, detail="上传到存储失败")
        access_url = await _presigned(object_name)
    else:
        from app.core.platform.config import BASE_DIR
        local_dir = Path(BASE_DIR) / "static" / "platform_docs"
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / object_name.replace("/", "_")
        local_path.write_bytes(data)
        object_name = str(local_path)
        access_url = f"/static/platform_docs/{local_path.name}"

    doc_type = "video" if ext in (".mp4", ".webm", ".mov") else "file"
    return StandardResponse(data={
        "file_key": object_name,
        "file_access_url": access_url,
        "doc_type": doc_type,
        "filename": file.filename,
        "size": len(data),
    }, message="上传成功")
