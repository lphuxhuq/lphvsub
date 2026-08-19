"""Animation helpers cho NovaSub.

Tất cả animation dùng QPropertyAnimation — GPU-safe, không animate
top/left/width/height trực tiếp mà dùng transform-equivalent.

Quy tắc (theo high-end-visual-design + design-taste-frontend skills):
  • Animate ONLY opacity (QGraphicsOpacityEffect) + geometry bounded props
  • Duration: FAST=120ms, MID=200ms, SLOW=280ms
  • Easing: InOutCubic cho layout, OutCubic cho entrances
  • Mọi animation phải có lý do: hierarchy, feedback, state transition
  • KHÔNG thêm animation chỉ vì "trông hay" (mỗi anim phải motivated)
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QObject, QParallelAnimationGroup, QPropertyAnimation,
    QSequentialAnimationGroup, QTimer, Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from autodub_gui import tokens


# ---------------------------------------------------------------------------
# Easing curves — custom spring-feel
# ---------------------------------------------------------------------------
_EASE_OUT_CUBIC  = QEasingCurve.Type.OutCubic
_EASE_INOUT_CUBIC = QEasingCurve.Type.InOutCubic
_EASE_OUT_BACK   = QEasingCurve.Type.OutBack


def fade_in(widget: QWidget, duration: int = tokens.ANIM_MID,
            from_opacity: float = 0.0) -> QPropertyAnimation:
    """Fade in một widget từ transparent → opaque.

    Tạo QGraphicsOpacityEffect nếu chưa có. Widget giữ effect sau khi
    animation kết thúc — gọi lại để fade in lần sau vẫn đúng.
    """
    effect = _ensure_opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(from_opacity)
    anim.setEndValue(1.0)
    anim.setEasingCurve(_EASE_OUT_CUBIC)
    anim.start()
    return anim


def fade_out(widget: QWidget, duration: int = tokens.ANIM_MID,
             on_finished: object = None) -> QPropertyAnimation:
    """Fade out một widget → transparent. Tùy chọn callback khi xong."""
    effect = _ensure_opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(_EASE_OUT_CUBIC)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start()
    return anim


def fade_switch(old_widget: QWidget, new_widget: QWidget,
                duration: int = tokens.ANIM_SLOW) -> QSequentialAnimationGroup:
    """Chuyển trang: fade out trang cũ → show trang mới → fade in.

    Pattern: page transition motivated bởi state change — người dùng
    cần biết họ đang ở trang mới.
    """
    group = QSequentialAnimationGroup(old_widget)

    # Phase 1: fade out old (ngắn hơn)
    fade_duration = duration // 2
    old_effect = _ensure_opacity_effect(old_widget)
    out_anim = QPropertyAnimation(old_effect, b"opacity")
    out_anim.setDuration(fade_duration)
    out_anim.setStartValue(old_effect.opacity())
    out_anim.setEndValue(0.0)
    out_anim.setEasingCurve(_EASE_OUT_CUBIC)
    group.addAnimation(out_anim)

    # Phase 2: switch + fade in new
    new_effect = _ensure_opacity_effect(new_widget)
    in_anim = QPropertyAnimation(new_effect, b"opacity")
    in_anim.setDuration(fade_duration)
    in_anim.setStartValue(0.0)
    in_anim.setEndValue(1.0)
    in_anim.setEasingCurve(_EASE_OUT_CUBIC)
    group.addAnimation(in_anim)

    group.start()
    return group


def slide_fade_in(widget: QWidget, direction: str = "up",
                  distance: int = 16,
                  duration: int = tokens.ANIM_SLOW) -> QParallelAnimationGroup:
    """Slide + fade in — cho page content, modal, toast.

    direction: 'up' | 'down' | 'left' | 'right'
    Dùng geometry.y/x animation — bounded, không trigger layout.
    """
    effect = _ensure_opacity_effect(widget)
    widget.show()
    geo = widget.geometry()

    group = QParallelAnimationGroup(widget)

    # Opacity
    op_anim = QPropertyAnimation(effect, b"opacity")
    op_anim.setDuration(duration)
    op_anim.setStartValue(0.0)
    op_anim.setEndValue(1.0)
    op_anim.setEasingCurve(_EASE_OUT_CUBIC)
    group.addAnimation(op_anim)

    # Position offset
    pos_anim = QPropertyAnimation(widget, b"geometry")
    pos_anim.setDuration(duration)
    offset_geo = _offset_geo(geo, direction, distance)
    pos_anim.setStartValue(offset_geo)
    pos_anim.setEndValue(geo)
    pos_anim.setEasingCurve(_EASE_OUT_CUBIC)
    group.addAnimation(pos_anim)

    group.start()
    return group


def animate_width(widget: QWidget, target_w: int,
                  duration: int = tokens.ANIM_MID) -> QParallelAnimationGroup:
    """Animate max + min width cùng lúc — dùng cho sidebar collapse/expand.

    Animate cả maxWidth lẫn minWidth để tránh widget bị squish khi thu.
    """
    group = QParallelAnimationGroup(widget)

    max_anim = QPropertyAnimation(widget, b"maximumWidth")
    max_anim.setDuration(duration)
    max_anim.setStartValue(widget.maximumWidth())
    max_anim.setEndValue(target_w)
    max_anim.setEasingCurve(_EASE_INOUT_CUBIC)
    group.addAnimation(max_anim)

    min_anim = QPropertyAnimation(widget, b"minimumWidth")
    min_anim.setDuration(duration)
    min_anim.setStartValue(widget.minimumWidth())
    min_anim.setEndValue(target_w)
    min_anim.setEasingCurve(_EASE_INOUT_CUBIC)
    group.addAnimation(min_anim)

    group.start()
    return group


def pulse_opacity(widget: QWidget, min_opacity: float = 0.4,
                  max_opacity: float = 1.0,
                  duration: int = 1400) -> QSequentialAnimationGroup:
    """Pulsing opacity loop — cho status indicator, logo khi processing.

    Motivated: trạng thái "đang chạy" cần visual indicator liên tục.
    Dùng loop vô hạn — nhớ gọi group.stop() khi không còn cần.
    """
    effect = _ensure_opacity_effect(widget)
    effect.setOpacity(min_opacity)

    group = QSequentialAnimationGroup(widget)
    group.setLoopCount(-1)  # vô hạn

    fade_up = QPropertyAnimation(effect, b"opacity")
    fade_up.setDuration(duration // 2)
    fade_up.setStartValue(min_opacity)
    fade_up.setEndValue(max_opacity)
    fade_up.setEasingCurve(QEasingCurve.Type.InOutSine)
    group.addAnimation(fade_up)

    fade_down = QPropertyAnimation(effect, b"opacity")
    fade_down.setDuration(duration // 2)
    fade_down.setStartValue(max_opacity)
    fade_down.setEndValue(min_opacity)
    fade_down.setEasingCurve(QEasingCurve.Type.InOutSine)
    group.addAnimation(fade_down)

    group.start()
    return group


def toast_slide_in(widget: QWidget,
                   duration: int = 160) -> QParallelAnimationGroup:
    """Toast slide in từ phải bottom — phiên bản nhanh hơn OutCubic.

    Motivated: feedback cho user action — cần instant nhưng vẫn smooth.
    """
    return slide_fade_in(widget, direction="up", distance=10,
                         duration=duration)


def delayed_fade_in(widget: QWidget, delay_ms: int,
                    duration: int = tokens.ANIM_MID) -> None:
    """Fade in sau một khoảng delay — staggered entry cho card lists.

    Motivated: hierarchy — items xuất hiện tuần tự để user theo dõi được.
    """
    QTimer.singleShot(delay_ms, lambda: fade_in(widget, duration))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _ensure_opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """Lấy hoặc tạo QGraphicsOpacityEffect gắn vào widget."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
    return effect


def _offset_geo(geo, direction: str, distance: int):
    """Tính geometry bắt đầu lệch so với vị trí đích."""
    from PySide6.QtCore import QRect
    x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
    if direction == "up":
        return QRect(x, y + distance, w, h)
    if direction == "down":
        return QRect(x, y - distance, w, h)
    if direction == "left":
        return QRect(x + distance, y, w, h)
    if direction == "right":
        return QRect(x - distance, y, w, h)
    return geo
