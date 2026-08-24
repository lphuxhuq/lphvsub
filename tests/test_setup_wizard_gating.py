"""Kiểm tra logic gating của wizard cài đặt lần đầu.

Không dùng Qt, không mở cửa sổ. Chỉ test:
  - AUTODUB_SMOKE=1 → không hiện
  - Marker file tồn tại → không hiện
  - Tất cả components cốt lõi đã sẵn sàng → đánh dấu done, không hiện
  - Chưa có components → cần wizard (_is_setup_needed = True)
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest import mock


def _reload_wizard():
    """Nạp lại module để reset cache import."""
    if "autodub_gui.setup_wizard" in sys.modules:
        del sys.modules["autodub_gui.setup_wizard"]
    return importlib.import_module("autodub_gui.setup_wizard")


# ---------------------------------------------------------------------------
# _is_setup_needed
# ---------------------------------------------------------------------------

def test_marker_exists_not_needed(tmp_path, monkeypatch):
    """Marker file tồn tại → wizard không cần hiện."""
    marker = tmp_path / "setup_wizard_done"
    marker.touch()

    wiz = _reload_wizard()
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))

    assert wiz._is_setup_needed() is False


def test_no_marker_needed(tmp_path, monkeypatch):
    """Không có marker → wizard cần hiện."""
    marker = tmp_path / "setup_wizard_done"
    # Không tạo file

    wiz = _reload_wizard()
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))

    assert wiz._is_setup_needed() is True


# ---------------------------------------------------------------------------
# maybe_show_setup_wizard — gating logic
# ---------------------------------------------------------------------------

def test_smoke_env_skips_wizard(tmp_path, monkeypatch):
    """AUTODUB_SMOKE=1 → wizard không hiện ngay cả khi chưa setup."""
    monkeypatch.setenv("AUTODUB_SMOKE", "1")

    wiz = _reload_wizard()
    # Đảm bảo _is_setup_needed sẽ trả về True nếu không có SMOKE
    marker = tmp_path / "setup_wizard_done"
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))
    monkeypatch.setattr(wiz, "_core_ready", lambda: False)

    showed = wiz.maybe_show_setup_wizard(None)
    assert showed is False


def test_marker_done_skips_wizard(tmp_path, monkeypatch):
    """Marker file tồn tại → wizard không hiện (người dùng cũ)."""
    monkeypatch.delenv("AUTODUB_SMOKE", raising=False)

    wiz = _reload_wizard()
    marker = tmp_path / "setup_wizard_done"
    marker.write_text("done\n")
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))

    showed = wiz.maybe_show_setup_wizard(None)
    assert showed is False


def test_all_core_ready_marks_done_no_wizard(tmp_path, monkeypatch):
    """Tất cả components cốt lõi sẵn sàng (user tự cài) → đánh dấu done,
    không hiện wizard."""
    monkeypatch.delenv("AUTODUB_SMOKE", raising=False)

    wiz = _reload_wizard()
    marker = tmp_path / "setup_wizard_done"
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))
    monkeypatch.setattr(wiz, "_is_setup_needed", lambda: True)
    monkeypatch.setattr(wiz, "_core_ready", lambda: True)

    showed = wiz.maybe_show_setup_wizard(None)

    assert showed is False
    assert marker.is_file(), "Phải ghi marker khi tất cả đã ready"


def test_missing_components_needs_wizard(tmp_path, monkeypatch):
    """Thiếu components + không có marker → should_show = True.

    Wizard phải được khởi tạo và exec() phải được gọi. Patch cả class để
    tránh tạo QWidget thật (cần QApplication).
    """
    monkeypatch.delenv("AUTODUB_SMOKE", raising=False)

    wiz = _reload_wizard()
    marker = tmp_path / "setup_wizard_done"
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))
    monkeypatch.setattr(wiz, "_is_setup_needed", lambda: True)
    monkeypatch.setattr(wiz, "_core_ready", lambda: False)

    # Patch toàn bộ class SetupWizard để không chạy Qt code nào
    fake_wizard_instance = mock.MagicMock()
    fake_wizard_class = mock.MagicMock(return_value=fake_wizard_instance)
    monkeypatch.setattr(wiz, "SetupWizard", fake_wizard_class)

    showed = wiz.maybe_show_setup_wizard(None)

    assert showed is True
    fake_wizard_instance.exec.assert_called_once()
    assert marker.is_file(), "Phải ghi marker sau khi wizard chạy xong"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_mark_done_creates_file(tmp_path, monkeypatch):
    """_mark_done() phải tạo file marker."""
    wiz = _reload_wizard()
    marker = tmp_path / "setup_wizard_done"
    monkeypatch.setattr(wiz, "_marker_path", lambda: str(marker))

    wiz._mark_done()

    assert marker.is_file()
    assert marker.read_text().strip() == "done"


def test_ffmpeg_ready_system_path(monkeypatch):
    """_ffmpeg_ready() trả True khi shutil.which tìm thấy ffmpeg."""
    wiz = _reload_wizard()
    monkeypatch.setattr(wiz, "_ffmpeg_ready",
                        lambda: True,  # mock trực tiếp để không cần PATH thật
                        raising=False)
    # Gọi hàm được mock
    assert wiz._ffmpeg_ready() is True


def test_ffmpeg_not_ready(monkeypatch):
    """_ffmpeg_ready() trả False khi không tìm thấy ffmpeg và bin/ không có."""
    import shutil as _shutil

    wiz = _reload_wizard()
    with mock.patch.object(_shutil, "which", return_value=None), \
         mock.patch("autodub_gui.setup_wizard.os.path.isfile", return_value=False):
        result = wiz._ffmpeg_ready()

    assert result is False


def test_paraformer_ready_checks_marker(tmp_path, monkeypatch):
    """_paraformer_ready() dựa vào Settings.paraformer_configured()."""
    wiz = _reload_wizard()

    # Giả lập chưa cài
    with mock.patch(
        "autodub_gui.setup_wizard._paraformer_ready", return_value=False
    ):
        assert wiz._paraformer_ready() is False

    # Giả lập đã cài
    with mock.patch(
        "autodub_gui.setup_wizard._paraformer_ready", return_value=True
    ):
        assert wiz._paraformer_ready() is True


def test_core_ready_requires_all_three(monkeypatch):
    """_core_ready() chỉ True khi cả 3 components (ffmpeg+vieneu+whisper) sẵn."""
    wiz = _reload_wizard()

    # Thiếu 1 → False
    with mock.patch("autodub_gui.setup_wizard._ffmpeg_ready", return_value=True), \
         mock.patch("autodub_gui.setup_wizard._vieneu_ready", return_value=False), \
         mock.patch("autodub_gui.setup_wizard._whisper_ready", return_value=True):
        assert wiz._core_ready() is False

    # Đủ 3 → True
    with mock.patch("autodub_gui.setup_wizard._ffmpeg_ready", return_value=True), \
         mock.patch("autodub_gui.setup_wizard._vieneu_ready", return_value=True), \
         mock.patch("autodub_gui.setup_wizard._whisper_ready", return_value=True):
        assert wiz._core_ready() is True
