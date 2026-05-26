"""Voluntary author support dialog."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .utils import get_resource_path


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("支持作者")
        self.setFixedSize(420, 570)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 22)
        layout.setSpacing(12)

        title = QLabel("支持 GitHub Hub")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e6edf3;")
        layout.addWidget(title)

        subtitle = QLabel("如果这个工具节省了你的时间，可以自愿请作者喝杯饮料。")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #aab3d2;")
        layout.addWidget(subtitle)

        qr_label = QLabel()
        qr_label.setFixedSize(300, 300)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #262b40; "
            "border-radius: 8px; color: #68708e;"
        )
        qr_path = Path(get_resource_path("assets/support/payment_qr.png"))
        if qr_path.is_file():
            pixmap = QPixmap(str(qr_path))
            qr_label.setPixmap(
                pixmap.scaled(
                    284, 284,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr_label.setText("作者尚未配置收款码")
        layout.addWidget(qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("打赏完全自愿，不影响软件功能、更新或技术支持。")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #7c85a6;")
        layout.addWidget(hint)

        close_button = QPushButton("关闭")
        close_button.setFixedHeight(38)
        close_button.clicked.connect(self.accept)
        layout.addStretch()
        layout.addWidget(close_button)
