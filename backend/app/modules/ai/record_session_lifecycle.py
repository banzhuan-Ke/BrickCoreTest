"""AI 录制会话：僵尸态恢复（Runner 异常退出未回调时释放设备占用）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.ai import AiRecordSession

logger = logging.getLogger(__name__)

# 录制期间 Runner 约 1s 心跳一次；超过该时长无更新视为僵尸
STALE_RECORDING_SECONDS = 180


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def recover_stale_record_session(record: AiRecordSession) -> bool:
    """将长期无心跳的 recording 标记为 failed，释放设备。返回是否已修改。"""
    if record.status != "recording":
        return False

    ref = record.update_time or record.create_time
    if not ref:
        return False

    elapsed = (utc_now() - as_utc(ref)).total_seconds()
    if elapsed <= STALE_RECORDING_SECONDS:
        return False

    record.status = "failed"
    record.error = record.error or "录制会话长时间无心跳，系统已自动结束并释放设备"
    await record.save()
    logger.info(
        "[record_session] 恢复僵尸录制: id=%s device=%s idle=%ss",
        record.id,
        record.device_id,
        int(elapsed),
    )
    return True


async def get_active_recording_on_device(device_id: str) -> Optional[AiRecordSession]:
    """查询设备上进行中的录制；会先尝试恢复僵尸态。"""
    if not device_id:
        return None

    record = await AiRecordSession.filter(
        device_id=device_id,
        status="recording",
    ).order_by("-id").first()
    if not record:
        return None

    await recover_stale_record_session(record)
    if record.status == "recording":
        return record
    return None
