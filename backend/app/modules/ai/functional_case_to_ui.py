"""
功能用例库 → UI 自动化：描述拼装、批量预览生成、导入 case 表
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.core.case.case_steps import align_steps_expects
from app.models.ai import AiConfig, AiFunctionalCase
from app.models.ui import Case

logger = logging.getLogger(__name__)

MAX_UI_PREVIEW_BATCH = 10
DESCRIPTION_MAX_LEN = 2000

LOGIN_STRATEGIES_WITH_CREDENTIALS = frozenset({"credentials", "both"})
LOGIN_STRATEGIES_WITH_PREPEND = frozenset({"prepend_login", "both"})


@dataclass
class UiGenerationContext:
    page_url: Optional[str] = None
    ai_config_id: Optional[int] = None
    test_username: Optional[str] = None
    test_password: Optional[str] = None
    login_ui_case_id: Optional[int] = None
    login_strategy: str = "none"
    source_method: str = "ai"
    extra_context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "UiGenerationContext":
        data = data or {}
        login_id = data.get("login_ui_case_id")
        return cls(
            page_url=(data.get("page_url") or "").strip() or None,
            ai_config_id=data.get("ai_config_id"),
            test_username=(data.get("test_username") or "").strip() or None,
            test_password=(data.get("test_password") or "").strip() or None,
            login_ui_case_id=int(login_id) if login_id else None,
            login_strategy=(data.get("login_strategy") or "none").strip() or "none",
            source_method=(data.get("source_method") or "ai").strip() or "ai",
            extra_context=(data.get("extra_context") or "").strip() or None,
        )


def validate_ui_generation_context(ctx: UiGenerationContext) -> None:
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND and not ctx.login_ui_case_id:
        raise HTTPException(status_code=400, detail="选择「引用登录用例」时需指定登录 UI 用例")
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_CREDENTIALS and not ctx.test_username:
        raise HTTPException(status_code=400, detail="选择「附加测试账号」时需填写用户名")


def enrich_description_with_credentials(description: str, ctx: UiGenerationContext) -> str:
    if ctx.login_strategy not in LOGIN_STRATEGIES_WITH_CREDENTIALS:
        return description[:DESCRIPTION_MAX_LEN]
    if not ctx.test_username:
        return description[:DESCRIPTION_MAX_LEN]
    lines = [description, f"【测试账号】{ctx.test_username}"]
    if ctx.test_password:
        lines.append(f"【测试密码】{ctx.test_password}")
    return "\n".join(lines)[:DESCRIPTION_MAX_LEN]


def _append_credentials_block(parts: list[str], ctx: UiGenerationContext) -> None:
    if ctx.login_strategy not in LOGIN_STRATEGIES_WITH_CREDENTIALS or not ctx.test_username:
        return
    cred_lines = [f"【测试账号】{ctx.test_username}"]
    if ctx.test_password:
        cred_lines.append(f"【测试密码】{ctx.test_password}")
    parts.append("\n".join(cred_lines))


def build_full_ui_description(fc: AiFunctionalCase, ctx: UiGenerationContext) -> str:
    """拼装完整 UI 生成描述：功能用例 + 页面/账号/前置导航 + 执行约束"""
    parts: list[str] = [build_ui_description(fc)]

    if ctx.page_url:
        parts.append(f"【目标页面】{ctx.page_url}")

    if ctx.extra_context:
        parts.append(f"【细节补充】\n{ctx.extra_context}")

    _append_credentials_block(parts, ctx)

    instructions: list[str] = []
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND:
        instructions.append("登录步骤由已有 UI 自动化用例前置提供，请勿重复生成登录步骤。")
    elif ctx.login_strategy in LOGIN_STRATEGIES_WITH_CREDENTIALS:
        instructions.append(
            "请首先打开目标页面，使用测试账号完成登录；若存在细节补充，登录后按说明进入目标业务模块。"
        )
    elif ctx.page_url or ctx.extra_context:
        instructions.append("请按目标页面与细节补充进入业务页面后再执行功能测试。")

    instructions.append(
        "仅生成功能测试所需步骤；完成用例预期验证后停止，不要重复操作、不要循环切换同一配置项。"
    )
    parts.append("【执行说明】\n" + "\n".join(f"- {line}" for line in instructions))

    text = "\n\n".join(p for p in parts if p.strip()).strip()
    return text[:DESCRIPTION_MAX_LEN]


def build_case_description_from_functional(
    fc: AiFunctionalCase,
    ctx: UiGenerationContext | None = None,
) -> str:
    """Web 用例描述：功能用例标题/步骤/预期 + 可选页面与补充说明。"""
    parts: list[str] = [build_ui_description(fc)]
    if ctx:
        if ctx.page_url:
            parts.append(f"【目标页面】{ctx.page_url}")
        if ctx.extra_context:
            parts.append(f"【细节补充】\n{ctx.extra_context}")
    return "\n\n".join(p for p in parts if p.strip())[:DESCRIPTION_MAX_LEN]


async def load_login_prefix_steps(project_id: int, login_ui_case_id: int) -> list:
    login_case = await Case.get_or_none(
        id=login_ui_case_id, project_id=project_id, is_del=False
    )
    if not login_case:
        raise HTTPException(status_code=400, detail=f"登录 UI 用例 #{login_ui_case_id} 不存在")
    return list(login_case.steps or [])


async def finalize_ui_steps(
    project_id: int, steps: list, ctx: UiGenerationContext
) -> tuple[list, int]:
    """合并登录前置步骤，返回 (最终步骤, 前置步数)"""
    prefix_count = 0
    if ctx.login_strategy in LOGIN_STRATEGIES_WITH_PREPEND and ctx.login_ui_case_id:
        prefix = await load_login_prefix_steps(project_id, ctx.login_ui_case_id)
        prefix_count = len(prefix)
        return prefix + list(steps or []), prefix_count
    return list(steps or []), prefix_count


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ui_description(fc: AiFunctionalCase) -> str:
    """将功能用例拼装为 UI 生成描述"""
    parts: list[str] = []
    title = (fc.title or "").strip()
    if title:
        parts.append(f"【用例】{title}")
    pre = (fc.precondition or "").strip()
    if pre:
        parts.append(f"【前置条件】{pre}")
    steps = align_steps_expects(fc.steps or [])
    if steps:
        parts.append("【测试步骤与预期】")
        for i, st in enumerate(steps, 1):
            step = (st.get("step") or "").strip()
            expect = (st.get("expect") or "").strip()
            if not step and not expect:
                continue
            line = f"{i}. {step or '（无步骤描述）'}"
            if expect:
                line += f" → 预期：{expect}"
            parts.append(line)
    text = "\n".join(parts).strip()
    if not text:
        text = title or "功能测试用例"
    return text[:DESCRIPTION_MAX_LEN]


def priority_to_level(priority: str) -> str:
    mapping = {"1": "P0", "2": "P1", "3": "P2", "4": "P3"}
    return mapping.get(str(priority or "2").strip(), "P2")


def truncate_case_name(title: str, max_len: int = 50) -> str:
    t = (title or "UI用例").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _get_ui_extra(fc: AiFunctionalCase) -> dict[str, Any]:
    extra = fc.extra if isinstance(fc.extra, dict) else {}
    ui = extra.get("ui_import")
    return ui if isinstance(ui, dict) else {}


async def _resolve_ai_config(
    ai_config_id: Optional[int],
    generation_mode: str = "single",
) -> AiConfig:
    from app.modules.ai.ai_scene_config import resolve_config_for_scene

    scene = "ui_case_agent" if generation_mode == "agent" else "ui_case_generate"
    return await resolve_config_for_scene(scene, ai_config_id)


async def _generate_ui_steps(
    *,
    description: str,
    page_url: Optional[str],
    ai_config_id: Optional[int],
    generation_mode: str,
    max_rounds: int,
    max_steps: int,
    project_id: int,
    user_info: dict,
) -> dict[str, Any]:
    from app.routers.ai.generate import (
        GenerateUiCaseAgentRequest,
        GenerateUiCaseRequest,
        UI_AGENT_DEFAULT_STEPS,
        _generate_ui_case_agent,
        _generate_ui_case_explore,
        _generate_ui_case_single,
    )

    config = await _resolve_ai_config(ai_config_id, generation_mode)
    body = GenerateUiCaseRequest(
        description=description,
        page_url=page_url,
        ai_config_id=config.id,
        auto_explore=generation_mode == "explore",
        max_rounds=max_rounds,
    )
    start_time = time.time()
    try:
        if generation_mode == "agent":
            if not (page_url or "").strip():
                raise HTTPException(status_code=400, detail="Agent 模式需填写目标页面 URL")
            agent_body = GenerateUiCaseAgentRequest(
                description=description,
                page_url=page_url.strip(),
                ai_config_id=config.id,
                max_steps=max_steps or UI_AGENT_DEFAULT_STEPS,
            )
            return await _generate_ui_case_agent(
                agent_body, config, project_id, user_info, start_time
            )
        if generation_mode == "explore" and body.page_url:
            resp = await _generate_ui_case_explore(body, config, project_id, user_info, start_time)
        else:
            resp = await _generate_ui_case_single(body, config, project_id, user_info, start_time)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[functional_case_to_ui] generate failed")
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {e}") from e

    data = resp.data if resp and resp.data else {}
    return data or {}


async def _set_ui_import_status(
    fc: AiFunctionalCase,
    status: str,
    *,
    ctx: Optional[UiGenerationContext] = None,
    page_url: Optional[str] = None,
    ai_config_id: Optional[int] = None,
    steps: Optional[list] = None,
    errors: Optional[list] = None,
    record_id: Optional[int] = None,
    ui_case_id: Optional[int] = None,
    error: Optional[str] = None,
    login_prefix_count: int = 0,
) -> None:
    extra = dict(fc.extra) if isinstance(fc.extra, dict) else {}
    ui = dict(_get_ui_extra(fc))
    ui["status"] = status
    ui["updated_at"] = _utc_now_iso()
    if ctx:
        if ctx.page_url is not None:
            ui["page_url"] = ctx.page_url
        if ctx.ai_config_id is not None:
            ui["ai_config_id"] = ctx.ai_config_id
        ui["login_strategy"] = ctx.login_strategy
        ui["login_ui_case_id"] = ctx.login_ui_case_id
        ui["source_method"] = ctx.source_method
        if ctx.test_username:
            ui["test_username"] = ctx.test_username
        if ctx.extra_context:
            ui["extra_context"] = ctx.extra_context
    if page_url is not None:
        ui["page_url"] = page_url
    if ai_config_id is not None:
        ui["ai_config_id"] = ai_config_id
    if steps is not None:
        ui["preview_steps_count"] = len(steps)
    if login_prefix_count:
        ui["login_prefix_steps_count"] = login_prefix_count
    if errors is not None:
        ui["preview_errors"] = errors[:10]
    if record_id is not None:
        ui["generate_record_id"] = record_id
    if ui_case_id is not None:
        ui["ui_case_id"] = ui_case_id
    if error is not None:
        ui["error"] = error
    elif status in ("generated", "imported"):
        ui.pop("error", None)
    extra["ui_import"] = ui
    fc.extra = extra
    await fc.save(update_fields=["extra"])


async def preview_functional_cases_to_ui(
    *,
    project_id: int,
    case_ids: list[int],
    ctx: UiGenerationContext,
    generation_mode: str,
    max_rounds: int,
    max_steps: int,
    user_info: dict,
) -> dict[str, Any]:
    validate_ui_generation_context(ctx)
    if not case_ids:
        raise HTTPException(status_code=400, detail="请至少选择一条功能用例")
    if len(case_ids) > MAX_UI_PREVIEW_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多预览 {MAX_UI_PREVIEW_BATCH} 条，请分批操作",
        )
    mode = (generation_mode or "single").strip().lower()
    if mode not in ("single", "explore", "agent"):
        raise HTTPException(status_code=400, detail="generation_mode 须为 single / explore / agent")
    if mode in ("explore", "agent") and not (ctx.page_url or "").strip():
        raise HTTPException(status_code=400, detail=f"{mode} 模式需填写目标页面 URL")

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
        description = build_full_ui_description(fc, ctx)
        item: dict[str, Any] = {
            "functional_case_id": fc.id,
            "title": fc.title,
            "description": description,
            "suggested_case_name": truncate_case_name(fc.title),
            "suggested_level": priority_to_level(fc.priority),
            "status": "pending",
            "steps": [],
            "errors": [],
            "tokens_used": 0,
            "record_id": None,
            "explore_info": None,
            "agent_info": None,
            "login_prefix_count": 0,
            "error": "",
        }
        await _set_ui_import_status(fc, "generating", ctx=ctx)
        try:
            data = await _generate_ui_steps(
                description=description,
                page_url=ctx.page_url,
                ai_config_id=ctx.ai_config_id,
                generation_mode=mode,
                max_rounds=max_rounds,
                max_steps=max_steps,
                project_id=project_id,
                user_info=user_info,
            )
            steps = data.get("steps") or []
            errors = data.get("errors") or []
            tokens = int(data.get("tokens_used") or 0)
            record_id = data.get("record_id")
            total_tokens += tokens
            if not steps:
                item["status"] = "failed"
                item["error"] = "AI 未返回有效步骤"
                await _set_ui_import_status(
                    fc, "failed", ctx=ctx, errors=errors, error=item["error"]
                )
            else:
                final_steps, prefix_n = await finalize_ui_steps(project_id, steps, ctx)
                item["status"] = "success"
                item["steps"] = final_steps
                item["errors"] = errors
                item["tokens_used"] = tokens
                item["record_id"] = record_id
                item["explore_info"] = data.get("explore_info")
                item["agent_info"] = data.get("agent_info")
                item["login_prefix_count"] = prefix_n
                await _set_ui_import_status(
                    fc,
                    "generated",
                    ctx=ctx,
                    steps=final_steps,
                    errors=errors,
                    record_id=record_id,
                    login_prefix_count=prefix_n,
                )
        except HTTPException as e:
            item["status"] = "failed"
            item["error"] = str(e.detail)
            await _set_ui_import_status(fc, "failed", ctx=ctx, error=item["error"])
        except Exception as e:
            logger.exception("[functional_case_to_ui] preview item %s failed", fc.id)
            item["status"] = "failed"
            item["error"] = str(e)
            await _set_ui_import_status(fc, "failed", ctx=ctx, error=item["error"])
        items.append(item)

    success_count = sum(1 for i in items if i["status"] == "success")
    return {
        "items": items,
        "success_count": success_count,
        "failed_count": len(items) - success_count,
        "total_tokens": total_tokens,
    }


async def import_functional_cases_to_ui(
    *,
    project_id: int,
    username: str,
    ctx: UiGenerationContext,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_ui_generation_context(ctx)
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
        case_description = (raw.get("case_description") or "").strip()
        if not case_description:
            case_description = build_case_description_from_functional(fc, ctx)

        try:
            final_steps, prefix_n = await finalize_ui_steps(project_id, steps, ctx)
            ui_case = await Case.create(
                name=case_name[:50],
                project_id=project_id,
                steps=final_steps,
                level=level,
                source_functional_case_id=fc.id,
                source_functional_case_title=(fc.title or "")[:500],
                description=case_description or None,
                username=username,
                update_by=username,
                is_del=False,
            )
            await _set_ui_import_status(
                fc,
                "imported",
                ctx=ctx,
                steps=final_steps,
                ui_case_id=ui_case.id,
                record_id=raw.get("record_id"),
                login_prefix_count=prefix_n,
            )
            imported.append(
                {
                    "functional_case_id": fc.id,
                    "ui_case_id": ui_case.id,
                    "case_name": ui_case.name,
                    "login_prefix_count": prefix_n,
                }
            )
        except HTTPException as e:
            await _set_ui_import_status(fc, "failed", ctx=ctx, error=str(e.detail))
            failed.append({"functional_case_id": fc_id, "error": str(e.detail)})
        except Exception as e:
            logger.exception("[functional_case_to_ui] import failed fc=%s", fc_id)
            await _set_ui_import_status(fc, "failed", ctx=ctx, error=str(e))
            failed.append({"functional_case_id": fc_id, "error": str(e)})

    return {
        "imported_count": len(imported),
        "failed_count": len(failed),
        "imported": imported,
        "failed": failed,
    }
