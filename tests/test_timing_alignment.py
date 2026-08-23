"""Comprehensive test suite for timing alignment and sync engine (autodub.media.timing & autodub.media.retime)."""
import pytest
from autodub.media.timing import plan_voice_placements, TimingReport
from autodub.media.retime import rescale_segments, rescale_blur_regions


def test_empty_segments():
    placements, report = plan_voice_placements([], [])
    assert placements == []
    assert report.segments_total == 0
    assert report.segments_shifted == 0
    assert report.segments_compressed == 0
    assert report.segments_overlapped == 0


def test_single_segment_zero_duration():
    segs = [{"id": 1, "start": 5.0, "end": 8.0}]
    placements, report = plan_voice_placements(segs, [0.0])
    assert len(placements) == 1
    assert placements[0]["start"] == 5.0
    assert placements[0]["atempo"] == 1.0
    assert report.segments_total == 1


def test_consecutive_extreme_overlaps_detail_logging():
    # 4 segments spaced by 1s, each audio is 4s
    segs = [
        {"id": 10, "start": 0.0, "end": 1.0},
        {"id": 20, "start": 1.0, "end": 2.0},
        {"id": 30, "start": 2.0, "end": 3.0},
        {"id": 40, "start": 3.0, "end": 4.0},
    ]
    durations = [4.0, 4.0, 4.0, 4.0]
    placements, report = plan_voice_placements(
        segs, durations, max_start_drift_s=0.15, min_gap_s=0.1,
        max_speed=1.1
    )

    assert report.segments_total == 4
    assert report.segments_shifted > 0
    assert report.segments_compressed > 0
    assert report.segments_overlapped > 0
    assert report.total_overlap_s > 0
    assert len(report.details) > 0

    # Ensure all detail records have valid segment ids
    for d in report.details:
        assert d["id"] in [10, 20, 30, 40]
        if "overlap_prev_s" in d:
            assert d["overlap_prev_s"] > 0
        if "shift_s" in d:
            assert d["shift_s"] > 0


def test_rescale_segments_precision():
    segs = [
        {"id": 1, "start": 1.000, "end": 3.500, "duration": 2.500},
        {"id": 2, "start": 4.000, "end": 8.123, "duration": 4.123},
    ]
    rescale_segments(segs, scale=1.2)
    assert segs[0]["start"] == 1.2
    assert segs[0]["end"] == 4.2
    assert segs[0]["duration"] == 3.0
    assert segs[1]["start"] == 4.8
    assert segs[1]["end"] == round(8.123 * 1.2, 3)


def test_rescale_segments_scales_speech_fields():
    # av-desync-videospeed: field speech_*/vad_* phải đi theo cùng timeline
    # làm chậm, không thì scheduler đặt giọng theo mốc cũ → lệch hình.
    scale = 1.0 / 0.92
    segs = [
        {"id": 1, "start": 0.2, "end": 4.4, "duration": 4.2,
         "speech_start": 0.156, "speech_end": 4.396,
         "speech_duration": 4.24,
         "vad_start": 0.2, "vad_end": 4.4},
        {"id": 2, "start": 5.3, "end": 6.4, "duration": 1.1},  # transcript cũ
    ]
    rescale_segments(segs, scale)
    assert segs[0]["speech_start"] == round(0.156 * scale, 3)
    assert segs[0]["speech_end"] == round(4.396 * scale, 3)
    assert segs[0]["speech_duration"] == round(4.24 * scale, 3)
    assert segs[0]["vad_start"] == round(0.2 * scale, 3)
    assert segs[0]["vad_end"] == round(4.4 * scale, 3)
    # Segment không có field voice-sync → behavior cũ y nguyên
    assert "speech_start" not in segs[1]
    assert segs[1]["start"] == round(5.3 * scale, 3)
    assert segs[1]["duration"] == round(segs[1]["end"] - segs[1]["start"], 3)


def test_voice_placements_follow_rescaled_speech_timeline():
    # Regression av-desync-videospeed: VIDEO_SPEED=0.92 — dub onset phải là
    # speech_start ĐÃ rescale (~0.170), không rơi về 0.156 của timeline gốc.
    scale = 1.0 / 0.92
    segs = [{"id": 1, "start": 0.2, "end": 4.4, "duration": 4.2,
             "speech_start": 0.156, "speech_end": 4.396,
             "speech_duration": 4.24}]
    rescale_segments(segs, scale)
    placements, _report = plan_voice_placements(segs, [3.218])
    assert placements[0]["start"] == pytest.approx(0.156 * scale, abs=0.002)
    assert placements[0]["start"] > 0.169  # không về mốc timeline gốc 0.156


def test_rescale_blur_regions():
    regions = [
        {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "t_start": 2.0, "t_end": 5.0},
        {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},  # Static region
    ]
    rescaled = rescale_blur_regions(regions, scale=1.5)
    assert rescaled[0]["t_start"] == 3.0
    assert rescaled[0]["t_end"] == 7.5
    assert "t_start" not in rescaled[1]


def test_voice_placements_stretch_opt_in():
    """VOICE_FIT_STRETCH: clip ngắn hơn slot được kéo dài chặn 0.90, mặc định thì không."""
    seg = {"id": 1, "start": 0.2, "end": 4.4, "duration": 4.2,
           "speech_start": 0.156, "speech_end": 4.396,
           "speech_duration": 4.24}

    placements_off, rep_off = plan_voice_placements([dict(seg)], [3.218])
    assert placements_off[0]["atempo"] == 1.0
    assert placements_off[0]["adjustment"] == "none"
    assert rep_off.segments_stretched == 0

    placements_on, rep_on = plan_voice_placements(
        [dict(seg)], [3.218], min_speed=0.90, max_speed=1.15,
        allow_stretch=True)
    # 3.218/4.24 = 0.759 → chặn tại floor 0.90 (đọc chậm thêm ~11%)
    assert abs(placements_on[0]["atempo"] - 0.90) < 0.001
    assert placements_on[0]["adjustment"] == "stretch"
    assert rep_on.segments_stretched == 1
