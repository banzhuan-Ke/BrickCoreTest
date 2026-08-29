"""测试管理 — 进行中计划运行的自动化结果定时补偿同步"""
from __future__ import annotations

import logging

from app.models.test_management import TestPlanRun
from app.modules.test_management.execution_bridge import sync_run_automation_items

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "tm_plan_run_automation_sync"


async def sync_running_plan_automation() -> dict[str, int]:
    runs = await TestPlanRun.filter(is_del=False, status="running").order_by("id")
    synced_runs = 0
    total_synced_items = 0
    for run in runs:
        try:
            data = await sync_run_automation_items(run, username="system_sync")
            if (data.get("synced") or 0) > 0:
                synced_runs += 1
                total_synced_items += int(data.get("synced") or 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("计划运行 sync 失败 run_id=%s: %s", run.id, exc)
    if synced_runs:
        logger.info(
            "[tm_automation_sync] 同步 %s 个运行批次，更新 %s 项",
            synced_runs,
            total_synced_items,
        )
    return {"runs": len(runs), "synced_runs": synced_runs, "synced_items": total_synced_items}


def register_tm_automation_sync_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        sync_running_plan_automation,
        trigger=IntervalTrigger(minutes=3),
        id=SYNC_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
