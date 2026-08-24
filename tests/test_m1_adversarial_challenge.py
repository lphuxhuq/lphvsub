"""Empirical Adversarial Stress Test Suite for Milestone 1.

Targeting:
1. Shortcut registration in EDITOR_SHORTCUTS and binding dispatch in install_editor_shortcuts.
2. Split at playhead: outside segment, near boundary (< 0.2s), exactly on boundary, short segment (< 0.4s), empty project, recursive splits.
3. Merge with next: last segment, no selection, non-adjacent items, single segment, empty project.
4. QUndoStack integration: 15-cycle undo/redo, chained multi-operation undo trees, disk transcript synchronization, voice/sub_vi preservation.
5. GUI stability: zoom slider synchronization, extreme timeline coordinates, audio peak edge cases, file locking release/restore.
"""
from __future__ import annotations

import json
import math
import os
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

from autodub.config import Settings
from autodub.editor import EditorError
from autodub_gui import waveform
from autodub_gui.pages.editor_commands import (
    AddSegmentCommand,
    DeleteSegmentCommand,
    MergeSegmentCommand,
    MoveSegmentCommand,
    SplitSegmentCommand,
)
from autodub_gui.pages.editor_page import EditorPage
from autodub_gui.shortcuts import (
    ALL_SHORTCUTS,
    EDITOR_SHORTCUTS,
    GLOBAL_SHORTCUTS,
    Shortcut,
    bind,
    install_editor_shortcuts,
    install_global_shortcuts,
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
    _snap,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_challenge_project(tmp_path):
    work = tmp_path / "challenge_m1_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 0.0, "end": 4.0, "duration": 4.0, "text": "Hello world", "text_vi": "Xin chào thế giới", "voice": "vi-VN-Standard-A"},
        {"id": 2, "start": 5.0, "end": 8.0, "duration": 3.0, "text": "How are you", "text_vi": "Bạn khỏe không", "sub_vi": "Bạn thế nào"},
        {"id": 3, "start": 9.0, "end": 12.0, "duration": 3.0, "text": "Goodbye", "text_vi": "Tạm biệt"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    for i in (1, 2, 3):
        (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"fake_wav")
    return str(work)


@pytest.fixture
def editor_page(qapp, mock_challenge_project):
    with patch.object(EditorPage, "_start_thumb_worker"):
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_challenge_project)
        yield page
        page.cleanup()
        page.deleteLater()


# ============================================================================
# Section 1: Adversarial Shortcut Registration & Dispatch Testing
# ============================================================================

class TestAdversarialShortcutDispatch:
    """Stress tests shortcut registry, QShortcut creation, and text-field protection."""

    def test_all_shortcuts_have_valid_key_sequences_and_scopes(self) -> None:
        assert len(ALL_SHORTCUTS) == len(GLOBAL_SHORTCUTS) + len(EDITOR_SHORTCUTS)
        for sc in ALL_SHORTCUTS:
            assert isinstance(sc.keys, str) and len(sc.keys) > 0
            assert isinstance(sc.action, str) and len(sc.action) > 0
            assert isinstance(sc.scope, str) and len(sc.scope) > 0
            seq = QKeySequence(sc.keys)
            assert not seq.isEmpty(), f"Invalid key sequence string: {sc.keys}"

    def test_m1_shortcuts_exact_registration(self) -> None:
        ctrl_b = [s for s in EDITOR_SHORTCUTS if s.keys == "Ctrl+B"]
        ctrl_j = [s for s in EDITOR_SHORTCUTS if s.keys == "Ctrl+J"]
        assert len(ctrl_b) == 1, "Ctrl+B must be registered in EDITOR_SHORTCUTS"
        assert len(ctrl_j) == 1, "Ctrl+J must be registered in EDITOR_SHORTCUTS"
        assert "tách" in ctrl_b[0].action.lower()
        assert "gộp" in ctrl_j[0].action.lower()

    def test_install_editor_shortcuts_dispatch_invocation(self, qapp) -> None:
        dummy = QWidget()
        dummy.toggle_play = MagicMock()
        dummy.delete_selected = MagicMock()
        dummy.save_now = MagicMock()
        dummy.undo = MagicMock()
        dummy.redo = MagicMock()
        dummy.split_current_segment = MagicMock()
        dummy.merge_current_segment = MagicMock()
        dummy.open_export_tab = MagicMock()
        dummy.focus_search = MagicMock()
        dummy.player = MagicMock()

        shortcuts = install_editor_shortcuts(dummy)
        sc_map = {sc.key().toString(): sc for sc in shortcuts}

        assert "Ctrl+B" in sc_map
        assert "Ctrl+J" in sc_map

        # Trigger activated signal on Ctrl+B and Ctrl+J
        sc_map["Ctrl+B"].activated.emit()
        assert dummy.split_current_segment.call_count == 1

        sc_map["Ctrl+J"].activated.emit()
        assert dummy.merge_current_segment.call_count == 1

        dummy.deleteLater()

    def test_typing_in_text_field_distinguishes_single_keys_vs_modifiers(self, qapp) -> None:
        window = QWidget()
        line_edit = QLineEdit(window)
        btn = QWidget(window)
        window.show()
        window.activateWindow()

        called = []
        bind(window, "Space", lambda: called.append("Space"), skip_when_typing=True)
        bind(window, "Ctrl+B", lambda: called.append("Ctrl+B"), skip_when_typing=False)
        bind(window, "Ctrl+J", lambda: called.append("Ctrl+J"), skip_when_typing=False)
        bind(window, "Delete", lambda: called.append("Delete"), skip_when_typing=True)

        sc_map = {sc.key().toString(): sc for sc in window.findChildren(QShortcut)}

        line_edit.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is True

        called.clear()
        sc_map["Space"].activated.emit()
        assert "Space" not in called, "Space must be skipped when typing"

        del_key = "Del" if "Del" in sc_map else "Delete"
        sc_map[del_key].activated.emit()
        assert "Delete" not in called, "Delete must be skipped when typing"

        sc_map["Ctrl+B"].activated.emit()
        assert "Ctrl+B" in called, "Ctrl+B must fire even when typing in text field"

        sc_map["Ctrl+J"].activated.emit()
        assert "Ctrl+J" in called, "Ctrl+J must fire even when typing in text field"

        btn.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is False

        called.clear()
        sc_map["Space"].activated.emit()
        assert "Space" in called

        sc_map[del_key].activated.emit()
        assert "Delete" in called

        window.deleteLater()

    def test_repeated_install_editor_shortcuts_stability(self, editor_page) -> None:
        sc1 = install_editor_shortcuts(editor_page)
        assert len(sc1) > 0
        sc2 = install_editor_shortcuts(editor_page)
        assert len(sc2) == len(sc1)
        assert editor_page._shortcuts is sc2


# ============================================================================
# Section 2: Adversarial Split At Playhead Testing
# ============================================================================

class TestAdversarialSplitAtPlayhead:
    """Stress tests all boundary conditions and edge cases for split_current_segment."""

    def test_split_at_playhead_normal_inside_segment(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        with patch.object(TOASTS, "info") as mock_info:
            editor_page.split_current_segment()
            assert mock_info.call_count == 1
        assert len(editor_page._segments) == 4
        assert abs(float(editor_page._segments[0]["start"]) - 0.0) < 1e-4
        assert abs(float(editor_page._segments[0]["end"]) - 2.0) < 1e-4
        assert abs(float(editor_page._segments[1]["start"]) - 2.0) < 1e-4
        assert abs(float(editor_page._segments[1]["end"]) - 4.0) < 1e-4
        assert editor_page._segments[0]["text_vi"] == "Xin chào"
        assert editor_page._segments[1]["text_vi"] == "thế giới"

    def test_split_at_exact_start_boundary_rejected(self, editor_page) -> None:
        editor_page.player.position = lambda: 0.0
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
            assert "quá sát" in mock_warn.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_split_at_exact_end_boundary_rejected(self, editor_page) -> None:
        editor_page.player.position = lambda: 4.0
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
            assert "quá sát" in mock_warn.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_split_near_boundary_less_than_0_2s_rejected(self, editor_page) -> None:
        editor_page.player.position = lambda: 0.19
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
        assert len(editor_page._segments) == 3

        editor_page.player.position = lambda: 3.81
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
        assert len(editor_page._segments) == 3

    def test_split_at_boundary_threshold_0_2s_succeeds(self, editor_page) -> None:
        editor_page.player.position = lambda: 0.20
        with patch.object(TOASTS, "info") as mock_info:
            editor_page.split_current_segment()
            assert mock_info.call_count == 1
        assert len(editor_page._segments) == 4
        assert abs(float(editor_page._segments[0]["end"]) - 0.20) < 1e-4

    def test_split_when_playhead_outside_segment_with_selected_subtitle(self, editor_page) -> None:
        editor_page.player.position = lambda: 4.5
        editor_page.subtitles.list.setCurrentRow(1)
        assert editor_page.subtitles.selected_id() == 2

        with patch.object(TOASTS, "info") as mock_info:
            editor_page.split_current_segment()
            assert mock_info.call_count == 1

        assert len(editor_page._segments) == 4
        seg2 = editor_page._segments[1]
        seg3 = editor_page._segments[2]
        assert abs(float(seg2["start"]) - 5.0) < 1e-4
        assert abs(float(seg2["end"]) - 6.5) < 1e-4
        assert abs(float(seg3["start"]) - 6.5) < 1e-4
        assert abs(float(seg3["end"]) - 8.0) < 1e-4

    def test_split_when_selected_segment_too_short_less_than_0_4s(self, editor_page) -> None:
        transcript_file = os.path.join(editor_page.work_dir(), "data", "transcript_vi.json")
        segs = [
            {"id": 1, "start": 0.0, "end": 0.35, "duration": 0.35, "text": "Short", "text_vi": "Ngắn"}
        ]
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(segs, f, ensure_ascii=False)
        editor_page.reload_segments()

        editor_page.player.position = lambda: 1.0
        editor_page.subtitles.list.setCurrentRow(0)

        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
            assert "quá ngắn" in mock_warn.call_args[0][0]

    def test_split_when_playhead_outside_and_no_selection(self, editor_page) -> None:
        editor_page.player.position = lambda: 4.5
        editor_page.subtitles.list.setCurrentItem(None)
        assert editor_page.subtitles.selected_id() == -1

        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.split_current_segment()
            assert mock_warn.call_count == 1
            assert "Không tìm thấy" in mock_warn.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_split_empty_segments_graceful(self, editor_page) -> None:
        editor_page._segments = []
        editor_page.player.position = lambda: 1.0
        editor_page.split_current_segment()

    def test_recursive_chained_splits(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 4

        editor_page.player.position = lambda: 1.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 5

        editor_page.player.position = lambda: 3.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 6

        for idx, seg in enumerate(editor_page._segments, start=1):
            assert seg["id"] == idx
            assert float(seg["start"]) < float(seg["end"])
            if idx > 1:
                assert float(seg["start"]) >= float(editor_page._segments[idx - 2]["end"])


# ============================================================================
# Section 3: Adversarial Merge With Next Testing
# ============================================================================

class TestAdversarialMergeWithNext:
    """Stress tests merge_current_segment and MergeSegmentCommand under adversarial conditions."""

    def test_merge_from_playhead_position(self, editor_page) -> None:
        editor_page.subtitles.list.setCurrentItem(None)
        editor_page.player.position = lambda: 1.0
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 2
        assert abs(float(editor_page._segments[0]["start"]) - 0.0) < 1e-4
        assert abs(float(editor_page._segments[0]["end"]) - 8.0) < 1e-4
        assert "Xin chào thế giới Bạn khỏe không" in editor_page._segments[0]["text_vi"]

    def test_merge_from_subtitle_selection(self, editor_page) -> None:
        editor_page.player.position = lambda: 0.5  # In seg 1
        editor_page.subtitles.list.setCurrentRow(1) # Selected seg 2
        assert editor_page.subtitles.selected_id() == 2
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 2
        assert abs(float(editor_page._segments[1]["start"]) - 5.0) < 1e-4
        assert abs(float(editor_page._segments[1]["end"]) - 12.0) < 1e-4
        assert "Bạn khỏe không Tạm biệt" in editor_page._segments[1]["text_vi"]

    def test_merge_on_last_segment_rejected(self, editor_page) -> None:
        editor_page.subtitles.list.setCurrentRow(2) # Last seg id 3
        assert editor_page.subtitles.selected_id() == 3
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.merge_current_segment()
            assert mock_warn.call_count == 1
            assert "Không có câu nào" in mock_warn.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_merge_no_selection_and_playhead_in_gap(self, editor_page) -> None:
        editor_page.subtitles.list.setCurrentItem(None)
        editor_page.player.position = lambda: 4.5
        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.merge_current_segment()
            assert mock_warn.call_count == 1
            assert "Vui lòng chọn" in mock_warn.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_merge_in_single_segment_project(self, editor_page) -> None:
        transcript_file = os.path.join(editor_page.work_dir(), "data", "transcript_vi.json")
        segs = [
            {"id": 1, "start": 0.0, "end": 4.0, "duration": 4.0, "text": "Single", "text_vi": "Duy nhất"}
        ]
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(segs, f, ensure_ascii=False)
        editor_page.reload_segments()
        editor_page.subtitles.list.setCurrentRow(0)

        with patch.object(TOASTS, "warn") as mock_warn:
            editor_page.merge_current_segment()
            assert mock_warn.call_count == 1
        assert len(editor_page._segments) == 1

    def test_merge_empty_project_graceful(self, editor_page) -> None:
        editor_page._segments = []
        editor_page.player.position = lambda: 1.0
        editor_page.merge_current_segment()

    def test_merge_non_adjacent_segments_command_error_handling(self, editor_page) -> None:
        with patch.object(editor_page, "report_error") as mock_report:
            editor_page._undo.push(MergeSegmentCommand(editor_page, [1, 3]))
            assert mock_report.call_count == 1
            assert "liền nhau" in mock_report.call_args[0][0]
        assert len(editor_page._segments) == 3

    def test_merge_less_than_two_segments_command_error_handling(self, editor_page) -> None:
        with patch.object(editor_page, "report_error") as mock_report:
            editor_page._undo.push(MergeSegmentCommand(editor_page, [1]))
            assert mock_report.call_count == 1
            assert "ít nhất hai câu" in mock_report.call_args[0][0]
        assert len(editor_page._segments) == 3


# ============================================================================
# Section 4: Adversarial QUndoStack Consistency & Cycle Testing
# ============================================================================

class TestAdversarialQUndoStackConsistency:
    """Stress tests deep undo/redo cycles, chained operations, and transcript integrity."""

    def test_qundo_stack_15_cycles_split_undo_redo(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 4

        for cycle in range(15):
            editor_page.undo()
            assert len(editor_page._segments) == 3, f"Undo failed at cycle {cycle}"
            assert float(editor_page._segments[0]["end"]) == 4.0

            editor_page.redo()
            assert len(editor_page._segments) == 4, f"Redo failed at cycle {cycle}"
            assert float(editor_page._segments[0]["end"]) == 2.0

    def test_qundo_stack_15_cycles_merge_undo_redo(self, editor_page) -> None:
        editor_page.subtitles.list.setCurrentRow(0)
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 2

        for cycle in range(15):
            editor_page.undo()
            assert len(editor_page._segments) == 3, f"Undo failed at cycle {cycle}"
            assert editor_page._segments[0]["text_vi"] == "Xin chào thế giới"
            assert editor_page._segments[1]["text_vi"] == "Bạn khỏe không"

            editor_page.redo()
            assert len(editor_page._segments) == 2, f"Redo failed at cycle {cycle}"
            assert "Xin chào thế giới Bạn khỏe không" in editor_page._segments[0]["text_vi"]

    def test_chained_mixed_operations_multi_level_undo_redo(self, editor_page) -> None:
        transcript_file = os.path.join(editor_page.work_dir(), "data", "transcript_vi.json")
        with open(transcript_file, encoding="utf-8") as f:
            initial_data = json.load(f)

        # 1. Split Seg 1 [0-4] at 2.0 -> 4 segments
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 4

        # 2. Move Seg 2 [2.0, 4.0] to [2.3, 4.3]
        editor_page._on_segment_moved(2, 2.3, 4.3)
        assert abs(float(editor_page._segments[1]["start"]) - 2.3) < 1e-4

        # 3. Merge Seg 2 and Seg 3 -> 3 segments
        editor_page._merge_with_next(2)
        assert len(editor_page._segments) == 3

        # 4. Add new segment after Seg 1 (duration 0.2s >= 0.2s)
        editor_page._undo.push(AddSegmentCommand(editor_page, 1, 2.05, 2.25, "Chèn mới"))
        assert len(editor_page._segments) == 4

        # 5. Undo all 4 steps sequentially
        editor_page.undo()  # Undo Add
        assert len(editor_page._segments) == 3

        editor_page.undo()  # Undo Merge
        assert len(editor_page._segments) == 4

        editor_page.undo()  # Undo Move
        assert abs(float(editor_page._segments[1]["start"]) - 2.0) < 1e-4

        editor_page.undo()  # Undo Split
        assert len(editor_page._segments) == 3

        # Verify disk transcript is identical to initial_data
        with open(transcript_file, encoding="utf-8") as f:
            restored_data = json.load(f)
        assert restored_data == initial_data

        # 6. Redo all 4 steps sequentially
        editor_page.redo()  # Redo Split
        assert len(editor_page._segments) == 4

        editor_page.redo()  # Redo Move
        assert abs(float(editor_page._segments[1]["start"]) - 2.3) < 1e-4

        editor_page.redo()  # Redo Merge
        assert len(editor_page._segments) == 3

        editor_page.redo()  # Redo Add
        assert len(editor_page._segments) == 4

    def test_voice_and_sub_vi_field_preservation_across_undo_redo(self, editor_page) -> None:
        assert editor_page._segments[0].get("voice") == "vi-VN-Standard-A"
        assert editor_page._segments[1].get("sub_vi") == "Bạn thế nào"

        # Split seg 1
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()

        # Merge seg 3 and seg 4
        editor_page._merge_with_next(3)

        # Undo merge and split
        editor_page.undo()
        editor_page.undo()

        assert editor_page._segments[0].get("voice") == "vi-VN-Standard-A"
        assert editor_page._segments[1].get("sub_vi") == "Bạn thế nào"


# ============================================================================
# Section 5: Adversarial GUI & Timeline Stability Testing
# ============================================================================

class TestAdversarialGUIStability:
    """Stress tests UI components, zoom synchronization, and graphics rendering."""

    def test_timeline_zoom_slider_continuous_synchronization_full_sweep(self, qapp) -> None:
        tl = Timeline()
        tl.resize(888, 120)

        for slider_val in range(10, 101, 5):
            tl.zoom_slider.setValue(slider_val)
            expected_zoom = slider_val / 10.0
            assert abs(tl.canvas.zoom() - expected_zoom) < 1e-4
            assert tl.zoom_label.text() == f"{expected_zoom:.1f}x"

        tl.deleteLater()

    def test_timeline_canvas_extreme_paint_conditions(self, qapp) -> None:
        canvas = TimelineCanvas()
        canvas.resize(888, 200)

        # 1. 0 duration, empty segments, empty peaks
        canvas.set_duration(0.0)
        canvas.set_segments([])
        canvas.set_peaks([])
        img1 = QImage(888, 200, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.render(img1)
        assert not img1.isNull()

        # 2. Huge peaks list (10,000 items)
        canvas.set_duration(3600.0)
        canvas.set_peaks([0.5] * 10000)
        img2 = QImage(888, 200, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.render(img2)
        assert not img2.isNull()

        # 3. Selected segment not present in segment list
        canvas.set_selected(99999)
        canvas.render(img2)

        canvas.deleteLater()

    def test_subtitle_block_drag_out_of_bounds_coordinates(self, qapp) -> None:
        canvas = TimelineCanvas()
        canvas.resize(888, 200)
        canvas.set_duration(10.0)
        canvas.set_segments([
            {"id": 1, "start": 2.0, "end": 4.0, "text_vi": "Test"}
        ])

        canvas._drag = {"mode": "move", "id": 1, "start": 2.0, "end": 4.0, "grab": 3.0}
        canvas._apply_drag(-5.0)
        seg = canvas._segments[0]
        assert float(seg["start"]) >= 0.0

        canvas._apply_drag(50.0)
        seg = canvas._segments[0]
        assert float(seg["end"]) <= 10.0

        canvas.deleteLater()
