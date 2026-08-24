"""Adversarial stress-test suite for Milestone 1.

Targets:
1. Shortcut registration in EDITOR_SHORTCUTS and bindings in install_editor_shortcuts.
2. split_current_segment edge cases (outside segment, boundary < 0.2s, on boundary, with/without selection, short segments).
3. merge_current_segment edge cases (single segment, last segment, no selection, non-adjacent items, gap bridging).
4. QUndoStack integration (deep multi-action undo/redo cycles, state restoration, timing reversibility, transcript file sync).
5. GUI stability (zoom slider synchronization, typing protection, canvas edge-case rendering, clean shutdown).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

from autodub.config import Settings
from autodub_gui.pages.editor_commands import MergeSegmentCommand, SplitSegmentCommand
from autodub_gui.pages.editor_page import EditorPage
from autodub_gui.shortcuts import (
    ALL_SHORTCUTS,
    EDITOR_SHORTCUTS,
    GLOBAL_SHORTCUTS,
    install_editor_shortcuts,
    typing_in_text_field,
)
from autodub_gui.ui.toast import TOASTS
from autodub_gui.video.timeline import (
    BAND_H,
    LABEL_W,
    MAX_ZOOM,
    MIN_ZOOM,
    RULER_H,
    THUMB_H,
    TRACK_H,
    Timeline,
    TimelineCanvas,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_project_dir(tmp_path):
    work = tmp_path / "adv_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 0.0, "end": 4.0, "duration": 4.0, "text": "seg 1", "text_vi": "Câu thứ nhất", "voice": "hn_female"},
        {"id": 2, "start": 5.0, "end": 8.0, "duration": 3.0, "text": "seg 2", "text_vi": "Câu thứ hai"},
        {"id": 3, "start": 9.0, "end": 12.0, "duration": 3.0, "text": "seg 3", "text_vi": "Câu thứ ba"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    (work / "source.mp4").write_bytes(b"fake-mp4")
    for i in (1, 2, 3):
        (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"wav_bytes")
    return str(work)


@pytest.fixture
def single_seg_project_dir(tmp_path):
    work = tmp_path / "single_seg_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 1.0, "end": 5.0, "duration": 4.0, "text": "only seg", "text_vi": "Câu duy nhất"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    (work / "source.mp4").write_bytes(b"fake-mp4")
    (seg_dir / "seg_00001.wav").write_bytes(b"wav_bytes")
    return str(work)


@pytest.fixture
def short_seg_project_dir(tmp_path):
    work = tmp_path / "short_seg_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 1.0, "end": 1.35, "duration": 0.35, "text": "short seg", "text_vi": "Ngắn"},
        {"id": 2, "start": 2.0, "end": 6.0, "duration": 4.0, "text": "normal seg", "text_vi": "Bình thường"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    (work / "source.mp4").write_bytes(b"fake-mp4")
    for i in (1, 2):
        (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"wav_bytes")
    return str(work)


# =========================================================================
# 1. Shortcut Registration & Event Handling Verification
# =========================================================================
class TestShortcutRegistrationAndEventHandling:
    def test_shortcut_definitions_integrity(self) -> None:
        """Verify Ctrl+B and Ctrl+J in EDITOR_SHORTCUTS and ALL_SHORTCUTS."""
        editor_keys = {sc.keys: sc for sc in EDITOR_SHORTCUTS}
        assert "Ctrl+B" in editor_keys
        assert "Ctrl+J" in editor_keys
        assert editor_keys["Ctrl+B"].scope == "Trình chỉnh sửa"
        assert editor_keys["Ctrl+J"].scope == "Trình chỉnh sửa"
        assert "tách" in editor_keys["Ctrl+B"].action.lower()
        assert "gộp" in editor_keys["Ctrl+J"].action.lower()

        # Check ALL_SHORTCUTS contains both global and editor shortcuts without loss
        assert len(ALL_SHORTCUTS) == len(GLOBAL_SHORTCUTS) + len(EDITOR_SHORTCUTS)
        assert any(sc.keys == "Ctrl+B" for sc in ALL_SHORTCUTS)
        assert any(sc.keys == "Ctrl+J" for sc in ALL_SHORTCUTS)

    def test_install_editor_shortcuts_exact_bindings(self, qapp) -> None:
        """Verify that install_editor_shortcuts connects callbacks to target page methods."""
        page = QWidget()
        page.split_current_segment = MagicMock()
        page.merge_current_segment = MagicMock()
        page.toggle_play = MagicMock()
        page.delete_selected = MagicMock()
        page.save_now = MagicMock()
        page.undo = MagicMock()
        page.redo = MagicMock()
        page.open_export_tab = MagicMock()
        page.focus_search = MagicMock()
        page.player = MagicMock()

        shortcuts = install_editor_shortcuts(page)
        assert isinstance(shortcuts, list)
        key_map = {sc.key().toString(): sc for sc in shortcuts}

        assert "Ctrl+B" in key_map
        assert "Ctrl+J" in key_map

        # Simulate activation
        key_map["Ctrl+B"].activated.emit()
        page.split_current_segment.assert_called_once()

        key_map["Ctrl+J"].activated.emit()
        page.merge_current_segment.assert_called_once()
        page.deleteLater()

    def test_typing_in_text_field_event_filtering(self, qapp) -> None:
        """Verify typing_in_text_field identifies QLineEdit, QTextEdit, and QPlainTextEdit."""
        win = QWidget()
        le = QLineEdit(win)
        te = QTextEdit(win)
        pte = QPlainTextEdit(win)
        other = QWidget(win)
        win.show()

        le.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is True

        te.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is True

        pte.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is True

        other.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is False
        win.deleteLater()


# =========================================================================
# 2. split_current_segment Edge Case Verification
# =========================================================================
class TestSplitCurrentSegmentEdgeCases:
    def test_split_playhead_outside_segment_without_selection(self, qapp, mock_project_dir, monkeypatch) -> None:
        """Playhead at 4.5s (gap between seg 1 [0-4s] and seg 2 [5-8s]), no selection."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 4.5
        page.subtitles.selected_id = lambda: -1

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.split_current_segment()
        assert len(toast_warnings) == 1
        assert "Không tìm thấy câu nào" in toast_warnings[0]
        assert len(page._segments) == 3
        page.cleanup()

    def test_split_playhead_outside_segment_with_selection_midpoint_fallback(self, qapp, mock_project_dir) -> None:
        """Playhead at 4.5s, but Segment 1 [0-4s] is selected -> splits Seg 1 at midpoint 2.0s."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 4.5
        page.subtitles.selected_id = lambda: 1

        page.split_current_segment()
        assert len(page._segments) == 4
        assert page._segments[0]["id"] == 1
        assert abs(float(page._segments[0]["end"]) - 2.0) < 1e-4
        assert page._segments[1]["id"] == 2
        assert abs(float(page._segments[1]["start"]) - 2.0) < 1e-4
        assert abs(float(page._segments[1]["end"]) - 4.0) < 1e-4
        page.cleanup()

    def test_split_selected_segment_too_short_for_midpoint_split(self, qapp, short_seg_project_dir, monkeypatch) -> None:
        """Segment 1 is 0.35s long [1.0, 1.35]. Midpoint 1.175 is 0.175s from edges (< 0.2s) -> rejected."""
        page = EditorPage(Settings.load)
        page.open_work_dir(short_seg_project_dir)

        page.player.position = lambda: 0.5  # outside
        page.subtitles.selected_id = lambda: 1

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.split_current_segment()
        assert len(toast_warnings) == 1
        assert "quá ngắn" in toast_warnings[0]
        assert len(page._segments) == 2
        page.cleanup()

    @pytest.mark.parametrize("playhead_offset, expected_allowed", [
        (0.00, False),   # exactly on start
        (0.05, False),   # < 0.2s from start
        (0.19, False),   # < 0.2s from start
        (0.20, True),    # boundary threshold >= 0.2s
        (0.21, True),    # allowed
        (3.79, True),    # allowed
        (3.80, True),    # boundary threshold end - 0.2s
        (3.81, False),   # < 0.2s from end
        (3.95, False),   # < 0.2s from end
        (4.00, False),   # exactly on end
    ])
    def test_split_near_and_on_boundary(self, qapp, mock_project_dir, playhead_offset, expected_allowed, monkeypatch) -> None:
        """Seg 1 is [0.0, 4.0]s. Test various playhead positions."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: playhead_offset
        page.subtitles.selected_id = lambda: -1

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.split_current_segment()
        if expected_allowed:
            assert len(page._segments) == 4
            assert abs(float(page._segments[0]["end"]) - playhead_offset) < 1e-4
            assert abs(float(page._segments[1]["start"]) - playhead_offset) < 1e-4
        else:
            assert len(page._segments) == 3
            assert len(toast_warnings) == 1
        page.cleanup()

    def test_split_playhead_priority_over_selection(self, qapp, mock_project_dir) -> None:
        """Playhead is at 6.0s (inside Seg 2 [5-8s]), but Seg 1 is selected in SubtitleList -> splits Seg 2!"""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 6.0
        page.subtitles.selected_id = lambda: 1  # selection is Seg 1

        page.split_current_segment()
        # Seg 1 remains untouched [0, 4]
        assert abs(float(page._segments[0]["start"]) - 0.0) < 1e-4
        assert abs(float(page._segments[0]["end"]) - 4.0) < 1e-4
        # Seg 2 was split into [5, 6] and [6, 8]
        assert abs(float(page._segments[1]["start"]) - 5.0) < 1e-4
        assert abs(float(page._segments[1]["end"]) - 6.0) < 1e-4
        assert abs(float(page._segments[2]["start"]) - 6.0) < 1e-4
        assert abs(float(page._segments[2]["end"]) - 8.0) < 1e-4
        page.cleanup()


# =========================================================================
# 3. merge_current_segment Edge Case Verification
# =========================================================================
class TestMergeCurrentSegmentEdgeCases:
    def test_merge_single_segment_project(self, qapp, single_seg_project_dir, monkeypatch) -> None:
        """Project only has 1 segment -> merge must be safely rejected."""
        page = EditorPage(Settings.load)
        page.open_work_dir(single_seg_project_dir)

        page.player.position = lambda: 2.0
        page.subtitles.selected_id = lambda: 1

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.merge_current_segment()
        assert len(toast_warnings) == 1
        assert "Không có câu nào bên dưới để gộp" in toast_warnings[0]
        assert len(page._segments) == 1
        page.cleanup()

    def test_merge_last_segment_in_project(self, qapp, mock_project_dir, monkeypatch) -> None:
        """Seg 3 is the last segment -> merge must be safely rejected."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 10.0
        page.subtitles.selected_id = lambda: 3

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.merge_current_segment()
        assert len(toast_warnings) == 1
        assert "Không có câu nào bên dưới để gộp" in toast_warnings[0]
        assert len(page._segments) == 3
        page.cleanup()

    def test_merge_no_selection_and_playhead_outside_segments(self, qapp, mock_project_dir, monkeypatch) -> None:
        """Playhead at 4.5s (gap), no selection in list."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 4.5
        page.subtitles.selected_id = lambda: -1

        toast_warnings = []
        monkeypatch.setattr(TOASTS, "warn", lambda msg: toast_warnings.append(msg))

        page.merge_current_segment()
        assert len(toast_warnings) == 1
        assert "Vui lòng chọn một câu" in toast_warnings[0]
        assert len(page._segments) == 3
        page.cleanup()

    def test_merge_adjacent_segments_across_time_gap(self, qapp, mock_project_dir) -> None:
        """Seg 1 [0-4s] and Seg 2 [5-8s] have 1.0s gap. Merging them spans [0-8s]."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        page.player.position = lambda: 2.0
        page.merge_current_segment()

        assert len(page._segments) == 2
        assert page._segments[0]["id"] == 1
        assert abs(float(page._segments[0]["start"]) - 0.0) < 1e-4
        assert abs(float(page._segments[0]["end"]) - 8.0) < 1e-4
        assert abs(float(page._segments[0]["duration"]) - 8.0) < 1e-4
        assert page._segments[0]["text_vi"] == "Câu thứ nhất Câu thứ hai"
        page.cleanup()

    def test_merge_non_adjacent_segments_command_rejection(self, qapp, mock_project_dir, monkeypatch) -> None:
        """Direct push of MergeSegmentCommand with non-adjacent ids [1, 3] reports error without crash."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        errors_reported = []
        monkeypatch.setattr(page, "report_error", lambda msg: errors_reported.append(msg))

        cmd = MergeSegmentCommand(page, [1, 3])
        page._undo.push(cmd)

        assert len(errors_reported) == 1
        assert "liền nhau" in errors_reported[0]
        assert len(page._segments) == 3
        page.cleanup()


# =========================================================================
# 4. QUndoStack Multi-Cycle Reversibility & State Restoration
# =========================================================================
class TestQUndoStackIntegrationAndStateRestoration:
    def test_deep_undo_redo_multi_operation_lifecycle(self, qapp, mock_project_dir) -> None:
        """Stress-test 4 consecutive structural edits with full undo/redo cycles and disk verification."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)
        transcript_file = tmp_transcript_path = page._work_dir + "/data/transcript_vi.json"

        # Baseline: 3 segments: [0-4], [5-8], [9-12]
        assert len(page._segments) == 3
        with open(transcript_file, encoding="utf-8") as f:
            t0 = json.load(f)
        assert len(t0) == 3

        # Step 1: Split Seg 1 at 2.0s -> 4 segments: [0-2], [2-4], [5-8], [9-12]
        page.player.position = lambda: 2.0
        page.split_current_segment()
        assert len(page._segments) == 4
        assert [s["id"] for s in page._segments] == [1, 2, 3, 4]
        with open(transcript_file, encoding="utf-8") as f:
            t1 = json.load(f)
        assert len(t1) == 4

        # Step 2: Split Seg 2 at 3.0s -> 5 segments: [0-2], [2-3], [3-4], [5-8], [9-12]
        page.player.position = lambda: 3.0
        page.split_current_segment()
        assert len(page._segments) == 5
        assert [s["id"] for s in page._segments] == [1, 2, 3, 4, 5]
        with open(transcript_file, encoding="utf-8") as f:
            t2 = json.load(f)
        assert len(t2) == 5

        # Step 3: Merge Seg 4 [5-8] and Seg 5 [9-12] -> 4 segments: [0-2], [2-3], [3-4], [5-12]
        page.player.position = lambda: 6.0
        page.merge_current_segment()
        assert len(page._segments) == 4
        assert [s["id"] for s in page._segments] == [1, 2, 3, 4]
        assert abs(float(page._segments[3]["end"]) - 12.0) < 1e-4
        with open(transcript_file, encoding="utf-8") as f:
            t3 = json.load(f)
        assert len(t3) == 4

        # Step 4: Move Seg 1 start to 0.5s -> Seg 1 [0.5, 2.0]
        page._on_segment_moved(1, 0.5, 2.0)
        assert abs(float(page._segments[0]["start"]) - 0.5) < 1e-4
        with open(transcript_file, encoding="utf-8") as f:
            t4 = json.load(f)
        assert abs(float(t4[0]["start"]) - 0.5) < 1e-4

        # --- FULL UNDO STACK DRAIN ---
        # Undo Step 4
        page.undo()
        assert abs(float(page._segments[0]["start"]) - 0.0) < 1e-4
        with open(transcript_file, encoding="utf-8") as f:
            assert abs(float(json.load(f)[0]["start"]) - 0.0) < 1e-4

        # Undo Step 3
        page.undo()
        assert len(page._segments) == 5
        assert [s["id"] for s in page._segments] == [1, 2, 3, 4, 5]
        with open(transcript_file, encoding="utf-8") as f:
            assert len(json.load(f)) == 5

        # Undo Step 2
        page.undo()
        assert len(page._segments) == 4
        assert [s["id"] for s in page._segments] == [1, 2, 3, 4]
        with open(transcript_file, encoding="utf-8") as f:
            assert len(json.load(f)) == 4

        # Undo Step 1
        page.undo()
        assert len(page._segments) == 3
        assert [s["id"] for s in page._segments] == [1, 2, 3]
        with open(transcript_file, encoding="utf-8") as f:
            restored = json.load(f)
        assert len(restored) == 3
        assert restored[0]["start"] == 0.0 and restored[0]["end"] == 4.0
        assert restored[0].get("voice") == "hn_female"  # voice property preserved!

        # --- FULL REDO STACK PLAY ---
        page.redo()  # Step 1
        assert len(page._segments) == 4
        page.redo()  # Step 2
        assert len(page._segments) == 5
        page.redo()  # Step 3
        assert len(page._segments) == 4
        page.redo()  # Step 4
        assert abs(float(page._segments[0]["start"]) - 0.5) < 1e-4

        page.cleanup()


# =========================================================================
# 5. GUI Stability, Slider Synchronization & Event Filters
# =========================================================================
class TestGUIStabilityAndSliderSync:
    def test_zoom_slider_continuous_synchronization(self, qapp) -> None:
        """Verify zoom_slider changes update canvas zoom and zoom_label accurately."""
        tl = Timeline()
        tl.resize(800, 150)
        tl.canvas.set_duration(30.0)

        # 1. Slider to 10 (1.0x)
        tl.zoom_slider.setValue(10)
        assert abs(tl.canvas.zoom() - 1.0) < 1e-4
        assert tl.zoom_label.text() == "1.0x"

        # 2. Slider to 25 (2.5x)
        tl.zoom_slider.setValue(25)
        assert abs(tl.canvas.zoom() - 2.5) < 1e-4
        assert tl.zoom_label.text() == "2.5x"

        # 3. Slider to 400 (40.0x MAX_ZOOM)
        tl.zoom_slider.setValue(400)
        assert abs(tl.canvas.zoom() - 40.0) < 1e-4
        assert tl.zoom_label.text() == "40.0x"

        # 4. Zoom in button
        tl.zoom_slider.setValue(10)
        tl._zoom_in()
        assert abs(tl.canvas.zoom() - 1.25) < 1e-4
        assert tl.zoom_slider.value() == 12
        assert tl.zoom_label.text() == "1.2x" or tl.zoom_label.text() == "1.3x"

        # 5. Zoom out button
        tl._zoom_out()
        assert abs(tl.canvas.zoom() - 1.0) < 1e-4
        assert tl.zoom_slider.value() == 10
        assert tl.zoom_label.text() == "1.0x"

        tl.deleteLater()

    def test_timeline_canvas_degenerate_inputs_rendering_stability(self, qapp) -> None:
        """Render canvas with empty segments, zero duration, null peaks, multi-track toggles."""
        canvas = TimelineCanvas()
        canvas.resize(600, 200)

        # 1. Zero duration
        canvas.set_duration(0.0)
        img = QImage(600, 200, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.render(img)
        assert not img.isNull()

        # 2. Positive duration with empty peaks
        canvas.set_duration(15.0)
        canvas.set_peaks([])
        canvas.render(img)

        # 3. Multitrack with thumbnails
        canvas.set_track_available("original", True)
        canvas.set_track_available("voice", True)
        canvas.set_track_available("music", True)
        canvas.set_track_peaks("original", [0.2, 0.4] * 50)
        canvas.set_track_peaks("voice", [0.8, 0.1] * 50)
        canvas.set_track_peaks("music", [0.05, 0.05] * 50)
        canvas.set_thumbnails([(0.0, "nonexistent.jpg"), (5.0, "thumb2.jpg")])
        canvas.render(img)

        # 4. Selection range
        canvas._selection = (2.0, 6.0)
        canvas.render(img)

        # 5. Scissors mode
        canvas.set_scissors(True)
        canvas.render(img)

        canvas.deleteLater()

    def test_editor_page_breakpoint_responsiveness(self, qapp, mock_project_dir) -> None:
        """Verify on_breakpoint layout adapts properly without exceptions."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_project_dir)

        for bp in ("xl", "lg", "md", "sm", "unknown"):
            page.on_breakpoint(bp)

        page.cleanup()
