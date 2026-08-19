"""Hiệu ứng đổ bóng mềm và glow cho NovaSub.

QSS không hỗ trợ box-shadow nên dùng QGraphicsDropShadowEffect.

Cảnh báo hiệu năng:
  • Chỉ đặt cho tối đa ~12 widget cùng lúc (thẻ lớn, dialog, popup).
  • TUYỆT ĐỐI KHÔNG đặt lên widget có QGraphicsView hay video — Qt vô hiệu
    hoá bề mặt vẽ gốc của OS.
  • Với blur overlay (grain/noise): chỉ dùng pointer-events-none + fixed
    pseudo-widget, KHÔNG gắn vào scrolling container.

Thiết kế (high-end-visual-design skill):
  • Shadow tinted theo màu nền (không dùng black generic)
  • Accent glow cho elements quan trọng (primary button, active card)
  • Bóng nhẹ — premium feel, không phủ màu
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from autodub_gui import tokens


def soft_shadow(widget: QWidget,
                blur: int = tokens.SHADOW_BLUR,
                dy: int = tokens.SHADOW_Y,
                alpha: int = tokens.SHADOW_ALPHA) -> QGraphicsDropShadowEffect:
    """Bóng mềm tinted indigo — không dùng black generic.

    Màu bóng: tối tím để phù hợp BG_APP.
    """
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setXOffset(0)
    eff.setYOffset(dy)
    # Tinted indigo-dark shadow — không phải black generic
    eff.setColor(QColor(0, 0, 16, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def accent_glow(widget: QWidget,
                blur: int = 20,
                dy: int = 2,
                alpha: int = 60) -> QGraphicsDropShadowEffect:
    """Glow tím nhẹ cho primary buttons và active elements.

    Motivated: primary action cần visual weight — glow chỉ dùng cho CTA,
    không dùng cho mọi thứ (anti-pattern: glow everywhere).
    """
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setXOffset(0)
    eff.setYOffset(dy)
    # PRIMARY -> RGB(99, 102, 241)
    r, g, b = 99, 102, 241
    eff.setColor(QColor(r, g, b, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def danger_glow(widget: QWidget,
                blur: int = 16,
                dy: int = 2,
                alpha: int = 50) -> QGraphicsDropShadowEffect:
    """Glow đỏ nhẹ cho destructive action buttons."""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setXOffset(0)
    eff.setYOffset(dy)
    # DANGER -> RGB(248, 113, 113)
    eff.setColor(QColor(248, 113, 113, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def panel_shadow(widget: QWidget) -> QGraphicsDropShadowEffect:
    """Bóng tối nhẹ cho panels, cards — subtle elevation.

    Nhẹ hơn soft_shadow, dùng khi panel cần float khỏi background
    mà không quá dramatic.
    """
    return soft_shadow(widget, blur=16, dy=6, alpha=30)


def popup_shadow(widget: QWidget) -> QGraphicsDropShadowEffect:
    """Bóng sâu hơn cho popup, dialog, notification panel.

    Dùng khi element cần appear "on top" — floating glass panel.
    """
    return soft_shadow(widget, blur=40, dy=16, alpha=80)
