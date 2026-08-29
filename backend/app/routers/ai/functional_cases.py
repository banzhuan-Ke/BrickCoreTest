"""
功能测试用例库
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from tortoise.expressions import Q, RawSQL

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.case.case_steps import align_steps_expects
from app.modules.ai.functional_case_duplicate import find_duplicate_groups
from app.modules.ai.functional_case_service import (
    copy_requirement_cases_to_library,
    functional_case_to_dict,
)
from app.modules.ai.functional_case_to_ui import (
    MAX_UI_PREVIEW_BATCH,
    UiGenerationContext,
    finalize_functional_case_agent_preview,
    import_functional_cases_to_ui,
    preview_functional_cases_to_ui,
    start_functional_case_agent_job,
    start_functional_case_explore_job,
)
from app.modules.ai.functional_case_to_app import (
    MAX_APP_PREVIEW_BATCH,
    AppGenerationContext,
    import_functional_cases_to_app,
    preview_functional_cases_to_app,
)
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW, APP_CASE_EDIT, UI_CASE_EDIT
from app.modules.ai.zentao_bindings import bindings_for_export, load_project_bindings
from app.modules.ai.zentao_case_export import ZENTAO_EXPORT_COLUMNS, build_xlsx_bytes, case_to_export_row
from app.modules.ai.zentao_case_import import parse_zentao_xlsx_to_cases
from app.models.ai import AiFunctionalCase, AiRequirement, AiRequirementCase
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/functional-cases", tags=["功能用例库"])

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_COPY_PER_REQUEST = 500
MAX_EXPORT_ROWS = 10000
ZENTAO_SORT_MEMORY_LIMIT = 5000

FUNCTIONAL_CASE_SORT_FIELDS = frozenset({"zentao_case_id", "create_time", "update_time"})


def _resolve_list_order(sort_by: Optional[str], sort_order: Optional[str]) -> tuple[str, ...]:
    """列表排序字段（白名单），返回 order_by 参数元组"""
    field = (sort_by or "").strip()
    if field not in FUNCTIONAL_CASE_SORT_FIELDS:
        return ("-id",)
    desc = (sort_order or "desc").strip().lower() != "asc"
    primary = f"-{field}" if desc else field
    return (primary, "-id")


def _sort_cases_by_zentao_id(cases: list, desc: bool) -> list:
    """禅道 ID 数值排序，无 ID 的始终排在最后"""
    def _num(c) -> int:
        zid = (getattr(c, "zentao_case_id", None) or "").strip()
        if zid.isdigit():
            return int(zid)
        return 0

    with_id = [c for c in cases if (getattr(c, "zentao_case_id", None) or "").strip()]
    without_id = [c for c in cases if not (getattr(c, "zentao_case_id", None) or "").strip()]
    with_id.sort(key=_num, reverse=desc)
    without_id.sort(key=lambda c: c.id or 0, reverse=True)
    return with_id + without_id


def _apply_list_order(q, sort_by: Optional[str], sort_order: Optional[str]):
    """应用列表排序（create_time / update_time / zentao_case_id 字符串序）"""
    field = (sort_by or "").strip()
    if field not in FUNCTIONAL_CASE_SORT_FIELDS:
        return q.order_by("-id")
    if field == "zentao_case_id":
        # Tortoise order_by 不支持 RawSQL；数值排序在 list 接口内单独处理
        return q.order_by("id")
    return q.order_by(*_resolve_list_order(sort_by, sort_order))


def _apply_zentao_id_presence_filter(q, has_zentao_case_id: Optional[str]):
    """筛选有/无禅道 ID"""
    flag = (has_zentao_case_id or "").strip().lower()
    if flag in ("1", "true", "yes", "has"):
        return q.filter(zentao_case_id__not_isnull=True).exclude(zentao_case_id="")
    if flag in ("0", "false", "no", "none"):
        return q.filter(Q(zentao_case_id__isnull=True) | Q(zentao_case_id=""))
    return q


def _apply_functional_case_filters(
    q,
    *,
    product: Optional[str] = None,
    module: Optional[str] = None,
    related_story: Optional[str] = None,
    priority: Optional[str] = None,
    source_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    keyword: Optional[str] = None,
    zentao_case_id: Optional[str] = None,
    has_zentao_case_id: Optional[str] = None,
    import_batch: Optional[str] = None,
):
    """与列表接口一致的筛选项"""
    if product:
        q = q.filter(product__icontains=product.strip())
    if module:
        q = q.filter(module__icontains=module.strip())
    if related_story:
        q = q.filter(related_story__icontains=related_story.strip())
    if priority:
        q = q.filter(priority=priority)
    if source_type:
        q = q.filter(source_type=source_type)
    if status_filter:
        q = q.filter(status=status_filter)
    if import_batch:
        q = q.filter(source_import_batch=import_batch)
    if keyword:
        q = q.filter(title__icontains=keyword)
    if zentao_case_id:
        q = q.filter(zentao_case_id__icontains=zentao_case_id.strip())
    return _apply_zentao_id_presence_filter(q, has_zentao_case_id)


async def _fetch_all_functional_cases(
    q,
    *,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> list:
    """按列表排序规则取全部匹配用例（导出用）"""
    sort_field = (sort_by or "").strip()
    desc = (sort_order or "desc").strip().lower() != "asc"
    if sort_field == "zentao_case_id":
        total = await q.count()
        if total > ZENTAO_SORT_MEMORY_LIMIT:
            order_fields = ("-_zentao_num", "-id") if desc else ("_zentao_num", "id")
            return (
                await q.annotate(_zentao_num=_zentao_id_numeric_sql())
                .order_by(*order_fields)
                .all()
            )
        all_cases = await q.all()
        return _sort_cases_by_zentao_id(all_cases, desc)
    return await _apply_list_order(q, sort_by, sort_order).all()


def _resolve_project_id(user_info: dict, project_id: Optional[int] = None) -> int:
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    if not pid:
        raise HTTPException(status_code=400, detail="请先在顶部导航栏选择项目")
    return int(pid)


class FunctionalCaseBody(BaseModel):
    product: str = ""
    module: str = ""
    related_story: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=500)
    zentao_case_id: Optional[str] = Field(default=None, max_length=64)
    precondition: Optional[str] = None
    steps: list = Field(default_factory=list)
    priority: str = "2"
    type: str = "功能测试"
    stage: str = "系统测试阶段"
    keywords: str = ""
    status: str = "confirmed"


def _apply_body_to_case(case: AiFunctionalCase, body: FunctionalCaseBody, username: str, *, is_create: bool) -> None:
    case.product = body.product
    case.module = body.module
    case.related_story = body.related_story
    case.title = body.title.strip()
    case.precondition = body.precondition
    case.steps = align_steps_expects(body.steps)
    case.priority = body.priority
    case.type = body.type
    case.stage = body.stage
    case.keywords = body.keywords
    case.status = body.status
    if body.zentao_case_id is not None:
        zid = (body.zentao_case_id or "").strip()
        case.zentao_case_id = zid or None
    if not is_create:
        case.update_by = username


class BatchDeleteBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class DuplicateCheckBody(BaseModel):
    module: Optional[str] = None
    source_type: Optional[str] = None
    import_batch: Optional[str] = None
    strict_mode: bool = False


class ImportToLibraryBody(BaseModel):
    case_ids: list[int] = Field(..., min_length=1)
    duplicate_title_mode: str = Field(default="skip")


class UiContextBody(BaseModel):
    page_url: Optional[str] = Field(default=None, max_length=500)
    ai_config_id: Optional[int] = None
    test_username: Optional[str] = Field(default=None, max_length=128)
    test_password: Optional[str] = Field(default=None, max_length=128)
    login_ui_case_id: Optional[int] = None
    login_strategy: str = Field(
        default="none",
        description="none/credentials/prepend_login/both",
    )
    extra_context: Optional[str] = Field(
        default=None,
        max_length=800,
        description="登录后导航、业务背景等细节补充（功能用例未写明的部分）",
    )
    source_method: str = Field(default="ai", description="ai 或 record")


class ToUiPreviewBody(UiContextBody):
    case_ids: list[int] = Field(..., min_length=1, max_length=MAX_UI_PREVIEW_BATCH)
    generation_mode: str = Field(
        default="single",
        description="single=单页面；explore=多轮探索；agent=Agent（MCP，请用 agent-job 接口）",
    )
    max_rounds: int = Field(default=3, ge=1, le=10)
    max_steps: int = Field(default=15, ge=3, le=30)
    device_id: Optional[str] = Field(default=None, max_length=100, description="Runner 设备 ID（有 page_url 时必填）")
    headless: bool = Field(default=True, description="无头模式（默认 true）")
    auto_explore: bool = Field(
        default=False,
        description="已废弃，请用 generation_mode=explore",
    )


class ToUiAgentJobBody(UiContextBody):
    functional_case_id: int = Field(..., ge=1)
    max_steps: int = Field(default=15, ge=3, le=30)
    run_mode: Optional[str] = Field(default=None, description="已忽略；固定 runner")
    device_id: Optional[str] = Field(default=None, max_length=100)
    headless: bool = Field(default=True, description="无头模式（默认 true）")


class ToUiAgentFinalizeBody(UiContextBody):
    job_id: int = Field(..., ge=1)
    functional_case_id: int = Field(..., ge=1)


class ToUiExploreJobBody(UiContextBody):
    functional_case_id: int = Field(..., ge=1)
    max_rounds: int = Field(default=3, ge=1, le=10)
    run_mode: Optional[str] = Field(default=None, description="已忽略；固定 runner")
    device_id: Optional[str] = Field(default=None, max_length=100)
    headless: bool = Field(default=True, description="无头模式（默认 true）")


class ImportUiCaseItem(BaseModel):
    functional_case_id: int
    steps: list = Field(default_factory=list)
    case_name: Optional[str] = Field(default=None, max_length=50)
    level: Optional[str] = Field(default=None, max_length=10)
    case_description: Optional[str] = Field(default=None, max_length=4000, description="Web 用例描述")
    record_id: Optional[int] = None
    login_prefix_count: int = Field(default=0, ge=0, le=50)


class ImportUiBody(UiContextBody):
    items: list[ImportUiCaseItem] = Field(..., min_length=1)


class AppContextBody(BaseModel):
    app_id: Optional[str] = Field(default=None, max_length=200, description="Android 包名或 launch_app 的 app_id")
    driver_mode: str = Field(
        default="hybrid",
        description="native|vision|hybrid|hybrid_web|mobile_chrome",
    )
    ai_config_id: Optional[int] = None
    test_username: Optional[str] = Field(default=None, max_length=128)
    test_password: Optional[str] = Field(default=None, max_length=128)
    login_app_case_id: Optional[int] = None
    login_strategy: str = Field(
        default="none",
        description="none/credentials/prepend_login/both",
    )
    extra_context: Optional[str] = Field(default=None, max_length=800)


class ToAppPreviewBody(AppContextBody):
    case_ids: list[int] = Field(..., min_length=1, max_length=MAX_APP_PREVIEW_BATCH)


class ImportAppCaseItem(BaseModel):
    functional_case_id: int
    steps: list = Field(default_factory=list)
    case_name: Optional[str] = Field(default=None, max_length=100)
    level: Optional[str] = Field(default=None, max_length=10)
    driver_mode: Optional[str] = Field(default=None, max_length=20)
    case_description: Optional[str] = Field(default=None, max_length=4000)
    record_id: Optional[int] = None


class ImportAppBody(AppContextBody):
    items: list[ImportAppCaseItem] = Field(..., min_length=1)


def _case_to_xlsx_row(case_dict: dict, defaults: dict) -> dict:
    """单条用例 → 导出行，多步骤合并到步骤/预期单元格（1.xxx\\n2.xxx）"""
    export_case = {
        **case_dict,
        "zentao_module": (case_dict.get("module") or "").strip(),
    }
    return case_to_export_row(export_case, defaults)


def _zentao_id_numeric_sql() -> RawSQL:
    """MySQL 数值排序表达式：纯数字 ID 转 UNSIGNED，否则 0"""
    return RawSQL(
        "CASE WHEN zentao_case_id REGEXP '^[0-9]+$' THEN CAST(zentao_case_id AS UNSIGNED) ELSE 0 END"
    )


async def _list_cases_by_zentao_id(q, *, desc: bool, page: int, size: int) -> tuple[list, int]:
    """禅道 ID 数值排序：小数据量内存排序，大数据量 SQL 分页"""
    total = await q.count()
    if total > ZENTAO_SORT_MEMORY_LIMIT:
        order_fields = ("-_zentao_num", "-id") if desc else ("_zentao_num", "id")
        cases = (
            await q.annotate(_zentao_num=_zentao_id_numeric_sql())
            .order_by(*order_fields)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return cases, total

    all_cases = await q.all()
    all_cases = _sort_cases_by_zentao_id(all_cases, desc)
    return all_cases[(page - 1) * size : page * size], total


async def _distinct_field_values(project_id: int, field: str, *, limit: int = 200) -> list[str]:
    """项目下某字段的去重非空值（按字母序）。"""
    rows = (
        await AiFunctionalCase.filter(project_id=project_id, is_del=False)
        .exclude(**{field: ""})
        .exclude(**{field: None})
        .order_by(field)
        .values_list(field, flat=True)
    )
    seen: set[str] = set()
    out: list[str] = []
    for val in rows:
        text = (val or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


@router.get(
    "/filter-options",
    summary="筛选项（所属产品、模块、关联需求）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_filter_options(
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    return StandardResponse(
        data={
            "products": await _distinct_field_values(pid, "product"),
            "modules": await _distinct_field_values(pid, "module"),
            "related_stories": await _distinct_field_values(pid, "related_story"),
        }
    )


@router.get("", summary="功能用例库列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_functional_cases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    product: Optional[str] = None,
    module: Optional[str] = None,
    related_story: Optional[str] = Query(None, description="关联需求（相关研发需求，模糊匹配）"),
    priority: Optional[str] = None,
    source_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = None,
    zentao_case_id: Optional[str] = Query(None, description="禅道用例ID（模糊匹配）"),
    has_zentao_case_id: Optional[str] = Query(
        None,
        description="禅道ID有无：1/has=仅有ID，0/none=仅无ID",
    ),
    import_batch: Optional[str] = None,
    ui_status: Optional[str] = None,
    sort_by: Optional[str] = Query(
        None,
        description="排序字段：zentao_case_id / create_time / update_time",
    ),
    sort_order: Optional[str] = Query("desc", description="asc 或 desc"),
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    q = AiFunctionalCase.filter(project_id=pid, is_del=False)
    q = _apply_functional_case_filters(
        q,
        product=product,
        module=module,
        related_story=related_story,
        priority=priority,
        source_type=source_type,
        status_filter=status_filter,
        keyword=keyword,
        zentao_case_id=zentao_case_id,
        has_zentao_case_id=has_zentao_case_id,
        import_batch=import_batch,
    )

    sort_field = (sort_by or "").strip()
    desc = (sort_order or "desc").strip().lower() != "asc"

    if sort_field == "zentao_case_id":
        cases, total = await _list_cases_by_zentao_id(q, desc=desc, page=page, size=size)
    else:
        total = await q.count()
        cases = await _apply_list_order(q, sort_by, sort_order).offset((page - 1) * size).limit(size).all()

    rows = [functional_case_to_dict(c) for c in cases]

    if ui_status:
        rows = [r for r in rows if r.get("ui_import_status") == ui_status]
        total = len(rows)

    return StandardResponse(data={"list": rows, "total": total, "page": page, "size": size})


@router.post("/duplicate-check", summary="重复检验", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def duplicate_check(
    body: DuplicateCheckBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    result = await find_duplicate_groups(
        pid,
        module=body.module,
        source_type=body.source_type,
        import_batch=body.import_batch,
        strict_mode=body.strict_mode,
    )
    return StandardResponse(data=result)


@router.get(
    "/import-batches",
    summary="导入批次列表",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_import_batches(
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    """返回项目下各 source_import_batch 及条数、文件名、最近导入时间"""
    pid = _resolve_project_id(user_info, project_id)
    rows = await AiFunctionalCase.filter(
        project_id=pid,
        is_del=False,
        source_import_batch__not_isnull=True,
    ).exclude(source_import_batch="").order_by("-id").values(
        "source_import_batch",
        "source_file_name",
        "create_time",
    )

    batch_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        batch = row["source_import_batch"]
        if batch not in batch_map:
            batch_map[batch] = {
                "import_batch": batch,
                "count": 0,
                "source_file_name": row.get("source_file_name") or "",
                "latest_create_time": row.get("create_time"),
            }
        batch_map[batch]["count"] += 1

    batches = sorted(
        batch_map.values(),
        key=lambda x: x.get("latest_create_time") or "",
        reverse=True,
    )
    return StandardResponse(data={"batches": batches, "total": len(batches)})


@router.delete(
    "/by-import-batch",
    summary="按导入批次回滚（逻辑删除）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def delete_by_import_batch(
    import_batch: str = Query(..., min_length=1, description="source_import_batch UUID"),
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    batch = import_batch.strip()
    updated = await AiFunctionalCase.filter(
        project_id=pid,
        source_import_batch=batch,
        is_del=False,
    ).update(is_del=True)
    if not updated:
        raise HTTPException(status_code=404, detail="未找到该批次的用例或已删除")
    return StandardResponse(
        data={"deleted_count": updated, "import_batch": batch},
        message=f"已回滚删除 {updated} 条",
    )


@router.post(
    "/to-ui/preview",
    summary="批量预览：功能用例 → UI 步骤",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def preview_to_ui(
    body: ToUiPreviewBody,
    request: Request,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

    pid = _resolve_project_id(user_info, project_id)
    user_info = {**user_info, "project_id": pid, "current_project_id": pid}
    ctx = UiGenerationContext.from_dict(body.model_dump())
    generation_mode = body.generation_mode
    if body.auto_explore and generation_mode == "single":
        generation_mode = "explore"
    data = await preview_functional_cases_to_ui(
        project_id=pid,
        case_ids=body.case_ids,
        ctx=ctx,
        generation_mode=generation_mode,
        max_rounds=body.max_rounds,
        max_steps=body.max_steps,
        user_info=user_info,
        device_id=body.device_id,
        request_base_url=request_base_url(request),
        headless=body.headless,
    )
    msg = f"预览完成：成功 {data['success_count']} 条"
    if data["failed_count"]:
        msg += f"，失败 {data['failed_count']} 条"
    return StandardResponse(data=data, message=msg)


@router.post(
    "/to-ui/agent-job",
    summary="功能用例单条 Agent 探索（异步 job）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def start_to_ui_agent_job(
    body: ToUiAgentJobBody,
    request: Request,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

    pid = _resolve_project_id(user_info, project_id)
    user_info = {**user_info, "project_id": pid, "current_project_id": pid}
    ctx = UiGenerationContext.from_dict({**body.model_dump(), "ai_config_id": body.ai_config_id})
    data = await start_functional_case_agent_job(
        project_id=pid,
        functional_case_id=body.functional_case_id,
        ctx=ctx,
        max_steps=body.max_steps,
        run_mode=body.run_mode,
        device_id=body.device_id,
        user_info=user_info,
        request_base_url=request_base_url(request),
        headless=body.headless,
    )
    return StandardResponse(data=data, message="Agent 任务已创建")


@router.post(
    "/to-ui/agent-finalize",
    summary="功能用例 Agent job 终态后生成预览行",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def finalize_to_ui_agent_job(
    body: ToUiAgentFinalizeBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    ctx = UiGenerationContext.from_dict(body.model_dump())
    item = await finalize_functional_case_agent_preview(
        project_id=pid,
        job_id=body.job_id,
        functional_case_id=body.functional_case_id,
        ctx=ctx,
    )
    return StandardResponse(data=item)


@router.post(
    "/to-ui/explore-job",
    summary="功能用例单条多轮探索（异步 job）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def start_to_ui_explore_job(
    body: ToUiExploreJobBody,
    request: Request,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

    pid = _resolve_project_id(user_info, project_id)
    user_info = {**user_info, "project_id": pid, "current_project_id": pid}
    ctx = UiGenerationContext.from_dict({**body.model_dump(), "ai_config_id": body.ai_config_id})
    data = await start_functional_case_explore_job(
        project_id=pid,
        functional_case_id=body.functional_case_id,
        ctx=ctx,
        max_rounds=body.max_rounds,
        run_mode=body.run_mode,
        device_id=body.device_id,
        user_info=user_info,
        request_base_url=request_base_url(request),
        headless=body.headless,
    )
    return StandardResponse(data=data, message="探索任务已创建")


@router.post(
    "/to-ui/explore-finalize",
    summary="功能用例探索 job 终态后生成预览行",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def finalize_to_ui_explore_job(
    body: ToUiAgentFinalizeBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    ctx = UiGenerationContext.from_dict(body.model_dump())
    item = await finalize_functional_case_agent_preview(
        project_id=pid,
        job_id=body.job_id,
        functional_case_id=body.functional_case_id,
        ctx=ctx,
    )
    return StandardResponse(data=item)


@router.post(
    "/import-ui",
    summary="导入 UI 自动化用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, UI_CASE_EDIT))],
)
async def import_to_ui(
    body: ImportUiBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or user_info.get("sub") or "system"
    ctx = UiGenerationContext.from_dict(body.model_dump())
    items = [it.model_dump() for it in body.items]
    data = await import_functional_cases_to_ui(
        project_id=pid,
        username=username,
        ctx=ctx,
        items=items,
    )
    msg = f"已导入 {data['imported_count']} 条 UI 用例"
    if data["failed_count"]:
        msg += f"，失败 {data['failed_count']} 条"
    return StandardResponse(data=data, message=msg)


@router.post(
    "/to-app/preview",
    summary="功能用例 → App 步骤预览",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def preview_to_app(
    body: ToAppPreviewBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    user_info = {**user_info, "project_id": pid, "current_project_id": pid}
    ctx = AppGenerationContext.from_dict(body.model_dump())
    data = await preview_functional_cases_to_app(
        project_id=pid,
        case_ids=body.case_ids,
        ctx=ctx,
        user_info=user_info,
    )
    msg = f"预览完成：成功 {data['success_count']} 条"
    if data["failed_count"]:
        msg += f"，失败 {data['failed_count']} 条"
    return StandardResponse(data=data, message=msg)


@router.post(
    "/import-app",
    summary="导入 App 自动化用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, APP_CASE_EDIT))],
)
async def import_to_app(
    body: ImportAppBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or user_info.get("sub") or "system"
    ctx = AppGenerationContext.from_dict(body.model_dump())
    items = [it.model_dump() for it in body.items]
    data = await import_functional_cases_to_app(
        project_id=pid,
        username=username,
        ctx=ctx,
        items=items,
    )
    msg = f"已导入 {data['imported_count']} 条 App 用例"
    if data["failed_count"]:
        msg += f"，失败 {data['failed_count']} 条"
    return StandardResponse(data=data, message=msg)


@router.get("/export/xlsx", summary="导出禅道 XLSX", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def export_xlsx(
    ids: Optional[str] = Query(None, description="逗号分隔的用例 ID；有值时仅导出勾选"),
    product: Optional[str] = None,
    module: Optional[str] = None,
    related_story: Optional[str] = Query(None, description="关联需求（模糊匹配）"),
    priority: Optional[str] = None,
    source_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = None,
    zentao_case_id: Optional[str] = Query(None, description="禅道用例ID（模糊匹配）"),
    has_zentao_case_id: Optional[str] = Query(
        None,
        description="禅道ID有无：1/has=仅有ID，0/none=仅无ID",
    ),
    import_batch: Optional[str] = None,
    sort_by: Optional[str] = Query(
        None,
        description="排序字段：zentao_case_id / create_time / update_time，默认与列表一致",
    ),
    sort_order: Optional[str] = Query("desc", description="asc 或 desc"),
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    q = AiFunctionalCase.filter(project_id=pid, is_del=False)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            q = q.filter(id__in=id_list)
        cases = await _fetch_all_functional_cases(q, sort_by=sort_by, sort_order=sort_order)
    else:
        q = _apply_functional_case_filters(
            q,
            product=product,
            module=module,
            related_story=related_story,
            priority=priority,
            source_type=source_type,
            status_filter=status_filter,
            keyword=keyword,
            zentao_case_id=zentao_case_id,
            has_zentao_case_id=has_zentao_case_id,
            import_batch=import_batch,
        )
        total = await q.count()
        if total > MAX_EXPORT_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"筛选结果共 {total} 条，超过单次导出上限 {MAX_EXPORT_ROWS} 条，请缩小筛选范围",
            )
        cases = await _fetch_all_functional_cases(q, sort_by=sort_by, sort_order=sort_order)

    if not cases:
        raise HTTPException(status_code=400, detail="没有可导出的用例")

    bindings = await load_project_bindings(pid)
    defaults = bindings_for_export(bindings)
    rows: list[dict] = []
    for case in cases:
        rows.append(_case_to_xlsx_row(functional_case_to_dict(case), defaults))

    xlsx_bytes = build_xlsx_bytes(rows, columns=ZENTAO_EXPORT_COLUMNS)
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="functional_cases_zentao.xlsx"'},
    )


@router.post("/import-zentao", summary="禅道 XLSX 导入", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def import_zentao_xlsx(
    file: UploadFile = File(...),
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 10MB 限制")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    bindings = await load_project_bindings(pid)
    defaults = bindings_for_export(bindings)

    try:
        case_dicts, failed_rows, warnings, batch = parse_zentao_xlsx_to_cases(content, defaults)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    imported_ids = []
    for cd in case_dicts:
        fc = await AiFunctionalCase.create(
            project_id=pid,
            product=cd["product"],
            module=cd["module"],
            related_story=cd.get("related_story"),
            title=cd["title"],
            zentao_case_id=cd.get("zentao_case_id"),
            precondition=cd.get("precondition"),
            steps=cd["steps"],
            priority=cd["priority"],
            type=cd["type"],
            stage=cd["stage"],
            keywords=cd.get("keywords", ""),
            status="confirmed",
            source_type="zentao_xlsx",
            source_import_batch=batch,
            source_file_name=file.filename,
            create_by=username,
        )
        imported_ids.append(fc.id)

    return StandardResponse(
        data={
            "import_batch": batch,
            "imported_count": len(imported_ids),
            "imported_ids": imported_ids,
            "failed_rows": failed_rows,
            "warnings": warnings,
        },
        message=f"成功导入 {len(imported_ids)} 条",
    )


@router.post("", summary="新建用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def create_functional_case(
    body: FunctionalCaseBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username", "")
    case = await AiFunctionalCase.create(
        project_id=pid,
        product=body.product,
        module=body.module,
        related_story=body.related_story,
        title=body.title.strip(),
        zentao_case_id=(body.zentao_case_id or "").strip() or None,
        precondition=body.precondition,
        steps=align_steps_expects(body.steps),
        priority=body.priority,
        type=body.type,
        stage=body.stage,
        keywords=body.keywords,
        status=body.status,
        source_type="manual",
        create_by=username,
        update_by=username,
    )
    return StandardResponse(data=functional_case_to_dict(case), message="创建成功")


@router.put("/{case_id}", summary="更新用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_functional_case(
    case_id: int,
    body: FunctionalCaseBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    case = await AiFunctionalCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    username = user_info.get("username", "")
    _apply_body_to_case(case, body, username, is_create=False)
    await case.save()
    return StandardResponse(data=functional_case_to_dict(case), message="更新成功")


@router.delete("", summary="批量删除", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_functional_cases(
    body: BatchDeleteBody,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    updated = await AiFunctionalCase.filter(
        project_id=pid, id__in=body.ids, is_del=False
    ).update(is_del=True)
    return StandardResponse(data={"deleted_count": updated}, message=f"已删除 {updated} 条")


@router.get(
    "/{case_id}/lifecycle",
    summary="功能用例生命周期聚合（需求/缺陷/计划运行）",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_functional_case_lifecycle(
    case_id: int,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management import case_lifecycle_service as life

    pid = _resolve_project_id(user_info, project_id)
    data = await life.build_functional_case_lifecycle(pid, case_id)
    return StandardResponse(data=data)


@router.get("/{case_id}", summary="用例详情", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_functional_case(
    case_id: int,
    project_id: Optional[int] = None,
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    case = await AiFunctionalCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    return StandardResponse(data=functional_case_to_dict(case))


# 需求工作区复制入库（路径挂在 requirements 下，此处提供实现函数供 requirements 调用）

async def import_requirement_cases_to_library_handler(
    req_id: int,
    case_ids: list[int],
    project_id: int,
    username: str,
    *,
    duplicate_title_mode: str = "skip",
) -> dict[str, Any]:
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    from app.modules.test_management.requirement_review_service import assert_requirement_design_allowed

    await assert_requirement_design_allowed(req)
    if len(case_ids) > MAX_COPY_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"单次最多复制 {MAX_COPY_PER_REQUEST} 条")

    src_cases = await AiRequirementCase.filter(
        requirement_id=req_id,
        project_id=project_id,
        id__in=case_ids,
        is_del=False,
    ).order_by("id").all()
    if not src_cases:
        raise HTTPException(status_code=400, detail="未找到可复制的用例")

    if duplicate_title_mode not in ("skip", "overwrite"):
        raise HTTPException(status_code=400, detail="duplicate_title_mode 须为 skip 或 overwrite")

    library_ids, copied, skipped, overwritten = await copy_requirement_cases_to_library(
        project_id,
        src_cases,
        username,
        req_id,
        duplicate_title_mode=duplicate_title_mode,  # type: ignore[arg-type]
    )
    return {
        "copied_count": copied,
        "skipped_count": skipped,
        "overwritten_count": overwritten,
        "not_found_count": len(case_ids) - len(src_cases),
        "library_ids": library_ids,
    }
