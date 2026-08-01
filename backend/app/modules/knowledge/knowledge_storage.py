"""资料库文件存储（MinIO 为主，本地磁盘回退）"""
from __future__ import annotations

import logging
import mimetypes
import os
import shutil
from typing import Any

from app.core.platform.config import AI_KNOWLEDGE_BUCKET, KNOWLEDGE_DIR
from app.core.infra.minio_client import is_minio_storage, minio_client

logger = logging.getLogger(__name__)

os.makedirs(KNOWLEDGE_DIR, exist_ok=True)


def source_object_key(project_id: int, doc_id: int, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}" if ext else ".bin"
    return f"{project_id}/docs/{doc_id}/source{ext}"


def output_object_key(project_id: int, report_id: int, ext: str = ".docx") -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{project_id}/outputs/{report_id}/report{ext}"


def _guess_content_type(file_name: str, fallback: str = "application/octet-stream") -> str:
    ct, _ = mimetypes.guess_type(file_name or "")
    return ct or fallback


def save_document_source(
    project_id: int,
    doc_id: int,
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    ext = os.path.splitext(file_name or "")[1].lower() or ".bin"
    if is_minio_storage():
        key = source_object_key(project_id, doc_id, ext)
        ok = minio_client.upload_bytes(
            key,
            content,
            _guess_content_type(file_name),
            bucket_name=AI_KNOWLEDGE_BUCKET,
        )
        if not ok:
            raise RuntimeError(f"资料库文件上传 MinIO 失败: {key}")
        return {
            "storage": {
                "type": "minio",
                "bucket": AI_KNOWLEDGE_BUCKET,
                "source_key": key,
            },
            "file_path": key,
        }

    rel_dir = os.path.join(KNOWLEDGE_DIR, str(project_id), str(doc_id))
    os.makedirs(rel_dir, exist_ok=True)
    path = os.path.join(rel_dir, f"source{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return {
        "storage": {"type": "local", "file_path": path},
        "file_path": path,
    }


def load_document_source(storage_meta: dict, file_name: str = "document.bin") -> bytes:
    storage = storage_meta if isinstance(storage_meta, dict) else {}
    inner = storage.get("storage") if isinstance(storage.get("storage"), dict) else {}

    if inner.get("type") == "minio" and inner.get("source_key"):
        bucket = inner.get("bucket") or AI_KNOWLEDGE_BUCKET
        data = minio_client.download_object(inner["source_key"], bucket)
        if data:
            return data
        raise FileNotFoundError(f"MinIO 文件不存在: {inner['source_key']}")

    for path in (inner.get("file_path"), storage.get("file_path")):
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()

    raise FileNotFoundError("资料库源文件不存在")


def save_report_output(
    project_id: int,
    report_id: int,
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    ext = os.path.splitext(file_name or "")[1].lower() or ".docx"
    if is_minio_storage():
        key = output_object_key(project_id, report_id, ext)
        ok = minio_client.upload_bytes(
            key,
            content,
            _guess_content_type(file_name),
            bucket_name=AI_KNOWLEDGE_BUCKET,
        )
        if not ok:
            raise RuntimeError(f"报告文件上传 MinIO 失败: {key}")
        return {"storage": {"type": "minio", "bucket": AI_KNOWLEDGE_BUCKET, "source_key": key}, "file_path": key}

    rel_dir = os.path.join(KNOWLEDGE_DIR, str(project_id), "outputs", str(report_id))
    os.makedirs(rel_dir, exist_ok=True)
    path = os.path.join(rel_dir, f"report{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return {"storage": {"type": "local", "file_path": path}, "file_path": path}


def load_report_output(storage_meta: dict, file_name: str = "report.docx") -> bytes:
    return load_document_source(storage_meta, file_name)


def _purge_storage_meta(storage_meta: dict | None) -> None:
    if not isinstance(storage_meta, dict):
        return
    inner = storage_meta.get("storage") if isinstance(storage_meta.get("storage"), dict) else storage_meta
    if not isinstance(inner, dict):
        return
    if inner.get("type") == "minio" and inner.get("source_key"):
        bucket = inner.get("bucket") or AI_KNOWLEDGE_BUCKET
        try:
            minio_client.client.remove_object(bucket, inner["source_key"])
        except Exception as exc:
            logger.warning("MinIO 删除对象失败 %s: %s", inner["source_key"], exc)
        return
    for path in (inner.get("file_path"), storage_meta.get("file_path")):
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning("本地删除报告文件失败 %s: %s", path, exc)


async def purge_report_output_files(report) -> None:
    """物理删除生成记录关联的输出文件（主报告与 Bug 工作簿）。"""
    cfg = report.config_json if isinstance(report.config_json, dict) else {}
    _purge_storage_meta(cfg.get("output_storage"))
    _purge_storage_meta(cfg.get("bug_workbook_storage"))
    file_path = getattr(report, "file_path", None)
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            logger.warning("本地删除报告 file_path 失败 %s: %s", file_path, exc)
    project_id = getattr(report, "project_id", None)
    report_id = getattr(report, "id", None)
    if project_id is not None and report_id is not None:
        rel_dir = os.path.join(KNOWLEDGE_DIR, str(project_id), "outputs", str(report_id))
        if os.path.isdir(rel_dir):
            shutil.rmtree(rel_dir, ignore_errors=True)


def purge_document_source_files(doc) -> None:
    """物理删除上传文档源文件（MinIO / 本地目录）。"""
    storage = doc.storage if isinstance(getattr(doc, "storage", None), dict) else {}
    _purge_storage_meta(storage)
    project_id = getattr(doc, "project_id", None)
    doc_id = getattr(doc, "id", None)
    if project_id is not None and doc_id is not None:
        rel_dir = os.path.join(KNOWLEDGE_DIR, str(project_id), str(doc_id))
        if os.path.isdir(rel_dir):
            shutil.rmtree(rel_dir, ignore_errors=True)
