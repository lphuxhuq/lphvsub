"""Trình chỉnh sửa: xem lại video, sửa từng câu và xuất lại.

Bố cục: thanh trên cùng, cột biểu tượng bên trái với sáu mục, khung video và
bảng bên phải, dải thời gian chạy suốt phía dưới. Video và dải thời gian luôn
hiển thị ở mọi mục để người dùng không mất mạch.

Lưu ý quan trọng về hành vi: sửa chữ KHÔNG tự tạo lại giọng đọc. Người dùng
phải bấm Lưu tất cả và đọc lại, rồi Xuất video. Một băng nhắc luôn hiện khi
còn câu đã sửa mà chưa đọc lại.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from autodub_gui import icons, tokens, waveform
from autodub_gui.pages import BasePage
from autodub_gui.pages.editor_export import VoiceAndExportMixin
from autodub_gui.pages.editor_commands import (
    AddSegmentCommand, DeleteSegmentCommand, EditTextCommand,
    MergeSegmentCommand, MoveSegmentCommand, SplitSegmentCommand,
)
from autodub_gui.pages.editor_panels import (
    AudioPanel, BackgroundPanel, DirtyBanner, ExportPanel, OverviewPanel,
    QCPanel, SubtitleListPanel, VoicePanel, debounce_timer,
)
from autodub_gui.run_state import REGISTRY, ActiveJob
from autodub_gui.system_open import open_file, open_folder
from autodub_gui.ui.buttons import PrimaryButton
from autodub_gui.ui.modal import ConfirmDialog, confirm_discard
from autodub_gui.ui.progress import SaveIndicator
from autodub_gui.ui.style import clear_background, panel_background
from autodub_gui.ui.toast import TOASTS
from autodub_gui.video.player import VideoPlayer
from autodub_gui.video.timeline import Timeline
from autodub_gui.voice_preview import VoicePreview
from autodub_gui.widgets import LogPanel
from autodub_gui.log_text import Narrator

TOP_BAR_H = 56
# Đủ rộng cho nhãn dài nhất («Xuất video») cộng biểu tượng, lề và đệm của
# mục điều hướng — hẹp hơn là chữ bị cắt.
RAIL_W = 138
_UNDO_LIMIT = 100
_SPLIT_LEFT, _SPLIT_RIGHT = 62, 38
_MIN_LIST_W = 280
DEFAULT_DUCK_DB = -12.0     # mức giảm tiếng gốc mặc định
_RAIL_ICON = 20

# (khóa, nhãn, hàm vẽ biểu tượng)
RAIL_ITEMS = (
    ("overview", "Tổng quan", icons.home),
    ("subtitles", "Phụ đề", icons.edit),
    ("qc", "Kiểm tra", icons.check),
    ("audio", "Âm thanh", icons.waveform),
    ("voice", "Giọng đọc", icons.mic),
    ("background", "Nhạc nền", icons.layers),
    ("export", "Xuất video", icons.download),
)


class EditorPage(VoiceAndExportMixin, BasePage):
    """Trang chỉnh sửa một dự án đã lồng tiếng."""

    settings_needed = Signal(str)
    close_requested = Signal()

    def __init__(self, settings_provider, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings_provider = settings_provider
        self._work_dir = ""
        self._state = None
        self._project = None
        self._segments: list[dict] = []
        self._pending_edits: dict[int, str] = {}
        self._pending_subs: dict[int, str] = {}
        self._dirty_ids: set[int] = set()
        self._sub_dirty_ids: set[int] = set()
        self._structural_edit = False
        self._undo = QUndoStack(self)
        self._undo.setUndoLimit(_UNDO_LIMIT)
        self._preview = VoicePreview(self)
        self._narrator = Narrator()
        self._save_worker = None
        self._resynth_worker = None
        self._rebuild_worker = None
        self._preview_seg_worker = None
        self._wave_worker = None
        self._wave_workers: list = []
        self._edit_worker = None
        self._thumb_worker = None
        self._export_subs_file_worker = None
        self._export_audio_worker = None
        self._selection_end: float | None = None  # mốc dừng khi phát vùng chọn
        self._build()
        self._save_timer = debounce_timer(self, self._flush_edits)
        from autodub_gui.shortcuts import install_editor_shortcuts

        install_editor_shortcuts(self)

    # -- Dựng giao diện ------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_rail())
        body.addWidget(self._build_content(), 1)
        root.addLayout(body, 1)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(TOP_BAR_H)
        panel_background(bar, tokens.BG_SIDEBAR,
                         border=f"none; border-bottom: 1px solid "
                                f"{tokens.BORDER_SUBTLE}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(tokens.SP_4, 0, tokens.SP_4, 0)
        row.setSpacing(tokens.SP_3)

        logo = QLabel()
        logo.setPixmap(icons.app_logo(24))
        clear_background(logo)
        caption = QLabel("Chỉnh sửa dự án")
        caption.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_LABEL}px; "
            f"background: transparent;")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Tên dự án")
        self.name_edit.setReadOnly(True)
        self.name_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_CARD_TITLE}px; "
            f"font-weight: 600; padding: 0; }}")
        row.addWidget(logo)
        row.addWidget(caption)
        row.addWidget(self.name_edit, 1)

        self.save_indicator = SaveIndicator()
        row.addWidget(self.save_indicator)
        self.btn_export_top = PrimaryButton("Xuất video")
        self.btn_export_top.clicked.connect(lambda: self._show_tab("export"))
        row.addWidget(self.btn_export_top)
        return bar

    def _build_rail(self) -> QWidget:
        self.rail = QListWidget()
        self.rail.setObjectName("nav")
        self.rail.setFixedWidth(RAIL_W)
        self.rail.setSpacing(2)
        self.rail.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rail.setStyleSheet(
            f"QListWidget#nav {{ background: {tokens.BG_SIDEBAR}; "
            f"border: none; border-right: 1px solid {tokens.BORDER_SUBTLE}; }}")
        for _key, label, icon_fn in RAIL_ITEMS:
            item = QListWidgetItem(label)
            item.setIcon(icons.nav_icon(icon_fn))
            item.setToolTip(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rail.addItem(item)
        self.rail.currentRowChanged.connect(self._on_rail_changed)
        return self.rail

    def _build_content(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(tokens.SP_3, tokens.SP_3,
                                  tokens.SP_3, tokens.SP_3)
        layout.setSpacing(tokens.SP_3)

        self.banner = DirtyBanner()
        layout.addWidget(self.banner)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.player = VideoPlayer()
        self.player.position_changed.connect(self._on_position)
        self.player.open_requested.connect(self._open_other_folder)
        self.splitter.addWidget(self.player)
        self.splitter.addWidget(self._build_panels())
        self.splitter.setStretchFactor(0, _SPLIT_LEFT)
        self.splitter.setStretchFactor(1, _SPLIT_RIGHT)
        layout.addWidget(self.splitter, 1)

        self.timeline = Timeline()
        self.timeline.seek_requested.connect(self.player.seek)
        self.timeline.segment_clicked.connect(self._on_timeline_click)
        self.timeline.segment_moved.connect(self._on_segment_moved)
        self.timeline.split_requested.connect(self._on_split_at)
        self.timeline.selection_play_requested.connect(self._play_selection)
        layout.addWidget(self.timeline)

        self.log = LogPanel()
        self.log.setMaximumHeight(90)
        self.log.setVisible(False)
        layout.addWidget(self.log)
        return holder

    def _build_panels(self) -> QWidget:
        holder = QWidget()
        holder.setMinimumWidth(_MIN_LIST_W)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panels = QStackedWidget()

        self.overview = OverviewPanel()
        self.overview.open_folder.connect(self._open_work_folder)
        self.overview.open_subtitle.connect(self._open_subtitle)
        self.overview.open_youtube.connect(self._open_youtube)
        self.overview.open_other.connect(self._open_other_folder)
        self.overview.issue_clicked.connect(self._jump_to_issue)
        self.overview.context_saved.connect(self._save_context)

        self.subtitles = SubtitleListPanel()
        self.subtitles.text_edited.connect(self._on_text_edited)
        self.subtitles.subtitle_edited.connect(self._on_subtitle_edited)
        self.subtitles.segment_selected.connect(self._on_segment_selected)
        self.subtitles.play_requested.connect(self._play_segment)
        self.subtitles.resynth_requested.connect(self._resynth_one)
        self.subtitles.split_requested.connect(self._split_at_playhead)
        self.subtitles.merge_requested.connect(self._merge_with_next)
        self.subtitles.delete_requested.connect(self._delete_segment)
        self.subtitles.voice_changed.connect(self._on_segment_voice_changed)
        self.subtitles.add_requested.connect(self._add_segment)
        self.subtitles.ai_translate_requested.connect(self._ai_translate_one)
        self.subtitles.retranslate_all_requested.connect(self._ai_retranslate_all)

        self.qc_panel = QCPanel()
        self.qc_panel.issue_clicked.connect(self._jump_to_issue)

        self.audio_panel = AudioPanel()
        self.audio_panel.changed.connect(self._save_render_opts)
        self.voice_panel = VoicePanel()
        self.voice_panel.preview_requested.connect(self._preview_voice)
        self.voice_panel.resynth_all_requested.connect(self._save_all_and_resynth)
        self.voice_panel.changed.connect(self._save_render_opts)
        self.background_panel = BackgroundPanel()
        self.background_panel.changed.connect(self._save_render_opts)
        self.export_panel = ExportPanel()
        self.export_panel.export_requested.connect(self._export)
        self.export_panel.subtitles_requested.connect(self._export_subtitles)
        self.export_panel.style_requested.connect(self._open_style_dialog)
        self.export_panel.preview_requested.connect(self._preview_segment)
        self.export_panel.viral_shorts_requested.connect(self._open_viral_clipper_dialog)
        self.export_panel.export_srt_requested.connect(self._export_srt_file)
        self.export_panel.export_ass_requested.connect(self._export_ass_file)
        self.export_panel.export_audio_mp3_requested.connect(self._export_audio_mp3)
        self.export_panel.open_thumb_requested.connect(self._open_thumbnail)
        self.export_panel.copy_title_requested.connect(self._copy_youtube_title)
        self.export_panel.copy_tags_requested.connect(self._copy_youtube_hashtags)
        self.export_panel.copy_desc_requested.connect(self._copy_youtube_description)
        self.export_panel.copy_all_requested.connect(self._copy_youtube_all)
        self.export_panel.changed.connect(self._on_export_options_changed)
        self._preview.status_changed.connect(self.voice_panel.status.setText)
        # Khoá nút khi đang tổng hợp / phát, mở lại khi xong — giống hành vi
        # trên tab Giọng đọc AI.  Tín hiệu finished luôn được phát sau play()
        # dù là phát ngay hay phải chờ tổng hợp câu mẫu lần đầu.
        self._preview.finished.connect(
            lambda _ok: self.voice_panel.picker.set_preview_enabled(True))

        for widget in (self.overview, self.subtitles, self.qc_panel,
                       self.audio_panel, self.voice_panel,
                       self.background_panel, self.export_panel):
            self.panels.addWidget(self._scrollable(widget))
        layout.addWidget(self.panels)
        # Mở sẵn mục Phụ đề vì đó là chỗ người dùng làm việc nhiều nhất.
        self.panels.setCurrentIndex(1)
        self.rail.setCurrentRow(1)
        return holder

    @staticmethod
    def _scrollable(widget: QWidget) -> QWidget:
        """Bọc bảng trong khung cuộn — cửa sổ thấp thì cuộn, không cắt nút.

        Bảng đã tự cuộn (OverviewPanel) hay tự quản không gian (danh sách
        phụ đề) thì giữ nguyên.
        """
        from PySide6.QtWidgets import QScrollArea

        if isinstance(widget, (QScrollArea, SubtitleListPanel)):
            return widget
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        clear_background(area)
        clear_background(area.viewport())
        holder = QWidget()
        clear_background(holder)
        wrap = QVBoxLayout(holder)
        wrap.setContentsMargins(0, 0, tokens.SP_2, 0)
        wrap.addWidget(widget)
        wrap.addStretch()
        area.setWidget(holder)
        return area

    def _on_rail_changed(self, index: int) -> None:
        if 0 <= index < self.panels.count():
            self.panels.setCurrentIndex(index)

    def _show_tab(self, key: str) -> None:
        """Mở một mục trong cột biểu tượng bên trái."""
        for index, (item_key, _label, _icon) in enumerate(RAIL_ITEMS):
            if item_key == key:
                self.rail.setCurrentRow(index)
                return

    # -- Mở dự án ------------------------------------------------------
    def open_work_dir(self, work_dir: str) -> None:
        """Nạp một dự án vào trình chỉnh sửa."""
        from autodub.editor import EditorError, load_work_dir
        from autodub_gui.projects import load_project

        if self._work_dir and self.has_unsaved_changes():
            if not confirm_discard(self, "Dự án đang mở"):
                return
        self._flush_edits()
        self.player.release()
        try:
            self._state = load_work_dir(work_dir)
        except EditorError as e:
            ConfirmDialog.show_error(
                self, "Không mở được dự án này",
                "Thư mục này chưa có bản dịch nên chưa chỉnh sửa được. Hãy "
                "chạy lồng tiếng cho video trước, hoặc chọn một thư mục khác.",
                detail=str(e))
            return
        self._work_dir = work_dir
        self._project = load_project(work_dir)
        self._segments = self._state.segments
        self._undo.clear()
        self._dirty_ids.clear()
        self._sub_dirty_ids.clear()
        self._pending_edits.clear()
        self._pending_subs.clear()
        self._structural_edit = False
        self._apply_state()

    def _apply_state(self) -> None:
        """Đổ dữ liệu vừa nạp lên toàn bộ giao diện."""
        self.name_edit.setText(self._project.title)
        self.subtitles.set_segments(self._segments, self._state.target.text_field)
        self.timeline.set_segments(self._segments)
        self.overview.set_project(self._project, len(self._segments),
                                  self._read_quality())
        self.overview.set_context(self._read_context())
        self._load_render_opts()
        self.banner.set_count(0, 0)
        self._refresh_qc()
        self.export_panel.refresh_history(self._work_dir)
        self._refresh_social_metadata()
        self.save_indicator.set_state("idle")
        self._load_video()
        self._load_waveform()

    def _read_quality(self) -> dict:
        from autodub.workdir import data_path
        import json

        try:
            with open(data_path(self._work_dir, "quality_report.json"),
                      encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _read_context(self) -> dict:
        from autodub.workdir import data_path
        import json

        try:
            with open(data_path(self._work_dir, "video_context.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_context(self, context: dict) -> None:
        """Lưu ngữ cảnh dịch người dùng vừa sửa vào video_context.json."""
        if not self._work_dir:
            return
        from autodub.utils import save_json_atomic
        from autodub.workdir import data_path

        try:
            save_json_atomic(context,
                             data_path(self._work_dir, "video_context.json"))
            TOASTS.info("Đã lưu ngữ cảnh dịch của video này.")
        except OSError as e:
            TOASTS.warn(f"Không lưu được ngữ cảnh: {e}")

    def _load_video(self) -> None:
        target = (self._project.output_path or self._state.video_path or "")
        if target and self.player.open(target):
            self.player.set_segments(self._segments,
                                     self._state.target.text_field)
            self._sync_overlay(target)
            dur = self._project.duration_s or self.player.duration()
            self.timeline.set_duration(dur)
            self.player.duration_changed.connect(self.timeline.set_duration)
            self._start_thumb_worker(target, dur)
        else:
            self.timeline.set_duration(self._project.duration_s)

    def _start_thumb_worker(self, video_path: str, duration_s: float) -> None:
        """Start background thumbnail extraction, cancelling the previous run."""
        from autodub_gui.workers import TimelineThumbnailWorker

        self._stop_thumb_worker()
        if not video_path or duration_s <= 0:
            return
        worker = TimelineThumbnailWorker(
            video_path, duration_s, self._work_dir, parent=self)
        worker.ready.connect(self.timeline.set_thumbnails)
        worker.finished.connect(lambda w=worker: self._thumb_worker_finished(w))
        self._thumb_worker = worker
        worker.start()

    def _thumb_worker_finished(self, worker) -> None:
        """Drop the wrapper before deleteLater invalidates its C++ object."""
        if self._thumb_worker is worker:
            self._thumb_worker = None
        worker.deleteLater()

    def _stop_thumb_worker(self) -> None:
        """Cancel the thumbnail thread, tolerating an already deleted Qt object."""
        worker = self._thumb_worker
        self._thumb_worker = None
        if worker is None:
            return
        try:
            worker.ready.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            # quit() is ineffective because this QThread overrides run().
            worker.cancel()
            worker.wait(2000)
        except RuntimeError:
            # deleteLater may already have destroyed the underlying C++ object.
            pass

    def _sync_overlay(self, opened_path: str) -> None:
        """Một video chỉ được có MỘT lớp phụ đề.

        Video kết quả với chế độ «ghi thẳng vào hình» đã có chữ nằm trong
        pixel — bật thêm lớp chữ xem trước là thành hai phụ đề chồng nhau.
        Khi đó tắt lớp xem trước đi: chữ bạn sửa vẫn được lưu, và bấm «Ghi
        lại phụ đề vào video» là thấy ngay bản mới.
        """
        from autodub.editor import load_render_opts

        opened_output = bool(
            self._project and self._project.output_path
            and os.path.normcase(os.path.normpath(opened_path))
            == os.path.normcase(os.path.normpath(self._project.output_path)))
        burned = (opened_output and load_render_opts(self._work_dir)
                  .get("subtitle_mode") == "burn")
        self.player.set_overlay_enabled(not burned)

    def _load_waveform(self) -> None:
        """Nạp dạng sóng cho từng track có mặt; thiếu hết thì về 1 dải cũ."""
        import functools

        from autodub_gui.workers import WaveformWorker

        sources = waveform.track_sources(self._work_dir)
        self._wave_workers = []
        for kind in ("original", "voice", "music"):
            self.timeline.set_track_available(kind, kind in sources)
        if not sources:
            path = waveform.source_for(self._work_dir)
            if not path:
                self.timeline.set_peaks([])
                return
            self.timeline.set_loading(True)
            worker = WaveformWorker(path, parent=self)
            worker.ready.connect(self.timeline.set_peaks)
            self._wave_worker = worker
            worker.start()
            return
        self.timeline.set_loading(True)
        for kind, path in sources.items():
            worker = WaveformWorker(
                path, parent=self,
                cache_name=waveform.cache_name_for(path))
            worker.ready.connect(
                functools.partial(self.timeline.set_track_peaks, kind))
            self._wave_workers.append(worker)
            worker.start()

    def _load_render_opts(self) -> None:
        from autodub.editor import load_render_opts

        opts = load_render_opts(self._work_dir)
        settings = self._settings_provider()
        self.audio_panel.load(opts, settings)
        
        # Nhạc nền: lấy từ opts của dự án hoặc fallback sang cài đặt mặc định đã lưu
        bg_mode_default = getattr(settings, "bg_mode", "demucs")
        bg_duck_default = getattr(settings, "bg_duck_db", DEFAULT_DUCK_DB)
        self.background_panel.mode.set_key(opts.get("bg_mode", bg_mode_default))
        self.background_panel.duck.set_value(
            float(opts.get("bg_duck_db", bg_duck_default)))
        self.background_panel.set_separated(self._has_separated_audio())

        # Phụ đề
        self.export_panel.subtitle.set_key(
            opts.get("subtitle_mode", settings.subtitle_mode))
        self.voice_panel.picker.reload(settings)

        # Giọng đọc
        from autodub.speech.tts import voices as voice_catalog
        project_voice = voice_catalog.resolve(
            settings, opts.get("voice") or getattr(settings, "vieneu_voice", "") or self._project.voice)
        self.voice_panel.set_project_voice(project_voice)
        self.overview.set_voice(project_voice)
        selected_voice = opts.get("selected_voice") or getattr(settings, "vieneu_voice", "")
        if selected_voice and selected_voice != project_voice:
            self.voice_panel.picker.set_voice(selected_voice)
            self.voice_panel._refresh_hint()
        self.voice_panel.speed.set_value(
            float(opts.get("voice_speed", settings.voice_speed)))
        self.voice_panel.set_speakers(
            self._segments,
            opts.get("speaker_voices"),
            opts.get("speaker_profiles"),
        )
        self.export_panel.set_source_info(0, 0, 0)

        # Vùng che mờ và kiểu phụ đề
        blur_def = getattr(settings, "blur_regions_list", lambda: [])() or []
        self._blur_regions = list(opts.get("blur_regions") if "blur_regions" in opts else blur_def)
        self._subtitle_style = opts.get("subtitle_style")
        self.export_panel.preset.set_key(
            (self._subtitle_style or {}).get("preset")
            or opts.get("subtitle_preset") or settings.subtitle_preset)

        # Logo & Watermark
        self._logo_path = opts.get("logo_path", getattr(settings, "logo_path", ""))
        self._logo_position = opts.get("logo_position", getattr(settings, "logo_position", "top_right"))
        self._logo_scale = opts.get("logo_scale", getattr(settings, "logo_scale", 0.12))
        self._logo_opacity = opts.get("logo_opacity", getattr(settings, "logo_opacity", 0.85))
        self._logo_margin = opts.get("logo_margin", getattr(settings, "logo_margin", 24))
        self._logo_motion = opts.get("logo_motion", getattr(settings, "logo_motion", "static"))
        self._watermark_text = opts.get("watermark_text", getattr(settings, "watermark_text", ""))
        self._watermark_opacity = opts.get("watermark_opacity", getattr(settings, "watermark_opacity", 0.28))
        self._watermark_font_size = opts.get("watermark_font_size", getattr(settings, "watermark_font_size", 26))
        self._watermark_color = opts.get("watermark_color", getattr(settings, "watermark_color", "white"))
        self._watermark_speed = opts.get("watermark_speed", getattr(settings, "watermark_speed", 40))
        self._watermark_motion = opts.get("watermark_motion", getattr(settings, "watermark_motion", "bounce"))

        # Mask options (Che / Xóa phụ đề)
        self._mask_method = opts.get("mask_method", getattr(settings, "mask_method", "blur"))
        self._inpaint_engine = opts.get("inpaint_engine", getattr(settings, "inpaint_engine", "lama_onnx"))
        self._inpaint_device = opts.get("inpaint_device", getattr(settings, "inpaint_device", "auto"))

        self._apply_style_to_player()

    def _has_separated_audio(self) -> bool:
        from autodub.workdir import data_path

        return os.path.isfile(data_path(self._work_dir, "no_vocals.wav"))

    def _save_render_opts(self) -> None:
        """Ghi tùy chọn của dự án và đồng bộ thành mặc định cho các video sau."""
        if not self._work_dir:
            return
        from autodub.editor import load_render_opts, save_render_opts

        opts = load_render_opts(self._work_dir)
        opts.update(self.audio_panel.values())
        opts.update(self.background_panel.values())
        opts.update(self.voice_panel.values())
        opts.update(self.export_panel.values())
        opts["selected_voice"] = self.voice_panel.picker.voice()
        opts["voice_speed"] = self.voice_panel.speed.value()
        opts["subtitle_mode"] = self.export_panel.subtitle.current_key()
        opts["subtitle_preset"] = self.export_panel.preset.current_key()
        opts["blur_regions"] = list(getattr(self, "_blur_regions", []))
        if getattr(self, "_subtitle_style", None):
            opts["subtitle_style"] = self._subtitle_style
        opts["logo_path"] = getattr(self, "_logo_path", "")
        opts["logo_position"] = getattr(self, "_logo_position", "top_right")
        opts["logo_scale"] = getattr(self, "_logo_scale", 0.12)
        opts["logo_opacity"] = getattr(self, "_logo_opacity", 0.85)
        opts["logo_margin"] = getattr(self, "_logo_margin", 24)
        opts["logo_motion"] = getattr(self, "_logo_motion", "static")
        opts["watermark_text"] = getattr(self, "_watermark_text", "")
        opts["watermark_opacity"] = getattr(self, "_watermark_opacity", 0.28)
        opts["watermark_font_size"] = getattr(self, "_watermark_font_size", 26)
        opts["watermark_color"] = getattr(self, "_watermark_color", "white")
        opts["watermark_speed"] = getattr(self, "_watermark_speed", 40)
        opts["watermark_motion"] = getattr(self, "_watermark_motion", "bounce")
        opts["mask_method"] = getattr(self, "_mask_method", "blur")
        opts["inpaint_engine"] = getattr(self, "_inpaint_engine", "lama_onnx")
        opts["inpaint_device"] = getattr(self, "_inpaint_device", "auto")
        try:
            save_render_opts(self._work_dir, opts)
        except OSError as e:
            TOASTS.warn(f"Không lưu được tùy chọn của dự án: {e}")

        # Tự động ghi nhớ cho các video tiếp theo
        self._sync_editor_defaults_to_env(opts)

    def _sync_editor_defaults_to_env(self, opts: dict) -> None:
        """Tự động lưu các lựa chọn trong Trình chỉnh sửa thành cấu hình mặc định cho các video sau."""
        try:
            from autodub_gui.env_store import bool_to_env, write_env
            import json

            updates = {}
            if "voice_speed" in opts:
                updates["VOICE_SPEED"] = str(opts["voice_speed"])
            if "selected_voice" in opts and opts["selected_voice"]:
                updates["VIENEU_VOICE"] = str(opts["selected_voice"])
            if "subtitle_mode" in opts:
                updates["SUBTITLE_MODE"] = str(opts["subtitle_mode"])
            if "subtitle_preset" in opts and opts["subtitle_preset"]:
                updates["SUBTITLE_PRESET"] = str(opts["subtitle_preset"])
            if "bg_mode" in opts:
                updates["BG_MODE"] = str(opts["bg_mode"])
            if "bg_duck_db" in opts:
                updates["BG_DUCK_DB"] = str(opts["bg_duck_db"])
            if "aspect_preset" in opts:
                updates["VIDEO_ASPECT_PRESET"] = str(opts["aspect_preset"])
            if "reframe_mode" in opts:
                updates["VIDEO_REFRAME_MODE"] = str(opts["reframe_mode"])
            if "auto_sfx_enabled" in opts:
                updates["AUTO_SFX_ENABLED"] = bool_to_env(bool(opts["auto_sfx_enabled"]))
            if "sfx_preset" in opts:
                updates["SFX_PRESET"] = str(opts["sfx_preset"])
            if "sfx_volume" in opts:
                updates["SFX_VOLUME"] = str(opts["sfx_volume"])
            if "voice_postprocess" in opts:
                updates["VOICE_POSTPROCESS"] = bool_to_env(bool(opts["voice_postprocess"]))
            if "voice_target_lufs" in opts:
                updates["VOICE_TARGET_LUFS"] = str(opts["voice_target_lufs"])
            if "bg_duck_voice_db" in opts:
                updates["BG_DUCK_VOICE_DB"] = str(opts["bg_duck_voice_db"])
            if "soft_timing_fit" in opts:
                updates["SOFT_TIMING_FIT"] = bool_to_env(bool(opts["soft_timing_fit"]))
            if "timing_max_drift_s" in opts:
                updates["TIMING_MAX_DRIFT_S"] = str(opts["timing_max_drift_s"])
            if "mask_method" in opts:
                updates["MASK_METHOD"] = str(opts["mask_method"])
            if "inpaint_engine" in opts:
                updates["INPAINT_ENGINE"] = str(opts["inpaint_engine"])
            if "inpaint_device" in opts:
                updates["INPAINT_DEVICE"] = str(opts["inpaint_device"])


            # Logo
            if "logo_path" in opts:
                updates["LOGO_PATH"] = str(opts["logo_path"])
            if "logo_position" in opts:
                updates["LOGO_POSITION"] = str(opts["logo_position"])
            if "logo_scale" in opts:
                updates["LOGO_SCALE"] = str(opts["logo_scale"])
            if "logo_opacity" in opts:
                updates["LOGO_OPACITY"] = str(opts["logo_opacity"])
            if "logo_margin" in opts:
                updates["LOGO_MARGIN"] = str(opts["logo_margin"])
            if "logo_motion" in opts:
                updates["LOGO_MOTION"] = str(opts["logo_motion"])

            # Watermark
            if "watermark_text" in opts:
                updates["WATERMARK_TEXT"] = str(opts["watermark_text"])
            if "watermark_opacity" in opts:
                updates["WATERMARK_OPACITY"] = str(opts["watermark_opacity"])
            if "watermark_font_size" in opts:
                updates["WATERMARK_FONT_SIZE"] = str(opts["watermark_font_size"])
            if "watermark_color" in opts:
                updates["WATERMARK_COLOR"] = str(opts["watermark_color"])
            if "watermark_speed" in opts:
                updates["WATERMARK_SPEED"] = str(opts["watermark_speed"])
            if "watermark_motion" in opts:
                updates["WATERMARK_MOTION"] = str(opts["watermark_motion"])

            # Blur regions
            if "blur_regions" in opts and isinstance(opts["blur_regions"], list):
                updates["BLUR_REGIONS"] = json.dumps(opts["blur_regions"])

            # Subtitle style
            style = opts.get("subtitle_style")
            if isinstance(style, dict):
                if "font" in style: updates["SUBTITLE_FONT"] = str(style["font"])
                if "font_size" in style: updates["SUBTITLE_FONT_SIZE"] = str(style["font_size"])
                if "position" in style: updates["SUBTITLE_POSITION"] = str(style["position"])
                if "color" in style: updates["SUBTITLE_COLOR"] = str(style["color"])
                if "outline" in style: updates["SUBTITLE_OUTLINE"] = str(style["outline"])
                if "outline_color" in style: updates["SUBTITLE_OUTLINE_COLOR"] = str(style["outline_color"])
                if "shadow" in style: updates["SUBTITLE_SHADOW"] = str(style["shadow"])
                if "bold" in style: updates["SUBTITLE_BOLD"] = bool_to_env(bool(style["bold"]))
                if "box" in style: updates["SUBTITLE_BOX"] = str(style["box"])
                if "box_color" in style: updates["SUBTITLE_BOX_COLOR"] = str(style["box_color"])
                if "box_opacity" in style: updates["SUBTITLE_BOX_OPACITY"] = str(style["box_opacity"])
                if "display" in style: updates["SUBTITLE_DISPLAY"] = str(style["display"])
                if "words_per_cue" in style: updates["KARAOKE_WORDS_PER_CUE"] = str(style["words_per_cue"])
                if "effect" in style: updates["KARAOKE_EFFECT"] = str(style["effect"])
                if "highlight_color" in style: updates["KARAOKE_HIGHLIGHT_COLOR"] = str(style["highlight_color"])

            if updates:
                write_env(updates)
        except Exception:
            pass

    def _on_export_options_changed(self) -> None:
        """Đổi bộ kiểu chữ ở ô chọn thì áp luôn vào kiểu đang dùng."""
        from autodub.media.subtitle import preset_style

        preset = self.export_panel.preset.current_key()
        current = getattr(self, "_subtitle_style", None) or {}
        if preset and preset != current.get("preset"):
            # Trùng với bộ trong Cài đặt thì lấy đủ tinh chỉnh từ đó — cùng
            # logic với lúc tạo dự án, để hai nơi ra cùng một chữ trên video.
            try:
                settings = self._settings_provider()
                self._subtitle_style = (settings.subtitle_style()
                                        if preset == settings.subtitle_preset
                                        else preset_style(preset))
            except Exception:  # noqa: BLE001 — cấu hình hỏng thì dùng bộ sẵn
                self._subtitle_style = preset_style(preset)
        self._save_render_opts()
        self._apply_style_to_player()

    def _apply_style_to_player(self) -> None:
        """Cho khung xem trước hiện chữ đúng kiểu sẽ ghi vào video.

        Chữ xem trước và chữ ghi vào hình dùng chung một dict kiểu, nên xem
        trước không còn là "một lớp phụ đề khác" mà đúng là bản nháp của phụ
        đề thật.
        """
        from autodub.media.subtitle import normalize_style

        style = normalize_style(getattr(self, "_subtitle_style", None))
        self.player.set_subtitle_style(style)

    # -- Sửa chữ và tự lưu ---------------------------------------------
    def _on_text_edited(self, seg_id: int, text: str) -> None:
        self._pending_edits[seg_id] = text
        self.save_indicator.set_state("saving")
        self._save_timer.start()

    def _on_subtitle_edited(self, seg_id: int, text: str) -> None:
        """Sửa PHỤ ĐỀ riêng: chỉ cần ghi lại chữ lên hình, khỏi đọc lại giọng."""
        self._pending_subs[seg_id] = text
        self.save_indicator.set_state("saving")
        self._save_timer.start()

    def _flush_edits(self) -> None:
        """Ghi những câu vừa sửa xuống đĩa."""
        if not self._work_dir or not (self._pending_edits
                                      or self._pending_subs):
            return
        from autodub.editor import (EditorError, save_segment_texts,
                                    save_subtitle_texts)
        from autodub.text.srt import SUBTITLE_FIELD

        edits = dict(self._pending_edits)
        subs = dict(self._pending_subs)
        self._pending_edits.clear()
        self._pending_subs.clear()
        try:
            changed = (save_segment_texts(self._work_dir, edits,
                                          self._state.target.key)
                       if edits else [])
            sub_changed = (save_subtitle_texts(self._work_dir, subs,
                                               self._state.target.key)
                           if subs else [])
        except (EditorError, OSError) as e:
            self.save_indicator.set_state("error", str(e))
            return

        by_id = {s.get("id"): s for s in self._segments}
        for seg_id, text in edits.items():
            if seg_id in by_id:
                by_id[seg_id][self._state.target.text_field] = text
        for seg_id, text in subs.items():
            segment = by_id.get(seg_id)
            if segment is None:
                continue
            clean = text.strip()
            if clean and clean != str(
                    segment.get(self._state.target.text_field, "")):
                segment[SUBTITLE_FIELD] = clean
            else:
                segment.pop(SUBTITLE_FIELD, None)

        self._dirty_ids.update(changed)
        self._sub_dirty_ids.update(sub_changed)
        self._refresh_banner()
        if sub_changed or changed:
            # Chữ trên khung xem trước phải đổi ngay dù sửa phụ đề riêng
            # (sub_vi) hay sửa chữ giọng đọc (text_vi) — cả hai đều ảnh
            # hưởng tới phụ đề hiện trên màn hình vì subtitle_text() dùng
            # sub_vi làm ghi đè, còn nếu thiếu thì fallback về text_vi.
            self.player.set_segments(self._segments,
                                     self._state.target.text_field)
        import time

        self.save_indicator.set_state(
            "saved", "lúc " + time.strftime("%H:%M"))

    def _refresh_banner(self) -> None:
        voice = len(self._dirty_ids) or (
            1 if getattr(self, "_structural_edit", False) else 0)
        self.banner.set_count(voice, len(self._sub_dirty_ids))
        self._refresh_qc()

    def _refresh_qc(self) -> None:
        """Cập nhật bảng Kiểm tra theo trạng thái hiện tại của dự án."""
        if not self._work_dir or self._state is None:
            return
        self.qc_panel.refresh(self._segments, self._read_quality(),
                              self._dirty_ids,
                              self._state.target.text_field)

    def has_unsaved_changes(self) -> bool:
        return bool(self._pending_edits or self._pending_subs)

    # -- Đồng bộ với video và dải thời gian -----------------------------
    def _on_position(self, seconds: float) -> None:
        self.timeline.set_position(seconds)
        # Đang phát vùng chọn → tự dừng khi chạy hết vùng
        if self._selection_end is not None and seconds >= self._selection_end:
            self._selection_end = None
            self.player.pause()
        segment = self.player.current_segment()
        if segment is not None:
            self.subtitles.highlight(int(segment.get("id", -1)))

    def _on_segment_selected(self, seg_id: int) -> None:
        self.timeline.set_selected(seg_id)
        segment = self._segment(seg_id)
        if segment is not None:
            self.player.seek(float(segment.get("start", 0.0)))

    def _jump_to_issue(self, seg_id: int) -> None:
        """Bấm một dòng trong báo cáo chất lượng — nhảy tới đúng câu đó."""
        self._show_tab("subtitles")
        self.subtitles.highlight(seg_id)
        self._on_segment_selected(seg_id)

    def _on_timeline_click(self, seg_id: int) -> None:
        self.timeline.set_selected(seg_id)
        segment = self._segment(seg_id)
        if segment is not None:
            self.player.seek(float(segment.get("start", 0.0)))

    def _segment(self, seg_id: int) -> dict | None:
        return next((s for s in self._segments if s.get("id") == seg_id), None)

    def _on_segment_moved(self, seg_id: int, start: float, end: float) -> None:
        segment = self._segment(seg_id)
        if segment is None:
            return
        self._undo.push(MoveSegmentCommand(self, seg_id, start, end))

    # -- Thao tác trên câu thoại ---------------------------------------
    def _play_segment(self, seg_id: int) -> None:
        segment = self._segment(seg_id)
        if segment is not None:
            self.player.seek(float(segment.get("start", 0.0)))
            self.player.play()

    def _play_selection(self, start: float, end: float) -> None:
        """Phát vùng thời gian đã chọn trên thước; tự dừng ở cuối vùng."""
        self._selection_end = end
        self.player.seek(start)
        self.player.play()

    def _on_segment_voice_changed(self, seg_id: int, voice: str) -> None:
        """Gán (hoặc bỏ) giọng riêng cho một câu và đánh dấu cần đọc lại."""
        from autodub.editor import set_segment_voice

        if not self._work_dir:
            return
        try:
            changed = set_segment_voice(
                self._work_dir, seg_id, voice,
                self.target_key())
        except Exception as e:  # noqa: BLE001
            from autodub_gui.ui.toast import TOASTS
            TOASTS.warn(f"Không lưu được giọng riêng: {e}")
            return
        if changed:
            # Cập nhật bản sao trong bộ nhớ để các thao tác tiếp theo nhất quán.
            seg = self._segment(seg_id)
            if seg is not None:
                if voice:
                    seg["voice"] = voice
                else:
                    seg.pop("voice", None)
            # Câu này cần đọc lại giọng để ra đúng voice mới.
            self._dirty_ids.add(seg_id)
            self._refresh_banner()
            from autodub_gui.ui.toast import TOASTS
            if voice:
                TOASTS.info(f"Câu {seg_id}: đọc bằng giọng «{voice}». "
                            "Bấm «Đọc lại câu này» để áp dụng.")
            else:
                TOASTS.info(f"Câu {seg_id}: đã bỏ giọng riêng, "
                            "quay về giọng chung của dự án.")

    def _add_segment(self) -> None:
        """Chèn một câu mới ngay sau câu đang chọn."""
        selected = self.subtitles.selected_id()
        after = selected if selected > 0 else (
            self._segments[-1]["id"] if self._segments else 0)
        segment = self._segment(after)
        start = float(segment.get("end", 0.0)) + 0.05 if segment else 0.0
        self._undo.push(AddSegmentCommand(self, after, start, start + 1.0))

    def _delete_segment(self, seg_id: int) -> None:
        confirmed, _ = ConfirmDialog.ask(
            self, "Xóa câu thoại",
            f"Xóa câu số {seg_id} khỏi dự án? Giọng đọc của câu này cũng bị "
            "xóa theo. Bạn có thể hoàn tác bằng Ctrl+Z.",
            kind="danger", confirm_label="Xóa câu")
        if confirmed:
            self._undo.push(DeleteSegmentCommand(self, seg_id))

    def _split_at_playhead(self, seg_id: int) -> None:
        segment = self._segment(seg_id)
        if segment is None:
            return
        position = self.player.position()
        start, end = float(segment["start"]), float(segment["end"])
        if not (start < position < end):
            position = (start + end) / 2
        self._undo.push(SplitSegmentCommand(self, seg_id, position))

    def _on_split_at(self, seg_id: int, at_time: float) -> None:
        self._undo.push(SplitSegmentCommand(self, seg_id, at_time))

    def _merge_with_next(self, seg_id: int) -> None:
        index = next((i for i, s in enumerate(self._segments)
                      if s.get("id") == seg_id), -1)
        if index < 0 or index + 1 >= len(self._segments):
            TOASTS.warn("Không có câu nào bên dưới để gộp.")
            return
        next_id = int(self._segments[index + 1]["id"])
        self._undo.push(MergeSegmentCommand(self, [seg_id, next_id]))

    def reload_segments(self) -> None:
        """Đọc lại danh sách câu từ đĩa sau khi cấu trúc thay đổi."""
        from autodub.editor import load_work_dir

        self._state = load_work_dir(self._work_dir)
        self._segments = self._state.segments
        self.subtitles.set_segments(self._segments,
                                    self._state.target.text_field)
        self.timeline.set_segments(self._segments)
        self.player.set_segments(self._segments,
                                 self._state.target.text_field)
        # Thêm, xóa, tách hay gộp câu đều làm một vài câu mất giọng đọc, nhưng
        # số thứ tự vừa được đánh lại nên không thể biết chắc là câu nào. Bật
        # băng nhắc để người dùng đọc lại trước khi xuất, thay vì âm thầm ghép
        # ra video thiếu tiếng.
        self._structural_edit = True
        self._refresh_banner()

    def release_video(self) -> float:
        """Nhả tệp video đang mở trước một thao tác xóa/ghi đè tệp đó.

        Trên Windows, trình phát giữ tệp đang mở nên mọi lệnh xóa
        dubbed_video.mp4 (khi sửa cấu trúc câu hay xuất lại) đều vấp
        WinError 32. Trả về vị trí đang xem để mở lại đúng chỗ.
        """
        position = self.player.position()
        self.player.release()
        return position

    def restore_video(self, position: float | None) -> None:
        """Mở lại video sau khi đã nhả, quay về đúng thời điểm đang xem.

        Video kết quả có thể vừa bị xóa để làm mới — khi đó rơi về video
        gốc, người dùng vẫn xem tiếp được và phụ đề xem trước vẫn chạy.
        """
        if position is None:
            return
        candidates = (self._project.output_path if self._project else "",
                      self._state.video_path if self._state else "")
        target = next((p for p in candidates if p and os.path.isfile(p)), "")
        if not target:
            self.player.show_empty()
            return
        if self.player.open(target):
            self.player.set_segments(self._segments,
                                     self._state.target.text_field)
            self._sync_overlay(target)
            self.player.seek(position)

    def report_error(self, message: str) -> None:
        """Hiện lỗi của một thao tác sửa câu bằng lời thường."""
        ConfirmDialog.show_error(
            self, "Không thực hiện được thao tác này", message)

    def work_dir(self) -> str:
        return self._work_dir

    def target_key(self) -> str:
        return self._state.target.key if self._state else "vi"

    def _ai_translate_one(self, seg_id: int) -> None:
        """Dịch lại một câu thoại bằng AI bên thứ 3."""
        if not self._work_dir:
            return
        import threading
        from PySide6.QtCore import QTimer
        from autodub.config import Settings
        from autodub.editor import retranslate_segment_ai
        from autodub_gui.ui.toast import TOASTS

        settings = self._settings_provider() if callable(self._settings_provider) else Settings.load()
        has_key = bool(
            getattr(settings, "gemini_api_key", "").strip()
            or getattr(settings, "deepseek_api_key", "").strip()
            or getattr(settings, "openrouter_api_key", "").strip()
            or getattr(settings, "openai_api_key", "").strip()
        )
        if not has_key:
            TOASTS.warn("Chưa cấu hình Google Gemini API Key. Vui lòng vào Cài đặt > Dịch thuật để nhập key Gemini.")
            return

        TOASTS.info(f"Đang dịch lại câu {seg_id} bằng AI...")

        def _worker():
            try:
                new_text = retranslate_segment_ai(
                    self._work_dir,
                    seg_id,
                    target_key=self.target_key(),
                    settings=settings,
                )
                def _done():
                    self._on_text_edited(seg_id, new_text)
                    self._flush_edits()
                    self.reload_segments()
                    TOASTS.success(f"Câu {seg_id}: đã dịch lại bằng AI thành công!")
                QTimer.singleShot(0, _done)
            except Exception as e:
                def _err():
                    TOASTS.error(f"Lỗi dịch lại câu {seg_id}: {e}")
                QTimer.singleShot(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    def _ai_retranslate_all(self) -> None:
        """Dịch lại toàn bộ các câu thoại trong dự án bằng AI bên thứ 3."""
        if not self._work_dir or not self._segments:
            return
        import threading
        from PySide6.QtCore import QTimer
        from autodub.config import Settings
        from autodub.editor import retranslate_all_segments_ai
        from autodub.progress import ProgressReporter
        from autodub_gui.ui.modal import ConfirmDialog
        from autodub_gui.ui.toast import TOASTS

        settings = self._settings_provider() if callable(self._settings_provider) else Settings.load()
        has_key = bool(
            getattr(settings, "custom_ai_api_key", "").strip()
            or getattr(settings, "gemini_api_key", "").strip()
            or getattr(settings, "deepseek_api_key", "").strip()
            or getattr(settings, "openrouter_api_key", "").strip()
            or getattr(settings, "openai_api_key", "").strip()
        )
        if not has_key:
            TOASTS.warn("Chưa cấu hình API Key AI. Vui lòng vào Cài đặt > Dịch thuật.")
            return

        confirmed, _ = ConfirmDialog.ask(
            self,
            "Dịch lại toàn bộ dự án bằng AI",
            f"Bạn có muốn dịch lại toàn bộ {len(self._segments)} câu bằng AI bên thứ 3?\n"
            "Bản dịch mới sẽ tự động cập nhật vào danh sách và làm mới dự án.",
            confirm_label="Bắt đầu dịch lại",
            cancel_label="Khoan đã",
        )
        if not confirmed:
            return

        self._flush_edits()
        TOASTS.info(f"Bắt đầu dịch lại {len(self._segments)} câu bằng AI...")
        self.save_indicator.set_state("saving", "Đang dịch AI...")

        def _worker():
            try:
                rep = ProgressReporter()
                translated = retranslate_all_segments_ai(
                    self._work_dir,
                    target_key=self.target_key(),
                    settings=settings,
                    reporter=rep,
                )
                def _done():
                    self._dirty_ids.update(int(s["id"]) for s in self._segments)
                    self.reload_segments()
                    self._refresh_banner()
                    self.save_indicator.set_state("saved", "Đã dịch AI xong")
                    TOASTS.success(f"Đã dịch lại xong toàn bộ {len(translated)} câu bằng AI!")
                QTimer.singleShot(0, _done)
            except Exception as e:
                def _err():
                    self.save_indicator.set_state("error", str(e))
                    TOASTS.error(f"Lỗi dịch lại dự án: {e}")
                QTimer.singleShot(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    # -- Mở tệp và thư mục ---------------------------------------------
    def _open_work_folder(self) -> None:
        ok, message = open_folder(self._work_dir)
        if not ok:
            TOASTS.warn(message)

    def _open_subtitle(self) -> None:
        path = os.path.join(self._work_dir, self._state.target.srt_name)
        ok, message = open_file(path)
        if not ok:
            TOASTS.warn(message)

    def _open_youtube(self) -> None:
        from autodub.workdir import youtube_dir

        ok, message = open_folder(youtube_dir(self._work_dir))
        if not ok:
            TOASTS.warn(message)

    def _open_other_folder(self) -> None:
        """Mở một thư mục dự án bất kỳ, giữ chức năng của bản cũ."""
        path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục dự án", "output")
        if path:
            self.open_work_dir(path)

    # -- Phím tắt ------------------------------------------------------
    def undo(self) -> None:
        self._undo.undo()

    def redo(self) -> None:
        self._undo.redo()

    def split_current_segment(self) -> None:
        """Tách câu tại vị trí con trỏ phát (Ctrl+B)."""
        if not self._work_dir or not self._segments:
            return
        pos = self.player.position()
        # 1. Tìm câu đang nằm dưới con trỏ phát
        target_seg = None
        for seg in self._segments:
            if float(seg.get("start", 0.0)) <= pos <= float(seg.get("end", 0.0)):
                target_seg = seg
                break

        # 2. Nếu con trỏ không nằm trong câu nào, lấy câu đang chọn (nếu có)
        if target_seg is None:
            selected_id = self.subtitles.selected_id()
            if selected_id > 0:
                target_seg = self._segment(selected_id)

        if target_seg is None:
            TOASTS.warn("Không tìm thấy câu nào tại vị trí con trỏ phát để tách.")
            return

        seg_id = int(target_seg["id"])
        start = float(target_seg.get("start", 0.0))
        end = float(target_seg.get("end", 0.0))

        if start <= pos <= end:
            split_time = pos
            if not (start + 0.2 <= split_time <= end - 0.2):
                TOASTS.warn("Vị trí con trỏ phát quá sát đầu hoặc cuối câu (tối thiểu 0.2s).")
                return
        else:
            split_time = round((start + end) / 2.0, 3)

        if not (start + 0.2 <= split_time <= end - 0.2):
            TOASTS.warn("Câu này quá ngắn (dưới 0.4s), không thể tách tiếp.")
            return

        self._undo.push(SplitSegmentCommand(self, seg_id, split_time))
        TOASTS.info(f"Đã tách câu {seg_id} tại {split_time:.2f}s.")

    def merge_current_segment(self) -> None:
        """Gộp câu đang chọn hoặc câu dưới con trỏ phát với câu liền sau (Ctrl+J)."""
        if not self._work_dir or not self._segments:
            return
        selected_id = self.subtitles.selected_id()
        if selected_id <= 0:
            pos = self.player.position()
            for seg in self._segments:
                if float(seg.get("start", 0.0)) <= pos <= float(seg.get("end", 0.0)):
                    selected_id = int(seg.get("id", 0))
                    break
        if selected_id <= 0:
            TOASTS.warn("Vui lòng chọn một câu hoặc đặt con trỏ phát vào câu cần gộp.")
            return
        self._merge_with_next(selected_id)

    def save_now(self) -> None:
        """Lưu ngay, dùng cho phím tắt Ctrl+S."""
        self._save_timer.stop()
        self._flush_edits()

    def delete_selected(self) -> None:
        seg_id = self.subtitles.selected_id()
        if seg_id > 0:
            self._delete_segment(seg_id)

    def focus_search(self) -> None:
        self.subtitles.focus_search()

    def toggle_play(self) -> None:
        self.player.toggle_play()

    def open_export_tab(self) -> None:
        self._show_tab("export")

    # -- Vòng đời ------------------------------------------------------
    def on_breakpoint(self, name: str) -> None:
        """Cửa sổ hẹp thì thu bớt phần bảng bên phải."""
        ratios = {"xl": (62, 38), "lg": (58, 42), "md": (55, 45),
                  "sm": (50, 50)}
        left, right = ratios.get(name, (62, 38))
        self.splitter.setStretchFactor(0, left)
        self.splitter.setStretchFactor(1, right)

    def is_running(self) -> bool:
        return any(w is not None and w.isRunning()
                   for w in (self._resynth_worker, self._rebuild_worker,
                             self._preview_seg_worker,
                             self._export_subs_file_worker,
                             self._export_audio_worker))

    def shutdown(self) -> None:
        for worker in (self._resynth_worker, self._rebuild_worker,
                       self._preview_seg_worker,
                       self._export_subs_file_worker,
                       self._export_audio_worker):
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait(5000)
        # Worker thumbnail chỉ chạy ffmpeg ngắn — hủy rồi chờ nhanh.
        self._stop_thumb_worker()

    def cleanup(self) -> None:
        # app.quit() có thể bỏ qua closeEvent → shutdown() chưa chắc đã chạy.
        # Gọi lại ở đây (idempotent) để không QThread nào bị hủy khi còn chạy
        # (0xC0000409 trên Windows).
        self.shutdown()
        self.save_now()
        self.player.cleanup()
        self._preview.cleanup()
        if self._wave_worker is not None and self._wave_worker.isRunning():
            self._wave_worker.wait(2000)
        for worker in self._wave_workers:
            if worker.isRunning():
                worker.wait(2000)
