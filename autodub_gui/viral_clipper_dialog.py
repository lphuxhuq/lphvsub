"""Hộp thoại AI Viral Shorts & Reels Clipper (9:16).

Hiển thị danh sách các phân đoạn cao trào do AI phân tích, kèm điểm số Viral Score,
tiêu đề giật tít tiếng Việt, nút xem trước và 1-click xuất video ngắn 9:16.
"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from autodub.config import Settings
from autodub.editor import EditorState, export_project_short_clip, get_or_analyze_viral_clips
from autodub_gui import icons, tokens
from autodub_gui.system_open import open_file, open_folder
from autodub_gui.ui.buttons import GhostButton, PrimaryButton
from autodub_gui.ui.toast import TOASTS


class ExportClipWorker(QThread):
    """Worker chạy ngầm xuất clip ngắn 9:16 không block GUI."""
    progress = Signal(int, str)
    finished_clip = Signal(int, str)
    error = Signal(int, str)

    def __init__(self, state: EditorState, clip_id: int, settings: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.clip_id = clip_id
        self.settings = settings

    def run(self) -> None:
        try:
            self.progress.emit(10, f"Đang dựng clip #{self.clip_id}...")
            out_path = export_project_short_clip(
                self.state,
                self.clip_id,
                settings=self.settings,
                aspect_preset="tiktok_9_16",
                reframe_mode="blur",
            )
            self.finished_clip.emit(self.clip_id, out_path)
        except Exception as e:
            self.error.emit(self.clip_id, str(e))


class ClipCard(QFrame):
    """Thẻ hiển thị 1 phân đoạn Viral Short."""
    export_requested = Signal(int)
    preview_requested = Signal(float, float)

    def __init__(self, clip_data: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.clip_data = clip_data
        self.clip_id = int(clip_data.get("id", 1))
        self.out_path: str | None = None

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"ClipCard {{ background: {tokens.BG_PANEL}; border: 1px solid {tokens.BORDER_SUBTLE}; "
            f"border-radius: {tokens.RADIUS_MD}px; padding: {tokens.SP_3}px; }}"
            f"ClipCard:hover {{ border-color: {tokens.PRIMARY}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.SP_2)
        layout.setContentsMargins(tokens.SP_3, tokens.SP_3, tokens.SP_3, tokens.SP_3)

        # 1. Top row: Badge điểm Viral + Thời lượng
        top_row = QHBoxLayout()
        score = int(clip_data.get("viral_score", 85))
        badge_color = tokens.DANGER if score >= 90 else tokens.WARNING if score >= 80 else tokens.PRIMARY

        badge = QLabel(f"Viral Score: {score}/100")
        badge.setStyleSheet(
            f"background: {badge_color}; color: {tokens.TEXT_ON_ACCENT}; font-weight: 700; "
            f"font-size: {tokens.FS_META}px; border-radius: {tokens.RADIUS_SM}px; "
            f"padding: 2px 8px;"
        )
        top_row.addWidget(badge)

        s_time = float(clip_data.get("start", 0.0))
        e_time = float(clip_data.get("end", 0.0))
        dur = float(clip_data.get("duration", e_time - s_time))
        
        m_s, sec_s = int(s_time // 60), int(s_time % 60)
        m_e, sec_e = int(e_time // 60), int(e_time % 60)
        time_lbl = QLabel(f"{m_s:02d}:{sec_s:02d} -> {m_e:02d}:{sec_e:02d} ({dur:.1f}s)")
        time_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px;")
        top_row.addWidget(time_lbl)
        top_row.addStretch()

        layout.addLayout(top_row)

        # 2. Tiêu đề Hook
        title_lbl = QLabel(str(clip_data.get("title", f"Short Clip #{self.clip_id}")))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_CARD_TITLE}px; font-weight: 600;"
        )
        layout.addWidget(title_lbl)

        # 3. Lý do / Hook text
        reason = clip_data.get("reason", "")
        if reason:
            reason_lbl = QLabel(str(reason))
            reason_lbl.setWordWrap(True)
            reason_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px;")
            layout.addWidget(reason_lbl)

        # 4. Action bar
        act_row = QHBoxLayout()
        act_row.setSpacing(tokens.SP_2)

        self.btn_preview = GhostButton("Xem đoạn này")
        self.btn_preview.clicked.connect(lambda: self.preview_requested.emit(s_time, e_time))
        act_row.addWidget(self.btn_preview)

        self.btn_export = PrimaryButton("Xuất Shorts 9:16")
        self.btn_export.clicked.connect(lambda: self.export_requested.emit(self.clip_id))
        act_row.addWidget(self.btn_export)

        self.btn_open = GhostButton("Mở file")
        self.btn_open.setVisible(False)
        self.btn_open.clicked.connect(self._open_exported_file)
        act_row.addWidget(self.btn_open)

        act_row.addStretch()
        layout.addLayout(act_row)

        # Progress bar cho từng card
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"max-height: 4px; border-radius: 2px;")
        layout.addWidget(self.progress_bar)

    def set_exporting(self, is_exporting: bool) -> None:
        self.progress_bar.setVisible(is_exporting)
        self.btn_export.setEnabled(not is_exporting)

    def mark_completed(self, path: str) -> None:
        self.out_path = path
        self.set_exporting(False)
        self.btn_export.setText("Đã xuất")
        self.btn_open.setVisible(True)

    def _open_exported_file(self) -> None:
        if self.out_path and os.path.exists(self.out_path):
            open_file(self.out_path)


class ViralClipperDialog(QDialog):
    """Hộp thoại quản trị và xuất các đoạn Shorts Viral."""

    def __init__(self, parent: QWidget | None, state: EditorState, settings: Any = None):
        super().__init__(parent)
        self.state = state
        self.settings = settings or Settings.load()
        self._workers: dict[int, ExportClipWorker] = {}
        self._cards: dict[int, ClipCard] = {}

        self.setWindowTitle("AI Viral Shorts & Reels Clipper (9:16)")
        self.setMinimumSize(720, 560)
        self.resize(780, 620)
        self.setStyleSheet(f"background: {tokens.BG_MAIN}; color: {tokens.TEXT_PRIMARY};")

        self._build_ui()
        self._load_clips()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(tokens.SP_4, tokens.SP_4, tokens.SP_4, tokens.SP_4)
        root.setSpacing(tokens.SP_3)

        # Header
        header = QHBoxLayout()
        h_text = QVBoxLayout()
        title = QLabel("AI Viral Shorts Studio")
        title.setStyleSheet(f"font-size: {tokens.FS_PAGE_TITLE}px; font-weight: 700; color: {tokens.TEXT_PRIMARY};")
        desc = QLabel("Tự động phân tích điểm cao trào kịch tính, căn mốc câu thoại và tạo Shorts 9:16 hoàn chỉnh.")
        desc.setStyleSheet(f"font-size: {tokens.FS_META}px; color: {tokens.TEXT_MUTED};")
        h_text.addWidget(title)
        h_text.addWidget(desc)
        header.addLayout(h_text)
        header.addStretch()

        self.btn_reanalyze = GhostButton("Phân tích lại bằng AI")
        self.btn_reanalyze.clicked.connect(self._reanalyze_clips)
        header.addWidget(self.btn_reanalyze)

        root.addLayout(header)

        # Scroll Area chứa danh sách cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(tokens.SP_3)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.addStretch()

        scroll.setWidget(self.cards_container)
        root.addWidget(scroll, 1)

        # Bottom Bar
        bottom = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_META}px;")
        bottom.addWidget(self.status_lbl)
        bottom.addStretch()

        self.btn_export_all = PrimaryButton("Xuất tất cả Shorts (9:16)")
        self.btn_export_all.clicked.connect(self._export_all)
        bottom.addWidget(self.btn_export_all)

        self.btn_open_folder = GhostButton("Mở thư mục Shorts")
        self.btn_open_folder.clicked.connect(self._open_shorts_folder)
        bottom.addWidget(self.btn_open_folder)

        btn_close = GhostButton("Đóng")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)

        root.addLayout(bottom)

    def _load_clips(self, force_refresh: bool = False) -> None:
        # Clear existing cards
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        self.status_lbl.setText("Đang phân tích kịch bản...")
        clips = get_or_analyze_viral_clips(self.state, settings=self.settings, force_refresh=force_refresh)
        self.status_lbl.setText(f"Tìm thấy {len(clips)} phân đoạn Shorts tiềm năng")

        for clip in clips:
            card = ClipCard(clip, self)
            card.export_requested.connect(self._on_export_clip)
            cid = int(clip.get("id", 1))
            self._cards[cid] = card
            # Insert before the stretch at the bottom
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _reanalyze_clips(self) -> None:
        self._load_clips(force_refresh=True)
        TOASTS.info("Đã phân tích lại toàn bộ các đoạn Viral Shorts!")

    def _on_export_clip(self, clip_id: int) -> None:
        card = self._cards.get(clip_id)
        if not card:
            return

        card.set_exporting(True)
        worker = ExportClipWorker(self.state, clip_id, self.settings, self)
        worker.finished_clip.connect(self._on_clip_success)
        worker.error.connect(self._on_clip_error)
        self._workers[clip_id] = worker
        worker.start()

    def _on_clip_success(self, clip_id: int, out_path: str) -> None:
        card = self._cards.get(clip_id)
        if card:
            card.mark_completed(out_path)
        TOASTS.success(f"Đã xuất xong Short Clip #{clip_id}!")

    def _on_clip_error(self, clip_id: int, error_msg: str) -> None:
        card = self._cards.get(clip_id)
        if card:
            card.set_exporting(False)
        TOASTS.error(f"Lỗi xuất Clip #{clip_id}: {error_msg}")

    def _export_all(self) -> None:
        for cid in self._cards:
            self._on_export_clip(cid)

    def _open_shorts_folder(self) -> None:
        folder = os.path.join(self.state.work_dir, "shorts")
        os.makedirs(folder, exist_ok=True)
        open_folder(folder)
