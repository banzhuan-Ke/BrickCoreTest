"""追溯矩阵 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import TEST_RELEASE_VIEW
from app.modules.test_management import traceability_service as svc
from app.schemas.test_management import StandardResponse

router = APIRouter(tags=["测试管理-追溯"])


@router.get(
    "/traceability/matrix",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def traceability_matrix(
    project_id: int = Query(...),
    release_id: Optional[int] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    size: int = Query(50, ge=1, le=500),
    keyword: Optional[str] = Query(None),
    trace_status: Optional[str] = Query(None),
    review_decision: Optional[str] = Query(None),
    all_rows: bool = Query(False, description="导出用：返回过滤后全部展平行"),
    nested: bool = Query(False, description="兼容：返回嵌套分组（不分页）"),
    user_info: dict = Depends(is_authenticated),
):
    if nested and not all_rows and page is None:
        data = await svc.build_traceability_matrix(project_id, release_id=release_id)
        return StandardResponse(data=data)
    data = await svc.build_traceability_matrix_page(
        project_id,
        release_id=release_id,
        page=page or 1,
        size=size,
        keyword=keyword,
        trace_status=trace_status,
        review_decision=review_decision,
        all_rows=all_rows,
    )
    return StandardResponse(data=data)


@router.get(
    "/traceability/coverage",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def traceability_coverage(
    project_id: int = Query(...),
    release_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.build_coverage_report(project_id, release_id=release_id)
    return StandardResponse(data=data)


@router.get(
    "/functional-cases/{case_id}/lifecycle",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def functional_case_lifecycle(
    case_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management import case_lifecycle_service as life

    data = await life.build_functional_case_lifecycle(project_id, case_id)
    return StandardResponse(data=data)
