"""
code_viewer.py — 代码浏览器
文件树 + 带语法高亮的代码查看器
"""
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QLabel, QPushButton, QFileIconProvider
)
from PySide6.QtCore import Qt, QFileInfo
from PySide6.QtGui import (
    QFont, QColor, QSyntaxHighlighter, QTextCharFormat
)
import re


# ─── 语法高亮 ──────────────────────────────────────────────

class PythonHighlighter(QSyntaxHighlighter):
    """Python 语法高亮"""

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        def add(pattern, color, bold=False, italic=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if bold: fmt.setFontWeight(700)
            if italic: fmt.setFontItalic(True)
            self.rules.append((re.compile(pattern), fmt))

        # 关键字
        keywords = (r"\b(?:False|None|True|and|as|assert|async|await|break|class|"
                    r"continue|def|del|elif|else|except|finally|for|from|global|if|"
                    r"import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|"
                    r"while|with|yield)\b")
        add(keywords, "#ff7b72", bold=True)

        # 内置函数/类型
        builtins = (r"\b(?:print|len|range|int|str|float|list|dict|set|tuple|"
                    r"bool|type|isinstance|hasattr|getattr|setattr|open|super|"
                    r"enumerate|zip|map|filter|sorted|reversed|any|all|abs|"
                    r"max|min|sum|round|input|repr|format|vars|dir)\b")
        add(builtins, "#79c0ff")

        # 装饰器
        add(r"@\w+", "#d2a8ff")

        # 字符串（双引号）
        add(r'"[^"\\]*(?:\\.[^"\\]*)*"', "#a5d6ff")
        # 字符串（单引号）
        add(r"'[^'\\]*(?:\\.[^'\\]*)*'", "#a5d6ff")
        # 三引号字符串（近似处理）
        add(r'""".*?"""', "#a5d6ff")
        add(r"'''.*?'''", "#a5d6ff")

        # 数字
        add(r"\b\d+\.?\d*\b", "#79c0ff")

        # 注释
        add(r"#[^\n]*", "#8b949e", italic=True)

        # 类名（PascalCase）
        add(r"\bclass\s+(\w+)", "#ffa657")
        add(r"\b[A-Z][a-zA-Z0-9_]*\b", "#ffa657")

        # self
        add(r"\bself\b", "#ff7b72", italic=True)

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class JsonHighlighter(QSyntaxHighlighter):
    """JSON 语法高亮"""

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        def add(pattern, color):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.rules.append((re.compile(pattern), fmt))

        add(r'"[^"]*"\s*:', "#79c0ff")       # key
        add(r':\s*"[^"]*"', "#a5d6ff")        # string value
        add(r'\b(?:true|false|null)\b', "#ff7b72")
        add(r'\b\d+\.?\d*\b', "#f2cc60")

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class GenericHighlighter(QSyntaxHighlighter):
    """通用高亮（YAML/TOML/Markdown 等）"""

    def __init__(self, document, lang=""):
        super().__init__(document)
        self.rules = []
        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#8b949e"))
        fmt_comment.setFontItalic(True)
        fmt_string = QTextCharFormat()
        fmt_string.setForeground(QColor("#a5d6ff"))
        fmt_key = QTextCharFormat()
        fmt_key.setForeground(QColor("#79c0ff"))

        if lang in ("yaml", "yml"):
            self.rules = [
                (re.compile(r"^\s*#.*"), fmt_comment),
                (re.compile(r"^\s*\w[\w-]*\s*:"), fmt_key),
                (re.compile(r'"[^"]*"'), fmt_string),
                (re.compile(r"'[^']*'"), fmt_string),
            ]
        elif lang in ("toml",):
            self.rules = [
                (re.compile(r"#[^\n]*"), fmt_comment),
                (re.compile(r'^\[.*\]'), fmt_key),
                (re.compile(r'"[^"]*"'), fmt_string),
            ]
        elif lang in ("md", "markdown"):
            fmt_h = QTextCharFormat()
            fmt_h.setForeground(QColor("#58a6ff"))
            fmt_h.setFontWeight(700)
            self.rules = [
                (re.compile(r"^#{1,6}\s.*"), fmt_h),
                (re.compile(r"`[^`]+`"), fmt_string),
            ]

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def get_highlighter(ext: str, document):
    ext = ext.lower().lstrip(".")
    if ext == "py":
        return PythonHighlighter(document)
    if ext == "json":
        return JsonHighlighter(document)
    if ext in ("yaml", "yml", "toml", "md", "markdown"):
        return GenericHighlighter(document, ext)
    return None


# ─── 文件树 ────────────────────────────────────────────────

IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
               "env", ".env", "dist", "build", "eggs", ".eggs",
               ".pytest_cache", ".mypy_cache", ".tox", "htmlcov"}
IGNORE_EXTS = {".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe",
               ".bin", ".dat", ".db", ".sqlite", ".jpg", ".jpeg",
               ".png", ".gif", ".ico", ".svg", ".bmp", ".webp",
               ".mp4", ".avi", ".mp3", ".wav", ".zip", ".tar", ".gz"}


def build_file_tree(root_dir: str, parent_item: QTreeWidgetItem,
                    max_depth: int = 4, depth: int = 0):
    if depth >= max_depth:
        return
    try:
        entries = sorted(os.scandir(root_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError:
        return
    for entry in entries:
        if entry.name.startswith(".") and entry.name not in (".gitignore", ".env.example"):
            if entry.is_dir():
                continue
        if entry.is_dir() and entry.name in IGNORE_DIRS:
            continue
        if entry.is_file():
            ext = Path(entry.name).suffix.lower()
            if ext in IGNORE_EXTS:
                continue

        item = QTreeWidgetItem(parent_item)
        item.setText(0, entry.name)
        item.setData(0, Qt.ItemDataRole.UserRole, entry.path)

        if entry.is_dir():
            item.setIcon(0, QFileIconProvider().icon(QFileIconProvider.IconType.Folder))
            build_file_tree(entry.path, item, max_depth, depth + 1)
        else:
            item.setIcon(0, QFileIconProvider().icon(QFileInfo(entry.path)))


# ─── 主组件 ────────────────────────────────────────────────

class CodeViewer(QWidget):
    """文件树 + 代码查看器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧文件树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(180)
        self.tree.setMaximumWidth(320)
        self.tree.setStyleSheet("""
            QTreeWidget { border: none; border-right: 1px solid #21262d;
                font-size: 12px; outline: none; }
            QTreeWidget::item { padding: 3px 0; border: none; }
        """)
        self.tree.itemClicked.connect(self._on_file_clicked)
        splitter.addWidget(self.tree)

        # 右侧代码编辑器
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 文件路径标签
        self.path_label = QLabel("— 请从左侧选择文件 —")
        self.path_label.setStyleSheet("""
            font-size: 11px;
            padding: 4px 10px;
            border-bottom: 1px solid #21262d;
        """)
        right_layout.addWidget(self.path_label)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        font = QFont("Consolas", 11)
        font.setFixedPitch(True)
        self.editor.setFont(font)
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                border: none;
            }
        """)
        # 设置 Tab 宽度为 4 个空格
        from PySide6.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        self.editor.setTabStopDistance(4 * metrics.horizontalAdvance(' '))
        right_layout.addWidget(self.editor)

        splitter.addWidget(right)
        splitter.setSizes([220, 600])
        layout.addWidget(splitter)

    def load_project(self, project_dir: str):
        """加载项目文件树"""
        self.tree.clear()
        self.editor.clear()
        self.path_label.setText("— 请从左侧选择文件 —")
        self._highlighter = None
        if not project_dir or not os.path.isdir(project_dir):
            return

        root_name = Path(project_dir).name
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, f"📁 {root_name}")
        root_item.setData(0, Qt.ItemDataRole.UserRole, None)
        root_item.setExpanded(True)

        build_file_tree(project_dir, root_item)

    def _on_file_clicked(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None or os.path.isdir(path):
            return
        self._load_file(path)

    def _load_file(self, path: str):
        try:
            size = os.path.getsize(path)
            if size > 2 * 1024 * 1024:  # > 2MB 不加载
                self.editor.setPlainText(f"[文件过大，跳过预览: {size//1024}KB]")
                return

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            self._highlighter = None
            self.editor.setPlainText(content)
            ext = Path(path).suffix
            self._highlighter = get_highlighter(ext, self.editor.document())
            self.path_label.setText(f"📄 {path}")
        except Exception as e:
            self.editor.setPlainText(f"[无法读取文件: {e}]")
