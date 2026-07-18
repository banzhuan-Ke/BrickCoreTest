"""Runner 桌面客户端 — Web 录制侧栏面板。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_ACTION_LABELS = {
    "click": "点击",
    "fill": "输入",
    "navigate": "导航",
    "wait": "等待",
    "dblclick": "双击",
    "select": "选择",
    "hover": "悬停",
    "drag_and_drop": "拖拽",
    "keydown": "按键",
    "scroll": "滚动",
    "contextmenu": "右键",
    "file": "上传",
    "save_variable": "存变量",
}


def action_type_label(action_type: str) -> str:
    return _ACTION_LABELS.get(action_type or "", action_type or "操作")


def format_action_detail(action: dict[str, Any]) -> str:
    action_type = action.get("action_type") or ""
    if action_type == "save_variable":
        return f"${action.get('value') or ''} ← {action.get('selector') or ''}"
    if action_type == "drag_and_drop":
        end = action.get("value") or (action.get("meta") or {}).get("end_selector") or ""
        if end:
            return f"{action.get('selector') or ''} → {end}"
    return (
        action.get("selector")
        or action.get("url")
        or action.get("value")
        or ""
    )


def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


class RecordingPanel(QGroupBox):
    """显示本机 Runner 进行中的 Web 录制（与平台弹窗数据同源）。"""

    pause_requested = Signal(int)
    resume_requested = Signal(int)
    stop_requested = Signal(int)
    save_variable_requested = Signal(int, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Web 录制", parent)
        self.setObjectName("recordingPanel")
        self._record_id: int | None = None
        self._paused = False
        self._recording_started_at: datetime | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.status_label = QLabel("未检测到进行中的录制")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("recordingStatus")
        layout.addWidget(self.status_label)

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("recordingStats")
        layout.addWidget(self.stats_label)

        preview_title = QLabel("实时操作预览")
        preview_title.setFont(QFont("", 9, QFont.Weight.Bold))
        layout.addWidget(preview_title)

        self.actions_list = QListWidget()
        self.actions_list.setObjectName("recordingActionsList")
        self.actions_list.setMinimumHeight(160)
        layout.addWidget(self.actions_list, stretch=1)

        save_row = QHBoxLayout()
        self.var_input = QLineEdit()
        self.var_input.setPlaceholderText("变量名 order_id")
        self.var_input.textChanged.connect(self._on_var_input_changed)
        save_row.addWidget(self.var_input, stretch=1)
        self.save_var_btn = QPushButton("存变量")
        self.save_var_btn.clicked.connect(self._on_save_variable)
        save_row.addWidget(self.save_var_btn)
        layout.addLayout(save_row)

        btn_row = QHBoxLayout()
        self.pause_btn = QPushButton("暂停")
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setObjectName("warningBtn")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("dangerBtn")
        self.pause_btn.clicked.connect(self._on_pause)
        self.resume_btn.clicked.connect(self._on_resume)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self.pause_btn)
        btn_row.addWidget(self.resume_btn)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed_label)

        self.clear_recording()

    def clear_recording(self) -> None:
        self._record_id = None
        self._paused = False
        self._recording_started_at = None
        self._elapsed_timer.stop()
        self.status_label.setText("未检测到进行中的录制\n请在平台用例编辑页发起「AI 录制步骤」")
        self.stats_label.setText("")
        self.actions_list.clear()
        self.var_input.clear()
        self._set_controls_enabled(False)

    def apply_snapshot(self, data: dict[str, Any] | None) -> None:
        if not data or data.get("status") != "recording":
            self.clear_recording()
            return

        record_id = int(data.get("record_id") or 0)
        if record_id <= 0:
            self.clear_recording()
            return

        if self._record_id != record_id:
            self._recording_started_at = _parse_iso_ts(data.get("create_time"))

        self._record_id = record_id
        self._paused = bool(data.get("paused"))
        url = str(data.get("url") or "").strip()
        if self._paused:
            self.status_label.setText(f"⏸ 录制已暂停\n{url}")
        else:
            self.status_label.setText(f"🔴 正在录制\n{url}")

        actions_count = int(data.get("actions_count") or 0)
        self._refresh_elapsed_label(actions_count=actions_count)

        if not self._elapsed_timer.isActive():
            self._elapsed_timer.start()

        self.actions_list.clear()
        for action in data.get("raw_actions") or []:
            if not isinstance(action, dict):
                continue
            label = action_type_label(str(action.get("action_type") or ""))
            detail = format_action_detail(action)
            item = QListWidgetItem(f"{label}  {detail}")
            item.setToolTip(detail)
            self.actions_list.addItem(item)
        self.actions_list.scrollToBottom()

        self._set_controls_enabled(True)
        self.pause_btn.setVisible(not self._paused)
        self.resume_btn.setVisible(self._paused)
        self.save_var_btn.setEnabled(not self._paused and bool(self.var_input.text().strip()))

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.pause_btn.setEnabled(enabled)
        self.resume_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.save_var_btn.setEnabled(enabled and not self._paused)
        self.var_input.setEnabled(enabled)

    def _refresh_elapsed_label(self, *, actions_count: int | None = None) -> None:
        if self._record_id is None:
            return
        count_text = ""
        if actions_count is not None:
            count_text = f"已记录 {actions_count} 个操作"
        elif self.stats_label.text():
            count_text = self.stats_label.text().split("，")[0]

        elapsed_sec = 0
        if self._recording_started_at:
            elapsed_sec = max(
                0,
                int((datetime.now(timezone.utc) - self._recording_started_at).total_seconds()),
            )
        mins, secs = divmod(elapsed_sec, 60)
        elapsed_text = f"{mins}:{secs:02d}" if elapsed_sec else "0:00"
        self.stats_label.setText(f"{count_text}，已录制 {elapsed_text}")

    def _on_var_input_changed(self, _text: str) -> None:
        if self._record_id is None:
            return
        self.save_var_btn.setEnabled(
            not self._paused and bool(self.var_input.text().strip())
        )

    def _on_pause(self) -> None:
        if self._record_id:
            self.pause_requested.emit(self._record_id)

    def _on_resume(self) -> None:
        if self._record_id:
            self.resume_requested.emit(self._record_id)

    def _on_stop(self) -> None:
        if self._record_id:
            self.stop_requested.emit(self._record_id)

    def _on_save_variable(self) -> None:
        if not self._record_id:
            return
        name = self.var_input.text().strip()
        if not name:
            return
        self.save_variable_requested.emit(self._record_id, name, "text")
