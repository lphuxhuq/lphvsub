"""Comprehensive Test Suite for Milestone 1 (M1: Timeline Waveform UI Component & Shortcuts).

Covers:
- Group 1: Waveform Peak Extraction & Caching (autodub_gui/waveform.py)
- Group 2: Timeline Coordinate & Math (autodub_gui/video/timeline.py)
- Group 3: Subtitle Block Drag & Interaction (autodub_gui/video/timeline.py)
- Group 4: Shortcuts & EditorPage (autodub_gui/shortcuts.py, autodub_gui/pages/editor_page.py)
- Group 5: Headless & GUI Integration (autodub_gui/video/timeline.py, autodub_gui/pages/editor_page.py)
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
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from autodub.config import Settings
from autodub_gui import waveform
from autodub_gui.pages.editor_page import EditorPage
from autodub_gui.shortcuts import (
    EDITOR_SHORTCUTS,
    Shortcut,
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
    _snap,
)


def _write_pcm_wav(path, seconds=1.0, rate=8000, channels=1, width=2,
                   amplitude=0.5, silent_tail=0.0):
    """Helper creating synthetic PCM WAV file."""
    frames = int(rate * seconds)
    time = np.arange(frames) / rate
    signal = np.sin(2 * math.pi * 440 * time) * amplitude
    if silent_tail > 0:
        quiet_from = int(frames * (1 - silent_tail))
        signal[quiet_from:] = 0.0
    scale = np.iinfo(np.int16 if width == 2 else np.int32).max
    data = (signal * scale).astype(np.int16 if width == 2 else np.int32)
    if channels > 1:
        data = np.repeat(data[:, None], channels, axis=1).ravel()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(data.tobytes())
    return str(path)


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
def sample_segments():
    return [
        {"id": 1, "start": 1.0, "end": 3.0, "duration": 2.0, "text_vi": "Câu một"},
        {"id": 2, "start": 4.0, "end": 6.0, "duration": 2.0, "text_vi": "Câu hai"},
        {"id": 3, "start": 7.0, "end": 9.0, "duration": 2.0, "text_vi": "Câu ba"},
    ]


@pytest.fixture
def mock_editor_project(tmp_path):
    work = tmp_path / "test_m1_project"
    data = work / "data"
    seg_dir = data / "segments"
    seg_dir.mkdir(parents=True)
    segs = [
        {"id": 1, "start": 0.0, "end": 4.0, "duration": 4.0, "text": "seg1", "text_vi": "Câu thoại một"},
        {"id": 2, "start": 5.0, "end": 8.0, "duration": 3.0, "text": "seg2", "text_vi": "Câu thoại hai"},
    ]
    (data / "transcript_vi.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (data / "quality_report.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    (data / "audio_vi_full.wav").write_bytes(b"RIFF....WAVE")
    (work / "source.mp4").write_bytes(b"fake-mp4")
    for i in (1, 2):
        (seg_dir / f"seg_{i:05d}.wav").write_bytes(b"wav")
    return str(work)


@pytest.fixture
def editor_page(qapp, mock_editor_project):
    page = EditorPage(Settings.load)
    page.open_work_dir(mock_editor_project)
    yield page
    page.cleanup()

# ========================================================================
# Group 1: Waveform Peak Extraction & Caching
# =======================================================================

class TestWaveformExtractionAndCaching:
    """Unit tests for audio peak extraction and caching logic in autodub_gui/waveform.py."""

    def test_waveform_pcm16_extraction(self, tmp_path) -> None:
        path = _write_pcm_wav(tmp_path / "pcm16.wav", seconds=2.0, rate=8000, channels=1, width=2, amplitude=0.6)
        res = waveform.peaks(path, buckets=100)
        assert len(res) == 100
        assert all(0.0 <= v <= 1.0 for v in res)
        assert 0.58 <= max(res) <= 0.62

    def test_waveform_pcm32_extraction(self, tmp_path) -> None:
        path = _write_pcm_wav(tmp_path / "pcm32.wav", seconds=1.0, rate=16000, channels=1, width=4, amplitude=0.8)
        res = waveform.peaks(path, buckets=50)
        assert len(res) == 50
        assert 0.78 <= max(res) <= 0.82

    def test_waveform_stereo_averaging(self, tmp_path) -> None:
        rate = 8000
        frames = int(rate * 1.0)
        time = np.arange(frames) / rate
        left = np.sin(2 * math.pi * 440 * time) * 0.2
        right = np.sin(2 * math.pi * 440 * time) * 0.8
        stereo = np.column_stack((left, right))
        scale = np.iinfo(np.int16).max
        data = (stereo * scale).astype(np.int16).ravel()
        path = str(tmp_path / "stereo.wav")
        with wave.open(path, "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data.tobytes())
        res = waveform.peaks(path, buckets=40)
        assert len(res) == 40
        assert 0.45 <= max(res) <= 0.55

    def test_waveform_json_cache_lifecycle(self, tmp_path) -> None:
        path = _write_pcm_wav(tmp_path / "audio_vi_full.wav", seconds=1.0, amplitude=0.5)
        res1 = waveform.peaks(path, buckets=64)
        cache_file = tmp_path / waveform.CACHE_NAME
        assert cache_file.is_file()
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["src"] == "audio_vi_full.wav"
        assert data["n"] == 64
        assert len(data["peaks"]) == 64
        marker = [0.777] * 64
        data["peaks"] = marker
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        res2 = waveform.peaks(path, buckets=64)
        assert res2 == marker
        assert res1 != marker

    def test_waveform_cache_invalidation_on_mtime_change(self, tmp_path) -> None:
        path = _write_pcm_wav(tmp_path / "test_mtime.wav", seconds=1.0, amplitude=0.2)
        quiet = waveform.peaks(path, buckets=64)
        _write_pcm_wav(tmp_path / "test_mtime.wav", seconds=1.0, amplitude=0.9)
        os.utime(path, (2_000_000, 2_000_000))
        loud = waveform.peaks(path, buckets=64)
        assert max(loud) > max(quiet)

    def test_waveform_cache_invalidation_on_bucket_count_change(self, tmp_path) -> None:
        path = _write_pcm_wav(tmp_path / "test_buckets.wav", seconds=1.0)
        waveform.peaks(path, buckets=50)
        res2 = waveform.peaks(path, buckets=120)
        assert len(res2) == 120

    def test_waveform_multi_track_sources_and_cache_naming(self, tmp_path) -> None:
        assert waveform.cache_name_for("audio_vi_full.wav") == "waveform_peaks.json"
        assert waveform.cache_name_for("original_audio.wav") == "waveform_peaks_original_audio.json"
        assert waveform.cache_name_for("slowed_background.wav") == "waveform_peaks_slowed_background.json"

        work = tmp_path / "proj"
        data = work / "data"
        data.mkdir(parents=True)
        _write_pcm_wav(data / "original_audio.wav")
        _write_pcm_wav(data / "audio_vi_full.wav")
        _write_pcm_wav(data / "no_vocals.wav")
        sources = waveform.track_sources(str(work))
        assert "original" in sources
        assert "voice" in sources
        assert "music" in sources

    def test_waveform_clear_cache_removes_all_track_caches(self, tmp_path) -> None:
        work = tmp_path / "clear_proj"
        data = work / "data"
        data.mkdir(parents=True)
        (data / "waveform_peaks.json").write_text("{}", encoding="utf-8")
        (data / "waveform_peaks_original_audio.json").write_text("{}", encoding="utf-8")
        (data / "waveform_peaks_slowed_background.json").write_text("{}", encoding="utf-8")
        assert waveform.clear_cache(str(work)) is True
        assert not (data / "waveform_peaks.json").exists()
        assert not (data / "waveform_peaks_original_audio.json").exists()
        assert not (data / "waveform_peaks_slowed_background.json").exists()

    def test_waveform_error_handling_and_corrupted_files(self, tmp_path) -> None:
        assert waveform.peaks("nonexistent.wav") == []
        assert waveform.peaks("") == []
        fake = tmp_path / "fake.wav"
        fake.write_bytes(b"not a wav file content")
        assert waveform.peaks(str(fake)) == []
        wav_8bit = tmp_path / "eight_bit.wav"
        with wave.open(str(wav_8bit), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(1)
            out.setframerate(8000)
            out.writeframes(b"\x80" * 8000)
        assert waveform.peaks(str(wav_8bit)) == []
        valid = _write_pcm_wav(tmp_path / "valid.wav")
        assert waveform.peaks(valid, buckets=0) == []
        # Corrupted cache
        (tmp_path / waveform.CACHE_NAME).write_text("{ invalid json", encoding="utf-8")
        res = waveform.peaks(valid, buckets=64)
        assert len(res) == 64

# ========================================================================
# Group 2: Timeline Coordinate & Math
# =========================================================================

class TestTimelineCoordinateAndMath:
    """Tests for coordinate transformation, zooming, offset clamping, and snapping."""

    def test_timeline_geometry_and_content_width(self, timeline_canvas) -> None:
        timeline_canvas.resize(888, 200)
        assert timeline_canvas._content_w() == 800
        timeline_canvas.resize(488, 200)
        assert timeline_canvas._content_w() == 400

    def test_timeline_time_to_pixel_conversion(self, timeline_canvas) -> None:
        timeline_canvas.resize(888, 200)
        timeline_canvas.set_duration(10.0)
        timeline_canvas.set_zoom(1.0)
        assert abs(timeline_canvas._to_x(0.0) - 88.0) < 1e-4
        assert abs(timeline_canvas._to_x(5.0) - 488.0) < 1e-4
        assert abs(timeline_canvas._to_x(10.0) - 888.0) < 1e-4

    def test_timeline_pixel_to_time_conversion(self, timeline_canvas) -> None:
        timeline_canvas.resize(888, 200)
        timeline_canvas.set_duration(10.0)
        timeline_canvas.set_zoom(1.0)
        assert abs(timeline_canvas._to_time(88.0) - 0.0) < 1e-4
        assert abs(timeline_canvas._to_time(488.0) - 5.0) < 1e-4
        assert abs(timeline_canvas._to_time(888.0) - 10.0) < 1e-4
        assert abs(timeline_canvas._to_time(40.0) - 0.0) < 1e-4

    def test_timeline_coordinate_bijection_roundtrip(self, timeline_canvas) -> None:
        timeline_canvas.resize(888, 200)
        timeline_canvas.set_duration(10.0)
        for t in [0.0, 0.5, 1.25, 3.7, 8.9, 10.0]:
            assert abs(timeline_canvas._to_time(timeline_canvas._to_x(t)) - t) < 1e-5
        for x in [88.0, 150.0, 488.0, 720.0, 888.0]:
            assert abs(timeline_canvas._to_x(timeline_canvas._to_time(x)) - x) < 1e-5

    def test_timeline_snap_quantization(self) -> None:
        assert abs(_snap(0.0) - 0.0) < 1e-6
        assert abs(_snap(0.024) - 0.0) < 1e-6
        assert abs(_snap(0.026) - 0.05) < 1e-6
        assert abs(_snap(1.22) - 1.20) < 1e-6
        assert abs(_snap(1.23) - 1.25) < 1e-6
        assert abs(_snap(1.28) - 1.30) < 1e-6

    def test_timeline_zoom_clamping_and_bounds(self, timeline_canvas) -> None:
        assert abs(timeline_canvas.zoom() - 1.0) < 1e-6
        timeline_canvas.set_zoom(0.2)
        assert abs(timeline_canvas.zoom() - MIN_ZOOM) < 1e-6
        timeline_canvas.set_zoom(50.0)
        assert abs(timeline_canvas.zoom() - MAX_ZOOM) < 1e-6
        timeline_canvas.set_zoom(1.0)
        timeline_canvas.zoom_in()
        assert abs(timeline_canvas.zoom() - 1.25) < 1e-6
        timeline_canvas.zoom_out()
        assert abs(timeline_canvas.zoom() - 1.0) < 1e-6

    def test_timeline_zoom_anchor_centering(self, timeline_canvas) -> None:
        timeline_canvas.set_duration(20.0)
        timeline_canvas.set_zoom(2.0, anchor=8.0)
        assert abs(timeline_canvas._offset - 3.0) < 1e-5

    def test_timeline_offset_clamping(self, timeline_canvas) -> None:
        timeline_canvas.set_duration(10.0)
        timeline_canvas.set_zoom(2.0)
        timeline_canvas._offset = -3.0
        timeline_canvas._clamp_offset()
        assert abs(timeline_canvas._offset - 0.0) < 1e-6
        timeline_canvas._offset = 8.0
        timeline_canvas._clamp_offset()
        assert abs(timeline_canvas._offset - 5.0) < 1e-6

    def test_timeline_playhead_auto_scroll(self, timeline_canvas) -> None:
        timeline_canvas.set_duration(30.0)
        timeline_canvas.set_zoom(3.0)  # span = 10.0s
        timeline_canvas.set_position(5.0)
        assert abs(timeline_canvas._offset - 0.0) < 1e-6
        timeline_canvas.set_position(18.0)
        assert abs(timeline_canvas._offset - 13.0) < 1e-5

    def test_timeline_multitrack_height_and_visibility_toggle(self, tmp_path, timeline_canvas) -> None:
        assert timeline_canvas._band_kinds() == ["default"]
        assert timeline_canvas.wave_height() == BAND_H

        timeline_canvas.set_track_available("original", True)
        assert timeline_canvas.wave_height() == BAND_H
        timeline_canvas.set_track_available("voice", True)
        assert timeline_canvas.wave_height() == BAND_H * 2
        timeline_canvas.set_track_available("music", True)
        assert timeline_canvas.wave_height() == BAND_H * 3
        timeline_canvas.set_thumbnails([(0.0, "thumb.jpg")])
        assert timeline_canvas.wave_height() == BAND_H * 3 + THUMB_H
        timeline_canvas.toggle_track_visible("voice")
        assert timeline_canvas.wave_height() == BAND_H * 2 + THUMB_H

# ========================================================================
# Group 3: Subtitle Block Drag & Interaction
# ========================================================================

class TestSubtitleBlockDragAndInteraction:
    """Tests for mouse interactions, hit testing, drag modes, and boundary collisions."""

    def test_segment_hit_detection_and_edge_modes(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        y_track = int(RULER_H + BAND_H + 10)
        # Seg 1 [1.0, 3.0]s -> left=168, right=328, center=248
        seg = timeline_canvas._segment_at(168, y_track)
        assert seg is not None and seg["id"] == 1
        timeline_canvas._begin_drag(seg, 168)
        assert timeline_canvas._drag["mode"] == "start"
        timeline_canvas._begin_drag(seg, 328)
        assert timeline_canvas._drag["mode"] == "end"
        timeline_canvas._begin_drag(seg, 248)
        assert timeline_canvas._drag["mode"] == "move"
        assert timeline_canvas._segment_at(50, y_track) is None

    def test_drag_move_mode_shifts_position_with_snap(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas._drag = {"mode": "move", "id": 1, "start": 1.0, "end": 3.0, "grab": 2.0}
        timeline_canvas._apply_drag(2.53)
        seg1 = next(s for s in timeline_canvas._segments if s["id"] == 1)
        assert abs(seg1["start"] - 1.55) < 1e-4
        assert abs(seg1["end"] - 3.55) < 1e-4

    def test_drag_start_edge_resizes_left_boundary(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas._drag = {"mode": "start", "id": 1, "start": 1.0, "end": 3.0, "grab": 1.0}
        timeline_canvas._apply_drag(1.48)
        seg1 = next(s for s in timeline_canvas._segments if s["id"] == 1)
        assert abs(seg1["start"] - 1.50) < 1e-4
        assert abs(seg1["end"] - 3.0) < 1e-4

    def test_drag_end_edge_resizes_right_boundary(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas._drag = {"mode": "end", "id": 1, "start": 1.0, "end": 3.0, "grab": 3.0}
        timeline_canvas._apply_drag(3.42)
        seg1 = next(s for s in timeline_canvas._segments if s["id"] == 1)
        assert abs(seg1["start"] - 1.0) < 1e-4
        assert abs(seg1["end"] - 3.40) < 1e-4

    def test_drag_minimum_block_duration_enforced(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas._drag = {"mode": "start", "id": 1, "start": 1.0, "end": 3.0, "grab": 1.0}
        timeline_canvas._apply_drag(3.5)
        seg1 = next(s for s in timeline_canvas._segments if s["id"] == 1)
        assert abs(seg1["start"] - 2.80) < 1e-4
        timeline_canvas._drag = {"mode": "end", "id": 1, "start": 1.0, "end": 3.0, "grab": 3.0}
        timeline_canvas._apply_drag(0.5)
        seg1 = next(s for s in timeline_canvas._segments if s["id"] == 1)
        assert abs(seg1["end"] - 1.20) < 1e-4

    def test_drag_neighbor_collision_clamping(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        s, e = timeline_canvas._limit_to_neighbours(2, 6.0, 8.0)
        assert abs(e - 7.0) < 1e-4 and abs(s - 6.0) < 1e-4
        s, e = timeline_canvas._limit_to_neighbours(2, 2.0, 4.0)
        assert abs(s - 3.0) < 1e-4 and abs(e - 5.0) < 1e-4
        s, e = timeline_canvas._limit_to_neighbours(1, -2.0, 0.0)
        assert abs(s - 0.0) < 1e-4
        s, e = timeline_canvas._limit_to_neighbours(3, 9.0, 11.0)
        assert abs(e - 10.0) < 1e-4

    def test_drag_mouse_release_emits_segment_moved_signal(self, timeline_canvas, sample_segments, qtbot) -> None:
        timeline_canvas.set_segments(sample_segments)
        emitted = []
        timeline_canvas.segment_moved.connect(lambda sid, s, e: emitted.append((sid, s, e)))
        y_track = int(RULER_H + BAND_H + 10)
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(248, y_track))
        QTest.mouseMove(timeline_canvas, QPoint(288, y_track))
        QTest.mouseRelease(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(288, y_track))
        assert len(emitted) == 1
        assert emitted[0][0] == 1
        assert abs(emitted[0][1] - 1.5) < 1e-3
        assert abs(emitted[0][2] - 3.5) < 1e-3

    def test_drag_zero_movement_does_not_emit_signal(self, timeline_canvas, sample_segments, qtbot) -> None:
        timeline_canvas.set_segments(sample_segments)
        emitted = []
        timeline_canvas.segment_moved.connect(lambda *a: emitted.append(a))
        y_track = int(RULER_H + BAND_H + 10)
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(248, y_track))
        QTest.mouseRelease(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(248, y_track))
        assert len(emitted) == 0

    def test_scissors_mode_split_requested_signal(self, timeline_canvas, sample_segments, qtbot) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas.set_scissors(True)
        emitted = []
        timeline_canvas.split_requested.connect(lambda sid, t: emitted.append((sid, t)))
        y_track = int(RULER_H + BAND_H + 10)
        x = int(timeline_canvas._to_x(2.5))
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y_track))
        assert len(emitted) == 1
        assert emitted[0][0] == 1
        assert abs(emitted[0][1] - 2.5) < 1e-3

    def test_timeline_range_selection_shift_drag(self, timeline_canvas, qtbot) -> None:
        emitted = []
        timeline_canvas.selection_changed.connect(lambda s, e: emitted.append((s, e)))
        x_start = int(timeline_canvas._to_x(2.0))
        x_end = int(timeline_canvas._to_x(5.0))
        QTest.mousePress(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x_start, 10))
        QTest.mouseMove(timeline_canvas, QPoint(x_end, 10))
        QTest.mouseRelease(timeline_canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x_end, 10))
        sel = timeline_canvas.get_selection()
        assert sel is not None
        assert abs(sel[0] - 2.0) < 1e-3
        assert abs(sel[1] - 5.0) < 1e-3
        assert len(emitted) == 1
        timeline_canvas.clear_selection()
        assert timeline_canvas.get_selection() is None

# ========================================================================
# Group 4: Shortcuts & EditorPage Integration
# =======================================================================

class TestShortcutsAndEditorPage:
    """Tests for Ctrl+B, Ctrl+J shortcut registration, execution, and QUndoStack integration."""

    def test_shortcuts_registry_contains_m1_bindings(self) -> None:
        ctrl_b = [s_s for s_s in EDITOR_SHORTCUTS if s_s.keys == "Ctrl+B"]
        ctrl_j = [s_j for s_j in EDITOR_SHORTCUTS if s_j.keys == "Ctrl+J"]
        assert len(ctrl_b) == 1
        assert len(ctrl_j) == 1
        assert ctrl_b[0].scope == "Trình chỉnh sửa"
        assert ctrl_j[0].scope == "Trình chỉnh sửa"

    def test_install_editor_shortcuts_binds_to_page(self, qapp) -> None:
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
        created = install_editor_shortcuts(dummy)
        key_seqs = [sc.key().toString() for sc in created]
        assert "Ctrl+B" in key_seqs
        assert "Ctrl+J" in key_seqs
        assert "Ctrl+Z" in key_seqs
        assert "Ctrl+Shift+Z" in key_seqs
        dummy.deleteLater()

    def test_editor_page_split_current_segment_success(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 3
        assert abs(float(editor_page._segments[0]["end"]) - 2.0) < 1e-3
        assert abs(float(editor_page._segments[1]["start"]) - 2.0) < 1e-3
        assert abs(float(editor_page._segments[1]["end"]) - 4.0) < 1e-3
        assert abs(float(editor_page._segments[2]["start"]) - 5.0) < 1e-3

    def test_editor_page_split_near_edge_rejected_safely(self, editor_page) -> None:
        editor_page.player.position = lambda: 0.05
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 2

    def test_editor_page_split_outside_segment_rejected(self, editor_page) -> None:
        editor_page.player.position = lambda: 4.5
        editor_page.subtitles.list.setCurrentItem(None)
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 2

    def test_editor_page_merge_current_segment_success(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 1
        assert abs(float(editor_page._segments[0]["start"]) - 0.0) < 1e-3
        assert abs(float(editor_page._segments[0]["end"]) - 8.0) < 1e-3
        assert "Câu thoại một Câu thoại hai" in editor_page._segments[0]["text_vi"]

    def test_editor_page_merge_last_segment_rejected(self, editor_page) -> None:
        editor_page.player.position = lambda: 6.0
        editor_page.subtitles.list.setCurrentRow(1)
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 2

    def test_editor_undo_redo_split_and_merge(self, editor_page) -> None:
        editor_page.player.position = lambda: 2.0
        editor_page.split_current_segment()
        assert len(editor_page._segments) == 3
        editor_page.undo()
        assert len(editor_page._segments) == 2
        editor_page.redo()
        assert len(editor_page._segments) == 3
        editor_page.player.position = lambda: 1.0
        editor_page.merge_current_segment()
        assert len(editor_page._segments) == 2
        editor_page.undo()
        assert len(editor_page._segments) == 3

    def test_editor_undo_redo_timeline_block_move(self, editor_page) -> None:
        editor_page._on_segment_moved(1, 0.5, 4.5)
        assert abs(float(editor_page._segments[0]["start"]) - 0.5) < 1e-3
        assert abs(float(editor_page._segments[0]["end"]) - 4.5) < 1e-3
        editor_page.undo()
        assert abs(float(editor_page._segments[0]["start"]) - 0.0) < 1e-3
        assert abs(float(editor_page._segments[0]["end"]) - 4.0) < 1e-3
        editor_page.redo()
        assert abs(float(editor_page._segments[0]["start"]) - 0.5) < 1e-3
        assert abs(float(editor_page._segments[0]["end"]) - 4.5) < 1e-3

    def test_typing_in_text_field_protects_single_key_shortcuts(self, qapp) -> None:
        window = QWidget()
        edit = QLineEdit(window)
        other = QWidget(window)
        window.show()
        window.activateWindow()
        edit.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is True
        other.setFocus()
        qapp.processEvents()
        assert typing_in_text_field() is False
        window.deleteLater()

# ========================================================================
# Group 5: Headless & GUI Integration
# =========================================================================

class TestHeadlessAndGUIIntegration:
    """Tests for QPainter headless rendering, composite widget toolbar controls, and clean shutdown."""

    def test_timeline_paint_event_headless_rendering(self, timeline_canvas, sample_segments) -> None:
        timeline_canvas.set_segments(sample_segments)
        timeline_canvas.set_peaks([0.1, 0.5, 0.8, 0.3] * 25)
        timeline_canvas.set_position(2.5)
        timeline_canvas.set_selected(1)
        img = QImage(888, 200, QImage.Format.Format_ARGB32_Premultiplied)
        timeline_canvas.render(img)
        assert not img.isNull()

    def test_timeline_composite_widget_toolbar_controls(self, qapp) -> None:
        tl = Timeline()
        tl.resize(888, 120)
        assert tl.canvas._scissors is False
        tl.btn_scissors.click()
        assert tl.canvas._scissors is True
        tl.btn_scissors.click()
        assert tl.canvas._scissors is False
        tl.zoom_slider.setValue(25)
        assert abs(tl.canvas.zoom() - 2.5) < 1e-4
        assert tl.zoom_label.text() == "2.5x"
        tl._zoom_in()
        assert tl.canvas.zoom() > 2.5
        tl._zoom_out()
        tl.deleteLater()

    def test_editor_page_clean_shutdown_and_worker_termination(self, editor_page) -> None:
        editor_page.cleanup()
        assert editor_page._thumb_worker is None
        assert not editor_page.is_running()

