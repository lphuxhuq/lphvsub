"""Component Thẻ Đăng bài & Metadata Video (SocialMetadataCard).

Hiển thị trực quan:
- Trạng thái xuất video thành công & thông tin tệp.
- Ảnh bìa Thumbnail thu nhỏ (kèm nút mở Thumbnail Studio).
- Tiêu đề video kèm nút «Chép Tiêu đề».
- Caption / Mô tả tóm tắt kèm nút «Chép Caption».
- Danh sách Hashtags dạng Pill Badges kèm nút «Chép Hashtags».
- Hàng nút hành động: «Chép Toàn bộ», «Mở video», «Mở thư mục», «Chỉnh sửa dự án».
"""
from __future__ import annotations

import os
from typing import Sequence
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from autodub_gui import tokens
from autodub_gui.system_open import open_file, open_folder, reveal_file
from autodub_gui.ui.buttons import GhostButton, PrimaryButton
from autodub_gui.ui.flow_layout import FlowLayout
from autodub_gui.ui.style import clear_background
from autodub_gui.ui.toast import TOASTS


class SocialMetadataCard(QFrame):
    """Thẻ hiển thị thông tin xuất bản và các nút sao chép 1-chạm."""

    open_video_requested = Signal()
    open_folder_requested = Signal()
    edit_requested = Signal()
    open_studio_requested = Signal()
    open_thumb_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._meta: dict = {}
        self._video_path: str = ""
        self._work_dir: str = ""
        self._thumb_path: str = ""

        self.setObjectName("socialMetadataCard")
        self.setStyleSheet(
            f"QFrame#socialMetadataCard {{"
            f"  background: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER_SUBTLE};"
            f"  border-left: 3px solid {tokens.SUCCESS};"
            f"  border-radius: 8px;"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(tokens.SP_3)

        # ── 1. Header: Trạng thái & Tên file ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.lbl_status = QLabel("🎉 Đã xuất video hoàn tất & tạo nội dung đăng bài")
        self.lbl_status.setStyleSheet(
            f"color: {tokens.SUCCESS}; font-size: {tokens.FS_BODY}px; font-weight: 600;"
        )
        header_row.addWidget(self.lbl_status)
        header_row.addStretch()

        self.lbl_video_filename = QLabel("")
        self.lbl_video_filename.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; "
            f"background: {tokens.BG_INPUT}; padding: 3px 8px; border-radius: 4px;"
        )
        header_row.addWidget(self.lbl_video_filename)
        root.addLayout(header_row)

        # ── 2. Khung Nội dung Chính (Chia làm 2 cột: Trái Thumbnail, Phải Metadata) ──
        content_row = QHBoxLayout()
        content_row.setSpacing(tokens.SP_3)

        # Cột Thumbnail Preview (ẩn nếu chưa có)
        self.thumb_box = QWidget()
        clear_background(self.thumb_box)
        thumb_layout = QVBoxLayout(self.thumb_box)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(6)

        self.lbl_thumb_preview = QLabel()
        self.lbl_thumb_preview.setFixedSize(160, 90)
        self.lbl_thumb_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb_preview.setStyleSheet(
            f"background: {tokens.BG_INPUT}; border: 1px solid {tokens.BORDER_SUBTLE}; "
            f"border-radius: 6px;"
        )
        self.lbl_thumb_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_thumb_preview.mousePressEvent = lambda _e: self.open_thumb_requested.emit()
        thumb_layout.addWidget(self.lbl_thumb_preview)

        self.btn_studio = GhostButton("🎨 Sửa ảnh bìa")
        self.btn_studio.setToolTip("Mở Studio thiết kế ảnh bìa 3D High-CTR")
        self.btn_studio.clicked.connect(self.open_studio_requested.emit)
        thumb_layout.addWidget(self.btn_studio)
        thumb_layout.addStretch()

        self.thumb_box.setVisible(False)
        content_row.addWidget(self.thumb_box)

        # Cột Metadata (Tiêu đề, Caption, Hashtags)
        meta_box = QWidget()
        clear_background(meta_box)
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(tokens.SP_2)

        # 2.1 Tiêu đề
        title_header = QHBoxLayout()
        lbl_title_tag = QLabel("📌 Tiêu đề video")
        lbl_title_tag.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_LABEL}px; font-weight: 600;"
        )
        self.btn_copy_title = GhostButton("Chép Tiêu đề")
        self.btn_copy_title.setToolTip("Sao chép Tiêu đề vào Clipboard")
        self.btn_copy_title.clicked.connect(self._copy_title)
        title_header.addWidget(lbl_title_tag)
        title_header.addStretch()
        title_header.addWidget(self.btn_copy_title)
        meta_layout.addLayout(title_header)

        self.lbl_title = QLabel("")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_title.setMinimumHeight(44)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lbl_title.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_BODY}px; "
            f"font-weight: 600; background: {tokens.BG_INPUT}; padding: 6px 10px; "
            f"border-radius: 6px; border: 1px solid {tokens.BORDER_SUBTLE};"
        )
        meta_layout.addWidget(self.lbl_title)

        # 2.2 Caption / Mô tả
        caption_header = QHBoxLayout()
        lbl_caption_tag = QLabel("💬 Caption / Mô tả")
        lbl_caption_tag.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_LABEL}px; font-weight: 600;"
        )
        self.btn_copy_caption = GhostButton("Chép Caption")
        self.btn_copy_caption.setToolTip("Sao chép Caption / Mô tả vào Clipboard")
        self.btn_copy_caption.clicked.connect(self._copy_caption)
        caption_header.addWidget(lbl_caption_tag)
        caption_header.addStretch()
        caption_header.addWidget(self.btn_copy_caption)
        meta_layout.addLayout(caption_header)

        self.lbl_caption = QLabel("")
        self.lbl_caption.setWordWrap(True)
        self.lbl_caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_caption.setMinimumHeight(38)
        self.lbl_caption.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lbl_caption.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FS_META}px; "
            f"background: {tokens.BG_INPUT}; padding: 6px 10px; border-radius: 6px; "
            f"border: 1px solid {tokens.BORDER_SUBTLE};"
        )
        meta_layout.addWidget(self.lbl_caption)

        # 2.3 Hashtags
        tags_header = QHBoxLayout()
        lbl_tags_tag = QLabel("🏷️ Hashtags")
        lbl_tags_tag.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FS_LABEL}px; font-weight: 600;"
        )
        self.btn_copy_tags = GhostButton("Chép Hashtags")
        self.btn_copy_tags.setToolTip("Sao chép danh sách hashtags (#shorts #reviewphim...) vào Clipboard")
        self.btn_copy_tags.clicked.connect(self._copy_tags)
        tags_header.addWidget(lbl_tags_tag)
        tags_header.addStretch()
        tags_header.addWidget(self.btn_copy_tags)
        meta_layout.addLayout(tags_header)

        self.tags_container = QWidget()
        clear_background(self.tags_container)
        self.tags_layout = FlowLayout(self.tags_container, margin=0, h_spacing=6, v_spacing=6)
        meta_layout.addWidget(self.tags_container)

        content_row.addWidget(meta_box, 1)
        root.addLayout(content_row)

        # ── 3. Hàng nút Hành Động Chính ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {tokens.BORDER_SUBTLE}; margin-top: 4px; margin-bottom: 4px;")
        root.addWidget(sep)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(tokens.SP_2)

        self.btn_copy_all = PrimaryButton("📄 Chép Toàn bộ")
        self.btn_copy_all.setToolTip("Sao chép Tiêu đề, Caption và Hashtags vào Clipboard để đăng bài ngay")
        self.btn_copy_all.clicked.connect(self._copy_all)
        actions_row.addWidget(self.btn_copy_all)

        self.btn_open_video = GhostButton("🎬 Mở video")
        self.btn_open_video.setToolTip("Mở xem video kết quả bằng trình phát mặc định")
        self.btn_open_video.clicked.connect(self._on_open_video)
        actions_row.addWidget(self.btn_open_video)

        self.btn_open_folder = GhostButton("📁 Mở thư mục")
        self.btn_open_folder.setToolTip("Mở thư mục chứa video và chọn sẵn tệp video trong File Explorer")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        actions_row.addWidget(self.btn_open_folder)

        self.btn_edit = GhostButton("✏️ Chỉnh sửa dự án")
        self.btn_edit.setToolTip("Chuyển sang Trình chỉnh sửa Studio để tinh chỉnh phụ đề / âm thanh")
        self.btn_edit.clicked.connect(self.edit_requested.emit)
        actions_row.addWidget(self.btn_edit)

        actions_row.addStretch()
        root.addLayout(actions_row)

        self.setVisible(False)

    def set_metadata(
        self,
        meta: dict | None,
        video_name: str = "",
        video_path: str = "",
        work_dir: str = "",
        thumb_path: str = "",
        segments_count: int = 0,
    ) -> None:
        """Cập nhật dữ liệu bài đăng và hiển thị thẻ."""
        self._meta = dict(meta or {})
        self._video_path = video_path or ""
        self._work_dir = work_dir or ""
        self._thumb_path = thumb_path or ""

        # Tên tệp
        name = video_name or (os.path.basename(video_path) if video_path else "")
        if name:
            detail = f"🎬 {name}"
            if segments_count > 0:
                detail += f" ({segments_count} câu)"
            self.lbl_video_filename.setText(detail)
            self.lbl_video_filename.setVisible(True)
        else:
            self.lbl_video_filename.setVisible(False)

        # Tiêu đề
        title = self._meta.get("title") or (os.path.splitext(name)[0] if name else "Video hoàn tất")
        self.lbl_title.setText(title)
        if len(title) > 90:
            self.lbl_title.setMinimumHeight(64)
        elif len(title) > 40:
            self.lbl_title.setMinimumHeight(46)
        else:
            self.lbl_title.setMinimumHeight(36)

        # Caption
        caption = (
            self._meta.get("caption")
            or self._meta.get("description")
            or f"{title}\n\nVideo lồng tiếng tiếng Việt tự động chất lượng cao."
        )
        self.lbl_caption.setText(caption)
        if len(caption) > 100:
            self.lbl_caption.setMinimumHeight(56)
        elif len(caption) > 40:
            self.lbl_caption.setMinimumHeight(40)
        else:
            self.lbl_caption.setMinimumHeight(32)

        # Hashtags
        tags = self._meta.get("hashtags") or ["#shorts", "#reviewphim", "#trending", "#viral"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split() if t.strip()]

        # Xóa các tag cũ
        while self.tags_layout.count() > 0:
            item = self.tags_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()

        # Thêm các tag mới dạng Pill Badge
        for t in tags:
            tag_str = t if t.startswith("#") else f"#{t}"
            tag_btn = QPushButton(tag_str)
            tag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            tag_btn.setToolTip(f"Bấm để sao chép {tag_str}")
            tag_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            tag_btn.setStyleSheet(
                f"QPushButton {{"
                f"  color: {tokens.PRIMARY_HOVER}; background: {tokens.BG_INPUT};"
                f"  border: 1px solid {tokens.BORDER_SUBTLE}; border-radius: 12px;"
                f"  padding: 4px 10px; font-size: {tokens.FS_META}px; font-weight: 500;"
                f"  white-space: nowrap;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background: {tokens.BG_PANEL_HOVER}; border-color: {tokens.PRIMARY};"
                f"}}"
            )
            tag_btn.clicked.connect(lambda _c=False, s=tag_str, b=tag_btn: self._copy_single_tag(s, b))
            self.tags_layout.addWidget(tag_btn)

        # Thumbnail
        if not self._thumb_path and self._work_dir:
            cand = os.path.join(self._work_dir, "youtube", "thumbnail_landscape.jpg")
            if os.path.exists(cand):
                self._thumb_path = cand

        if self._thumb_path and os.path.exists(self._thumb_path):
            pix = QPixmap(self._thumb_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    160, 90,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_thumb_preview.setPixmap(scaled)
                self.thumb_box.setVisible(True)
            else:
                self.thumb_box.setVisible(False)
        else:
            self.thumb_box.setVisible(False)

        self.setVisible(True)

    def title_text(self) -> str:
        return self.lbl_title.text()

    def caption_text(self) -> str:
        return self.lbl_caption.text()

    def hashtags_text(self) -> str:
        tags = self._meta.get("hashtags") or []
        if isinstance(tags, list):
            return " ".join([t if t.startswith("#") else f"#{t}" for t in tags])
        return str(tags)

    def _copy_single_tag(self, tag: str, button: QPushButton) -> None:
        self._copy_text(tag, button, f"Đã chép {tag} vào Clipboard!")

    def _copy_title(self) -> None:
        txt = self.title_text()
        self._copy_text(txt, self.btn_copy_title, "Đã chép Tiêu đề vào Clipboard!")

    def _copy_caption(self) -> None:
        txt = self.caption_text()
        self._copy_text(txt, self.btn_copy_caption, "Đã chép Caption vào Clipboard!")

    def _copy_tags(self) -> None:
        txt = self.hashtags_text()
        self._copy_text(txt, self.btn_copy_tags, "Đã chép Hashtags vào Clipboard!")

    def _copy_all(self) -> None:
        title = self.title_text()
        caption = self.caption_text()
        tags = self.hashtags_text()
        full = f"Tiêu đề: {title}\n\n{caption}\n\n{tags}".strip()
        self._copy_text(full, self.btn_copy_all, "Đã chép Toàn bộ vào Clipboard!")

    def _set_clipboard_text(self, text: str) -> None:
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def _copy_text(self, text: str, button: QPushButton, toast_msg: str) -> None:
        if not text:
            TOASTS.info("Chưa có nội dung để sao chép.")
            return
        self._set_clipboard_text(text)
        TOASTS.success(toast_msg)

        # Phản hồi thị giác tức thì
        orig_text = button.text()
        button.setText("✓ Đã chép!")
        button.setEnabled(False)

        def _restore():
            button.setText(orig_text)
            button.setEnabled(True)

        QTimer.singleShot(1500, _restore)

    def _on_open_video(self) -> None:
        if self._video_path and os.path.exists(self._video_path):
            ok, msg = open_file(self._video_path)
            if not ok:
                TOASTS.warn(msg)
        else:
            self.open_video_requested.emit()

    def _on_open_folder(self) -> None:
        if self._video_path and os.path.exists(self._video_path):
            ok, msg = reveal_file(self._video_path)
            if not ok:
                TOASTS.warn(msg)
        elif self._work_dir and os.path.exists(self._work_dir):
            ok, msg = open_folder(self._work_dir)
            if not ok:
                TOASTS.warn(msg)
        else:
            self.open_folder_requested.emit()
