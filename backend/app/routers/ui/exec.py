"""
执行相关路由
"""
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from tortoise import transactions

from app.models.sys import Device, Environment
from app.models.ui import Suite, Case, Task, UiPlanExecution, UiSuiteExecution, UiCaseExecution
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import UI_CASE_EXECUTE, UI_SUITE_EXECUTE, UI_TASK_EXECUTE
from app.core.mq_producer import MQProducer
from app.core.ai_project_settings import resolve_locator_heal_for_execute
from app.core.ui_execution_stop import stop_plan_execution, stop_suite_execution, stop_case_execution
from app.schemas.ui import RunForm, CaseDebugForm

router = APIRouter(
    prefix="/exec",
    dependencies=[Depends(is_authenticated)],
    tags=["测试运行"]
)


class ExecutionService:
    """
    测试执行服务层
    
    负责组装执行上下文、创建执行记录、分发任务到执行器
    """
    
    @staticmethod
    async def build_env_payload(
        env: Environment,
        browser_type: str,
        headless: bool,
        project_id: int,
        user_heal_override: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        构建执行环境负载；ai_heal_enabled 由 Backend 项目配置计算，不信任 Runner/前端单独决策。
        """
        ai_heal_enabled = await resolve_locator_heal_for_execute(project_id, user_heal_override)
        payload = {
            "headless": headless,
            "browser": browser_type if browser_type in ["chromium", "firefox", "webkit"] else "chromium",
            "target_host": env.host,
            "environment_id": env.id,
            "env_name": env.name,
            "variables": env.global_vars,
            "ai_heal_enabled": ai_heal_enabled,
        }
        return payload

    @staticmethod
    def with_trigger_source(env_payload: Dict[str, Any], trigger_source: Optional[str]) -> Dict[str, Any]:
        if not trigger_source:
            return env_payload
        out = dict(env_payload)
        out["trigger_source"] = trigger_source.strip()
        return out
    
    @staticmethod
    async def run_suite_setup_sql(suite_: Suite, env_id: int) -> None:
        """执行 UI 套件前置 SQL（数据工厂 setup）"""
        if not (suite_.setup_sql_ids or []):
            return
        from app.core.db_factory_service import run_sql_templates_by_ids
        from app.models.sys import Project

        proj = await Project.get_or_none(id=suite_.project_id, is_del=False)
        env = await Environment.get_or_none(id=env_id, is_del=False)
        variables = {
            **((proj.global_vars or {}) if proj else {}),
            **((env.global_vars or {}) if env else {}),
        }
        setup_res = await run_sql_templates_by_ids(
            suite_.setup_sql_ids, variables, env_id, suite_.project_id, phase="setup"
        )
        if not setup_res.get("success"):
            logs = setup_res.get("logs") or []
            detail = logs[0].get("message") if logs else "前置 SQL 执行失败"
            raise HTTPException(status_code=422, detail=f"套件前置 SQL 执行失败: {detail}")

    @staticmethod
    def build_case_item(case_execution: UiCaseExecution, case_: Case, step_meta: Any) -> Dict[str, Any]:
        """构建单个用例执行项"""
        return {
            "execution_id": case_execution.id,
            "id": case_.id,
            "name": case_.name,
            "skip": step_meta.skip if step_meta else False,
            "steps": case_.steps
        }
    
    @staticmethod
    def build_suite_payload(suite_: Suite, suite_record: UiSuiteExecution,
                            cases: List[Dict], plan_record: UiPlanExecution = None) -> Dict[str, Any]:
        """构建套件执行负载"""
        payload = {
            "id": suite_.id,
            "suite_execution_id": suite_record.id,
            "name": suite_.name,
            "username": suite_record.username,
            "pre_actions": suite_.pre_actions or [],
            "cases": cases
        }
        if plan_record:
            payload["plan_execution_id"] = plan_record.id
        return payload
    
    @staticmethod
    async def dispatch_to_device(env_payload: Dict, suite_payload: Dict, device_id: str) -> bool:
        """将执行任务分发到指定设备"""
        device = await Device.get_or_none(id=device_id)
        if not device or device.status != "在线":
            return False
        
        mq = MQProducer()
        try:
            mq.send_test_task(env_payload, suite_payload, device_id)
            return True
        finally:
            mq.close()


# 执行单条用例
@router.post("/cases/{case_id}", summary="执行用例", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def run_case(case_id: int, item: RunForm):
    """执行单条用例"""
    async with transactions.in_transaction():
        case_ = await Case.get_or_none(id=case_id, is_del=False)
        if not case_:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="目标用例不存在或已被移除"
            )
        
        env = await Environment.get_or_none(id=item.env_id, is_del=False)
        if not env:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="所选运行环境不存在或已被移除"
            )
        
        env_payload = await ExecutionService.build_env_payload(
            env,
            item.browser_type,
            item.config,
            case_.project_id,
            item.ai_heal_enabled,
        )
        env_payload = ExecutionService.with_trigger_source(env_payload, item.trigger_source)
        env_payload["device_id"] = item.device_id

        case_execution = await UiCaseExecution.create(
            case=case_,
            username=item.username,
            env=env_payload,
            is_del=False
        )
        
        suite_payload = {
            "id": case_.id,
            "name": case_.name,
            "case_execution_id": case_execution.id,
            "pre_actions": [],
            "username": item.username,
            "cases": [
                {
                    "execution_id": case_execution.id,
                    "id": case_.id,
                    "name": case_.name,
                    "skip": False,
                    "steps": case_.steps
                }
            ]
        }
        
        dispatched = await ExecutionService.dispatch_to_device(
            env_payload, suite_payload, item.device_id
        )
        
        return {
            "msg": "用例已加入执行队列，正在等待执行器处理" if dispatched else "用例已创建，但暂无在线设备可执行",
            "execution_id": case_execution.id
        }


# 步骤级调试：仅执行前 N 步（含当前步）
@router.post(
    "/cases/{case_id}/debug",
    summary="调试用例至指定步骤",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))],
)
async def debug_case(case_id: int, item: CaseDebugForm):
    """执行 steps[0:through_index+1] 后停止，支持使用编辑器中未保存的步骤。"""
    if not item.steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="步骤列表不能为空",
        )
    if item.through_index >= len(item.steps):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"through_index 超出范围（共 {len(item.steps)} 步）",
        )

    async with transactions.in_transaction():
        case_ = await Case.get_or_none(id=case_id, is_del=False)
        if not case_:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="目标用例不存在或已被移除",
            )

        env = await Environment.get_or_none(id=item.env_id, is_del=False)
        if not env:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="所选运行环境不存在或已被移除",
            )

        debug_steps = item.steps[: item.through_index + 1]
        env_payload = await ExecutionService.build_env_payload(
            env,
            item.browser_type,
            item.config,
            case_.project_id,
            item.ai_heal_enabled,
        )
        env_payload["debug_mode"] = True
        env_payload["debug_through_index"] = item.through_index
        env_payload["device_id"] = item.device_id

        case_execution = await UiCaseExecution.create(
            case=case_,
            username=item.username,
            env=env_payload,
            is_del=False,
        )

        suite_payload = {
            "id": case_.id,
            "name": f"{case_.name}（调试至第 {item.through_index + 1} 步）",
            "case_execution_id": case_execution.id,
            "pre_actions": [],
            "username": item.username,
            "cases": [
                {
                    "execution_id": case_execution.id,
                    "id": case_.id,
                    "name": case_.name,
                    "skip": False,
                    "steps": debug_steps,
                }
            ],
        }

        dispatched = await ExecutionService.dispatch_to_device(
            env_payload, suite_payload, item.device_id
        )

        return {
            "msg": "调试任务已加入执行队列" if dispatched else "调试记录已创建，但暂无在线设备可执行",
            "execution_id": case_execution.id,
            "through_index": item.through_index,
            "step_count": len(debug_steps),
        }


# 运行测试套件
@router.post("/suites/{suite_id}", summary="执行套件", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_SUITE_EXECUTE))])
async def run_suite(suite_id: int, item: RunForm):
    """运行测试套件"""
    async with transactions.in_transaction():
        suite_ = await Suite.get_or_none(id=suite_id, is_del=False).prefetch_related("steps")
        if not suite_:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="目标套件不存在或已被移除"
            )
        
        env = await Environment.get_or_none(id=item.env_id, is_del=False)
        if not env:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="所选运行环境不存在或已被移除"
            )
        
        env_payload = await ExecutionService.build_env_payload(
            env,
            item.browser_type,
            item.config,
            suite_.project_id,
            item.ai_heal_enabled,
        )
        env_payload = ExecutionService.with_trigger_source(env_payload, item.trigger_source)
        env_payload["device_id"] = item.device_id

        suite_record = await UiSuiteExecution.create(
            suite=suite_,
            username=item.username,
            env=env_payload,
            device_id=item.device_id,
            is_del=False
        )
        
        cases = []
        for step in await suite_.steps.filter(is_del=False).order_by("sort"):
            case_ = await step.cases
            if case_.is_del:
                continue
            
            case_execution = await UiCaseExecution.create(
                case=case_,
                username=item.username,
                suite_execution=suite_record,
                env=env_payload,
                is_del=False
            )
            cases.append(ExecutionService.build_case_item(case_execution, case_, step))
        
        suite_record.case_count = len(cases)
        await suite_record.save()

        await ExecutionService.run_suite_setup_sql(suite_, item.env_id)

        suite_payload = ExecutionService.build_suite_payload(
            suite_, suite_record, cases
        )
        
        dispatched = await ExecutionService.dispatch_to_device(
            env_payload, suite_payload, item.device_id
        )
        
        return {
            "msg": "套件已加入执行队列，正在等待执行器处理" if dispatched else "套件已创建，但暂无在线设备可执行",
            "suite_record_id": suite_record.id
        }


# 运行测试计划
@router.post("/tasks/{task_id}", summary="执行任务", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_TASK_EXECUTE))])
async def run_task(task_id: int, item: RunForm):
    """运行测试计划"""
    async with transactions.in_transaction():
        task_ = await Task.get_or_none(id=task_id, is_del=False).prefetch_related("suites", "project")
        if not task_:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="目标测试计划不存在或已被移除"
            )
        
        env = await Environment.get_or_none(id=item.env_id, is_del=False)
        if not env:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="所选运行环境不存在或已被移除"
            )
        
        env_payload = await ExecutionService.build_env_payload(
            env,
            item.browser_type,
            item.config,
            task_.project_id,
            item.ai_heal_enabled,
        )
        env_payload = ExecutionService.with_trigger_source(env_payload, item.trigger_source)
        env_payload["device_id"] = item.device_id

        plan_record = await UiPlanExecution.create(
            task=task_,
            username=item.username,
            env=env_payload,
            device_id=item.device_id,
            project=task_.project,
            is_del=False,
            execution_log=[]
        )
        
        task_count = 0
        for suite in await task_.suites.filter(is_del=False).all():
            suite_ = await Suite.get_or_none(id=suite.id, is_del=False).prefetch_related("steps")
            if not suite_:
                continue
            
            suite_record = await UiSuiteExecution.create(
                suite=suite_,
                username=item.username,
                env=env_payload,
                device_id=item.device_id,
                plan_execution=plan_record,
                is_del=False
            )
            
            cases = []
            for step in await suite_.steps.filter(is_del=False).order_by("sort"):
                case_ = await step.cases
                if case_.is_del:
                    continue
                
                case_execution = await UiCaseExecution.create(
                    case=case_,
                    username=item.username,
                    suite_execution=suite_record,
                    env=env_payload,
                    is_del=False
                )
                cases.append(ExecutionService.build_case_item(case_execution, case_, step))
            
            task_count += len(cases)
            suite_record.case_count = len(cases)
            await suite_record.save()

            await ExecutionService.run_suite_setup_sql(suite_, item.env_id)
            
            suite_payload = ExecutionService.build_suite_payload(
                suite_, suite_record, cases, plan_record
            )
            
            await ExecutionService.dispatch_to_device(
                env_payload, suite_payload, item.device_id
            )
        
        plan_record.case_count = task_count
        await plan_record.save()
        
        return {
            "msg": "测试计划已加入执行队列，正在等待执行器处理",
            "task_record_id": plan_record.id
        }


@router.post("/stop/{record_id}", summary="停止 UI 计划执行", status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def stop_execution(record_id: int):
    """停止 UI 测试计划执行（通过 MQ 通知 Runner 真正中断）"""
    return await stop_plan_execution(record_id)


@router.post("/stop/suite/{record_id}", summary="停止 UI 套件执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_SUITE_EXECUTE))])
async def stop_suite_execution_route(record_id: int):
    """停止 UI 套件执行"""
    return await stop_suite_execution(record_id)


@router.post("/stop/case/{record_id}", summary="停止 UI 用例执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def stop_case_execution_route(record_id: int):
    """停止 UI 单用例/调试执行"""
    return await stop_case_execution(record_id)
