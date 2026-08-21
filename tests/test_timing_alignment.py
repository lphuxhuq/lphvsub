"""Comprehensive test suite for timing alignment and sync engine (autodub.media.timing & autodub.media.retime)."""
import pytest
from autodub.media.timing import plan_placements, TimingReport
from autodub.media.retime import rescale_segments, rescale_blur_regions


def test_empty_segments():
    placements, report = plan_placements([], [])
    assert placements == []
    assert report.segments_total == 0
    assert report.segments_shifted == 0
    assert report.segments_compressed == 0
    assert report.segments_overlapped == 0


def test_single_segment_zero_duration():
    segs = [{"id": 1, "start": 5.0, "end": 8.0}]
    placements, report = plan_placements(segs, [0.0])
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
    placements, report = plan_placements(
        segs, durations, max_drift_s=1.5, min_gap_s=0.1, max_atempo=1.1
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


def test_rescale_blur_regions():
    regions = [
        {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "t_start": 2.0, "t_end": 5.0},
        {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},  # Static region
    ]
    rescaled = rescale_blur_regions(regions, scale=1.5)
    assert rescaled[0]["t_start"] == 3.0
    assert rescaled[0]["t_end"] == 7.5
    assert "t_start" not in rescaled[1]
