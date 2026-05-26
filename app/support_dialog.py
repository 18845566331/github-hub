"""Voluntary author support dialog."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .utils import get_resource_path


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("支持作者")
        self.setFixedSize(760, 600)
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

        qr_row = QHBoxLayout()
        qr_row.setSpacing(18)
        qr_row.addWidget(self._qr_card("支付宝", "assets/support/alipay_qr.jpg", "#1677ff"))
        qr_row.addWidget(self._qr_card("微信支付", "assets/support/wechat_pay_qr.png", "#07c160"))
        layout.addLayout(qr_row)

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

    def _qr_card(self, name: str, relative_path: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #171926; border: 1px solid #262b40; border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setSpacing(10)

        label = QLabel(name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {color}; border: none;")
        card_layout.addWidget(label)

        qr_label = QLabel()
        qr_label.setFixedSize(300, 350)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #262b40; "
            "border-radius: 6px; color: #68708e;"
        )
        qr_path = Path(get_resource_path(relative_path))
        if qr_path.is_file():
            pixmap = QPixmap(str(qr_path))
            qr_label.setPixmap(
                pixmap.scaled(
                    290, 340,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr_label.setText(f"尚未配置{name}收款码")
        card_layout.addWidget(qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        return card
