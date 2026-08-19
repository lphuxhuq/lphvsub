# TASK 01 — UI FOUNDATION Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign and standardize the UI Foundation for **NovaSub** (`lphvsub`), establishing a consistent, modern dark design system (Ethereal Glass aesthetic) strictly inside `autodub_gui/tokens.py` and `autodub_gui/theme.py` using PySide6/Qt Widgets.

**Architecture:** Centralize all visual design decisions into an atomic token layer (`tokens.py`) and a modular, comprehensive Qt Style Sheet (`theme.py`). Establish a strict surface elevation system, scalable 4px spacing tokens, typography scale, semantic color palette, state matrix (default/hover/active/focus/disabled/loading), and motion duration constants, without modifying any backend logic, workers, or routing.

**Tech Stack:** Python 3.10+, PySide6 (Qt 6.11.1 Widgets + QSS), pytest, pytest-qt.

---

## Global Constraints

- **Scope boundary:** Modify ONLY `autodub_gui/tokens.py` and `autodub_gui/theme.py` (and test file `tests/test_ui_tokens.py` to match new tokens).
- **Backend Safety:** Do NOT touch `autodub/`, `autodub_gui/workers.py`, worker logic, translation logic, TTS, FFmpeg, project state, or routing.
- **Component Preservation:** Do NOT remove or rename existing component object names (`#card`, `#primary`, `#ghost`, `#danger`, `#iconbtn`, `#segment`, `#pillTab`, `#chip`, `#nav`, `#sidebarCard`, etc.) to prevent breaking existing pages.
- **Zero Hex Outside Tokens:** No hex colors outside `tokens.py` (strictly enforced by `tests/test_ui_tokens.py`).
- **Dark Theme Ergonomics:** High-contrast text on deep dark backgrounds (`#07070f`), hairline glass borders (`rgba(255,255,255,12)` / `#18183a`), no generic AI purple gradient slop.

---

### Task 1: Complete Token System Specification (`autodub_gui/tokens.py`)

**Files:**
- Modify: `autodub_gui/tokens.py`
- Test: `tests/test_ui_tokens.py`

**Interfaces:**
- Produces: Complete set of surface, border, text, semantic, spacing, typography, radius, and animation tokens exported for `theme.py` and GUI components.

- [ ] **Step 1: Write failing/enhanced tests for design token completeness in `tests/test_ui_tokens.py`**

```python
# tests/test_ui_tokens.py (addition)
def test_tokens_surface_and_elevation_system():
    """Bảo đảm tokens có đủ hệ thống phân cấp bề mặt (surface hierarchy)."""
    from autodub_gui import tokens

    surfaces = (
        "BG_APP", "BG_SIDEBAR", "BG_MAIN", "BG_PANEL", "BG_PANEL_HOVER",
        "BG_ELEVATED", "BG_INPUT", "BG_INPUT_DISABLED", "BG_BUTTON",
        "BG_BUTTON_PRESSED", "BG_VIDEO", "BG_SELECTED", "BG_SELECTED_SOFT",
    )
    for name in surfaces:
        assert hasattr(tokens, name), f"tokens.py thiếu token bề mặt: {name}"

def test_tokens_spacing_and_radius_scales():
    """Bảo đảm tokens có đủ thang khoảng cách và bo góc nhất quán."""
    from autodub_gui import tokens

    spacing = ("SP_1", "SP_2", "SP_3", "SP_4", "SP_5", "SP_6", "SP_8", "SP_10", "SP_12")
    for name in spacing:
        assert hasattr(tokens, name), f"tokens.py thiếu token khoảng cách: {name}"

    radii = ("RADIUS_SM", "RADIUS_MD", "RADIUS_LG", "RADIUS_XL", "RADIUS_2XL")
    for name in radii:
        assert hasattr(tokens, name), f"tokens.py thiếu token bo góc: {name}"

def test_tokens_animation_timings():
    """Bảo đảm tokens có đủ hằng số thời gian chuyển động."""
    from autodub_gui import tokens

    timings = ("ANIM_FAST", "ANIM_MID", "ANIM_SLOW")
    for name in timings:
        assert hasattr(tokens, name), f"tokens.py thiếu token animation: {name}"
        assert isinstance(getattr(tokens, name), int)
```

- [ ] **Step 2: Run test to verify it fails on missing tokens**

Run: `pytest tests/test_ui_tokens.py -v`
Expected: FAIL on any missing token (e.g. `BG_ELEVATED`, `SP_10`, `SP_12`).

- [ ] **Step 3: Implement comprehensive token specification in `autodub_gui/tokens.py`**

```python
"""Design token — nguồn sự thật DUY NHẤT về màu, khoảng cách và bo góc.

Mọi file giao diện đều lấy màu từ đây. Cấm viết mã màu hex ở nơi khác
(bài kiểm thử `tests/test_ui_tokens.py` sẽ báo lỗi).

Giao diện TỐI (dark theme) — Ethereal Glass aesthetic:
OLED near-black với indigo tint, elevated glass panels, hairline borders.
"""
from __future__ import annotations

# -- Nền & Phân cấp bề mặt (Surface Hierarchy) ------------------------
BG_APP            = "#07070f"   # Layer 0: Canvas nền sâu nhất (OLED dark)
BG_SIDEBAR        = "#0a0a18"   # Layer 1: Thanh bên điều hướng
BG_MAIN           = "#07070f"   # Layer 0: Vùng nội dung chính
BG_PANEL          = "#0f0f22"   # Layer 2: Thẻ / Khung nhóm cơ bản (Surface L1)
BG_PANEL_HOVER    = "#141430"   # Hover trên panel — indigo push nhẹ
BG_ELEVATED       = "#161632"   # Layer 3: Bề mặt nổi (Dropdown, Modal, Popup)
BG_INPUT          = "#0d0d1e"   # Sunken: Ô nhập liệu (chìm hơn panel)

# Nền phụ trợ & Tương tác
BG_INPUT_DISABLED = "#0a0a14"
BG_BUTTON         = "#141428"   # Nút mặc định
BG_BUTTON_PRESSED = "#1e1e3c"   # Nút khi nhấn
BG_VIDEO          = "#050508"   # Sân khấu video — OLED đen tuyệt đối
BG_SELECTED       = "#1c1c40"   # Item đang chọn (Sidebar, Menu)
BG_SELECTED_SOFT  = "#141438"   # Selected nhạt (Chip, Badge, Hover phụ)

# -- Viền (Hairline Glass Borders) ------------------------------------
BORDER_SUBTLE     = "#18183a"   # Viền rất mờ — phân tách nhẹ
BORDER_DEFAULT    = "#22224a"   # Viền mặc định của card/input
BORDER_ACTIVE     = "#6366f1"   # Viền khi focus/selected (= PRIMARY)
BORDER_BUTTON     = "#1e1e40"   # Viền nút bấm mặc định
BORDER_DANGER     = "#4a1a1a"   # Viền cảnh báo lỗi
BORDER_UPLOAD     = "#2e2e68"   # Viền vùng thả tệp
BORDER_GLOW       = "#3a3cb0"   # Viền viền có glow accent

# -- Màu chính & Nhấn (Primary & Accent) ------------------------------
PRIMARY              = "#6366f1"   # Brand Indigo
PRIMARY_HOVER        = "#7577f5"   # Hover sáng nhẹ
PRIMARY_DARK         = "#4f46e5"   # Active / Pressed
PRIMARY_GRAD_B       = "#8b5cf6"   # Điểm cuối gradient
PRIMARY_GRAD_B_HOVER = "#7c4ff0"
PRIMARY_DISABLED_BG  = "#1c1c3c"

ACCENT_BLUE          = "#4f6ef7"
ACCENT_PURPLE        = "#8b5cf6"
ACCENT_PURPLE_HOVER  = "#9b6ef8"
ACCENT_CYAN          = "#06b6d4"

# -- Chữ & Độ tương phản (Typography Contrast) ------------------------
TEXT_PRIMARY      = "#e8e8f4"   # Chữ chính: gần trắng với cool tint
TEXT_SECONDARY    = "#5a5a8a"   # Chữ phụ: xám tím vừa
TEXT_MUTED        = "#2e2e50"   # Chữ mờ: hint, meta, shortcut
TEXT_DISABLED     = "#282848"   # Chữ bị khóa
TEXT_ON_ACCENT    = "#ffffff"   # Chữ trên nền màu đậm

# -- Trạng thái (Semantic Statuses) -----------------------------------
SUCCESS           = "#22c55e"   # Xanh lá
WARNING           = "#f59e0b"   # Vàng hổ phách
DANGER            = "#f87171"   # Đỏ sáng
PROCESSING        = "#6366f1"   # Chàm đang chạy

SUCCESS_BG        = "#0a2016"
WARNING_BG        = "#1e1608"
DANGER_BG         = "#200a0a"
PROCESSING_BG     = "#14143a"
NEUTRAL_BG        = "#0f0f22"
PURPLE_BG         = "#160e2a"

# -- Dải thời gian & Waveform (Timeline Palette) ----------------------
WAVEFORM          = "#6366f1"
WAVEFORM_LIGHT    = "#3a3c7a"
PLAYHEAD          = "#ff4466"   # Neon red — high contrast
SUB_BLOCK_BG      = "#1e1806"
SUB_BLOCK_BORDER  = "#a07820"
SUB_BLOCK_TEXT    = "#d4a840"
RULER_TEXT        = "#3a3a5a"

TRACK_ORIGINAL      = "#8b5cf6"
TRACK_ORIGINAL_BG   = "#100e22"
TRACK_VOICE         = "#22c55e"
TRACK_VOICE_BG      = "#081810"
TRACK_MUSIC         = "#ec4899"
TRACK_MUSIC_BG      = "#1a0812"
TRACK_VIDEO_BG      = "#0c0c18"
TRACK_LABEL_BG      = "#0a0a16"
TRACK_LABEL_BORDER  = "#18183a"

# -- Canvas xem trước & Phụ đề ---------------------------------------
PREVIEW_CANVAS_BG   = "#0c0c14"
PREVIEW_GUIDE       = "#3f6fb5"
PREVIEW_BLUR_EDGE   = "#c2913a"
PREVIEW_EMPTY_BG    = "#0f0f22"
PREVIEW_EMPTY_TEXT  = "#3a3a5a"
LOG_BG              = "#09091a"

SUBTITLE_TEXT_DEFAULT      = "#FFFFFF"
SUBTITLE_OUTLINE_DEFAULT   = "#000000"
SUBTITLE_HIGHLIGHT_DEFAULT = "#FFD54A"
SUBTITLE_BOXFILL_DEFAULT   = "#000000"

# -- Thành phần giao diện chung --------------------------------------
STEP_DONE_BG        = "#6366f1"
STEP_UPCOMING_BG    = "#14142a"
STEP_UPCOMING_TEXT  = "#3a3a5a"

TRACK_BG            = "#14142a"
SCROLL_HANDLE_HOVER = "#32325a"
BRAND_LOGO_BG       = "#14143a"

CHIP_BG             = "#0f0f22"
CHIP_BG_ACTIVE      = "#141438"
CHIP_BORDER_ACTIVE  = "#6366f1"
VOICE_SELECTED_BG   = "#141438"
SECTION_LABEL       = "#2e2e50"

AVATAR_GRADIENTS = (
    ("#6366f1", "#8b5cf6"),
    ("#ec4899", "#8b5cf6"),
    ("#3b82f6", "#6366f1"),
    ("#22c55e", "#0ea5a4"),
    ("#f59e0b", "#ef4444"),
    ("#8b5cf6", "#ec4899"),
)

# -- Màu bán trong suốt QSS (Alpha 0..255) ---------------------------
NAV_SEL_GRAD_A    = "rgba(99,102,241,38)"
NAV_SEL_GRAD_B    = "rgba(99,102,241,28)"
NAV_HOVER_BG      = "rgba(99,102,241,22)"
MODAL_OVERLAY     = "rgba(0,0,0,200)"
DURATION_BADGE_BG = "rgba(0,0,0,210)"
UPLOAD_GRAD_A     = "rgba(99,102,241,20)"
UPLOAD_GRAD_B     = "rgba(139,92,246,20)"
DRAG_ACTIVE_BG    = "rgba(99,102,241,38)"
PLAYER_BAR_BG     = "rgba(10,10,24,235)"
SUBTITLE_BOX_BG   = "rgba(0,0,0,160)"

# Glass surface tokens
GLASS_BG          = "rgba(255,255,255,6)"
GLASS_BORDER      = "rgba(255,255,255,12)"
GLASS_HIGHLIGHT   = "rgba(255,255,255,18)"
GLASS_SHADOW      = "rgba(0,0,16,180)"

# -- Bo góc (Border Radius Scale) ------------------------------------
RADIUS_NONE = 0
RADIUS_SM   = 6     # Badges, inner tags, scrollbars
RADIUS_MD   = 10    # Buttons, inputs, chips
RADIUS_LG   = 14    # Cards, dialogs, group boxes
RADIUS_XL   = 18    # Large floating modals
RADIUS_2XL  = 24    # Pill containers

# -- Khoảng cách (4px Spacing Grid) ----------------------------------
SP_0 = 0
SP_1 = 4
SP_2 = 8
SP_3 = 12
SP_4 = 16
SP_5 = 20
SP_6 = 24
SP_8 = 32
SP_10 = 40
SP_12 = 48

# -- Kiểu chữ (Typography Hierarchy) ---------------------------------
FONT_STACK      = '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
FONT_MONO       = '"Cascadia Code", "Cascadia Mono", "Consolas", monospace'
FS_PAGE_TITLE   = 26
FS_SECTION      = 17
FS_CARD_TITLE   = 14
FS_BODY         = 13
FS_LABEL        = 12
FS_META         = 11
FS_BADGE        = 10

# -- Kích thước cố định (Layout Metrics) ------------------------------
SIDEBAR_W         = 220
SIDEBAR_W_COMPACT = 200
SIDEBAR_W_ICON    = 64
NAV_ITEM_H        = 42
HEADER_H          = 68
CARD_MIN_W        = 240

# -- Đổ bóng (Elevation & Shadows) -----------------------------------
SHADOW_BLUR   = 28
SHADOW_Y      = 10
SHADOW_ALPHA  = 18

# -- Thời gian Animation (ms) ----------------------------------------
ANIM_FAST  = 120   # Phản hồi tức thì (button press, tooltip, icon hover)
ANIM_MID   = 200   # Chuyển động chuẩn (sidebar collapse, panel hover)
ANIM_SLOW  = 280   # Chuyển trang, modal slide-in


def rgba(hex_color: str, alpha: float) -> str:
    """Đổi mã hex '#rrggbb' thành chuỗi 'rgba(r,g,b,a)' dùng trong QSS."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"
```

- [ ] **Step 4: Run test to verify all token tests pass**

Run: `pytest tests/test_ui_tokens.py -v`
Expected: PASS (all 5+ tests pass).

---

### Task 2: Modular Dark QSS Architecture (`autodub_gui/theme.py`)

**Files:**
- Modify: `autodub_gui/theme.py`
- Test: `tests/test_ui_tokens.py::test_theme_stylesheet_builds_from_tokens`

**Interfaces:**
- Consumes: All tokens from `autodub_gui.tokens`
- Produces: `autodub_gui.theme.STYLESHEET` string applied to the entire application `QApplication.setStyleSheet()`.

- [ ] **Step 1: Write test verifying stylesheet structure and state coverage**

```python
# tests/test_ui_tokens.py (addition)
def test_stylesheet_covers_all_core_states():
    """Kiểm tra STYLESHEET có đủ định nghĩa cho các trạng thái quan trọng."""
    from autodub_gui import theme

    css = theme.STYLESHEET
    assert "QPushButton#primary:hover" in css
    assert "QPushButton#primary:disabled" in css
    assert "QPushButton#ghost:hover" in css
    assert "QPushButton#danger:hover" in css
    assert "QLineEdit:focus" in css
    assert "QLineEdit:disabled" in css
    assert "QScrollBar:vertical" in css
    assert "QComboBox QAbstractItemView" in css
```

- [ ] **Step 2: Run test to verify initial status**

Run: `pytest tests/test_ui_tokens.py -k test_stylesheet_covers_all_core_states -v`

- [ ] **Step 3: Refactor `autodub_gui/theme.py` into clean modular structure**

1. Base Window & Dialogs (`QMainWindow`, `QDialog`, `QWidget`).
2. Elevated Surfaces & Glass Cards (`QFrame#card`, `QFrame#cardFlat`, `QFrame#sidebarCard`, `QGroupBox`).
3. Navigation & Rail (`QListWidget#nav`, `QListWidget#nav2`, `QLabel#sectionLabel`).
4. Inputs & Focus Rings (`QLineEdit`, `QComboBox`, `QSpinBox`, `QPlainTextEdit`, `QTextEdit`, `QCheckBox`, `QRadioButton`).
5. Button Hierarchy & States (`QPushButton`, `Primary`, `Ghost`, `Danger`, `IconButton`, `Segment`, `PillTab`, `Chip`).
6. Tables, Splitters & Sliders (`QTableWidget`, `QHeaderView`, `QSplitter`, `QSlider`, `QProgressBar`, `QScrollBar`).
7. Feedback, Tooltips & Context Menus (`QToolTip`, `QMenu`, `QStatusBar`).

Ensure zero hardcoded hex literals in comments or rules (all referenced via `_t.<TOKEN_NAME>`).

- [ ] **Step 4: Verify with pytest**

Run: `pytest tests/test_ui_tokens.py -v`
Expected: PASS (all tests green, 0 errors).

---

### Task 3: Comprehensive Regression & GUI Render Verification

**Files:**
- Test: All test files in `tests/`
- Target: Entire GUI application rendering

- [ ] **Step 1: Run full pytest suite**

Run: `pytest`
Expected: All 606 tests pass.

- [ ] **Step 2: Run offscreen GUI smoke test to verify all 15 pages render**

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'; from PySide6.QtWidgets import QApplication; app = QApplication([]); from autodub_gui.app import MainWindow, PAGES; w = MainWindow(); [w.switch_page(row) for row, _, _, _, _, _ in PAGES]; print('ALL PAGES RENDERED CLEANLY')"
```
Expected output: `ALL PAGES RENDERED CLEANLY`

- [ ] **Step 3: Verify no warning logs or stylesheet parsing errors in terminal**

---

### Task 4: Complete Foundation Summary Report

- Document all updated tokens, visual hierarchy tokens, and QSS enhancements.
- Verify compatibility across all pages (Home, New Project, Editor, Projects, Batch, Download, Voice, Translate, Subtitle, Settings, Help).

---

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-08-19-task-01-ui-foundation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach would you like to take?
