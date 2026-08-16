"""搬砖加载动画（QPainter）与启动闪屏。"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget


def _splash_app_icon() -> QIcon | None:
    here = Path(__file__).resolve().parent.parent
    candidates = [
        here / "icon.ico",
        here.parent / "runner" / "icon.ico",
        Path(sys.executable).resolve().parent / "icon.ico",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "icon.ico")
    for path in candidates:
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return None


def _make_pen(
    color: QColor,
    width: float = 1.0,
    cap: Qt.PenCapStyle = Qt.PenCapStyle.SquareCap,
) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(cap)
    pen.setStyle(Qt.PenStyle.SolidLine)
    return pen


class BrickLoaderWidget(QWidget):
    """循环播放：工人从砖堆取砖 → 搬到右侧堆叠。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(300, 170)
        self._phase = 0.0
        self._caption = "搬砖中，请稍候…"
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._tick)

    def set_caption(self, text: str) -> None:
        self._caption = text.strip() or "搬砖中，请稍候…"
        self.update()

    def start_animation(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop_animation(self) -> None:
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    @staticmethod
    def _draw_brick(p: QPainter, rect: QRectF, shade: float = 1.0) -> None:
        top = QColor(
            min(255, int(251 * shade)),
            min(255, int(146 * shade)),
            min(255, int(60 * shade)),
        )
        side = QColor(
            min(255, int(194 * shade)),
            min(255, int(65 * shade)),
            min(255, int(12 * shade)),
        )
        p.setPen(_make_pen(QColor(154, 52, 18), 1.2))
        p.setBrush(QBrush(top))
        p.drawRoundedRect(rect, 3, 3)
        side_rect = QRectF(rect.right() - 6, rect.top() + 4, 6, rect.height() - 4)
        p.setBrush(QBrush(side))
        p.drawRect(side_rect)
        p.setPen(_make_pen(QColor(255, 255, 255, 70), 1.0))
        mid_y = rect.center().y()
        p.drawLine(int(rect.left() + 3), int(mid_y), int(rect.right() - 8), int(mid_y))

    @staticmethod
    def _draw_worker(p: QPainter, x: float, y: float, carry: bool) -> None:
        body_pen = _make_pen(QColor(55, 65, 81), 2.4, Qt.PenCapStyle.RoundCap)
        p.setBrush(QBrush(QColor(249, 115, 22)))
        p.setPen(_make_pen(QColor(194, 65, 12), 1.5))
        p.drawEllipse(QPointF(x, y - 28), 11, 9)
        p.setPen(body_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y - 18), 7, 7)
        p.drawLine(int(x), int(y - 11), int(x), int(y + 16))
        p.drawLine(int(x), int(y + 16), int(x - 10), int(y + 34))
        p.drawLine(int(x), int(y + 16), int(x + 10), int(y + 34))
        if carry:
            p.drawLine(int(x), int(y - 2), int(x + 18), int(y - 8))
            p.drawLine(int(x), int(y - 2), int(x - 14), int(y + 2))
        else:
            p.drawLine(int(x), int(y - 2), int(x + 12), int(y + 6))
            p.drawLine(int(x), int(y - 2), int(x - 12), int(y + 6))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if not p.isActive():
            return
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, QColor(255, 247, 237))
            grad.setColorAt(1, QColor(255, 255, 255))
            p.fillRect(self.rect(), grad)

            ground_y = 132.0
            p.setPen(_make_pen(QColor(209, 213, 219), 1.0))
            p.drawLine(20, int(ground_y), self.width() - 20, int(ground_y))

            for i, (bx, by, w, h) in enumerate(
                (
                    (36, ground_y - 18, 34, 16),
                    (52, ground_y - 34, 34, 16),
                    (28, ground_y - 50, 34, 16),
                )
            ):
                self._draw_brick(p, QRectF(bx, by, w, h), shade=0.92 + i * 0.02)

            stacked = int((self._phase * 3) % 4)
            for i in range(stacked):
                self._draw_brick(
                    p,
                    QRectF(210, ground_y - 18 - i * 16, 34, 16),
                    shade=1.0 - i * 0.03,
                )

            if self._phase < 0.55:
                t = self._phase / 0.55
                wx = 70 + t * 120
                carry = True
            else:
                t = (self._phase - 0.55) / 0.45
                wx = 190 - t * 120
                carry = False

            wy = ground_y - 34 + math.sin(self._phase * math.pi * 4) * 1.5
            self._draw_worker(p, wx, wy, carry=carry)

            if carry:
                brick_x = wx + 8
                brick_y = wy - 22 + math.sin(self._phase * math.pi * 6) * 1.0
                self._draw_brick(p, QRectF(brick_x, brick_y, 30, 14))

            p.setPen(QColor(107, 114, 128))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(
                QRectF(0, ground_y + 8, self.width(), 24),
                Qt.AlignmentFlag.AlignHCenter,
                self._caption,
            )
        finally:
            p.end()


class StartupSplash(QWidget):
    """客户端启动时的搬砖动画窗口（非「上线」流程）。"""

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(380, 280)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        splash_icon = _splash_app_icon()
        if splash_icon is not None:
            self.setWindowIcon(splash_icon)
        self.setStyleSheet(
            """
            StartupSplash, QWidget#splashRoot {
                background-color: #ffffff;
                border: 1px solid #fed7aa;
                border-radius: 16px;
            }
            """
        )

        root = QFrame(self)
        root.setObjectName("splashRoot")
        root.setGeometry(0, 0, 380, 280)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("BrickCore Runner")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #1f2937; font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self._loader = BrickLoaderWidget(root)
        self._loader.set_caption("正在启动执行器…")
        layout.addWidget(self._loader, alignment=Qt.AlignmentFlag.AlignCenter)

        self._message = QLabel("加载界面与运行环境，请稍候")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._message)

    def show_centered(self) -> None:
        self._loader.start_animation()
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        self.show()
        self.raise_()
        QApplication.processEvents()

    def finish(self) -> None:
        self._loader.stop_animation()
        self.close()
