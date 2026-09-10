"""Comprehensive tests for Phase 5: Timing Engine Invariants.

Guarantees:
- Every segment produces usable_end > usable_start (strictly positive duration).
- No scene cut can ever force usable_end <= usable_start.
- Invariants hold across:
  * scene cut immediately after start
  * scene cut immediately before end
  * adjacent segments
  * overlapping segments
  * multiple speakers
  * very short segments
"""
import pytest

from autodub.media.timing import plan_voice_placements


def _assert_invariants(placements):
    """Core invariants that must hold for ALL timing placements."""
    assert len(placements) > 0
    for i, p in enumerate(placements):
        start = p["start"]
        usable_end = p["usable_end"]
        available = p["available"]
        
        # Invariant 1: usable_end is strictly greater than start
        assert usable_end > start, f"Segment {i} violated invariant: usable_end ({usable_end}) <= start ({start})"
        
        # Invariant 2: available slot is strictly positive
        assert available is not None and available > 0, f"Segment {i} available slot must be > 0, got {available}"
        
        # Invariant 3: tempo factor is positive and finite
        assert p["atempo"] > 0, f"Segment {i} tempo must be > 0, got {p['atempo']}"


def test_scene_cut_immediately_after_start():
    """Scene cut occurs right at or 10ms after speech start (e.g. camera cut during speech onset)."""
    segments = [
        {"id": 1, "start": 2.0, "end": 4.0, "duration": 2.0},
        {"id": 2, "start": 5.0, "end": 7.0, "duration": 2.0},
    ]
    durations = [2.2, 1.9]
    # Scene cut occurs at 2.01s (just 10ms after segment 1 starts)
    scene_cuts = [1.0, 2.01, 8.0]

    placements, rep = plan_voice_placements(segments, durations, scene_cuts=scene_cuts)
    _assert_invariants(placements)
    assert placements[0]["usable_end"] > placements[0]["start"]


def test_scene_cut_immediately_before_end():
    """Scene cut occurs 10ms before expected segment end."""
    segments = [
        {"id": 1, "start": 2.0, "end": 4.0, "duration": 2.0},
    ]
    durations = [2.0]
    scene_cuts = [3.99]

    placements, rep = plan_voice_placements(segments, durations, scene_cuts=scene_cuts)
    _assert_invariants(placements)
    assert placements[0]["usable_end"] > placements[0]["start"]
    # Should clamp near 3.99 - 0.02 = 3.97
    assert placements[0]["usable_end"] <= 3.99


def test_scene_cut_exactly_at_start():
    """Scene cut occurs exactly on the segment start timestamp."""
    segments = [
        {"id": 1, "start": 5.0, "end": 6.5, "duration": 1.5},
    ]
    durations = [1.5]
    scene_cuts = [5.0]

    placements, rep = plan_voice_placements(segments, durations, scene_cuts=scene_cuts)
    _assert_invariants(placements)
    assert placements[0]["usable_end"] > placements[0]["start"]


def test_adjacent_segments():
    """Back-to-back contiguous segments with zero gap."""
    segments = [
        {"id": 1, "start": 1.0, "end": 2.0, "duration": 1.0},
        {"id": 2, "start": 2.0, "end": 3.0, "duration": 1.0},
        {"id": 3, "start": 3.0, "end": 4.0, "duration": 1.0},
    ]
    durations = [1.1, 1.0, 1.2]

    placements, rep = plan_voice_placements(segments, durations, min_gap_s=0.12)
    _assert_invariants(placements)


def test_overlapping_segments():
    """Overlapping segments (e.g. cross-talk or background voice)."""
    segments = [
        {"id": 1, "start": 1.0, "end": 2.5, "duration": 1.5},
        {"id": 2, "start": 1.8, "end": 3.2, "duration": 1.4},
        {"id": 3, "start": 2.9, "end": 4.0, "duration": 1.1},
    ]
    durations = [1.6, 1.5, 1.2]

    placements, rep = plan_voice_placements(segments, durations)
    _assert_invariants(placements)


def test_multiple_speakers():
    """Multiple speakers with varying pauses, rapid turns, and scene changes."""
    segments = [
        {"id": 1, "speaker": "SPEAKER_00", "start": 0.5, "end": 1.8, "duration": 1.3},
        {"id": 2, "speaker": "SPEAKER_01", "start": 1.82, "end": 2.4, "duration": 0.58},
        {"id": 3, "speaker": "SPEAKER_00", "start": 2.45, "end": 4.0, "duration": 1.55},
        {"id": 4, "speaker": "SPEAKER_02", "start": 4.05, "end": 5.2, "duration": 1.15},
    ]
    durations = [1.4, 0.7, 1.8, 1.2]
    scene_cuts = [1.83, 3.5, 4.06]

    placements, rep = plan_voice_placements(segments, durations, scene_cuts=scene_cuts)
    _assert_invariants(placements)


def test_very_short_segments():
    """Micro segments (e.g. 'Oh!', 'Yeah', clicks, 50ms-150ms words)."""
    segments = [
        {"id": 1, "start": 1.0, "end": 1.08, "duration": 0.08},
        {"id": 2, "start": 1.2, "end": 1.25, "duration": 0.05},
        {"id": 3, "start": 1.5, "end": 1.65, "duration": 0.15},
    ]
    durations = [0.10, 0.08, 0.18]
    scene_cuts = [1.02, 1.21]

    placements, rep = plan_voice_placements(segments, durations, scene_cuts=scene_cuts)
    _assert_invariants(placements)
    for p in placements:
        assert p["usable_end"] - p["start"] >= 0.05
