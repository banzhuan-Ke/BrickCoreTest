from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont, QIcon, QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QScrollArea,
    QSplitter,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner_client import __version__
from runner_client.app.api_client import ApiError, BrickCoreApi, compare_version
from runner_client.app.app_local_status import build_app_local_panel_text
from runner_client.app.brick_animation import StartupSplash
from runner_client.app.recording_panel import RecordingPanel
from runner_client.app.engine_manager import EngineManager
from runner_client.app.agent_task_tracker import ActiveAgentTask, apply_log_line
from runner_client.app.local_runner_control import request_stop_active_agent
from runner_client.app.health import probe_connect_bundle
from runner_client.app.perf_worker_manager import PerfWorkerManager
from runner_client.app.preferences import load_preferences
from runner_client.app.runtime_check import (
    RepairKind,
    diagnose_app_runtime,
    diagnose_perf_runtime,
    diagnose_runner_runtime,
    is_packaged_app,
    repair_playwright_browsers,
    repair_runner_dependencies,
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
from runner_client.app.styles import APP_STYLESHEET

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

EXEC_ROLE_UI = "ui"
EXEC_ROLE_PERF = "perf"
EXEC_ROLE_BOTH = "both"


def _clean_log_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    return cleaned.replace("\x00", "")


def _status_dot(ok: bool | None) -> str:
    if ok is True:
        return "●"
    if ok is False:
        return "●"
    return "○"


def _health_state(ok: bool | None) -> str:
    if ok is True:
        return "ok"
    if ok is False:
        return "bad"
    return "idle"


def _resolve_app_icon_path() -> Path | None:
    """解析小搬砖图标：开发态 / 打包态 / 引擎目录多路径回退。"""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "icon.ico",
        here.parent / "runner" / "icon.ico",
        Path(sys.executable).resolve().parent / "icon.ico",
        Path(sys.executable).resolve().parent / "runner" / "icon.ico",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "icon.ico")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_app_icon() -> QIcon | None:
    path = _resolve_app_icon_path()
    if not path:
        return None
    icon = QIcon(str(path))
    return icon if not icon.isNull() else None


class _ApiHealthWorker(QThread):
    result_ready = Signal(bool)

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        self.result_ready.emit(BrickCoreApi(self._base_url).health_check())


class _VersionInfoWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        self.result_ready.emit(BrickCoreApi(self._base_url).fetch_version_info())


class _LayeredUpdateWorker(QThread):
    """后台下载/解密增量，避免主线程卡死显示「未响应」。"""

    progress = Signal(str)
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, api: BrickCoreApi, version_info: dict, baked_gui_version: str, parent=None) -> None:
        super().__init__(parent)
        self._api = api
        self._version_info = version_info
        self._baked_gui_version = baked_gui_version

    def run(self) -> None:
        try:
            from runner_client.app.layered_updater import prepare_layered_update

            def _progress(label: str, received: int, total: int) -> None:
                if total > 0:
                    pct = int(received * 100 / total)
                    self.progress.emit(f"正在准备增量更新… {label} {pct}%")
                else:
                    self.progress.emit(f"正在准备增量更新… {label}")

            result = prepare_layered_update(
                self._api,
                self._version_info,
                baked_gui_version=self._baked_gui_version,
                progress=_progress,
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _AppStatusWorker(QThread):
    """后台探测 adb/u2，避免阻塞 GUI 线程。"""

    result_ready = Signal(dict)

    def __init__(self, *, enable_app: bool, force_probe: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._enable_app = enable_app
        self._force_probe = force_probe

    def run(self) -> None:
        panel = build_app_local_panel_text(
            enable_app=self._enable_app,
            force_probe=self._force_probe,
        )
        self.result_ready.emit(panel)


class _RecordingControlWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        api: BrickCoreApi,
        action: str,
        record_id: int,
        *,
        var_name: str = "",
        source: str = "text",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._action = action
        self._record_id = record_id
        self._var_name = var_name
        self._source = source

    def run(self) -> None:
        try:
            if self._action == "pause":
                self._api.pause_recording(self._record_id)
                self.finished_ok.emit(f"[录制面板] 已暂停录制 #{self._record_id}")
            elif self._action == "resume":
                self._api.resume_recording(self._record_id)
                self.finished_ok.emit(f"[录制面板] 已继续录制 #{self._record_id}")
            elif self._action == "stop":
                self._api.stop_recording(self._record_id)
                self.finished_ok.emit(f"[录制面板] 已发送停止录制 #{self._record_id}")
            elif self._action == "save_variable":
                self._api.save_recording_variable(
                    self._record_id,
                    self._var_name,
                    self._source,
                )
                self.finished_ok.emit(f"[录制面板] 已存变量 ${{{self._var_name}}}")
            else:
                self.failed.emit(f"未知录制操作: {self._action}")
        except ApiError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class _RecordingPollWorker(QThread):
    """后台轮询本机进行中的 Web 录制。"""

    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, api: BrickCoreApi, parent=None) -> None:
        super().__init__(parent)
        self._api = api

    def run(self) -> None:
        try:
            self.result_ready.emit(self._api.fetch_active_recording())
        except ApiError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class _ConnectWorker(QThread):
    """上线前检查 Runner 依赖并调用 connect API（避免阻塞 UI）。"""

    prepared = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        api: BrickCoreApi,
        device_name: str,
        runner_dir: Path,
        *,
        execution_role: str,
        enable_web: bool = True,
        enable_app: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._device_name = device_name
        self._runner_dir = runner_dir
        self._execution_role = execution_role
        self._enable_web = enable_web
        self._enable_app = enable_app

    def run(self) -> None:
        need_ui = self._execution_role in (EXEC_ROLE_UI, EXEC_ROLE_BOTH)
        need_perf = self._execution_role in (EXEC_ROLE_PERF, EXEC_ROLE_BOTH)

        if need_ui:
            if not self._enable_web and not self._enable_app:
                self.prepared.emit(
                    {
                        "runtime_ok": False,
                        "message": "已选择 UI 通道，请至少勾选 Web 或 App。",
                        "repair": None,
                        "runtime_kind": "ui",
                    }
                )
                return

            ok, message, repair = diagnose_runner_runtime(
                self._runner_dir,
                require_playwright_browser=self._enable_web,
            )
            if not ok:
                self.prepared.emit(
                    {
                        "runtime_ok": False,
                        "message": message,
                        "repair": repair,
                        "runtime_kind": "ui",
                    }
                )
                return

            if self._enable_app:
                ok, message, repair = diagnose_app_runtime(self._runner_dir)
                if not ok:
                    self.prepared.emit(
                        {
                            "runtime_ok": False,
                            "message": message,
                            "repair": repair,
                            "runtime_kind": "app",
                        }
                    )
                    return

        if need_perf:
            ok, message, repair = diagnose_perf_runtime(self._runner_dir)
            if not ok:
                self.prepared.emit(
                    {
                        "runtime_ok": False,
                        "message": message,
                        "repair": repair,
                        "runtime_kind": "perf",
                    }
                )
                return

        connect_data: dict = {}
        if need_ui:
            try:
                connect_data = self._api.connect_runner(self._device_name)
            except ApiError as exc:
                self.failed.emit(str(exc))
                return
            except Exception as exc:
                self.failed.emit(str(exc))
                return

        self.prepared.emit(
            {
                "runtime_ok": True,
                "connect_data": connect_data,
                "execution_role": self._execution_role,
            }
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BrickCore Runner · 执行器客户端")
        self.resize(820, 780)
        self.setMinimumSize(720, 560)
        app_icon = _load_app_icon()
        if app_icon is not None:
            self.setWindowIcon(app_icon)

        self.engine = EngineManager()
        self.perf_engine = PerfWorkerManager()
        self.api: BrickCoreApi | None = None
        self.connect_data: dict | None = None
        self._online = False
        self._active_role = EXEC_ROLE_UI
        self._perf_project_id: int | None = None
        self.servers = load_servers()
        self.prefs = load_preferences()
        self._version_info: dict | None = None
        self._quitting = False
        self._health_poll_ms = 10_000
        # 独立 API 探活间隔：上线且绿灯主要靠心跳，避免额外刷 /runner/health
        self._api_health_ttl_ok_sec = 120.0
        self._api_health_ttl_bad_sec = 30.0
        self._api_health_ttl_unknown_sec = 15.0
        self._last_api_health_ts = 0.0
        self._last_api_health_ok: bool | None = None
        self._api_health_gen = 0
        self._api_health_worker: _ApiHealthWorker | None = None
        self._recording_poll_idle_ms = 3_000
        self._recording_poll_active_ms = 1_500
        self._recording_active = False
        self._version_worker: _VersionInfoWorker | None = None
        self._layered_update_worker: _LayeredUpdateWorker | None = None
        self._connect_worker: _ConnectWorker | None = None
        self._app_status_worker: _AppStatusWorker | None = None
        self._recording_poll_worker: _RecordingPollWorker | None = None
        self._recording_control_worker: _RecordingControlWorker | None = None
        self._recording_control_busy = False
        self._pending_perf_project_id: int | None = None
        self._last_app_udid: str = ""
        self._active_agent_task: ActiveAgentTask | None = None

        self._app_status_debounce = QTimer(self)
        self._app_status_debounce.setSingleShot(True)
        self._app_status_debounce.setInterval(450)
        self._app_status_debounce.timeout.connect(
            lambda: self._refresh_app_local_status(force_probe=False)
        )

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

        self.recording_poll_timer = QTimer(self)
        self.recording_poll_timer.setInterval(self._recording_poll_idle_ms)
        self.recording_poll_timer.timeout.connect(self._poll_active_recording)

        QTimer.singleShot(100, self._refresh_version_badge)
        QTimer.singleShot(300, self._check_version_on_startup)

    def _check_runner_runtime(self) -> None:
        ok, message, repair = diagnose_runner_runtime(self.engine.runner_dir)
        if ok:
            return
        self._offer_runtime_repair(message, repair)

    def _offer_runtime_repair(self, message: str, repair: RepairKind) -> bool:
        if not repair:
            QMessageBox.critical(self, "Runner 运行时", message)
            return False
        if repair == "deps":
            prompt = (
                f"{message}\n\n"
                "常见原因：未通过 start-client.bat 启动，或 runner/venv 依赖未装全。\n"
                "是否现在安装 Python 依赖？（需联网）"
            )
        else:
            prompt = f"{message}\n\n是否现在下载安装 Chromium？（需联网，约 150MB）"
        answer = QMessageBox.question(
            self,
            "Runner 运行时",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        dialog = _RuntimeRepairDialog(self.engine.runner_dir, repair_kind=repair, parent=self)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("centralRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_card = QWidget()
        header_card.setObjectName("headerCard")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("BrickCore Runner")
        title.setObjectName("appTitle")
        subtitle = QLabel("Web / App / 接口代发 / 压测")
        subtitle.setObjectName("appSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch()

        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("versionBadge")
        header_layout.addWidget(self.version_label)

        self.update_btn = QPushButton("检查更新")
        header_layout.addWidget(self.update_btn)
        self.update_btn.clicked.connect(self._check_version_update)
        layout.addWidget(header_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(12)

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
        scroll_layout.addWidget(server_box)

        login_box = QGroupBox("登录")
        login_form = QFormLayout(login_box)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        login_form.addRow("用户名", self.username_edit)
        login_form.addRow("密码", self.password_edit)
        scroll_layout.addWidget(login_box)

        device_box = QGroupBox("设备")
        device_form = QFormLayout(device_box)
        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("如：Windows本地 / Windows本地-线上")
        device_form.addRow("设备名称", self.device_name_edit)
        scroll_layout.addWidget(device_box)

        self.engine_box = QGroupBox("本机能力")
        engine_layout = QVBoxLayout(self.engine_box)
        engine_row = QHBoxLayout()
        self.engine_web_cb = QCheckBox("Web")
        self.engine_web_cb.setChecked(bool(self.prefs.get("engine_web_enabled", True)))
        self.engine_app_cb = QCheckBox("App")
        self.engine_app_cb.setChecked(bool(self.prefs.get("engine_app_enabled", False)))
        self.role_api_cb = QCheckBox("接口代发")
        self.role_api_cb.setChecked(bool(self.prefs.get("enable_api_proxy", False)))
        self.role_perf_cb = QCheckBox("压测")
        self.role_perf_cb.setChecked(bool(self.prefs.get("enable_perf", False)))
        self.engine_web_cb.setToolTip("承接 Playwright Web UI 自动化任务")
        self.engine_app_cb.setToolTip("承接 Android App 自动化任务（需 adb + uiautomator2 + 真机）")
        self.role_api_cb.setToolTip(
            "承接平台「经执行机发送」的接口调试 / 套件整包。与压测共用同一 Worker 进程和项目。"
        )
        self.role_perf_cb.setToolTip("承接分布式压测任务。与接口代发共用同一 Worker 进程和项目。")
        for cb in (self.engine_web_cb, self.engine_app_cb, self.role_api_cb, self.role_perf_cb):
            engine_row.addWidget(cb)
            cb.toggled.connect(self._on_caps_changed)
        engine_row.addStretch()
        engine_layout.addLayout(engine_row)
        engine_hint = QLabel(
            "复选，选啥用啥。Web / App 走 UI 通道；接口代发与压测共用同一执行机进程和项目（同一时间只能跑一个任务）。"
            "勾选接口或压测后需选择项目（与平台顶部项目一致）。"
        )
        engine_hint.setWordWrap(True)
        engine_hint.setStyleSheet("color: #909399; font-size: 11px;")
        engine_layout.addWidget(engine_hint)
        scroll_layout.addWidget(self.engine_box)

        self.app_box = QGroupBox("App 自动化（本机）")
        app_layout = QVBoxLayout(self.app_box)
        app_layout.setContentsMargins(4, 6, 4, 4)
        app_layout.setSpacing(10)

        app_pill_row = QHBoxLayout()
        self.app_adb_pill = QLabel("adb ○")
        self.app_u2_pill = QLabel("u2 ○")
        self.app_ready_pill = QLabel("App ○")
        for lbl in (self.app_adb_pill, self.app_u2_pill, self.app_ready_pill):
            lbl.setObjectName("healthPill")
            lbl.setProperty("health", "idle")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
            app_pill_row.addWidget(lbl)
        app_pill_row.addStretch()
        self.app_refresh_btn = QPushButton("刷新检测")
        self.app_refresh_btn.clicked.connect(lambda: self._refresh_app_local_status(force_probe=True))
        app_pill_row.addWidget(self.app_refresh_btn)
        app_layout.addLayout(app_pill_row)

        app_action_row = QHBoxLayout()
        self.app_inspector_btn = QPushButton("打开元素探查")
        self.app_inspector_btn.setToolTip("在浏览器中打开平台「元素探查」（需已登录并上线）")
        self.app_inspector_btn.clicked.connect(self._open_app_inspector)
        app_action_row.addWidget(self.app_inspector_btn)
        app_action_row.addStretch()
        app_layout.addLayout(app_action_row)

        self.app_summary_label = QLabel("")
        self.app_summary_label.setWordWrap(True)
        self.app_summary_label.setStyleSheet(
            "color: #374151; font-size: 12px; margin-top: 4px; padding-top: 2px;"
        )
        app_layout.addWidget(self.app_summary_label)

        self.app_connect_hint_label = QLabel("")
        self.app_connect_hint_label.setWordWrap(True)
        self.app_connect_hint_label.setStyleSheet(
            "color: #4b5563; font-size: 11px; line-height: 1.45; "
            "margin-top: 2px; padding: 8px 10px; background: #f9fafb; "
            "border: 1px solid #e5e7eb; border-radius: 8px;"
        )
        self.app_connect_hint_label.setVisible(False)
        app_layout.addWidget(self.app_connect_hint_label)

        self.app_devices_label = QLabel("")
        self.app_devices_label.setWordWrap(True)
        self.app_devices_label.setStyleSheet(
            "color: #4b5563; font-size: 11px; font-family: Consolas, 'Courier New', monospace;"
        )
        app_layout.addWidget(self.app_devices_label)

        self.app_report_label = QLabel("")
        self.app_report_label.setWordWrap(True)
        self.app_report_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        app_layout.addWidget(self.app_report_label)

        app_hint = QLabel(
            "说明：勾选上方「App」后上线才会接收 App 任务。"
            "首次使用请在 runner\\venv 下执行 python -m uiautomator2 init（需 adb 已连通设备）。"
            "详细步骤见解压目录内《执行器安装指南》→ App 自动化。"
        )
        app_hint.setWordWrap(True)
        app_hint.setStyleSheet("color: #909399; font-size: 11px; margin-top: 4px;")
        app_layout.addWidget(app_hint)
        scroll_layout.addWidget(self.app_box)
        self._reset_app_local_status_idle()

        self.perf_box = QGroupBox("接口 / 压测项目")
        perf_form = QFormLayout(self.perf_box)
        self.perf_project_combo = QComboBox()
        self.perf_project_combo.setPlaceholderText("登录后加载项目列表")
        perf_form.addRow("所属项目", self.perf_project_combo)
        self.perf_max_concurrent_spin = QSpinBox()
        self.perf_max_concurrent_spin.setRange(1, 2000)
        self.perf_max_concurrent_spin.setValue(200)
        perf_form.addRow("压测最大并发", self.perf_max_concurrent_spin)
        self.perf_max_concurrent_spin.setToolTip("仅压测施压使用；接口代发不受此值限制。")
        self.perf_box.setVisible(False)
        scroll_layout.addWidget(self.perf_box)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("登录")
        self.connect_btn = QPushButton("上线")
        self.connect_btn.setObjectName("primaryBtn")
        self.disconnect_btn = QPushButton("下线")
        self.disconnect_btn.setObjectName("dangerBtn")
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
        scroll_layout.addLayout(btn_row)

        health_box = QGroupBox("连接状态")
        health_layout = QHBoxLayout(health_box)
        health_layout.setSpacing(10)
        self.health_api = QLabel("平台 API ○")
        self.health_mq = QLabel("消息队列 ○")
        self.health_redis = QLabel("Redis ○")
        self.health_engine = QLabel("Web/App ○")
        self.health_perf = QLabel("执行机 ○")
        for lbl in (self.health_api, self.health_mq, self.health_redis, self.health_engine, self.health_perf):
            lbl.setObjectName("healthPill")
            lbl.setProperty("health", "idle")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
            health_layout.addWidget(lbl)
        health_layout.addStretch()
        scroll_layout.addWidget(health_box)

        self.status_label = QLabel("状态：未连接")
        self.status_label.setObjectName("statusBanner")
        self.status_label.setWordWrap(True)
        scroll_layout.addWidget(self.status_label)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)

        log_panel = QWidget()
        log_panel_layout = QVBoxLayout(log_panel)
        log_panel_layout.setContentsMargins(0, 0, 0, 0)
        log_panel_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("当前会话日志")
        log_title.setFont(QFont("", 10, QFont.Weight.Bold))
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.clear_log_btn = QPushButton("清空显示")
        self.clear_log_btn.setToolTip("仅清空下方面板中的日志显示，不删除磁盘上的日志文件")
        self.clear_log_btn.clicked.connect(self._clear_log_display)
        log_header.addWidget(self.clear_log_btn)
        self.stop_agent_btn = QPushButton("停止当前任务")
        self.stop_agent_btn.setObjectName("dangerBtn")
        self.stop_agent_btn.setToolTip("停止本机正在运行的智能浏览器 / UI Agent 任务（无需打开平台页面）")
        self.stop_agent_btn.setEnabled(False)
        self.stop_agent_btn.clicked.connect(self._on_stop_active_agent)
        log_header.addWidget(self.stop_agent_btn)
        self.history_log_btn = QPushButton("历史日志…")
        self.history_log_btn.clicked.connect(self._open_log_history)
        log_header.addWidget(self.history_log_btn)
        log_panel_layout.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("本次上线后的 Runner 日志将显示在这里…")
        self.log_view.setMinimumHeight(120)
        log_panel_layout.addWidget(self.log_view, stretch=1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(scroll)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([420, 260])

        self.recording_panel = RecordingPanel()
        self.recording_panel.setVisible(False)
        self.recording_panel.setMinimumWidth(260)
        self.recording_panel.pause_requested.connect(self._on_recording_pause)
        self.recording_panel.resume_requested.connect(self._on_recording_resume)
        self.recording_panel.stop_requested.connect(self._on_recording_stop)
        self.recording_panel.save_variable_requested.connect(self._on_recording_save_variable)

        self._outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._outer_splitter.addWidget(splitter)
        self._outer_splitter.addWidget(self.recording_panel)
        self._outer_splitter.setStretchFactor(0, 3)
        self._outer_splitter.setStretchFactor(1, 2)
        self._outer_splitter.setChildrenCollapsible(False)
        self._outer_splitter.setSizes([820, 0])
        layout.addWidget(self._outer_splitter, stretch=1)
        self._on_caps_changed()

    def _reset_app_local_status_idle(self) -> None:
        """App 面板初始态：不探测 adb/u2，等用户点击「刷新检测」。"""
        for pill, name in (
            (self.app_adb_pill, "adb"),
            (self.app_u2_pill, "u2"),
            (self.app_ready_pill, "App"),
        ):
            self._set_health_label(pill, name, None)
        self.app_summary_label.setText("点击「刷新检测」查看本机 adb / u2 / Android 设备状态。")
        self.app_connect_hint_label.setText("")
        self.app_connect_hint_label.setVisible(False)
        self.app_devices_label.setText("")
        self.app_report_label.setText("")

    def _refresh_app_local_status(self, *, force_probe: bool = False) -> None:
        if self._app_status_worker and self._app_status_worker.isRunning():
            if not force_probe:
                return
            self._app_status_worker.requestInterruption()
            self._app_status_worker.wait(200)

        if force_probe:
            from runner_client.app.engine_capabilities import invalidate_app_toolchain_cache

            invalidate_app_toolchain_cache()

        _, enable_app = self._get_engine_flags()
        self.app_refresh_btn.setEnabled(False)
        worker = _AppStatusWorker(enable_app=enable_app, force_probe=force_probe, parent=self)
        self._app_status_worker = worker
        worker.result_ready.connect(self._apply_app_local_panel)
        worker.finished.connect(lambda: self.app_refresh_btn.setEnabled(True))
        worker.start()

    def _apply_app_local_panel(self, panel: dict) -> None:
        self._set_health_label(self.app_adb_pill, "adb", panel.get("adb_ok"))
        self._set_health_label(self.app_u2_pill, "u2", panel.get("u2_ok"))
        self._set_health_label(self.app_ready_pill, "App", panel.get("app_ready"))
        adb_path = panel.get("adb_path") or ""
        summary = panel.get("summary") or ""
        if adb_path:
            summary = f"{summary}\nadb 路径：{adb_path}"
        self.app_summary_label.setText(summary.strip())
        connect_hint = (panel.get("connect_hint") or "").strip()
        self.app_connect_hint_label.setText(connect_hint)
        self.app_connect_hint_label.setVisible(bool(connect_hint))
        self.app_devices_label.setText(panel.get("devices_text") or "")
        self.app_report_label.setText(panel.get("report_text") or "")
        caps = panel.get("caps") or {}
        udid = (caps.get("app_udid") or "").strip()
        if udid:
            self._last_app_udid = udid

    def _schedule_app_local_status_refresh(self) -> None:
        if self._online:
            return
        self._app_status_debounce.start()

    def _open_app_inspector(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            QMessageBox.warning(self, "提示", "请先配置并登录平台服务器。")
            return
        if not self.api or not self.api.user_token:
            QMessageBox.warning(self, "提示", "请先登录平台。")
            return
        if not self._online:
            QMessageBox.warning(self, "提示", "请先上线 Runner，再在平台中使用 Inspector。")
            return
        device_id = (self.connect_data or {}).get("device_id", "")
        if not device_id:
            QMessageBox.warning(self, "提示", "未获取到设备 ID，请重新上线。")
            return
        query_params = {"device_id": device_id}
        udid = (self._last_app_udid or "").strip()
        if udid:
            query_params["app_udid"] = udid
        url = f"{base_url.rstrip('/')}/#/app-inspector?{urlencode(query_params)}"
        QDesktopServices.openUrl(QUrl(url))

    def _set_health_label(self, label: QLabel, name: str, ok: bool | None) -> None:
        state = _health_state(ok)
        label.setText(f"{name} {_status_dot(ok)}")
        label.setProperty("health", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def _setup_tray(self) -> None:
        icon = _load_app_icon() or self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
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
        online = self._online
        self.tray_connect_action.setEnabled(logged_in and not online)
        self.tray_disconnect_action.setEnabled(online)
        self.tray_login_action.setEnabled(not online)

    def _get_execution_role(self) -> str:
        need_ui = self._needs_ui_role()
        need_perf = self._needs_perf_role()
        if need_ui and need_perf:
            return EXEC_ROLE_BOTH
        if need_perf:
            return EXEC_ROLE_PERF
        if need_ui:
            return EXEC_ROLE_UI
        return ""

    def _worker_kind_labels(self) -> list[str]:
        labels: list[str] = []
        if self.role_api_cb.isChecked():
            labels.append("接口代发")
        if self.role_perf_cb.isChecked():
            labels.append("压测")
        return labels

    def _worker_kind_text(self, *, empty: str = "执行机") -> str:
        labels = self._worker_kind_labels()
        return " + ".join(labels) if labels else empty

    def _worker_health_name(self) -> str:
        labels = self._worker_kind_labels()
        if len(labels) == 2:
            return "接口/压测"
        if labels:
            return labels[0]
        return "执行机"

    def _ui_engine_health_name(self) -> str:
        enable_web, enable_app = self._get_engine_flags()
        if enable_web and enable_app:
            return "Web/App"
        if enable_web:
            return "Web"
        if enable_app:
            return "App"
        return "Web/App"

    def _needs_ui_role(self, role: str | None = None) -> bool:
        if role is not None:
            return role in (EXEC_ROLE_UI, EXEC_ROLE_BOTH)
        return self.engine_web_cb.isChecked() or self.engine_app_cb.isChecked()

    def _needs_perf_role(self, role: str | None = None) -> bool:
        if role is not None:
            return role in (EXEC_ROLE_PERF, EXEC_ROLE_BOTH)
        return self.role_api_cb.isChecked() or self.role_perf_cb.isChecked()

    def _get_engine_flags(self) -> tuple[bool, bool]:
        return self.engine_web_cb.isChecked(), self.engine_app_cb.isChecked()

    def _apply_engine_flags(self, enable_web: bool, enable_app: bool) -> None:
        self.engine_web_cb.blockSignals(True)
        self.engine_app_cb.blockSignals(True)
        self.engine_web_cb.setChecked(enable_web)
        self.engine_app_cb.setChecked(enable_app)
        self.engine_web_cb.blockSignals(False)
        self.engine_app_cb.blockSignals(False)

    def _sync_api_engine_flags(self) -> None:
        enable_web, enable_app = self._get_engine_flags()
        if self.api:
            self.api.engine_web_enabled = enable_web
            self.api.engine_app_enabled = enable_app

    def _on_caps_changed(self, _checked: bool = False) -> None:
        enable_web, enable_app = self._get_engine_flags()
        self.prefs["engine_web_enabled"] = enable_web
        self.prefs["engine_app_enabled"] = enable_app
        self.prefs["enable_api_proxy"] = self.role_api_cb.isChecked()
        self.prefs["enable_perf"] = self.role_perf_cb.isChecked()
        from runner_client.app.preferences import save_preferences

        save_preferences(self.prefs)
        self._sync_api_engine_flags()
        need_perf = self._needs_perf_role()
        self.perf_box.setVisible(need_perf)
        self.app_box.setVisible(enable_app)
        disabled = self._online
        for cb in (self.engine_web_cb, self.engine_app_cb, self.role_api_cb, self.role_perf_cb):
            cb.setEnabled(not disabled)
        self.perf_project_combo.setEnabled(not disabled)
        self.perf_max_concurrent_spin.setEnabled(
            not disabled and self.role_perf_cb.isChecked()
        )
        if not self._online:
            self._set_health_label(self.health_engine, self._ui_engine_health_name(), None)
            self._set_health_label(self.health_perf, self._worker_health_name(), None)
            if enable_app:
                self._schedule_app_local_status_refresh()

    def _apply_session_execution_prefs(self, session: dict) -> None:
        """恢复会话中的能力勾选、项目与压测并发。"""
        max_conc = session.get("perf_max_concurrent")
        if isinstance(max_conc, int) and max_conc > 0:
            self.perf_max_concurrent_spin.setValue(max_conc)
        self._pending_perf_project_id = session.get("perf_project_id")
        enable_web = session.get("engine_web_enabled")
        if enable_web is None:
            enable_web = self.prefs.get("engine_web_enabled", True)
        enable_app = session.get("engine_app_enabled")
        if enable_app is None:
            enable_app = self.prefs.get("engine_app_enabled", False)
        self._apply_engine_flags(bool(enable_web), bool(enable_app))
        enable_api = session.get("enable_api_proxy")
        if enable_api is None:
            enable_api = self.prefs.get("enable_api_proxy", False)
        enable_perf = session.get("enable_perf")
        if enable_perf is None:
            enable_perf = self.prefs.get("enable_perf", False)
        self.role_api_cb.blockSignals(True)
        self.role_perf_cb.blockSignals(True)
        self.role_api_cb.setChecked(bool(enable_api))
        self.role_perf_cb.setChecked(bool(enable_perf))
        self.role_api_cb.blockSignals(False)
        self.role_perf_cb.blockSignals(False)
        self._sync_api_engine_flags()
        self._on_caps_changed()

    def _select_perf_project(self, project_id: int | None) -> None:
        if project_id is None:
            return
        for i in range(self.perf_project_combo.count()):
            if self.perf_project_combo.itemData(i) == project_id:
                self.perf_project_combo.setCurrentIndex(i)
                return

    def _load_projects_for_user(self) -> None:
        if not self.api or not self.api.user_token:
            return
        try:
            projects = self.api.list_projects()
        except ApiError as exc:
            self._append_log(f"[客户端] 加载项目列表失败：{exc}")
            return
        except Exception as exc:
            self._append_log(f"[客户端] 加载项目列表失败：{exc}")
            return

        current_id = self.perf_project_combo.currentData()
        self.perf_project_combo.blockSignals(True)
        self.perf_project_combo.clear()
        default_id = None
        for project in projects:
            pid = project.get("id")
            name = project.get("name") or f"项目 {pid}"
            if pid is None:
                continue
            label = name
            if project.get("is_user_default"):
                label = f"{name}（默认）"
                default_id = pid
            self.perf_project_combo.addItem(label, pid)
        self.perf_project_combo.blockSignals(False)

        pending = getattr(self, "_pending_perf_project_id", None)
        if pending:
            self._select_perf_project(pending)
            self._pending_perf_project_id = None
        elif current_id:
            self._select_perf_project(current_id)
        elif default_id:
            self._select_perf_project(default_id)
        elif self.perf_project_combo.count() > 0:
            self.perf_project_combo.setCurrentIndex(0)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._quitting = True
        if self._online:
            self._on_disconnect()
        self.tray.hide()
        QApplication.quit()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, runner_online=self._online)
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
        self._apply_session_execution_prefs(session)
        self.password_edit.clear()
        if self.prefs.get("remember_password"):
            token = session.get("password_token", "")
            if token:
                self.password_edit.setText(decrypt_text(token))
        # 换服务器后清空旧灯态，避免上一台的红/绿粘住
        self._last_api_health_ok = None
        self._last_api_health_ts = 0.0
        self._api_health_gen += 1
        self._refresh_health(force_api_probe=True)

    def _append_log(self, text: str) -> None:
        if not text:
            return
        cleaned = _clean_log_text(text)
        self.log_view.appendPlainText(cleaned)
        for line in cleaned.splitlines():
            self._active_agent_task = apply_log_line(self._active_agent_task, line)
        self._sync_stop_agent_btn()
        scrollbar = self.log_view.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _sync_stop_agent_btn(self) -> None:
        if not hasattr(self, "stop_agent_btn"):
            return
        enabled = bool(
            self._online
            and self._active_agent_task
            and self._needs_ui_role(self._active_role)
            and self.engine.is_running
        )
        self.stop_agent_btn.setEnabled(enabled)
        if self._active_agent_task:
            self.stop_agent_btn.setText(f"停止 {self._active_agent_task.label}")
        else:
            self.stop_agent_btn.setText("停止当前任务")

    def _on_stop_active_agent(self) -> None:
        task = self._active_agent_task
        label = task.label if task else "当前 Agent 任务"
        answer = QMessageBox.question(
            self,
            "停止任务",
            f"确定停止本机正在运行的 {label}？\n\n将通知 Runner 优雅停止并回传「已停止」到平台。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            request_stop_active_agent(source="runner_client_ui")
            self._append_log(f"[客户端] 已发送本机停止指令：{label}")
        except Exception as exc:
            QMessageBox.warning(self, "停止失败", str(exc))

    def _open_log_history(self) -> None:
        dialog = _LogHistoryDialog(self.engine, parent=self)
        dialog.exec()

    def _clear_log_display(self) -> None:
        """仅清空会话日志面板；磁盘日志保留，读指针移到文件末尾以免旧内容回灌。"""
        self.log_view.clear()
        try:
            self.engine.discard_displayed_logs()
        except Exception:
            pass
        try:
            self.perf_engine.discard_displayed_logs()
        except Exception:
            pass
        self._append_log("[客户端] 已清空会话日志显示（磁盘日志未删除）")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _api_health_ttl_sec(self) -> float:
        if self._last_api_health_ok is True:
            return self._api_health_ttl_ok_sec
        if self._last_api_health_ok is False:
            return self._api_health_ttl_bad_sec
        return self._api_health_ttl_unknown_sec

    def _mark_api_health(self, ok: bool, *, invalidate_inflight: bool = True) -> None:
        """同步更新平台 API 灯；可作废进行中的探活，避免旧结果回刷。"""
        if invalidate_inflight:
            self._api_health_gen += 1
        self._last_api_health_ok = bool(ok)
        self._last_api_health_ts = time.monotonic()
        self._set_health_label(self.health_api, "平台 API", self._last_api_health_ok)

    def _schedule_api_health_probe(self, *, force: bool = False) -> None:
        base_url = self._current_server_url()
        if not base_url:
            return
        now = time.monotonic()
        ttl = self._api_health_ttl_sec()
        if (
            not force
            and self._last_api_health_ok is not None
            and (now - self._last_api_health_ts) < ttl
        ):
            self._set_health_label(self.health_api, "平台 API", self._last_api_health_ok)
            return
        # 非强制：已有探活在跑则复用，避免叠请求
        if not force and self._api_health_worker and self._api_health_worker.isRunning():
            return
        # 强制探活：抬升代数，丢弃进行中/迟到的旧结果
        self._api_health_gen += 1
        gen = self._api_health_gen
        if self._last_api_health_ok is None:
            self._set_health_label(self.health_api, "平台 API", None)
            self.health_api.setText("平台 API ○ 检测中…")
        worker = _ApiHealthWorker(base_url, parent=self)
        self._api_health_worker = worker
        worker.result_ready.connect(
            lambda ok, g=gen: self._on_api_health_probe_result(ok, g)
        )
        worker.start()

    def _on_api_health_probe_result(self, api_ok: bool, gen: int | None = None) -> None:
        # 迟到的旧探活（换服务器 / 登录已标绿 / 强制重探）一律丢弃
        if gen is not None and gen != self._api_health_gen:
            return
        self._last_api_health_ok = bool(api_ok)
        self._last_api_health_ts = time.monotonic()
        self._set_health_label(self.health_api, "平台 API", self._last_api_health_ok)

    def _refresh_health(self, *, force_api_probe: bool = False) -> None:
        # UI 上线且已绿：靠 30s 心跳维持，不另打 /runner/health
        # 仅接口代发/压测时无 UI 心跳，仍按 TTL 低频探活，避免绿灯永久粘住
        if force_api_probe:
            self._schedule_api_health_probe(force=True)
        elif (
            self._online
            and self._last_api_health_ok is True
            and self._needs_ui_role(self._active_role)
        ):
            self._set_health_label(self.health_api, "平台 API", True)
        else:
            self._schedule_api_health_probe(force=False)

        mq_ok = redis_ok = None
        if self.connect_data and self._needs_ui_role(self._active_role):
            probes = probe_connect_bundle(self.connect_data)
            mq_ok = probes["mq"]
            redis_ok = probes["redis"]
        self._set_health_label(self.health_mq, "消息队列", mq_ok)
        self._set_health_label(self.health_redis, "Redis", redis_ok)

        if self._online:
            if self._needs_ui_role(self._active_role):
                engine_ok = self.engine.is_running
            else:
                engine_ok = None
            if self._needs_perf_role(self._active_role):
                perf_ok = self.perf_engine.is_running
            else:
                perf_ok = None
        else:
            engine_ok = perf_ok = None
        self._set_health_label(self.health_engine, self._ui_engine_health_name(), engine_ok)
        self._set_health_label(self.health_perf, self._worker_health_name(), perf_ok)

    def _check_version_on_startup(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            return
        if self._version_worker and self._version_worker.isRunning():
            return
        worker = _VersionInfoWorker(base_url, parent=self)
        self._version_worker = worker
        worker.result_ready.connect(self._on_version_info_ready)
        worker.start()

    def _installed_package_version(self) -> str:
        from runner_client.app.layered_updater import package_version

        return package_version(baked_fallback=__version__)

    def _refresh_version_badge(self) -> None:
        pkg = self._installed_package_version()
        if pkg != __version__:
            self.version_label.setText(f"v{pkg}（GUI {__version__}）")
        else:
            self.version_label.setText(f"v{pkg}")

    def _on_version_info_ready(self, info: object) -> None:
        self._version_info = info if isinstance(info, dict) else None
        self._schedule_api_health_probe(force=True)
        if not self._version_info:
            return
        current = self._installed_package_version()
        latest = self._version_info.get("runner_client_version_latest") or ""
        minimum = self._version_info.get("runner_client_version_min") or ""
        if minimum and compare_version(current, minimum) < 0:
            self._show_version_dialog(
                f"当前客户端 {current} 低于平台要求 {minimum}，请尽快升级。",
                force=True,
            )
        elif latest and compare_version(current, latest) < 0:
            self._show_version_dialog(
                f"发现新版本 {latest}（当前 {current}），建议升级。",
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
        current = self._installed_package_version()
        latest = info.get("runner_client_version_latest") or ""
        if latest and compare_version(current, latest) < 0:
            self._show_version_dialog(f"发现新版本 {latest}（当前 {current}）", force=False)
        else:
            QMessageBox.information(self, "检查更新", f"当前已是最新版本（{current}）")

    def _is_logged_in(self) -> bool:
        return bool(self.api and self.api.user_token)

    def _show_version_dialog(self, message: str, force: bool = False) -> None:
        download = BrickCoreApi.resolve_download_url(self._current_server_url(), self._version_info)
        package_available = bool(self._version_info and self._version_info.get("package_available"))
        patches_available = bool(self._version_info and self._version_info.get("update_patches_available"))
        logged_in = self._is_logged_in()
        box = QMessageBox(self)
        box.setWindowTitle("客户端更新")
        box.setText(message)
        extra = []
        # 版本查询接口公开，无需登录；下载/增量包需登录，避免未登录仍露出会失败的按钮
        if not logged_in:
            extra.append("检查版本无需登录；下载完整包或一键增量更新请先登录平台账号。")
        elif patches_available:
            extra.append("平台已提供加密分层增量包，可点击「一键增量更新」（将自动覆盖并重启）。")
        if package_available and logged_in:
            extra.append("也可下载完整安装包后手动解压覆盖。")
        if download:
            extra.append(f"外链/静态地址：\n{download}")
        if extra:
            box.setInformativeText("\n".join(extra))
        patch_btn = None
        dl_btn = None
        login_btn = None
        if logged_in and patches_available:
            patch_btn = box.addButton("一键增量更新", QMessageBox.ButtonRole.AcceptRole)
        if logged_in and package_available:
            dl_btn = box.addButton("下载完整包", QMessageBox.ButtonRole.ActionRole)
        if not logged_in:
            login_btn = box.addButton("去登录", QMessageBox.ButtonRole.AcceptRole)
        open_btn = None
        if download:
            open_btn = box.addButton("在浏览器打开", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        if force:
            box.setIcon(QMessageBox.Icon.Warning)
        box.exec()
        clicked = box.clickedButton()
        if clicked == login_btn:
            self.username_edit.setFocus()
            self._set_status("请先登录后再下载或增量更新")
        elif clicked == patch_btn:
            self._apply_layered_update()
        elif clicked == dl_btn:
            self._download_client_package()
        elif clicked == open_btn and download:
            QDesktopServices.openUrl(QUrl(download))

    def _apply_layered_update(self) -> None:
        base_url = self._current_server_url()
        if not base_url:
            QMessageBox.warning(self, "更新", "请先选择服务器地址")
            return
        api = self.api if self.api and self.api.base_url.rstrip("/") == base_url.rstrip("/") else None
        if api is None:
            api = BrickCoreApi(base_url)
            if self.api and self.api.user_token:
                api.user_token = self.api.user_token
                api.username = self.api.username
        if not api.user_token:
            QMessageBox.warning(self, "更新", "请先登录平台后再增量更新")
            return
        if self._online:
            reply = QMessageBox.question(
                self,
                "更新",
                "更新前需要下线并退出客户端，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._on_disconnect()
        else:
            reply = QMessageBox.question(
                self,
                "更新",
                "增量更新将退出客户端并覆盖安装目录，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 重新拉版本信息，避免本地缓存清单过期
        info = api.fetch_version_info() or self._version_info or {}
        self._version_info = info
        if self._layered_update_worker and self._layered_update_worker.isRunning():
            QMessageBox.information(self, "更新", "增量更新正在准备中，请稍候")
            return
        try:
            self.update_btn.setEnabled(False)
            self._layered_progress_logged_pct = -1
            self._set_status("正在准备增量更新…（进度见下方状态栏与会话日志）")
            self._append_log("[客户端] 开始准备增量更新…")
            worker = _LayeredUpdateWorker(api, info, __version__, parent=self)
            self._layered_update_worker = worker
            worker.progress.connect(self._on_layered_update_progress)
            worker.finished_ok.connect(self._on_layered_update_ready)
            worker.finished_err.connect(self._on_layered_update_failed)
            worker.finished.connect(lambda: self.update_btn.setEnabled(True))
            worker.start()
        except Exception as exc:
            self.update_btn.setEnabled(True)
            self._append_log(f"[客户端] 启动增量更新失败: {exc}")
            QMessageBox.critical(self, "增量更新失败", str(exc))
            self._set_status(f"增量更新失败：{exc}")

    def _on_layered_update_progress(self, text: str) -> None:
        """增量下载进度：状态条 + 会话日志都可见（避免只改中部标签被忽略）。"""
        self._set_status(text)
        # 日志区刷太密会卡，约每 10% 或文案变化时写一行
        pct_mark = None
        if "%" in text:
            try:
                pct_mark = int(text.rsplit(" ", 1)[-1].rstrip("%"))
            except ValueError:
                pct_mark = None
        last = getattr(self, "_layered_progress_logged_pct", -1)
        if pct_mark is None or pct_mark >= last + 10 or pct_mark >= 100:
            self._append_log(f"[客户端] {text}")
            if pct_mark is not None:
                self._layered_progress_logged_pct = pct_mark

    def _on_layered_update_failed(self, message: str) -> None:
        QMessageBox.critical(self, "增量更新失败", message)
        self._set_status("增量更新失败")

    def _on_layered_update_ready(self, result: object) -> None:
        if not isinstance(result, dict):
            self._on_layered_update_failed("增量准备结果无效")
            return
        action = result.get("action")
        if action == "none":
            QMessageBox.information(self, "检查更新", "当前已是最新版本")
            self._set_status("当前已是最新版本")
            return
        if action != "patch" or not result.get("helper_script"):
            QMessageBox.information(
                self,
                "增量不可用",
                f"{result.get('reason') or '请改用完整安装包更新。'}",
            )
            self._download_client_package()
            return

        from runner_client.app.layered_updater import launch_apply_helper

        helper = Path(result["helper_script"])
        launch_apply_helper(helper)
        QMessageBox.information(
            self,
            "即将重启",
            "增量包已准备完成，客户端将退出并由更新助手覆盖文件后自动重启。",
        )
        QApplication.quit()

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
        payload: dict = {
            "username": username,
            "device_name": device_name,
            "perf_max_concurrent": self.perf_max_concurrent_spin.value(),
            "engine_web_enabled": self.engine_web_cb.isChecked(),
            "engine_app_enabled": self.engine_app_cb.isChecked(),
            "enable_api_proxy": self.role_api_cb.isChecked(),
            "enable_perf": self.role_perf_cb.isChecked(),
        }
        project_id = self.perf_project_combo.currentData()
        if project_id is not None:
            payload["perf_project_id"] = project_id
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
        self._sync_api_engine_flags()
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
        self._set_status(f"已登录 {base_url}（{username}），可点击「上线」启动执行器。")
        self._append_log(f"[客户端] 登录成功：{username} @ {base_url}")
        # 登录前已 health_check、登录接口也成功 → 直接绿灯；作废进行中的探活，避免迟到失败刷红
        self._mark_api_health(True, invalidate_inflight=True)
        self._load_projects_for_user()
        self._refresh_health(force_api_probe=False)
        self._sync_tray_actions()

    def _on_connect(self) -> None:
        if not self.api or not self.api.user_token:
            QMessageBox.warning(self, "提示", "请先登录")
            return
        if self._connect_worker and self._connect_worker.isRunning():
            return

        execution_role = self._get_execution_role()
        enable_web, enable_app = self._get_engine_flags()
        need_ui = self._needs_ui_role()
        need_perf = self._needs_perf_role()
        if not need_ui and not need_perf:
            QMessageBox.warning(self, "提示", "请至少勾选一项本机能力：Web、App、接口代发或压测")
            return
        if need_ui:
            self._sync_api_engine_flags()
        if need_perf:
            project_id = self.perf_project_combo.currentData()
            if not project_id:
                QMessageBox.warning(self, "提示", "请选择所属项目（需与平台顶部项目一致）")
                return

        if need_ui and need_perf:
            answer = QMessageBox.question(
                self,
                "双开确认",
                "UI（Web/App）与接口代发/压测同时运行会占用较多 CPU 与网络，可能影响 UI 用例稳定性。\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        device_name = self.device_name_edit.text().strip() or "执行设备"
        base_url = self._current_server_url()
        self._persist_session(self.username_edit.text().strip(), device_name, self.password_edit.text())

        self.connect_btn.setEnabled(False)
        self.login_btn.setEnabled(False)
        self._set_status("正在检查运行环境并上线…")

        enable_web, enable_app = self._get_engine_flags()
        worker = _ConnectWorker(
            self.api,
            device_name,
            self.engine.runner_dir,
            execution_role=execution_role,
            enable_web=enable_web,
            enable_app=enable_app,
            parent=self,
        )
        self._connect_worker = worker
        worker.prepared.connect(self._on_connect_prepared)
        worker.failed.connect(self._on_connect_failed)
        worker.start()

    def _on_connect_failed(self, message: str) -> None:
        self.connect_btn.setEnabled(True)
        self.login_btn.setEnabled(True)
        self._set_status("上线失败")
        QMessageBox.critical(self, "上线失败", message)

    def _on_connect_prepared(self, result: dict) -> None:
        if not result.get("runtime_ok"):
            self.connect_btn.setEnabled(True)
            self.login_btn.setEnabled(True)
            self._set_status("运行环境未就绪")
            if not self._offer_runtime_repair(
                str(result.get("message") or "运行时检查未通过"),
                result.get("repair"),
            ):
                return
            self._on_connect()
            return

        execution_role = result.get("execution_role") or ""
        if execution_role not in (EXEC_ROLE_UI, EXEC_ROLE_PERF, EXEC_ROLE_BOTH):
            self.connect_btn.setEnabled(True)
            self.login_btn.setEnabled(True)
            self._set_status("上线失败")
            QMessageBox.warning(self, "提示", "请至少勾选一项本机能力：Web、App、接口代发或压测")
            return
        self._active_role = execution_role
        self.connect_data = result.get("connect_data") or {}
        device_name = self.device_name_edit.text().strip() or "执行设备"
        base_url = self._current_server_url()

        if self._needs_ui_role(execution_role):
            latest = self.connect_data.get("client_version_latest") or ""
            pkg = self._installed_package_version()
            pkg_behind = bool(latest) and compare_version(pkg, latest) < 0
            gui_behind = bool(latest) and compare_version(__version__, latest) < 0
            if pkg_behind or gui_behind:
                # 刷新版本清单，便于对话框展示「一键增量更新」
                try:
                    info = BrickCoreApi(base_url).fetch_version_info()
                    if info:
                        self._version_info = info
                except Exception:
                    pass
                self._show_version_dialog(
                    f"当前客户端 {pkg}，平台最新 {latest}。",
                    force=False,
                )

        started_parts: list[str] = []
        enable_web, enable_app = self._get_engine_flags()
        try:
            if self._needs_ui_role(execution_role):
                if enable_web:
                    started_parts.append("Web")
                if enable_app:
                    started_parts.append("App")
                self.engine.start(self.connect_data, device_name)
            if self._needs_perf_role(execution_role):
                project_id = int(self.perf_project_combo.currentData())
                self._perf_project_id = project_id
                perf_name = device_name if execution_role == EXEC_ROLE_PERF else f"{device_name}-执行机"
                self.perf_engine.start(
                    master_url=base_url,
                    name=perf_name,
                    project_id=project_id,
                    max_concurrent=self.perf_max_concurrent_spin.value(),
                    # UI 角色上线后才有 runner_token；纯压测/接口代发依赖登录 JWT（Authorization Bearer）
                    runner_token=self.api.runner_token if self.api else None,
                    access_token=self.api.user_token if self.api else None,
                )
                if self.role_api_cb.isChecked():
                    started_parts.append("接口代发")
                if self.role_perf_cb.isChecked():
                    started_parts.append("压测")
        except Exception as exc:
            if self.engine.is_running:
                self.engine.stop()
            if self.perf_engine.is_running:
                self.perf_engine.stop()
            if self._needs_ui_role(execution_role) and self.api and self.connect_data.get("device_id"):
                try:
                    self.api.disconnect_runner(self.connect_data.get("device_id", ""))
                except Exception:
                    pass
            self.connect_btn.setEnabled(True)
            self.login_btn.setEnabled(True)
            self.connect_data = None
            self._active_role = EXEC_ROLE_UI
            self._set_status("启动失败")
            QMessageBox.critical(self, "启动失败", str(exc))
            return

        self._online = True
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.login_btn.setEnabled(False)
        self._sync_stop_agent_btn()
        self.poll_timer.start()
        if self._needs_ui_role(execution_role):
            self.heartbeat_timer.start()
            self._sync_recording_poll_interval(active=False)
            self.recording_poll_timer.start()
            QTimer.singleShot(200, self._poll_active_recording)
        else:
            self.heartbeat_timer.stop()
            self.recording_poll_timer.stop()
            self._set_recording_panel_visible(False)

        role_label = " + ".join(started_parts)
        device_id = self.connect_data.get("device_id", "")
        self.log_view.clear()
        status_bits = [f"已上线 · {role_label}"]
        if device_id:
            status_bits.append(f"设备 {device_name} ({device_id})")
        else:
            status_bits.append(device_name)
        status_bits.append(base_url)
        self._set_status(" · ".join(status_bits))

        from runner_client.app.engine_capabilities import detect_runner_capabilities
        from runner_client.app.engine_manager import runner_python_executable

        enable_web, enable_app = self._get_engine_flags()
        if self._needs_ui_role(execution_role):
            ui_parts = []
            if enable_web:
                ui_parts.append("Web")
            if enable_app:
                ui_parts.append("App")
            self._append_log(
                f"[客户端] 已启动 {' + '.join(ui_parts) or 'Web/App'} 通道，"
                f"device_id={device_id}，python={runner_python_executable()}"
            )
            caps = detect_runner_capabilities(enable_web=enable_web, enable_app=enable_app)
            engine_types = caps.get("runner_engine_types") or []
            labels: list[str] = []
            if "web" in engine_types:
                labels.append("Web")
            if "app" in engine_types:
                labels.append("App")
            self._append_log(f"[客户端] 已上报引擎能力：{' + '.join(labels) if labels else '无'}")
            if enable_web:
                bu = (caps.get("toolchain_status") or {}).get("browser_use")
                if bu == "ok":
                    self._append_log("[Web] browser-use 已就绪（智能浏览器 Runner 模式可用）")
                elif bu == "missing":
                    self._append_log(
                        "[Web] browser-use 未安装，智能浏览器 Runner 模式不可用；"
                        "请重新运行 start-client.bat 或安装包内的依赖修复"
                    )
            if enable_app and "app" in engine_types:
                udid = caps.get("app_udid") or "（未识别序列号）"
                if caps.get("app_udid"):
                    self._last_app_udid = str(caps.get("app_udid")).strip()
                self._append_log(f"[App] 已启用：adb + u2 正常，当前 Android 设备 {udid}")
            elif enable_app:
                self._append_log("[App] 已勾选但未就绪，请查看 App 面板并点击「刷新检测」")
        if self._needs_perf_role(execution_role):
            kinds = self._worker_kind_labels()
            extra = ""
            if self.role_perf_cb.isChecked():
                extra = f"，max_concurrent={self.perf_max_concurrent_spin.value()}"
            self._append_log(
                f"[客户端] 已启动执行机（{' + '.join(kinds) or 'Worker'}），"
                f"project_id={self.perf_project_combo.currentData()}{extra}"
            )

        self._on_caps_changed()
        self.health_timer.start()
        self._refresh_health(force_api_probe=True)
        self._sync_tray_actions()
        self.tray.showMessage(
            "BrickCore Runner",
            f"已上线（{role_label}），等待平台派发任务",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _on_disconnect(self) -> None:
        self.poll_timer.stop()
        self.heartbeat_timer.stop()
        self.health_timer.stop()
        self.recording_poll_timer.stop()
        self._sync_recording_poll_interval(active=False)
        self._set_recording_panel_visible(False)
        self.recording_panel.clear_recording()
        device_id = (self.connect_data or {}).get("device_id", "")
        if self.api and device_id and self._needs_ui_role(self._active_role):
            try:
                self.api.disconnect_runner(device_id)
            except Exception:
                pass
        if (
            self.api
            and self._needs_perf_role(self._active_role)
            and self._perf_project_id
        ):
            try:
                self.api.unregister_perf_worker(self._perf_project_id)
                self._append_log(f"[客户端] 执行机已向平台注销（{self._worker_kind_text()}）")
            except Exception as exc:
                self._append_log(f"[客户端] 执行机注销失败：{exc}")
        self.engine.stop()
        self.perf_engine.stop()
        self.connect_data = None
        self._perf_project_id = None
        self._online = False
        self._active_role = EXEC_ROLE_UI
        self._active_agent_task = None
        self.connect_btn.setEnabled(bool(self.api and self.api.user_token))
        self.disconnect_btn.setEnabled(False)
        self.login_btn.setEnabled(True)
        self._set_status("已下线")
        self._append_log("[客户端] 执行器已下线")
        self._sync_stop_agent_btn()
        self._on_caps_changed()
        self._refresh_health()
        self._sync_tray_actions()

    def _set_recording_panel_visible(self, visible: bool) -> None:
        self.recording_panel.setVisible(visible)
        if visible:
            self.recording_panel.setMaximumWidth(16777215)
            self._outer_splitter.setSizes([560, 300])
        else:
            self.recording_panel.setMaximumWidth(0)
            self._outer_splitter.setSizes([860, 0])

    def _poll_active_recording(self) -> None:
        if not self._online or not self.api or not self.api.runner_token:
            return
        if not self._needs_ui_role(self._active_role):
            return
        if self._recording_poll_worker and self._recording_poll_worker.isRunning():
            return
        worker = _RecordingPollWorker(self.api, parent=self)
        self._recording_poll_worker = worker
        worker.result_ready.connect(self._on_recording_snapshot)
        worker.failed.connect(self._on_recording_poll_failed)
        worker.start()

    def _sync_recording_poll_interval(self, *, active: bool) -> None:
        self._recording_active = bool(active)
        want = self._recording_poll_active_ms if active else self._recording_poll_idle_ms
        if self.recording_poll_timer.interval() != want:
            self.recording_poll_timer.setInterval(want)

    def _on_recording_snapshot(self, data: object) -> None:
        if not isinstance(data, dict) or data.get("status") != "recording":
            self._sync_recording_poll_interval(active=False)
            self._set_recording_panel_visible(False)
            self.recording_panel.clear_recording()
            return
        self._sync_recording_poll_interval(active=True)
        self._set_recording_panel_visible(True)
        self.recording_panel.apply_snapshot(data)

    def _on_recording_poll_failed(self, message: str) -> None:
        self._append_log(f"[录制面板] 轮询失败：{message}")

    def _run_recording_control(self, action: str, record_id: int, **kwargs) -> None:
        if not self.api or self._recording_control_busy:
            return
        if self._recording_control_worker and self._recording_control_worker.isRunning():
            return
        self._recording_control_busy = True
        worker = _RecordingControlWorker(
            self.api,
            action,
            record_id,
            var_name=str(kwargs.get("var_name") or ""),
            source=str(kwargs.get("source") or "text"),
            parent=self,
        )
        self._recording_control_worker = worker

        def _done(message: str) -> None:
            self._recording_control_busy = False
            self._append_log(message)
            self._poll_active_recording()

        def _fail(message: str) -> None:
            self._recording_control_busy = False
            QMessageBox.warning(self, "录制操作失败", message)

        worker.finished_ok.connect(_done)
        worker.failed.connect(_fail)
        worker.start()

    def _on_recording_pause(self, record_id: int) -> None:
        self._run_recording_control("pause", record_id)

    def _on_recording_resume(self, record_id: int) -> None:
        self._run_recording_control("resume", record_id)

    def _on_recording_stop(self, record_id: int) -> None:
        answer = QMessageBox.question(
            self,
            "停止录制",
            f"确定停止录制 #{record_id}？\n停止后请在平台弹窗中查看并应用步骤。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_recording_control("stop", record_id)

    def _on_recording_save_variable(self, record_id: int, var_name: str, source: str) -> None:
        self._run_recording_control(
            "save_variable",
            record_id,
            var_name=var_name,
            source=source,
        )

    def _poll_logs(self) -> None:
        if self._needs_ui_role(self._active_role):
            chunk = self.engine.read_new_log_lines()
            if chunk:
                self._append_log(chunk)
            chunk = self.engine.read_new_output()
            if chunk:
                self._append_log(chunk)

        if self._needs_perf_role(self._active_role):
            perf_chunk = self.perf_engine.read_new_log_lines()
            if not perf_chunk:
                perf_chunk = self.perf_engine.read_new_output()
            if perf_chunk:
                for line in perf_chunk.splitlines():
                    self._append_log(f"[执行机] {line}")

        if not self._online:
            return

        ui_dead = (
            self._needs_ui_role(self._active_role)
            and not self.engine.is_running
        )
        perf_dead = (
            self._needs_perf_role(self._active_role)
            and not self.perf_engine.is_running
        )
        if ui_dead:
            self._append_log("[客户端] Web/App 通道进程已退出")
        if perf_dead:
            self._append_log("[客户端] 执行机进程已退出")
        if ui_dead or perf_dead:
            self._on_disconnect()
        self._sync_stop_agent_btn()

    def _send_heartbeat(self) -> None:
        if not self.api or not self.connect_data or not self._needs_ui_role(self._active_role):
            return
        self._sync_api_engine_flags()
        device_id = self.connect_data.get("device_id", "")
        try:
            self.api.heartbeat(device_id)
            # 心跳成功即视为平台 HTTP 可达，无需另打 /runner/health
            self._mark_api_health(True, invalidate_inflight=False)
        except ApiError as exc:
            if exc.status_code in (401, 403):
                self._append_log("[客户端] 会话已失效或被管理员停止，自动下线")
                self._on_disconnect()
            elif self._last_api_health_ok is not False:
                self._mark_api_health(False, invalidate_inflight=False)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            if self._online:
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
        if self._online:
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
        self._match_cursors: list[QTextCursor] = []
        self._active_match_index = -1
        self.setWindowTitle("Runner 历史日志")
        self.resize(720, 520)

        layout = QVBoxLayout(self)
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #606266;")
        layout.addWidget(self._info_label)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索日志内容…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._search_edit.returnPressed.connect(self._find_next)
        search_row.addWidget(self._search_edit, stretch=1)
        self._prev_btn = QPushButton("上一个")
        self._prev_btn.clicked.connect(self._find_prev)
        self._next_btn = QPushButton("下一个")
        self._next_btn.clicked.connect(self._find_next)
        search_row.addWidget(self._prev_btn)
        search_row.addWidget(self._next_btn)
        self._match_label = QLabel("")
        self._match_label.setStyleSheet("color: #909399; min-width: 72px;")
        search_row.addWidget(self._match_label)
        layout.addLayout(search_row)

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

    def _on_search_changed(self) -> None:
        self._active_match_index = -1
        self._apply_search_highlight()
        if self._match_cursors:
            self._active_match_index = 0
            self._apply_search_highlight()
            self._scroll_to_match(0)

    def _find_next(self) -> None:
        if not self._match_cursors:
            self._apply_search_highlight()
        if not self._match_cursors:
            return
        self._active_match_index = (self._active_match_index + 1) % len(self._match_cursors)
        self._apply_search_highlight()
        self._scroll_to_match(self._active_match_index)

    def _find_prev(self) -> None:
        if not self._match_cursors:
            self._apply_search_highlight()
        if not self._match_cursors:
            return
        self._active_match_index = (self._active_match_index - 1) % len(self._match_cursors)
        self._apply_search_highlight()
        self._scroll_to_match(self._active_match_index)

    def _scroll_to_match(self, index: int) -> None:
        if index < 0 or index >= len(self._match_cursors):
            return
        cursor = QTextCursor(self._match_cursors[index])
        self._content_view.setTextCursor(cursor)
        self._content_view.centerCursor()

    def _apply_search_highlight(self) -> None:
        needle = self._search_edit.text().strip()
        self._match_cursors = []
        if not needle:
            self._content_view.setExtraSelections([])
            self._match_label.setText("")
            return

        doc = self._content_view.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        flags = QTextDocument.FindFlag(0)

        normal_fmt = QTextCharFormat()
        normal_fmt.setBackground(QColor("#fff566"))
        active_fmt = QTextCharFormat()
        active_fmt.setBackground(QColor("#ff9632"))
        active_fmt.setForeground(QColor("#1f1f1f"))

        extra: list[QTextEdit.ExtraSelection] = []
        while True:
            cursor = doc.find(needle, cursor, flags)
            if cursor.isNull():
                break
            self._match_cursors.append(QTextCursor(cursor))
            sel = QTextEdit.ExtraSelection()
            sel.cursor = QTextCursor(cursor)
            sel.format = normal_fmt
            extra.append(sel)

        if not self._match_cursors:
            self._content_view.setExtraSelections([])
            self._match_label.setText("0/0")
            return

        if self._active_match_index < 0:
            self._active_match_index = 0
        elif self._active_match_index >= len(self._match_cursors):
            self._active_match_index = len(self._match_cursors) - 1

        extra[self._active_match_index].format = active_fmt
        self._content_view.setExtraSelections(extra)
        self._match_label.setText(f"{self._active_match_index + 1}/{len(self._match_cursors)}")

    def _reload(self) -> None:
        path = self._engine.log_path
        size = self._engine.log_file_size()
        running_hint = "（引擎运行中，删除已禁用）" if self._engine.is_running else ""
        self._info_label.setText(f"文件：{path}\n大小：{_format_log_size(size)}{running_hint}")
        self._delete_btn.setEnabled(not self._engine.is_running and size > 0)
        if size == 0:
            self._content_view.setPlainText("")
            self._match_cursors = []
            self._active_match_index = -1
            self._match_label.setText("")
            return
        content, _ = self._engine.read_log_file_content()
        self._content_view.setPlainText(content)
        if self._search_edit.text().strip():
            self._on_search_changed()
        else:
            cursor = self._content_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
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

    def __init__(self, runner_dir: Path, repair_kind: RepairKind = "playwright", parent=None) -> None:
        super().__init__(parent)
        self._runner_dir = runner_dir
        self._repair_kind = repair_kind or "playwright"

    def run(self) -> None:
        try:
            repair_fn = (
                repair_runner_dependencies
                if self._repair_kind == "deps"
                else repair_playwright_browsers
            )
            repair_fn(
                self._runner_dir,
                on_output=lambda text: self.log_line.emit(text),
            )
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _RuntimeRepairDialog(QDialog):
    def __init__(self, runner_dir, repair_kind: RepairKind = "playwright", parent=None) -> None:
        super().__init__(parent)
        self._repair_kind = repair_kind or "playwright"
        if self._repair_kind == "deps":
            self.setWindowTitle("安装 Runner 依赖")
            hint = "正在安装 Python 依赖，请稍候（需联网）…"
            done_text = "[完成] 依赖已就绪"
        else:
            self.setWindowTitle("安装 Playwright Chromium")
            hint = "正在安装浏览器，请稍候（约 150MB，需联网）…"
            done_text = "[完成] Chromium 已就绪"
        self._done_text = done_text
        self.resize(560, 320)
        self._runner_dir = runner_dir
        self._worker: _InstallWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(hint))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self._close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        self._close_btn.setEnabled(False)
        layout.addWidget(buttons)

        self._worker = _InstallWorker(runner_dir, repair_kind=self._repair_kind, parent=self)
        self._worker.log_line.connect(self._append)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.start()

    def _append(self, text: str) -> None:
        if text:
            self.log_view.appendPlainText(text)

    def _on_ok(self) -> None:
        self._append(self._done_text)
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
    app_icon = _load_app_icon()
    if app_icon is not None:
        app.setWindowIcon(app_icon)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLESHEET)

    splash = StartupSplash()
    splash.show_centered()
    app.processEvents()

    splash_start = time.monotonic()
    main_window: MainWindow | None = None

    def _open_main_window() -> None:
        nonlocal main_window
        if main_window is None:
            main_window = MainWindow()
        splash.finish()
        main_window.setWindowTitle("BrickCore Runner · 执行器客户端")
        main_window.show()

    def _bootstrap() -> None:
        nonlocal main_window
        main_window = MainWindow()
        elapsed_ms = int((time.monotonic() - splash_start) * 1000)
        remain = max(0, 1200 - elapsed_ms)
        QTimer.singleShot(remain, _open_main_window)

    QTimer.singleShot(0, _bootstrap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
