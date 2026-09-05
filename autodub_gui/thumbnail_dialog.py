"""Hộp thoại thiết kế ảnh bìa (Thumbnail Studio) độc lập.

Cho phép:
- Xem trước trực tiếp (Live Preview) với cơ chế debounce mượt mà.
- Kéo thanh tua Timeline chọn chính xác frame ưng ý từ video (có bộ đệm frame).
- Tự động bắt frame đẹp nhất bằng thuật toán Frame Scoring.
- Tải ảnh đồ họa ngoài từ máy tính làm nền.
- Tùy biến Tiêu đề trên, Tiêu đề dưới, Huy hiệu (Badge), Phong cách (Preset) và Tỷ lệ (16:9 / 9:16).
- Lưu tệp hoàn chỉnh vào thư mục `youtube/` và cập nhật metadata đồng nhất.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from PIL import Image

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSlider, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from autodub.media.thumbnail import (
    PRESETS,
    detect_badge_from_context,
    extract_frame_at_timestamp,
    extract_info_from_link_or_text,
    find_best_frame,
    get_video_duration,
    render_thumbnail,
    score_frame_quality,
)
from autodub.workdir import load_social_metadata, save_social_metadata
from autodub_gui import tokens
from autodub_gui.ui.buttons import GhostButton, PrimaryButton
from autodub_gui.ui.inputs import LabeledCombo, polish_combo
from autodub_gui.ui.toast import TOASTS


def _format_time(sec: float) -> str:
    """Định dạng giây thành chuỗi MM:SS hoặc HH:MM:SS."""
    s = max(0, int(sec))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class _FrameExtractWorker(QThread):
    """Trích xuất frame ngầm ngoài UI thread để không giật lag."""
    frame_ready = Signal(str, float)
    failed = Signal(str)

    def __init__(self, video_path: str, timestamp_sec: float, out_path: str, parent=None):
        super().__init__(parent)
        self._video_path = video_path
        self._timestamp_sec = timestamp_sec
        self._out_path = out_path

    def run(self):
        try:
            res = extract_frame_at_timestamp(self._video_path, self._timestamp_sec, self._out_path)
            self.frame_ready.emit(res, self._timestamp_sec)
        except Exception as e:
            self.failed.emit(str(e))


class _AutoBestFrameWorker(QThread):
    """Tìm frame đẹp nhất chạy ngầm."""
    best_frame_found = Signal(str, float)
    failed = Signal(str)

    def __init__(self, video_path: str, out_path: str, duration_sec: float, parent=None):
        super().__init__(parent)
        self._video_path = video_path
        self._out_path = out_path
        self._duration_sec = duration_sec

    def run(self):
        try:
            out_file, best_time = find_best_frame(
                self._video_path, self._out_path, duration_sec=self._duration_sec
            )
            self.best_frame_found.emit(out_file, best_time)
        except Exception as e:
            self.failed.emit(str(e))


class ThumbnailStudioDialog(QDialog):
    """Hộp thoại Thumbnail Studio độc lập (Agency Tier)."""

    thumbnail_saved = Signal(str)

    def __init__(
        self,
        work_dir: str,
        video_path: str = "",
        initial_title: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._work_dir = work_dir
        self._video_path = video_path
        self._duration_sec = get_video_duration(video_path) if (video_path and os.path.exists(video_path)) else 30.0
        self._custom_frame_path: str | None = None
        self._current_frame_path: str | None = None
        self._frame_cache: dict[int, str] = {}
        self._worker: QThread | None = None

        self._temp_dir = os.path.join(tempfile.gettempdir(), f"autodub_studio_{os.getpid()}")
        os.makedirs(self._temp_dir, exist_ok=True)
        self._preview_out_path = os.path.join(self._temp_dir, "studio_preview.jpg")

        self.setWindowTitle("Thiết kế ảnh bìa (Thumbnail Studio)")
        self.resize(1180, 740)
        self.setMinimumSize(960, 620)
        self.setStyleSheet(
            f"QDialog {{ background-color: {tokens.BG_APP}; color: {tokens.TEXT_PRIMARY}; }} "
            f"QLabel {{ color: {tokens.TEXT_PRIMARY}; }} "
            f"QLineEdit, QTextEdit {{ background-color: {tokens.BG_INPUT}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER_DEFAULT}; border-radius: 6px; padding: 6px 10px; }} "
            f"QLineEdit:focus, QTextEdit:focus {{ border-color: {tokens.PRIMARY}; }} "
            f"QGroupBox {{ font-weight: bold; border: 1px solid {tokens.BORDER_SUBTLE}; "
            f"border-radius: 8px; margin-top: 14px; padding-top: 10px; background: {tokens.BG_PANEL}; }} "
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {tokens.PRIMARY_HOVER}; }}"
        )

        # Timer debounce cho việc cập nhật Live Preview
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(160)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._render_preview_now)

        self._build_ui(initial_title)
        self._load_metadata()
        self._init_first_frame()

    def _build_ui(self, initial_title: str) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(tokens.SP_4, tokens.SP_4, tokens.SP_4, tokens.SP_4)
        main_layout.setSpacing(tokens.SP_4)

        # ---------------- CỘT TRÁI: LIVE PREVIEW & TIMELINE ----------------
        left_box = QVBoxLayout()
        left_box.setSpacing(tokens.SP_3)

        # Khung chứa Live Preview
        preview_container = QFrame()
        preview_container.setStyleSheet(
            f"QFrame {{ background: {tokens.BG_VIDEO}; border: 1px solid {tokens.BORDER_DEFAULT}; "
            f"border-radius: 8px; }}"
        )
        pv_layout = QVBoxLayout(preview_container)
        pv_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel("Đang nạp ảnh xem trước…")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 270)
        self.preview_label.setStyleSheet("background: transparent;")
        pv_layout.addWidget(self.preview_label)
        left_box.addWidget(preview_container, stretch=1)

        # Thông tin thanh trạng thái preview
        self.info_label = QLabel("Kích thước: 1280x720 • Preset: Cổ Đại Làm Giàu")
        self.info_label.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; background: transparent;"
        )
        left_box.addWidget(self.info_label)

        # Timeline Slider
        slider_group = QGroupBox("Chọn khung hình từ video")
        sg_layout = QVBoxLayout(slider_group)
        sg_layout.setSpacing(tokens.SP_2)

        time_row = QHBoxLayout()
        self.time_display = QLabel("00:00:00 / 00:00:00")
        self.time_display.setStyleSheet(
            f"font-weight: bold; color: {tokens.PRIMARY_HOVER}; font-size: {tokens.FS_BODY}px;"
        )
        time_row.addWidget(self.time_display)
        time_row.addStretch()
        sg_layout.addLayout(time_row)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        max_steps = max(10, int(self._duration_sec * 10))
        self.timeline_slider.setRange(0, max_steps)
        self.timeline_slider.setValue(int(min(self._duration_sec * 0.25, 2.0) * 10))
        self.timeline_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 6px; background: {tokens.BG_INPUT}; border-radius: 3px; }} "
            f"QSlider::sub-page:horizontal {{ background: {tokens.PRIMARY}; border-radius: 3px; }} "
            f"QSlider::handle:horizontal {{ background: {tokens.TEXT_ON_ACCENT}; border: 2px solid {tokens.PRIMARY}; "
            f"width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}"
        )
        self.timeline_slider.valueChanged.connect(self._on_slider_changed)
        sg_layout.addWidget(self.timeline_slider)

        # Nút điều khiển frame
        frame_btn_row = QHBoxLayout()
        frame_btn_row.setSpacing(tokens.SP_2)

        self.btn_auto_frame = GhostButton("Auto chọn frame đẹp")
        self.btn_auto_frame.setToolTip("Quét toàn bộ video và tự nhảy tới khung hình sắc nét, bắt mắt nhất.")
        self.btn_auto_frame.clicked.connect(self._auto_pick_best_frame)
        frame_btn_row.addWidget(self.btn_auto_frame)

        self.btn_custom_img = GhostButton("Chọn ảnh từ máy…")
        self.btn_custom_img.setToolTip("Tải ảnh poster/nhân vật từ máy tính thay cho frame video.")
        self.btn_custom_img.clicked.connect(self._pick_custom_image)
        frame_btn_row.addWidget(self.btn_custom_img)

        self.btn_reset_frame = GhostButton("Dùng lại video")
        self.btn_reset_frame.setVisible(False)
        self.btn_reset_frame.clicked.connect(self._reset_to_video_frame)
        frame_btn_row.addWidget(self.btn_reset_frame)

        frame_btn_row.addStretch()
        sg_layout.addLayout(frame_btn_row)
        left_box.addWidget(slider_group)

        main_layout.addLayout(left_box, stretch=6)

        # ---------------- CỘT PHẢI: TÙY BIẾN CHỮ, STYLE & XUẤT ----------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        right_widget = QWidget()
        right_box = QVBoxLayout(right_widget)
        right_box.setSpacing(tokens.SP_3)
        right_box.setContentsMargins(0, 0, 0, 0)

        # 1. Nội dung chữ
        text_group = QGroupBox("Nội dung chữ (Typography 3D)")
        tg_layout = QVBoxLayout(text_group)
        tg_layout.setSpacing(tokens.SP_2)

        tg_layout.addWidget(QLabel("Tiêu đề trên (Eyebrow / Tên bối cảnh):"))
        self.input_top = QLineEdit()
        self.input_top.setPlaceholderText("Ví dụ: Xuyên Không Về Thời Cổ Đại")
        self.input_top.textChanged.connect(self._schedule_preview_update)
        tg_layout.addWidget(self.input_top)

        tg_layout.addWidget(QLabel("Tiêu đề dưới (Main Hook / Punchline):"))
        self.input_bottom = QLineEdit()
        self.input_bottom.setPlaceholderText("Ví dụ: DÙNG TƯ DUY HIỆN ĐẠI ĐỂ LÀM GIÀU")
        self.input_bottom.textChanged.connect(self._schedule_preview_update)
        tg_layout.addWidget(self.input_bottom)

        tg_layout.addWidget(QLabel("Huy hiệu (Badge số tập):"))
        badge_row = QHBoxLayout()
        badge_row.setSpacing(tokens.SP_1)
        self.input_badge = QLineEdit()
        self.input_badge.setText("1-100")
        self.input_badge.setPlaceholderText("Ví dụ: 1-100, TẬP 1, FULL HD (hoặc để trống)")
        self.input_badge.textChanged.connect(self._schedule_preview_update)
        badge_row.addWidget(self.input_badge, stretch=1)

        btn_down = GhostButton("▼")
        btn_down.setToolTip("Giảm 1 tập")
        btn_down.clicked.connect(lambda: self._step_episode(-1))
        badge_row.addWidget(btn_down)

        btn_up = GhostButton("▲")
        btn_up.setToolTip("Tăng 1 tập")
        btn_up.clicked.connect(lambda: self._step_episode(1))
        badge_row.addWidget(btn_up)
        tg_layout.addLayout(badge_row)

        # Quick chips chọn nhanh cho Video dài & Tập lẻ
        chip_row1 = QHBoxLayout()
        chip_row1.setSpacing(tokens.SP_1)
        for label, val in [("1-100", "1-100"), ("FULL 1-100", "FULL 1-100"), ("TRỌN BỘ", "TRỌN BỘ"), ("1-50", "1-50")]:
            b = GhostButton(label)
            b.clicked.connect(lambda _c=False, v=val: self.input_badge.setText(v))
            chip_row1.addWidget(b)
        chip_row1.addStretch()
        tg_layout.addLayout(chip_row1)

        chip_row2 = QHBoxLayout()
        chip_row2.setSpacing(tokens.SP_1)
        for label, val in [("TẬP 1", "TẬP 1"), ("TẬP CUỐI", "TẬP CUỐI"), ("Ẩn huy hiệu", "")]:
            b = GhostButton(label)
            b.clicked.connect(lambda _c=False, v=val: self.input_badge.setText(v))
            chip_row2.addWidget(b)

        btn_detect = GhostButton("Nhận diện từ link / video")
        btn_detect.setToolTip("Tự động quét link gốc, tiêu đề và thời lượng để bắt số tập")
        btn_detect.clicked.connect(self._detect_badge_now)
        chip_row2.addWidget(btn_detect)

        btn_paste_link = GhostButton("Dán link...")
        btn_paste_link.setToolTip("Dán trực tiếp liên kết YouTube, Bilibili, Douyin hoặc tiêu đề để tự động nhận diện tập và ảnh")
        btn_paste_link.clicked.connect(self._prompt_detect_from_link)
        chip_row2.addWidget(btn_paste_link)
        chip_row2.addStretch()
        tg_layout.addLayout(chip_row2)

        right_box.addWidget(text_group)

        # 2. Phong cách & Bố cục
        style_group = QGroupBox("Phong cách & Tỷ lệ")
        stg_layout = QVBoxLayout(style_group)
        stg_layout.setSpacing(tokens.SP_2)

        stg_layout.addWidget(QLabel("Bộ màu (Style Preset):"))
        self.combo_preset = QComboBox()
        self.combo_preset.addItem("Cổ Đại Làm Giàu (Vàng Gold 3D)", "co_dai")
        self.combo_preset.addItem("Quân Sư Hiện Đại (Neon Tím Hồng)", "quan_su")
        self.combo_preset.addItem("Chiến Thần Rực Lửa (Đỏ Cam 3D)", "chien_than")
        polish_combo(self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._schedule_preview_update)
        stg_layout.addWidget(self.combo_preset)

        stg_layout.addWidget(QLabel("Tỷ lệ khung hình:"))
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItem("16:9 Ngang (YouTube Video)", "16:9")
        self.combo_aspect.addItem("9:16 Dọc (TikTok / Shorts / Reels)", "9:16")
        polish_combo(self.combo_aspect)
        self.combo_aspect.currentIndexChanged.connect(self._schedule_preview_update)
        stg_layout.addWidget(self.combo_aspect)

        self.chk_enhance = QCheckBox("Tăng cường độ nét & rực màu (Clarity & Vibrance)")
        self.chk_enhance.setChecked(True)
        self.chk_enhance.setStyleSheet(f"color: {tokens.TEXT_PRIMARY};")
        self.chk_enhance.stateChanged.connect(self._schedule_preview_update)
        stg_layout.addWidget(self.chk_enhance)

        right_box.addWidget(style_group)

        # 3. Nội dung Đăng bài (Caption & Hashtags)
        social_group = QGroupBox("Nội dung Đăng bài (Caption & Hashtag)")
        soc_layout = QVBoxLayout(social_group)
        soc_layout.setSpacing(tokens.SP_2)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(tokens.SP_2)
        fmt_row.addWidget(QLabel("Nền tảng:"))
        self.combo_platform = QComboBox()
        self.combo_platform.addItem("TikTok / Shorts / Reels (Ngắn gọn & Viral)", "tiktok")
        self.combo_platform.addItem("YouTube Video dài (SEO & Đầy đủ)", "youtube")
        self.combo_platform.addItem("Facebook / Khác", "facebook")
        polish_combo(self.combo_platform)
        self.combo_platform.currentIndexChanged.connect(self._on_platform_changed)
        fmt_row.addWidget(self.combo_platform, stretch=1)
        soc_layout.addLayout(fmt_row)

        soc_layout.addWidget(QLabel("Caption (Mô tả bài đăng):"))
        self.input_caption = QTextEdit()
        self.input_caption.setFixedHeight(68)
        self.input_caption.setPlaceholderText("Nhập caption hoặc tóm tắt ngắn cho video...")
        soc_layout.addWidget(self.input_caption)

        soc_layout.addWidget(QLabel("Hashtags (#tag):"))
        self.input_tags = QLineEdit()
        self.input_tags.setPlaceholderText("#shorts #reviewphim #xuhuong #phimhay")
        soc_layout.addWidget(self.input_tags)

        # Các nút sao chép nhanh
        soc_copy_row = QHBoxLayout()
        soc_copy_row.setSpacing(tokens.SP_1)

        self.btn_copy_caption = PrimaryButton("📋 Sao chép Caption")
        self.btn_copy_caption.setToolTip("Sao chép nội dung Caption vào Clipboard để đăng bài.")
        self.btn_copy_caption.clicked.connect(self._copy_caption_to_clipboard)
        soc_copy_row.addWidget(self.btn_copy_caption)

        self.btn_copy_tags = GhostButton("🏷️ Sao chép Hashtag")
        self.btn_copy_tags.setToolTip("Sao chép danh sách hashtags (#shorts #reviewphim...) vào Clipboard.")
        self.btn_copy_tags.clicked.connect(self._copy_tags_to_clipboard)
        soc_copy_row.addWidget(self.btn_copy_tags)

        self.btn_copy_post_all = GhostButton("🚀 Sao chép Toàn bộ")
        self.btn_copy_post_all.setToolTip("Sao chép Tiêu đề, Caption và Hashtags vào Clipboard.")
        self.btn_copy_post_all.clicked.connect(self._copy_all_social_to_clipboard)
        soc_copy_row.addWidget(self.btn_copy_post_all)

        soc_layout.addLayout(soc_copy_row)

        self.btn_caption_to_hook = GhostButton("✨ Dùng Caption làm chữ Thumbnail")
        self.btn_caption_to_hook.setToolTip("Lấy câu mở đầu hoặc tiêu đề từ caption đưa lên chữ ảnh bìa.")
        self.btn_caption_to_hook.clicked.connect(self._apply_caption_to_thumbnail)
        soc_layout.addWidget(self.btn_caption_to_hook)

        right_box.addWidget(social_group)

        # 4. Nút hành động
        action_group = QGroupBox("Thao tác")
        ag_layout = QVBoxLayout(action_group)
        ag_layout.setSpacing(tokens.SP_2)

        self.btn_save = PrimaryButton("Lưu Thumbnail")
        self.btn_save.setToolTip("Lưu ảnh bìa vào thư mục dự án và cập nhật lên màn hình xuất.")
        self.btn_save.clicked.connect(self._save_thumbnail)
        ag_layout.addWidget(self.btn_save)

        self.btn_copy = GhostButton("Chép ảnh vào Clipboard")
        self.btn_copy.clicked.connect(self._copy_image_to_clipboard)
        ag_layout.addWidget(self.btn_copy)

        self.btn_open = GhostButton("Mở file ảnh")
        self.btn_open.clicked.connect(self._open_saved_image)
        ag_layout.addWidget(self.btn_open)

        self.btn_close = GhostButton("Đóng")
        self.btn_close.clicked.connect(self.accept)
        ag_layout.addWidget(self.btn_close)

        right_box.addWidget(action_group)
        right_box.addStretch()

        right_scroll.setWidget(right_widget)
        main_layout.addWidget(right_scroll, stretch=4)

        # Gán tiêu đề mặc định
        if initial_title:
            if " - " in initial_title:
                parts = initial_title.split(" - ", 1)
                self.input_top.setText(parts[0].strip())
                self.input_bottom.setText(parts[1].strip())
            else:
                self.input_top.setText("XUYÊN KHÔNG VỀ THỜI CỔ ĐẠI")
                self.input_bottom.setText(initial_title.strip())

    # ---------------- DỮ LIỆU & INITIALIZATION ----------------

    def _metadata_path(self) -> str:
        return os.path.join(self._work_dir, "youtube", "youtube_metadata.json")

    def _load_metadata(self) -> None:
        """Đọc metadata đã lưu (Single Source of Truth) nếu có."""
        meta_file = self._metadata_path()
        has_saved_badge = False
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if data.get("top_title"):
                        self.input_top.setText(str(data["top_title"]))
                    if data.get("bottom_title"):
                        self.input_bottom.setText(str(data["bottom_title"]))
                    if data.get("badge_text") is not None and str(data.get("badge_text")).strip():
                        self.input_badge.setText(str(data["badge_text"]))
                        has_saved_badge = True
                    if data.get("preset"):
                        idx = self.combo_preset.findData(str(data["preset"]))
                        if idx >= 0:
                            self.combo_preset.setCurrentIndex(idx)
                    if data.get("timestamp_sec") is not None:
                        sec = float(data["timestamp_sec"])
                        self.timeline_slider.setValue(int(sec * 10))
            except Exception:
                pass

        if not has_saved_badge:
            # Tự động nhận diện từ link / tiêu đề nếu chưa có cấu hình trước đó và có ngữ cảnh nguồn
            from autodub.workdir import load_video_meta
            meta = load_video_meta(self._work_dir)
            st = meta.get("title", "")
            su = meta.get("source_url", "") or meta.get("url", "")
            fn = os.path.basename(self._video_path) if self._video_path else ""
            if su or st:
                full_t = f"{st} {self.input_top.text()} {self.input_bottom.text()}".strip()
                auto_badge = detect_badge_from_context(
                    title=full_t,
                    source_url=su,
                    filename=fn,
                    duration_sec=self._duration_sec,
                )
                if auto_badge:
                    self.input_badge.setText(auto_badge)

        # Tải nội dung đăng bài (Caption & Hashtags)
        def_t = self.input_bottom.text().strip() or (f"{self.input_top.text()} {self.input_bottom.text()}".strip())
        self._social_cache = load_social_metadata(self._work_dir, default_title=def_t)
        cap = self._social_cache.get("caption") or self._social_cache.get("tiktok_caption") or self._social_cache.get("description") or ""
        tags = self._social_cache.get("hashtags_str") or " ".join(self._social_cache.get("hashtags", []))
        self.input_caption.setPlainText(cap)
        self.input_tags.setText(tags)

    def _on_platform_changed(self) -> None:
        """Đổi mẫu caption và hashtag theo nền tảng được chọn."""
        key = self.combo_platform.currentData() or "tiktok"
        if not hasattr(self, "_social_cache"):
            def_t = self.input_bottom.text().strip() or (f"{self.input_top.text()} {self.input_bottom.text()}".strip())
            self._social_cache = load_social_metadata(self._work_dir, default_title=def_t)

        if key == "tiktok":
            cap = self._social_cache.get("tiktok_caption") or self._social_cache.get("caption") or ""
            tags = self._social_cache.get("tiktok_hashtags_str") or self._social_cache.get("hashtags_str") or "#shorts #reviewphim #trending #viral #xuhuong #phimhay"
        elif key == "youtube":
            cap = self._social_cache.get("description") or self._social_cache.get("caption") or ""
            tags = self._social_cache.get("hashtags_str") or "#shorts #reviewphim #trending #viral #xuhuong #phimhay"
        else:
            cap = self._social_cache.get("caption") or self._social_cache.get("description") or ""
            tags = self._social_cache.get("hashtags_str") or "#reviewphim #phimhay #xuhuong"

        self.input_caption.setPlainText(cap)
        self.input_tags.setText(tags)

    def _copy_caption_to_clipboard(self) -> None:
        """Sao chép Caption vào clipboard."""
        txt = self.input_caption.toPlainText().strip()
        if txt:
            QApplication.clipboard().setText(txt)
            TOASTS.success("Đã sao chép Caption vào Clipboard!")
        else:
            TOASTS.info("Chưa có nội dung Caption để chép.")

    def _copy_tags_to_clipboard(self) -> None:
        """Sao chép danh sách hashtag vào clipboard."""
        txt = self.input_tags.text().strip()
        if txt:
            QApplication.clipboard().setText(txt)
            TOASTS.success("Đã sao chép Hashtag vào Clipboard!")
        else:
            TOASTS.info("Chưa có Hashtags để chép.")

    def _copy_all_social_to_clipboard(self) -> None:
        """Sao chép toàn bộ Tiêu đề, Caption và Hashtags vào clipboard."""
        top = self.input_top.text().strip()
        bot = self.input_bottom.text().strip()
        title = f"{top} - {bot}".strip(" - ") or self.input_bottom.text().strip()
        cap = self.input_caption.toPlainText().strip()
        tags = self.input_tags.text().strip()

        parts = []
        if title:
            parts.append(f"📌 {title}")
        if cap:
            parts.append(cap)
        if tags:
            parts.append(tags)

        full = "\n\n".join(parts).strip()
        if full:
            QApplication.clipboard().setText(full)
            TOASTS.success("Đã sao chép toàn bộ Tiêu đề, Caption & Hashtags!")
        else:
            TOASTS.info("Chưa có nội dung để chép.")

    def _apply_caption_to_thumbnail(self) -> None:
        """Đưa dòng đầu tiên hoặc tiêu đề của Caption làm chữ trên Thumbnail."""
        txt = self.input_caption.toPlainText().strip()
        if not txt:
            txt = self.input_bottom.text().strip()
        if not txt:
            TOASTS.info("Chưa có nội dung Caption để tạo chữ ảnh bìa.")
            return

        lines = [line.strip() for line in txt.split("\n") if line.strip()]
        first_line = lines[0] if lines else txt
        for sep in [" - ", ": ", " | "]:
            if sep in first_line:
                parts = first_line.split(sep, 1)
                self.input_top.setText(parts[0].strip()[:35])
                self.input_bottom.setText(parts[1].strip()[:50])
                self._schedule_preview_update()
                TOASTS.success("Đã đưa tiêu đề Caption lên ảnh bìa!")
                return

        self.input_bottom.setText(first_line[:50])
        self._schedule_preview_update()
        TOASTS.success("Đã đưa tiêu đề Caption lên ảnh bìa!")

    def _step_episode(self, delta: int) -> None:
        """Tăng hoặc giảm số tập nhanh."""
        import re
        curr = self.input_badge.text().strip()
        range_m = re.match(r"^(\d+)\s*[-–~]\s*(\d+)$", curr)
        if range_m:
            s, e = int(range_m.group(1)), int(range_m.group(2))
            diff = max(1, e - s + 1)
            new_s = max(1, s + delta * diff)
            new_e = new_s + diff - 1
            self.input_badge.setText(f"{new_s}-{new_e}")
            return

        num_m = re.search(r"\d+", curr)
        if num_m:
            num = int(num_m.group(0))
            new_num = max(1, num + delta)
            prefix = curr[:num_m.start()]
            suffix = curr[num_m.end():]
            self.input_badge.setText(f"{prefix}{new_num}{suffix}")
            return

        if not curr:
            self.input_badge.setText("TẬP 1")

    def _prompt_detect_from_link(self) -> None:
        """Mở hộp thoại cho phép người dùng dán bất kỳ link video hoặc text chia sẻ nào."""
        from PySide6.QtWidgets import QInputDialog, QApplication

        clip_text = QApplication.clipboard().text().strip()
        default_val = clip_text if ("http" in clip_text or "第" in clip_text or "tập" in clip_text.lower()) else ""

        text, ok = QInputDialog.getText(
            self,
            "Nhận diện từ liên kết / văn bản",
            "Dán liên kết video (YouTube, Bilibili, Douyin, TikTok) hoặc tiêu đề phim:",
            text=default_val,
        )
        if not ok or not text.strip():
            return

        yt_dir = os.path.join(self._work_dir, "youtube")
        info = extract_info_from_link_or_text(text.strip(), output_dir=yt_dir)

        if info.get("badge"):
            self.input_badge.setText(info["badge"])

        if info.get("suggested_title"):
            self.input_bottom.setText(info["suggested_title"])

        if info.get("thumbnail_path") and os.path.exists(info["thumbnail_path"]):
            self._current_frame_path = info["thumbnail_path"]
            self._schedule_preview_update()

        platform_str = f" [{info['platform']}]" if info.get("platform") else ""
        TOASTS.success(f"Đã nhận diện{platform_str}: {info.get('badge') or 'Thành công'}")

    def _detect_badge_now(self) -> None:
        """Tự động phân tích từ link dự án, tiêu đề và video; nếu chưa có thì mở popup dán link."""
        from autodub.workdir import load_video_meta
        meta = load_video_meta(self._work_dir)
        st = meta.get("title", "")
        su = meta.get("source_url", "") or meta.get("url", "")
        fn = os.path.basename(self._video_path) if self._video_path else ""

        if not su and not st and not fn:
            self._prompt_detect_from_link()
            return

        full_t = f"{st} {self.input_top.text()} {self.input_bottom.text()}".strip()
        badge = detect_badge_from_context(
            title=full_t,
            source_url=su,
            filename=fn,
            duration_sec=self._duration_sec,
        )
        self.input_badge.setText(badge)
        TOASTS.success(f"Đã nhận diện: {badge}")

    def _init_first_frame(self) -> None:
        """Trích xuất frame đầu tiên hoặc dùng frame đã lưu."""
        yt_dir = os.path.join(self._work_dir, "youtube")
        cand_img = os.path.join(yt_dir, "thumbnail_original.jpg")
        if os.path.exists(cand_img):
            self._current_frame_path = cand_img
            self._schedule_preview_update()
            return

        if self._video_path and os.path.exists(self._video_path):
            current_sec = self.timeline_slider.value() / 10.0
            self._request_frame_at_sec(current_sec)
        else:
            # Fallback nếu không có video
            self._current_frame_path = os.path.join(self._temp_dir, "blank_frame.jpg")
            img = Image.new("RGB", (1280, 720), color=(20, 20, 35))
            img.save(self._current_frame_path)
            self._schedule_preview_update()

    # ---------------- TIMELINE & FRAME EXTRACTION ----------------

    def _on_slider_changed(self, value: int) -> None:
        sec = value / 10.0
        self.time_display.setText(f"{_format_time(sec)} / {_format_time(self._duration_sec)}")
        if self._custom_frame_path:
            return
        self._request_frame_at_sec(sec)

    def _request_frame_at_sec(self, sec: float) -> None:
        if not self._video_path or not os.path.exists(self._video_path):
            return

        bucket_key = int(round(sec * 2))  # Cache mỗi 0.5s
        if bucket_key in self._frame_cache and os.path.exists(self._frame_cache[bucket_key]):
            self._current_frame_path = self._frame_cache[bucket_key]
            self._schedule_preview_update()
            return

        # Trích xuất ngầm
        frame_dest = os.path.join(self._temp_dir, f"frame_{bucket_key}.jpg")
        if self._worker and self._worker.isRunning():
            self._worker.terminate()

        worker = _FrameExtractWorker(self._video_path, sec, frame_dest, parent=self)
        worker.frame_ready.connect(lambda path, t: self._on_frame_extracted(bucket_key, path))
        worker.start()
        self._worker = worker

    def _on_frame_extracted(self, bucket_key: int, path: str) -> None:
        self._frame_cache[bucket_key] = path
        self._current_frame_path = path
        self._schedule_preview_update()

    def _auto_pick_best_frame(self) -> None:
        if not self._video_path or not os.path.exists(self._video_path):
            TOASTS.info("Không tìm thấy video để quét frame.")
            return

        self.btn_auto_frame.setEnabled(False)
        self.btn_auto_frame.setText("Đang phân tích…")

        best_dest = os.path.join(self._temp_dir, "best_auto_frame.jpg")
        worker = _AutoBestFrameWorker(self._video_path, best_dest, self._duration_sec, parent=self)
        worker.best_frame_found.connect(self._on_best_frame_found)
        worker.failed.connect(lambda err: TOASTS.warn(f"Lỗi quét frame: {err}"))
        worker.finished.connect(lambda: (
            self.btn_auto_frame.setEnabled(True),
            self.btn_auto_frame.setText("Auto chọn frame đẹp")
        ))
        worker.start()
        self._worker = worker

    def _on_best_frame_found(self, path: str, best_time: float) -> None:
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(int(best_time * 10))
        self.timeline_slider.blockSignals(False)
        self.time_display.setText(f"{_format_time(best_time)} / {_format_time(self._duration_sec)}")

        self._current_frame_path = path
        self._schedule_preview_update()
        TOASTS.success(f"Đã chọn frame đắt giá nhất tại {_format_time(best_time)}!")

    def _pick_custom_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh poster / nhân vật", "",
            "Hình ảnh (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        self._custom_frame_path = path
        self._current_frame_path = path
        self.btn_reset_frame.setVisible(True)
        self._schedule_preview_update()
        TOASTS.success("Đã chọn ảnh ngoài làm nền!")

    def _reset_to_video_frame(self) -> None:
        self._custom_frame_path = None
        self.btn_reset_frame.setVisible(False)
        sec = self.timeline_slider.value() / 10.0
        self._request_frame_at_sec(sec)

    # ---------------- LIVE PREVIEW RENDERER ----------------

    def _schedule_preview_update(self) -> None:
        """Kích hoạt debounce 160ms trước khi render preview."""
        self._debounce_timer.start()

    def _render_preview_now(self) -> None:
        if not self._current_frame_path or not os.path.exists(self._current_frame_path):
            return

        aspect_key = self.combo_aspect.currentData() or "16:9"
        preset_key = self.combo_preset.currentData() or "co_dai"
        is_vertical = aspect_key == "9:16"

        w = 540 if is_vertical else 960
        h = 960 if is_vertical else 540

        top_txt = self.input_top.text().strip()
        bot_txt = self.input_bottom.text().strip()
        badge_txt = self.input_badge.text().strip()

        try:
            render_thumbnail(
                frame_path=self._current_frame_path,
                title="",
                output_path=self._preview_out_path,
                width=w,
                height=h,
                badge_text=badge_txt,
                top_title=top_txt,
                bottom_title=bot_txt,
                preset=preset_key,
                enhance_image=self.chk_enhance.isChecked(),
            )

            pix = QPixmap(self._preview_out_path)
            if not pix.isNull():
                target_w = 260 if is_vertical else 460
                target_h = 460 if is_vertical else 260
                scaled_pix = pix.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_label.setPixmap(scaled_pix)
                self.info_label.setText(
                    f"Kích thước xuất: {'720x1280 (9:16)' if is_vertical else '1280x720 (16:9)'} • "
                    f"Preset: {self.combo_preset.currentText()}"
                )
        except Exception as e:
            self.preview_label.setText(f"Lỗi render preview: {e}")

    # ---------------- LƯU & XUẤT ----------------

    def _save_thumbnail(self) -> None:
        if not self._work_dir:
            return

        yt_dir = os.path.join(self._work_dir, "youtube")
        os.makedirs(yt_dir, exist_ok=True)

        top_txt = self.input_top.text().strip()
        bot_txt = self.input_bottom.text().strip()
        badge_txt = self.input_badge.text().strip()
        preset_key = self.combo_preset.currentData() or "co_dai"
        enhance = self.chk_enhance.isChecked()
        curr_sec = self.timeline_slider.value() / 10.0

        out_16_9 = os.path.join(yt_dir, "thumbnail_landscape.jpg")
        out_9_16 = os.path.join(yt_dir, "thumbnail_portrait.jpg")

        frame_to_use = self._current_frame_path
        if not frame_to_use or not os.path.exists(frame_to_use):
            TOASTS.warn("Chưa có khung hình hợp lệ để lưu.")
            return

        self.btn_save.setEnabled(False)
        self.btn_save.setText("Đang xuất ảnh…")

        try:
            # 1. Render 16:9
            render_thumbnail(
                frame_path=frame_to_use,
                title="",
                output_path=out_16_9,
                width=1280,
                height=720,
                badge_text=badge_txt,
                top_title=top_txt,
                bottom_title=bot_txt,
                preset=preset_key,
                enhance_image=enhance,
            )

            # 2. Render 9:16
            render_thumbnail(
                frame_path=frame_to_use,
                title="",
                output_path=out_9_16,
                width=720,
                height=1280,
                badge_text=badge_txt,
                top_title=top_txt,
                bottom_title=bot_txt,
                preset=preset_key,
                enhance_image=enhance,
            )

            # 3. Lưu frame gốc để dùng lại sau
            import shutil
            orig_save = os.path.join(yt_dir, "thumbnail_original.jpg")
            if os.path.abspath(frame_to_use) != os.path.abspath(orig_save):
                shutil.copyfile(frame_to_use, orig_save)

            # 4. Ghi Single Source of Truth Metadata JSON
            cap_val = self.input_caption.toPlainText().strip()
            tags_val = self.input_tags.text().strip()
            tags_list = [t.strip() for t in tags_val.split() if t.strip()]

            meta_data = {
                "top_title": top_txt,
                "bottom_title": bot_txt,
                "badge_text": badge_txt,
                "preset": preset_key,
                "timestamp_sec": curr_sec,
                "caption": cap_val,
                "hashtags": tags_list,
                "hashtags_str": tags_val,
                "description": f"{cap_val}\n\n{tags_val}".strip(),
                "updated_at": time.time(),
            }
            if top_txt and bot_txt:
                meta_data["title"] = f"{top_txt} - {bot_txt}"

            save_social_metadata(self._work_dir, meta_data)

            self.thumbnail_saved.emit(out_16_9)
            TOASTS.success("Đã lưu xong ảnh bìa Thumbnail (16:9 & 9:16)!", action_label="Mở xem", on_action=self._open_saved_image)
            self.accept()
        except Exception as e:
            TOASTS.warn(f"Không thể lưu thumbnail: {e}")
        finally:
            self.btn_save.setEnabled(True)
            self.btn_save.setText("Lưu Thumbnail")

    def _copy_image_to_clipboard(self) -> None:
        if os.path.exists(self._preview_out_path):
            pix = QPixmap(self._preview_out_path)
            if not pix.isNull():
                QApplication.clipboard().setPixmap(pix)
                TOASTS.success("Đã chép ảnh bìa vào Clipboard!")
                return
        TOASTS.info("Chưa có ảnh bìa để sao chép.")

    def _open_saved_image(self) -> None:
        from autodub_gui.system_open import open_file
        yt_dir = os.path.join(self._work_dir, "youtube")
        cand = os.path.join(yt_dir, "thumbnail_landscape.jpg")
        if os.path.exists(cand):
            open_file(cand)
        elif os.path.exists(self._preview_out_path):
            open_file(self._preview_out_path)
        else:
            TOASTS.info("Chưa có file ảnh bìa để mở.")
