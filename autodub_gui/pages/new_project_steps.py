"""Sáu ô cấu hình của trang Tạo dự án.

Mỗi bước là một widget độc lập, tự giữ giá trị của mình và báo ra ngoài khi
có thay đổi. Trang cha chỉ lo chuyển qua lại giữa các bước và gom dữ liệu.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from autodub_gui import dub_constants as consts
from autodub_gui import tokens
from autodub_gui.formatting import format_size
from autodub_gui.ui.buttons import GhostButton, SegmentedControl
from autodub_gui.ui.inputs import (
    LabeledCombo, LabeledLineEdit, LabeledSlider, LabeledWidget,
)
from autodub_gui.ui.labels import ElidedLabel
from autodub_gui.ui.style import clear_background

STEP_NAMES = ("Video", "Nhận dạng", "Dịch thuật", "Giọng & Phụ đề",
              "Chạy dịch", "Xuất video")

VIDEO_FILTER = ("Video (*.mp4 *.mkv *.mov *.avi *.webm);;Tất cả tệp (*.*)")
_LARGE_FILE_BYTES = 4 * 1024 ** 3


class _StepPanel(QWidget):
    """Khung chung cho một bước: tiêu đề, mô tả ngắn rồi tới các ô nhập."""

    changed = Signal()

    def __init__(self, title: str, description: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        # Mỗi bước nằm trong một thẻ — để nền trong suốt thì nó ăn theo nền
        # của thẻ, không tự vẽ ra một khối tối rời rạc bên trong.
        clear_background(self)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(tokens.SP_4)
        heading = QLabel(title)
        heading.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_CARD_TITLE}px; "
            f"font-weight: 700; background: transparent;")
        note = QLabel(description)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(heading)
        self.body.addWidget(note)

    def finish(self) -> None:
        """Đẩy phần còn lại lên trên, gọi sau khi thêm hết các ô nhập."""
        self.body.addStretch()

    def is_complete(self) -> tuple[bool, str]:
        """Bước này đã đủ dữ liệu chưa, kèm lý do nếu chưa."""
        return True, ""


class VideoPreviewLoaderDialog(QDialog):
    """Hộp thoại chờ tải video từ link để xem trước và phát trực tiếp trong StyleDialog."""

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đang chuẩn bị video xem trước")
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.video_path: str | None = None
        self._url = url
        self._worker = None

        from autodub_gui.ui.buttons import GhostButton
        from PySide6.QtWidgets import QProgressBar

        root = QVBoxLayout(self)
        root.setContentsMargins(tokens.SP_4, tokens.SP_4, tokens.SP_4, tokens.SP_4)
        root.setSpacing(tokens.SP_3)

        title_lbl = QLabel("Đang tải video xem trước từ link...")
        title_lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 600; font-size: {tokens.FS_SECTION}px;")
        root.addWidget(title_lbl)

        url_lbl = ElidedLabel(url)
        url_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px;")
        root.addWidget(url_lbl)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 0)
        self.pbar.setFixedHeight(6)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(
            f"QProgressBar {{ background: {tokens.BG_INPUT}; border-radius: 3px; }} "
            f"QProgressBar::chunk {{ background: {tokens.PRIMARY}; border-radius: 3px; }}"
        )
        root.addWidget(self.pbar)

        desc_lbl = QLabel(
            "Video đang được tải về tạm để bạn có thể xem trực tiếp video thật, bấm phát/tua khi căn chỉnh phụ đề và vùng che.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px;")
        root.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(tokens.SP_2)
        btn_row.addStretch()

        self.btn_skip = GhostButton("Mở ngay (nền mẫu)")
        self.btn_skip.clicked.connect(self._skip_waiting)
        btn_row.addWidget(self.btn_skip)

        self.btn_cancel = GhostButton("Hủy")
        self.btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self.btn_cancel)
        root.addLayout(btn_row)

        self._start_download()

    def _start_download(self):
        from autodub.config import cache_dir
        from autodub_gui.workers import PrefetchWorker
        out_dir = os.path.join(cache_dir(), "preview_videos")
        self._worker = PrefetchWorker(self._url, out_dir, self)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_finished(self, path: str):
        self.video_path = path
        self.accept()

    def _on_failed(self, _err: str):
        self.video_path = None
        self.accept()

    def _skip_waiting(self):
        if self._worker:
            self._worker.cancel()
        self.video_path = None
        self.accept()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
        self.reject()

    def closeEvent(self, event):
        if self._worker:
            self._worker.cancel()
        super().closeEvent(event)


class VideoStep(_StepPanel):
    """Bước 1: chọn nguồn video (hỗ trợ nhập 1 hoặc nhiều liên kết để chạy đa luồng)."""

    SOURCES = [("Dán liên kết", "url"), ("Tải tệp lên", "file"),
               ("Tiếp tục dang dở", "resume")]

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Chọn video", "Dán một hoặc nhiều liên kết (chạy đa luồng), "
                                       "chọn tệp từ máy, hoặc chạy tiếp dự án đang dở.", parent)
        from autodub_gui.ui.inputs import LabeledPlainTextEdit

        self.source = SegmentedControl(self.SOURCES)
        self.source.selection_changed.connect(self._on_source)
        self.body.addWidget(LabeledWidget("Nguồn video", self.source))

        self.url = LabeledPlainTextEdit(
            "Liên kết video (hỗ trợ nhập nhiều link)",
            "Dán một hoặc nhiều liên kết (YouTube, Douyin, Bilibili, TikTok...)\n"
            "Ví dụ:\nhttps://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...",
            "Dán một hoặc nhiều liên kết video, mỗi liên kết trên một dòng để xử lý đa luồng song song.",
            min_height=90,
        )
        self.url.changed.connect(self._on_url_changed)
        self.body.addWidget(self.url)

        self.url_badge = QLabel("")
        self.url_badge.setWordWrap(True)
        self.url_badge.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(self.url_badge)

        self.concurrency_slider = LabeledSlider(
            "Số luồng xử lý song song", 1.0, 4.0, 1.0,
            "Số video được tải và lồng tiếng đồng thời cùng lúc", " luồng", decimals=0)
        self.concurrency_slider.set_value(2.0)
        self.concurrency_slider.changed.connect(lambda _v: self.changed.emit())
        self.concurrency_slider.setVisible(False)
        self.body.addWidget(self.concurrency_slider)

        # Khung thiết lập chi tiết từng video (Giọng đọc riêng, danh sách link)
        from autodub_gui.ui.collapsible import CollapsibleSection
        from PySide6.QtCore import QTimer

        self._custom_items: dict[str, dict] = {}
        self._prefetched_paths: dict[str, str] = {}
        self._prefetch_workers: list = []
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._auto_prefetch_urls)

        self.setup_section = CollapsibleSection("Cấu hình chi tiết từng video trước khi chạy", expanded=True)
        self.setup_container = QWidget()
        clear_background(self.setup_container)
        self.setup_layout = QVBoxLayout(self.setup_container)
        self.setup_layout.setContentsMargins(0, tokens.SP_1, 0, tokens.SP_1)
        self.setup_layout.setSpacing(tokens.SP_2)
        self.setup_section.add_widget(self.setup_container)
        self.setup_section.setVisible(False)
        self.body.addWidget(self.setup_section)

        self.file_row, self.file_edit = self._picker(
            "Tệp video trên máy", "Chưa chọn tệp nào", self._pick_file)
        self.body.addWidget(self.file_row)

        self.resume_row, self.resume_edit = self._picker(
            "Thư mục dự án đang dở", "Chọn thư mục kết quả của lần chạy trước",
            self._pick_folder)
        self.body.addWidget(self.resume_row)

        self.info = ElidedLabel("")
        self.info.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(self.info)
        self.finish()
        self._on_source("url")

    def _picker(self, label: str, placeholder: str,
                handler) -> tuple[QWidget, LabeledLineEdit]:
        holder = QWidget()
        clear_background(holder)     # ăn theo nền của thẻ chứa nó
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SP_2)
        edit = LabeledLineEdit(label, placeholder)
        edit.changed.connect(lambda _t: self._on_path_changed())
        row = QHBoxLayout()
        row.addStretch()
        button = GhostButton("Chọn…")
        button.clicked.connect(handler)
        row.addWidget(button)
        layout.addWidget(edit)
        layout.addLayout(row)
        return holder, edit

    def _on_source(self, key: str) -> None:
        self.url.setVisible(key == "url")
        self.url_badge.setVisible(key == "url")
        has_multi = key == "url" and len(self.urls()) > 1
        self.concurrency_slider.setVisible(has_multi)
        self.setup_section.setVisible(has_multi)
        if has_multi:
            self._refresh_setup_table()
        self.file_row.setVisible(key == "file")
        self.resume_row.setVisible(key == "resume")
        self.changed.emit()

    def _auto_prefetch_urls(self) -> None:
        """Tự động tải video ngầm từ các link vừa nhập để người dùng mở xem trước ngay không cần chờ."""
        if self.source.current_key() != "url":
            return
        from autodub.config import cache_dir
        from autodub_gui.workers import PrefetchWorker

        out_dir = os.path.join(cache_dir(), "preview_videos")
        for u in self.urls():
            if u and u.startswith(("http://", "https://")):
                if u not in self._prefetched_paths or not os.path.isfile(self._prefetched_paths[u]):
                    worker = PrefetchWorker(u, out_dir, self)
                    worker.finished_ok.connect(lambda p, url=u: self._on_prefetch_done(url, p))
                    self._prefetch_workers.append(worker)
                    worker.start()

    def _on_prefetch_done(self, url: str, path: str) -> None:
        self._prefetched_paths[url] = path
        self._refresh_setup_table()

    def _on_url_changed(self) -> None:
        urls = self.urls()
        n = len(urls)
        if n == 0:
            self.url_badge.setText("")
            self.concurrency_slider.setVisible(False)
            self.setup_section.setVisible(False)
        elif n == 1:
            self.url_badge.setText("1 liên kết video (đang tự động tải ngầm...)")
            self.concurrency_slider.setVisible(False)
            self.setup_section.setVisible(False)
        else:
            self.url_badge.setText(
                f"Đã nhập {n} liên kết video (Chế độ xử lý đa luồng — đang tự động tải ngầm...)")
            is_url = self.source.current_key() == "url"
            self.concurrency_slider.setVisible(is_url)
            self.setup_section.setVisible(is_url)
            if is_url:
                self._refresh_setup_table()
        # Kích hoạt tải ngầm sau 1s khi người dùng dán/gõ link
        self._prefetch_timer.start(1000)
        self.changed.emit()

    def items(self):
        from autodub.batch import parse_lines
        raw = self.url.text()
        base_items = parse_lines(raw)
        result = []
        for it in base_items:
            custom = self._custom_items.get(it.url or "", {})
            it.subtitle_style = custom.get("subtitle_style")
            it.blur_regions = custom.get("blur_regions")
            it.logo_opts = custom.get("logo_opts")
            it.watermark_opts = custom.get("watermark_opts")
            it.reframe_opts = custom.get("reframe_opts")
            it.sfx_opts = custom.get("sfx_opts")
            result.append(it)
        return result

    def urls(self) -> list[str]:
        return [it.url for it in self.items() if it.url]

    def _open_item_custom_dialog(self, url: str, index: int) -> None:
        """Mở hộp thoại Kiểu chữ, Vùng che Blur, Logo & Watermark riêng cho video này."""
        from autodub_gui.style_dialog import StyleDialog
        from autodub.config import Settings
        from PySide6.QtWidgets import QDialog

        video_path = None
        if url and url.startswith(("http://", "https://")):
            if url in self._prefetched_paths and os.path.isfile(self._prefetched_paths[url]):
                video_path = self._prefetched_paths[url]
            else:
                loader = VideoPreviewLoaderDialog(url, parent=self)
                if loader.exec() != QDialog.DialogCode.Accepted:
                    return
                video_path = loader.video_path
                if video_path:
                    self._prefetched_paths[url] = video_path
        elif url and os.path.isfile(url):
            video_path = url

        settings = Settings.load()
        custom = self._custom_items.get(url, {})
        style = custom.get("subtitle_style") or settings.subtitle_style()
        regions = list(custom.get("blur_regions") or [])
        logo_opts = custom.get("logo_opts") or {
            "logo_path": getattr(settings, "logo_path", ""),
            "logo_position": getattr(settings, "logo_position", "top_right"),
            "logo_scale": getattr(settings, "logo_scale", 0.12),
            "logo_opacity": getattr(settings, "logo_opacity", 0.85),
            "logo_motion": getattr(settings, "logo_motion", "static"),
        }
        wm_opts = custom.get("watermark_opts") or {
            "watermark_text": getattr(settings, "watermark_text", ""),
            "watermark_motion": getattr(settings, "watermark_motion", "bounce"),
            "watermark_opacity": getattr(settings, "watermark_opacity", 0.28),
            "watermark_font_size": getattr(settings, "watermark_font_size", 26),
            "watermark_speed": getattr(settings, "watermark_speed", 40),
        }
        reframe_opts = custom.get("reframe_opts") or {
            "aspect_preset": getattr(settings, "video_aspect_preset", "original"),
            "reframe_mode": "blur",
        }
        sfx_opts = custom.get("sfx_opts") or {
            "auto_sfx_enabled": getattr(settings, "auto_sfx_enabled", False),
            "sfx_preset": getattr(settings, "sfx_preset", "whoosh"),
            "sfx_volume_db": getattr(settings, "sfx_volume_db", -4.0),
        }
        mask_opts = custom.get("mask_opts") or {
            "mask_method": getattr(settings, "mask_method", "blur"),
            "inpaint_engine": getattr(settings, "inpaint_engine", "lama_onnx"),
            "inpaint_device": getattr(settings, "inpaint_device", "auto"),
        }

        dialog = StyleDialog(
            video_path=video_path,
            style=style,
            regions=regions,
            parent=self,
            logo_options=logo_opts,
            watermark_options=wm_opts,
            reframe_options=reframe_opts,
            sfx_options=sfx_opts,
            mask_options=mask_opts,
        )
        if not dialog.exec():
            return

        self._custom_items[url] = {
            "subtitle_style": dialog.style(),
            "blur_regions": dialog.regions(),
            "logo_opts": dialog.logo_options(),
            "watermark_opts": dialog.watermark_options(),
            "reframe_opts": dialog.reframe_options(),
            "sfx_opts": dialog.sfx_options(),
            "mask_opts": dialog.mask_options(),
        }

        self._refresh_setup_table()
        self.changed.emit()

    def _refresh_setup_table(self) -> None:
        if getattr(self, "_block_table_refresh", False):
            return
        items = self.items()
        if len(items) <= 1 or self.source.current_key() != "url":
            self.setup_section.setVisible(False)
            return

        self.setup_section.setVisible(True)
        # Xóa các dòng cũ
        while self.setup_layout.count():
            child = self.setup_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        from autodub_gui import icons
        from autodub_gui.ui.buttons import GhostButton, IconButton
        from PySide6.QtWidgets import QComboBox

        # Lấy danh sách giọng đọc có sẵn
        available_voices = ["(Theo dự án)"]
        try:
            from autodub.config import Settings
            from autodub.speech.tts import voices
            all_v = voices.names(Settings.load())
            if all_v:
                available_voices.extend(all_v)
        except Exception:
            pass

        # Thanh công cụ thao tác hàng loạt
        toolbar = QWidget()
        toolbar.setStyleSheet(
            f"background: {tokens.BG_ELEVATED}; border-radius: {tokens.RADIUS_MD}px; "
            f"padding: {tokens.SP_1}px {tokens.SP_2}px; margin-bottom: {tokens.SP_1}px;"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(tokens.SP_2, tokens.SP_1, tokens.SP_2, tokens.SP_1)
        tb_layout.setSpacing(tokens.SP_2)

        lbl_bulk = QLabel("Đổi giọng hàng loạt:")
        lbl_bulk.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; font-weight: 600;")
        tb_layout.addWidget(lbl_bulk)

        self._bulk_voice_combo = QComboBox()
        self._bulk_voice_combo.addItems(available_voices)
        self._bulk_voice_combo.setStyleSheet(
            f"QComboBox {{ background: {tokens.BG_INPUT}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER_SUBTLE}; border-radius: {tokens.RADIUS_SM}px; "
            f"padding: 2px 8px; font-size: {tokens.FS_META}px; min-width: 120px; }}"
        )
        tb_layout.addWidget(self._bulk_voice_combo)

        btn_apply_all_voice = GhostButton("Áp dụng cho tất cả")
        btn_apply_all_voice.setStyleSheet(
            f"color: {tokens.PRIMARY}; border: 1px solid {tokens.BORDER_SUBTLE}; "
            f"font-size: {tokens.FS_META}px; border-radius: {tokens.RADIUS_SM}px; padding: 2px 8px;"
        )
        btn_apply_all_voice.clicked.connect(self._apply_bulk_voice)
        tb_layout.addWidget(btn_apply_all_voice)
        tb_layout.addStretch()

        self.setup_layout.addWidget(toolbar)

        for idx, item in enumerate(items):
            row = QWidget()
            row.setStyleSheet(
                f"background: {tokens.BG_INPUT}; border-radius: {tokens.RADIUS_MD}px; "
                f"padding: {tokens.SP_1}px {tokens.SP_2}px;"
            )
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(tokens.SP_2, tokens.SP_1, tokens.SP_2, tokens.SP_1)
            r_layout.setSpacing(tokens.SP_2)

            num_lbl = QLabel(f"#{idx + 1}")
            num_lbl.setStyleSheet(f"color: {tokens.PRIMARY}; font-weight: bold; font-size: {tokens.FS_META}px;")
            r_layout.addWidget(num_lbl)

            url_lbl = ElidedLabel(item.url or "")
            url_lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_META}px;")
            r_layout.addWidget(url_lbl, 1)

            # Huy hiệu trạng thái tải ngầm
            if item.url in self._prefetched_paths and os.path.isfile(self._prefetched_paths[item.url]):
                tag = QLabel("Đã tải xong")
                tag.setStyleSheet(
                    f"color: {tokens.SUCCESS}; font-size: {tokens.FS_META}px; "
                    f"background: transparent; font-weight: 500;"
                )
                r_layout.addWidget(tag)

            cb_voice = QComboBox()
            cb_voice.addItems(available_voices)
            curr_v = item.voice or "(Theo dự án)"
            curr_idx = cb_voice.findText(curr_v)
            if curr_idx >= 0:
                cb_voice.setCurrentIndex(curr_idx)
            elif item.voice:
                cb_voice.addItem(item.voice)
                cb_voice.setCurrentIndex(cb_voice.count() - 1)

            cb_voice.setStyleSheet(
                f"QComboBox {{ background: {tokens.BG_ELEVATED}; color: {tokens.TEXT_PRIMARY}; "
                f"border: 1px solid {tokens.BORDER_SUBTLE}; border-radius: {tokens.RADIUS_SM}px; "
                f"padding: 2px 8px; font-size: {tokens.FS_META}px; min-width: 130px; }}"
            )
            cb_voice.currentTextChanged.connect(
                lambda v, i=idx: self._on_item_voice_changed(i, v)
            )
            r_layout.addWidget(cb_voice)

            # Nút chỉnh Blur, Sub, Logo, Watermark riêng cho video này
            has_custom = item.url in self._custom_items and any(
                bool(v) for v in self._custom_items[item.url].values()
            )
            btn_text = "Đã chỉnh riêng" if has_custom else "Hiệu ứng & Sub…"
            btn_fx = GhostButton(btn_text)
            if has_custom:
                btn_fx.setStyleSheet(
                    f"color: {tokens.PRIMARY}; border: 1px solid {tokens.PRIMARY}; "
                    f"font-size: {tokens.FS_META}px; border-radius: {tokens.RADIUS_SM}px; padding: 2px 8px;"
                )
            else:
                btn_fx.setStyleSheet(
                    f"font-size: {tokens.FS_META}px; border-radius: {tokens.RADIUS_SM}px; padding: 2px 8px;"
                )
            btn_fx.clicked.connect(lambda _c=False, u=item.url, i=idx: self._open_item_custom_dialog(u, i))
            r_layout.addWidget(btn_fx)

            if has_custom:
                btn_clone = GhostButton("Nhân bản cho tất cả")
                btn_clone.setStyleSheet(
                    f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; "
                    f"border: 1px dashed {tokens.BORDER_SUBTLE}; border-radius: {tokens.RADIUS_SM}px; padding: 2px 6px;"
                )
                btn_clone.clicked.connect(lambda _c=False, u=item.url: self._apply_custom_to_all(u))
                r_layout.addWidget(btn_clone)

            btn_del = IconButton(icons.trash(tokens.DANGER), "Xóa video này", size=24)
            btn_del.clicked.connect(lambda _c=False, i=idx: self._remove_item(i))
            r_layout.addWidget(btn_del)

            self.setup_layout.addWidget(row)

    def _apply_bulk_voice(self) -> None:
        """Áp dụng một giọng đọc cho tất cả các video trong danh sách."""
        if not hasattr(self, "_bulk_voice_combo"):
            return
        chosen = self._bulk_voice_combo.currentText()
        val = chosen if chosen and chosen != "(Theo dự án)" else None
        items = self.items()
        new_lines = []
        for it in items:
            it.voice = val
            if val:
                new_lines.append(f"{it.url} | {val}")
            else:
                new_lines.append(it.url)
        self._block_table_refresh = True
        self.url.set_text("\n".join(new_lines))
        self._block_table_refresh = False
        self._refresh_setup_table()
        self.changed.emit()

    def _apply_custom_to_all(self, source_url: str) -> None:
        """Sao chép cấu hình riêng (Blur, Sub, Logo, Watermark) của 1 video sang mọi video khác."""
        if source_url not in self._custom_items:
            return
        import copy
        src_data = self._custom_items[source_url]
        for it in self.items():
            if it.url and it.url != source_url:
                self._custom_items[it.url] = copy.deepcopy(src_data)
        self._refresh_setup_table()
        self.changed.emit()

    def _remove_item(self, index: int) -> None:
        items = self.items()
        if 0 <= index < len(items):
            popped = items.pop(index)
            if popped.url and popped.url in self._custom_items:
                self._custom_items.pop(popped.url, None)
            new_lines = []
            for it in items:
                if it.voice:
                    new_lines.append(f"{it.url} | {it.voice}")
                else:
                    new_lines.append(it.url)
            self.url.set_text("\n".join(new_lines))

    def _on_item_voice_changed(self, index: int, voice_name: str) -> None:
        items = self.items()
        if 0 <= index < len(items):
            items[index].voice = voice_name if voice_name and voice_name != "(Theo dự án)" else None
            new_lines = []
            for it in items:
                if it.voice:
                    new_lines.append(f"{it.url} | {it.voice}")
                else:
                    new_lines.append(it.url)
            self._block_table_refresh = True
            self.url.set_text("\n".join(new_lines))
            self._block_table_refresh = False
            self.changed.emit()

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn video", os.path.expanduser("~"), VIDEO_FILTER)
        if path:
            self.file_edit.set_text(path)
            self.source.set_key("file")
            self._on_source("file")

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục dự án đang dở", "output")
        if path:
            self.resume_edit.set_text(path)
            self.source.set_key("resume")
            self._on_source("resume")

    def _on_path_changed(self) -> None:
        path = self.file_edit.text()
        if path and os.path.isfile(path):
            size = os.path.getsize(path)
            warn = ("  —  video rất lớn, xử lý có thể mất nhiều giờ"
                    if size > _LARGE_FILE_BYTES else "")
            self.info.setText(f"{os.path.basename(path)} · "
                              f"{format_size(size)}{warn}")
        else:
            self.info.setText("")
        self.changed.emit()

    def set_file(self, path: str) -> None:
        """Điền sẵn tệp khi người dùng kéo thả từ Trang chủ."""
        self.source.set_key("file")
        self._on_source("file")
        self.file_edit.set_text(path)

    def set_resume(self, work_dir: str) -> None:
        """Chuyển bước 1 sang «Tiếp tục dang dở» trỏ vào một dự án có sẵn."""
        self.source.set_key("resume")
        self._on_source("resume")
        self.resume_edit.set_text(work_dir)

    def values(self) -> dict:
        items = self.items()
        urls = [it.url for it in items if it.url]
        return {
            "source": self.source.current_key(),
            "url": urls[0] if len(urls) == 1 else self.url.text(),
            "urls": urls,
            "items": [{"url": it.url, "voice": it.voice,
                       "has_custom": it.url in self._custom_items} for it in items],
            "custom_items": self._custom_items,
            "concurrency": int(self.concurrency_slider.value()) if len(urls) > 1 else 1,
            "file_path": self.file_edit.text(),
            "resume_dir": self.resume_edit.text(),
        }

    def load(self, data: dict) -> None:
        self.source.set_key(data.get("source", "url"))
        self._custom_items = dict(data.get("custom_items") or {})
        if data.get("source") == "file":
            self.file_edit.set_text(data.get("file_path", ""))
        elif data.get("source") == "resume":
            self.resume_edit.set_text(data.get("resume_dir", ""))
        else:
            self.url.set_text(data.get("url", ""))
        self._on_source(data.get("source", "url"))
        self._on_url_changed()
        if "concurrency" in data:
            self.concurrency_slider.set_value(float(data["concurrency"]))
        self._on_source(self.source.current_key())
        self._on_url_changed()

    def is_complete(self) -> tuple[bool, str]:
        key = self.source.current_key()
        if key == "url" and not self.urls():
            return False, "Hãy dán ít nhất một liên kết video hợp lệ trước khi đi tiếp."
        if key == "file":
            path = self.file_edit.text()
            if not path:
                return False, "Hãy chọn một tệp video trước khi đi tiếp."
            if not os.path.isfile(path):
                return False, "Không tìm thấy tệp này nữa. Hãy chọn lại."
        if key == "resume" and not os.path.isdir(self.resume_edit.text()):
            return False, "Hãy chọn thư mục dự án đang dở có thật trên máy."
        return True, ""


class RecognizeStep(_StepPanel):
    """Bước 2: nghe và chép lời video gốc, kèm cách xử lý nhạc nền."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Nghe và chép lời",
                         "Ứng dụng nghe video gốc rồi chép lại thành chữ. "
                         "Chép càng đúng thì bản dịch càng sát.", parent)
        from autodub_gui.ui.collapsible import CollapsibleSection

        self.engine = LabeledCombo(
            "Bộ nhận dạng", consts.ASR_ENGINES,
            "Whisper nghe được mọi ngôn ngữ. Paraformer chính xác hơn với "
            "video tiếng Trung nhưng phải cài thêm một lần.")
        self.model = LabeledCombo(
            "Độ chính xác", consts.WHISPER_MODELS,
            "Mức càng cao thì nghe càng đúng nhưng chạy càng lâu và tải "
            "về càng nặng.")
        self.language = LabeledCombo(
            "Ngôn ngữ trong video", consts.SOURCE_LANGS,
            "Cho biết video gốc nói tiếng gì.")
        self.auto_detect = QCheckBox("Để ứng dụng tự nhận ra ngôn ngữ")
        self.auto_detect.setToolTip(
            "Bật khi bạn không chắc video nói tiếng gì. Tắt thì dùng đúng "
            "ngôn ngữ bạn chọn ở trên, thường chính xác hơn.")
        self.auto_detect.toggled.connect(self._on_auto)

        self.diarization_enabled = QCheckBox("Tự động phân tách người nói (Speaker Diarization)")
        self.diarization_enabled.setToolTip(
            "Tự động nhận diện và phân biệt các nhân vật khác nhau trong video bằng âm sắc giọng nói.")
        self.diarization_enabled.setChecked(True)
        self.diarization_enabled.toggled.connect(lambda _c: self.changed.emit())

        for widget in (self.engine, self.model, self.language):
            widget.changed.connect(lambda *_a: self.changed.emit())
        self.body.addWidget(self.engine)
        self.body.addWidget(self.model)
        self.body.addWidget(self.language)
        self.body.addWidget(self.auto_detect)
        self.body.addWidget(self.diarization_enabled)

        # Nhạc nền — dọn về đây từ bước Xuất video cũ, vì tách giọng chạy
        # ngay sau bước nghe; gập lại mặc định cho gọn.
        self._bg_section = CollapsibleSection("Nhạc nền")
        self.background = LabeledCombo(
            "Cách giữ nhạc nền", consts.BG_MODES,
            "Tách giọng gốc giữ được nhạc nền hay nhất nhưng chạy lâu hơn.")
        self.background.changed.connect(self._on_background)
        self.duck = LabeledSlider(
            "Mức giảm tiếng gốc", -40.0, 0.0, 1.0,
            "Càng âm thì tiếng gốc càng nhỏ khi có lời thoại tiếng Việt.",
            " dB", decimals=0)
        self.duck.set_value(-12.0)
        self.duck.changed.connect(lambda _v: self.changed.emit())
        self._bg_section.add_widget(self.background)
        self._bg_section.add_widget(self.duck)
        self.body.addWidget(self._bg_section)
        self.finish()
        self._on_background()

    def _on_auto(self, checked: bool) -> None:
        self.language.setEnabled(not checked)
        self.changed.emit()

    def _on_background(self) -> None:
        self.duck.setEnabled(self.background.current_key() == "duck")
        self.changed.emit()

    def values(self) -> dict:
        return {
            "asr_engine": self.engine.current_key(),
            "whisper_model": self.model.current_key(),
            "source_lang": self.language.current_key(),
            "auto_detect": self.auto_detect.isChecked(),
            "diarization_enabled": self.diarization_enabled.isChecked(),
            "bg_mode": self.background.current_key(),
            "bg_duck_db": self.duck.value(),
        }

    def load(self, data: dict) -> None:
        self.engine.set_key(data.get("asr_engine", "whisper"))
        self.model.set_key(data.get("whisper_model", "auto"))
        self.language.set_key(data.get("source_lang", "zh-CN"))
        self.auto_detect.setChecked(bool(data.get("auto_detect", False)))
        self.diarization_enabled.setChecked(bool(data.get("diarization_enabled", True)))
        self.background.set_key(data.get("bg_mode", "demucs"))
        self.duck.set_value(float(data.get("bg_duck_db", -12.0)))
        self._on_background()


class TranslateStep(_StepPanel):
    """Bước 3: dịch sang tiếng Việt."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Dịch sang tiếng Việt",
                         "Chọn cách dịch và giọng văn cho bản dịch. Ngôn ngữ "
                         "đích luôn là tiếng Việt.", parent)
        self.source_view = QLabel("")
        self.source_view.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_BODY}px; "
            f"background: {tokens.BG_INPUT}; border-radius: 8px; "
            f"padding: 8px 12px;")
        self.body.addWidget(LabeledWidget(
            "Dịch từ", self.source_view,
            "Lấy theo ngôn ngữ bạn chọn ở bước Nghe và chép lời."))

        target = QLabel("Tiếng Việt")
        target.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_BODY}px; "
            f"font-weight: 600; background: {tokens.BG_INPUT}; "
            f"border-radius: 8px; padding: 8px 12px;")
        self.body.addWidget(LabeledWidget(
            "Dịch sang", target, "Bản này chỉ lồng tiếng Việt."))

        # Hai lựa chọn quyết định dịch & metadata
        self.auto_translate = QCheckBox("Dịch tự động bằng AI")
        self.auto_translate.setToolTip(
            "Bật: tự động dịch toàn bộ các câu thoại sang tiếng Việt. Tắt: dừng ở bước dịch để bạn dịch tay.")
        self.auto_translate.setChecked(True)
        self.auto_translate.toggled.connect(self._on_auto_translate)
        self.body.addWidget(self.auto_translate)

        self.metadata = QCheckBox("Tạo tiêu đề + mô tả đăng bài (YouTube/TikTok/Facebook)")
        self.metadata.setToolTip(
            "AI viết sẵn tiêu đề, mô tả và hashtag cho mạng xã hội, lưu vào "
            "tệp youtube_post.txt trong thư mục dự án.")
        self.metadata.setChecked(True)
        self.metadata.toggled.connect(lambda _c: self.changed.emit())
        self.body.addWidget(self.metadata)

        # Bộ chọn công nghệ dịch: Gemini SRT Pro, DeepSeek, OpenRouter, OpenAI
        self.engine = LabeledCombo(
            "Công nghệ dịch",
            [
                ("Gemini SRT Translator Pro / Gemini Direct (Google AI - Nhanh & Chuẩn)", "gemini"),
                ("Google AI Studio qua Trình duyệt (Miễn phí, không cần API Key)", "ai_studio"),
                ("DeepSeek API Trực tiếp (deepseek-chat)", "deepseek"),
                ("OpenRouter API (Hàng trăm mô hình AI)", "openrouter"),
                ("OpenAI API (GPT-4o, GPT-4o-mini)", "openai"),
            ],
            "Chọn nơi xử lý dịch thuật: Gemini SRT Pro, AI Studio (trình duyệt, miễn phí), API trực tiếp (DeepSeek/OpenRouter/OpenAI).")
        self.engine.changed.connect(self._on_engine_changed)

        # 1. Các ô nhập cho Gemini SRT Pro
        self.gemini_key = LabeledLineEdit(
            "Google Gemini API Key(s)",
            "AIzaSyKey1, AIzaSyKey2... (dán 1 hoặc nhiều key để chia luồng)",
            "Khóa API Gemini (lấy miễn phí tại aistudio.google.com). Có thể nhập nhiều key để chia luồng.")
        self.gemini_key.changed.connect(lambda _t: self.changed.emit())

        self.gemini_model = LabeledCombo(
            "Mô hình Gemini",
            [
                ("Gemini 2.5 Flash (Mới nhất, nhanh & chuẩn)", "gemini-2.5-flash"),
                ("Gemini 1.5 Flash (Ổn định, tốc độ cao)", "gemini-1.5-flash"),
                ("Gemini 2.5 Pro (Văn phong cao cấp, thông minh)", "gemini-2.5-pro"),
            ],
            "Mô hình AI xử lý dịch thuật và tạo nội dung đăng bài.")
        self.gemini_model.changed.connect(lambda *_a: self.changed.emit())

        self.btn_open_gemini_web = GhostButton("Mở Trình Dịch Web Gemini SRT Pro")
        self.btn_open_gemini_web.clicked.connect(self._open_gemini_web_tool)

        self.btn_login_ai_studio = GhostButton("Đăng nhập Google AI Studio")
        self.btn_login_ai_studio.setToolTip(
            "Mở Chrome để đăng nhập Google lần đầu. Cookies sẽ được lưu cho các lần sau.")
        self.btn_login_ai_studio.clicked.connect(self._open_ai_studio_login)

        self.ai_studio_hint = QLabel(
            "Dùng Google AI Studio miễn phí qua trình duyệt Chrome — không cần API Key. "
            "Chậm hơn API trực tiếp nhưng không tốn phí. Cần đăng nhập Google lần đầu. "
            "Lần chạy này bỏ qua API Key đã lưu (phương thức 1) để đi đường trình duyệt.")
        self.ai_studio_hint.setWordWrap(True)
        self.ai_studio_hint.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.ai_studio_hint.setVisible(False)

        self.ai_studio_login_status = QLabel("")
        self.ai_studio_login_status.setWordWrap(True)
        self.ai_studio_login_status.setStyleSheet(
            f"font-size: {tokens.FS_META}px; background: transparent;")
        self.ai_studio_login_status.setVisible(False)

        # 2. Các ô nhập cho DeepSeek, OpenRouter, OpenAI
        self.deepseek_key = LabeledLineEdit(
            "DeepSeek API Key",
            "sk-...",
            "Khóa API DeepSeek từ platform.deepseek.com.")
        self.deepseek_key.changed.connect(lambda _t: self.changed.emit())

        self.openrouter_key = LabeledLineEdit(
            "OpenRouter API Key",
            "sk-or-v1-...",
            "Khóa API OpenRouter từ openrouter.ai.")
        self.openrouter_key.changed.connect(lambda _t: self.changed.emit())

        self.openai_key = LabeledLineEdit(
            "OpenAI API Key",
            "sk-...",
            "Khóa API OpenAI từ platform.openai.com.")
        self.openai_key.changed.connect(lambda _t: self.changed.emit())

        self.style = LabeledCombo(
            "Phong cách dịch",
            [(label, key) for label, key, _note in consts.TRANSLATE_STYLES],
            "Quyết định giọng văn của bản dịch, ví dụ trang trọng hay đời thường.")
        self.note = LabeledLineEdit(
            "Ghi chú thêm cho người dịch",
            "ví dụ: giữ tên nhân vật Hán Việt, xưng hô mình với các bạn",
            "Ghi chú này được gửi kèm mỗi lần dịch.")
        self.style.changed.connect(lambda *_a: self.changed.emit())
        self.note.changed.connect(lambda _t: self.changed.emit())

        self.body.addWidget(self.engine)
        self.body.addWidget(self.gemini_key)
        self.body.addWidget(self.gemini_model)
        self.body.addWidget(self.btn_open_gemini_web)
        self.body.addWidget(self.btn_login_ai_studio)
        self.body.addWidget(self.ai_studio_hint)
        self.body.addWidget(self.ai_studio_login_status)
        self.body.addWidget(self.deepseek_key)
        self.body.addWidget(self.openrouter_key)
        self.body.addWidget(self.openai_key)
        self.body.addWidget(self.style)
        self.body.addWidget(self.note)

        self.manual_note = QLabel(
            "Đã tắt dịch tự động: chạy tới bước dịch, ứng dụng sẽ dừng lại và "
            "mở hướng dẫn để bạn tự dịch (theo TRANSLATE_PENDING.txt), xong "
            "bấm tiếp tục.")
        self.manual_note.setWordWrap(True)
        self.manual_note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.manual_note.setVisible(False)
        self.body.addWidget(self.manual_note)
        self.finish()

    def _open_gemini_web_tool(self) -> None:
        try:
            from autodub.tools.gemini_srt_ui.server_manager import get_server_manager
            from autodub_gui.system_open import open_url
            mgr = get_server_manager()
            url = mgr.start(open_browser=False)
            if url:
                open_url(url)
        except Exception:
            pass

    def _open_ai_studio_login(self) -> None:
        import threading
        btn = self.btn_login_ai_studio
        btn.setEnabled(False)
        btn.setText("⏳ Đang mở cửa sổ đăng nhập...")

        def worker():
            try:
                from autodub.text.translate_browser import AiStudioBrowserClient
                client = AiStudioBrowserClient(headless=False)
                client.open_login_window()
            except Exception:
                pass

            def _finish():
                btn.setEnabled(True)
                btn.setText("Đăng nhập Google AI Studio")
                self._check_ai_studio_login()
            try:
                from PySide6.QtWidgets import QApplication
                from PySide6.QtCore import QEvent

                class _Ev(QEvent):
                    _TYPE = QEvent.Type(QEvent.registerEventType())
                    def __init__(self, cb):
                        super().__init__(self._TYPE)
                        self.cb = cb

                QApplication.instance().postEvent(self, _Ev(_finish))
            except Exception:
                _finish()

        threading.Thread(target=worker, daemon=True).start()

    def _check_ai_studio_login(self) -> None:
        import threading
        from autodub.text.translate_browser import get_cached_login_status, _has_google_session, _get_default_profile_dir

        cached = get_cached_login_status()
        if cached == "true":
            self.ai_studio_login_status.setStyleSheet(
                f"color: {tokens.SUCCESS}; font-size: {tokens.FS_META}px; background: transparent;")
            self.ai_studio_login_status.setText("Đã đăng nhập Google AI Studio — sẵn sàng dịch!")
            return

        profile_dir = _get_default_profile_dir()
        if not _has_google_session(profile_dir):
            self.ai_studio_login_status.setStyleSheet(
                f"color: {tokens.WARNING}; font-size: {tokens.FS_META}px; background: transparent;")
            self.ai_studio_login_status.setText("Chưa đăng nhập — bấm nút 'Đăng nhập Google AI Studio' ở trên trước khi chạy.")
            return

        self.ai_studio_login_status.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; background: transparent;")
        self.ai_studio_login_status.setText("Đang kiểm tra đăng nhập...")

        def worker():
            from autodub.text.translate_browser import check_login_status
            result = check_login_status()

            def _update():
                if result["logged_in"]:
                    self.ai_studio_login_status.setStyleSheet(
                        f"color: {tokens.SUCCESS}; font-size: {tokens.FS_META}px; background: transparent;")
                    self.ai_studio_login_status.setText("Đã đăng nhập Google AI Studio — sẵn sàng dịch!")
                else:
                    self.ai_studio_login_status.setStyleSheet(
                        f"color: {tokens.WARNING}; font-size: {tokens.FS_META}px; background: transparent;")
                    msg = result.get("error") or "Chưa đăng nhập"
                    self.ai_studio_login_status.setText(f"{msg} — bấm nút 'Đăng nhập' ở trên.")
            try:
                from PySide6.QtWidgets import QApplication
                from PySide6.QtCore import QEvent

                class _Ev(QEvent):
                    _TYPE = QEvent.Type(QEvent.registerEventType())
                    def __init__(self, cb):
                        super().__init__(self._TYPE)
                        self.cb = cb

                QApplication.instance().postEvent(self, _Ev(_update))
            except Exception:
                _update()

        threading.Thread(target=worker, daemon=True).start()

    def customEvent(self, event):
        if hasattr(event, 'cb'):
            event.cb()

    def _on_engine_changed(self) -> None:
        key = self.engine.current_key()
        self.gemini_key.setVisible(key in ("gemini", "gemini_srt"))
        self.gemini_model.setVisible(key in ("gemini", "gemini_srt"))
        self.btn_open_gemini_web.setVisible(key in ("gemini", "gemini_srt"))
        self.btn_login_ai_studio.setVisible(key == "ai_studio")
        self.ai_studio_hint.setVisible(key == "ai_studio")
        self.ai_studio_login_status.setVisible(key == "ai_studio")
        self.deepseek_key.setVisible(key == "deepseek")
        self.openrouter_key.setVisible(key == "openrouter")
        self.openai_key.setVisible(key == "openai")
        self.changed.emit()
        if key == "ai_studio":
            self._check_ai_studio_login()

    def _on_auto_translate(self, checked: bool) -> None:
        for widget in (
            self.engine, self.gemini_key, self.gemini_model, self.btn_open_gemini_web,
            self.btn_login_ai_studio, self.ai_studio_hint, self.ai_studio_login_status,
            self.deepseek_key, self.openrouter_key, self.openai_key, self.style, self.note
        ):
            widget.setEnabled(checked)
        self.manual_note.setVisible(not checked)
        self.changed.emit()

    def set_source_language(self, label: str) -> None:
        self.source_view.setText(label)

    def values(self) -> dict:
        return {
            "auto_translate": self.auto_translate.isChecked(),
            "generate_metadata": self.metadata.isChecked(),
            "translate_engine": self.engine.current_key(),
            "gemini_api_key": self.gemini_key.text().strip(),
            "gemini_model": self.gemini_model.current_key(),
            "deepseek_api_key": self.deepseek_key.text().strip(),
            "openrouter_api_key": self.openrouter_key.text().strip(),
            "openai_api_key": self.openai_key.text().strip(),
            "translate_style": self.style.current_key(),
            "translate_note": self.note.text(),
        }

    def load(self, data: dict) -> None:
        fb_ai_studio = False
        try:
            from autodub.config import Settings
            settings = Settings.load()
            fb_auto = settings.translate_enabled
            fb_meta = settings.generate_metadata
            fb_gemini_key = settings.gemini_api_key
            fb_gemini_model = settings.gemini_model
            fb_deepseek_key = settings.deepseek_api_key
            fb_openrouter_key = settings.openrouter_api_key
            fb_openai_key = settings.openai_api_key
            fb_ai_studio = bool(settings.ai_studio_enabled)
        except Exception:  # noqa: BLE001 — cấu hình hỏng thì dùng mặc định
            fb_auto, fb_meta = True, True
            fb_gemini_key, fb_gemini_model = "", "gemini-2.5-flash"
            fb_deepseek_key, fb_openrouter_key, fb_openai_key = "", "", ""
            fb_ai_studio = False

        self.auto_translate.setChecked(bool(data.get("auto_translate", fb_auto)))
        self.metadata.setChecked(bool(data.get("generate_metadata", fb_meta)))

        self.gemini_key.set_text(data.get("gemini_api_key", fb_gemini_key))
        self.gemini_model.set_key(data.get("gemini_model", fb_gemini_model or "gemini-2.5-flash"))

        self.deepseek_key.set_text(data.get("deepseek_api_key", fb_deepseek_key))
        self.openrouter_key.set_text(data.get("openrouter_api_key", fb_openrouter_key))
        self.openai_key.set_text(data.get("openai_api_key", fb_openai_key))

        engine_key = data.get("translate_engine")
        if not engine_key or engine_key == "custom_ai":
            if fb_gemini_key:
                engine_key = "gemini"
            elif fb_deepseek_key:
                engine_key = "deepseek"
            elif fb_openrouter_key:
                engine_key = "openrouter"
            elif fb_openai_key:
                engine_key = "openai"
            elif fb_ai_studio:
                engine_key = "ai_studio"
            else:
                engine_key = "gemini"
        self.engine.set_key(engine_key)
        self._on_engine_changed()

        self.style.set_key(data.get("translate_style", "natural"))
        self.note.set_text(data.get("translate_note", ""))
        self._on_auto_translate(self.auto_translate.isChecked())


class VoiceStep(_StepPanel):
    """Bước 4: giọng đọc + phụ đề — hai lựa chọn cuối trước khi chạy."""

    preview_requested = Signal(str)     # tên giọng
    style_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Giọng đọc & phụ đề",
                         "Video này sẽ đọc bằng giọng mặc định bạn chọn trong "
                         "Cài đặt. Chọn thêm cách hiện phụ đề — sau khi chạy "
                         "xong vẫn sửa được trong Trình chỉnh sửa.",
                         parent)
        from autodub.media.subtitle import PRESET_CHOICES
        from autodub_gui.ui.collapsible import CollapsibleSection
        from autodub_gui.voice_picker import VoicePicker

        # Giọng mặc định đang dùng + nút nghe thử ngay
        default_row = QHBoxLayout()
        default_row.setSpacing(tokens.SP_2)
        self._default_label = ElidedLabel("")
        self._default_label.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_BODY}px; "
            f"font-weight: 600; background: transparent;")
        self._btn_default_preview = GhostButton("Nghe thử")
        self._btn_default_preview.clicked.connect(
            lambda: self.preview_requested.emit(self._default_voice()))
        default_row.addWidget(self._default_label, 1)
        default_row.addWidget(self._btn_default_preview)
        self.body.addLayout(default_row)

        # Đổi giọng riêng — gập lại mặc định; mở ra nghĩa là muốn ghi đè.
        self._override = CollapsibleSection("Đổi giọng riêng cho video này")
        self._override.toggled.connect(lambda _e: self.changed.emit())
        self.picker = VoicePicker("Giọng đọc")
        self.picker.changed.connect(lambda *_a: self.changed.emit())
        self.picker.preview_requested.connect(self.preview_requested.emit)
        self._override.add_widget(self.picker)
        self.body.addWidget(self._override)

        self.speed = LabeledSlider(
            "Tốc độ đọc", 0.5, 2.0, 0.05,
            "1.00 là tốc độ tự nhiên. Tăng lên khi câu tiếng Việt dài hơn câu "
            "gốc và bị chồng sang câu sau.", "x")
        self.speed.set_value(1.0)
        self.speed.changed.connect(lambda _v: self.changed.emit())
        self.body.addWidget(self.speed)

        # Phụ đề — dọn về đây từ bước Phụ đề cũ (bước 5 giờ là Chạy dịch).
        self.mode = LabeledCombo(
            "Kiểu phụ đề", consts.SUBTITLE_MODES,
            "Phụ đề rời là tệp riêng, người xem tự bật tắt. Ghi thẳng vào "
            "hình thì chữ nằm luôn trên video.")
        self.mode.changed.connect(lambda *_a: self.changed.emit())
        self.body.addWidget(self.mode)

        self.preset = LabeledCombo(
            "Bộ kiểu chữ", PRESET_CHOICES,
            "Chọn một bộ có sẵn là xong. Muốn tự quyết từng thông số thì bấm "
            "Kiểu chữ và vùng che.")
        self.preset.changed.connect(lambda *_a: self.changed.emit())
        self.body.addWidget(self.preset)

        row = QHBoxLayout()
        row.setSpacing(tokens.SP_2)
        self.btn_style = GhostButton("Kiểu chữ và vùng che…")
        self.btn_style.clicked.connect(self.style_requested.emit)
        row.addWidget(self.btn_style)
        row.addStretch()
        self.body.addLayout(row)

        self.summary = QLabel("Kiểu mặc định, chưa che vùng nào")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(self.summary)

        # Logo / Watermark thương hiệu
        self._logo_section = CollapsibleSection("Logo / Watermark thương hiệu")
        self._logo_section.toggled.connect(lambda _e: self.changed.emit())

        logo_file_row = QHBoxLayout()
        logo_file_row.setSpacing(tokens.SP_2)
        self.logo_path_input = LabeledLineEdit(
            "Tệp logo", "Đường dẫn tệp logo (.png trong suốt, .jpg, .webp)...",
            "Chọn hình ảnh logo để chèn lên video xuất ra.")
        self.logo_path_input.changed.connect(lambda *_a: self.changed.emit())
        self.btn_browse_logo = GhostButton("Chọn ảnh…")
        self.btn_browse_logo.clicked.connect(self._browse_logo)
        self.btn_clear_logo = GhostButton("Xóa")
        self.btn_clear_logo.clicked.connect(lambda: (self.logo_path_input.set_text(""), self.changed.emit()))
        logo_file_row.addWidget(self.logo_path_input, 1)
        logo_file_row.addWidget(self.btn_browse_logo)
        logo_file_row.addWidget(self.btn_clear_logo)
        self._logo_section.add_layout(logo_file_row)

        _LOGO_POS_CHOICES = (
            ("Góc trên bên phải (Khuyên dùng)", "top_right"),
            ("Góc trên bên trái", "top_left"),
            ("Góc dưới bên phải", "bottom_right"),
            ("Góc dưới bên trái", "bottom_left"),
            ("Trên cùng ở giữa", "top_center"),
            ("Dưới cùng ở giữa", "bottom_center"),
            ("Chính giữa video", "center"),
        )
        self.logo_position = LabeledCombo("Vị trí hiển thị", _LOGO_POS_CHOICES)
        self.logo_position.changed.connect(lambda *_a: self.changed.emit())
        self._logo_section.add_widget(self.logo_position)

        self.logo_motion = LabeledCombo(
            "Hiệu ứng logo",
            [("Cố định tại vị trí đã chọn", "static"),
             ("Chạy nảy mượt mà quanh video (Bouncing)", "bounce")])
        self.logo_motion.changed.connect(lambda *_a: self.changed.emit())
        self._logo_section.add_widget(self.logo_motion)

        self.logo_scale = LabeledSlider("Kích thước logo", 0.04, 0.40, 0.01,
                                        "Tỷ lệ chiều rộng logo so với chiều rộng khung hình video.", "")
        self.logo_scale.set_value(0.12)
        self.logo_scale.changed.connect(lambda _v: self.changed.emit())
        self._logo_section.add_widget(self.logo_scale)

        self.logo_opacity = LabeledSlider("Độ rõ nét", 0.10, 1.0, 0.05,
                                          "Độ mờ / trong suốt của logo.", "")
        self.logo_opacity.set_value(0.85)
        self.logo_opacity.changed.connect(lambda _v: self.changed.emit())
        self._logo_section.add_widget(self.logo_opacity)

        self.body.addWidget(self._logo_section)

        # Watermark chữ chìm chuyển động
        self._wm_section = CollapsibleSection("Watermark chữ chìm chuyển động (Chống reup)")
        self._wm_section.toggled.connect(lambda _e: self.changed.emit())

        self.wm_text = LabeledLineEdit(
            "Chữ watermark", "@KenhCuaBan, SĐT, hoặc tên bạn...",
            "Dòng chữ chìm di chuyển quanh video để bảo vệ bản quyền.")
        self.wm_text.changed.connect(lambda *_a: self.changed.emit())
        self._wm_section.add_widget(self.wm_text)

        self.wm_motion = LabeledCombo(
            "Kiểu chuyển động",
            [("Chạy nảy mượt mà quanh video (Khuyên dùng)", "bounce"),
             ("Cố định góc trên bên phải", "top_right"),
             ("Cố định góc dưới bên phải", "bottom_right"),
             ("Cố định góc dưới bên trái", "bottom_left"),
             ("Cố định góc trên bên trái", "top_left")])
        self.wm_motion.changed.connect(lambda *_a: self.changed.emit())
        self._wm_section.add_widget(self.wm_motion)

        self.wm_opacity = LabeledSlider("Độ mờ chìm", 0.08, 0.60, 0.02,
                                        "Độ trong suốt của chữ watermark (0.15 - 0.35 là chìm nhẹ tinh tế).", "")
        self.wm_opacity.set_value(0.28)
        self.wm_opacity.changed.connect(lambda _v: self.changed.emit())
        self._wm_section.add_widget(self.wm_opacity)

        self.wm_speed = LabeledSlider("Tốc độ chạy", 10, 150, 5,
                                      "Tốc độ di chuyển quanh khung hình.", " px/s")
        self.wm_speed.set_value(40)
        self.wm_speed.changed.connect(lambda _v: self.changed.emit())
        self._wm_section.add_widget(self.wm_speed)

        self.body.addWidget(self._wm_section)

        # Xử lý Video & Chống quét bản quyền (Anti-Content ID)
        self._anti_id_section = CollapsibleSection("Xử lý Video & Chống bản quyền (Anti-Content ID)")
        self._anti_id_section.toggled.connect(lambda _e: self.changed.emit())

        self.smart_flip = QCheckBox("Lật gương thông minh (Smart Flip — Giữ nguyên phụ đề / logo)")
        self.smart_flip.setToolTip("Lật ngang hình ảnh video để tránh nhận diện bản quyền nhưng không lật chữ tiếng Việt.")
        self.smart_flip.toggled.connect(lambda _c: self.changed.emit())
        self._anti_id_section.add_widget(self.smart_flip)

        self.micro_zoom = QCheckBox("Zoom động 103% & Trượt góc máy (Micro-zoom)")
        self.micro_zoom.setToolTip("Phóng to nhẹ và chuyển động vi mô phá vỡ thuật toán quét khuôn hình.")
        self.micro_zoom.toggled.connect(lambda _c: self.changed.emit())
        self._anti_id_section.add_widget(self.micro_zoom)

        self.color_filter = LabeledCombo(
            "Bộ lọc màu điện ảnh",
            [("none", "Nguyên bản (Không lọc màu)"),
             ("cinematic_warm", "Cinematic Warm (Ấm áp điện ảnh)"),
             ("teal_orange", "Teal & Orange (Phim bom tấn Hollywood)"),
             ("vintage", "Vintage Retro (Hoài niệm cổ điển)"),
             ("moody_dark", "Moody Dark (Tương phản cao)"),
             ("clean_film", "Clean Film (Trong trẻo sắc nét)")])
        self.color_filter.changed.connect(lambda *_a: self.changed.emit())
        self._anti_id_section.add_widget(self.color_filter)

        self.body.addWidget(self._anti_id_section)

        self.audio_only = QCheckBox("Chỉ xuất âm thanh và phụ đề, bỏ ghép video")
        self.audio_only.setToolTip(
            "Bật khi bạn tự dựng video ở phần mềm khác và chỉ cần tiếng Việt "
            "cùng tệp phụ đề.")
        self.audio_only.toggled.connect(lambda _c: self.changed.emit())
        self.body.addWidget(self.audio_only)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(self.status)
        self.finish()
        self._refresh_default_label()

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn hình ảnh Logo / Watermark", "",
            "Hình ảnh (*.png *.jpg *.jpeg *.webp *.svg);;Tất cả tệp (*.*)")
        if path:
            self.logo_path_input.set_text(path)
            self.changed.emit()

    @staticmethod
    def _default_voice() -> str:
        """Tên giọng mặc định trong Cài đặt, đọc lại mỗi lần cần."""
        from autodub.speech.tts.voices import DEFAULT_VOICE

        try:
            from autodub.config import Settings
            return Settings.load(override=True).vieneu_voice or DEFAULT_VOICE
        except Exception:  # noqa: BLE001 — cấu hình hỏng thì dùng giọng gốc
            return DEFAULT_VOICE

    def _refresh_default_label(self) -> None:
        self._default_label.setText(
            f"Giọng mặc định: {self._default_voice()}")
        self._default_label.setToolTip(
            "Đổi giọng mặc định trong Cài đặt, thẻ Giọng đọc.")

    def showEvent(self, event) -> None:  # noqa: N802 — theo quy ước của Qt
        # Người dùng có thể vừa đổi giọng mặc định trong Cài đặt.
        self._refresh_default_label()
        super().showEvent(event)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_summary(self, text: str) -> None:
        self.summary.setText(text)

    def values(self) -> dict:
        # Không mở phần đổi giọng thì trả về rỗng — pipeline sẽ tự dùng
        # giọng mặc định trong Cài đặt.
        logo_path = self.logo_path_input.text().strip() if self._logo_section.is_expanded() else ""
        wm_text = self.wm_text.text().strip() if self._wm_section.is_expanded() else ""
        return {
            "voice": (self.picker.voice()
                      if self._override.is_expanded() else ""),
            "voice_speed": self.speed.value(),
            "subtitle_mode": self.mode.current_key(),
            "subtitle_preset": self.preset.current_key(),
            "logo_path": logo_path,
            "logo_position": self.logo_position.current_key(),
            "logo_scale": self.logo_scale.value(),
            "logo_opacity": self.logo_opacity.value(),
            "logo_motion": self.logo_motion.current_key(),
            "watermark_text": wm_text,
            "watermark_motion": self.wm_motion.current_key(),
            "watermark_opacity": self.wm_opacity.value(),
            "watermark_speed": int(self.wm_speed.value()),
            "smart_flip": self.smart_flip.isChecked() if self._anti_id_section.is_expanded() else False,
            "micro_zoom": self.micro_zoom.isChecked() if self._anti_id_section.is_expanded() else False,
            "color_filter": self.color_filter.current_key() if self._anti_id_section.is_expanded() else "none",
            "skip_video": self.audio_only.isChecked(),
        }

    def load(self, data: dict) -> None:
        voice = (data.get("voice") or "").strip()
        self.picker.reload()
        if voice:
            self.picker.set_voice(voice)
        self._override.set_expanded(bool(voice))
        self.speed.set_value(float(data.get("voice_speed", 1.0)))
        # Nháp không có mục nào thì rơi về giá trị trong Cài đặt, không
        # phải "none"/"clean" cứng — để hai nơi luôn thống nhất.
        try:
            from autodub.config import Settings
            settings = Settings.load()
            fb_mode = settings.subtitle_mode
            fb_preset = settings.subtitle_preset
            fb_logo_path = settings.logo_path
            fb_logo_pos = settings.logo_position
            fb_logo_scale = settings.logo_scale
            fb_logo_opacity = settings.logo_opacity
            fb_logo_motion = settings.logo_motion
            fb_wm_text = settings.watermark_text
            fb_wm_motion = settings.watermark_motion
            fb_wm_opacity = settings.watermark_opacity
            fb_wm_speed = settings.watermark_speed
        except Exception:  # noqa: BLE001 — cấu hình hỏng thì dùng mặc định
            fb_mode, fb_preset = "none", "clean"
            fb_logo_path, fb_logo_pos, fb_logo_scale, fb_logo_opacity, fb_logo_motion = "", "top_right", 0.12, 0.85, "static"
            fb_wm_text, fb_wm_motion, fb_wm_opacity, fb_wm_speed = "", "bounce", 0.28, 40

        self.mode.set_key(data.get("subtitle_mode", fb_mode))
        self.preset.set_key(data.get("subtitle_preset", fb_preset))

        logo_path = data.get("logo_path", fb_logo_path)
        self.logo_path_input.set_text(logo_path)
        self.logo_position.set_key(data.get("logo_position", fb_logo_pos or "top_right"))
        self.logo_scale.set_value(float(data.get("logo_scale", fb_logo_scale or 0.12)))
        self.logo_opacity.set_value(float(data.get("logo_opacity", fb_logo_opacity or 0.85)))
        self.logo_motion.set_key(data.get("logo_motion", fb_logo_motion or "static"))
        self._logo_section.set_expanded(bool(logo_path))

        wm_text = data.get("watermark_text", fb_wm_text)
        self.wm_text.set_text(wm_text)
        self.wm_motion.set_key(data.get("watermark_motion", fb_wm_motion or "bounce"))
        self.wm_opacity.set_value(float(data.get("watermark_opacity", fb_wm_opacity or 0.28)))
        self.wm_speed.set_value(float(data.get("watermark_speed", fb_wm_speed or 40)))
        self._wm_section.set_expanded(bool(wm_text))

        self.audio_only.setChecked(bool(data.get("skip_video", False)))
        self._refresh_default_label()

    def set_logo_options(self, opts: dict) -> None:
        path = opts.get("logo_path", "")
        self.logo_path_input.set_text(path)
        if "logo_position" in opts:
            self.logo_position.set_key(opts["logo_position"])
        if "logo_scale" in opts:
            self.logo_scale.set_value(float(opts["logo_scale"]))
        if "logo_opacity" in opts:
            self.logo_opacity.set_value(float(opts["logo_opacity"]))
        if "logo_motion" in opts:
            self.logo_motion.set_key(opts["logo_motion"])
        self._logo_section.set_expanded(bool(path))
        self.changed.emit()

    def set_watermark_options(self, opts: dict) -> None:
        text = opts.get("watermark_text", "")
        self.wm_text.set_text(text)
        if "watermark_motion" in opts:
            self.wm_motion.set_key(opts["watermark_motion"])
        if "watermark_opacity" in opts:
            self.wm_opacity.set_value(float(opts["watermark_opacity"]))
        if "watermark_speed" in opts:
            self.wm_speed.set_value(float(opts["watermark_speed"]))
        self._wm_section.set_expanded(bool(text))
        self.changed.emit()


class RunStep(_StepPanel):
    """Bước 5: xem lại lựa chọn rồi chạy thật — tiến trình hiện ở cột trái."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Chạy dịch và lồng tiếng",
                         "Xem lại các lựa chọn rồi bấm Bắt đầu lồng tiếng. "
                         "Ứng dụng sẽ nghe, dịch và đọc toàn bộ video — "
                         "tiến trình và nhật ký hiện ở khung bên trái.", parent)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; "
            f"background: {tokens.BG_INPUT}; border-radius: 8px; "
            f"padding: 10px 12px;")
        self.body.addWidget(LabeledWidget("Tóm tắt lựa chọn", self.summary))

        note = QLabel(
            "Giá của video chốt ngay sau bước nghe-chép, theo số câu thoại "
            "(10 Vox/câu, 12 nếu bật dịch tự động, +20 cho gói tiêu đề + mô "
            "tả) và không đổi nữa — ứng dụng báo tổng Vox trước khi trừ ví.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self.body.addWidget(note)
        self.finish()

    def set_summary(self, rows: list[tuple[str, str]]) -> None:
        """Đổ bảng tóm tắt hai cột."""
        lines = [f"<b>{name}:</b> {value}" for name, value in rows]
        self.summary.setText("<br>".join(lines))

    def values(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass


class ExportSummaryStep(_StepPanel):
    """Bước 6: tổng kết lần chạy và chốt Vox khi bấm Xuất video.

    Nút Xuất video là nút chính ở chân trang (do trang cha đổi nhãn khi
    đến bước này) — bước chỉ lo hiển thị số liệu.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Xuất video",
                         "Video đã lồng tiếng xong. Bấm Xuất video để nhận "
                         "video hoàn chỉnh.", parent)
        self.summary = QLabel("Chưa có lần chạy nào chờ xuất.")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_BODY}px; "
            f"background: {tokens.BG_INPUT}; border-radius: 8px; "
            f"padding: 12px 14px;")
        self.body.addWidget(LabeledWidget("Tổng kết lần chạy", self.summary))
        self.finish()

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        mins, secs = divmod(int(seconds or 0), 60)
        return f"{mins} phút {secs:02d} giây" if mins else f"{secs} giây"

    def set_stats(self, sentences: int, duration_s: float,
                  usage: dict | None, hold: dict | None) -> None:
        """Bảng tổng kết: thời lượng và số câu thoại."""
        rows = [
            ("Thời lượng video", self._fmt_duration(duration_s)),
            ("Số câu thoại", f"{sentences:,}"),
        ]
        self.summary.setText(
            "<br>".join(f"<b>{name}:</b> {value}" for name, value in rows))

    def set_error(self, message: str) -> None:
        """Xuất trượt — thông báo kiểm tra mạng rồi thử lại."""
        self.summary.setText(
            f"Chưa xuất được: {message}<br>Kiểm tra mạng rồi bấm Xuất video lần nữa.")


    def values(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass
