"""Trang Dịch thuật — ngữ cảnh video và kiểm tra kết nối máy chủ.

Mô hình, lời nhắc và API Key đã chuyển hẳn lên máy chủ VoxDub, nên trang này
không còn ô API Key nào. Thứ còn lại là NGỮ CẢNH: những gì người làm kênh
biết về video mà máy không tự đoán chính xác được — chủ đề, xưng hô, thuật
ngữ phải dịch cố định.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from autodub_gui.pages import settings_fields as spec
from autodub_gui.pages.settings_panels import ConnectionChecks
from autodub_gui.pages.tool_page_base import ToolPage


class TranslateToolPage(ToolPage):
    """Ngữ cảnh dịch và trạng thái kết nối tới máy chủ."""

    TAB = spec.TAB_TRANSLATE
    TITLE = "Dịch thuật"
    SUBTITLE = ("Cấu hình danh sách khóa API (Google Gemini Direct, OpenRouter, OpenAI, DeepSeek) "
                "để chia luồng song song hoặc điều chỉnh ngữ cảnh và xưng hô cho video.")
    EXPANDED = {
        "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)",
        "Khóa API dịch AI",
        "Dịch tự động",
        "Ngữ cảnh video",
        "Nội dung đăng bài",
    }
    SAVE_LABEL = "Lưu cấu hình dịch"
    SAVED_TOAST = "Đã lưu cấu hình dịch."

    def extra_panels(self) -> list[QWidget]:
        self.checks_panel = ConnectionChecks()
        return [self.checks_panel]

    def cleanup(self) -> None:
        panel = getattr(self, "checks_panel", None)
        if panel is not None and hasattr(panel, "cleanup"):
            panel.cleanup()
