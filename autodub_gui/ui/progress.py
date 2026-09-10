"""Thanh tiến trình mỏng và chỉ báo lưu tự động."""
from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from autodub_gui import tokens

_BAR_H = 5
_DOT = "●"          # chấm tròn đặc — ký tự hình học, không phải biểu tượng cảm xúc
_SPIN_MS = 400

# trạng thái lưu -> (màu chấm, nhãn hiển thị)
_SAVE_STATES: dict[str, tuple[str, str]] = {
    "idle":   (tokens.TEXT_MUTED, "Lưu tự động"),
    "saving": (tokens.PROCESSING, "Đang lưu"),
    "saved":  (tokens.SUCCESS, "Đã lưu"),
    "error":  (tokens.DANGER, "Lỗi lưu"),
}


class ThinProgressBar(QProgressBar):
    """Thanh tiến trình cao 5px, không hiện số phần trăm bên trong."""

    def __init__(self, parent: QWidget | None = None, *,
                 color: str = tokens.PRIMARY):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)
        # Chỉ là thanh đồ họa, không chứa chữ, nên đặt chiều cao cứng là an toàn.
        self.setFixedHeight(_BAR_H)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        """Đổi màu phần đã chạy cho khớp trạng thái của mục."""
        from autodub_gui.theme import _grad_h
        chunk_grad = _grad_h(color, tokens.ACCENT_BLUE)
        self.setStyleSheet(
            f"QProgressBar {{ background: {tokens.TRACK_BG}; border: none; "
            f"border-radius: 2px; height: 4px; }}"
            f"QProgressBar::chunk {{ background: {chunk_grad}; "
            f"border-radius: 2px; }}")

    def set_indeterminate(self, on: bool) -> None:
        """Chế độ chưa rõ phần trăm, dùng khi đang chờ tác vụ chưa đo được."""
        self.setRange(0, 0) if on else self.setRange(0, 100)


class SaveIndicator(QWidget):
    """Chấm màu kèm chữ: Lưu tự động, Đang lưu, Đã lưu, Lỗi lưu."""

    _sig_state = Signal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._sig_state.connect(self._do_set_state, Qt.ConnectionType.QueuedConnection)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._dot = QLabel(_DOT)
        self._text = QLabel("")
        self._text.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_LABEL}px; "
            f"background: transparent;")
        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        self._timer = QTimer(self)
        self._timer.setInterval(_SPIN_MS)
        self._timer.timeout.connect(self._tick)
        self._dots = 0
        self._state = "idle"
        self._label = _SAVE_STATES["idle"][1]
        self.set_state("idle")

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, detail: str = "") -> None:
        """Đổi trạng thái: idle, saving, saved hoặc error."""
        if QThread.currentThread() != self.thread():
            self._sig_state.emit(state, detail)
            return
        self._do_set_state(state, detail)

    @Slot(str, str)
    def _do_set_state(self, state: str, detail: str = "") -> None:
        color, label = _SAVE_STATES.get(state, _SAVE_STATES["idle"])
        self._state = state
        self._dot.setStyleSheet(
            f"color: {color}; font-size: {tokens.FS_META}px; "
            f"background: transparent;")
        self._label = label
        self._text.setText(f"{label} {detail}".strip())
        self.setToolTip(detail or label)
        if state == "saving":
            self._dots = 0
            self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self._text.setText(self._label + "." * self._dots)


class DownloadProgressBar(QWidget):
    """Thanh tiến trình tải video hiển thị chi tiết dung lượng MB, tốc độ và phần trăm."""

    _sig_progress = Signal(float, str)
    _sig_reset = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._sig_progress.connect(self._do_set_progress, Qt.ConnectionType.QueuedConnection)
        self._sig_reset.connect(self._do_reset, Qt.ConnectionType.QueuedConnection)

        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
        from autodub_gui import tokens
        from autodub_gui.theme import _grad_h

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, tokens.SP_1, 0, tokens.SP_1)
        layout.setSpacing(tokens.SP_1)

        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_status = QLabel("Đang chuẩn bị tải...")
        self.lbl_status.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FS_META}px; background: transparent;"
        )

        self.lbl_percent = QLabel("0%")
        self.lbl_percent.setStyleSheet(
            f"color: {tokens.PRIMARY}; font-weight: bold; font-size: {tokens.FS_META}px; background: transparent;"
        )

        info_layout.addWidget(self.lbl_status)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_percent)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        chunk_grad = _grad_h(tokens.PRIMARY, tokens.ACCENT_BLUE)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {tokens.TRACK_BG}; border: none; border-radius: 3px; height: 6px; }}"
            f"QProgressBar::chunk {{ background: {chunk_grad}; border-radius: 3px; }}"
        )

        layout.addLayout(info_layout)
        layout.addWidget(self.bar)
        self.hide()

    def set_progress(self, pct: float, msg: str = "") -> None:
        """pct: 0.0 - 1.0, msg: thông tin tốc độ và dung lượng."""
        if QThread.currentThread() != self.thread():
            self._sig_progress.emit(pct, msg)
            return
        self._do_set_progress(pct, msg)

    @Slot(float, str)
    def _do_set_progress(self, pct: float, msg: str = "") -> None:
        self.show()
        val = int(max(0.0, min(1.0, pct)) * 100)
        self.bar.setValue(val)
        self.lbl_percent.setText(f"{val}%")
        if msg:
            self.lbl_status.setText(msg)

    def reset(self) -> None:
        if QThread.currentThread() != self.thread():
            self._sig_reset.emit()
            return
        self._do_reset()

    @Slot()
    def _do_reset(self) -> None:
        self.bar.setValue(0)
        self.lbl_percent.setText("0%")
        self.lbl_status.setText("")
        self.hide()


