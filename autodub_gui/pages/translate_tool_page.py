"""Trang Dịch thuật — ngữ cảnh video và cấu hình khóa API."""
from __future__ import annotations

import threading

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QWidget

from autodub_gui.pages import settings_fields as spec
from autodub_gui.pages.tool_page_base import ToolPage
from autodub_gui.ui.buttons import PrimaryButton


class _FinishEvent(QEvent):
    _TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback):
        super().__init__(self._TYPE)
        self.callback = callback


class TranslateToolPage(ToolPage):
    """Ngữ cảnh dịch và trạng thái kết nối tới máy chủ."""

    TAB = spec.TAB_TRANSLATE
    TITLE = "Dịch thuật"
    SUBTITLE = ("Cấu hình khóa API (phương thức 1) hoặc Google AI Studio trình duyệt "
                "(phương thức 2, miễn phí). Có API Key thì luôn ưu tiên phương thức 1.")
    EXPANDED = {
        "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)",
        "Khóa API dịch AI",
        "Dịch tự động",
        "Ngữ cảnh video",
        "Nội dung đăng bài",
        "Dịch qua AI Studio (Trình duyệt)",
    }
    SAVE_LABEL = "Lưu cấu hình dịch"
    SAVED_TOAST = "Đã lưu cấu hình dịch."

    def extra_panels(self) -> list[QWidget]:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_login_studio = PrimaryButton("Đăng nhập Google AI Studio")
        self.btn_login_studio.setToolTip(
            "Mở Chrome để đăng nhập Google lần đầu. Cookies sẽ được lưu "
            "cho các lần dịch sau."
        )
        self.btn_login_studio.clicked.connect(self._on_login_studio)
        layout.addWidget(self.btn_login_studio)

        self.btn_check_studio = PrimaryButton("Kiểm tra đăng nhập")
        self.btn_check_studio.setToolTip(
            "Kiểm tra xem Chrome profile đã đăng nhập Google AI Studio hay chưa."
        )
        self.btn_check_studio.clicked.connect(self._on_check_studio)
        layout.addWidget(self.btn_check_studio)

        self._login_status = QLabel("")
        self._login_status.setObjectName("hint")
        layout.addWidget(self._login_status, 1)

        return [panel]

    def reload(self) -> None:
        super().reload()
        self._auto_check_studio()

    def _auto_check_studio(self) -> None:
        from autodub.text.translate_browser import _has_google_session, _get_default_profile_dir, get_cached_login_status
        cached = get_cached_login_status()
        if cached == "true":
            self._login_status.setText("Đã đăng nhập Google AI Studio — sẵn sàng dịch!")
            return

        profile_dir = _get_default_profile_dir()
        if not _has_google_session(profile_dir):
            self._login_status.setText("Chưa đăng nhập — bấm 'Đăng nhập Google AI Studio' trước khi dịch.")
            return

        self._login_status.setText("Đang kiểm tra đăng nhập AI Studio...")
        self.btn_check_studio.setEnabled(False)

        def worker():
            from autodub.text.translate_browser import check_login_status
            result = check_login_status()

            def _update():
                self.btn_check_studio.setEnabled(True)
                if result["logged_in"]:
                    self._login_status.setText("Đã đăng nhập Google AI Studio — sẵn sàng dịch!")
                else:
                    self._login_status.setText("Chưa đăng nhập — bấm 'Đăng nhập Google AI Studio' trước khi dịch.")
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.instance().postEvent(self, _FinishEvent(_update))
            except Exception:
                _update()

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_studio(self) -> None:
        if getattr(self, "_check_running", False):
            return
        self._check_running = True
        self.btn_check_studio.setEnabled(False)
        self._login_status.setText("Đang kiểm tra đăng nhập AI Studio...")

        def worker():
            from autodub.text.translate_browser import check_login_status
            result = check_login_status()
            self._check_running = False

            def _finish():
                self.btn_check_studio.setEnabled(True)
                if result["logged_in"]:
                    self._login_status.setText("Đã đăng nhập Google AI Studio — sẵn sàng dịch!")
                elif result["error"]:
                    self._login_status.setText(f"{result['error']}")
                else:
                    self._login_status.setText("Chưa đăng nhập — bấm 'Đăng nhập Google AI Studio' trước khi dịch.")
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.instance().postEvent(self, _FinishEvent(_finish))
            except Exception:
                _finish()

        threading.Thread(target=worker, daemon=True).start()

    def _on_login_studio(self) -> None:
        if getattr(self, "_login_running", False):
            return
        self._login_running = True
        self.btn_login_studio.setEnabled(False)
        self.btn_login_studio.setText("Đang mở cửa sổ đăng nhập...")
        self._login_status.setText("Hãy đăng nhập Google trên cửa sổ Chrome vừa mở...")

        def worker():
            error = ""
            try:
                from autodub.text.translate_browser import AiStudioBrowserClient
                client = AiStudioBrowserClient(headless=False)
                client.open_login_window()
            except Exception as exc:
                error = str(exc)
            finally:
                self._login_running = False
            err = error

            def _finish():
                self.btn_login_studio.setEnabled(True)
                self.btn_login_studio.setText("Đăng nhập Google AI Studio")
                if err:
                    self._login_status.setText(f"Lỗi: {err}")
                    QMessageBox.warning(
                        self, "Không mở được cửa sổ đăng nhập",
                        f"Hãy đóng các cửa sổ Chrome khác của AI Studio rồi thử lại.\n\nChi tiết: {err}",
                    )
                else:
                    self._login_status.setText("Đang xác minh đăng nhập...")
                    self._auto_check_studio()

            try:
                from PySide6.QtWidgets import QApplication
                QApplication.instance().postEvent(self, _FinishEvent(_finish))
            except Exception:
                _finish()

        threading.Thread(target=worker, daemon=True).start()

    def customEvent(self, event):
        if isinstance(event, _FinishEvent):
            event.callback()

    def cleanup(self) -> None:
        pass
