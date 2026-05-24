"""
project_list.py — 项目列表侧边栏
显示已克隆的项目，支持搜索和状态标识（含副标题自定义委托渲染）
"""
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QLineEdit, QPushButton,
    QFrame, QStyledItemDelegate, QStyleOptionViewItem, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QRect, QPoint
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPixmap, QFont,
    QFontMetrics, QPen, QBrush, QPainterPath
)

# ── 状态颜色 ──────────────────────────────────────────────
STATUS_COLORS = {
    "ready":         "#7ee787",
    "running":       "#7c4dff",
    "installing":    "#e3b341",
    "not_installed": "#f85149",
    "updating":      "#d2a8ff",
    "unknown":       "#6e7681",
}

STATUS_LABELS = {
    "ready":         "✅ 已就绪",
    "running":       "▶ 运行中",
    "installing":    "⏳ 安装中",
    "not_installed": "⚠ 未安装",
    "updating":      "🔄 更新中",
    "unknown":       "• 未知",
}

# 语言颜色映射（参考 GitHub 配色）
LANG_COLORS = {
    "Python":     "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "C++":        "#f34b7d",
    "C":          "#555555",
    "Java":       "#b07219",
    "Go":         "#00ADD8",
    "Rust":       "#dea584",
    "C#":         "#178600",
    "Ruby":       "#701516",
    "Shell":      "#89e051",
    "HTML":       "#e34c26",
    "CSS":        "#563d7c",
    "Jupyter":    "#DA5B0B",
}

def _make_dot_icon(color: str, size: int = 10) -> QIcon:
    """创建圆点状态图标"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pix)

class ProjectItemDelegate(QStyledItemDelegate):
    """自定义项目列表委托：渲染名称 + 状态标签 + 副标题信息"""

    ITEM_HEIGHT = 72

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ITEM_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = option.rect
        is_selected = bool(option.state & option.state.State_Selected)
        is_hovered  = bool(option.state & option.state.State_MouseOver)

        # ── 背景 ──
        if is_selected:
            bg_color = QColor("#1d2136")
            painter.fillRect(rect, bg_color)
            # 左侧蓝色指示条
            accent_rect = QRect(rect.left(), rect.top(), 3, rect.height())
            painter.fillRect(accent_rect, QColor("#7c4dff"))
        elif is_hovered:
            painter.fillRect(rect, QColor("#171926"))
        else:
            painter.fillRect(rect, QColor("#0f111a"))

        # ── 底部分割线 ──
        pen = QPen(QColor("#191c2b"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(rect.left() + 12, rect.bottom(),
                         rect.right() - 12, rect.bottom())

        # ── 读取数据 ──
        project = index.data(Qt.ItemDataRole.UserRole)
        if not project:
            painter.restore()
            return

        status  = project.get("status", "unknown")
        name    = project.get("name", "未知项目")
        lang    = project.get("language", "")
        stars   = project.get("stars", 0)
        desc    = project.get("description", "")

        dot_color  = STATUS_COLORS.get(status, "#6e7681")
        status_lbl = STATUS_LABELS.get(status, "• 未知")

        left_pad = 16 if is_selected else 13
        x = rect.left() + left_pad
        y = rect.top()
        w = rect.width() - left_pad - 12

        # ── 状态圆点 ──
        dot_size = 8
        dot_x = x
        dot_y = y + 18
        painter.setBrush(QColor(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        # ── 项目名称 ──
        name_font = QFont("Microsoft YaHei UI", 10, QFont.Weight.DemiBold)
        painter.setFont(name_font)
        name_color = QColor("#f8f9fa") if (is_selected or is_hovered) else QColor("#d0d4fc")
        painter.setPen(name_color)
        name_x = dot_x + dot_size + 8
        name_rect = QRect(name_x, y + 10, w - dot_size - 8, 22)
        fm_name = QFontMetrics(name_font)
        name_text = fm_name.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name_text)

        # ── 第二行：状态标签 ──
        sub_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(sub_font)
        painter.setPen(QColor(dot_color))
        sub_y = y + 34
        painter.drawText(QRect(name_x, sub_y, 80, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         status_lbl)

        # ── Stars 标签 ──
        if stars > 0:
            stars_str = f"⭐ {stars/1000:.1f}k" if stars >= 1000 else f"⭐ {stars}"
            painter.setPen(QColor("#e3b341"))
            stars_rect = QRect(name_x + 85, sub_y, 80, 16)
            painter.drawText(stars_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, stars_str)

        # ── 语言标签（右侧角标） ──
        if lang:
            lang_color = QColor(LANG_COLORS.get(lang, "#6e7681"))
            tag_font = QFont("Segoe UI", 8)
            painter.setFont(tag_font)
            fm_tag = QFontMetrics(tag_font)
            tag_w = fm_tag.horizontalAdvance(lang) + 12
            tag_h = 16
            tag_x = rect.right() - tag_w - 10
            tag_y = y + 36
            # 语言点
            painter.setBrush(lang_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(tag_x, tag_y + 4, 7, 7)
            painter.setPen(QColor("#7c85a6"))
            painter.drawText(QRect(tag_x + 10, tag_y, tag_w, tag_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lang)

        # ── 描述文字（第三行，极淡） ──
        if desc:
            desc_font = QFont("Microsoft YaHei UI", 8)
            painter.setFont(desc_font)
            painter.setPen(QColor("#484f58"))
            fm_desc = QFontMetrics(desc_font)
            desc_text = fm_desc.elidedText(desc, Qt.TextElideMode.ElideRight, w - 10)
            painter.drawText(QRect(name_x, y + 50, w - 10, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, desc_text)

        painter.restore()

class ProjectItem(QListWidgetItem):
    """项目列表条目（数据存储）"""

    def __init__(self, project_data: dict):
        super().__init__()
        self.project_data = project_data
        self.setData(Qt.ItemDataRole.UserRole, project_data)
        self.setSizeHint(QSize(0, ProjectItemDelegate.ITEM_HEIGHT))
        # 保持 tooltip
        self.setToolTip(project_data.get("description", ""))

class ProjectListPanel(QWidget):
    """项目列表侧边栏面板"""

    project_selected = Signal(dict)
    add_project_clicked = Signal()
    projects_reordered = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectListPanel")
        self._all_projects: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部标题栏 ──
        header = QFrame()
        header.setObjectName("panel_header")
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QFrame#panel_header {
                background: #161b22;
                border-bottom: 1px solid #21262d;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        title_lbl = QLabel("📁  项目列表")
        title_lbl.setStyleSheet(
            "color: #f8f9fa; font-size: 13px; font-weight: 600;"
        )
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        self.btn_add = QPushButton("＋")
        self.btn_add.setFixedSize(28, 28)
        self.btn_add.setToolTip("添加 GitHub 项目 (Ctrl+N)")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #1f6feb; color: white; border: none;
                border-radius: 6px; font-size: 15px; font-weight: bold;
            }
            QPushButton:hover { background: #388bfd; }
            QPushButton:pressed { background: #1158c7; }
        """)
        self.btn_add.clicked.connect(self.add_project_clicked.emit)
        header_layout.addWidget(self.btn_add)
        layout.addWidget(header)

        # ── 搜索框（由 add_search_bar 增强） ──
        self.search_container = QWidget()
        self.search_container.setStyleSheet("border-bottom: 1px solid #21262d;")
        self.search_container_layout = QHBoxLayout(self.search_container)
        self.search_container_layout.setContentsMargins(8, 6, 8, 6)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍  搜索项目...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(30)
        self.search_edit.setStyleSheet("""
            QLineEdit {
                border-radius: 6px;
                padding: 0 10px; font-size: 12px;
            }
        """)
        self.search_edit.textChanged.connect(self._on_search)
        self.search_container_layout.addWidget(self.search_edit)
        layout.addWidget(self.search_container)

        # ── 项目列表 ──
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(0)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setItemDelegate(ProjectItemDelegate(self.list_widget))
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 0;
            }
        """)
        layout.addWidget(self.list_widget, 1)

        # ── 底部统计 ──
        self.status_label = QLabel("0 个项目")
        self.status_label.setStyleSheet("""
            color: #7c85a6; font-size: 11px; padding: 5px 12px;
            border-top: 1px solid #21262d;
        """)
        self.status_label.setFixedHeight(26)
        layout.addWidget(self.status_label)

    def load_projects(self, projects: list[dict]):
        self._all_projects = projects
        try:
            self._apply_filters()

        except RuntimeError:
            pass
    def _render_list(self, projects: list[dict]):
        try:
            self.list_widget.clear()
        except RuntimeError:
            return
        for p in projects:
            self._add_project_item(p)

    def _filter_projects(self, text: str):
        text = text.lower().strip()
        if not text:
            self._render_list(self._all_projects)
            return
        filtered = [p for p in self._all_projects
                    if text in p.get("name", "").lower()
                    or text in p.get("description", "").lower()
                    or text in p.get("language", "").lower()]
        self._render_list(filtered)

    def _on_selection_changed(self, current: QListWidgetItem, previous):
        if current and isinstance(current, ProjectItem):
            self.project_selected.emit(current.project_data)

    def update_project_status(self, project_id: str, status: str):
        for proj in self._all_projects:
            if proj.get("id") == project_id:
                proj["status"] = status
                break
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if isinstance(item, ProjectItem) and item.project_data.get("id") == project_id:
                item.project_data["status"] = status
                item.setData(Qt.ItemDataRole.UserRole, item.project_data)
                # 强制重绘该条目
                self.list_widget.update(self.list_widget.indexFromItem(item))
                break

    def get_selected_project(self):
        """获取当前选中的项目信息"""
        try:
            item = self.list_widget.currentItem()
        except RuntimeError:
            return None
        if item and isinstance(item, ProjectItem):
            return item.project_data
        return None
    def select_project_by_id(self, project_id: str):
        try:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if isinstance(item, ProjectItem) and item.project_data.get("id") == project_id:
                    self.list_widget.setCurrentItem(item)
                    break
        except RuntimeError:
            pass
# === NEW FEATURES: Search, Filter, Tags, Drag-Drop ===

    def add_search_bar(self):
        """Add filter combo to the search bar."""
        try:
            from PySide6.QtWidgets import QComboBox
            self.filter_combo = QComboBox()
            self.filter_combo.addItems(["全部", "运行中", "就绪", "安装中", "未安装", "Python", "Node.js", "Go", "Rust"])
            self.filter_combo.currentTextChanged.connect(self._on_filter)
            
            self.filter_combo.setFixedWidth(120)
            if hasattr(self, 'search_container_layout'):
                self.search_container_layout.addWidget(self.filter_combo)
            self.search_bar = getattr(self, 'search_container', None)
        except Exception:
            pass

    def _on_search(self, text):
        """Filter project list by search text."""
        self._search_text = text.lower()
        self._apply_filters()

    def _on_filter(self, filter_text):
        """Filter by status or language."""
        self._filter_text = filter_text
        self._apply_filters()

    def _apply_filters(self):
        """Apply search and filter to project list."""
        try:
            self.list_widget.clear()
        except RuntimeError:
            return
        for p in getattr(self, "_all_projects", []):
            name = p.get("name", "").lower()
            lang = p.get("language", "") or p.get("lang", "")
            status = p.get("status", "")
            tags = p.get("tags", [])
            search_text = getattr(self, "_search_text", "").lower()
            filter_text = getattr(self, "_filter_text", "全部")
            
            # Search filter
            if search_text and search_text not in name and search_text not in " ".join(tags).lower():
                continue
            # Status/language filter
            if filter_text != "全部":
                f_lower = filter_text.lower()
                if f_lower in ["running", "ready", "installing", "not_installed", "unknown", "updating"]:
                    if status.lower() != f_lower:
                        continue
                else:
                    if lang.lower() != f_lower:
                        continue
            self._add_project_item(p)

    def _add_project_item(self, project):
        """Add a single project item."""
        try:
            item = ProjectItem(project)
            self.list_widget.addItem(item)
        except RuntimeError:
            pass
    def _get_color(self, hex_color):
        """Convert hex color to QColor."""
        from PySide6.QtGui import QColor
        hex_color = hex_color.lstrip("#")
        return QColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    def enable_drag_drop(self):
        """Enable drag-drop reordering of projects."""
        from PySide6.QtWidgets import QAbstractItemView
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        try:
            self.list_widget.model().rowsMoved.connect(self._on_order_changed)
        except:
            pass
    def _on_order_changed(self):
        """Save new project order after drag-drop."""
        new_order = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            pid = item.data(32)
            for p in getattr(self, "_all_projects", []):
                if p.get("id") == pid:
                    new_order.append(p)
                    break
        if new_order:
            self._all_projects = new_order
            self.projects_reordered.emit(new_order)

