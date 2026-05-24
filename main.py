"""
main.py 鈥?GitHub Hub 绋嬪簭鍏ュ彛
"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(__file__))

# 打包兼容：PyInstaller 用 _MEIPASS 定位，app 在 _internal 下
import importlib.util as _imp_util
_meipass = getattr(sys, '_MEIPASS', None)
if _meipass and not os.path.exists(os.path.join(_meipass, 'app')):
    _internal = os.path.join(_meipass, '_internal')
    if os.path.exists(_internal):
        sys.path.insert(0, _internal)

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QFont, QPixmap, QPainter, QColor,
    QLinearGradient, QRadialGradient, QPen, QBrush
)

from app.main_window import MainWindow
from app.theme import APP_STYLESHEET


def create_splash() -> QSplashScreen:
    """Create high-quality startup splash screen"""
    W, H = 520, 300
    pix = QPixmap(W, H)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # Background gradient
    bg_grad = QLinearGradient(0, 0, W, H)
    bg_grad.setColorAt(0.0, QColor("#0d1117"))
    bg_grad.setColorAt(0.6, QColor("#161b22"))
    bg_grad.setColorAt(1.0, QColor("#0d1117"))
    painter.setBrush(QBrush(bg_grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, W, H, 16, 16)

    # Glow effect behind logo
    glow = QRadialGradient(W // 2, 110, 80)
    glow.setColorAt(0.0, QColor(31, 111, 235, 60))
    glow.setColorAt(1.0, QColor(31, 111, 235, 0))
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(W // 2 - 80, 30, 160, 160)

    # Border
    pen = QPen(QColor("#21262d"))
    pen.setWidth(1)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(1, 1, W - 2, H - 2, 15, 15)

    # Logo circle background
    cx, cy, cr = W // 2, 108, 44
    logo_grad = QLinearGradient(cx - cr, cy - cr, cx + cr, cy + cr)
    logo_grad.setColorAt(0.0, QColor("#388bfd"))
    logo_grad.setColorAt(1.0, QColor("#1158c7"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(logo_grad))
    painter.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)

    # Logo ring highlight
    highlight_pen = QPen(QColor(255, 255, 255, 30))
    highlight_pen.setWidth(2)
    painter.setPen(highlight_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(cx - cr + 3, cy - cr + 3, (cr - 3) * 2, (cr - 3) * 2)

    # "GH" text
    painter.setPen(QColor("white"))
    f = QFont("Segoe UI", 26, QFont.Weight.Bold)
    painter.setFont(f)
    painter.drawText(cx - cr, cy - cr, cr * 2, cr * 2, Qt.AlignmentFlag.AlignCenter, "GH")

    # Title
    painter.setPen(QColor("#e6edf3"))
    f = QFont("Segoe UI", 22, QFont.Weight.Bold)
    painter.setFont(f)
    painter.drawText(0, 170, W, 36, Qt.AlignmentFlag.AlignCenter, "GitHub Hub")

    # Subtitle
    painter.setPen(QColor("#8b949e"))
    f = QFont("Segoe UI", 11)
    painter.setFont(f)
    painter.drawText(0, 208, W, 24, Qt.AlignmentFlag.AlignCenter, "Open Source Project Manager")

    # Separator line
    sep_pen = QPen(QColor("#21262d"))
    sep_pen.setWidth(1)
    painter.setPen(sep_pen)
    painter.drawLine(W // 2 - 80, 240, W // 2 + 80, 240)

    # Version/signature
    painter.setPen(QColor("#484f58"))
    f = QFont("Segoe UI", 9)
    painter.setFont(f)
    painter.drawText(0, 248, W, 20, Qt.AlignmentFlag.AlignCenter, "v1.0.0  |  Powered by Antigravity")

    # Loading hint
    painter.setPen(QColor("#30363d"))
    f = QFont("Segoe UI", 8)
    painter.setFont(f)
    painter.drawText(0, 272, W, 18, Qt.AlignmentFlag.AlignCenter, "Loading...")

    painter.end()

    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.setStyleSheet("color: #8b949e; font-size: 11px;")
    return splash


def main():
    # 楂?DPI 鏀寔
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("GitHub Hub")
    app.setOrganizationName("Antigravity")
    app.setApplicationVersion("1.0.0")

    # 鈹€鈹€ 鍏ㄥ眬瀛椾綋 鈹€鈹€
    font = QFont("Microsoft YaHei UI", 9)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    # 鈹€鈹€ 鍏ㄥ眬娣辫壊涓婚 鈹€鈹€
    app.setStyleSheet(APP_STYLESHEET)

    # 鈹€鈹€ 鍚姩灞?鈹€鈹€
    splash = create_splash()
    splash.show()
    app.processEvents()

    # 鈹€鈹€ 鍔犺浇涓荤獥鍙?鈹€鈹€
    window = MainWindow()

    # 寤惰繜鏄剧ず涓荤獥鍙ｏ紙璁╁惎鍔ㄥ睆鑷冲皯鏄剧ず 1.8 绉掞級
    def _show():
        splash.finish(window)
        window.show()

    QTimer.singleShot(1800, _show)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
