"""Quản lý vòng đời và điều phối Flask Server cho Gemini SRT Translator Pro.

Chạy server trên luồng phụ an toàn (background daemon thread) sử dụng werkzeug make_server,
tự động đồng bộ các cấu hình API Key và cài đặt từ VoxDub Studio (.env).
"""
from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser
from typing import Optional

from werkzeug.serving import make_server

from autodub.tools.gemini_srt_ui.app import create_app


def find_free_port(start_port: int = 5050, max_attempts: int = 50) -> int:
    """Tìm một cổng mạng còn trống từ start_port trở lên."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_GLOBAL_MANAGER: Optional[GeminiSrtServerManager] = None


def get_server_manager() -> GeminiSrtServerManager:
    """Lấy hoặc tạo instance Server Manager dùng chung toàn hệ thống."""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = GeminiSrtServerManager()
    return _GLOBAL_MANAGER


class GeminiSrtServerManager:
    """Quản lý việc bật/tắt và đồng bộ cấu hình cho Web Server Gemini SRT."""

    def __init__(self, default_port: int = 5050, host: str = "127.0.0.1"):
        self.default_port = default_port
        self.host = host
        self.port: Optional[int] = None
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._url = ""
        self.pending_file: Optional[dict] = None

    def is_running(self) -> bool:
        """Kiểm tra xem server có đang chạy không."""
        with self._lock:
            return self._server is not None and self._thread is not None and self._thread.is_alive()

    def get_url(self) -> str:
        """Lấy địa chỉ URL của server đang chạy."""
        with self._lock:
            return self._url

    def _open_in_browser(self, url: str) -> None:
        """Mở URL trong trình duyệt qua QDesktopServices hoặc webbrowser."""
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if QDesktopServices.openUrl(QUrl(url)):
                return
        except Exception:
            pass
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def start(self, port: Optional[int] = None, open_browser: bool = False) -> str:
        """Khởi động server trên background thread.

        Nếu port không được chỉ định hoặc bị chiếm, tự động tìm port trống.
        """
        with self._lock:
            if self._server is not None and self._thread is not None and self._thread.is_alive():
                url = self._url
                if open_browser and url:
                    self._open_in_browser(url)
                return url

            target_port = port or self.default_port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((self.host, target_port)) == 0:
                    target_port = find_free_port(target_port + 1)

            self.port = target_port
            app = create_app()
            self._server = make_server(self.host, self.port, app, threaded=True)
            self._url = f"http://{self.host}:{self.port}"
            url = self._url

            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="GeminiSrtServerThread",
                daemon=True,
            )
            self._thread.start()

        if open_browser:
            time.sleep(0.3)
            self._open_in_browser(url)

        return url

    def open_project_srt(self, srt_path: str, work_dir: str = "", open_browser: bool = True) -> str:
        """Nạp trực tiếp file SRT từ dự án vào server và mở trình duyệt."""
        import shutil
        import uuid
        from werkzeug.utils import secure_filename
        from autodub.tools.gemini_srt_ui.app import UPLOAD_FOLDER, load_subtitles_safe

        url = self.start(open_browser=False)

        if not os.path.exists(srt_path):
            if open_browser:
                self._open_in_browser(url)
            return url

        base_name = os.path.basename(srt_path)
        unique_name = uuid.uuid4().hex + "_" + secure_filename(base_name)
        dst_path = os.path.join(UPLOAD_FOLDER, unique_name)
        try:
            shutil.copy2(srt_path, dst_path)
            subs = load_subtitles_safe(dst_path)
            line_count = len(subs)
        except Exception:
            line_count = 0

        self.pending_file = {
            "filename": unique_name,
            "original": base_name,
            "line_count": line_count,
            "file_type": "subtitle",
            "work_dir": work_dir,
        }

        full_url = f"{url}/?preload={unique_name}"
        if open_browser:
            time.sleep(0.3)
            self._open_in_browser(full_url)

        return full_url

    def stop(self) -> None:
        """Dừng server và giải phóng socket mà không giữ khóa."""
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._url = ""

        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass

        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

    @staticmethod
    def get_voxdub_config() -> dict:
        """Đọc danh sách API Keys và cấu hình từ VoxDub Settings / .env."""
        raw_keys_list = []
        target_lang = "Tiếng Việt"
        glossary = ""

        try:
            from autodub.config import Settings
            settings = Settings.load(override=True)
            if hasattr(settings, "gemini_api_keys") and settings.gemini_api_keys:
                raw_keys_list = list(settings.gemini_api_keys)
            elif hasattr(settings, "gemini_api_key") and settings.gemini_api_key:
                raw_keys_list = [settings.gemini_api_key]

            if hasattr(settings, "target_lang") and settings.target_lang:
                target_lang = settings.target_lang

            if hasattr(settings, "glossary") and settings.glossary:
                glossary = settings.glossary
        except Exception:
            pass

        if not raw_keys_list:
            raw_env = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
            if raw_env:
                raw_keys_list = [raw_env]

        # Tách từng key nếu được nối bằng dấu phẩy hoặc xuống dòng
        parsed_keys = []
        for item in raw_keys_list:
            if not item:
                continue
            for sub in item.replace(",", "\n").splitlines():
                k = sub.strip()
                if k and k not in parsed_keys:
                    parsed_keys.append(k)

        return {
            "api_keys": parsed_keys,
            "target_lang": target_lang,
            "glossary": glossary,
        }
