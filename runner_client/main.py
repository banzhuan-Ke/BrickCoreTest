from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from runner_client import __version__
from runner_client.app.api_client import ApiError, BrickCoreApi, compare_version
from runner_client.app.engine_manager import EngineManager
from runner_client.app.health import probe_connect_bundle
from runner_client.app.preferences import load_preferences
from runner_client.app.runtime_check import (
    diagnose_runner_runtime,
    is_packaged_app,
    repair_playwright_browsers,
)
from runner_client.app.secure_store import decrypt_text, encrypt_text
from runner_client.app.server_dialog import ServerManageDialog
from runner_client.app.settings_dialog import SettingsDialog
from runner_client.app.store import (
    clear_session_password,
    load_servers,
    load_session,
    save_servers,
    save_session,
)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _clean_log_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    return cleaned.replace("\x00", "")


def _status_dot(ok: bool | None) -> str:
    if ok is True:
        return "🟢"
    if ok is False:
        return "🔴"
    return "⚪"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BrickCore Runner 客户端")
        self.resize(780, 680)

        self.engine = EngineManager()
        self.api: BrickCoreApi | None = None
        self.connect_data: dict | None = None
        self.servers = load_servers()
        self.prefs = load_preferences()
        self._version_info: dict | None = None
        self._quitting = False
        self._health_poll_ms = 10_000
        self._last_api_health_ts = 0.0
        self._last_api_health_ok: bool | None = None

        self._build_ui()
        self._setup_tray()
        self._load_defaults()

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1500)
        self.poll_timer.timeout.connect(self._poll_logs)

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(30000)
        self.heartbeat_timer.timeout.connect(self._send_heartbeat)

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(self._health_poll_ms)
        self.health_timer.timeout.connect(self._refresh_health)

        QTimer.singleShot(400, self._check_version_on_startup)
        if is_packaged_app():
            QTimer.singleShot(300, self._check_runner_runtime)

    def _check_runner_runtime(self) -> None:
        ok, message, fixable = diagnose_runner_runtime(self.engine.runner_dir)
        if ok:
            return
        if not fixable:
            QMessageBox.critical(self, "Runner 运行时", message)
            return
        answer = QMessageBox.question(
            self,
            "Runner 运行时",
            f"{message}\n\n是否现在下载安装 Chromium？（需联网，约 150MB）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        dialog = _RuntimeRepairDialog(self.engine.runner_dir, parent=self)
        dialog.exec()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        header = QHBoxLayout()
        title = QLabel("BrickCore Runner · 执行器客户端")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()
        self.version_label = QLabel(f"v{__version__}")
        header.addWidget(self.version_label)
        self.update_btn = QPushButton("检查更新")
        self.update_btn.clicked.connect(self._check_version_update)
        header.addWidget(self.update_btn)
        layout.addLayout(header)

        server_box = QGroupBox("服务器环境")
        server_form = QFormLayout(server_box)
        env_row = QHBoxLayout()
        self.server_combo = QComboBox()
        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        env_row.addWidget(self.server_combo, stretch=1)
        manage_btn = QPushButton("管理…")
        manage_btn.clicked.connect(self._manage_servers)
        env_row.addWidget(manage_btn)
        server_form.addRow("环境", env_row)

        self.server_url_edit = QLineEdit()
        self.server_url_edit.setPlaceholderText("http://localhost:8000")
        self.server_url_edit.editingFinished.connect(self._sync_url_to_current_server)
        server_form.addRow("地址", self.server_url_edit)
        layout.addWidget(server_box)

        login_box = QGroupBox("登录")
        login_form = QFormLayout(login_box)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        login_form.addRow("用户名", self.username_edit)
        login_form.addRow("密码", self.password_edit)
        layout.addWidget(login_box)

        device_box = QGroupBox("设备")
        device_form = QFormLayout(device_box)
        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("如：Windows本地 / Windows本地-线上")
        device_form.addRow("设备名称", self.device_name_edit)
        layout.addWidget(device_box)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("登录")
        self.connect_btn = QPushButton("上线")
        self.disconnect_btn = QPushButton("下线")
        self.settings_btn = QPushButton("设置…")
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.login_btn.clicked.connect(self._on_login)
        self.connect_btn.clicked.connect(self._on_connect)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.settings_btn.clicked.connect(self._open_settings)
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.settings_btn)
        layout.addLayout(btn_row)

        health_box = QGroupBox("连接状态")
        health_layout = QHBoxLayout(health_box)
        self.health_api = QLabel("平台 API ⚪")
        self.health_mq = QLabel("消息队列 ⚪")
        self.health_redis = QLabel("Redis ⚪")
        self.health_engine = QLabel("Runner 引擎 ⚪")
        for lbl in (self.health_api, self.health_mq, self.health_redis, self.health_engine):
            health_layout.addWidget(lbl)
        health_layout.addStretch()
        layout.addWidget(health_box)

        self.status_label = QLabel("状态：未连接")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        log_header = QHBoxLayout()
        log_title = QLabel("当前会话日志")
        log_title.setFont(QFont("", 10, QFont.Weight.Bold))
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.history_log_btn = QPushButton("历史日志…")
        self.history_log_btn.clicked.connect(self._open_log_history)
        log_header.addWidget(self.history_log_btn)
        layout.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("本次上线后的 Runner 日志将显示在这里…")
        layout.addWidget(self.log_view, stretch=1)

    def _setup_tray(self) -> None:
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("BrickCore Runner")

        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        self.tray_login_action = QAction("登录", self)
        self.tray_login_action.triggered.connect(self._on_login)
        menu.addAction(self.tray_login_action)
        self.tray_connect_action = QAction("上线", self)
        self.tray_connect_action.triggered.connect(self._on_connect)
        menu.addAction(self.tray_connect_action)
        self.tray_disconnect_action = QAction("下线", self)
        self.tray_disconnect_action.triggered.connect(self._on_disconnect)
        menu.addAction(self.tray_disconnect_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._sync_tray_actions()

    def _sync_tray_actions(self) -> None:
        logged_in = bool(self.api and self.api.user_token)
        online = bool(self.connect_data and self.engine.is_running)
        self.tray_connect_action.setEnabled(logged_in and not online)
        self.tray_disconnect_action.setEnabled(online)
        self.tray_login_action.setEnabled(not online)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._quitting = True
        if self.engine.is_running:
            self._on_disconnect()
        self.tray.hide()
        QApplication.quit()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.prefs = dialog.preferences()
            if not self.prefs.get("remember_password"):
                clear_session_password(self._current_server_url())

    def _manage_servers(self) -> None:
        dialog = ServerManageDialog(self.servers, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.servers = dialog.result_servers()
        current_url = self._current_server_url()
        self._reload_server_combo(select_url=current_url)

    def _reload_server_combo(self, select_url: str | None = None) -> None:
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        for item in self.servers:
            self.server_combo.addItem(item.get("label") or item.get("url", ""), item.get("url"))
        self.server_combo.blockSignals(False)
        if select_url:
            for i in range(self.server_combo.count()):
                if str(self.server_combo.itemData(i)).rstrip("/") == select_url.rstrip("/"):
                    self.server_combo.setCurrentIndex(i)
                    self._on_server_changed(i)
                    return
        if self.servers:
            local_idx = next((i for i, s in enumerate(self.servers) if s.get("id") == "local"), 0)
            self.server_combo.setCurrentIndex(local_idx)
            self._on_server_changed(local_idx)

    def _load_defaults(self) -> None:
        self._reload_server_combo()

    def _current_server_url(self) -> str:
        return self.server_url_edit.text().strip().rstrip("/")

    def _sync_url_to_current_server(self) -> None:
        url = self._current_server_url()
        idx = self.server_combo.currentIndex()
        if idx < 0 or not url:
            return
        label = self.server_combo.currentText()
        combo_url = str(self.server_combo.itemData(idx) or "")
        for item in self.servers:
            if item.get("label") == label or item.get("url") == combo_url:
                if item.get("url") != url:
                    item["url"] = url
                    save_servers(self.servers)
                    self.server_combo.setItemData(idx, url)
                break

    def _on_server_changed(self, _index: int) -> None:
        url = self.server_combo.currentData()
        if url:
            self.server_url_edit.setText(str(url))
        session = load_session(self._current_server_url())
        self.username_edit.setText(session.get("username", ""))
        self.device_name_edit.setText(
            session.get("device_name")
            or ("Windows本地" if "localhost" in self._current_server_url() else "Windows本地-线上")
        )
        self.password_edit.clear()
        if self.prefs.get("remember_password"):
            token = session.get("password_token", "")
            if token:
                self.password_edit.setText(decrypt_text(token))
        self._refresh_health()

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log_view.appendPlainText(_clean_log_text(text))

    def _open_log_history(self) -> None:
        dialog = _LogHistoryDialog(self.engine, parent=self)
        dialog.exec()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _refresh_health(self, *, force_api_probe: bool = False) -> None:
        base_url = self._current_server_url()
        api_ok: bool | None = None
        now = time.monotonic()
        should_probe_api = force_api_probe or (
            base_url and (now - self._last_api_health_ts) >= self._health_poll_ms / 1000.0
        )
        if should_probe_api and base_url:
            probe = BrickCoreApi(base_url)
            api_ok = probe.health_check()
            self._last_api_health_ts = now
        elif base_url and self._last_api_health_ok is not None:
            api_ok = self._last_api_health_ok
        if api_ok is not None:
            self._last_api_health_ok = api_ok
        self.health_api.setText(f"平台 API {_status_dot(api_ok)}")

        mq_ok = redis_ok = None
        if self.connect_data:
            probes = probe_connect_bundle(self.connect_data)
            mq_ok = probes["mq"]
            redis_ok = probes["redis"]
        self.health_mq.setText(f"消息队列 {_status_dot(mq_ok)}")
        self.health_redis.setText(f"Redis {_status_dot(redis_ok)}")

        if self.connect_data:
            engine_ok = self.engine.is_running
        else:
            engine_ok = None
        self.health_engine.setText(f"Runner 引擎 {_status_dot(engine_ok)}")

    def _check_version_on_startup(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            return
        api = BrickCoreApi(base_url)
        self._version_info = api.fetch_version_info()
        self._refresh_health()
        if not self._version_info:
            return
        latest = self._version_info.get("runner_client_version_latest") or ""
        minimum = self._version_info.get("runner_client_version_min") or ""
        if minimum and compare_version(__version__, minimum) < 0:
            self._show_version_dialog(
                f"当前客户端 {__version__} 低于平台要求 {minimum}，请尽快升级。",
                force=True,
            )
        elif latest and compare_version(__version__, latest) < 0:
            self._show_version_dialog(
                f"发现新版本 {latest}（当前 {__version__}），建议升级。",
                force=False,
            )

    def _check_version_update(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            QMessageBox.information(self, "检查更新", "请先填写服务器地址")
            return
        api = BrickCoreApi(base_url)
        info = api.fetch_version_info()
        if not info:
            QMessageBox.warning(self, "检查更新", "无法获取平台版本信息")
            return
        self._version_info = info
        latest = info.get("runner_client_version_latest") or ""
        if latest and compare_version(__version__, latest) < 0:
            self._show_version_dialog(f"发现新版本 {latest}（当前 {__version__}）", force=False)
        else:
            QMessageBox.information(self, "检查更新", f"当前已是最新版本（{__version__}）")

    def _show_version_dialog(self, message: str, force: bool = False) -> None:
        download = BrickCoreApi.resolve_download_url(self._current_server_url(), self._version_info)
        package_available = bool(self._version_info and self._version_info.get("package_available"))
        box = QMessageBox(self)
        box.setWindowTitle("客户端更新")
        box.setText(message)
        extra = []
        if package_available:
            extra.append("平台已提供安装包，可点击「下载安装包」（需已登录）。")
        if download:
            extra.append(f"静态地址：\n{download}")
        if extra:
            box.setInformativeText("\n".join(extra))
        dl_btn = None
        if package_available:
            dl_btn = box.addButton("下载安装包", QMessageBox.ButtonRole.ActionRole)
        open_btn = None
        if download:
            open_btn = box.addButton("在浏览器打开", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        if force:
            box.setIcon(QMessageBox.Icon.Warning)
        box.exec()
        clicked = box.clickedButton()
        if clicked == dl_btn:
            self._download_client_package()
        elif clicked == open_btn and download:
            QDesktopServices.openUrl(QUrl(download))

    def _download_client_package(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            QMessageBox.warning(self, "下载", "请先选择服务器地址")
            return
        api = self.api if self.api and self.api.base_url.rstrip("/") == base_url.rstrip("/") else BrickCoreApi(base_url)
        if not api.user_token:
            QMessageBox.warning(self, "下载", "请先使用平台账号登录后再下载安装包")
            return
        from runner_client.app.package_updater import default_download_path

        filename = (self._version_info or {}).get("package_filename") or "BrickCoreRunner.zip"
        dest = default_download_path(filename)
        try:
            path = api.download_client_package(dest)
        except Exception as exc:
            QMessageBox.critical(self, "下载失败", str(exc))
            return
        QMessageBox.information(
            self,
            "下载完成",
            f"已保存到：\n{path}\n\n请关闭本客户端后，解压 zip 覆盖原安装目录完成升级。",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _persist_session(self, username: str, device_name: str, password: str = "") -> None:
        base_url = self._current_server_url()
        payload: dict = {"username": username, "device_name": device_name}
        if self.prefs.get("remember_password") and password:
            payload["password_token"] = encrypt_text(password)
        elif not self.prefs.get("remember_password"):
            clear_session_password(base_url)
        save_session(base_url, payload)

    def _on_login(self) -> None:
        base_url = self._current_server_url()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not base_url or not username or not password:
            QMessageBox.warning(self, "提示", "请填写服务器地址、用户名和密码")
            return

        self.api = BrickCoreApi(base_url)
        if not self.api.health_check():
            QMessageBox.warning(self, "连接失败", f"无法访问服务器：{base_url}\n请确认 Backend 已启动。")
            self._refresh_health(force_api_probe=True)
            return

        try:
            self.api.login(username, password)
        except ApiError as exc:
            QMessageBox.critical(self, "登录失败", str(exc))
            return

        self._persist_session(username, self.device_name_edit.text().strip(), password)
        self.connect_btn.setEnabled(True)
        self._set_status(f"已登录 {base_url}（{username}），可点击「上线」启动 Runner。")
        self._append_log(f"[客户端] 登录成功：{username} @ {base_url}")
        self._refresh_health(force_api_probe=True)
        self._sync_tray_actions()

    def _on_connect(self) -> None:
        if not self.api or not self.api.user_token:
            QMessageBox.warning(self, "提示", "请先登录")
            return
        device_name = self.device_name_edit.text().strip() or "执行设备"
        base_url = self._current_server_url()
        self._persist_session(self.username_edit.text().strip(), device_name, self.password_edit.text())

        try:
            ok, message, fixable = diagnose_runner_runtime(self.engine.runner_dir)
            if not ok:
                if fixable:
                    answer = QMessageBox.question(
                        self,
                        "Runner 运行时",
                        f"{message}\n\n是否现在安装 Chromium？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        dialog = _RuntimeRepairDialog(self.engine.runner_dir, parent=self)
                        if dialog.exec() != QDialog.DialogCode.Accepted:
                            return
                    else:
                        return
                else:
                    QMessageBox.critical(self, "Runner 运行时", message)
                    return

            self.connect_data = self.api.connect_runner(device_name)
        except ApiError as exc:
            QMessageBox.critical(self, "上线失败", str(exc))
            return

        latest = self.connect_data.get("client_version_latest") or ""
        if latest and compare_version(__version__, latest) < 0:
            self._show_version_dialog(
                f"当前客户端 {__version__}，平台最新 {latest}。",
                force=False,
            )

        try:
            self.engine.start(self.connect_data, device_name)
        except Exception as exc:
            QMessageBox.critical(self, "启动引擎失败", str(exc))
            return

        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.login_btn.setEnabled(False)
        self.poll_timer.start()
        self.heartbeat_timer.start()
        device_id = self.connect_data.get("device_id", "")
        self.log_view.clear()
        self._set_status(f"已上线 · 设备 {device_name} ({device_id}) · {base_url}")
        self._append_log(f"[客户端] Runner 引擎已启动，device_id={device_id}")
        self.health_timer.start()
        self._refresh_health(force_api_probe=True)
        self._sync_tray_actions()
        self.tray.showMessage("BrickCore Runner", "已上线，等待平台派发任务", QSystemTrayIcon.MessageIcon.Information, 3000)

    def _on_disconnect(self) -> None:
        self.poll_timer.stop()
        self.heartbeat_timer.stop()
        self.health_timer.stop()
        device_id = (self.connect_data or {}).get("device_id", "")
        if self.api and device_id:
            try:
                self.api.disconnect_runner(device_id)
            except Exception:
                pass
        self.engine.stop()
        self.connect_data = None
        self.connect_btn.setEnabled(bool(self.api and self.api.user_token))
        self.disconnect_btn.setEnabled(False)
        self.login_btn.setEnabled(True)
        self._set_status("已下线")
        self._append_log("[客户端] Runner 已下线")
        self._refresh_health()
        self._sync_tray_actions()

    def _poll_logs(self) -> None:
        chunk = self.engine.read_new_log_lines()
        if chunk:
            self._append_log(chunk)
            return
        chunk = self.engine.read_new_output()
        if chunk:
            self._append_log(chunk)
        elif self.connect_data and not self.engine.is_running:
            self._append_log("[客户端] Runner 进程已退出")
            self._on_disconnect()

    def _send_heartbeat(self) -> None:
        if not self.api or not self.connect_data:
            return
        device_id = self.connect_data.get("device_id", "")
        try:
            self.api.heartbeat(device_id)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            if self.engine.is_running:
                self._on_disconnect()
            event.accept()
            return
        if self.prefs.get("close_hides_to_tray", True) and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "BrickCore Runner",
                "已最小化到系统托盘，双击图标可恢复窗口",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        if self.engine.is_running:
            self._on_disconnect()
        event.accept()


def _format_log_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


class _LogHistoryDialog(QDialog):
    def __init__(self, engine: EngineManager, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.setWindowTitle("Runner 历史日志")
        self.resize(720, 520)

        layout = QVBoxLayout(self)
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #606266;")
        layout.addWidget(self._info_label)

        self._content_view = QPlainTextEdit()
        self._content_view.setReadOnly(True)
        self._content_view.setPlaceholderText("暂无历史日志文件")
        layout.addWidget(self._content_view, stretch=1)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self._reload)
        self._delete_btn = QPushButton("删除历史日志")
        self._delete_btn.clicked.connect(self._delete_log)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._reload()

    def _reload(self) -> None:
        path = self._engine.log_path
        size = self._engine.log_file_size()
        running_hint = "（引擎运行中，删除已禁用）" if self._engine.is_running else ""
        self._info_label.setText(f"文件：{path}\n大小：{_format_log_size(size)}{running_hint}")
        self._delete_btn.setEnabled(not self._engine.is_running and size > 0)
        if size == 0:
            self._content_view.setPlainText("")
            return
        content, _ = self._engine.read_log_file_content()
        self._content_view.setPlainText(content)
        cursor = self._content_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._content_view.setTextCursor(cursor)

    def _delete_log(self) -> None:
        if self._engine.is_running:
            QMessageBox.warning(self, "无法删除", "请先下线 Runner，再删除历史日志文件。")
            return
        if self._engine.log_file_size() == 0:
            return
        answer = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除历史日志文件？\n{self._engine.log_path}\n\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._engine.clear_log_file()
            QMessageBox.information(self, "已删除", "历史日志文件已删除。")
            self._reload()
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))


class _InstallWorker(QThread):
    log_line = Signal(str)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(self, runner_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._runner_dir = runner_dir

    def run(self) -> None:
        try:
            repair_playwright_browsers(
                self._runner_dir,
                on_output=lambda text: self.log_line.emit(text),
            )
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _RuntimeRepairDialog(QDialog):
    def __init__(self, runner_dir, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("安装 Playwright Chromium")
        self.resize(560, 320)
        self._runner_dir = runner_dir
        self._worker: _InstallWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("正在安装浏览器，请稍候（约 150MB，需联网）…"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self._close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        self._close_btn.setEnabled(False)
        layout.addWidget(buttons)

        self._worker = _InstallWorker(runner_dir, self)
        self._worker.log_line.connect(self._append)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.start()

    def _append(self, text: str) -> None:
        if text:
            self.log_view.appendPlainText(text)

    def _on_ok(self) -> None:
        self._append("[完成] Chromium 已就绪")
        self._close_btn.setText("完成")
        self._close_btn.setEnabled(True)
        self.accept()

    def _on_err(self, message: str) -> None:
        self._append(f"[失败] {message}")
        self._close_btn.setText("关闭")
        self._close_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        event.accept()


def run_app() -> int:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
    app = QApplication(sys.argv)
    app.setApplicationName("BrickCore Runner")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
