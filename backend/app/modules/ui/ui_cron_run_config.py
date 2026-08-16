"""Web 定时任务执行器配置（W-37）：解析 run_config 并与在线 Web 设备求交。"""
from __future__ import annotations

from typing import Any, Optional

from app.models.sys import Device


def _engine_types(device: Device) -> list[str]:
    types = device.runner_engine_types
    if isinstance(types, list) and types:
        return [str(t).strip().lower() for t in types if str(t).strip()]
    return ["web"]


def is_web_runner_device(device: Device) -> bool:
    return "web" in _engine_types(device)


def normalize_run_config(raw: Any) -> dict[str, Any]:
    """规范化前端/库中的 run_config；空则返回 {}。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    devices_in = raw.get("devices")
    devices: list[dict[str, Any]] = []
    if isinstance(devices_in, list):
        for item in devices_in:
            if not isinstance(item, dict):
                continue
            did = str(item.get("device_id") or "").strip()
            if not did:
                continue
            try:
                weight = int(item.get("weight") or 1)
            except (TypeError, ValueError):
                weight = 1
            try:
                concurrency = int(item.get("concurrency") or 1)
            except (TypeError, ValueError):
                concurrency = 1
            devices.append(
                {
                    "device_id": did,
                    "weight": max(1, min(100, weight)),
                    "concurrency": max(1, min(20, concurrency)),
                }
            )
    if devices:
        out["devices"] = devices

    preferred = str(raw.get("device_id") or "").strip()
    if preferred:
        out["device_id"] = preferred

    if "concurrency" in raw and raw.get("concurrency") is not None:
        try:
            out["concurrency"] = max(1, min(20, int(raw.get("concurrency"))))
        except (TypeError, ValueError):
            pass

    browser = str(raw.get("browser_type") or "").strip().lower()
    if browser in ("chromium", "firefox", "webkit"):
        out["browser_type"] = browser

    if "headless" in raw and raw.get("headless") is not None:
        out["headless"] = bool(raw.get("headless"))

    return out


async def list_online_web_devices() -> list[Device]:
    rows = await Device.filter(status="在线", is_del=False).all()
    return [d for d in rows if is_web_runner_device(d)]


async def resolve_cron_dispatch(
    *,
    parallel: bool,
    run_config: Optional[dict[str, Any]],
) -> tuple[Optional[str], list[dict[str, Any]], int, str, bool, Optional[str]]:
    """
    返回 (device_id, devices, concurrency, browser_type, headless, warning)。

    - 有配置：与在线 Web 机求交（宽松：仅在线子集）
    - 无配置：兼容旧行为——全部在线 Web 等权 / 第一台
    - 无可用设备：devices=[] 且 device_id=None，由调用方写失败记录
    """
    cfg = normalize_run_config(run_config)
    online = await list_online_web_devices()
    online_by_id = {d.id: d for d in online}
    browser_type = cfg.get("browser_type") or "chromium"
    headless = bool(cfg["headless"]) if "headless" in cfg else True
    default_concurrency = int(cfg.get("concurrency") or 1)
    warning: Optional[str] = None

    configured = cfg.get("devices") or []
    if configured:
        selected: list[dict[str, Any]] = []
        offline_names: list[str] = []
        for item in configured:
            did = item["device_id"]
            if did not in online_by_id:
                offline_names.append(did)
                continue
            selected.append(
                {
                    "device_id": did,
                    "weight": item["weight"],
                    "concurrency": item["concurrency"],
                }
            )
        if offline_names and selected:
            warning = (
                f"部分勾选执行器当前不在线，已用在线子集执行：离线 {len(offline_names)} 台"
            )
        if not selected:
            warning = (
                f"勾选执行器均不在线（{len(offline_names)} 台），本次未派发"
                if offline_names
                else "无可用在线 Web 执行器"
            )
            return None, [], default_concurrency, browser_type, headless, warning
        if parallel and len(selected) > 1:
            return None, selected, default_concurrency, browser_type, headless, warning
        # 串行或仅一台：优先首选机
        preferred = cfg.get("device_id")
        pick = next((s for s in selected if s["device_id"] == preferred), selected[0])
        return (
            pick["device_id"],
            [],
            int(pick.get("concurrency") or default_concurrency),
            browser_type,
            headless,
            warning,
        )

    # 旧任务无配置
    if not online:
        return None, [], default_concurrency, browser_type, headless, warning
    if parallel and len(online) > 1:
        devices = [{"device_id": d.id, "weight": 1, "concurrency": 1} for d in online]
        return None, devices, 1, browser_type, headless, warning
    preferred = cfg.get("device_id")
    if preferred and preferred in online_by_id:
        return preferred, [], default_concurrency, browser_type, headless, warning
    return online[0].id, [], default_concurrency, browser_type, headless, warning
