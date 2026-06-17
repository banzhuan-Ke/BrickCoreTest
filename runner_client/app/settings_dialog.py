from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from runner_client.app.preferences import (
    autostart_executable,
    load_preferences,
    save_preferences,
    set_windows_autostart,
)
from runner_client.app.runtime_check import is_packaged_app


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


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("客户端设置")
        self.resize(420, 280)
        self._prefs = load_preferences()

        layout = QVBoxLayout(self)
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
        layout.addWidget(QLabel(_settings_hint_text()))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        prefs: dict[str, Any] = {
            "remember_password": self.remember_cb.isChecked(),
            "minimize_to_tray": True,
            "close_hides_to_tray": self.tray_cb.isChecked(),
            "autostart": self.autostart_cb.isChecked(),
        }
        ok, err = set_windows_autostart(prefs["autostart"])
        if not ok and prefs["autostart"]:
            QMessageBox.warning(self, "开机自启", err)
            prefs["autostart"] = False
            self.autostart_cb.setChecked(False)
        save_preferences(prefs)
        self._prefs = prefs
        self.accept()

    def preferences(self) -> dict[str, Any]:
        return self._prefs
