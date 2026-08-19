"""Công cụ Dịch phụ đề Gemini SRT Translator Pro.
Tích hợp giao diện Web và Server xử lý dịch SRT/ASS với Google Gemini AI.
"""
from autodub.tools.gemini_srt_ui.app import create_app, get_static_folder
from autodub.tools.gemini_srt_ui.server_manager import (
    GeminiSrtServerManager,
    get_server_manager,
)

__all__ = ["create_app", "get_static_folder", "GeminiSrtServerManager", "get_server_manager"]
