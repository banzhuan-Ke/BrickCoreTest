import json as _json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Form, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import Response
from app.models.sys import Project
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import UI_CASE_VIEW, UI_CASE_EDIT
from app.core.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.core.ui_execution_stale import cleanup_stale_ui_executions
from app.core.catalog_utils import apply_catalog_filter, resolve_catalog
from app.schemas.ui import CaseSchemas, AddCaseForm, UpdateCaseForm, UiCaseBatchExportRequest, UiCaseImportResult, UiCaseBatchUpdateCatalogRequest
from app.core.case_execution_hints import build_execution_hints_response, resolve_latest_failure_record
from app.models.ui import Case, UiCaseExecution

# 创建路由对象，并指定依赖项为is_authenticated的验证，确保用户已通过身份验证
router = APIRouter(prefix="/cases", dependencies=[Depends(is_authenticated)], tags=["测试用例"])

_UI_CASE_FAIL_STATUSES = frozenset({"fail", "failed"})


def _match_case_run_status(state: str, filter_status: str | None) -> bool:
    """用例最近运行状态筛选（Runner 落库为 failed，筛选项/模型为 fail）。"""
    if not filter_status:
        return True
    if state == filter_status:
        return True
    if filter_status in _UI_CASE_FAIL_STATUSES and state in _UI_CASE_FAIL_STATUSES:
        return True
    return False


# 创建测试用例的接口
@router.post("", summary="创建用例", status_code=status.HTTP_201_CREATED, response_model=CaseSchemas,
             dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def create_case(item: AddCaseForm):
    """创建测试用例的接口"""
    # 获取项目信息
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="创建用例失败，传入的项目不存在")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    cases = await Case.create(**item.model_dump(exclude_unset=True), is_del=False, update_by=item.username)
    return cases


# 更新测试用例的接口
@router.put("/{case_id}", summary="更新用例", response_model=CaseSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def update_case(
    case_id: int,
    item: UpdateCaseForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EDIT)),
):
    """更新用例信息的接口"""
    # 获取用例信息
    cases = await Case.get_or_none(id=case_id)
    if not cases:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用例不存在")
    await assert_user_project_member(user_info, cases.project_id)
    if item.catalog_id is not None:
        await resolve_catalog(cases.project_id, item.catalog_id)
    await cases.update_from_dict(item.model_dump(exclude_unset=True))
    cases.update_by = user_info.get("username") or cases.username
    await cases.save()
    return cases


# 删除测试用例的接口
@router.delete("/{case_id}", summary="删除用例", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def delete_case(
    case_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_EDIT)),
):
    """删除用例信息的接口"""
    cases = await Case.get_or_none(id=case_id)
    if not cases:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用例不存在")
    await assert_user_project_member(user_info, cases.project_id)
    # 删除用例
    cases.is_del = True
    await cases.save()


# 获取单个用例详情的接口
@router.get("/{case_id}", summary="用例详情", response_model=CaseSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_case_detail(
    case_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_VIEW)),
):
    """获取单个用例详情的接口"""
    cases = await Case.get_or_none(id=case_id, is_del=False)
    if not cases:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用例不存在")
    await assert_user_project_viewer(user_info, cases.project_id)
    return cases


@router.get(
    "/{case_id}/execution-hints",
    summary="用例最近失败执行提示（编辑页步骤高亮）",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(UI_CASE_VIEW))],
)
async def get_case_execution_hints(
    case_id: int,
    execution_id: int | None = None,
    user_info: dict = Depends(require_permissions(UI_CASE_VIEW)),
):
    """返回最近一次失败（或指定 execution_id）的步骤失败信息与日志摘要。"""
    case = await Case.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_viewer(user_info, case.project_id)

    if execution_id:
        record = await UiCaseExecution.get_or_none(id=execution_id, is_del=False)
        if not record or record.case_id != case_id:
            raise HTTPException(status_code=422, detail="执行记录不存在")
    else:
        record = await resolve_latest_failure_record(UiCaseExecution, case_id)

    if not record:
        return build_execution_hints_response(None)

    return build_execution_hints_response(record)


class CopyCaseRequest(BaseModel):
    target_project_id: Optional[int] = None
    target_catalog_id: Optional[int] = None
    new_name: Optional[str] = None


# 复制用例
@router.post("/{case_id}/copy", summary="复制用例", response_model=CaseSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def copy_case(
    case_id: int,
    body: CopyCaseRequest | None = None,
    user_info: dict = Depends(require_permissions(UI_CASE_EDIT)),
):
    """复制用例；可指定 target_project_id 跨项目复制。"""
    from app.core.cross_project_copy import copy_ui_case_to_project, ensure_target_project, resolve_target_catalog

    cases = await Case.get_or_none(id=case_id).prefetch_related("project")
    if not cases:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用例不存在")
    await assert_user_project_member(user_info, cases.project_id)

    req = body or CopyCaseRequest()
    target_project_id = req.target_project_id or cases.project_id
    if target_project_id != cases.project_id:
        await assert_user_project_member(user_info, target_project_id)
        await ensure_target_project(target_project_id)
    target_catalog_id = await resolve_target_catalog(target_project_id, req.target_catalog_id)

    username = user_info.get("username") or cases.username
    new_cases = await copy_ui_case_to_project(
        cases,
        target_project_id,
        target_catalog_id if target_project_id != cases.project_id else (req.target_catalog_id or cases.catalog_id),
        username,
        req.new_name,
    )
    return new_cases


# 批量删除用例
@router.post("/batch-delete", summary="批量删除用例", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def batch_delete_cases(
    data: dict,
    user_info: dict = Depends(require_permissions(UI_CASE_EDIT)),
):
    """批量删除用例"""
    case_ids = data.get("case_ids", [])
    deleted = 0
    for case_id in case_ids:
        case = await Case.get_or_none(id=case_id, is_del=False)
        if not case:
            continue
        await assert_user_project_member(user_info, case.project_id)
        case.is_del = True
        await case.save()
        deleted += 1
    return {"detail": "删除成功", "deleted": deleted}


@router.post("/batch-update-catalog", summary="批量修改用例目录", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def batch_update_case_catalog(
    item: UiCaseBatchUpdateCatalogRequest,
    user_info: dict = Depends(require_permissions(UI_CASE_EDIT)),
):
    """批量修改 UI 用例所属目录"""
    if not item.case_ids:
        raise HTTPException(status_code=400, detail="请选择要修改的用例")
    updated = 0
    for case_id in item.case_ids:
        case = await Case.get_or_none(id=case_id, is_del=False)
        if not case:
            continue
        if item.catalog_id is not None:
            await resolve_catalog(case.project_id, item.catalog_id)
        case.catalog_id = item.catalog_id
        case.update_by = user_info.get("username") or case.username
        await case.save()
        updated += 1
    return {"updated": updated}


@router.post("/export", summary="批量导出UI用例",
             dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def export_ui_cases(item: UiCaseBatchExportRequest):
    """批量导出 Web 自动化用例为 JSON 文件"""
    if not item.case_ids:
        raise HTTPException(status_code=400, detail="请选择要导出的用例")
    if len(item.case_ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多导出 500 条")
    cases = await Case.filter(id__in=item.case_ids, is_del=False).all()
    cases_data = [
        {"name": c.name, "level": c.level, "steps": c.steps, "description": c.description or ""}
        for c in cases
    ]
    payload = {
        "meta": {
            "version": "1.0",
            "type": "ui_cases",
            "export_time": datetime.now(timezone.utc).isoformat(),
            "count": len(cases_data),
        },
        "cases": cases_data,
    }
    json_str = _json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ui_cases_export.json"},
    )


@router.post("/import", summary="批量导入UI用例",
             response_model=UiCaseImportResult,
             dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def import_ui_cases(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    username: str = Form(default="admin"),
):
    """从 JSON 文件批量导入 Web 自动化用例"""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大，最大支持 10MB")
    try:
        data = _json.loads(content.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="文件格式错误，请上传有效的 JSON 文件")

    meta = data.get("meta", {})
    if meta.get("type") != "ui_cases":
        raise HTTPException(
            status_code=400,
            detail=f"文件类型不匹配，期望 ui_cases，实际为 {meta.get('type')}"
        )

    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    existing_raw = await Case.filter(project_id=project_id, is_del=False).values_list("name", flat=True)
    existing_names = set(existing_raw)

    def resolve_name(base: str) -> str:
        candidate = base + "_导入"
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
        i = 2
        while True:
            candidate = f"{base}_导入{i}"
            if candidate not in existing_names:
                existing_names.add(candidate)
                return candidate
            i += 1

    success, failed = 0, 0
    errors_list, created_names = [], []

    for idx, c in enumerate(data.get("cases", [])):
        try:
            new_name = resolve_name(c.get("name", f"导入用例{idx + 1}"))
            await Case.create(
                name=new_name,
                project_id=project_id,
                steps=c.get("steps") or [],
                level=c.get("level") or "P2",
                description=(c.get("description") or "").strip() or None,
                username=username,
                update_by=username,
                is_del=False,
            )
            created_names.append(new_name)
            success += 1
        except Exception as e:
            errors_list.append(f"第 {idx + 1} 条用例处理失败：{str(e)}")
            failed += 1

    return UiCaseImportResult(
        success=success,
        failed=failed,
        errors=errors_list,
        created_names=created_names,
    )


# 查询测试用例列表
@router.get("", summary="用例列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_case(project_id: int, page: int = 1, size: int = 10,
                   name: str | None = None, status: str | None = None, level: str | None = None,
                   catalog_id: int | None = None, include_children: bool = True):
    """查询测试用例列表的接口"""
    await cleanup_stale_ui_executions()
    query = Case.filter(project_id=project_id, is_del=False)
    if name:
        query = query.filter(name__icontains=name)
    if level:
        query = query.filter(level=level)
    if catalog_id is not None:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)
    query = query.order_by("-create_time")
    all_cases = await query.all()
    # 查询用例的执行记录次数，并按 status 过滤
    result = []
    for i in all_cases:
        run_count = await UiCaseExecution.filter(case=i).count()
        # 获取最近一次执行状态
        run_record = await UiCaseExecution.filter(case=i).order_by("-id").first()
        state = run_record.status if run_record else 'no_run'
        if not _match_case_run_status(state, status):
            continue
        result.append({
            "id": i.id,
            "name": i.name,
            "username": i.username,
            "update_by": i.update_by or i.username,
            "status": state,
            "run_count": run_count,
            "steps_count": len(i.steps),
            "level": i.level,
            "source_functional_case_id": getattr(i, "source_functional_case_id", None),
            "source_functional_case_title": getattr(i, "source_functional_case_title", None) or "",
            "catalog_id": i.catalog_id,
            "create_time": i.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": i.update_time.strftime("%Y-%m-%d %H:%M:%S")
        })
    total = len(result)
    data = result[(page - 1) * size: page * size]
    return {"total": total, "data": data}
