"""BrickCore Runner 客户端全局样式"""

APP_STYLESHEET = """
QMainWindow, QWidget#centralRoot {
    background-color: #f0f2f5;
}

QLabel#appTitle {
    color: #1f2937;
    font-size: 18px;
    font-weight: 700;
}

QLabel#appSubtitle {
    color: #6b7280;
    font-size: 11px;
}

QLabel#versionBadge {
    background-color: #fff7ed;
    color: #c2410c;
    border: 1px solid #fed7aa;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QSplitter::handle {
    background-color: #e5e7eb;
    height: 4px;
    margin: 4px 0;
    border-radius: 2px;
}

QSplitter::handle:hover {
    background-color: #fdba74;
}

QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-top: 18px;
    padding: 22px 14px 14px 14px;
    font-weight: 600;
    color: #374151;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #111827;
}

QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #fafafa;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: #fdba74;
}

QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #ea580c;
    background-color: #ffffff;
}

QPushButton {
    background-color: #ffffff;
    color: #374151;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #f9fafb;
    border-color: #9ca3af;
}

QPushButton:pressed {
    background-color: #f3f4f6;
}

QPushButton#primaryBtn {
    background-color: #ea580c;
    color: #ffffff;
    border: 1px solid #c2410c;
}

QPushButton#primaryBtn:hover {
    background-color: #f97316;
}

QPushButton#primaryBtn:pressed {
    background-color: #c2410c;
}

QPushButton#dangerBtn {
    background-color: #fef2f2;
    color: #b91c1c;
    border: 1px solid #fecaca;
}

QPushButton#dangerBtn:hover {
    background-color: #fee2e2;
}

QPushButton:disabled {
    color: #9ca3af;
    background-color: #f3f4f6;
    border-color: #e5e7eb;
}

QLabel#statusBanner {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 10px 14px;
    color: #374151;
}

QLabel#healthPill {
    background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 6px 12px;
    color: #4b5563;
    font-size: 12px;
}

QLabel#healthPill[health="ok"] {
    background-color: #ecfdf5;
    border-color: #a7f3d0;
    color: #047857;
}

QLabel#healthPill[health="bad"] {
    background-color: #fef2f2;
    border-color: #fecaca;
    color: #b91c1c;
}

QLabel#healthPill[health="idle"] {
    background-color: #f9fafb;
    border-color: #e5e7eb;
    color: #6b7280;
}

QPlainTextEdit#logView {
    background-color: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    border-radius: 10px;
    font-family: Consolas, "Cascadia Mono", "Microsoft YaHei UI", monospace;
    font-size: 12px;
    padding: 8px;
}

QWidget#headerCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #fff7ed, stop:0.55 #ffffff, stop:1 #fff7ed);
    border: 1px solid #fed7aa;
    border-radius: 12px;
}

QGroupBox#recordingPanel {
    margin-top: 12px;
    min-width: 260px;
}

QLabel#recordingStatus {
    color: #374151;
    font-size: 12px;
}

QLabel#recordingStats {
    color: #6b7280;
    font-size: 11px;
}

QListWidget#recordingActionsList {
    background-color: #fafafa;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    font-size: 11px;
}
"""
