"""Design token — nguồn sự thật DUY NHẤT về màu, khoảng cách và bo góc.

Mọi file giao diện đều lấy màu từ đây. Cấm viết mã màu hex ở nơi khác
(bài kiểm thử `tests/test_ui_tokens.py` sẽ báo lỗi).

Giao diện TỐI (dark theme) — Ethereal Glass aesthetic:
OLED near-black với indigo tint, elevated glass panels, hairline borders.
Chuẩn thiết kế: agency-tier AI video editor, không generic AI purple slop.
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
BORDER_GLOW       = "#3a3cb0"   # Viền có glow accent

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
FS_DISPLAY      = 32
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
