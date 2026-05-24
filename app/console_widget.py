"""
console_widget.py — 控制台输出组件
带颜色高亮、自动滚动、清空和复制功能
"""
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QSizePolicy, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont,
    QTextDocument
)


class ConsoleWidget(QWidget):
    command_sent = Signal(str)
    """
    控制台组件：显示彩色日志输出
    线程安全：通过 Signal 在主线程更新
    """

    append_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.append_requested.connect(self._do_append, Qt.ConnectionType.QueuedConnection)
        self._interactive = False

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar.setObjectName("console_toolbar")
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("""
            QWidget#console_toolbar {
                border-bottom: 1px solid #21262d;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 0, 8, 0)

        self.label = QLabel("📟 控制台输出")
        self.label.setStyleSheet(
            "color: #7c85a6; font-size: 12px; font-weight: 600;"
        )
        toolbar_layout.addWidget(self.label)
        toolbar_layout.addStretch()

        _btn_style = """
            QPushButton {
                border-radius: 4px; font-size: 11px; padding: 0;
            }
        """

        self.btn_copy = QPushButton("📋 复制")
        self.btn_copy.setFixedSize(60, 24)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet(_btn_style)
        self.btn_copy.clicked.connect(self._copy_all)

        self.btn_clear = QPushButton("🗑 清空")
        self.btn_clear.setFixedSize(60, 24)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(_btn_style)
        self.btn_clear.clicked.connect(self.clear)

        toolbar_layout.addWidget(self.btn_copy)
        toolbar_layout.addWidget(self.btn_clear)
        layout.addWidget(toolbar)

        # 文本区域
        self.text_edit = QPlainTextEdit()
        self.text_edit.setObjectName("console_output")
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)
        self.text_edit.setStyleSheet("""
            QPlainTextEdit#console_output {
                color: #00e676;
                border: none;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 12px;
                padding: 8px 12px;
            }
        """)
        layout.addWidget(self.text_edit)

        # command input bar
        input_bar = QWidget()
        input_bar.setObjectName("console_input_bar")
        input_bar.setFixedHeight(40)
        input_bar.setStyleSheet("""
            QWidget#console_input_bar {
                border-top: 1px solid #21262d;
            }
        """)
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(8, 4, 8, 4)
        input_layout.setSpacing(6)

        prompt = QLabel("$ ")
        prompt.setStyleSheet("color: #00e676; font-size: 13px; font-weight: bold;")
        prompt.setFixedWidth(20)
        input_layout.addWidget(prompt)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入命令... (Enter 发送)")
        self.input_edit.setFixedHeight(30)
        self.input_edit.setEnabled(False)
        self.input_edit.setStyleSheet("""
            QLineEdit {
                border-radius: 5px; padding: 0 8px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
            }
        """)
        self.input_edit.returnPressed.connect(self._on_input_enter)
        input_layout.addWidget(self.input_edit, 1)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedSize(50, 30)
        self.btn_send.setEnabled(False)
        self.btn_send.setStyleSheet("""
            QPushButton {
                border-radius: 5px; font-size: 12px; font-weight: 600;
            }
        """)
        self.btn_send.clicked.connect(self._on_input_enter)
        input_layout.addWidget(self.btn_send)

        layout.addWidget(input_bar)

    # ── 颜色规则 ──
    _COLORS = {
        "[ERROR]":   "#f85149",
        "[WARN]":    "#e3b341",
        "[WARNING]": "#e3b341",
        "[INFO]":    "#58a6ff",
        "[SUCCESS]": "#7ee787",
        "[进程已退出]": "#8b949e",
        "Requirement already": "#6e7681",
        "Successfully installed": "#7ee787",
        "error":     "#f85149",
        "Error":     "#f85149",
        "warning":   "#e3b341",
        "Warning":   "#e3b341",
    }

    def _get_color(self, line: str) -> QColor:
        for keyword, color in self._COLORS.items():
            if keyword in line:
                return QColor(color)
        return QColor("#c9d1d9")  # 默认浅灰

    def append_line(self, line: str):
        """线程安全地追加一行日志"""
        self.append_requested.emit(line)

    def append_line_direct(self, line: str):
        """直接追加（主线程使用）"""
        self._do_append(line)

    def _do_append(self, line: str):
        # 移除终端 ANSI 颜色转义字符
        line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
        color = self._get_color(line)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.setCharFormat(fmt)
        cursor.insertText(line + "\n")
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()

    def clear(self):
        self.text_edit.clear()

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.text_edit.toPlainText())

    def set_label(self, text: str):
        self.label.setText(text)

    def set_interactive(self, enabled: bool):
        """切换交互模式"""
        self._interactive = enabled
        self.input_edit.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)
        if enabled:
            self.input_edit.setFocus()
        else:
            self.input_edit.clear()

    def _on_input_enter(self):
        text = self.input_edit.text().strip()
        if not text or not self._interactive:
            return
        self.append_line_direct(f"$ {text}")
        self.command_sent.emit(text)
        self.input_edit.clear()
