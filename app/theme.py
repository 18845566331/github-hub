"""
theme.py - Global Theme & Style Constants
Unified UI colors, fonts, and style sheet.
"""

# ══════════════════════════════════════════════════════
# Color Palette — refined for better contrast & harmony
# ══════════════════════════════════════════════════════

# Backgrounds
BG_DEEP      = "#080a10"   # Deepest bg (main content)
BG_BASE      = "#0f111a"   # Secondary bg (sidebar, titlebar)
BG_CARD      = "#171926"   # Card/control bg
BG_HOVER     = "#212438"   # Hover bg
BG_SELECTED  = "#1d2136"   # Selected bg

# Borders
BORDER_SUBTLE = "#191c2b"  # Subtle border
BORDER_MUTED  = "#262b40"  # Normal border
BORDER_FOCUS  = "#7c4dff"  # Focus border

# Text
TEXT_PRIMARY   = "#f8f9fa" # Primary text
TEXT_SECONDARY = "#d0d4fc" # Secondary text
TEXT_MUTED     = "#7c85a6" # Muted text
TEXT_FAINT     = "#5c6280" # Very faint text
TEXT_DISABLED  = "#393d54" # Disabled text

# Accents
ACCENT_BLUE    = "#7c4dff" # Primary accent (purple-blue)
ACCENT_BLUE_DK = "#536dfe" # Deep blue accent
ACCENT_BLUE_LT = "#8c9eff" # Light blue
ACCENT_GREEN   = "#00e676" # Success / ready
ACCENT_YELLOW  = "#ffd600" # Warning / installing
ACCENT_RED     = "#ff1744" # Error / not installed
ACCENT_PURPLE  = "#d500f9" # Updating


# ══════════════════════════════════════════════════════
# Global QSS Stylesheet
# ══════════════════════════════════════════════════════
APP_STYLESHEET = f"""

/* ════════════════════════════════════════════════════════════
   GLOBAL BASE
   ════════════════════════════════════════════════════════════ */
QWidget {{
    background: {BG_DEEP};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Microsoft YaHei UI", -apple-system, sans-serif;
    font-size: 13px;
}}

/* ════════════════════════════════════════════════════════════
   MENUBAR
   ════════════════════════════════════════════════════════════ */
QMenuBar {{
    background: {BG_BASE};
    color: {TEXT_SECONDARY};
    border-bottom: 1px solid {BORDER_SUBTLE};
    padding: 3px 8px;
    font-size: 13px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 14px;
    border-radius: 6px;
    font-weight: 500;
}}
QMenuBar::item:selected {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
}}
QMenuBar::item:pressed {{
    background: {ACCENT_BLUE_DK};
    color: white;
}}

/* ════════════════════════════════════════════════════════════
   MENU
   ════════════════════════════════════════════════════════════ */
QMenu {{
    background: {BG_BASE};
    border: 1px solid {BORDER_MUTED};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 24px 7px 14px;
    border-radius: 5px;
    color: {TEXT_SECONDARY};
}}
QMenu::item:selected {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QMenu::item:disabled {{
    color: {TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_SUBTLE};
    margin: 5px 8px;
}}

/* ════════════════════════════════════════════════════════════
   DIALOG
   ════════════════════════════════════════════════════════════ */
QDialog {{
    background: {BG_DEEP};
}}

/* ════════════════════════════════════════════════════════════
   MESSAGE BOX
   ════════════════════════════════════════════════════════════ */
QMessageBox {{
    background: {BG_BASE};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
    min-width: 280px;
    font-size: 13px;
}}
QMessageBox QPushButton {{
    background: {BG_CARD};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    padding: 6px 20px;
    min-width: 76px;
    font-weight: 500;
}}
QMessageBox QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT_BLUE};
    color: {TEXT_PRIMARY};
}}
QMessageBox QPushButton:default {{
    background: {ACCENT_BLUE_DK};
    border-color: {ACCENT_BLUE_DK};
    color: white;
    font-weight: 600;
}}

/* ════════════════════════════════════════════════════════════
   BUTTONS — modern, consistent, with subtle transitions
   ════════════════════════════════════════════════════════════ */
QPushButton {{
    background: {BG_CARD};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    padding: 6px 16px;
    font-weight: 500;
    min-height: 28px;
}}
QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT_BLUE};
    color: {TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background: {ACCENT_BLUE_DK};
    border-color: {ACCENT_BLUE_DK};
    color: white;
}}
QPushButton:disabled {{
    background: {BG_BASE};
    border-color: {BORDER_SUBTLE};
    color: {TEXT_DISABLED};
}}

/* Primary action button */
QPushButton[class="primary"],
QPushButton#primaryBtn {{
    background: {ACCENT_BLUE_DK};
    border: none;
    color: white;
    font-weight: 600;
}}
QPushButton[class="primary"]:hover,
QPushButton#primaryBtn:hover {{
    background: {ACCENT_BLUE};
}}
QPushButton[class="primary"]:pressed,
QPushButton#primaryBtn:pressed {{
    background: {ACCENT_BLUE_DK};
}}

/* Success/install button */
QPushButton[class="success"] {{
    background: #1a6b3c;
    border: 1px solid #238636;
    color: white;
    font-weight: 600;
}}
QPushButton[class="success"]:hover {{
    background: #238636;
}}

/* Danger button */
QPushButton[class="danger"] {{
    background: #6b1a2a;
    border: 1px solid #da3633;
    color: white;
}}
QPushButton[class="danger"]:hover {{
    background: #da3633;
}}

/* ════════════════════════════════════════════════════════════
   TOOLBAR
   ════════════════════════════════════════════════════════════ */
QToolBar {{
    background: {BG_BASE};
    border-bottom: 1px solid {BORDER_SUBTLE};
    spacing: 4px;
    padding: 4px 8px;
}}
QToolBar::separator {{
    width: 1px;
    background: {BORDER_SUBTLE};
    margin: 4px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    padding: 4px 10px;
    font-weight: 500;
}}
QToolButton:hover {{
    background: {BG_CARD};
    border-color: {BORDER_MUTED};
    color: {TEXT_PRIMARY};
}}
QToolButton:pressed {{
    background: {BG_HOVER};
}}
QToolButton:disabled {{
    color: {TEXT_DISABLED};
}}

/* ════════════════════════════════════════════════════════════
   INPUT FIELDS
   ════════════════════════════════════════════════════════════ */
QLineEdit {{
    background: {BG_CARD};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 6px 12px;
    selection-background-color: {ACCENT_BLUE_DK};
    min-height: 28px;
}}
QLineEdit:focus {{
    border-color: {ACCENT_BLUE};
    background: {BG_BASE};
}}
QLineEdit:hover {{
    border-color: {TEXT_FAINT};
}}
QLineEdit:disabled {{
    background: {BG_BASE};
    color: {TEXT_DISABLED};
}}

/* ════════════════════════════════════════════════════════════
   SPINBOX (numeric input)
   ════════════════════════════════════════════════════════════ */
QSpinBox {{
    background: {BG_CARD};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 8px;
    min-height: 28px;
}}
QSpinBox:focus {{
    border-color: {ACCENT_BLUE};
}}

/* ════════════════════════════════════════════════════════════
   COMBOBOX
   ════════════════════════════════════════════════════════════ */
QComboBox {{
    background: {BG_CARD};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 5px 12px;
    min-height: 26px;
}}
QComboBox:hover {{
    border-color: {TEXT_FAINT};
}}
QComboBox:focus {{
    border-color: {ACCENT_BLUE};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid {BORDER_MUTED};
}}
QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {BG_BASE};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    selection-background-color: {BG_HOVER};
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px;
    border-radius: 4px;
    min-height: 28px;
    color: {TEXT_SECONDARY};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {BG_SELECTED};
}}

/* ════════════════════════════════════════════════════════════
   GROUPBOX
   ════════════════════════════════════════════════════════════ */
QGroupBox {{
    background: {BG_BASE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: 600;
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 14px;
    color: {ACCENT_BLUE};
}}

/* ════════════════════════════════════════════════════════════
   TABS — clean, minimal
   ════════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    background: {BG_DEEP};
    border: none;
    border-top: 1px solid {BORDER_SUBTLE};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    padding: 9px 20px;
    font-size: 12px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
}}
QTabBar::tab:selected {{
    color: {ACCENT_BLUE};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT_BLUE};
}}

/* ════════════════════════════════════════════════════════════
   SCROLLBARS — thin, minimal
   ════════════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_HOVER};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BG_HOVER};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}

/* ════════════════════════════════════════════════════════════
   TEXT EDIT / PLAINTEXT EDIT
   ════════════════════════════════════════════════════════════ */
QPlainTextEdit, QTextEdit {{
    background: {BG_DEEP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 13px;
    selection-background-color: {ACCENT_BLUE_DK};
    padding: 8px;
}}

/* ════════════════════════════════════════════════════════════
   TOOLTIP
   ════════════════════════════════════════════════════════════ */
QToolTip {{
    background: {BG_BASE};
    border: 1px solid {BORDER_MUTED};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 5px 10px;
    font-size: 12px;
}}

/* ════════════════════════════════════════════════════════════
   PROGRESS BAR
   ════════════════════════════════════════════════════════════ */
QProgressBar {{
    background: {BG_DEEP};
    border: 1px solid {BORDER_MUTED};
    border-radius: 4px;
    text-align: center;
    color: {ACCENT_BLUE};
    font-size: 11px;
    font-weight: bold;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_BLUE_DK});
    border-radius: 3px;
}}

/* ════════════════════════════════════════════════════════════
   SPLITTER
   ════════════════════════════════════════════════════════════ */
QSplitter::handle {{
    background: {BORDER_SUBTLE};
    width: 2px;
    height: 2px;
}}
QSplitter::handle:hover {{
    background: {ACCENT_BLUE};
}}

/* ════════════════════════════════════════════════════════════
   LABEL (transparent by default)
   ════════════════════════════════════════════════════════════ */
QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}

/* ════════════════════════════════════════════════════════════
   TREE VIEW / LIST VIEW — improved spacing & selection
   ════════════════════════════════════════════════════════════ */
QTreeView, QListView, QListWidget, QTreeWidget {{
    background: {BG_DEEP};
    border: none;
    outline: none;
    color: {TEXT_PRIMARY};
    alternate-background-color: {BG_BASE};
}}
QTreeView::item, QListView::item, QListWidget::item {{
    padding: 6px 12px;
    border-radius: 4px;
    margin: 1px 4px;
    color: {TEXT_SECONDARY};
}}
QTreeView::item:hover, QListView::item:hover, QListWidget::item:hover {{
    background: {BG_BASE};
    color: {TEXT_PRIMARY};
}}
QTreeView::item:selected, QListView::item:selected, QListWidget::item:selected {{
    background: {BG_SELECTED};
    color: {TEXT_PRIMARY};
    border-left: 3px solid {ACCENT_BLUE};
}}

/* Table headers */
QHeaderView::section {{
    background: {BG_BASE};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_MUTED};
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
}}

/* ════════════════════════════════════════════════════════════
   STATUS BAR
   ════════════════════════════════════════════════════════════ */
QStatusBar {{
    background: {BG_BASE};
    border-top: 1px solid {BORDER_SUBTLE};
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 3px 10px;
}}
QStatusBar::item {{
    border: none;
}}

/* ════════════════════════════════════════════════════════════
   FRAME / CARD (for InfoCard panels)
   ════════════════════════════════════════════════════════════ */
QFrame[class="card"],
QFrame#cardFrame {{
    background: {BG_BASE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
}}
QFrame[class="card"]:hover,
QFrame#cardFrame:hover {{
    border-color: {BORDER_MUTED};
    background: {BG_CARD};
}}

/* Toolbar / header bar frames */
QFrame[class="header"],
QFrame#headerFrame {{
    background: {BG_BASE};
    border-bottom: 1px solid {BORDER_SUBTLE};
}}

/* ════════════════════════════════════════════════════════════
   TABLE WIDGET
   ════════════════════════════════════════════════════════════ */
QTableWidget {{
    background: {BG_DEEP};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    gridline-color: {BORDER_SUBTLE};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QTableWidget::item:selected {{
    background: {BG_SELECTED};
}}

/* ════════════════════════════════════════════════════════════
   CHECKBOX & RADIO
   ════════════════════════════════════════════════════════════ */
QCheckBox {{
    color: {TEXT_SECONDARY};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_MUTED};
    border-radius: 3px;
    background: {BG_CARD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_BLUE_DK};
    border-color: {ACCENT_BLUE_DK};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT_BLUE};
}}
QRadioButton {{
    color: {TEXT_SECONDARY};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_MUTED};
    border-radius: 8px;
    background: {BG_CARD};
}}
QRadioButton::indicator:checked {{
    background: {ACCENT_BLUE_DK};
    border-color: {ACCENT_BLUE_DK};
}}

/* ════════════════════════════════════════════════════════════
   FILE DIALOG
   ════════════════════════════════════════════════════════════ */
QFileDialog {{
    background: {BG_DEEP};
}}
"""
