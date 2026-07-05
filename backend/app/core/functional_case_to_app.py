"""
功能用例库 → App 自动化：描述拼装、批量预览生成、导入 app_case 表
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.core.app_keywords import (
    APP_DEFAULT_PARAMS,
    APP_REQUIRED_PARAMS,
    APP_VALID_METHODS,
    METHOD_TO_KEYWORD,
)
from app.core.app_locator_validate import validate_case_steps_driver_mode_for_project, validate_driver_mode
from app.core.functional_case_to_ui import (
    DESCRIPTION_MAX_LEN,
    LOGIN_STRATEGIES_WITH_CREDENTIALS,
    LOGIN_STRATEGIES_WITH_PREPEND,
    build_ui_description,
    enrich_description_with_credentials,
    priority_to_level,
    truncate_case_name,
)
from app.models.ai import AiFunctionalCase
from app.models.app import AppCase

logger = logging.getLogger(__name__)

MAX_APP_PREVIEW_BATCH = 10


@dataclass
class AppGenerationContext:
    app_id: Optional[str] = None
    driver_mode: str = "hybrid"
    ai_config_id: Optional[int] = None
    test_username: Optional[str] = None
    test_password: Optional[str] = None
    login_app_case_id: Optional[int] = None
    login_strategy: str = "none"
    extra_context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AppGenerationContext":
        data = data or {}
        login_id = data.get("login_app_case_id")
        parsed_login_id = None
        if login_id not in (None, ""):
            try:
                parsed_login_id = int(login_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="login_app_case_id 无效") from exc
        return cls(
            app_id=(data.get("app_id") or "").strip() or None,
            driver_mode=(data.get("driver_mode") or "hybrid").strip() or "hybrid",
            ai_config_id=data.get("ai_config_id"),
            test_username=(data.get("test_username") or "").strip() or None,
            test_password=(data.get("test_password") or "").strip() or None,
            login_app_case_id=parsed_login_id,
            login_strategy=(data.get("login_strategy") or "none").strip() or "none",
            extra_context=(data.get("extra_context") or "").strip() or None,
        )


def validate_app_generation_context(ctx: AppGenerationContext) -> None:
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND and not ctx.login_app_case_id:
        raise HTTPException(status_code=400, detail="选择「引用登录 App 用例」时需指定登录用例")
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_CREDENTIALS and not ctx.test_username:
        raise HTTPException(status_code=400, detail="选择「附加测试账号」时需填写用户名")
    if ctx.driver_mode not in ("native", "vision", "hybrid", "hybrid_web", "mobile_chrome"):
        raise HTTPException(status_code=400, detail="driver_mode 无效")


def build_full_app_description(fc: AiFunctionalCase, ctx: AppGenerationContext) -> str:
    parts: list[str] = [build_ui_description(fc)]

    if ctx.app_id:
        parts.append(f"【目标应用】包名/Activity：{ctx.app_id}")
    if ctx.extra_context:
        parts.append(f"【细节补充】\n{ctx.extra_context}")

    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_CREDENTIALS and ctx.test_username:
        cred_lines = [f"【测试账号】{ctx.test_username}"]
        if ctx.test_password:
            cred_lines.append(f"【测试密码】{ctx.test_password}")
        parts.append("\n".join(cred_lines))

    instructions: list[str] = []
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND:
        instructions.append("登录步骤由已有 App 自动化用例前置提供，请勿重复生成登录步骤。")
    elif ctx.login_strategy in LOGIN_STRATEGIES_WITH_CREDENTIALS:
        instructions.append("请首先启动应用并完成登录，再执行业务测试步骤。")
    elif ctx.app_id or ctx.extra_context:
        instructions.append("请按目标应用与细节补充进入业务页面后再执行功能测试。")

    instructions.append(
        "仅生成功能测试所需步骤；完成用例预期验证后停止，不要重复操作。"
    )
    instructions.append(f"驱动模式偏好：{ctx.driver_mode}（native=原生控件；hybrid=原生+图像；vision=图像为主）。")
    parts.append("【执行说明】\n" + "\n".join(f"- {line}" for line in instructions))

    text = "\n\n".join(p for p in parts if p.strip()).strip()
    return text[:DESCRIPTION_MAX_LEN]


def build_case_description_from_functional(
    fc: AiFunctionalCase,
    ctx: AppGenerationContext | None = None,
) -> str:
    parts: list[str] = [build_ui_description(fc)]
    if ctx:
        if ctx.app_id:
            parts.append(f"【目标应用】{ctx.app_id}")
        if ctx.extra_context:
            parts.append(f"【细节补充】\n{ctx.extra_context}")
    return "\n\n".join(p for p in parts if p.strip())[:DESCRIPTION_MAX_LEN]


def _locator_filled(locator: Any) -> bool:
    if not isinstance(locator, dict):
        return False
    by_value = str(locator.get("by") or "").strip().lower()
    if not by_value:
        return False
    if by_value == "coordinates":
        val = locator.get("value")
        return (
            isinstance(val, dict)
            and val.get("x") is not None
            and val.get("y") is not None
        )
    return bool(str(locator.get("value") or "").strip())


def _param_filled(key: str, params: dict) -> bool:
    if key not in params:
        return False
    val = params[key]
    if key == "locator":
        return _locator_filled(val)
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def normalize_app_steps(steps: list) -> tuple[list[dict], list[str]]:
    valid_steps: list[dict] = []
    errors: list[str] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"第 {i + 1} 步不是对象")
            continue

        method = (step.get("method") or "").strip()
        if method not in APP_VALID_METHODS:
            errors.append(f"第 {i + 1} 步 method '{method}' 不在支持列表中，已跳过")
            continue

        params = step.get("params", {}) or {}
        if not isinstance(params, dict):
            params = {}

        required = APP_REQUIRED_PARAMS.get(method, set())
        missing = {k for k in required if not _param_filled(k, params)}
        if missing:
            errors.append(f"第 {i + 1} 步 '{method}' 缺少必填参数: {', '.join(sorted(missing))}")
            continue

        defaults = APP_DEFAULT_PARAMS.get(method, {})
        for key, val in defaults.items():
            if key not in params or params[key] is None:
                params[key] = val

        keyword = METHOD_TO_KEYWORD.get(method, step.get("keyword", method))
        normalized = {
            "id": step.get("id") or f"step_{int(time.time() * 1000)}_{i}",
            "keyword": step.get("keyword") or keyword,
            "desc": step.get("desc") or keyword,
            "method": method,
            "params": params,
            "children": step.get("children", []) if isinstance(step.get("children"), list) else [],
        }
        if method == "condition_branch":
            normalized["branches"] = step.get("branches") if isinstance(step.get("branches"), list) else []
        if step.get("meta") and isinstance(step.get("meta"), dict):
            normalized["meta"] = step["meta"]
        valid_steps.append(normalized)

    return valid_steps, errors


async def load_login_prefix_steps(project_id: int, login_app_case_id: int) -> list:
    login_case = await AppCase.get_or_none(
        id=login_app_case_id, project_id=project_id, is_del=False
    )
    if not login_case:
        raise HTTPException(status_code=400, detail=f"登录 App 用例 #{login_app_case_id} 不存在")
    return list(login_case.steps or [])


async def finalize_app_steps(
    project_id: int, steps: list, ctx: AppGenerationContext
) -> tuple[list, int]:
    prefix_count = 0
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND and ctx.login_app_case_id:
        prefix = await load_login_prefix_steps(project_id, ctx.login_app_case_id)
        prefix_count = len(prefix)
        return prefix + list(steps or []), prefix_count
    return list(steps or []), prefix_count


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_app_extra(fc: AiFunctionalCase) -> dict[str, Any]:
    extra = fc.extra if isinstance(fc.extra, dict) else {}
    app = extra.get("app_import")
    return app if isinstance(app, dict) else {}


async def _resolve_ai_config(ai_config_id: Optional[int]) -> Any:
    from app.core.ai_scene_config import resolve_config_for_scene

    return await resolve_config_for_scene("app_case_generate", ai_config_id)


async def _generate_app_steps(
    *,
    description: str,
    ctx: AppGenerationContext,
    project_id: int,
    user_info: dict,
) -> dict[str, Any]:
    from app.core.ai_prompts import PromptManager
    from app.core.ai_usage_log import log_ai_usage
    from app.routers.ai.generate import _call_llm, _extract_json_array

    config = await _resolve_ai_config(ctx.ai_config_id)
    enriched = enrich_description_with_credentials(description, ctx)  # type: ignore[arg-type]
    start_time = time.time()

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "app_case_generation",
            {
                "description": enriched,
                "app_id": ctx.app_id or "",
                "driver_mode": ctx.driver_mode,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Prompt 渲染失败: {e}") from e

    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "app_case_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=description[:500],
            output_summary=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e

    raw_response = resp.get("content", "")
    tokens_used = int(resp.get("tokens") or 0)
    steps = _extract_json_array(raw_response)
    if not steps:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "app_case_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            status="failed",
            input_summary=description[:500],
            output_summary="JSON 解析失败",
        )
        raise HTTPException(status_code=500, detail="AI 返回内容无法解析为步骤 JSON，请重试或调整描述")

    valid_steps, errors = normalize_app_steps(steps)
    if not valid_steps:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "app_case_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            status="failed",
            input_summary=description[:500],
            output_summary="无有效步骤",
        )
        detail = "AI 未返回有效步骤"
        if errors:
            detail = f"{detail}（{errors[0]}）"
        raise HTTPException(status_code=500, detail=detail)
    duration_ms = int((time.time() - start_time) * 1000)
    await log_ai_usage(
        config,
        "app_case_generate",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=description[:500],
        output_summary=f"生成 {len(valid_steps)} 步",
    )
    return {
        "steps": valid_steps,
        "errors": errors,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
    }


async def _set_app_import_status(
    fc: AiFunctionalCase,
    status: str,
    *,
    ctx: Optional[AppGenerationContext] = None,
    steps: Optional[list] = None,
    errors: Optional[list] = None,
    app_case_id: Optional[int] = None,
    error: Optional[str] = None,
    login_prefix_count: int = 0,
) -> None:
    extra = dict(fc.extra) if isinstance(fc.extra, dict) else {}
    app = dict(_get_app_extra(fc))
    app["status"] = status
    app["updated_at"] = _utc_now_iso()
    if ctx:
        if ctx.app_id is not None:
            app["app_id"] = ctx.app_id
        if ctx.ai_config_id is not None:
            app["ai_config_id"] = ctx.ai_config_id
        app["driver_mode"] = ctx.driver_mode
        app["login_strategy"] = ctx.login_strategy
        app["login_app_case_id"] = ctx.login_app_case_id
        if ctx.extra_context:
            app["extra_context"] = ctx.extra_context
    if steps is not None:
        app["preview_steps_count"] = len(steps)
    if login_prefix_count:
        app["login_prefix_steps_count"] = login_prefix_count
    if errors is not None:
        app["preview_errors"] = errors[:10]
    if app_case_id is not None:
        app["app_case_id"] = app_case_id
    if error is not None:
        app["error"] = error
    elif status in ("generated", "imported"):
        app.pop("error", None)
    extra["app_import"] = app
    fc.extra = extra
    await fc.save(update_fields=["extra"])


async def preview_functional_cases_to_app(
    *,
    project_id: int,
    case_ids: list[int],
    ctx: AppGenerationContext,
    user_info: dict,
) -> dict[str, Any]:
    validate_app_generation_context(ctx)
    if not case_ids:
        raise HTTPException(status_code=400, detail="请至少选择一条功能用例")
    if len(case_ids) > MAX_APP_PREVIEW_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多预览 {MAX_APP_PREVIEW_BATCH} 条，请分批操作",
        )

    cases = await AiFunctionalCase.filter(
        project_id=project_id, id__in=case_ids, is_del=False
    ).all()
    found_ids = {c.id for c in cases}
    missing = [i for i in case_ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=400, detail=f"用例不存在或无权访问: {missing}")

    order_map = {cid: idx for idx, cid in enumerate(case_ids)}
    cases.sort(key=lambda c: order_map.get(c.id, 9999))

    items: list[dict[str, Any]] = []
    total_tokens = 0

    for fc in cases:
        description = build_full_app_description(fc, ctx)
        item: dict[str, Any] = {
            "functional_case_id": fc.id,
            "title": fc.title,
            "description": description,
            "suggested_case_name": truncate_case_name(fc.title),
            "suggested_level": priority_to_level(fc.priority),
            "suggested_driver_mode": ctx.driver_mode,
            "status": "pending",
            "steps": [],
            "errors": [],
            "tokens_used": 0,
            "login_prefix_count": 0,
            "error": "",
        }
        await _set_app_import_status(fc, "generating", ctx=ctx)
        try:
            data = await _generate_app_steps(
                description=description,
                ctx=ctx,
                project_id=project_id,
                user_info=user_info,
            )
            steps = data.get("steps") or []
            errors = data.get("errors") or []
            tokens = int(data.get("tokens_used") or 0)
            total_tokens += tokens
            if not steps:
                item["status"] = "failed"
                item["error"] = "AI 未返回有效步骤"
                await _set_app_import_status(
                    fc, "failed", ctx=ctx, errors=errors, error=item["error"]
                )
            else:
                final_steps, prefix_n = await finalize_app_steps(project_id, steps, ctx)
                item["status"] = "success"
                item["steps"] = final_steps
                item["errors"] = errors
                item["tokens_used"] = tokens
                item["login_prefix_count"] = prefix_n
                await _set_app_import_status(
                    fc,
                    "generated",
                    ctx=ctx,
                    steps=final_steps,
                    errors=errors,
                    login_prefix_count=prefix_n,
                )
        except HTTPException as e:
            item["status"] = "failed"
            item["error"] = str(e.detail)
            await _set_app_import_status(fc, "failed", ctx=ctx, error=item["error"])
        except Exception as e:
            logger.exception("[functional_case_to_app] preview item %s failed", fc.id)
            item["status"] = "failed"
            item["error"] = str(e)
            await _set_app_import_status(fc, "failed", ctx=ctx, error=item["error"])
        items.append(item)

    success_count = sum(1 for i in items if i["status"] == "success")
    return {
        "items": items,
        "success_count": success_count,
        "failed_count": len(items) - success_count,
        "total_tokens": total_tokens,
    }


async def import_functional_cases_to_app(
    *,
    project_id: int,
    username: str,
    ctx: AppGenerationContext,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_app_generation_context(ctx)
    if not items:
        raise HTTPException(status_code=400, detail="没有可导入的项")

    imported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for raw in items:
        fc_id = raw.get("functional_case_id")
        steps = raw.get("steps") or []
        if not fc_id:
            failed.append({"functional_case_id": fc_id, "error": "缺少 functional_case_id"})
            continue
        if not steps:
            failed.append({"functional_case_id": fc_id, "error": "步骤为空"})
            continue

        fc = await AiFunctionalCase.get_or_none(
            id=int(fc_id), project_id=project_id, is_del=False
        )
        if not fc:
            failed.append({"functional_case_id": fc_id, "error": "功能用例不存在"})
            continue

        case_name = (raw.get("case_name") or "").strip() or truncate_case_name(fc.title)
        level = (raw.get("level") or "").strip() or priority_to_level(fc.priority)
        driver_mode = (raw.get("driver_mode") or ctx.driver_mode or "hybrid").strip()
        case_description = (raw.get("case_description") or "").strip()
        if not case_description:
            case_description = build_case_description_from_functional(fc, ctx)

        try:
            prefix_n = int(raw.get("login_prefix_count") or 0)
            if prefix_n > 0:
                final_steps = list(steps)
            else:
                final_steps, prefix_n = await finalize_app_steps(project_id, steps, ctx)
            driver_mode = validate_driver_mode(driver_mode)
            driver_mode = await validate_case_steps_driver_mode_for_project(
                driver_mode, final_steps, project_id
            )
            app_case = await AppCase.create(
                name=case_name[:100],
                project_id=project_id,
                steps=final_steps,
                level=level,
                platform_scope="android",
                driver_mode=driver_mode,
                description=case_description or None,
                username=username,
                update_by=username,
                is_del=False,
            )
            await _set_app_import_status(
                fc,
                "imported",
                ctx=ctx,
                steps=final_steps,
                app_case_id=app_case.id,
                login_prefix_count=prefix_n,
            )
            imported.append(
                {
                    "functional_case_id": fc.id,
                    "app_case_id": app_case.id,
                    "case_name": app_case.name,
                    "login_prefix_count": prefix_n,
                }
            )
        except HTTPException as e:
            await _set_app_import_status(fc, "failed", ctx=ctx, error=str(e.detail))
            failed.append({"functional_case_id": fc_id, "error": str(e.detail)})
        except Exception as e:
            logger.exception("[functional_case_to_app] import failed fc=%s", fc_id)
            await _set_app_import_status(fc, "failed", ctx=ctx, error=str(e))
            failed.append({"functional_case_id": fc_id, "error": str(e)})

    return {
        "imported_count": len(imported),
        "failed_count": len(failed),
        "imported": imported,
        "failed": failed,
    }
