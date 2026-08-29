"""接口 HTTP 经 PerfWorker 代发（复用 task_type=api_debug）。

编排/断言仍在平台；Worker 只发请求。选定 Worker 后禁止静默回退本机。
form-data 文件字段：平台从 MinIO 读出后以 file_content_b64 嵌入任务
（上限为 Redis 任务体积保护，与测试文件库上传上限可不同）。
"""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException

from app.core.runner.runner_version import compare_version
from app.modules.http.http_utils import prepare_httpx_headers

MIN_API_PROXY_ENGINE = "1.0.0"
# 带文件 form-data / 套件整包：与建议执行器 1.6.2 对齐（1.6.1 外发包不含这些能力）
MIN_API_PROXY_ENGINE_WITH_FILES = "1.6.2"
MIN_API_SUITE_ENGINE = "1.6.2"
NO_LOCAL_FALLBACK = "未回退为本机发送"
# Redis / 长轮询 JSON 体积保护（测试文件库上传默认可达 50MB，经执行机更严）
MAX_WORKER_FORM_FILE_BYTES = 10 * 1024 * 1024
MAX_WORKER_FORM_FILES_TOTAL_BYTES = 15 * 1024 * 1024
MAX_WORKER_TASK_JSON_BYTES = 22 * 1024 * 1024
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _with_no_fallback(message: str) -> str:
    text = str(message or "").strip().rstrip("。，,")
    if "未回退" in text or "勿回退" in text:
        return text
    return f"{text}，{NO_LOCAL_FALLBACK}"


class WorkerProxyError(Exception):
    """代发失败；status_code 供 HTTP 入口映射为 400/503/408。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(_with_no_fallback(message))
        self.status_code = status_code


def to_http_exception(exc: WorkerProxyError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def form_data_has_file(body_fields: Any) -> bool:
    for field in body_fields or []:
        if isinstance(field, dict):
            ftype = str(field.get("field_type") or field.get("type") or "text")
        else:
            ftype = str(
                getattr(field, "field_type", None) or getattr(field, "type", None) or "text"
            )
        if ftype.strip().lower() == "file":
            return True
    return False


def serialize_body_fields(body_fields: Any) -> list[dict]:
    out: list[dict] = []
    for field in body_fields or []:
        if hasattr(field, "model_dump"):
            out.append(field.model_dump())
        elif isinstance(field, dict):
            out.append(dict(field))
        else:
            out.append({
                "name": getattr(field, "name", "") or "",
                "value": getattr(field, "value", "") or "",
                "field_type": getattr(field, "field_type", None)
                or getattr(field, "type", None)
                or "text",
            })
    return out


def _field_type(field: dict) -> str:
    return str(field.get("field_type") or field.get("type") or "text").strip().lower()


def prepare_body_fields_for_worker(body_type: str, body_fields: Any) -> list[dict]:
    """序列化 body_fields；form-data 文件字段从 MinIO 嵌入 file_content_b64。"""
    fields = serialize_body_fields(body_fields)
    if (body_type or "").strip().lower() != "form-data" or not form_data_has_file(fields):
        return fields

    from app.core.infra.minio_client import minio_client
    from app.core.platform.config import API_FILE_BUCKET

    prepared: list[dict] = []
    total_bytes = 0
    for field in fields:
        item = dict(field)
        if _field_type(item) != "file":
            prepared.append(item)
            continue

        name = (item.get("name") or "").strip() or "file"
        file_key = (item.get("file_key") or "").strip()
        if not file_key:
            raise WorkerProxyError(
                f"文件字段「{name}」缺少文件引用，请先上传或选择测试文件",
                400,
            )
        file_bucket = str(item.get("file_bucket") or API_FILE_BUCKET or "").strip()
        if not file_bucket:
            raise WorkerProxyError(
                f"文件字段「{name}」缺少存储桶，无法从测试文件库读取",
                400,
            )
        file_bytes = minio_client.download_object(file_key, file_bucket)
        if file_bytes is None:
            raise WorkerProxyError(
                f"无法从存储读取文件字段「{name}」，请确认文件仍在测试文件库中或存储服务可用",
                400,
            )
        raw = bytes(file_bytes)
        size = len(raw)
        if size > MAX_WORKER_FORM_FILE_BYTES:
            raise WorkerProxyError(
                f"文件字段「{name}」过大（{size} 字节），经执行机单文件上限 "
                f"{MAX_WORKER_FORM_FILE_BYTES // (1024 * 1024)}MB，请改小文件",
                400,
            )
        total_bytes += size
        if total_bytes > MAX_WORKER_FORM_FILES_TOTAL_BYTES:
            raise WorkerProxyError(
                f"form-data 文件合计过大（已超 {MAX_WORKER_FORM_FILES_TOTAL_BYTES // (1024 * 1024)}MB），"
                "请减少文件后重试",
                400,
            )
        item["file_content_b64"] = base64.b64encode(raw).decode("ascii")
        if not item.get("file_name"):
            item["file_name"] = file_key.replace("\\", "/").split("/")[-1] or "upload.bin"
        if not item.get("mime_type"):
            item["mime_type"] = "application/octet-stream"
        prepared.append(item)
    return prepared


def estimate_worker_task_bytes(task: dict) -> int:
    """估算 api_debug 任务 JSON 体积（文件用 b64 长度，其余序列化 body/headers）。"""
    size = 4096
    for item in task.get("body_fields") or []:
        if not isinstance(item, dict):
            continue
        b64 = item.get("file_content_b64")
        if b64:
            size += len(b64)
        else:
            size += len(str(item.get("value") or "").encode("utf-8"))
    body = task.get("body")
    if isinstance(body, (bytes, bytearray)):
        size += len(body)
    elif body not in (None, ""):
        try:
            size += len(json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            size += len(str(body).encode("utf-8"))
    size += len(str(task.get("url") or "").encode("utf-8"))
    headers = task.get("headers") or {}
    try:
        size += len(json.dumps(headers, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        size += 1024
    return size


def strip_multipart_content_type(headers: dict[str, str]) -> dict[str, str]:
    """multipart 由 httpx 生成带 boundary 的 Content-Type，须去掉用户手动指定。"""
    out = dict(headers or {})
    for key in list(out.keys()):
        if str(key).lower() == "content-type":
            out.pop(key, None)
    return out


def append_query_params(url: str, params: Optional[dict] = None) -> str:
    if not params:
        return url
    extra = []
    for key, value in params.items():
        if key is None or value is None or value == "":
            continue
        extra.append((str(key), str(value)))
    if not extra:
        return url
    parts = urlsplit(url or "")
    merged = parse_qsl(parts.query, keep_blank_values=True) + extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))


def headers_to_plain_dict(headers: Any) -> dict[str, str]:
    prepared = prepare_httpx_headers(headers if isinstance(headers, dict) else dict(headers or {}))
    return {str(k): str(v) for k, v in prepared.items()}


def worker_record_fields(worker: Any, worker_id: Optional[int] = None) -> dict[str, Any]:
    if worker is not None:
        name = (getattr(worker, "name", None) or "")[:100]
        return {"worker_id": worker.id, "worker_name": name}
    if worker_id is not None:
        try:
            return {"worker_id": int(worker_id), "worker_name": ""}
        except (TypeError, ValueError):
            return {"worker_id": worker_id, "worker_name": ""}
    return {}


@dataclass
class WorkerHttpResponse:
    status_code: int = 0
    headers: dict = field(default_factory=dict)
    text: str = ""
    _json: Any = None
    elapsed_ms: float = 0
    size: int = 0
    worker_id: Optional[int] = None
    worker_name: str = ""

    def json(self):
        if self._json is not None:
            return self._json
        if not self.text:
            return {}
        return json.loads(self.text)


def _result_to_response(result: dict, worker: Any) -> WorkerHttpResponse:
    body = result.get("body")
    text = ""
    parsed: Any = None
    if isinstance(body, (dict, list)):
        parsed = body
        text = json.dumps(body, ensure_ascii=False)
    elif body is None:
        text = ""
    else:
        text = str(body)
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    return WorkerHttpResponse(
        status_code=int(result.get("status_code") or 0),
        headers=dict(result.get("headers") or {}),
        text=text,
        _json=parsed,
        elapsed_ms=float(result.get("time") or 0),
        size=int(result.get("size") or 0),
        worker_id=getattr(worker, "id", None),
        worker_name=(getattr(worker, "name", None) or "")[:100],
    )


def _rewrite_worker_file_error(message: str) -> str:
    text = str(message or "").strip()
    if "暂不支持带文件" in text or "不支持带文件" in text:
        return (
            "当前执行机不支持 form-data 文件代发，请更新含该能力的压测执行机包后重试"
        )
    return text


async def require_api_proxy_worker(project_id: int, worker_id: int):
    """校验指定 Worker 在线空闲且引擎 ≥ 1.0.0。失败抛 WorkerProxyError，不回退本机。"""
    from app.models.perf import PerfWorker
    from app.routers.perf.workers import get_active_workers

    if not project_id:
        raise WorkerProxyError("经执行机发送需要指定项目", 400)
    if not worker_id:
        raise WorkerProxyError("请选择在线空闲执行机", 400)

    active = await get_active_workers(project_id, exclude_busy=True)
    worker = next((w for w in active if w.id == worker_id), None)
    if not worker:
        w_raw = await PerfWorker.get_or_none(id=worker_id)
        if not w_raw or w_raw.project_id != project_id:
            raise WorkerProxyError("指定的执行机不存在或不属于当前项目", 400)
        raise WorkerProxyError(
            "指定的执行机当前不可用（离线或忙碌），请选择空闲在线 Worker",
            503,
        )

    engine_ver = (getattr(worker, "engine_version", None) or "").strip()
    if not engine_ver or compare_version(engine_ver, MIN_API_PROXY_ENGINE) < 0:
        raise WorkerProxyError(
            f"经执行机发送需要引擎 ≥ {MIN_API_PROXY_ENGINE}（当前 "
            f"{engine_ver or '未知'}），请升级 BrickCorePerf / Runner 压测包",
            400,
        )
    return worker


def require_file_form_proxy_engine(worker) -> None:
    """带文件代发前校验引擎版本，避免旧包先收任务再报不支持。"""
    engine_ver = (getattr(worker, "engine_version", None) or "").strip()
    if not engine_ver or compare_version(engine_ver, MIN_API_PROXY_ENGINE_WITH_FILES) < 0:
        raise WorkerProxyError(
            f"带文件的 form-data 经执行机发送需要引擎 ≥ {MIN_API_PROXY_ENGINE_WITH_FILES}"
            f"（当前 {engine_ver or '未知'}），请更新 BrickCorePerf / Runner 压测包",
            400,
        )


async def require_api_proxy_worker_http(project_id: int, worker_id: int):
    try:
        return await require_api_proxy_worker(project_id, worker_id)
    except WorkerProxyError as exc:
        raise to_http_exception(exc) from exc


async def list_idle_api_proxy_workers(project_id: int) -> list[dict]:
    """列出在线执行机（含忙碌）。前端按 current_record_id 过滤可选项，忙碌项用于提示。"""
    from app.routers.perf.workers import get_active_workers

    active = await get_active_workers(project_id, exclude_busy=False)
    out: list[dict] = []
    for w in active:
        engine_ver = (getattr(w, "engine_version", None) or "").strip()
        if not engine_ver or compare_version(engine_ver, MIN_API_PROXY_ENGINE) < 0:
            continue
        busy_id = getattr(w, "current_record_id", None)
        out.append({
            "id": w.id,
            "name": w.name,
            "host": w.host,
            "engine_version": engine_ver,
            "agent_kind": getattr(w, "agent_kind", "") or "",
            "current_record_id": busy_id,
            "status": "busy" if busy_id else "online",
            "supports_file_form": compare_version(engine_ver, MIN_API_PROXY_ENGINE_WITH_FILES) >= 0,
            "supports_api_suite": compare_version(engine_ver, MIN_API_SUITE_ENGINE) >= 0,
        })
    out.sort(key=lambda x: x["id"], reverse=True)
    return out


async def _cleanup_worker_task(worker, request_id: Optional[str] = None) -> None:
    from app.routers.perf import worker_queue

    if request_id:
        await worker_queue.clear_task_if_request(worker.id, request_id)
    # 无 request_id 时不清队列，避免误删压测待领取任务
    from app.routers.perf.workers import release_worker_after_proxy_task

    await release_worker_after_proxy_task(worker.id)


async def send_http_via_worker(
    *,
    worker=None,
    project_id: Optional[int] = None,
    worker_id: Optional[int] = None,
    method: str,
    url: str,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    body: Any = None,
    body_type: str = "json",
    body_fields: Optional[list] = None,
    timeout: int = 30,
) -> WorkerHttpResponse:
    """拼好的请求经 Worker 代发。失败抛 WorkerProxyError，绝不改走本机 httpx。"""
    from app.routers.perf import api_debug_bridge
    from app.routers.perf.workers import send_task_to_worker

    if worker is None:
        worker = await require_api_proxy_worker(int(project_id or 0), int(worker_id or 0))

    method_u = (method or "GET").upper()
    bt = (body_type or "json").strip().lower()
    # GET/DELETE 等不会发 body，避免白白把文件塞进 Redis
    will_embed_files = (
        method_u in _BODY_METHODS and bt == "form-data" and form_data_has_file(body_fields)
    )
    if will_embed_files:
        require_file_form_proxy_engine(worker)
        fields = await asyncio.to_thread(prepare_body_fields_for_worker, bt, body_fields)
        has_files = True
    else:
        fields = serialize_body_fields(body_fields)
        has_files = False

    final_url = append_query_params(url, params)
    header_dict = headers_to_plain_dict(headers)
    if bt == "form-data":
        header_dict = strip_multipart_content_type(header_dict)

    timeout_sec = max(1, int(timeout or 30))
    wait_timeout = max(5, timeout_sec + 15)
    if has_files:
        wait_timeout = max(wait_timeout, timeout_sec + 60)

    request_id = api_debug_bridge.new_request_id()
    await api_debug_bridge.register_wait(request_id)
    task = {
        "task_type": "api_debug",
        "request_id": request_id,
        "method": method_u,
        "url": final_url,
        "headers": header_dict,
        "body": body,
        "body_type": body_type or "json",
        "body_fields": fields,
        "timeout": timeout_sec,
    }
    payload_bytes = estimate_worker_task_bytes(task)
    if payload_bytes > MAX_WORKER_TASK_JSON_BYTES:
        await api_debug_bridge.cancel(request_id)
        raise WorkerProxyError(
            f"经执行机任务过大（约 {payload_bytes // (1024 * 1024)}MB），"
            f"上限约 {MAX_WORKER_TASK_JSON_BYTES // (1024 * 1024)}MB，请减小请求体或 form-data 文件",
            400,
        )

    ok = await send_task_to_worker(worker, task)
    if not ok:
        await api_debug_bridge.cancel(request_id)
        busy = False
        try:
            from app.routers.perf import worker_queue
            busy = await worker_queue.has_pending_task(worker.id)
        except Exception:
            busy = False
        if busy:
            raise WorkerProxyError(
                "下发任务失败（执行机任务队列占用），请稍后重试或换一台空闲执行机",
                503,
            )
        raise WorkerProxyError(
            "下发任务失败（写入执行机队列失败，可能是 Redis 不可用或任务过大），"
            "请稍后重试或减小 form-data 文件",
            503,
        )

    result = await api_debug_bridge.wait_result(request_id, timeout=float(wait_timeout))
    await _cleanup_worker_task(worker, request_id)

    if result is None:
        hint = ""
        if has_files:
            hint = "（若刚更新平台但未更新压测包，带文件请求也会超时或失败）"
        raise WorkerProxyError(
            f"等待执行机结果超时{hint}，请确认执行机在线且版本支持接口代发",
            408,
        )
    if result.get("error"):
        err = _rewrite_worker_file_error(str(result.get("error") or ""))
        raise WorkerProxyError(f"执行机发送失败: {err}", 400)
    return _result_to_response(result, worker)
