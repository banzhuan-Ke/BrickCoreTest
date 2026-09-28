"""小测 Job 桥：assistant_job_link 持久化 + Browser Lab / UI Agent / 评测 / 生成。

长任务以 link 表为准，不依赖纯内存 watcher 作为唯一机制。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.models.ai import (
    AiRequirementGenerateJob,
    AssistantJobLink,
    AssistantSession,
    BrowserLabTask,
    UiAgentJob,
)
from app.modules.assistant.assistant_session import load_session_messages, save_session_messages
from brickcore_assist.jobs.bridge import (
    ACTION_SPAWN_BROWSER_LAB,
    ACTION_SPAWN_UI_AGENT,
    JOB_TYPE_BROWSER_LAB,
    JOB_TYPE_GENERATE,
    JOB_TYPE_QA_EVAL,
    JOB_TYPE_UI_AGENT,
    job_type_title,
    notify_headline,
    parse_confirm_job,
    report_url_for,
)
from brickcore_assist.jobs import normalize_job_status

logger = logging.getLogger(__name__)

# 归一化状态（会话 / API 对外）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_TERMINAL = frozenset({STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED})

_BL_TO_NORMAL = {
    "pending": STATUS_PENDING,
    "running": STATUS_RUNNING,
    "done": STATUS_SUCCEEDED,
    "failed": STATUS_FAILED,
    "stopped": STATUS_CANCELLED,
}


def normalize_browser_lab_status(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    return _BL_TO_NORMAL.get(key, STATUS_PENDING if not key else STATUS_FAILED)


def normalize_ui_agent_status(raw: str | None) -> str:
    return normalize_job_status(JOB_TYPE_UI_AGENT, raw)


def is_terminal_status(status: str | None) -> bool:
    return (status or "").strip().lower() in _TERMINAL


def build_job_progress_card(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "job_progress",
        "link_id": job.get("link_id") or job.get("id"),
        "job_type": job.get("job_type") or JOB_TYPE_BROWSER_LAB,
        "job_id": str(job.get("job_id") or ""),
        "status": job.get("status") or STATUS_PENDING,
        "title": job.get("title") or job_type_title(job.get("job_type")),
        "summary": job.get("summary") or "",
        "report_url": job.get("report_url") or "",
        "can_cancel": bool(job.get("can_cancel")),
        "payload": job.get("payload") or {},
    }


def _http_detail(exc: HTTPException) -> str:
    detail = exc.detail
    return detail if isinstance(detail, str) else str(detail)


def build_browser_lab_config(
    *,
    device_id: str,
    env_id: int | None = None,
    ai_config_id: int | None = None,
    max_steps: int | None = None,
    use_vision: bool = True,
    generate_gif: bool = True,
    headless: bool = True,
) -> dict[str, Any]:
    """对齐 Browser Lab create 默认配置（不经 pydantic，便于 MCP 调用）。"""
    from app.core.platform import config as settings

    device = (device_id or "").strip()
    if not device:
        raise ValueError("请选择在线 Runner 执行设备（device_id）")
    steps = int(max_steps or settings.BROWSER_LAB_DEFAULT_MAX_STEPS)
    steps = min(max(3, steps), settings.BROWSER_LAB_MAX_STEPS_CAP)
    cap = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP)
    repeat_cap = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS_CAP)
    return {
        "ai_config_id": ai_config_id,
        "max_steps": steps,
        "use_vision": bool(use_vision),
        "generate_gif": bool(generate_gif),
        "enable_browser_restart": True,
        "max_browser_restarts": min(2, cap),
        "max_repeat_steps": min(3, repeat_cap),
        "use_action_cache": True,
        "force_refresh_cache": False,
        "on_replay_fail": "fallback_agent",
        "env_id": int(env_id) if env_id else None,
        "run_mode": "runner",
        "device_id": device,
        "headless": bool(headless),
    }


async def spawn_browser_lab_task(
    *,
    project_id: int,
    username: str,
    task_text: str,
    start_url: str,
    device_id: str,
    env_id: int | None = None,
    ai_config_id: int | None = None,
    max_steps: int | None = None,
    headless: bool = True,
    platform_base_url: str | None = None,
) -> BrowserLabTask:
    """复用 Browser Lab 现有 create/quota/权限路径（_start_task）。"""
    from app.routers.ai.browser_lab import _normalize_url, _start_task

    text = (task_text or "").strip()
    if len(text) < 2:
        raise ValueError("任务描述太短")
    try:
        url = _normalize_url(start_url)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc

    config_json = build_browser_lab_config(
        device_id=device_id,
        env_id=env_id,
        ai_config_id=ai_config_id,
        max_steps=max_steps,
        headless=headless,
    )
    try:
        return await _start_task(
            project_id=int(project_id),
            username=username or "",
            task_text=text,
            start_url=url,
            config_json=config_json,
            platform_base_url=platform_base_url,
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc


async def create_job_link(
    *,
    session_id: int,
    job_type: str,
    job_id: str | int,
    status: str = STATUS_PENDING,
    payload: dict[str, Any] | None = None,
) -> AssistantJobLink:
    return await AssistantJobLink.create(
        session_id=int(session_id),
        job_type=(job_type or JOB_TYPE_BROWSER_LAB)[:64],
        job_id=str(job_id)[:64],
        status=(status or STATUS_PENDING)[:32],
        payload_json=payload or {},
    )


async def link_after_confirm(
    *,
    session_id: int | None,
    action: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """confirm 成功后写入 job_link（Browser Lab / UI Agent / 评测 / 需求生成）。"""
    if not session_id:
        return None
    parsed = parse_confirm_job(action, result if isinstance(result, dict) else {})
    if not parsed:
        return None
    status = normalize_job_status(parsed["job_type"], str(parsed.get("raw_status") or "pending"))
    payload = dict(parsed.get("payload") or {})
    payload["notified"] = False
    if not payload.get("title"):
        payload["title"] = job_type_title(parsed["job_type"])
    link = await create_job_link(
        session_id=session_id,
        job_type=parsed["job_type"],
        job_id=parsed["job_id"],
        status=status,
        payload=payload,
    )
    return await serialize_job_link(link, refresh=False)


async def _ensure_session_owner(session_id: int, user_id: int) -> AssistantSession:
    session = await AssistantSession.get_or_none(id=int(session_id), user_id=int(user_id))
    if not session:
        raise ValueError("会话不存在或无权访问")
    return session


def _report_url(job_type: str, job_id: str, payload: dict[str, Any] | None = None) -> str:
    return report_url_for(job_type, job_id, payload)


async def _refresh_browser_lab_link(link: AssistantJobLink) -> AssistantJobLink:
    if is_terminal_status(link.status):
        return link
    try:
        task_id = int(link.job_id)
    except (TypeError, ValueError):
        return link
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        link.status = STATUS_FAILED
        payload = dict(link.payload_json or {})
        payload["error_message"] = "任务不存在或已删除"
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
        return link

    new_status = normalize_browser_lab_status(task.status)
    payload = dict(link.payload_json or {})
    payload.update(
        {
            "project_id": task.project_id,
            "task_text": (task.task_text or "")[:200],
            "start_url": task.start_url or "",
            "device_id": (task.config_json or {}).get("device_id") or "",
            "result_summary": (task.result_summary or "")[:500],
            "error_message": (task.error_message or "")[:500],
            "steps_count": task.steps_count,
            "bl_status": task.status,
        }
    )
    if not payload.get("title"):
        payload["title"] = job_type_title(JOB_TYPE_BROWSER_LAB)
    changed = link.status != new_status or link.payload_json != payload
    if changed:
        link.status = new_status
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def _refresh_ui_agent_link(link: AssistantJobLink) -> AssistantJobLink:
    if is_terminal_status(link.status):
        return link
    try:
        job_id = int(link.job_id)
    except (TypeError, ValueError):
        return link
    job = await UiAgentJob.get_or_none(id=job_id)
    if not job:
        link.status = STATUS_FAILED
        payload = dict(link.payload_json or {})
        payload["error_message"] = "任务不存在或已删除"
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
        return link

    new_status = normalize_ui_agent_status(job.status)
    payload = dict(link.payload_json or {})
    steps = job.steps_json if isinstance(job.steps_json, list) else []
    stop_requested = bool(payload.get("stop_requested")) or bool(
        (job.source_ref or {}).get("stop_requested") if isinstance(job.source_ref, dict) else False
    )
    if is_terminal_status(new_status):
        summary = (job.error_message or f"已产出 {len(steps)} 步")[:500]
    elif stop_requested:
        summary = "已请求停止，等待执行机确认"
    else:
        summary = f"进行中，已产出 {len(steps)} 步"
    payload.update(
        {
            "project_id": job.project_id,
            "page_url": job.page_url or "",
            "description": (job.description or "")[:200],
            "device_id": job.device_id or "",
            "steps_count": len(steps),
            "error_message": (job.error_message or "")[:500],
            "result_summary": summary,
            "stop_requested": stop_requested,
            "ua_status": job.status,
        }
    )
    if not payload.get("title"):
        payload["title"] = job_type_title(JOB_TYPE_UI_AGENT)
    if link.status != new_status or link.payload_json != payload:
        link.status = new_status
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def _refresh_qa_eval_link(link: AssistantJobLink) -> AssistantJobLink:
    """开源发行版已移除问答评测模型；历史 link 标记失败即可。"""
    if is_terminal_status(link.status):
        return link
    link.status = STATUS_FAILED
    payload = dict(link.payload_json or {})
    payload["error_message"] = "当前发行版不支持该任务类型"
    payload["result_summary"] = payload["error_message"]
    if not payload.get("title"):
        payload["title"] = job_type_title(JOB_TYPE_QA_EVAL)
    link.payload_json = payload
    await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def _refresh_generate_link(link: AssistantJobLink) -> AssistantJobLink:
    if is_terminal_status(link.status):
        return link
    try:
        job_id = int(link.job_id)
    except (TypeError, ValueError):
        return link
    job = await AiRequirementGenerateJob.get_or_none(id=job_id, is_del=False)
    if not job:
        link.status = STATUS_FAILED
        payload = dict(link.payload_json or {})
        payload["error_message"] = "生成任务不存在或已删除"
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
        return link

    new_status = normalize_job_status(JOB_TYPE_GENERATE, job.status)
    total = int(job.total_batches or 0)
    done = int(job.done_batches or 0)
    pct = int(done / total * 100) if total else 0
    payload = dict(link.payload_json or {})
    gr = job.generate_report if isinstance(job.generate_report, dict) else {}
    case_count = len(gr.get("created_case_ids") or [])
    payload.update(
        {
            "project_id": job.project_id,
            "requirement_id": job.requirement_id,
            "progress_percent": pct,
            "done_batches": done,
            "total_batches": total,
            "current_batch_name": job.current_batch_name or "",
            "case_count": case_count,
            "error_message": (job.error or "")[:500],
            "result_summary": (
                (job.error or "")[:500]
                if new_status == STATUS_FAILED
                else (
                    f"已生成 {case_count} 条用例"
                    if new_status == STATUS_SUCCEEDED
                    else f"批次进度 {done}/{total}"
                    + (f"：{job.current_batch_name}" if job.current_batch_name else "")
                )
            ),
            "gen_status": job.status,
        }
    )
    if not payload.get("title"):
        payload["title"] = job_type_title(JOB_TYPE_GENERATE)
    if link.status != new_status or link.payload_json != payload:
        link.status = new_status
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def _refresh_job_link(link: AssistantJobLink) -> AssistantJobLink:
    if link.job_type == JOB_TYPE_BROWSER_LAB:
        return await _refresh_browser_lab_link(link)
    if link.job_type == JOB_TYPE_UI_AGENT:
        return await _refresh_ui_agent_link(link)
    if link.job_type == JOB_TYPE_QA_EVAL:
        return await _refresh_qa_eval_link(link)
    if link.job_type == JOB_TYPE_GENERATE:
        return await _refresh_generate_link(link)
    return link


async def maybe_notify_job_finished(
    *,
    link: AssistantJobLink,
    user_id: int,
    project_id: int | None,
) -> bool:
    """终态且未通知时追加会话消息；返回是否写入。

    先占位 notified 防并发双写；会话写入失败则回滚 notified 以便下次重试。
    """
    if not is_terminal_status(link.status):
        return False
    payload = dict(link.payload_json or {})
    if payload.get("notified") or payload.get("detached"):
        return False

    payload["notified"] = True
    link.payload_json = payload
    await link.save(update_fields=["payload_json", "update_time"])

    title = payload.get("title") or job_type_title(link.job_type)
    summary = (
        payload.get("result_summary")
        or payload.get("error_message")
        or ""
    ).strip()
    report = _report_url(link.job_type, link.job_id, payload)
    head = notify_headline(link.job_type, link.status or "", link.job_id)
    lines = [head, f"- 标题：{title}"]
    if summary:
        lines.append(f"- 摘要：{summary}")
    if report:
        label = "打开工作台" if link.job_type == JOB_TYPE_GENERATE else "打开报告"
        lines.append(f"- {label}：[{label}]({report})")
    content = "\n".join(lines)

    try:
        _, msgs = await load_session_messages(user_id, project_id, session_id=link.session_id)
        follow = {
            "role": "assistant",
            "content": content,
            "tools": [f"job:{link.job_type}:{link.job_id}"],
            "execution_follow_up": True,
            "job_follow_up": True,
            "cards": [
                build_job_progress_card(
                    {
                        "link_id": link.id,
                        "job_type": link.job_type,
                        "job_id": link.job_id,
                        "status": link.status,
                        "title": title,
                        "summary": summary,
                        "report_url": report,
                        "can_cancel": False,
                        "payload": payload,
                    }
                )
            ],
        }
        await save_session_messages(
            user_id,
            project_id,
            msgs + [follow],
            session_id=link.session_id,
        )
    except Exception:
        logger.exception(
            "[assistant_jobs] notify failed link=%s session=%s",
            link.id,
            link.session_id,
        )
        try:
            payload["notified"] = False
            link.payload_json = payload
            await link.save(update_fields=["payload_json", "update_time"])
        except Exception:
            logger.exception("[assistant_jobs] rollback notified failed link=%s", link.id)
        return False
    return True


async def serialize_job_link(
    link: AssistantJobLink,
    *,
    refresh: bool = True,
) -> dict[str, Any]:
    if refresh:
        link = await _refresh_job_link(link)
    payload = dict(link.payload_json or {})
    status = link.status or STATUS_PENDING
    title = payload.get("title") or job_type_title(link.job_type)
    summary = (
        payload.get("result_summary")
        or payload.get("error_message")
        or payload.get("task_text")
        or payload.get("description")
        or ""
    )
    report = _report_url(link.job_type, str(link.job_id), payload)
    return {
        "id": link.id,
        "link_id": link.id,
        "session_id": link.session_id,
        "job_type": link.job_type,
        "job_id": str(link.job_id),
        "status": status,
        "title": title,
        "summary": str(summary)[:500],
        "report_url": report,
        "can_cancel": not is_terminal_status(status),
        "payload": payload,
        "create_time": link.create_time.isoformat() if link.create_time else None,
        "update_time": link.update_time.isoformat() if link.update_time else None,
        "card": build_job_progress_card(
            {
                "link_id": link.id,
                "job_type": link.job_type,
                "job_id": link.job_id,
                "status": status,
                "title": title,
                "summary": summary,
                "report_url": report,
                "can_cancel": not is_terminal_status(status),
                "payload": payload,
            }
        ),
    }


async def list_session_jobs(
    *,
    user_id: int,
    session_id: int,
    project_id: int | None = None,
    refresh: bool = True,
    notify: bool = True,
) -> list[dict[str, Any]]:
    session = await _ensure_session_owner(session_id, user_id)
    resolved_pid = project_id if project_id is not None else session.project_id
    rows = await AssistantJobLink.filter(session_id=int(session_id)).order_by("-id")
    out: list[dict[str, Any]] = []
    for link in rows:
        item = await serialize_job_link(link, refresh=refresh)
        if notify:
            fresh = await AssistantJobLink.get(id=link.id)
            await maybe_notify_job_finished(
                link=fresh,
                user_id=user_id,
                project_id=resolved_pid,
            )
            item = await serialize_job_link(fresh, refresh=False)
        out.append(item)
    return out


async def _cancel_browser_lab(link: AssistantJobLink, username: str) -> AssistantJobLink:
    try:
        task_id = int(link.job_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("无效的任务 ID") from exc

    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        link.status = STATUS_FAILED
        payload = dict(link.payload_json or {})
        payload["error_message"] = "任务不存在或已删除"
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
        return link

    if task.status not in ("pending", "running"):
        return await _refresh_browser_lab_link(link)

    from app.modules.browser_lab.browser_lab_runner import request_stop

    request_stop(task_id)
    cfg = task.config_json or {}
    if (cfg.get("run_mode") or "").strip().lower() == "runner" and cfg.get("device_id"):
        from app.modules.browser_lab.browser_lab_dispatch import send_browser_lab_stop

        send_browser_lab_stop(str(cfg.get("device_id")), task_id)

    log = list(task.step_log or [])
    if not any(e.get("type") == "done" for e in log):
        log.append({"type": "done", "status": "stopped", "summary": "用户已停止（小测）"})
    task.status = "stopped"
    task.error_message = "用户已停止"
    task.result_summary = "用户已停止"
    task.finished_at = datetime.now(timezone.utc)
    task.step_log = log
    await task.save(
        update_fields=["status", "error_message", "result_summary", "finished_at", "step_log"]
    )
    try:
        from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

        await ensure_browser_lab_usage_logged(task)
    except Exception:
        logger.debug("[assistant_jobs] usage log skip task=%s", task_id, exc_info=True)

    link.status = STATUS_CANCELLED
    payload = dict(link.payload_json or {})
    payload["result_summary"] = "用户已停止"
    payload["error_message"] = "用户已停止"
    payload["stopped_by"] = username or "assistant"
    link.payload_json = payload
    await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def _cancel_ui_agent(link: AssistantJobLink, username: str) -> AssistantJobLink:
    try:
        job_id = int(link.job_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("无效的任务 ID") from exc

    from app.modules.ui.ui_agent_job_service import request_stop_ui_agent_job

    try:
        await request_stop_ui_agent_job(job_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            link.status = STATUS_FAILED
            payload = dict(link.payload_json or {})
            payload["error_message"] = "任务不存在或已删除"
            link.payload_json = payload
            await link.save(update_fields=["status", "payload_json", "update_time"])
            return link
        if exc.status_code == 400:
            return await _refresh_ui_agent_link(link)
        raise ValueError(_http_detail(exc)) from exc

    # 停止请求已写入；Runner 回调前保持 running，轮询会刷新到 cancelled
    payload = dict(link.payload_json or {})
    payload["stop_requested"] = True
    payload["stopped_by"] = username or "assistant"
    payload["result_summary"] = "已请求停止，等待执行机确认"
    link.payload_json = payload
    await link.save(update_fields=["payload_json", "update_time"])
    return await _refresh_ui_agent_link(link)


async def _cancel_qa_eval(link: AssistantJobLink, username: str) -> AssistantJobLink:
    _ = username
    return await _refresh_qa_eval_link(link)


async def _cancel_generate(link: AssistantJobLink, username: str) -> AssistantJobLink:
    try:
        job_id = int(link.job_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("无效的任务 ID") from exc
    job = await AiRequirementGenerateJob.get_or_none(id=job_id, is_del=False)
    if not job:
        link.status = STATUS_FAILED
        payload = dict(link.payload_json or {})
        payload["error_message"] = "生成任务不存在或已删除"
        link.payload_json = payload
        await link.save(update_fields=["status", "payload_json", "update_time"])
        return link
    if job.status not in ("pending", "running"):
        return await _refresh_generate_link(link)

    from app.core.platform.datetime_utils import now_app

    job.status = "cancelled"
    job.error = "用户已停止"
    job.finish_time = now_app()
    await job.save()

    link.status = STATUS_CANCELLED
    payload = dict(link.payload_json or {})
    payload["result_summary"] = "将在当前批次结束后停止"
    payload["error_message"] = "用户已停止"
    payload["stopped_by"] = username or "assistant"
    link.payload_json = payload
    await link.save(update_fields=["status", "payload_json", "update_time"])
    return link


async def detach_session_jobs(session_id: int) -> int:
    """清空会话时拆掉 Job 桥：标记 detached，阻止后续 follow-up 写入。"""
    rows = await AssistantJobLink.filter(session_id=int(session_id))
    n = 0
    for link in rows:
        payload = dict(link.payload_json or {})
        if payload.get("detached"):
            continue
        payload["detached"] = True
        payload["notified"] = True
        link.payload_json = payload
        await link.save(update_fields=["payload_json", "update_time"])
        n += 1
    return n


async def cancel_session_job(
    *,
    user_id: int,
    link_id: int,
    username: str = "",
) -> dict[str, Any]:
    link = await AssistantJobLink.get_or_none(id=int(link_id))
    if not link:
        raise ValueError("任务关联不存在")
    await _ensure_session_owner(link.session_id, user_id)
    if is_terminal_status(link.status):
        return await serialize_job_link(link, refresh=False)

    if link.job_type == JOB_TYPE_BROWSER_LAB:
        link = await _cancel_browser_lab(link, username)
    elif link.job_type == JOB_TYPE_UI_AGENT:
        link = await _cancel_ui_agent(link, username)
    elif link.job_type == JOB_TYPE_QA_EVAL:
        link = await _cancel_qa_eval(link, username)
    elif link.job_type == JOB_TYPE_GENERATE:
        link = await _cancel_generate(link, username)
    else:
        raise ValueError(f"暂不支持取消该类型任务: {link.job_type}")

    return await serialize_job_link(link, refresh=False)


async def spawn_ui_agent_job(
    *,
    project_id: int,
    username: str,
    page_url: str,
    description: str,
    device_id: str,
    ai_config_id: int | None = None,
    max_steps: int | None = None,
    headless: bool = True,
    platform_base_url: str | None = None,
) -> dict[str, Any]:
    """创建并派发 UI Agent（source=assistant），复用现有 Runner 路径。"""
    from app.core.platform import config as settings
    from app.modules.ai.ai_scene_config import resolve_assist_config_for_scene
    from app.modules.browser_dispatch import merge_job_platform_base_url, validate_device_online
    from app.modules.ui.ui_agent_dispatch import dispatch_ui_agent_to_runner
    from app.modules.ui.ui_agent_job_service import create_ui_agent_job, job_to_dict
    from app.routers.ai.generate import UI_AGENT_DEFAULT_STEPS, UI_AGENT_MAX_STEPS

    url = (page_url or "").strip()
    desc = (description or "").strip()
    device = (device_id or "").strip()
    if len(url) < 8:
        raise ValueError("起始 URL 无效")
    if len(desc) < 2:
        raise ValueError("探索目标描述太短")
    if not device:
        raise ValueError("请选择在线 Runner 执行设备（device_id）")
    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise ValueError("Runner 派发未启用（BROWSER_RUN_DISPATCH_ENABLED=0）")

    try:
        await validate_device_online(device)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc

    steps = int(max_steps or UI_AGENT_DEFAULT_STEPS)
    steps = min(max(1, steps), UI_AGENT_MAX_STEPS)
    try:
        config = await resolve_assist_config_for_scene("ui_case_generate", ai_config_id)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc

    job = await create_ui_agent_job(
        project_id=int(project_id),
        page_url=url,
        description=desc,
        max_steps=steps,
        ai_config_id=config.id,
        created_by=username or "",
        run_mode="runner",
        device_id=device,
        source="assistant",
        source_ref=merge_job_platform_base_url(
            {"max_rounds": steps, "headless": bool(headless), "trigger": "assistant"},
            platform_base_url,
        ),
    )
    try:
        await dispatch_ui_agent_to_runner(job, config=config)
    except HTTPException as exc:
        await job.delete()
        raise ValueError(_http_detail(exc)) from exc
    except Exception as exc:
        await job.delete()
        raise ValueError(f"启动 UI Agent 失败: {exc}") from exc

    return {
        "job_id": job.id,
        "status": job.status,
        "project_id": job.project_id,
        "page_url": job.page_url,
        "description": job.description,
        "device_id": job.device_id or device,
        "title": job_type_title(JOB_TYPE_UI_AGENT),
        "poll_path": f"/ai/ui-agent-jobs/{job.id}",
        "job": job_to_dict(job),
        "message": "UI Agent 探索任务已创建，正在启动",
    }
