"""性能测试资源的项目归属校验"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.core.platform.auth import is_authenticated
from app.core.platform.project_access import (
    PROJECT_ROLE_MEMBER,
    PROJECT_ROLE_VIEWER,
    assert_project_access,
)
from app.models.perf import PerfCronJob, PerfRecord, PerfScene, PerfWorker
from app.models.sys import Environment


async def assert_env_in_project(env_id: int, project_id: int) -> Environment:
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="环境不存在")
    if env.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="运行环境与场景/项目不匹配",
        )
    return env


async def get_scene_for_viewer(
    scene_id: int,
    user_info: dict = Depends(is_authenticated),
) -> PerfScene:
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在")
    await assert_project_access(user_info, scene.project_id, min_role=PROJECT_ROLE_VIEWER)
    return scene


async def get_scene_for_member(
    scene_id: int,
    user_info: dict = Depends(is_authenticated),
) -> PerfScene:
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在")
    await assert_project_access(user_info, scene.project_id, min_role=PROJECT_ROLE_MEMBER)
    return scene


async def get_record_for_viewer(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
) -> PerfRecord:
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    await assert_project_access(user_info, record.project_id, min_role=PROJECT_ROLE_VIEWER)
    return record


async def get_record_for_member(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
) -> PerfRecord:
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    await assert_project_access(user_info, record.project_id, min_role=PROJECT_ROLE_MEMBER)
    return record


async def get_worker_for_member(
    worker_id: int,
    user_info: dict = Depends(is_authenticated),
) -> PerfWorker:
    worker = await PerfWorker.get_or_none(id=worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker 不存在")
    if worker.project_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Worker 未绑定项目")
    await assert_project_access(user_info, worker.project_id, min_role=PROJECT_ROLE_MEMBER)
    return worker


async def get_cron_for_viewer(
    job_id: str,
    user_info: dict = Depends(is_authenticated),
) -> PerfCronJob:
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    await assert_project_access(user_info, job.project_id, min_role=PROJECT_ROLE_VIEWER)
    return job


async def get_cron_for_member(
    job_id: str,
    user_info: dict = Depends(is_authenticated),
) -> PerfCronJob:
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    await assert_project_access(user_info, job.project_id, min_role=PROJECT_ROLE_MEMBER)
    return job


async def assert_scene_in_project(scene_id: int, project_id: int) -> PerfScene:
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在")
    if scene.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="场景与项目不匹配",
        )
    return scene
