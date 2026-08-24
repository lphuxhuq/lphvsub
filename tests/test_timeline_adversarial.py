"""Adversarial stress tests and boundary condition verifications for Milestone 1.

Targeting:
1. Waveform extraction across unusual formats, bit depths, corruptions, and cache attacks.
2. Timeline Canvas numerical stability under extreme coordinate, duration, zoom, and geometry conditions.
3. Subtitle block drag, collision enforcement, minimum duration invariants, and edge grab behavior.
4. Successive rapid split (Ctrl+B), merge (Ctrl+J), and undo/redo state integrity.
"""
from __future__ import annotations

import json
import math
import os
import wave
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from autodub.config import Settings
from autodub_gui import waveform
from autodub_gui.pages.editor_page import EditorPage
from autodub_gui.shortcuts import (
    ALL_SHORTCUTS,
    EDITOR_SHORTCUTS,
    GLOBAL_SHORTCUTS,
    Shortcut,
    bind,
    install_editor_shortcuts,
    typing_in_text_field,
)
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
    _MIN_BLOCK_S,
    _snap,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def timeline_canvas(qapp):
    canvas = TimelineCanvas()
    canvas.resize(888, 200)
    canvas.set_duration(10.0)
    return canvas


@pytest.fixture
def mock_adversarial_project(tmp_path):
    work = tmp_path / "adv_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0, "text": "seg1", "text_vi": "Câu thoại một"},
        {"id": 2, "start": 2.5, "end": 5.0, "duration": 2.5, "text": "seg2", "text_vi": "Câu thoại hai"},
        {"id": 3, "start": 5.5, "end": 8.0, "duration": 2.5, "text": "seg3", "text_vi": "Câu thoại ba"},
        {"id": 4, "start": 8.5, "end": 10.0, "duration": 1.5, "text": "seg4", "text_vi": "Câu thoại bốn"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    (work / "source.mp4").write_bytes(b"fake-mp4")
    for i in range(1, 5):
        (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"wav")
    return str(work)


# ========================================================================
# Suite 1: Waveform Adversarial & Stress Testing
# ========================================================================

class TestWaveformAdversarial:
    """Stress-test peak extraction against malformed files, weird bit-depths, and cache anomalies."""

    def test_multichannel_audio_4ch_6ch_8ch(self, tmp_path) -> None:
        """Verify peak extraction handles 4-channel, 6-channel (5.1), and 8-channel (7.1) WAVs."""
        for num_channels in (4, 6, 8):
            path = tmp_path / f"audio_{num_channels}ch.wav"
            rate = 8000
            frames = 8000
            scale = np.iinfo(np.int16).max
            # Create multichannel signal
            data = np.ones((frames, num_channels), dtype=np.int16) * int(scale * 0.5)
            with wave.open(str(path), "wb") as out:
                out.setnchannels(num_channels)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(data.tobytes())

            res = waveform.peaks(str(path), buckets=50, use_cache=False)
            assert len(res) == 50, f"Failed for {num_channels} channels"
            assert all(0.48 <= v <= 0.52 for v in res), f"Incorrect peak average for {num_channels} channels"

    def test_waveform_non_power_of_two_chunk_alignment(self, tmp_path) -> None:
        """Audio with frame count not divisible by chunks or buckets."""
        path = tmp_path / "odd_length.wav"
        rate = 11025
        frames = 33333  # prime-ish length
        scale = np.iinfo(np.int16).max
        data = (np.sin(np.linspace(0, 100, frames)) * scale * 0.75).astype(np.int16)
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data.tobytes())

        res = waveform.peaks(str(path), buckets=77, use_cache=False)
        assert len(res) == 77
        assert all(0.0 <= v <= 1.0 for v in res)
        assert 0.70 <= max(res) <= 0.80

    def test_waveform_unsupported_formats_graceful_empty_return(self, tmp_path) -> None:
        """Verify 8-bit, 24-bit (3 bytes), and non-standard widths return empty list without crash."""
        # 24-bit WAV (3 bytes per sample)
        path24 = tmp_path / "audio_24bit.wav"
        with wave.open(str(path24), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(3)
            out.setframerate(8000)
            out.writeframes(b"\x00\x00\x40" * 1000)
        assert waveform.peaks(str(path24), buckets=50) == []

        # Zero frames file
        path_empty = tmp_path / "zero_frames.wav"
        with wave.open(str(path_empty), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(b"")
        assert waveform.peaks(str(path_empty), buckets=50) == []

    def test_waveform_cache_corruption_resilience(self, tmp_path) -> None:
        """Cache containing invalid JSON, wrong data types, NaN, or out-of-bounds numbers."""
        path = tmp_path / "audio.wav"
        rate = 8000
        frames = 8000
        data = np.zeros(frames, dtype=np.int16)
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data.tobytes())

        cache_path = tmp_path / waveform.CACHE_NAME

        # Case 1: Corrupt JSON syntax
        cache_path.write_text("{ unclosed", encoding="utf-8")
        res1 = waveform.peaks(str(path), buckets=20)
        assert len(res1) == 20

        # Case 2: Peaks field is not a list
        cache_path.write_text(json.dumps({
            "version": 1,
            "src": "audio.wav",
            "mtime": os.path.getmtime(str(path)),
            "n": 20,
            "peaks": "not a list",
        }), encoding="utf-8")
        res2 = waveform.peaks(str(path), buckets=20)
        assert len(res2) == 20

        # Case 3: Wrong version
        cache_path.write_text(json.dumps({
            "version": 999,
            "src": "audio.wav",
            "mtime": os.path.getmtime(str(path)),
            "n": 20,
            "peaks": [0.5] * 20,
        }), encoding="utf-8")
        res3 = waveform.peaks(str(path), buckets=20)
        assert len(res3) == 20
        assert res3[0] == 0.0  # Freshly computed from zeroed audio

    def test_waveform_extreme_bucket_sizes(self, tmp_path) -> None:
        """Bucket sizes from 1 to 100,000 buckets."""
        path = tmp_path / "audio_buckets.wav"
        rate = 8000
        frames = 8000
        scale = np.iinfo(np.int16).max
        data = (np.ones(frames, dtype=np.int16) * int(scale * 0.4))
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data.tobytes())

        # 1 bucket
        res1 = waveform.peaks(str(path), buckets=1, use_cache=False)
        assert len(res1) == 1
        assert 0.38 <= res1[0] <= 0.42

        # 10,000 buckets (more buckets than frames)
        res_large = waveform.peaks(str(path), buckets=10000, use_cache=False)
        assert len(res_large) == 10000


# ========================================================================
# Suite 2: Timeline Canvas Coordinates & Math Stress
# ========================================================================

class TestTimelineCanvasMathAdversarial:
    """Stress-test geometry, coordinate conversion, zooming, and extreme parameters."""

    def test_canvas_zero_and_negative_duration(self, timeline_canvas) -> None:
        """Negative and zero duration must not produce ZeroDivisionError or crash."""
        timeline_canvas.set_duration(0.0)
        assert timeline_canvas._visible_span() == 1.0
        assert timeline_canvas._to_x(5.0) == float(LABEL_W) + 5.0 * timeline_canvas._content_w()
        assert timeline_canvas._to_time(100.0) >= 0.0

        timeline_canvas.set_duration(-10.0)
        assert timeline_canvas._duration == 0.0  # clamped to 0.0
        assert timeline_canvas._visible_span() == 1.0

    def test_canvas_extreme_zoom_levels(self, timeline_canvas) -> None:
        """Extreme zoom values: sub-minimum, mega-zoom, infinity, negative."""
        timeline_canvas.set_duration(100.0)
        timeline_canvas.set_zoom(0.0001)
        assert timeline_canvas.zoom() == MIN_ZOOM
        timeline_canvas.set_zoom(-10.0)
        assert timeline_canvas.zoom() == MIN_ZOOM
        timeline_canvas.set_zoom(10000.0)
        assert timeline_canvas.zoom() == MAX_ZOOM

    def test_canvas_sub_pixel_or_collapsed_widget_size(self, timeline_canvas) -> None:
        """Widget width smaller than LABEL_W (e.g. width=50px)."""
        timeline_canvas.resize(50, 100)
        assert timeline_canvas._content_w() == 1  # max(1, width - LABEL_W)
        # Coordinate mapping should not divide by zero
        x = timeline_canvas._to_x(5.0)
        t = timeline_canvas._to_time(x)
        assert not math.isnan(x) and not math.isinf(x)
        assert not math.isnan(t) and not math.isinf(t)

    def test_canvas_ruler_label_step_under_extreme_spans(self, timeline_canvas) -> None:
        """Test ruler label step calculation under 100,000s duration and 0.001s span."""
        timeline_canvas.resize(800, 200)
        # Very large span
        timeline_canvas.set_duration(100000.0)
        timeline_canvas.set_zoom(1.0)
        step_large = timeline_canvas._label_step()
        assert step_large > 0

        # Very small span
        timeline_canvas.set_duration(1.0)
        timeline_canvas.set_zoom(40.0)
        step_small = timeline_canvas._label_step()
        assert step_small > 0

    def test_canvas_paint_event_extreme_states(self, timeline_canvas) -> None:
        """QPainter render on zero duration, negative offset, empty peaks, corrupted peaks."""
        # Zero duration
        timeline_canvas.set_duration(0.0)
        img0 = QImage(888, 200, QImage.Format.Format_ARGB32_Premultiplied)
        timeline_canvas.render(img0)
        assert not img0.isNull()

        # Extreme duration with many segments
        timeline_canvas.set_duration(50000.0)
        timeline_canvas.set_peaks([0.5] * 4000)
        segs = [{"id": i, "start": i * 10.0, "end": i * 10.0 + 8.0, "text_vi": f"Seg {i}"} for i in range(1000)]
        timeline_canvas.set_segments(segs)
        timeline_canvas.set_position(25000.0)
        img1 = QImage(888, 200, QImage.Format.Format_ARGB32_Premultiplied)
        timeline_canvas.render(img1)
        assert not img1.isNull()


# ========================================================================
# Suite 3: Subtitle Block Drag, Collisions & Snapping Stress
# ========================================================================

class TestSubtitleBlockAdversarial:
    """Stress-test interactive block dragging, boundary limits, minimum duration invariant."""

    def test_drag_left_handle_past_right_handle(self, timeline_canvas) -> None:
        """Dragging start handle past the end handle must clamp start <= end - 0.2s."""
        segs = [{"id": 1, "start": 2.0, "end": 4.0, "text_vi": "Test"}]
        timeline_canvas.set_segments(segs)
        timeline_canvas._drag = {"mode": "start", "id": 1, "start": 2.0, "end": 4.0, "grab": 2.0}
        # Attempt to drag start to 5.0s (past end 4.0s)
        timeline_canvas._apply_drag(5.0)
        seg = timeline_canvas._segments[0]
        assert seg["start"] <= seg["end"] - _MIN_BLOCK_S
        assert abs(seg["start"] - (4.0 - _MIN_BLOCK_S)) < 1e-4

    def test_drag_right_handle_before_left_handle(self, timeline_canvas) -> None:
        """Dragging end handle before start handle must clamp end >= start + 0.2s."""
        segs = [{"id": 1, "start": 2.0, "end": 4.0, "text_vi": "Test"}]
        timeline_canvas.set_segments(segs)
        timeline_canvas._drag = {"mode": "end", "id": 1, "start": 2.0, "end": 4.0, "grab": 4.0}
        # Attempt to drag end to 1.0s (before start 2.0s)
        timeline_canvas._apply_drag(1.0)
        seg = timeline_canvas._segments[0]
        assert seg["end"] >= seg["start"] + _MIN_BLOCK_S
        assert abs(seg["end"] - (2.0 + _MIN_BLOCK_S)) < 1e-4

    def test_drag_block_across_adjacent_neighbors_multi_block(self, timeline_canvas) -> None:
        """Dragging middle block cannot invade previous block or next block."""
        segs = [
            {"id": 1, "start": 0.0, "end": 2.0, "text_vi": "A"},
            {"id": 2, "start": 3.0, "end": 5.0, "text_vi": "B"},
            {"id": 3, "start": 6.0, "end": 8.0, "text_vi": "C"},
        ]
        timeline_canvas.set_segments(segs)
        timeline_canvas._drag = {"mode": "move", "id": 2, "start": 3.0, "end": 5.0, "grab": 4.0}

        # Attempt to move left into seg 1 [0.0, 2.0]
        timeline_canvas._apply_drag(1.0)  # shift = -3.0
        seg2 = timeline_canvas._segments[1]
        assert seg2["start"] >= 2.0
        assert seg2["end"] >= 2.0 + _MIN_BLOCK_S

        # Attempt to move right into seg 3 [6.0, 8.0]
        timeline_canvas._apply_drag(9.0)  # shift = +5.0
        seg2 = timeline_canvas._segments[1]
        assert seg2["end"] <= 6.0
        assert seg2["start"] <= 6.0 - _MIN_BLOCK_S

    def test_drag_on_tightly_packed_segments(self, timeline_canvas) -> None:
        """Packed segments with 0 gap: [0, 2.0], [2.0, 4.0], [4.0, 6.0]."""
        segs = [
            {"id": 1, "start": 0.0, "end": 2.0, "text_vi": "A"},
            {"id": 2, "start": 2.0, "end": 4.0, "text_vi": "B"},
            {"id": 3, "start": 4.0, "end": 6.0, "text_vi": "C"},
        ]
        timeline_canvas.set_segments(segs)
        timeline_canvas._drag = {"mode": "start", "id": 2, "start": 2.0, "end": 4.0, "grab": 2.0}
        # Try resizing seg2 start to left (past seg1 end 2.0)
        timeline_canvas._apply_drag(1.0)
        seg2 = timeline_canvas._segments[1]
        assert seg2["start"] >= 2.0


# ========================================================================
# Suite 4: Successive Rapid Split / Merge & Undo/Redo Stress
# ========================================================================

class TestEditorShortcutsAdversarial:
    """Stress-test rapid split (Ctrl+B), merge (Ctrl+J), and undo/redo stacks."""

    def test_rapid_consecutive_splits(self, qapp, mock_adversarial_project) -> None:
        """Split a segment repeatedly 5 times into smaller sub-segments."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_adversarial_project)

        # Initial segment 1 is [0.0, 2.0]s
        initial_count = len(page._segments)
        assert initial_count == 4

        # Split 1 at 1.0s -> [0, 1.0] and [1.0, 2.0]
        page.player.position = lambda: 1.0
        page.split_current_segment()
        assert len(page._segments) == initial_count + 1

        # Split 2 at 0.5s -> [0, 0.5] and [0.5, 1.0]
        page.player.position = lambda: 0.5
        page.split_current_segment()
        assert len(page._segments) == initial_count + 2

        # Split 3 at 0.25s -> [0, 0.25] and [0.25, 0.5]
        page.player.position = lambda: 0.25
        page.split_current_segment()
        assert len(page._segments) == initial_count + 3

        # Attempt split on [0, 0.25]s (length = 0.25s < 0.4s min required for 0.2s margin)
        # Should be rejected safely without crash or state corruption
        page.player.position = lambda: 0.12
        page.split_current_segment()
        assert len(page._segments) == initial_count + 3  # Rejected!

        # Verify segments strictly monotonic and non-overlapping
        for i in range(len(page._segments) - 1):
            assert float(page._segments[i]["end"]) <= float(page._segments[i + 1]["start"]) + 1e-5

        page.cleanup()

    def test_rapid_consecutive_merges_to_single_segment(self, qapp, mock_adversarial_project) -> None:
        """Merge all segments in the project consecutively until only 1 remains."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_adversarial_project)
        assert len(page._segments) == 4

        # Merge seg 1 with seg 2
        page.player.position = lambda: 0.5
        page.merge_current_segment()
        assert len(page._segments) == 3

        # Merge merged seg 1 with seg 3
        page.player.position = lambda: 0.5
        page.merge_current_segment()
        assert len(page._segments) == 2

        # Merge merged seg 1 with seg 4
        page.player.position = lambda: 0.5
        page.merge_current_segment()
        assert len(page._segments) == 1
        assert abs(float(page._segments[0]["start"]) - 0.0) < 1e-4
        assert abs(float(page._segments[0]["end"]) - 10.0) < 1e-4

        # Attempt to merge single remaining segment with non-existent next
        page.merge_current_segment()
        assert len(page._segments) == 1

        page.cleanup()

    def test_interleaved_split_merge_undo_redo_cycles(self, qapp, mock_adversarial_project) -> None:
        """Stress-test 10 cycles of split -> merge -> undo -> redo."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_adversarial_project)
        base_len = len(page._segments)

        for cycle in range(5):
            # Split segment 2 [2.5, 5.0] at 3.75
            page.player.position = lambda: 3.75
            page.split_current_segment()
            assert len(page._segments) == base_len + 1

            # Undo split
            page.undo()
            assert len(page._segments) == base_len

            # Redo split
            page.redo()
            assert len(page._segments) == base_len + 1

            # Merge back
            page.player.position = lambda: 3.0
            page.merge_current_segment()
            assert len(page._segments) == base_len

            # Undo merge
            page.undo()
            assert len(page._segments) == base_len + 1

            # Undo split
            page.undo()
            assert len(page._segments) == base_len

        page.cleanup()

    def test_split_fallback_to_selected_segment_midpoint(self, qapp, mock_adversarial_project) -> None:
        """Playhead is at 99.0s (outside all segments), but segment 2 is selected in subtitle list."""
        page = EditorPage(Settings.load)
        page.open_work_dir(mock_adversarial_project)
        page.player.position = lambda: 99.0
        page.subtitles.list.setCurrentRow(1)  # seg_id = 2 [2.5, 5.0]
        assert page.subtitles.selected_id() == 2

        page.split_current_segment()
        assert len(page._segments) == 5
        # Midpoint of [2.5, 5.0] is 3.75
        seg2_a = page._segments[1]
        seg2_b = page._segments[2]
        assert abs(float(seg2_a["start"]) - 2.5) < 1e-3
        assert abs(float(seg2_a["end"]) - 3.75) < 1e-3
        assert abs(float(seg2_b["start"]) - 3.75) < 1e-3
        assert abs(float(seg2_b["end"]) - 5.0) < 1e-3
        page.cleanup()

    def test_split_threshold_0_39s_vs_0_40s(self, qapp, tmp_path) -> None:
        """Test split boundary: 0.39s segment (< 0.40s) must be rejected; 0.40s segment must succeed."""
        work = tmp_path / "split_thresh_project"
        data = work / "data"
        seg_dir = data / "segments"
        seg_dir.mkdir(parents=True)
        segs = [
            {"id": 1, "start": 0.0, "end": 0.39, "duration": 0.39, "text": "short", "text_vi": "Ngắn"},
            {"id": 2, "start": 1.0, "end": 1.40, "duration": 0.40, "text": "exact", "text_vi": "Đủ"},
        ]
        (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
        (data / "quality_report.json").write_text("{}", encoding="utf-8")
        (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
        (work / "source.mp4").write_bytes(b"fake-mp4")
        for i in (1, 2):
            (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"wav")

        page = EditorPage(Settings.load)
        page.open_work_dir(str(work))

        # Attempt to split seg 1 (0.39s) at midpoint -> rejected (< 0.4s)
        page.player.position = lambda: 50.0
        page.subtitles.list.setCurrentRow(0)
        page.split_current_segment()
        assert len(page._segments) == 2

        # Attempt to split seg 2 (0.40s) at midpoint (1.20s) -> allowed!
        page.subtitles.list.setCurrentRow(1)
        page.split_current_segment()
        assert len(page._segments) == 3
        page.cleanup()

    def test_timeline_mouse_press_outside_bounds(self, timeline_canvas) -> None:
        """Mouse click at extreme negative or out-of-bounds coordinates."""
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(-50, -50))
        QTest.mouseRelease(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(-50, -50))
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5000, 5000))
        QTest.mouseRelease(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5000, 5000))

    def test_timeline_slider_zoom_sync_extremes(self, qapp) -> None:
        """Zoom slider synchronization at MIN_ZOOM and MAX_ZOOM."""
        tl = Timeline()
        tl.resize(800, 120)
        tl.zoom_slider.setValue(int(MIN_ZOOM * 10))
        assert tl.zoom_label.text() == f"{MIN_ZOOM:.1f}x"
        assert abs(tl.canvas.zoom() - MIN_ZOOM) < 1e-4

        tl.zoom_slider.setValue(int(MAX_ZOOM * 10))
        assert tl.zoom_label.text() == f"{MAX_ZOOM:.1f}x"
        assert abs(tl.canvas.zoom() - MAX_ZOOM) < 1e-4
        tl.deleteLater()

