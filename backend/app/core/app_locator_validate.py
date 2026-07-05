"""App Locator DSL 校验（与 Runner locator.py 对齐）"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

APP_DRIVER_MODES = frozenset({"native", "vision", "hybrid", "hybrid_web", "mobile_chrome"})
H5_DRIVER_MODES = frozenset({"hybrid_web", "mobile_chrome"})
WEBVIEW_ONLY_BY = frozenset({"css", "id"})


def _parse_pair(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    if isinstance(value, dict) and "x" in value and "y" in value:
        return float(value["x"]), float(value["y"])
    if isinstance(value, str) and "," in value:
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if len(parts) >= 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                return None
    return None


def validate_image_locator(locator: dict) -> None:
    if not isinstance(locator, dict):
        raise HTTPException(status_code=422, detail="图像元素 locator 无效")
    if str(locator.get("by") or "").lower() != "image":
        raise HTTPException(status_code=422, detail="图像元素 locator.by 须为 image")
    if not str(locator.get("value") or "").strip():
        raise HTTPException(status_code=422, detail="图像模板路径不能为空")
    threshold = locator.get("threshold")
    if threshold is not None:
        try:
            tv = float(threshold)
            if not 0 < tv <= 1:
                raise HTTPException(status_code=422, detail="图像 threshold 须在 (0, 1] 之间")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="图像 threshold 无效") from exc
    resolution = locator.get("resolution")
    if resolution is not None and resolution != "":
        pair = _parse_pair(resolution)
        if not pair or int(pair[0]) <= 0 or int(pair[1]) <= 0:
            raise HTTPException(status_code=422, detail="resolution 须为 [宽, 高] 正整数")
    record_pos = locator.get("record_pos")
    if record_pos is not None and record_pos != "":
        pair = _parse_pair(record_pos)
        if not pair:
            raise HTTPException(status_code=422, detail="record_pos 须为 [x, y] 数值")


def _validate_h5_metadata(loc: dict) -> None:
    page_index = loc.get("page_index")
    if page_index is not None and page_index != "":
        try:
            idx = int(page_index)
            if idx < 0:
                raise HTTPException(status_code=422, detail="page_index 不能为负数")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="page_index 须为整数") from exc
    devtools_source = loc.get("devtools_source")
    if devtools_source is not None and str(devtools_source).strip():
        src = str(devtools_source).strip().lower()
        if src not in ("webview", "chrome"):
            raise HTTPException(status_code=422, detail="devtools_source 须为 webview 或 chrome")


def _is_webview_locator(loc: dict) -> bool:
    if not isinstance(loc, dict):
        return False
    if str(loc.get("context") or "").lower() == "webview":
        return True
    return str(loc.get("by") or "").lower() in WEBVIEW_ONLY_BY


def _is_image_locator(loc: dict) -> bool:
    return isinstance(loc, dict) and str(loc.get("by") or "").lower() == "image"


def _collect_locators_from_steps(steps: list) -> list[dict]:
    locators: list[dict] = []
    if not isinstance(steps, list):
        return locators
    for step in steps:
        if not isinstance(step, dict):
            continue
        params = step.get("params") or {}
        loc = params.get("locator")
        if isinstance(loc, dict):
            locators.append(loc)
        branches = step.get("branches") or params.get("branches") or []
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                cond = branch.get("condition") or {}
                cond_loc = cond.get("locator")
                if isinstance(cond_loc, dict):
                    locators.append(cond_loc)
                locators.extend(_collect_locators_from_steps(branch.get("steps") or []))
    return locators


def validate_case_steps_driver_mode(driver_mode: str | None, steps: list | None) -> str:
    """校验用例步骤与 driver_mode 一致性，返回规范化后的 driver_mode"""
    mode = validate_driver_mode(driver_mode)
    locators = _collect_locators_from_steps(steps or [])
    has_webview = any(_is_webview_locator(loc) for loc in locators)
    has_image = any(_is_image_locator(loc) for loc in locators)
    if has_webview and mode not in H5_DRIVER_MODES:
        raise HTTPException(
            status_code=422,
            detail="用例含 H5/WebView 定位，驱动模式须为 hybrid_web 或 mobile_chrome",
        )
    if has_image and mode == "native":
        raise HTTPException(
            status_code=422,
            detail="用例含图像模板定位，驱动模式不能为 native",
        )
    for loc in locators:
        if not _is_webview_locator(loc):
            continue
        src = str(loc.get("devtools_source") or "").strip().lower()
        if src == "chrome" and mode == "hybrid_web":
            raise HTTPException(
                status_code=422,
                detail="元素 H5 来源为 Chrome，驱动模式须为 mobile_chrome",
            )
        if src == "webview" and mode == "mobile_chrome":
            raise HTTPException(
                status_code=422,
                detail="元素 H5 来源为 App WebView，驱动模式须为 hybrid_web",
            )
    return mode


async def validate_case_steps_driver_mode_for_project(
    driver_mode: str | None,
    steps: list | None,
    project_id: int,
) -> str:
    """展开 locator_ref 后校验（含元素库图像/H5 元数据）。"""
    from app.core.app_locator_service import expand_locator_refs_in_steps

    expanded = await expand_locator_refs_in_steps(steps or [], project_id)
    return validate_case_steps_driver_mode(driver_mode, expanded)


def validate_element_payload(element_type: str, locator: dict) -> None:
    et = (element_type or "control").strip().lower()
    loc = locator if isinstance(locator, dict) else {}
    by_value = str(loc.get("by") or "").strip().lower()

    if et == "image":
        validate_image_locator(loc)
        return
    if et == "control" and by_value == "image":
        raise HTTPException(status_code=422, detail="控件类型元素不可使用 image 定位，请改类型为「图像模板」")
    if by_value in WEBVIEW_ONLY_BY or str(loc.get("context") or "").lower() == "webview":
        if not str(loc.get("value") or "").strip():
            raise HTTPException(status_code=422, detail="H5 定位值不能为空")
        _validate_h5_metadata(loc)
        return
    if by_value and by_value != "coordinates" and not str(loc.get("value") or "").strip():
        raise HTTPException(status_code=422, detail="定位值不能为空")


def validate_driver_mode(value: str | None) -> str:
    mode = (value or "hybrid").strip().lower()
    if mode not in APP_DRIVER_MODES:
        raise HTTPException(status_code=422, detail=f"不支持的 driver_mode: {mode}")
    return mode
