"""Bảng màu và bảng kiểu Qt duy nhất cho toàn ứng dụng.

Nguồn sự thật về màu và khoảng cách nằm ở `autodub_gui/tokens.py`.
Tệp này chỉ làm hai việc:
  1. Xuất lại các tên cũ để những tệp chưa chuyển sang token không bị vỡ.
  2. Dựng chuỗi `STYLESHEET` từ token.

Cấm viết mã màu hex trực tiếp ở đây (`tests/test_ui_tokens.py` sẽ báo lỗi).

Thiết kế: Ethereal Glass — OLED dark, hairline borders, elevated surface system.
Ma trận trạng thái: default / hover / active / focus / disabled / selected.
"""
from __future__ import annotations

import os as _os

from autodub_gui import tokens as _t

# -- Tên cũ giữ cho tương thích ngược --------------------------------
BG = _t.BG_APP
BG_SIDEBAR = _t.BG_SIDEBAR
BG_PANEL = _t.BG_PANEL
BG_INPUT = _t.BG_INPUT
BG_HOVER = _t.BG_PANEL_HOVER

BORDER = _t.BORDER_SUBTLE
BORDER_CARD = _t.BORDER_SUBTLE
BORDER_FOCUS = _t.BORDER_ACTIVE

TEXT = _t.TEXT_PRIMARY
TEXT_MUTED = _t.TEXT_SECONDARY
TEXT_DIM = _t.TEXT_MUTED

ACCENT = _t.PRIMARY
ACCENT_HOVER = _t.PRIMARY_HOVER
ACCENT_PRESSED = _t.PRIMARY_DARK
ACCENT_PURPLE = _t.ACCENT_PURPLE
ACCENT_PURPLE_HOVER = _t.ACCENT_PURPLE_HOVER

SUCCESS = _t.SUCCESS
SUCCESS_BG = _t.SUCCESS_BG
WARNING = _t.WARNING
WARNING_BG = _t.WARNING_BG
ERROR = _t.DANGER
ERROR_BG = _t.DANGER_BG
RUNNING = _t.PROCESSING


def _grad_h(start: str, end: str) -> str:
    """Dải chuyển sắc ngang từ trái sang phải, dùng trong QSS."""
    return (f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {start}, stop:1 {end})")


def _grad_v(start: str, end: str) -> str:
    """Dải chuyển sắc dọc từ trên xuống dưới, dùng trong QSS."""
    return (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {start}, stop:1 {end})")


def _triangle_asset(name: str, w: int, h: int, color: str, *,
                    up: bool = False) -> str:
    """Vẽ một tam giác nhỏ ra tệp PNG rồi trả về đường dẫn dùng trong QSS."""
    from PySide6.QtCore import QPointF, Qt as _Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

    folder = _os.path.join(_os.path.expanduser("~"), ".voxdub_cache", "ui")
    _os.makedirs(folder, exist_ok=True)
    path = _os.path.join(folder, f"{name}.png")
    image = QImage(w, h, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(_Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    if up:
        points = [QPointF(0, h), QPointF(w, h), QPointF(w / 2, 0)]
    else:
        points = [QPointF(0, 0), QPointF(w, 0), QPointF(w / 2, h)]
    painter.drawPolygon(QPolygonF(points))
    painter.end()
    image.save(path)
    return path.replace("\\", "/")


_ARROW_DOWN = _triangle_asset("arrow_down", 10, 6, _t.TEXT_SECONDARY)
_ARROW_UP_S = _triangle_asset("arrow_up_s", 8, 5, _t.TEXT_SECONDARY, up=True)
_ARROW_DOWN_S = _triangle_asset("arrow_down_s", 8, 5, _t.TEXT_SECONDARY)


# ---------------------------------------------------------------------------
# STYLESHEET — Bảng kiểu QSS chuẩn hóa cho toàn ứng dụng NovaSub
#
# Module 1: Base Application & Window (OLED canvas layer)
# Module 2: Surfaces, Elevation & Glass Cards
# Module 3: Navigation Rail & Sidebar
# Module 4: Form Inputs, Controls & Focus System
# Module 5: Buttons Hierarchy & Interaction States
# Module 6: Data Tables, Sliders & Scrollbars
# Module 7: Feedback, Tooltips & Context Menus
# ---------------------------------------------------------------------------
STYLESHEET = f"""
/* ==========================================================================
   MODULE 1: BASE APPLICATION & WINDOW
   ========================================================================== */
QWidget {{
    background: {_t.BG_APP};
    color: {_t.TEXT_PRIMARY};
    font-family: {_t.FONT_STACK};
    font-size: {_t.FS_BODY}px;
    font-weight: 400;
}}
QMainWindow {{
    background: {_t.BG_APP};
}}
QDialog {{
    background: {_t.BG_ELEVATED};
    border: 1px solid {_t.BORDER_DEFAULT};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_XL}px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 4px;
    background: {_t.BORDER_SUBTLE};
}}
QSplitter::handle:vertical {{
    height: 4px;
    background: {_t.BORDER_SUBTLE};
}}
QSplitter::handle:hover {{
    background: {_t.BORDER_DEFAULT};
}}
QStatusBar {{
    background: {_t.BG_SIDEBAR};
    color: {_t.TEXT_SECONDARY};
    border-top: 1px solid {_t.BORDER_SUBTLE};
    font-size: {_t.FS_LABEL}px;
}}
QStatusBar::item {{
    border: none;
}}

/* ==========================================================================
   MODULE 2: SURFACES, ELEVATION & GLASS CARDS
   ========================================================================== */
QFrame#card {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_LG}px;
}}
QFrame#card:hover {{
    border-color: {_t.BORDER_DEFAULT};
    border-top-color: {_t.GLASS_HIGHLIGHT};
    background: {_t.BG_PANEL_HOVER};
}}
QFrame#cardFlat {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_LG}px;
}}
QFrame#sidebarCard {{
    background: {_t.GLASS_BG};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_MD}px;
}}
QFrame#banner {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_MD}px;
}}
QFrame#divider {{
    border: none;
    background: {_t.BORDER_SUBTLE};
    max-height: 1px;
}}
QGroupBox {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_LG}px;
    margin-top: 22px;
    padding: 18px 16px 16px 16px;
    font-weight: normal;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 2px 10px;
    color: {_t.TEXT_PRIMARY};
    font-size: {_t.FS_BODY}px;
    font-weight: 600;
}}
QFrame#voiceCard {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_LG}px;
}}
QFrame#voiceCard:hover {{
    background: {_t.BG_PANEL_HOVER};
    border-color: {_t.BORDER_DEFAULT};
    border-top-color: {_t.GLASS_HIGHLIGHT};
}}
QFrame#voiceCard[selected="true"] {{
    background: {_t.VOICE_SELECTED_BG};
    border: 1px solid {_t.BORDER_ACTIVE};
    border-top: 1px solid {_t.PRIMARY};
}}



/* ==========================================================================
   MODULE 3: NAVIGATION RAIL & SIDEBAR
   ========================================================================== */
QListWidget#nav, QListWidget#nav2 {{
    background: {_t.BG_SIDEBAR};
    border: none;
    outline: none;
    padding: 2px 0px;
}}
QListWidget#nav::item, QListWidget#nav2::item {{
    height: {_t.NAV_ITEM_H}px;
    padding: 0px 14px;
    border: none;
    border-radius: {_t.RADIUS_MD}px;
    margin: 1px 8px;
    color: {_t.TEXT_SECONDARY};
    font-size: {_t.FS_BODY}px;
    font-weight: 500;
}}
QListWidget#nav::item:hover, QListWidget#nav2::item:hover {{
    background: {_t.NAV_HOVER_BG};
    color: {_t.TEXT_PRIMARY};
}}
QListWidget#nav::item:selected, QListWidget#nav2::item:selected {{
    background: {_grad_h(_t.NAV_SEL_GRAD_A, _t.NAV_SEL_GRAD_B)};
    color: {_t.PRIMARY};
    font-weight: 600;
    border-left: 2px solid {_t.PRIMARY};
}}
QListWidget#nav::item:selected:hover, QListWidget#nav2::item:selected:hover {{
    background: {_grad_h(_t.NAV_SEL_GRAD_A, _t.NAV_SEL_GRAD_B)};
    color: {_t.PRIMARY};
}}
QLabel#sectionLabel {{
    color: {_t.SECTION_LABEL};
    font-size: {_t.FS_BADGE}px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 2px 16px;
    background: transparent;
}}
QWidget#notifRow {{
    border-radius: {_t.RADIUS_SM}px;
}}
QWidget#notifRow:hover {{
    background: {_t.BG_PANEL_HOVER};
    border-radius: {_t.RADIUS_SM}px;
}}

/* ==========================================================================
   MODULE 4: FORM INPUTS, CONTROLS & FOCUS SYSTEM
   ========================================================================== */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {_t.BG_INPUT};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_MD}px;
    padding: 8px 12px;
    min-height: 22px;
    color: {_t.TEXT_PRIMARY};
    selection-background-color: {_t.PRIMARY};
    selection-color: {_t.TEXT_ON_ACCENT};
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: {_t.BORDER_DEFAULT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {_t.BORDER_ACTIVE};
    background: {_t.BG_INPUT};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {_t.TEXT_DISABLED};
    background: {_t.BG_INPUT_DISABLED};
    border-color: {_t.BORDER_SUBTLE};
}}
QCheckBox, QRadioButton {{
    spacing: 9px;
    background: transparent;
    padding: 3px 0;
}}
QCheckBox:disabled, QRadioButton:disabled, QLabel:disabled {{
    color: {_t.TEXT_DISABLED};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {_t.BORDER_DEFAULT};
    background: {_t.BG_INPUT};
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {_t.PRIMARY};
    border-color: {_t.PRIMARY};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {_t.BORDER_ACTIVE};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: {_t.BG_INPUT_DISABLED};
    border-color: {_t.BORDER_SUBTLE};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: url("{_ARROW_DOWN}");
    width: 10px;
    height: 6px;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {_t.BG_ELEVATED};
    border: 1px solid {_t.BORDER_DEFAULT};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_LG}px;
    selection-background-color: {_t.BG_SELECTED};
    selection-color: {_t.PRIMARY};
    outline: none;
    padding: 6px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 32px;
    padding: 4px 12px;
    border: none;
    border-radius: {_t.RADIUS_SM}px;
    color: {_t.TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {_t.BG_PANEL_HOVER};
    color: {_t.TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {_t.BG_SELECTED};
    color: {_t.PRIMARY};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_ARROW_UP_S}");
    width: 8px;
    height: 5px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_ARROW_DOWN_S}");
    width: 8px;
    height: 5px;
}}

/* ==========================================================================
   MODULE 5: BUTTONS HIERARCHY & INTERACTION STATES
   ========================================================================== */
QPushButton {{
    background: {_t.BG_BUTTON};
    border: 1px solid {_t.BORDER_BUTTON};
    border-radius: {_t.RADIUS_MD}px;
    padding: 9px 18px;
    min-height: 22px;
    color: {_t.TEXT_PRIMARY};
    font-weight: 500;
}}
QPushButton:hover {{
    background: {_t.BG_PANEL_HOVER};
    border-color: {_t.BORDER_DEFAULT};
    color: {_t.TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background: {_t.BG_BUTTON_PRESSED};
    border-color: {_t.BORDER_ACTIVE};
}}
QPushButton:focus {{
    border-color: {_t.BORDER_ACTIVE};
    outline: none;
}}
QPushButton:disabled {{
    color: {_t.TEXT_DISABLED};
    background: {_t.BG_PANEL};
    border-color: {_t.BORDER_SUBTLE};
}}

/* Primary CTA Button */
QPushButton#primary {{
    background: {_grad_h(_t.PRIMARY, _t.PRIMARY_GRAD_B)};
    border: 1px solid {_t.BORDER_GLOW};
    border-top: 1px solid {_t.GLASS_HIGHLIGHT};
    color: {_t.TEXT_ON_ACCENT};
    font-weight: 600;
    padding: 10px 24px;
    border-radius: {_t.RADIUS_MD}px;
    letter-spacing: 0px;
}}
QPushButton#primary:hover {{
    background: {_grad_h(_t.PRIMARY_HOVER, _t.PRIMARY_GRAD_B_HOVER)};
    border-color: {_t.PRIMARY};
    color: {_t.TEXT_ON_ACCENT};
}}
QPushButton#primary:pressed {{
    background: {_t.PRIMARY_DARK};
    border-color: {_t.PRIMARY_DARK};
    color: {_t.TEXT_ON_ACCENT};
}}
QPushButton#primary:focus {{
    background: {_grad_h(_t.PRIMARY_HOVER, _t.PRIMARY_GRAD_B_HOVER)};
    border: 2px solid {_t.PRIMARY};
    color: {_t.TEXT_ON_ACCENT};
    outline: none;
}}
QPushButton#primary:disabled {{
    background: {_t.PRIMARY_DISABLED_BG};
    border-color: {_t.BORDER_SUBTLE};
    color: {_t.TEXT_DISABLED};
}}

/* Danger Action Button */
QPushButton#danger {{
    color: {_t.DANGER};
    border-color: {_t.BORDER_DANGER};
    background: transparent;
    font-weight: 600;
}}
QPushButton#danger:hover {{
    background: {_t.DANGER_BG};
    border-color: {_t.DANGER};
}}
QPushButton#danger:pressed {{
    background: {_t.DANGER_BG};
    border-color: {_t.DANGER};
}}
QPushButton#danger:disabled {{
    color: {_t.TEXT_DISABLED};
    border-color: {_t.BORDER_SUBTLE};
    background: transparent;
}}

/* Ghost / Secondary Button */
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {_t.BORDER_DEFAULT};
    color: {_t.TEXT_SECONDARY};
    font-weight: 500;
}}
QPushButton#ghost:hover {{
    background: {_t.BG_SELECTED_SOFT};
    color: {_t.TEXT_PRIMARY};
    border-color: {_t.BORDER_ACTIVE};
}}
QPushButton#ghost:pressed {{
    background: {_t.BG_SELECTED};
    color: {_t.TEXT_PRIMARY};
    border-color: {_t.PRIMARY};
}}
QPushButton#ghost:focus {{
    border-color: {_t.BORDER_ACTIVE};
    color: {_t.TEXT_PRIMARY};
    outline: none;
}}
QPushButton#ghost:disabled {{
    color: {_t.TEXT_DISABLED};
    background: transparent;
}}

/* Icon Only Button */
QPushButton#iconbtn {{
    background: transparent;
    border: none;
    border-radius: {_t.RADIUS_SM}px;
    padding: 0px;
    min-height: 0px;
}}
QPushButton#iconbtn:hover {{
    background: {_t.NAV_HOVER_BG};
    border: 1px solid {_t.BORDER_SUBTLE};
}}
QPushButton#iconbtn:pressed {{
    background: {_t.BG_SELECTED};
}}
QPushButton#iconbtn:checked {{
    background: {_t.BG_SELECTED};
    border: 1px solid {_t.BORDER_ACTIVE};
}}
QPushButton#iconbtn:focus {{
    background: {_t.NAV_HOVER_BG};
    outline: none;
}}

/* Segmented Control Buttons */
QPushButton#segment {{
    background: transparent;
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_NONE}px;
    padding: 8px 14px;
    font-size: {_t.FS_BODY}px;
    font-weight: 500;
    color: {_t.TEXT_SECONDARY};
}}
QPushButton#segment[position="first"] {{
    border-top-left-radius: {_t.RADIUS_MD}px;
    border-bottom-left-radius: {_t.RADIUS_MD}px;
}}
QPushButton#segment[position="last"] {{
    border-top-right-radius: {_t.RADIUS_MD}px;
    border-bottom-right-radius: {_t.RADIUS_MD}px;
}}
QPushButton#segment:hover:!checked {{
    background: {_t.BG_PANEL_HOVER};
    color: {_t.TEXT_PRIMARY};
    border-color: {_t.BORDER_DEFAULT};
}}
QPushButton#segment:checked {{
    background: {_t.PRIMARY};
    border-color: {_t.PRIMARY};
    color: {_t.TEXT_ON_ACCENT};
    font-weight: 600;
}}
QPushButton#segment:disabled {{
    color: {_t.TEXT_DISABLED};
}}

/* Pill Tab Bar */
QWidget#pillTabBar {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: 20px;
}}
QPushButton#pillTab {{
    background: transparent;
    border: none;
    color: {_t.TEXT_SECONDARY};
    border-radius: 17px;
    padding: 7px 18px;
    font-size: {_t.FS_BODY}px;
    font-weight: 500;
    min-height: 20px;
}}
QPushButton#pillTab:hover:!checked {{
    background: {_t.NAV_HOVER_BG};
    color: {_t.TEXT_PRIMARY};
}}
QPushButton#pillTab:checked {{
    background: {_grad_h(_t.PRIMARY, _t.ACCENT_PURPLE)};
    color: {_t.TEXT_ON_ACCENT};
    font-weight: 600;
}}


/* Tag / Filter Chip */
QPushButton#chip {{
    background: {_t.CHIP_BG};
    border: 1px solid {_t.BORDER_BUTTON};
    color: {_t.TEXT_SECONDARY};
    border-radius: 14px;
    padding: 4px 14px;
    font-size: {_t.FS_LABEL}px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton#chip:hover:!checked {{
    border-color: {_t.BORDER_DEFAULT};
    color: {_t.TEXT_PRIMARY};
    background: {_t.BG_PANEL_HOVER};
}}
QPushButton#chip:checked {{
    background: {_t.CHIP_BG_ACTIVE};
    border-color: {_t.CHIP_BORDER_ACTIVE};
    color: {_t.TEXT_PRIMARY};
    font-weight: 600;
}}

/* Legacy Button Types */
QPushButton#stop {{
    color: {_t.DANGER};
    font-weight: 600;
    border-color: {_t.BORDER_DANGER};
    background: transparent;
}}
QPushButton#stop:hover {{
    background: {_t.DANGER_BG};
    border-color: {_t.DANGER};
}}
QPushButton#stop:disabled {{
    color: {_t.TEXT_DISABLED};
    border-color: {_t.BORDER_SUBTLE};
}}
QPushButton#purple {{
    background: {_t.ACCENT_PURPLE};
    border: none;
    color: {_t.TEXT_ON_ACCENT};
    font-weight: 600;
    padding: 9px 18px;
    border-radius: {_t.RADIUS_MD}px;
}}
QPushButton#purple:hover {{
    background: {_t.ACCENT_PURPLE_HOVER};
}}
QPushButton#purple:disabled {{
    background: {_t.BG_PANEL};
    color: {_t.TEXT_DISABLED};
}}
QPushButton#pill {{
    background: transparent;
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_NONE}px;
    padding: 8px 20px;
    font-size: {_t.FS_BODY}px;
    font-weight: 500;
    color: {_t.TEXT_SECONDARY};
}}
QPushButton#pill:checked {{
    background: {_t.PRIMARY};
    color: {_t.TEXT_ON_ACCENT};
    border-color: {_t.PRIMARY};
    font-weight: 600;
}}
QPushButton#pill:hover:!checked {{
    background: {_t.BG_PANEL_HOVER};
    color: {_t.TEXT_PRIMARY};
}}

/* Voice Card Item */
QFrame#voiceCard {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_LG}px;
}}
QFrame#voiceCard:hover {{
    background: {_t.BG_PANEL_HOVER};
    border-color: {_t.BORDER_DEFAULT};
    border-top-color: {_t.GLASS_BORDER};
}}
QFrame#voiceCard[selected="true"] {{
    background: {_t.VOICE_SELECTED_BG};
    border: 1px solid {_t.BORDER_ACTIVE};
    border-top: 1px solid {_t.PRIMARY};
}}

/* ==========================================================================
   MODULE 6: DATA TABLES, SLIDERS & SCROLLBARS
   ========================================================================== */
QProgressBar {{
    background: {_t.TRACK_BG};
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: {_t.TEXT_SECONDARY};
    font-size: {_t.FS_META}px;
}}
QProgressBar::chunk {{
    background: {_grad_h(_t.PRIMARY, _t.ACCENT_BLUE)};
    border-radius: 3px;
}}

QTableWidget, QTableView {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_LG}px;
    gridline-color: transparent;
    selection-background-color: {_t.BG_SELECTED};
    selection-color: {_t.TEXT_PRIMARY};
    outline: none;
}}
QTableWidget::item {{
    padding: 6px 12px;
    border: none;
}}
QTableWidget::item:selected {{
    background: {_t.BG_SELECTED};
    color: {_t.TEXT_PRIMARY};
}}
QHeaderView::section {{
    background: {_t.BG_PANEL};
    color: {_t.TEXT_MUTED};
    padding: 12px;
    border: none;
    border-bottom: 1px solid {_t.BORDER_SUBTLE};
    font-size: {_t.FS_LABEL}px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QTableCornerButton::section {{
    background: {_t.BG_PANEL};
    border: none;
}}

QListWidget {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_LG}px;
    outline: none;
}}
QListWidget::item {{
    border: none;
    color: {_t.TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background: {_t.BG_SELECTED};
    color: {_t.PRIMARY};
}}

QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {_t.TEXT_SECONDARY};
    padding: 9px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: {_t.FS_BODY}px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {_t.TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    color: {_t.TEXT_PRIMARY};
    border-bottom: 2px solid {_t.PRIMARY};
    font-weight: 600;
}}
QTabBar::tab:disabled {{
    color: {_t.TEXT_DISABLED};
}}

/* Thin Minimal Scrollbar */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {_t.BORDER_DEFAULT};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_t.SCROLL_HANDLE_HOVER};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {_t.BORDER_DEFAULT};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_t.SCROLL_HANDLE_HOVER};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 4px;
    background: {_t.TRACK_BG};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {_grad_h(_t.PRIMARY, _t.ACCENT_BLUE)};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {_t.TEXT_ON_ACCENT};
    border: 1px solid {_t.PRIMARY};
}}
QSlider::handle:horizontal:hover {{
    background: {_t.PRIMARY};
    border-color: {_t.PRIMARY_HOVER};
}}
QSlider::handle:horizontal:disabled {{
    background: {_t.TEXT_DISABLED};
}}
QSlider::sub-page:horizontal:disabled {{
    background: {_t.BORDER_DEFAULT};
}}

/* Typography Class Hooks */
QLabel {{
    background: transparent;
}}
QLabel#pageTitle {{
    font-size: {_t.FS_PAGE_TITLE}px;
    font-weight: 700;
    color: {_t.TEXT_PRIMARY};
    letter-spacing: -0.5px;
}}
QLabel#sectionTitle {{
    font-size: {_t.FS_SECTION}px;
    font-weight: 700;
    color: {_t.TEXT_PRIMARY};
}}
QLabel#cardTitle {{
    font-size: {_t.FS_CARD_TITLE}px;
    font-weight: 600;
    color: {_t.TEXT_PRIMARY};
}}
QLabel#hint {{
    color: {_t.TEXT_MUTED};
    font-size: {_t.FS_LABEL}px;
}}
QLabel#meta {{
    color: {_t.TEXT_MUTED};
    font-size: {_t.FS_META}px;
}}
QLabel#sectionNote {{
    color: {_t.TEXT_SECONDARY};
    font-size: {_t.FS_LABEL}px;
}}
QLabel#sectionHeader {{
    color: {_t.TEXT_MUTED};
    font-size: {_t.FS_META}px;
    font-weight: 700;
    padding-bottom: 4px;
    letter-spacing: 0.5px;
}}

/* ==========================================================================
   MODULE 7: FEEDBACK, TOOLTIPS & CONTEXT MENUS
   ========================================================================== */
QToolTip {{
    background: {_t.BG_ELEVATED};
    color: {_t.TEXT_PRIMARY};
    border: 1px solid {_t.BORDER_DEFAULT};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_MD}px;
    padding: 6px 12px;
    font-size: {_t.FS_LABEL}px;
    font-weight: 400;
}}

QMenu {{
    background: {_t.BG_ELEVATED};
    border: 1px solid {_t.BORDER_DEFAULT};
    border-top: 1px solid {_t.GLASS_BORDER};
    border-radius: {_t.RADIUS_LG}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 16px;
    border-radius: {_t.RADIUS_SM}px;
    color: {_t.TEXT_PRIMARY};
    font-size: {_t.FS_BODY}px;
}}
QMenu::item:selected {{
    background: {_t.BG_SELECTED};
    color: {_t.PRIMARY};
}}
QMenu::separator {{
    height: 1px;
    background: {_t.BORDER_SUBTLE};
    margin: 4px 8px;
}}

/* Video Card Surface */
QFrame#videoCard {{
    background: {_t.BG_PANEL};
    border: 1px solid {_t.BORDER_SUBTLE};
    border-radius: {_t.RADIUS_LG}px;
}}
QFrame#videoCard:hover {{
    border-color: {_t.BORDER_DEFAULT};
    background: {_t.BG_PANEL_HOVER};
}}
"""
