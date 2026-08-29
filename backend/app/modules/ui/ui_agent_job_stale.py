"""UI Agent Job 僵死恢复（进程重启后 Runner 任务无法自行结束）。"""

from __future__ import annotations

import logging

from app.models.ai import UiAgentJob
from app.modules.ui.ui_agent_job_service import finish_ui_agent_job

logger = logging.getLogger(__name__)


async def recover_stale_ui_agent_jobs_on_startup() -> int:
    """Backend 重启后清理升级前遗留的 local 模式 job（进程内 asyncio 已不可恢复）。

    现网不再创建 local job，此扫描对新部署多为 0 条；保留以兼容升级前 DB 数据。
    Runner 模式 job 不在此处理：Backend 重启不等于 Runner 掉线，交由心跳超时机制。
    """
    jobs = await UiAgentJob.filter(
        status__in=["pending", "running"],
        run_mode="local",
    ).all()
    if not jobs:
        return 0
    count = 0
    for job in jobs:
        await finish_ui_agent_job(
            job,
            status="failed",
            error_message="服务重启，本地 Agent 任务已中断，请重新创建",
        )
        count += 1
    logger.warning("[ui_agent] recovered %s stale job(s) after startup", count)
    return count
