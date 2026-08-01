from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from runner_client.app.preferences import (
    autostart_executable,
    load_preferences,
    save_preferences,
    set_windows_autostart,
)
from runner_client.app.runner_execution_config import (
    DEFAULT_CASE_ERROR_RETRIES,
    DEFAULT_VIEWPORT_HEIGHT,
    DEFAULT_VIEWPORT_WIDTH,
    MAX_CASE_ERROR_RETRIES,
    MIN_VIEWPORT_HEIGHT,
    MIN_VIEWPORT_WIDTH,
    PREF_UI_DEBUG_HOTKEYS,
    normalize_execution_prefs,
    save_execution_prefs,
)
from runner_client.app.runtime_check import is_packaged_app
from runner_client.app.ui_debug_hotkeys import (
    DEFAULT_HOTKEYS,
    HOTKEY_ACTION_LABELS,
    HOTKEY_ACTIONS,
    merge_hotkeys,
    normalize_hotkey_combo,
)


def _is_public_source_tree() -> bool:
    """公开仓库无 runner/WebEngine 与打包脚本。"""
    here = Path(__file__).resolve()
    for root in here.parents:
        if (root / "docs-site").is_dir():
            return not (root / "runner" / "WebEngine").is_dir()
    return False


def _settings_hint_text() -> str:
    if is_packaged_app():
        return (
            "说明：登录平台后点击「上线」即可连接执行器。\n"
            "安装包请从平台「系统管理 → 执行器发布」或网盘获取。"
        )
    if _is_public_source_tree():
        return (
            "说明：请从网盘或平台「执行器发布」下载 BrickCoreRunner.zip。\n"
            "本仓库仅含客户端 GUI 源码，引擎随安装包分发。"
        )
    return (
        "说明：安装包由 scripts\\build_runner_client.ps1 生成，\n"
        "输出 runner_client\\dist\\BrickCoreRunner\\，可复制到其他 Windows 电脑。"
    )


def _qt_event_to_combo(event) -> str:
    mods: list[str] = []
    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
        mods.append("Ctrl")
    if event.modifiers() & Qt.KeyboardModifier.AltModifier:
        mods.append("Alt")
    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
        mods.append("Shift")
    if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
        mods.append("Meta")
    key = event.key()
    if key in (
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    ):
        return ""
    name = QKeySequence(key).toString()
    if not name:
        return ""
    return normalize_hotkey_combo("+".join(mods + [name]))


class SettingsDialog(QDialog):
    def __init__(self, parent=None, *, runner_online: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("客户端设置")
        self.resize(520, 640)
        self._runner_online = runner_online
        self._prefs = load_preferences()
        exec_prefs = normalize_execution_prefs(self._prefs)
        self._hotkeys = merge_hotkeys(self._prefs.get(PREF_UI_DEBUG_HOTKEYS))
        self._listening_action: str | None = None
        self._hotkey_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)

        form = QFormLayout()
        self.remember_cb = QCheckBox("记住密码（本机加密保存）")
        self.remember_cb.setChecked(bool(self._prefs.get("remember_password", True)))
        form.addRow(self.remember_cb)

        self.tray_cb = QCheckBox("关闭窗口时最小化到系统托盘")
        self.tray_cb.setChecked(bool(self._prefs.get("close_hides_to_tray", True)))
        form.addRow(self.tray_cb)

        self.autostart_cb = QCheckBox("开机自动启动客户端")
        self.autostart_cb.setChecked(bool(self._prefs.get("autostart", False)))
        if not autostart_executable():
            self.autostart_cb.setEnabled(False)
            self.autostart_cb.setToolTip("需使用打包后的 BrickCoreRunner.exe")
        form.addRow(self.autostart_cb)
        layout.addLayout(form)

        exec_box = QGroupBox("Web 执行配置")
        exec_form = QFormLayout(exec_box)

        self.viewport_width_spin = QSpinBox()
        self.viewport_width_spin.setRange(MIN_VIEWPORT_WIDTH, 3840)
        self.viewport_width_spin.setSingleStep(10)
        self.viewport_width_spin.setValue(exec_prefs["runner_viewport_width"])
        self.viewport_width_spin.setSuffix(" px")
        exec_form.addRow("无头视口宽度", self.viewport_width_spin)

        self.viewport_height_spin = QSpinBox()
        self.viewport_height_spin.setRange(MIN_VIEWPORT_HEIGHT, 2160)
        self.viewport_height_spin.setSingleStep(10)
        self.viewport_height_spin.setValue(exec_prefs["runner_viewport_height"])
        self.viewport_height_spin.setSuffix(" px")
        exec_form.addRow("无头视口高度", self.viewport_height_spin)

        self.error_retries_spin = QSpinBox()
        self.error_retries_spin.setRange(0, MAX_CASE_ERROR_RETRIES)
        self.error_retries_spin.setValue(exec_prefs["runner_case_error_retries"])
        self.error_retries_spin.setToolTip(
            "用例因异常（error）失败时的额外重跑次数；断言失败（fail）不会重跑。"
        )
        exec_form.addRow("异常重跑次数", self.error_retries_spin)

        exec_hint = QLabel(
            "无头模式下截图/录屏分辨率与视口一致。异常重跑 0 表示关闭；"
            f"默认 {DEFAULT_CASE_ERROR_RETRIES} 表示最多跑 2 次。"
        )
        exec_hint.setWordWrap(True)
        exec_form.addRow(exec_hint)

        reset_btn = QPushButton("恢复 Web 执行默认")
        reset_btn.clicked.connect(self._reset_execution_defaults)
        exec_form.addRow(reset_btn)
        layout.addWidget(exec_box)

        hotkey_box = QGroupBox("交互调试快捷键")
        hotkey_form = QFormLayout(hotkey_box)
        hint = QLabel(
            "点击右侧按钮后按下组合键进行绑定；空表示未绑定。"
            "改完后需下线再上线，新会话才会带上执行器默认快捷键。"
            "平台调试页也可覆盖当前会话快捷键。"
        )
        hint.setWordWrap(True)
        hotkey_form.addRow(hint)
        for action in HOTKEY_ACTIONS:
            row = QHBoxLayout()
            btn = QPushButton(self._hotkeys.get(action) or "未绑定")
            btn.setMinimumWidth(160)
            btn.clicked.connect(lambda _=False, a=action: self._start_listen(a))
            clear_btn = QPushButton("清空")
            clear_btn.clicked.connect(lambda _=False, a=action: self._clear_hotkey(a))
            row.addWidget(btn)
            row.addWidget(clear_btn)
            self._hotkey_buttons[action] = btn
            hotkey_form.addRow(HOTKEY_ACTION_LABELS.get(action, action), row)
        reset_hk = QPushButton("恢复快捷键默认")
        reset_hk.clicked.connect(self._reset_hotkeys)
        hotkey_form.addRow(reset_hk)
        layout.addWidget(hotkey_box)

        layout.addWidget(QLabel(_settings_hint_text()))
        scroll.setWidget(body)
        root.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_hotkey_buttons(self) -> None:
        for action, btn in self._hotkey_buttons.items():
            if self._listening_action == action:
                btn.setText("请按下组合键…")
            else:
                btn.setText(self._hotkeys.get(action) or "未绑定")

    def _start_listen(self, action: str) -> None:
        self._listening_action = action
        self._refresh_hotkey_buttons()

    def _clear_hotkey(self, action: str) -> None:
        self._hotkeys[action] = ""
        if self._listening_action == action:
            self._listening_action = None
        self._refresh_hotkey_buttons()

    def _reset_hotkeys(self) -> None:
        self._hotkeys = dict(DEFAULT_HOTKEYS)
        self._listening_action = None
        self._refresh_hotkey_buttons()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._listening_action:
            combo = _qt_event_to_combo(event)
            if combo:
                for act, bound in list(self._hotkeys.items()):
                    if act != self._listening_action and bound == combo:
                        self._hotkeys[act] = ""
                self._hotkeys[self._listening_action] = combo
                self._listening_action = None
                self._refresh_hotkey_buttons()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._listening_action = None
                self._refresh_hotkey_buttons()
                event.accept()
                return
        super().keyPressEvent(event)

    def _reset_execution_defaults(self) -> None:
        self.viewport_width_spin.setValue(DEFAULT_VIEWPORT_WIDTH)
        self.viewport_height_spin.setValue(DEFAULT_VIEWPORT_HEIGHT)
        self.error_retries_spin.setValue(DEFAULT_CASE_ERROR_RETRIES)

    def _save(self) -> None:
        prefs: dict[str, Any] = dict(load_preferences())
        prefs.update(
            {
                "remember_password": self.remember_cb.isChecked(),
                "minimize_to_tray": True,
                "close_hides_to_tray": self.tray_cb.isChecked(),
                "autostart": self.autostart_cb.isChecked(),
                PREF_UI_DEBUG_HOTKEYS: merge_hotkeys(self._hotkeys),
            }
        )
        ok, err = set_windows_autostart(prefs["autostart"])
        if not ok and prefs["autostart"]:
            QMessageBox.warning(self, "开机自启", err)
            prefs["autostart"] = False
            self.autostart_cb.setChecked(False)

        exec_changed = (
            self.viewport_width_spin.value() != prefs.get("runner_viewport_width", DEFAULT_VIEWPORT_WIDTH)
            or self.viewport_height_spin.value() != prefs.get("runner_viewport_height", DEFAULT_VIEWPORT_HEIGHT)
            or self.error_retries_spin.value() != prefs.get("runner_case_error_retries", DEFAULT_CASE_ERROR_RETRIES)
            or merge_hotkeys(prefs.get(PREF_UI_DEBUG_HOTKEYS)) != merge_hotkeys(self._prefs.get(PREF_UI_DEBUG_HOTKEYS))
        )

        self._prefs = save_execution_prefs(
            self.viewport_width_spin.value(),
            self.viewport_height_spin.value(),
            self.error_retries_spin.value(),
            base_prefs=prefs,
        )

        if exec_changed and self._runner_online:
            QMessageBox.information(
                self,
                "Web 执行配置",
                "执行参数/快捷键已保存。请先「下线」再「上线」，新配置才会生效。",
            )
        self.accept()

    def preferences(self) -> dict[str, Any]:
        return dict(self._prefs)
