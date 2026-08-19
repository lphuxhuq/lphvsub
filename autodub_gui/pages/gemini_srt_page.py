"""Trang Công cụ Dịch phụ đề Gemini SRT Translator Pro.

Giao diện quản lý và khởi chạy công cụ dịch SRT đa luồng với Google Gemini AI,
tự động đồng bộ khóa API từ VoxDub Studio và mở trình duyệt web tương tác.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from autodub_gui import tokens
from autodub_gui.pages import BasePage
from autodub_gui.system_open import open_folder, open_url
from autodub.tools.gemini_srt_ui.server_manager import GeminiSrtServerManager
from autodub_gui.ui.badges import StatusBadge
from autodub_gui.ui.buttons import GhostButton, PrimaryButton
from autodub_gui.ui.cards import Card
from autodub_gui.ui.style import clear_background, panel_background
from autodub_gui.ui.toast import TOASTS

_PAGE_MARGIN = tokens.SP_6


class GeminiSrtPage(BasePage):
    """Trang công cụ điều khiển Gemini SRT Translator Pro."""

    def __init__(self, settings_getter: Callable, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._settings_getter = settings_getter
        self.server_manager = GeminiSrtServerManager()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        clear_background(scroll)

        content = QWidget()
        panel_background(content, tokens.BG_APP)
        self.layout = QVBoxLayout(content)
        self.layout.setContentsMargins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN)
        self.layout.setSpacing(tokens.SP_4)

        self._build_ui()
        self.layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_ui(self) -> None:
        # 1. Hero Card
        hero = Card()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setSpacing(tokens.SP_2)

        title = QLabel("Gemini SRT Translator Pro")
        title.setStyleSheet(f"font-size: {tokens.FS_PAGE_TITLE}px; font-weight: 700; color: {tokens.TEXT_PRIMARY};")
        desc = QLabel(
            "Hệ thống dịch phụ đề và video/audio chuyên sâu sử dụng Google Gemini AI "
            "với Multi-Key Pooling, Hậu xử lý chống sót chữ (Auto CJK) và Trình chỉnh sửa phụ đề trực tiếp."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: {tokens.FS_BODY}px; color: {tokens.TEXT_SECONDARY};")

        hero_layout.addWidget(title)
        hero_layout.addWidget(desc)
        self.layout.addWidget(hero)

        # 2. Server Control Card
        self.server_card = Card()
        srv_layout = QVBoxLayout(self.server_card)
        srv_layout.setSpacing(tokens.SP_3)

        srv_header = QHBoxLayout()
        srv_title = QLabel("Trạng thái Máy chủ Dịch thuật")
        srv_title.setStyleSheet(f"font-size: {tokens.FS_SECTION}px; font-weight: 600; color: {tokens.TEXT_PRIMARY};")

        self.status_badge = StatusBadge("Đang kiểm tra...", "neutral")
        srv_header.addWidget(srv_title)
        srv_header.addStretch(1)
        srv_header.addWidget(self.status_badge)
        srv_layout.addLayout(srv_header)

        self.url_label = QLabel("Địa chỉ: Đang khởi động...")
        self.url_label.setStyleSheet(f"font-size: {tokens.FS_BODY}px; color: {tokens.TEXT_SECONDARY}; font-family: {tokens.FONT_MONO};")
        srv_layout.addWidget(self.url_label)

        self.keys_info_label = QLabel("")
        self.keys_info_label.setStyleSheet(f"font-size: {tokens.FS_LABEL}px; color: {tokens.TEXT_MUTED};")
        srv_layout.addWidget(self.keys_info_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(tokens.SP_3)

        self.btn_open_browser = PrimaryButton("Mở Giao diện Dịch Web")
        self.btn_open_browser.clicked.connect(self._open_web_ui)

        self.btn_restart = GhostButton("Khởi động lại Server")
        self.btn_restart.clicked.connect(self._restart_server)

        self.btn_open_output = GhostButton("Mở thư mục kết quả")
        self.btn_open_output.clicked.connect(self._open_output_folder)

        btn_layout.addWidget(self.btn_open_browser)
        btn_layout.addWidget(self.btn_restart)
        btn_layout.addWidget(self.btn_open_output)
        btn_layout.addStretch(1)

        srv_layout.addLayout(btn_layout)
        self.layout.addWidget(self.server_card)

        # 3. Features Highlight Card
        feat_card = Card()
        feat_layout = QVBoxLayout(feat_card)
        feat_layout.setSpacing(tokens.SP_3)

        feat_title = QLabel("Tính năng nổi bật")
        feat_title.setStyleSheet(f"font-size: {tokens.FS_SECTION}px; font-weight: 600; color: {tokens.TEXT_PRIMARY};")
        feat_layout.addWidget(feat_title)

        features = [
            ("Multi-Key Pooling thông minh", "Nạp nhiều API Key cùng lúc, tự động xoay vòng và chia luồng song song tránh giới hạn hạn mức (Rate limit 429)."),
            ("Tự động hậu xử lý CJK", "Tự động phát hiện và dịch bù các câu còn sót tiếng Trung/Nhật/Hàn sau khi dịch file."),
            ("Trình chỉnh sửa phụ đề trực quan", "Chỉnh sửa trực tiếp trên trình duyệt, đo lường tốc độ đọc CPS và xuất phụ đề theo chuẩn mong muốn."),
            ("Dịch hàng loạt & Xuất ZIP", "Kéo thả nhiều file SRT/ASS/VTT hoặc Video/Audio, dịch tự động theo hàng đợi và tải trọn bộ bằng 1 click."),
        ]

        for f_title, f_desc in features:
            item_box = QVBoxLayout()
            item_box.setSpacing(2)
            t_lbl = QLabel(f_title)
            t_lbl.setStyleSheet(f"font-size: {tokens.FS_CARD_TITLE}px; font-weight: 600; color: {tokens.PRIMARY};")
            d_lbl = QLabel(f_desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet(f"font-size: {tokens.FS_LABEL}px; color: {tokens.TEXT_SECONDARY};")
            item_box.addWidget(t_lbl)
            item_box.addWidget(d_lbl)
            feat_layout.addLayout(item_box)

        self.layout.addWidget(feat_card)

    def _ensure_server_running(self) -> str:
        if not self.server_manager.is_running():
            url = self.server_manager.start(open_browser=False)
            self._update_status()
            return url
        return self.server_manager.get_url()

    def _update_status(self) -> None:
        if self.server_manager.is_running():
            url = self.server_manager.get_url()
            self.status_badge.set_state("Đang hoạt động", "success")
            self.url_label.setText(f"Địa chỉ cục bộ: {url}")
        else:
            self.status_badge.set_state("Đã dừng", "error")
            self.url_label.setText("Địa chỉ: Server chưa chạy")

        cfg = GeminiSrtServerManager.get_voxdub_config()
        key_count = len(cfg.get("api_keys", []))
        if key_count > 0:
            self.keys_info_label.setText(f"Đã đồng bộ {key_count} Gemini API Key từ cấu hình VoxDub Studio.")
        else:
            self.keys_info_label.setText("Chưa tìm thấy API Key trong cài đặt VoxDub. Bạn có thể thêm key trên giao diện web.")

    def _open_web_ui(self) -> None:
        url = self._ensure_server_running()
        if url:
            open_url(url)
            TOASTS.info("Đã mở trình dịch web trong trình duyệt.")

    def _restart_server(self) -> None:
        self.server_manager.stop()
        url = self.server_manager.start(open_browser=False)
        self._update_status()
        TOASTS.success(f"Đã khởi động lại server tại {url}")

    def _open_output_folder(self) -> None:
        try:
            settings = self._settings_getter()
            out_dir = getattr(settings, "output_dir", "") or os.path.join(os.getcwd(), "output")
        except Exception:
            out_dir = os.path.join(os.getcwd(), "output")

        os.makedirs(out_dir, exist_ok=True)
        open_folder(out_dir)

    def on_shown(self) -> None:
        """Được gọi khi chuyển vào trang: tự động bật server và cập nhật trạng thái."""
        self._ensure_server_running()
        self._update_status()

    def shutdown(self) -> None:
        """Dừng server khi đóng ứng dụng."""
        if self.server_manager.is_running():
            self.server_manager.stop()

    def cleanup(self) -> None:
        """Dọn dẹp tài nguyên."""
        self.shutdown()
