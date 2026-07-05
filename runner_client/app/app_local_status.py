"""Runner 本机 App 自动化状态（adb / u2 / 已连接 Android 设备）。"""
from __future__ import annotations

import shutil
from typing import Any

from runner_client.app.engine_capabilities import (
    build_capabilities_from_toolchain,
    probe_app_toolchain,
)


def _status_label(ok: bool | None) -> str:
    if ok is True:
        return "正常"
    if ok is False:
        return "未就绪"
    return "未知"


def build_app_local_panel_text(*, enable_app: bool = False, force_probe: bool = False) -> dict[str, Any]:
    """供 Runner GUI 展示的本机 App 状态摘要（单次 adb 探测，避免重复弹窗）。"""
    toolchain = probe_app_toolchain(force=force_probe)
    caps = build_capabilities_from_toolchain(toolchain, enable_web=False, enable_app=enable_app)
    adb_ok = toolchain["adb_ok"]
    u2_ok = toolchain["u2_ok"]
    app_ready = enable_app and "app" in (caps.get("runner_engine_types") or [])
    devices = toolchain.get("devices") or []
    online = [d for d in devices if d.get("state") == "device"]
    adb_path = shutil.which("adb") or ""

    if not enable_app:
        summary = "未勾选「App 自动化」，上线后不会接收 App 任务。可在此查看本机工具链状态。"
        connect_hint = ""
    elif not adb_ok:
        summary = "本机未检测到 adb，请安装 Android SDK platform-tools 并加入 PATH。"
        connect_hint = ""
    elif not u2_ok:
        summary = "runner/venv 缺少 uiautomator2，请在 runner 目录执行 pip install -r requirements.txt。"
        connect_hint = ""
    elif not online:
        summary = "adb 与 u2 已就绪，但未发现在线 Android 设备。"
        connect_hint = (
            "连接设备（任选其一）：\n"
            "· USB：数据线连接手机，开启「USB 调试」并在手机上点允许\n"
            "· WiFi（Android 11+）：设置 → 开发者选项 → 无线调试 →「使用配对码配对」；"
            "PC 执行 adb pair 配对IP:端口 配对码，再 adb connect 连接IP:端口\n"
            "· 公司 WiFi 若 ping 不通手机（AP 隔离），改用手机个人热点再配对\n"
            "· 模拟器：adb connect 127.0.0.1:端口（MuMu 等查看 adb 端口）"
        )
    else:
        summary = f"App 自动化已就绪，勾选启用后上线将上报 {len(online)} 台 Android 设备。"
        connect_hint = ""

    if not devices:
        devices_text = "adb devices：无设备（请连接手机或执行 adb devices 排查）"
    else:
        lines = ["adb devices："]
        for item in devices:
            serial = item.get("serial") or "?"
            state = item.get("state") or "unknown"
            marker = " ← 将上报" if enable_app and state == "device" and serial == caps.get("app_udid") else ""
            lines.append(f"  · {serial}\t{state}{marker}")
        devices_text = "\n".join(lines)

    report_udid = (caps.get("app_udid") or "").strip()
    if not enable_app:
        report_text = "未启用 App 能力；勾选上方「App 自动化」后再上线"
    elif app_ready and report_udid:
        conn = caps.get("app_connection") or "usb"
        report_text = f"上线后将上报：app_udid={report_udid}（{conn}）"
    elif app_ready:
        report_text = "上线后将启用 App 能力（未识别到默认 UDID）"
    else:
        report_text = "已勾选 App 自动化，但工具链未就绪；修复上述问题后点击「刷新检测」"

    return {
        "adb_ok": adb_ok,
        "u2_ok": u2_ok,
        "app_ready": app_ready if enable_app else None,
        "adb_path": adb_path,
        "summary": summary,
        "connect_hint": connect_hint,
        "devices_text": devices_text,
        "report_text": report_text,
        "caps": caps,
        "adb_label": _status_label(adb_ok if adb_path or not adb_ok else None),
        "u2_label": _status_label(u2_ok),
        "app_label": _status_label(app_ready if enable_app else None),
    }
