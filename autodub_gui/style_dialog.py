"""Dialog to style subtitles and pick blur regions on a video frame.

One place for everything drawn over the video:

- **Subtitle styling** — font, size, outline, colours, position. A live preview
  line is painted straight onto the frame and can be dragged up/down to set
  its position; controls on the right stay in sync.
- **Blur regions** — drag rectangles over hardcoded captions to blur them
  (same normalized 0..1 dicts as before).

Scaling note: ffmpeg's SRT→ASS conversion uses a PlayResY=288 canvas, so a
``FontSize``/``MarginV`` of N means N pixels *on a 288-line screen*. The
preview multiplies by ``frame_height / 288`` to show the real rendered size.

Works without a video too (URL mode before download): the canvas falls back to
a placeholder frame so styling is still possible; only region picking needs a
real frame.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink

from autodub_gui import tokens
from autodub_gui.ui.inputs import polish_combo

# ffmpeg renders SRT subtitles on an ASS canvas of this height; FontSize and
# MarginV in force_style are expressed in this coordinate space.
ASS_PLAY_RES_Y = 288

PREVIEW_TEXT = "Xin chào, đây là phụ đề xem trước"
# Preview ở chế độ karaoke: một cụm chữ ngắn như lúc render thật.
PREVIEW_TEXT_KARAOKE = "đây là phụ đề"

_POSITIONS = [("Dưới", "bottom"), ("Giữa", "middle"), ("Trên", "top")]

_BOXES = [("Không", "none"), ("Khối nền sau chữ", "box")]

_DISPLAYS = [("Cả câu", "sentence"),
             ("Cụm chữ theo giọng đọc", "karaoke")]

_EFFECTS = [("Nảy nhẹ", "pop"),
            ("Mờ dần", "fade"),
            ("Đổi màu theo lời", "karaoke"),
            ("Không", "none")]


def extract_frame(video_path: str, out_png: str, at_seconds: float = 1.0) -> str:
    """Grab a single frame from the video as a PNG via ffmpeg.

    Designed to be called from a background thread — never call this on the
    UI thread because a corrupt/long video can make ffmpeg block for 30s.
    """
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", str(at_seconds), "-i", video_path,
        "-frames:v", "1", "-y", out_png,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not os.path.exists(out_png):
        # Retry from the very start — the video may be shorter than at_seconds.
        cmd[cmd.index("-ss") + 1] = "0"
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not os.path.exists(out_png):
            raise RuntimeError(f"Could not extract a frame: {result.stderr}")
    return out_png


class _FrameWorker(QThread):
    """Chạy ffmpeg trong luồng nền để không chặn UI thread."""

    ready = Signal(str)   # đường dẫn tệp PNG khi thành công
    failed = Signal(str)  # thông báo lỗi

    def __init__(self, video_path: str, out_png: str,
                 at_seconds: float = 1.0, parent=None):
        super().__init__(parent)
        self._video = video_path
        self._out = out_png
        self._at = at_seconds

    def run(self) -> None:
        try:
            path = extract_frame(self._video, self._out, self._at)
            self.ready.emit(path)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def subtitle_zone(center_ratio: float) -> str:
    """Map a dragged text's vertical centre (0=top, 1=bottom) to a position."""
    if center_ratio < 0.38:
        return "top"
    if center_ratio < 0.62:
        return "middle"
    return "bottom"


class _FrameCanvas(QWidget):
    """Frame + blur rectangles + logo + watermark + draggable live subtitle preview."""

    def __init__(self, pixmap: QPixmap, style: dict,
                 allow_regions: bool = True, parent=None):
        super().__init__(parent)
        self._source = pixmap
        self._scaled = pixmap
        self._style = dict(style)
        self._logo_opts: dict = {}
        self._wm_opts: dict = {}
        self._allow_regions = allow_regions
        self._rects: list[QRect] = []
        self._selected_index: int | None = None
        self._drag_origin: QPoint | None = None
        self._drag_current: QRect | None = None
        self._dragging_text = False
        self._text_rect = QRectF()
        self.on_style_dragged = None      # callback(position: str, margin_v: int)
        self.on_regions_changed = None    # callback(regions: list[dict])
        self.setMinimumSize(480, 270)
        self.setMouseTracking(True)

    # ------------------------------------------------------- geometry ----- #

    def _pixmap_rect(self) -> QRect:
        pw, ph = self._scaled.width(), self._scaled.height()
        ox = (self.width() - pw) // 2
        oy = (self.height() - ph) // 2
        return QRect(ox, oy, pw, ph)

    def _ass_scale(self) -> float:
        """Canvas pixels per ASS unit (PlayResY=288 space)."""
        return max(self._scaled.height(), 1) / ASS_PLAY_RES_Y

    def resizeEvent(self, event):
        self._scaled = self._source.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().resizeEvent(event)
        self.update()

    # --------------------------------------------------------- style ------ #

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._scaled = self._source.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.update()

    def set_image(self, img: QImage) -> None:
        self.set_pixmap(QPixmap.fromImage(img))

    def set_style(self, style: dict) -> None:
        self._style = dict(style)
        self.update()

    def set_logo_options(self, opts: dict) -> None:
        self._logo_opts = dict(opts)
        self.update()

    def set_watermark_options(self, opts: dict) -> None:
        self._wm_opts = dict(opts)
        self.update()

    def set_rects_from_normalized(self, regions: list[dict]) -> None:
        """Restore previously picked regions onto the current canvas."""
        pr = self._pixmap_rect()
        self._rects = [
            QRect(int(pr.x() + r["x"] * pr.width()),
                  int(pr.y() + r["y"] * pr.height()),
                  int(r["w"] * pr.width()),
                  int(r["h"] * pr.height()))
            for r in regions
        ]
        self._selected_index = len(self._rects) - 1 if self._rects else None
        self.update()
        if self.on_regions_changed is not None:
            self.on_regions_changed(self.normalized_regions())

    # --------------------------------------------------------- mouse ------ #

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        if self._text_rect.adjusted(-8, -8, 8, 8).contains(pos):
            self._dragging_text = True
        elif self._allow_regions:
            self._drag_origin = pos.toPoint()
            self._drag_current = None

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._dragging_text:
            self._apply_text_drag(pos.y())
        elif self._drag_origin is not None:
            self._drag_current = QRect(
                self._drag_origin, pos.toPoint()).normalized()
            self.update()
        else:
            inside = self._text_rect.adjusted(-8, -8, 8, 8).contains(pos)
            self.setCursor(Qt.SizeVerCursor if inside else Qt.CrossCursor)

    def mouseReleaseEvent(self, event):
        if self._dragging_text:
            self._dragging_text = False
        elif self._drag_origin is not None and self._drag_current is not None:
            clipped = self._drag_current.intersected(self._pixmap_rect())
            if clipped.width() > 4 and clipped.height() > 4:
                self._rects.append(clipped)
                self._selected_index = len(self._rects) - 1
                if self.on_regions_changed is not None:
                    self.on_regions_changed(self.normalized_regions())
        self._drag_origin = None
        self._drag_current = None
        self.update()

    def _apply_text_drag(self, mouse_y: float) -> None:
        """Move the preview line to the cursor; report position + margin back."""
        pr = self._pixmap_rect()
        if pr.height() == 0:
            return
        clamped_y = max(pr.y(), min(mouse_y, pr.bottom()))
        center_ratio = (clamped_y - pr.y()) / pr.height()
        pos = subtitle_zone(center_ratio)
        scale = self._ass_scale()
        if pos == "top":
            margin_v = int((clamped_y - pr.y()) / scale)
        elif pos == "bottom":
            margin_v = int((pr.bottom() - clamped_y) / scale)
        else:
            margin_v = 0
        margin_v = max(0, min(margin_v, 200))
        self._style["position"] = pos
        self._style["margin_v"] = margin_v
        self.update()
        if self.on_style_dragged is not None:
            self.on_style_dragged(pos, margin_v)

    # ------------------------------------------------------- regions ------ #

    def clear_all(self) -> None:
        self._rects.clear()
        self._selected_index = None
        self.update()
        if self.on_regions_changed is not None:
            self.on_regions_changed([])

    def clear_last(self) -> None:
        if self._rects:
            self._rects.pop()
            self._selected_index = len(self._rects) - 1 if self._rects else None
            self.update()
            if self.on_regions_changed is not None:
                self.on_regions_changed(self.normalized_regions())

    def remove_region(self, index: int) -> None:
        """Xoá một vùng theo số thứ tự (0-indexed)."""
        if 0 <= index < len(self._rects):
            self._rects.pop(index)
            if self._selected_index == index:
                self._selected_index = len(self._rects) - 1 if self._rects else None
            elif self._selected_index is not None and self._selected_index > index:
                self._selected_index -= 1
            self.update()
            if self.on_regions_changed is not None:
                self.on_regions_changed(self.normalized_regions())

    def select_region(self, index: int | None) -> None:
        """Đánh dấu chọn một vùng để làm nổi bật trên canvas."""
        self._selected_index = index if (index is not None and 0 <= index < len(self._rects)) else None
        self.update()

    def add_preset_region(self, preset_type: str) -> None:
        """Tạo nhanh một vùng làm mờ từ mẫu phổ biến."""
        if preset_type == "bottom_band":
            reg = {"x": 0.0, "y": 0.82, "w": 1.0, "h": 0.16}
        elif preset_type == "top_band":
            reg = {"x": 0.0, "y": 0.02, "w": 1.0, "h": 0.15}
        elif preset_type == "top_right_logo":
            reg = {"x": 0.74, "y": 0.02, "w": 0.24, "h": 0.14}
        elif preset_type == "top_left_logo":
            reg = {"x": 0.02, "y": 0.02, "w": 0.24, "h": 0.14}
        elif preset_type == "bottom_right":
            reg = {"x": 0.74, "y": 0.84, "w": 0.24, "h": 0.14}
        elif preset_type == "bottom_left":
            reg = {"x": 0.02, "y": 0.84, "w": 0.24, "h": 0.14}
        else:
            reg = {"x": 0.0, "y": 0.82, "w": 1.0, "h": 0.16}

        pr = self._pixmap_rect()
        if pr.width() <= 0 or pr.height() <= 0:
            return
        new_r = QRect(int(pr.x() + reg["x"] * pr.width()),
                      int(pr.y() + reg["y"] * pr.height()),
                      int(reg["w"] * pr.width()),
                      int(reg["h"] * pr.height()))
        self._rects.append(new_r)
        self._selected_index = len(self._rects) - 1
        self.update()
        if self.on_regions_changed is not None:
            self.on_regions_changed(self.normalized_regions())

    def normalized_regions(self) -> list[dict]:
        """Convert stored displayed rectangles to normalized 0..1 dicts."""
        pr = self._pixmap_rect()
        if pr.width() == 0 or pr.height() == 0:
            return []
        out = []
        for r in self._rects:
            out.append({
                "x": round((r.x() - pr.x()) / pr.width(), 4),
                "y": round((r.y() - pr.y()) / pr.height(), 4),
                "w": round(r.width() / pr.width(), 4),
                "h": round(r.height() / pr.height(), 4),
            })
        return out

    # --------------------------------------------------------- paint ------ #

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pr = self._pixmap_rect()
        painter.fillRect(self.rect(), QColor(tokens.PREVIEW_CANVAS_BG))
        painter.drawPixmap(pr.topLeft(), self._scaled)

        # Blur regions
        default_pen = QPen(QColor(tokens.PREVIEW_GUIDE), 2)
        default_fill = QColor(63, 111, 181, 70)
        selected_pen = QPen(QColor(tokens.WARNING), 3)
        sel_c = QColor(tokens.WARNING)
        sel_c.setAlpha(90)
        selected_fill = sel_c

        badge_font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(badge_font)

        for i, r in enumerate(self._rects):
            is_sel = (i == self._selected_index)
            painter.setPen(selected_pen if is_sel else default_pen)
            painter.fillRect(r, selected_fill if is_sel else default_fill)
            painter.drawRect(r)

            # Vẽ số thứ tự vùng (1, 2, 3...)
            badge_rect = QRect(r.x() + 2, r.y() + 2, 18, 16)
            painter.fillRect(badge_rect, QColor(0, 0, 0, 180))
            painter.setPen(QColor(tokens.WARNING if is_sel else tokens.TEXT_ON_ACCENT))
            painter.drawText(badge_rect, Qt.AlignCenter, str(i + 1))

        if self._drag_current is not None:
            painter.setPen(QPen(QColor(tokens.PREVIEW_BLUR_EDGE), 2, Qt.DashLine))
            painter.drawRect(self._drag_current)

        self._paint_logo(painter, pr)
        self._paint_watermark(painter, pr)
        self._paint_subtitle(painter, pr)

    def _paint_logo(self, painter: QPainter, pr: QRect) -> None:
        """Vẽ logo xem trước trên canvas."""
        if not self._logo_opts or not self._logo_opts.get("enabled"):
            return
        path = str(self._logo_opts.get("path", "")).strip()
        scale = float(self._logo_opts.get("scale", 0.12))
        opacity = float(self._logo_opts.get("opacity", 0.85))
        pos = str(self._logo_opts.get("position", "top_right"))
        motion = str(self._logo_opts.get("motion", "static"))
        margin = max(8, int(pr.width() * 0.025))

        target_w = max(24, int(pr.width() * scale))

        painter.save()
        painter.setOpacity(max(0.1, min(1.0, opacity)))

        pix = QPixmap(path) if (path and os.path.exists(path)) else None
        if pix and not pix.isNull():
            scaled_pix = pix.scaledToWidth(target_w, Qt.SmoothTransformation)
            pw, ph = scaled_pix.width(), scaled_pix.height()
        else:
            pw = target_w
            ph = int(target_w * 0.6)
            scaled_pix = None

        if motion == "bounce":
            lx = pr.x() + int(pr.width() * 0.35)
            ly = pr.y() + int(pr.height() * 0.15)
        elif pos == "top_left":
            lx = pr.x() + margin
            ly = pr.y() + margin
        elif pos == "bottom_left":
            lx = pr.x() + margin
            ly = pr.bottom() - ph - margin
        elif pos == "bottom_right":
            lx = pr.right() - pw - margin
            ly = pr.bottom() - ph - margin
        else:  # top_right
            lx = pr.right() - pw - margin
            ly = pr.y() + margin

        if scaled_pix:
            painter.drawPixmap(lx, ly, scaled_pix)
        else:
            l_rect = QRect(lx, ly, pw, ph)
            painter.fillRect(l_rect, QColor(30, 35, 60, 200))
            painter.setPen(QPen(QColor(tokens.PRIMARY), 1, Qt.DashLine))
            painter.drawRect(l_rect)
            painter.setPen(QColor(tokens.TEXT_PRIMARY))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(l_rect, Qt.AlignCenter, "LOGO")

        painter.setOpacity(0.9)
        painter.setPen(QPen(QColor(tokens.PRIMARY), 1, Qt.DotLine))
        painter.drawRect(QRect(lx - 2, ly - 2, pw + 4, ph + 4))

        painter.restore()

    def _paint_watermark(self, painter: QPainter, pr: QRect) -> None:
        """Vẽ watermark chìm xem trước trên canvas."""
        if not self._wm_opts or not self._wm_opts.get("enabled"):
            return
        text = str(self._wm_opts.get("text", "")).strip()
        if not text:
            return
        opacity = float(self._wm_opts.get("opacity", 0.28))
        font_size = int(self._wm_opts.get("font_size", 26))
        scale = self._ass_scale()
        motion = str(self._wm_opts.get("motion", "bounce"))

        painter.save()
        painter.setOpacity(max(0.05, min(1.0, opacity)))

        wm_font = QFont("Arial", max(9, int(font_size * scale * 0.7)), QFont.Bold)
        painter.setFont(wm_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY))

        if motion == "bounce":
            painter.drawText(pr, Qt.AlignCenter, text)
        elif motion == "top_left":
            painter.drawText(pr.adjusted(24, 24, -24, -24), Qt.AlignTop | Qt.AlignLeft, text)
        elif motion == "bottom_left":
            painter.drawText(pr.adjusted(24, 24, -24, -24), Qt.AlignBottom | Qt.AlignLeft, text)
        elif motion == "bottom_right":
            painter.drawText(pr.adjusted(24, 24, -24, -24), Qt.AlignBottom | Qt.AlignRight, text)
        else:  # top_right
            painter.drawText(pr.adjusted(24, 24, -24, -24), Qt.AlignTop | Qt.AlignRight, text)

        painter.restore()

    def _paint_subtitle(self, painter: QPainter, pr: QRect) -> None:
        """Render the preview line exactly as ffmpeg/libass would place it."""
        s = self._style
        scale = self._ass_scale()

        font = QFont(s.get("font", "Arial"))
        font.setPixelSize(max(6, round(int(s.get("font_size", 22)) * scale)))
        font.setBold(bool(s.get("bold", True)))

        preview = (PREVIEW_TEXT_KARAOKE
                   if s.get("display") == "karaoke" else PREVIEW_TEXT)
        if s.get("all_caps"):
            preview = preview.upper()
        path = QPainterPath()
        path.addText(0, 0, font, preview)
        bounds = path.boundingRect()

        margin_px = int(s.get("margin_v", 40)) * scale
        x = pr.x() + (pr.width() - bounds.width()) / 2
        position = s.get("position", "bottom")
        if position == "top":
            top = pr.y() + margin_px
        elif position == "middle":
            top = pr.y() + (pr.height() - bounds.height()) / 2
        else:
            top = pr.bottom() - margin_px - bounds.height()
        dx, dy = x - bounds.x(), top - bounds.y()
        path.translate(dx, dy)
        self._text_rect = path.boundingRect()

        # Khối nền sau chữ (BorderStyle=4 của libass): vẽ TRƯỚC chữ, chừa
        # đệm quanh chữ như libass chừa theo Outline.
        if s.get("box") == "box":
            pad = max(4.0, int(s.get("outline", 2)) * scale * 2)
            box_rect = self._text_rect.adjusted(-pad, -pad, pad, pad)
            box_color = QColor(s.get("box_color", tokens.SUBTITLE_BOXFILL_DEFAULT))
            opacity = int(s.get("box_opacity", 60))
            box_color.setAlpha(round(255 * max(0, min(opacity, 100)) / 100))
            painter.setPen(Qt.NoPen)
            painter.fillRect(box_rect, box_color)

        # Bóng đổ: libass dịch chữ màu viền xuống dưới-phải Shadow điểm ảnh.
        shadow_px = int(s.get("shadow", 0)) * scale
        if shadow_px > 0 and s.get("box") != "box":
            sh = QPainterPath(path)
            sh.translate(shadow_px, shadow_px)
            shadow_color = QColor(s.get("outline_color", tokens.SUBTITLE_OUTLINE_DEFAULT))
            shadow_color.setAlpha(160)
            painter.setPen(Qt.NoPen)
            painter.fillPath(sh, shadow_color)

        outline_px = int(s.get("outline", 2)) * scale * 2
        if outline_px > 0 and s.get("box") != "box":
            painter.setPen(QPen(QColor(s.get("outline_color", tokens.SUBTITLE_OUTLINE_DEFAULT)),
                                outline_px, Qt.SolidLine, Qt.RoundCap,
                                Qt.RoundJoin))
            painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, QColor(s.get("color", tokens.SUBTITLE_TEXT_DEFAULT)))

        # Karaoke đổi màu: minh hoạ chữ đầu cụm đang được "đọc" — vẽ đè
        # bằng màu highlight với CÙNG phép dịch (dx, dy) của dòng chính,
        # nên chữ đè khít lên chữ gốc.
        if s.get("display") == "karaoke" and s.get("effect") == "karaoke":
            hi = QPainterPath()
            hi.addText(0, 0, font, preview.split()[0])
            hi.translate(dx, dy)
            painter.fillPath(hi, QColor(s.get("highlight_color", tokens.SUBTITLE_HIGHLIGHT_DEFAULT)))


def _placeholder_frame() -> QPixmap:
    """A neutral 16:9 frame used when no video is available yet."""
    pm = QPixmap(1280, 720)
    pm.fill(QColor(tokens.PREVIEW_EMPTY_BG))
    painter = QPainter(pm)
    painter.setPen(QColor(tokens.PREVIEW_EMPTY_TEXT))
    f = QFont("Arial")
    f.setPixelSize(40)
    painter.setFont(f)
    painter.drawText(pm.rect(), Qt.AlignCenter,
                     "(Chưa có video — xem trước phụ đề trên nền mẫu)")
    painter.end()
    return pm


class StyleDialog(QDialog):
    """Style the subtitles, blur regions, logo and dynamic watermark in one place."""

    def __init__(self, video_path: str | None, style: dict,
                 regions: list[dict] | None = None, parent=None,
                 preview_text: str = "",
                 logo_options: dict | None = None,
                 watermark_options: dict | None = None,
                 reframe_options: dict | None = None,
                 sfx_options: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Phụ đề & hiệu ứng video")
        self.resize(1180, 720)
        self.setMinimumSize(1080, 640)
        self._style = dict(style)
        self._logo_opts = dict(logo_options or {})
        self._wm_opts = dict(watermark_options or {})
        self._reframe_opts = dict(reframe_options or {})
        self._sfx_opts = dict(sfx_options or {})
        self._video_path = video_path
        self._regions_pending = regions
        self._frame_worker = None

        if preview_text:
            global PREVIEW_TEXT, PREVIEW_TEXT_KARAOKE  # noqa: PLW0603
            PREVIEW_TEXT = preview_text
            words = preview_text.split()
            PREVIEW_TEXT_KARAOKE = " ".join(words[:3]) if len(words) >= 3 else preview_text

        has_video = bool(video_path)
        pixmap = _placeholder_frame()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # --- Left: canvas (6 phần) ---
        left = QVBoxLayout()
        left.setSpacing(6)
        self.canvas = _FrameCanvas(pixmap, self._style, allow_regions=True)
        self.canvas.on_style_dragged = self._on_canvas_drag
        left.addWidget(self.canvas, 1)

        # Thanh điều khiển phát video (Live Video Playback)
        self._player: QMediaPlayer | None = None
        self._audio_output: QAudioOutput | None = None
        self._video_sink: QVideoSink | None = None
        self._duration_ms = 0

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        self.btn_play = QPushButton("▶ Phát")
        self.btn_play.setFixedWidth(75)
        self.btn_play.clicked.connect(self._toggle_playback)
        self.slider_pos = QSlider(Qt.Horizontal)
        self.slider_pos.setRange(0, 1000)
        self.slider_pos.sliderMoved.connect(self._on_seek)
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setMinimumWidth(85)
        controls_row.addWidget(self.btn_play)
        controls_row.addWidget(self.slider_pos, 1)
        controls_row.addWidget(self.lbl_time)
        left.addLayout(controls_row)

        if has_video and os.path.isfile(str(video_path)):
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._video_sink = QVideoSink(self)
            self._player.setVideoSink(self._video_sink)
            self._video_sink.videoFrameChanged.connect(self._on_video_frame)
            self._player.positionChanged.connect(self._on_player_position)
            self._player.durationChanged.connect(self._on_player_duration)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._player.setSource(QUrl.fromLocalFile(os.path.abspath(str(video_path))))
            self._player.setPosition(0)
        else:
            self.btn_play.setEnabled(False)
            self.slider_pos.setEnabled(False)

        hint = QLabel(
            "Kéo dòng phụ đề để đặt vị trí. "
            "Kéo chuột trên hình để khoanh vùng che chữ (làm mờ suốt video)."
            + ("" if has_video else
               " Đang dùng khung mẫu — vùng che sẽ áp đúng lên video khi xử lý."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        body.addLayout(left, 6)

        # --- Right: Tabbed Panel (4 phần) ---
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(420)
        self.tabs.setMaximumWidth(480)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {tokens.BORDER_SUBTLE}; background: {tokens.BG_PANEL}; border-radius: 6px; }} "
            f"QTabBar::tab {{ background: {tokens.BG_INPUT}; color: {tokens.TEXT_MUTED}; padding: 8px 14px; font-weight: 600; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; }} "
            f"QTabBar::tab:selected {{ background: {tokens.BG_PANEL}; color: {tokens.TEXT_PRIMARY}; border: 1px solid {tokens.BORDER_SUBTLE}; border-bottom: none; }} "
            f"QTabBar::tab:hover {{ background: {tokens.BG_PANEL_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )

        # ================================= TAB 1: KIỂU CHỮ ================================= #
        tab_font_scroll = QScrollArea()
        tab_font_scroll.setWidgetResizable(True)
        tab_font_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_font_w = QWidget()
        panel_l = QVBoxLayout(tab_font_w)
        panel_l.setContentsMargins(10, 10, 10, 10)
        panel_l.setSpacing(8)

        def _section(title: str) -> None:
            if panel_l.count():
                panel_l.addSpacing(10)
            lb = QLabel(title)
            lb.setObjectName("sectionHeader")
            panel_l.addWidget(lb)

        _section("Phông chữ & Vị trí")
        f = QFormLayout()
        f.setContentsMargins(0, 0, 0, 0)
        f.setLabelAlignment(Qt.AlignRight)
        f.setSpacing(7)
        panel_l.addLayout(f)

        self.cb_font = QComboBox()
        self._populate_fonts()
        self.cb_font.setToolTip(
            "Font trong nhóm 'Font của app' hiển thị đúng trên video ở mọi máy.")
        self.btn_fonts_dir = QPushButton("+")
        self.btn_fonts_dir.setFixedWidth(28)
        self.btn_fonts_dir.setToolTip("Thêm font: mở thư mục font của app.")
        self.btn_fonts_dir.clicked.connect(self._open_fonts_dir)
        font_row = QHBoxLayout()
        font_row.setSpacing(4)
        font_row.addWidget(self.cb_font, 1)
        font_row.addWidget(self.btn_fonts_dir)

        self.sp_size = QSpinBox()
        self.sp_size.setRange(8, 120)
        self.sp_size.setToolTip("Cỡ chữ — tự co giãn theo độ phân giải video")
        self.sp_outline = QSpinBox()
        self.sp_outline.setRange(0, 10)
        self.sp_outline.setToolTip("Độ dày viền quanh chữ")

        size_row = QHBoxLayout()
        size_row.setSpacing(4)
        size_row.addWidget(self.sp_size, 1)
        lbl_out = QLabel("Viền")
        lbl_out.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        size_row.addWidget(lbl_out)
        size_row.addWidget(self.sp_outline, 1)

        self.chk_bold = QCheckBox("Chữ đậm")
        self.sp_shadow = QSpinBox()
        self.sp_shadow.setRange(0, 10)
        self.sp_shadow.setToolTip("Độ lệch bóng đổ (pixel theo độ phân giải 288p)")
        bold_row = QHBoxLayout()
        bold_row.setSpacing(4)
        bold_row.addWidget(self.chk_bold, 1)
        lbl_sh = QLabel("Bóng")
        lbl_sh.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        bold_row.addWidget(lbl_sh)
        bold_row.addWidget(self.sp_shadow, 1)

        self.btn_color = QPushButton()
        self.btn_color.setToolTip("Màu chữ chính")
        self.btn_color.clicked.connect(lambda: self._pick_color("color"))
        self.btn_outline_color = QPushButton()
        self.btn_outline_color.setToolTip("Màu viền quanh chữ")
        self.btn_outline_color.clicked.connect(lambda: self._pick_color("outline_color"))
        color_row = QHBoxLayout()
        color_row.setSpacing(4)
        color_row.addWidget(self.btn_color, 1)
        color_row.addWidget(self.btn_outline_color, 1)

        self.cb_pos = QComboBox()
        for label, val in _POSITIONS:
            self.cb_pos.addItem(label, val)
        polish_combo(self.cb_pos)
        self.sp_margin = QSpinBox()
        self.sp_margin.setRange(0, 200)
        self.sp_margin.setToolTip("Khoảng cách từ mép video tới chữ (pixel)")
        pos_row = QHBoxLayout()
        pos_row.setSpacing(4)
        pos_row.addWidget(self.cb_pos, 1)
        lbl_mg = QLabel("Lề")
        lbl_mg.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        pos_row.addWidget(lbl_mg)
        pos_row.addWidget(self.sp_margin, 1)

        self.cb_box = QComboBox()
        for label, val in _BOXES:
            self.cb_box.addItem(label, val)
        polish_combo(self.cb_box)
        self.btn_box_color = QPushButton()
        self.btn_box_color.setToolTip("Màu của khối nền phía sau chữ")
        self.btn_box_color.clicked.connect(lambda: self._pick_color("box_color"))
        self.sp_box_opacity = QSpinBox()
        self.sp_box_opacity.setRange(0, 100)
        self.sp_box_opacity.setSuffix(" %")
        self.sp_box_opacity.setToolTip("Độ đậm của khối nền (100% = đục hoàn toàn)")

        box_color_row = QHBoxLayout()
        box_color_row.setSpacing(4)
        box_color_row.addWidget(self.btn_box_color, 1)
        lbl_duc = QLabel("Đục")
        lbl_duc.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        box_color_row.addWidget(lbl_duc)
        box_color_row.addWidget(self.sp_box_opacity, 1)

        f.addRow("Font:", font_row)
        f.addRow("Cỡ chữ:", size_row)
        f.addRow("Đậm / bóng:", bold_row)
        f.addRow("Màu / viền:", color_row)
        f.addRow("Vị trí:", pos_row)
        f.addRow("Nền chữ:", self.cb_box)
        f.addRow("Màu nền:", box_color_row)

        _section("Cách hiện chữ")
        f2 = QFormLayout()
        f2.setContentsMargins(0, 0, 0, 0)
        f2.setLabelAlignment(Qt.AlignRight)
        f2.setSpacing(7)
        panel_l.addLayout(f2)

        self.cb_display = QComboBox()
        for label, val in _DISPLAYS:
            self.cb_display.addItem(label, val)
        polish_combo(self.cb_display)
        self.cb_display.setToolTip(
            "Cả câu: hiện trọn câu một lần (kiểu chuẩn).\n"
            "Cụm chữ theo giọng đọc: chữ nhảy theo từng cụm ngắn khớp nhịp nói.")

        self.sp_line_words = QSpinBox()
        self.sp_line_words.setRange(1, 20)
        self.sp_line_words.setToolTip("Số chữ trên mỗi dòng trước khi xuống dòng")
        self.sp_max_lines = QSpinBox()
        self.sp_max_lines.setRange(1, 4)
        self.sp_max_lines.setToolTip("Số dòng tối đa trên màn hình cùng lúc")

        words_row = QHBoxLayout()
        words_row.setSpacing(4)
        words_row.addWidget(self.sp_line_words, 1)
        lbl_td = QLabel("Tối đa")
        lbl_td.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        words_row.addWidget(lbl_td)
        words_row.addWidget(self.sp_max_lines, 1)

        self.chk_all_caps = QCheckBox("Viết hoa toàn bộ")

        self.cb_effect = QComboBox()
        for label, val in _EFFECTS:
            self.cb_effect.addItem(label, val)
        polish_combo(self.cb_effect)

        self.sp_words = QSpinBox()
        self.sp_words.setRange(1, 20)
        self.sp_words.setToolTip("Số chữ hiện trong mỗi cụm")
        self.btn_highlight = QPushButton()
        self.btn_highlight.setToolTip("Màu nhấn cho chữ đang nói")
        self.btn_highlight.clicked.connect(lambda: self._pick_color("highlight_color"))

        cue_row = QHBoxLayout()
        cue_row.setSpacing(4)
        cue_row.addWidget(self.sp_words, 1)
        lbl_nhan = QLabel("Màu nhấn")
        lbl_nhan.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        cue_row.addWidget(lbl_nhan)
        cue_row.addWidget(self.btn_highlight, 1)

        f2.addRow("Hiển thị:", self.cb_display)
        f2.addRow("Chữ mỗi hàng:", words_row)
        f2.addRow("", self.chk_all_caps)
        f2.addRow("Hiệu ứng:", self.cb_effect)
        f2.addRow("Chữ mỗi lần:", cue_row)

        panel_l.addStretch()
        tab_font_scroll.setWidget(tab_font_w)
        self.tabs.addTab(tab_font_scroll, "Kiểu chữ")

        # ================================= TAB 2: VÙNG CHE ================================= #
        tab_blur_scroll = QScrollArea()
        tab_blur_scroll.setWidgetResizable(True)
        tab_blur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_blur_w = QWidget()
        blur_l = QVBoxLayout(tab_blur_w)
        blur_l.setContentsMargins(10, 10, 10, 10)
        blur_l.setSpacing(10)

        lbl_blur_title = QLabel("Mẫu vùng che nhanh")
        lbl_blur_title.setObjectName("sectionHeader")
        blur_l.addWidget(lbl_blur_title)

        p_row1 = QHBoxLayout()
        p_row1.setSpacing(4)
        self.btn_pre_bot = QPushButton("+ Dải đáy")
        self.btn_pre_bot.setToolTip("Che dải phụ đề đáy màn hình (100% x 16%)")
        self.btn_pre_bot.clicked.connect(lambda: self.canvas.add_preset_region("bottom_band"))
        self.btn_pre_top = QPushButton("+ Dải đỉnh")
        self.btn_pre_top.setToolTip("Che dải phụ đề đỉnh màn hình (100% x 15%)")
        self.btn_pre_top.clicked.connect(lambda: self.canvas.add_preset_region("top_band"))
        self.btn_pre_tr = QPushButton("+ Góc phải")
        self.btn_pre_tr.setToolTip("Che logo/watermark góc trên bên phải (24% x 14%)")
        self.btn_pre_tr.clicked.connect(lambda: self.canvas.add_preset_region("top_right_logo"))
        self.btn_pre_tl = QPushButton("+ Góc trái")
        self.btn_pre_tl.setToolTip("Che logo góc trên bên trái (24% x 14%)")
        self.btn_pre_tl.clicked.connect(lambda: self.canvas.add_preset_region("top_left_logo"))

        p_row1.addWidget(self.btn_pre_bot)
        p_row1.addWidget(self.btn_pre_top)
        p_row1.addWidget(self.btn_pre_tr)
        p_row1.addWidget(self.btn_pre_tl)
        blur_l.addLayout(p_row1)

        self.lbl_regions_count = QLabel("Danh sách vùng làm mờ (0 vùng):")
        self.lbl_regions_count.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 12px; margin-top: 4px;")
        blur_l.addWidget(self.lbl_regions_count)

        self.list_regions = QListWidget()
        self.list_regions.setFixedHeight(120)
        self.list_regions.setStyleSheet(
            f"background: {tokens.BG_PANEL}; border: 1px solid {tokens.BORDER_DEFAULT}; border-radius: 4px; padding: 2px;"
        )
        self.list_regions.currentRowChanged.connect(self._on_region_selected)
        blur_l.addWidget(self.list_regions)

        b = QHBoxLayout()
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(4)
        blur_l.addLayout(b)
        self.btn_auto_detect = QPushButton("Dò tự động")
        self.btn_auto_detect.setToolTip("Quét video tự động tìm và khoanh vùng phụ đề cứng gốc")
        self.btn_auto_detect.clicked.connect(self._on_auto_detect_clicked)

        self.btn_del_sel = QPushButton("Xoá vùng chọn")
        self.btn_del_sel.setToolTip("Xoá vùng làm mờ đang được chọn trong danh sách")
        self.btn_del_sel.clicked.connect(self._delete_selected_region)

        self.btn_clear = QPushButton("Xoá tất cả")
        self.btn_clear.clicked.connect(self.canvas.clear_all)

        b.addWidget(self.btn_auto_detect)
        b.addWidget(self.btn_del_sel)
        b.addWidget(self.btn_clear)

        self.canvas.on_regions_changed = self._sync_regions_list
        blur_l.addStretch()
        tab_blur_scroll.setWidget(tab_blur_w)
        self.tabs.addTab(tab_blur_scroll, "Vùng che (Blur)")

        # ================================= TAB 3: LOGO & WATERMARK ================================= #
        tab_lw_scroll = QScrollArea()
        tab_lw_scroll.setWidgetResizable(True)
        tab_lw_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_lw_w = QWidget()
        lw_l = QVBoxLayout(tab_lw_w)
        lw_l.setContentsMargins(10, 10, 10, 10)
        lw_l.setSpacing(8)

        # 1. Logo thương hiệu
        lbl_logo_header = QLabel("Logo thương hiệu")
        lbl_logo_header.setObjectName("sectionHeader")
        lw_l.addWidget(lbl_logo_header)

        self.chk_logo_enabled = QCheckBox("Hiển thị logo trên video")
        lw_l.addWidget(self.chk_logo_enabled)

        f_logo = QFormLayout()
        f_logo.setContentsMargins(0, 0, 0, 0)
        f_logo.setLabelAlignment(Qt.AlignRight)
        f_logo.setSpacing(6)
        lw_l.addLayout(f_logo)

        self.txt_logo_path = QLineEdit()
        self.txt_logo_path.setPlaceholderText("Đường dẫn tệp ảnh PNG, JPG...")
        self.btn_browse_logo = QPushButton("Chọn…")
        self.btn_browse_logo.setFixedWidth(55)
        self.btn_browse_logo.clicked.connect(self._browse_logo_file)
        row_logo_f = QHBoxLayout()
        row_logo_f.setSpacing(4)
        row_logo_f.addWidget(self.txt_logo_path, 1)
        row_logo_f.addWidget(self.btn_browse_logo)
        f_logo.addRow("Tệp ảnh:", row_logo_f)

        self.cb_logo_pos = QComboBox()
        self.cb_logo_pos.addItem("Góc trên bên phải", "top_right")
        self.cb_logo_pos.addItem("Góc trên bên trái", "top_left")
        self.cb_logo_pos.addItem("Góc dưới bên phải", "bottom_right")
        self.cb_logo_pos.addItem("Góc dưới bên trái", "bottom_left")
        polish_combo(self.cb_logo_pos)
        f_logo.addRow("Vị trí:", self.cb_logo_pos)

        self.sp_logo_scale = QSpinBox()
        self.sp_logo_scale.setRange(4, 50)
        self.sp_logo_scale.setValue(12)
        self.sp_logo_scale.setSuffix(" %")

        self.sp_logo_opacity = QSpinBox()
        self.sp_logo_opacity.setRange(10, 100)
        self.sp_logo_opacity.setValue(85)
        self.sp_logo_opacity.setSuffix(" %")

        row_logo_dim = QHBoxLayout()
        row_logo_dim.setSpacing(4)
        row_logo_dim.addWidget(self.sp_logo_scale, 1)
        lbl_r = QLabel("Độ rõ")
        lbl_r.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        row_logo_dim.addWidget(lbl_r)
        row_logo_dim.addWidget(self.sp_logo_opacity, 1)
        f_logo.addRow("Kích thước:", row_logo_dim)

        self.cb_logo_motion = QComboBox()
        self.cb_logo_motion.addItem("Cố định vị trí", "static")
        self.cb_logo_motion.addItem("Chạy nảy mượt mà (Bouncing)", "bounce")
        polish_combo(self.cb_logo_motion)
        f_logo.addRow("Hiệu ứng:", self.cb_logo_motion)

        lw_l.addSpacing(10)

        # 2. Watermark chữ chìm
        lbl_wm_header = QLabel("Watermark chống reup")
        lbl_wm_header.setObjectName("sectionHeader")
        lw_l.addWidget(lbl_wm_header)

        self.chk_wm_enabled = QCheckBox("Hiển thị watermark chữ chìm")
        lw_l.addWidget(self.chk_wm_enabled)

        f_wm = QFormLayout()
        f_wm.setContentsMargins(0, 0, 0, 0)
        f_wm.setLabelAlignment(Qt.AlignRight)
        f_wm.setSpacing(6)
        lw_l.addLayout(f_wm)

        self.txt_wm_text = QLineEdit()
        self.txt_wm_text.setPlaceholderText("@KenhCuaBan, SĐT, hoặc ID...")
        f_wm.addRow("Chữ:", self.txt_wm_text)

        self.cb_wm_motion = QComboBox()
        self.cb_wm_motion.addItem("Chạy nảy quanh video (Khuyên dùng)", "bounce")
        self.cb_wm_motion.addItem("Cố định góc trên bên phải", "top_right")
        self.cb_wm_motion.addItem("Cố định góc trên bên trái", "top_left")
        self.cb_wm_motion.addItem("Cố định góc dưới bên phải", "bottom_right")
        self.cb_wm_motion.addItem("Cố định góc dưới bên trái", "bottom_left")
        polish_combo(self.cb_wm_motion)
        f_wm.addRow("Quỹ đạo:", self.cb_wm_motion)

        self.sp_wm_opacity = QSpinBox()
        self.sp_wm_opacity.setRange(5, 80)
        self.sp_wm_opacity.setValue(28)
        self.sp_wm_opacity.setSuffix(" %")

        self.sp_wm_font_size = QSpinBox()
        self.sp_wm_font_size.setRange(12, 72)
        self.sp_wm_font_size.setValue(26)
        self.sp_wm_font_size.setSuffix(" px")

        row_wm_spec = QHBoxLayout()
        row_wm_spec.setSpacing(4)
        row_wm_spec.addWidget(self.sp_wm_opacity, 1)
        lbl_c = QLabel("Cỡ")
        lbl_c.setStyleSheet(f"color: {tokens.TEXT_MUTED};")
        row_wm_spec.addWidget(lbl_c)
        row_wm_spec.addWidget(self.sp_wm_font_size, 1)
        f_wm.addRow("Độ mờ / Cỡ:", row_wm_spec)

        self.sp_wm_speed = QSpinBox()
        self.sp_wm_speed.setRange(10, 200)
        self.sp_wm_speed.setValue(40)
        self.sp_wm_speed.setSuffix(" px/s")
        f_wm.addRow("Tốc độ chạy:", self.sp_wm_speed)

        lw_l.addStretch()
        tab_lw_scroll.setWidget(tab_lw_w)
        self.tabs.addTab(tab_lw_scroll, "Logo & Watermark")

        # ================================= TAB 4: BỐ CỤC & HIỆU ỨNG ================================= #
        tab_fx_scroll = QScrollArea()
        tab_fx_scroll.setWidgetResizable(True)
        tab_fx_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_fx_w = QWidget()
        fx_l = QVBoxLayout(tab_fx_w)
        fx_l.setContentsMargins(10, 10, 10, 10)
        fx_l.setSpacing(8)

        def _fx_section(title: str) -> None:
            if fx_l.count():
                fx_l.addSpacing(10)
            lb = QLabel(title)
            lb.setObjectName("sectionHeader")
            fx_l.addWidget(lb)

        _fx_section("Tỷ lệ khung hình (Auto-Reframe)")
        f_reframe = QFormLayout()
        f_reframe.setContentsMargins(0, 0, 0, 0)
        f_reframe.setLabelAlignment(Qt.AlignRight)
        f_reframe.setSpacing(7)
        fx_l.addLayout(f_reframe)

        self.cb_aspect = QComboBox()
        self.cb_aspect.addItem("Giữ nguyên tỷ lệ gốc", "original")
        self.cb_aspect.addItem("TikTok / Shorts / Reels (9:16 dọc)", "tiktok_9_16")
        self.cb_aspect.addItem("YouTube ngang chuẩn (16:9)", "youtube_16_9")
        self.cb_aspect.addItem("Vuông Instagram / Facebook (1:1)", "square_1_1")
        polish_combo(self.cb_aspect)
        f_reframe.addRow("Tỷ lệ xuất:", self.cb_aspect)

        self.cb_reframe_mode = QComboBox()
        self.cb_reframe_mode.addItem("Mờ nền nghệ thuật (Blur Background)", "blur")
        self.cb_reframe_mode.addItem("Khung trên / Phụ đề dưới (Top-Split)", "top_split")
        self.cb_reframe_mode.addItem("Cắt vừa khít lấp đầy (Center Crop)", "center_crop")
        polish_combo(self.cb_reframe_mode)
        f_reframe.addRow("Kiểu căn chỉnh:", self.cb_reframe_mode)

        _fx_section("Âm thanh chuyển cảnh (Auto SFX)")
        f_sfx = QFormLayout()
        f_sfx.setContentsMargins(0, 0, 0, 0)
        f_sfx.setLabelAlignment(Qt.AlignRight)
        f_sfx.setSpacing(7)
        fx_l.addLayout(f_sfx)

        self.chk_auto_sfx = QCheckBox("Bật âm thanh chuyển cảnh tự động")
        self.chk_auto_sfx.setToolTip("Tự động chèn hiệu ứng âm thanh nhỏ khi video chuyển cảnh (Scene Cut)")
        f_sfx.addRow("", self.chk_auto_sfx)

        self.cb_sfx_preset = QComboBox()
        self.cb_sfx_preset.addItem("Whoosh (Vút gió êm dịu)", "whoosh")
        self.cb_sfx_preset.addItem("Pop (Tiếng pop hiện đại)", "pop")
        self.cb_sfx_preset.addItem("Swish (Lướt nhanh)", "swish")
        self.cb_sfx_preset.addItem("Cinematic (Trầm ấm điện ảnh)", "cinematic")
        polish_combo(self.cb_sfx_preset)
        f_sfx.addRow("Kiểu âm thanh:", self.cb_sfx_preset)

        self.sp_sfx_volume = QSpinBox()
        self.sp_sfx_volume.setRange(-30, 0)
        self.sp_sfx_volume.setValue(-14)
        self.sp_sfx_volume.setSuffix(" dB")
        self.sp_sfx_volume.setToolTip("Âm lượng âm thanh chuyển cảnh (-14 dB là mức êm dịu, không át tiếng nói)")
        f_sfx.addRow("Âm lượng SFX:", self.sp_sfx_volume)

        fx_l.addStretch()
        tab_fx_scroll.setWidget(tab_fx_w)
        self.tabs.addTab(tab_fx_scroll, "Bố cục & SFX")

        body.addWidget(self.tabs, 4)

        # --- Bottom: actions ---
        actions = QHBoxLayout()
        actions.addStretch()
        btn_cancel = QPushButton("Huỷ")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Xong")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self.accept)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        root.addLayout(actions)

        self._load_controls()
        self._connect_controls()
        if regions:
            # Defer until the canvas has its final size, then restore rects.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(
                0, lambda: self.canvas.set_rects_from_normalized(regions))

        # Bắt đầu trích xuất frame video trong luồng nền NGAY SAU KHI
        # dialog đã dựng xong — người dùng thấy dialog lập tức với placeholder,
        # frame thật thay thế khi ffmpeg xong (thường < 2 giây).
        if has_video:
            self._start_frame_extract(video_path)

    def _start_frame_extract(self, video_path: str) -> None:
        """Trích xuất frame từ video trong luồng nền."""
        tmp_png = os.path.join(tempfile.gettempdir(), "autodub_style_frame.png")
        worker = _FrameWorker(video_path, tmp_png, at_seconds=1.0, parent=self)
        worker.ready.connect(self._on_frame_ready)
        worker.failed.connect(self._on_frame_failed)
        self._frame_worker = worker
        worker.start()

    def _on_frame_ready(self, path: str) -> None:
        """Cập nhật canvas với frame thật vừa trích xuất xong."""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.canvas._source = pixmap
        self.canvas._scaled = pixmap.scaled(
            self.canvas.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation)
        self.canvas.update()
        # Khôi phục vùng blur lên frame thật nếu có
        if self._regions_pending:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(
                0, lambda: self.canvas.set_rects_from_normalized(
                    self._regions_pending))

    def _sync_regions_list(self, regions: list[dict]) -> None:
        """Đồng bộ danh sách các vùng làm mờ vào QListWidget."""
        self.list_regions.blockSignals(True)
        self.list_regions.clear()
        count = len(regions)
        if count == 0:
            self.lbl_regions_count.setText("Danh sách vùng làm mờ (0 vùng):")
            self.lbl_regions_count.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 12px; margin-top: 4px;")
        else:
            self.lbl_regions_count.setText(f"Danh sách vùng làm mờ ({count} vùng):")
            self.lbl_regions_count.setStyleSheet(f"color: {tokens.WARNING}; font-weight: bold; font-size: 12px; margin-top: 4px;")

        for i, r in enumerate(regions):
            x_pct = int(round(float(r.get("x", 0)) * 100))
            y_pct = int(round(float(r.get("y", 0)) * 100))
            w_pct = int(round(float(r.get("w", 0)) * 100))
            h_pct = int(round(float(r.get("h", 0)) * 100))
            desc = f"Vùng {i + 1}: x={x_pct}%, y={y_pct}%, rộng={w_pct}%, cao={h_pct}%"
            item = QListWidgetItem(desc)
            self.list_regions.addItem(item)

        if self.canvas._selected_index is not None and 0 <= self.canvas._selected_index < count:
            self.list_regions.setCurrentRow(self.canvas._selected_index)
        self.list_regions.blockSignals(False)

    def _on_region_selected(self, row: int) -> None:
        if row >= 0:
            self.canvas.select_region(row)
        else:
            self.canvas.select_region(None)

    def _delete_selected_region(self) -> None:
        row = self.list_regions.currentRow()
        if row >= 0:
            self.canvas.remove_region(row)
        else:
            self.canvas.clear_last()

    def _on_frame_failed(self, message: str) -> None:
        """Hiện cảnh báo nhẹ; không đóng dialog — phụ đề vẫn chỉnh được."""
        from autodub_gui.ui.toast import TOASTS
        TOASTS.warn(f"Không lấy được frame video: {message}")

    def _on_auto_detect_clicked(self) -> None:
        """Tự động quét video để tìm dải phụ đề cứng gốc."""
        if not self._video_path or not os.path.exists(self._video_path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Tự động dò phụ đề",
                "Cần có tệp video nguồn trên máy để thực hiện quét tự động."
            )
            return

        from autodub.media.hardsub_detector import detect_hardsub_regions
        self.btn_auto_detect.setEnabled(False)
        self.btn_auto_detect.setText("Đang dò...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            regs = detect_hardsub_regions(self._video_path)
            if regs:
                self.canvas.set_rects_from_normalized(regs)
                from autodub_gui.ui.toast import TOASTS
                TOASTS.info(f"Đã phát hiện {len(regs)} vùng phụ đề cứng.")
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Tự động dò phụ đề",
                    "Không phát hiện thấy dải phụ đề cứng cố định nào trong video."
                )
        except Exception as e:
            from autodub_gui.ui.toast import TOASTS
            TOASTS.warn(f"Lỗi khi quét phụ đề: {e}")
        finally:
            self.btn_auto_detect.setEnabled(True)
            self.btn_auto_detect.setText("Dò tự động")



    # ------------------------------------------------------- controls ----- #

    def _load_controls(self) -> None:
        s = self._style
        d_idx = self.cb_display.findData(s.get("display", "sentence"))
        self.cb_display.setCurrentIndex(d_idx if d_idx >= 0 else 0)
        self.sp_line_words.setValue(int(s.get("line_words", 0) or 0))
        self.sp_max_lines.setValue(int(s.get("max_lines", 2)))
        self.chk_all_caps.setChecked(bool(s.get("all_caps", False)))
        e_idx = self.cb_effect.findData(s.get("effect", "pop"))
        self.cb_effect.setCurrentIndex(e_idx if e_idx >= 0 else 0)
        self.sp_words.setValue(int(s.get("words_per_cue", 3)))
        self._paint_color_button(self.btn_highlight,
                                 s.get("highlight_color", tokens.SUBTITLE_HIGHLIGHT_DEFAULT))
        idx = self.cb_pos.findData(s.get("position", "bottom"))
        self.cb_pos.setCurrentIndex(idx if idx >= 0 else 0)
        self._select_font(s.get("font", "Arial"))
        self.sp_size.setValue(int(s.get("font_size", 22)))
        self.sp_margin.setValue(int(s.get("margin_v", 40)))
        self.sp_outline.setValue(int(s.get("outline", 2)))
        self.sp_shadow.setValue(int(s.get("shadow", 0)))
        self.chk_bold.setChecked(bool(s.get("bold", True)))
        b_idx = self.cb_box.findData(s.get("box", "none"))
        self.cb_box.setCurrentIndex(b_idx if b_idx >= 0 else 0)
        self.sp_box_opacity.setValue(int(s.get("box_opacity", 60)))
        self._paint_color_button(self.btn_box_color,
                                 s.get("box_color", tokens.SUBTITLE_BOXFILL_DEFAULT))
        self._paint_color_button(self.btn_color, s.get("color", tokens.SUBTITLE_TEXT_DEFAULT))
        self._paint_color_button(self.btn_outline_color,
                                 s.get("outline_color", tokens.SUBTITLE_OUTLINE_DEFAULT))
        self._update_karaoke_enabled()
        self._update_box_enabled()

        # Logo controls
        logo_path = str(self._logo_opts.get("logo_path") or self._logo_opts.get("path") or "").strip()
        self.txt_logo_path.setText(logo_path)
        self.chk_logo_enabled.setChecked(bool(logo_path or self._logo_opts.get("enabled", False)))
        l_pos = self._logo_opts.get("logo_position") or self._logo_opts.get("position", "top_right")
        l_pos_idx = self.cb_logo_pos.findData(l_pos)
        self.cb_logo_pos.setCurrentIndex(l_pos_idx if l_pos_idx >= 0 else 0)
        l_scale = int(round(float(self._logo_opts.get("logo_scale", self._logo_opts.get("scale", 0.12))) * 100))
        self.sp_logo_scale.setValue(max(4, min(50, l_scale)))
        l_op = int(round(float(self._logo_opts.get("logo_opacity", self._logo_opts.get("opacity", 0.85))) * 100))
        self.sp_logo_opacity.setValue(max(10, min(100, l_op)))
        l_motion = self._logo_opts.get("logo_motion") or self._logo_opts.get("motion", "static")
        l_mot_idx = self.cb_logo_motion.findData(l_motion)
        self.cb_logo_motion.setCurrentIndex(l_mot_idx if l_mot_idx >= 0 else 0)

        # Watermark controls
        wm_text = str(self._wm_opts.get("watermark_text") or self._wm_opts.get("text") or "").strip()
        self.txt_wm_text.setText(wm_text)
        self.chk_wm_enabled.setChecked(bool(wm_text or self._wm_opts.get("enabled", False)))
        wm_mot = self._wm_opts.get("watermark_motion") or self._wm_opts.get("motion", "bounce")
        wm_mot_idx = self.cb_wm_motion.findData(wm_mot)
        self.cb_wm_motion.setCurrentIndex(wm_mot_idx if wm_mot_idx >= 0 else 0)
        wm_op = int(round(float(self._wm_opts.get("watermark_opacity", self._wm_opts.get("opacity", 0.28))) * 100))
        self.sp_wm_opacity.setValue(max(5, min(80, wm_op)))
        self.sp_wm_font_size.setValue(int(self._wm_opts.get("watermark_font_size", self._wm_opts.get("font_size", 26))))
        self.sp_wm_speed.setValue(int(self._wm_opts.get("watermark_speed", self._wm_opts.get("speed", 40))))

        # Reframe & SFX controls
        asp = self._reframe_opts.get("aspect_preset", "original")
        asp_idx = self.cb_aspect.findData(asp)
        self.cb_aspect.setCurrentIndex(asp_idx if asp_idx >= 0 else 0)
        ref_mode = self._reframe_opts.get("reframe_mode", "blur")
        ref_idx = self.cb_reframe_mode.findData(ref_mode)
        self.cb_reframe_mode.setCurrentIndex(ref_idx if ref_idx >= 0 else 0)

        self.chk_auto_sfx.setChecked(bool(self._sfx_opts.get("auto_sfx_enabled", False)))
        sfx_p = self._sfx_opts.get("sfx_preset", "whoosh")
        sfx_p_idx = self.cb_sfx_preset.findData(sfx_p)
        self.cb_sfx_preset.setCurrentIndex(sfx_p_idx if sfx_p_idx >= 0 else 0)
        sfx_v = int(round(float(self._sfx_opts.get("sfx_volume_db", -14.0))))
        self.sp_sfx_volume.setValue(max(-30, min(0, sfx_v)))

        self._sync_logo_wm_from_controls()

    def _connect_controls(self) -> None:
        self.cb_display.currentIndexChanged.connect(self._sync_from_controls)
        self.sp_line_words.valueChanged.connect(self._sync_from_controls)
        self.sp_max_lines.valueChanged.connect(self._sync_from_controls)
        self.chk_all_caps.toggled.connect(self._sync_from_controls)
        self.cb_effect.currentIndexChanged.connect(self._sync_from_controls)
        self.sp_words.valueChanged.connect(self._sync_from_controls)
        self.cb_pos.currentIndexChanged.connect(self._sync_from_controls)
        self.cb_font.currentIndexChanged.connect(self._sync_from_controls)
        self.sp_size.valueChanged.connect(self._sync_from_controls)
        self.sp_margin.valueChanged.connect(self._sync_from_controls)
        self.sp_outline.valueChanged.connect(self._sync_from_controls)
        self.sp_shadow.valueChanged.connect(self._sync_from_controls)
        self.chk_bold.toggled.connect(self._sync_from_controls)
        self.cb_box.currentIndexChanged.connect(self._sync_from_controls)
        self.sp_box_opacity.valueChanged.connect(self._sync_from_controls)

        self.chk_logo_enabled.toggled.connect(self._sync_logo_wm_from_controls)
        self.txt_logo_path.textChanged.connect(self._sync_logo_wm_from_controls)
        self.cb_logo_pos.currentIndexChanged.connect(self._sync_logo_wm_from_controls)
        self.sp_logo_scale.valueChanged.connect(self._sync_logo_wm_from_controls)
        self.sp_logo_opacity.valueChanged.connect(self._sync_logo_wm_from_controls)
        self.cb_logo_motion.currentIndexChanged.connect(self._sync_logo_wm_from_controls)

        self.chk_wm_enabled.toggled.connect(self._sync_logo_wm_from_controls)
        self.txt_wm_text.textChanged.connect(self._sync_logo_wm_from_controls)
        self.cb_wm_motion.currentIndexChanged.connect(self._sync_logo_wm_from_controls)
        self.sp_wm_opacity.valueChanged.connect(self._sync_logo_wm_from_controls)
        self.sp_wm_font_size.valueChanged.connect(self._sync_logo_wm_from_controls)
        self.sp_wm_speed.valueChanged.connect(self._sync_logo_wm_from_controls)

    def _browse_logo_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn hình ảnh Logo / Watermark", "",
            "Hình ảnh (*.png *.jpg *.jpeg *.webp *.svg);;Tất cả tệp (*.*)")
        if path:
            self.txt_logo_path.setText(path)
            self.chk_logo_enabled.setChecked(True)
            self._sync_logo_wm_from_controls()

    def _sync_logo_wm_from_controls(self, *_args) -> None:
        self._logo_opts = {
            "enabled": self.chk_logo_enabled.isChecked(),
            "path": self.txt_logo_path.text().strip(),
            "position": self.cb_logo_pos.currentData() or "top_right",
            "scale": self.sp_logo_scale.value() / 100.0,
            "opacity": self.sp_logo_opacity.value() / 100.0,
            "motion": self.cb_logo_motion.currentData() or "static",
        }
        self._wm_opts = {
            "enabled": self.chk_wm_enabled.isChecked(),
            "text": self.txt_wm_text.text().strip(),
            "motion": self.cb_wm_motion.currentData() or "bounce",
            "opacity": self.sp_wm_opacity.value() / 100.0,
            "font_size": self.sp_wm_font_size.value(),
            "speed": self.sp_wm_speed.value(),
        }
        self.canvas.set_logo_options(self._logo_opts)
        self.canvas.set_watermark_options(self._wm_opts)

    def _update_karaoke_enabled(self) -> None:
        karaoke = self.cb_display.currentData() == "karaoke"
        self.cb_effect.setEnabled(karaoke)
        self.sp_words.setEnabled(karaoke)
        # "Chữ mỗi hàng" là của chế độ CẢ CÂU — karaoke tự chia cụm riêng.
        self.sp_line_words.setEnabled(not karaoke)
        self.sp_max_lines.setEnabled(not karaoke)
        self.btn_highlight.setEnabled(
            karaoke and self.cb_effect.currentData() == "karaoke")

    def _update_box_enabled(self) -> None:
        """Nền chữ bật thì màu nền/độ đục dùng được; viền + bóng thì không
        (libass BorderStyle=4 bỏ qua Outline/Shadow khi có khối nền)."""
        boxed = self.cb_box.currentData() == "box"
        self.btn_box_color.setEnabled(boxed)
        self.sp_box_opacity.setEnabled(boxed)
        self.sp_outline.setEnabled(not boxed)
        self.sp_shadow.setEnabled(not boxed)
        self.btn_outline_color.setEnabled(not boxed)

    def _sync_from_controls(self, *_args) -> None:
        font = self.cb_font.currentData()
        self._style.update({
            "display": self.cb_display.currentData(),
            "line_words": self.sp_line_words.value(),
            "max_lines": self.sp_max_lines.value(),
            "all_caps": self.chk_all_caps.isChecked(),
            "effect": self.cb_effect.currentData(),
            "words_per_cue": self.sp_words.value(),
            "position": self.cb_pos.currentData(),
            **({"font": font} if font else {}),   # header không có data
            "font_size": self.sp_size.value(),
            "margin_v": self.sp_margin.value(),
            "outline": self.sp_outline.value(),
            "shadow": self.sp_shadow.value(),
            "bold": self.chk_bold.isChecked(),
            "box": self.cb_box.currentData(),
            "box_opacity": self.sp_box_opacity.value(),
        })
        self.sp_margin.setEnabled(self._style["position"] != "middle")
        self._update_karaoke_enabled()
        self._update_box_enabled()
        self.canvas.set_style(self._style)

    def _on_canvas_drag(self, position: str, margin_v: int) -> None:
        """Dragging the preview updates the spinners without echo loops."""
        for w in (self.cb_pos, self.sp_margin):
            w.blockSignals(True)
        idx = self.cb_pos.findData(position)
        if idx >= 0:
            self.cb_pos.setCurrentIndex(idx)
        self.sp_margin.setValue(margin_v)
        for w in (self.cb_pos, self.sp_margin):
            w.blockSignals(False)
        self._style["position"] = position
        self._style["margin_v"] = margin_v
        self.sp_margin.setEnabled(position != "middle")

    def _paint_color_button(self, btn: QPushButton, hex_color: str) -> None:
        btn.setText(hex_color)
        # Chữ đen/trắng theo độ sáng thật của màu (so sánh chuỗi hex là
        # so sánh từ điển, nên màu đỏ sẫm cũng bị coi nhầm là màu sáng).
        c = QColor(hex_color)
        luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        btn.setStyleSheet(
            f"background: {hex_color}; color: "
            f"{tokens.BG_APP if luminance > 140 else tokens.TEXT_ON_ACCENT};")

    def _populate_fonts(self) -> None:
        """Đổ danh sách phông chữ, CHỈ lấy từ thư mục phông của dự án.

        Phông có sẵn trong máy không được liệt kê, vì chữ phụ đề ghi lên
        video chỉ chắc chắn hiện đúng khi phông nằm trong thư mục này.
        Phông thiếu dấu tiếng Việt vẫn hiện nhưng gắn cảnh báo, vì chữ
        thiếu dấu sẽ thành ô vuông ngay trên video.
        """
        from autodub_gui.fonts import font_choices

        self.cb_font.clear()
        for label, family in font_choices():
            self.cb_font.addItem(label, family)
            self.cb_font.setItemData(
                self.cb_font.count() - 1, QFont(family), Qt.FontRole)
        if self.cb_font.count() == 0:
            self.cb_font.addItem(
                "Thư mục phông chữ đang trống — hãy thả tệp .ttf vào đó", "")
            self.cb_font.setEnabled(False)
        polish_combo(self.cb_font)

    def _select_font(self, family: str) -> None:
        idx = self.cb_font.findData(family)
        if idx < 0:
            # Font đã lưu không còn (bị xoá/máy khác) — chọn font app đầu
            # tiên, không im lặng giữ tên font sẽ render sai.
            for i in range(self.cb_font.count()):
                if self.cb_font.itemData(i):
                    idx = i
                    break
        if idx >= 0:
            self.cb_font.setCurrentIndex(idx)

    def changeEvent(self, event) -> None:  # noqa: N802 — Qt API
        # Quay lại dialog sau khi thả font vào thư mục (Explorer) → đổ lại
        # danh sách để font mới hiện ngay, không phải mở lại app.
        from PySide6.QtCore import QEvent
        if (event.type() == QEvent.ActivationChange and self.isActiveWindow()
                and hasattr(self, "cb_font")):
            current = self.cb_font.currentData()
            self.cb_font.blockSignals(True)
            self._populate_fonts()
            self._select_font(current or self._style.get("font", "Arial"))
            self.cb_font.blockSignals(False)
        super().changeEvent(event)

    def _open_fonts_dir(self) -> None:
        """Mở (tạo nếu chưa có) thư mục fonts/ cạnh app trong Explorer."""
        from autodub.utils import fonts_dir
        d = fonts_dir()
        os.makedirs(d, exist_ok=True)
        # README để người mở thư mục lần đầu biết phải làm gì.
        readme = os.path.join(d, "THEM_FONT_O_DAY.txt")
        if not os.path.exists(readme):
            try:
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(
                        "THÊM FONT CHO PHỤ ĐỀ\n"
                        "=====================\n\n"
                        "1. Tải font tại https://fonts.google.com\n"
                        "   (lọc Language → Vietnamese để font có đủ dấu "
                        "tiếng Việt).\n"
                        "2. Giải nén, thả các file .ttf / .otf vào thư mục "
                        "này.\n"
                        "3. Quay lại cửa sổ chỉnh phụ đề — font mới hiện "
                        "ngay trong danh sách\n   và hiển thị đúng trên "
                        "video ở mọi máy.\n\n"
                        "Gợi ý font hợp kiểu chữ video: Be Vietnam Pro, "
                        "Montserrat, Lexend, Baloo 2.\n"
                        "Font Google Fonts dùng giấy phép mở (OFL) — đóng "
                        "gói kèm app thoải mái.\n")
            except OSError:
                pass
        os.startfile(d)  # noqa: S606

    def _pick_color(self, key: str) -> None:
        from PySide6.QtWidgets import QColorDialog
        defaults = {"color": tokens.SUBTITLE_TEXT_DEFAULT,
                    "outline_color": tokens.SUBTITLE_OUTLINE_DEFAULT,
                    "box_color": tokens.SUBTITLE_BOXFILL_DEFAULT,
                    "highlight_color": tokens.SUBTITLE_HIGHLIGHT_DEFAULT}
        current = self._style.get(key, defaults.get(key, tokens.SUBTITLE_TEXT_DEFAULT))
        color = QColorDialog.getColor(QColor(current), self, "Chọn màu")
        if not color.isValid():
            return
        hex_color = color.name().upper()
        self._style[key] = hex_color
        btn = {"color": self.btn_color,
               "outline_color": self.btn_outline_color,
               "box_color": self.btn_box_color,
               "highlight_color": self.btn_highlight}[key]
        self._paint_color_button(btn, hex_color)
        self.canvas.set_style(self._style)

    # ------------------------------------------------------ playback ------ #

    def _toggle_playback(self) -> None:
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Dừng")
        else:
            self.btn_play.setText("▶ Phát")

    def _on_seek(self, value: int) -> None:
        if not self._player or self._duration_ms <= 0:
            return
        pos_ms = int(value * self._duration_ms / 1000)
        self._player.setPosition(pos_ms)

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        img = frame.toImage()
        if not img.isNull():
            self.canvas.set_image(img)

    def _on_player_position(self, pos_ms: int) -> None:
        if self._duration_ms > 0:
            if not self.slider_pos.isSliderDown():
                self.slider_pos.setValue(int(pos_ms * 1000 / self._duration_ms))
            cur = self._format_time(pos_ms)
            tot = self._format_time(self._duration_ms)
            self.lbl_time.setText(f"{cur} / {tot}")

    def _on_player_duration(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        cur = self._format_time(self._player.position() if self._player else 0)
        tot = self._format_time(duration_ms)
        self.lbl_time.setText(f"{cur} / {tot}")

    @staticmethod
    def _format_time(ms: int) -> str:
        sec = max(0, ms // 1000)
        m, s = divmod(sec, 60)
        return f"{m:02d}:{s:02d}"

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_player") and self._player:
            self._player.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        if hasattr(self, "_player") and self._player:
            self._player.stop()
        super().reject()

    def accept(self) -> None:
        if hasattr(self, "_player") and self._player:
            self._player.stop()
        super().accept()

    # -------------------------------------------------------- results ----- #

    def style(self) -> dict:
        return dict(self._style)

    def regions(self) -> list[dict]:
        return self.canvas.normalized_regions()

    def logo_options(self) -> dict:
        """Thông số cấu hình logo thương hiệu."""
        return {
            "logo_path": self.txt_logo_path.text().strip() if self.chk_logo_enabled.isChecked() else "",
            "logo_position": self.cb_logo_pos.currentData() or "top_right",
            "logo_scale": self.sp_logo_scale.value() / 100.0,
            "logo_opacity": self.sp_logo_opacity.value() / 100.0,
            "logo_motion": self.cb_logo_motion.currentData() or "static",
        }

    def watermark_options(self) -> dict:
        """Thông số cấu hình watermark chữ chìm."""
        return {
            "watermark_text": self.txt_wm_text.text().strip() if self.chk_wm_enabled.isChecked() else "",
            "watermark_motion": self.cb_wm_motion.currentData() or "bounce",
            "watermark_opacity": self.sp_wm_opacity.value() / 100.0,
            "watermark_font_size": self.sp_wm_font_size.value(),
            "watermark_speed": self.sp_wm_speed.value(),
        }

    def reframe_options(self) -> dict:
        """Thông số cấu hình tỷ lệ khung hình và chế độ Reframe."""
        return {
            "aspect_preset": self.cb_aspect.currentData() or "original",
            "reframe_mode": self.cb_reframe_mode.currentData() or "blur",
        }

    def sfx_options(self) -> dict:
        """Thông số cấu hình âm thanh chuyển cảnh Auto SFX."""
        return {
            "auto_sfx_enabled": self.chk_auto_sfx.isChecked(),
            "sfx_preset": self.cb_sfx_preset.currentData() or "whoosh",
            "sfx_volume_db": float(self.sp_sfx_volume.value()),
        }

