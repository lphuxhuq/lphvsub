import json
import pytest
from autodub.media.timing import build_timing_guide, save_timing_guide


def test_build_timing_guide_basic():
    segments = [
        {"id": 1, "text": "Hello world", "text_vi": "Xin chào thế giới", "start": 0.0, "end": 2.0, "duration": 2.0},
        {"id": 2, "text": "This is a long sentence", "text_vi": "Đây là một câu rất dài dài dài", "start": 2.5, "end": 4.5, "duration": 2.0},
        {"id": 3, "text": "Short", "text_vi": "Ngắn", "start": 5.0, "end": 7.0, "duration": 2.0},
    ]
    # seg 1: 2.0s -> diff 0.0 -> OK
    # seg 2: 3.5s -> diff +1.5s -> TOO_LONG
    # seg 3: 1.0s -> diff -1.0s -> TOO_SHORT
    durations = [2.0, 3.5, 1.0]

    guide = build_timing_guide(segments, durations, target_field="text_vi", source_url="https://youtu.be/123")

    summary = guide["summary"]
    assert summary["total_segments"] == 3
    assert summary["total_original_duration"] == 6.0
    assert summary["total_tts_duration"] == 6.5
    assert summary["segments_ok"] == 1
    assert summary["segments_need_edit"] == 2
    assert guide["source_url"] == "https://youtu.be/123"

    items = guide["segments"]
    assert len(items) == 3
    assert items[0]["status"] == "OK"
    assert items[0]["edit_hint"] == "OK"

    assert items[1]["status"] == "TOO_LONG"
    assert "Dài hơn 1.5s" in items[1]["edit_hint"]

    assert items[2]["status"] == "TOO_SHORT"
    assert "Ngắn hơn 1.0s" in items[2]["edit_hint"]


def test_build_timing_guide_empty_and_none():
    guide = build_timing_guide([], [])
    assert guide["summary"]["total_segments"] == 0
    assert guide["summary"]["segments_ok"] == 0
    assert guide["segments"] == []

    segments = [{"id": 1, "text": "Hi", "text_vi": "Chào", "start": 0.0, "end": 1.0, "duration": 1.0}]
    guide_none = build_timing_guide(segments, [None])
    assert guide_none["summary"]["total_segments"] == 1
    assert guide_none["segments"][0]["status"] == "OK"


def test_save_timing_guide(tmp_path):
    work_dir = str(tmp_path)
    segments = [{"id": 1, "text": "Test", "text_vi": "Thử nghiệm", "start": 0.0, "end": 1.0, "duration": 1.0}]
    guide = build_timing_guide(segments, [1.0])

    out_file = save_timing_guide(work_dir, guide)
    assert out_file.endswith("timing_report.json")

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["summary"]["total_segments"] == 1
    assert data["segments"][0]["text_target"] == "Thử nghiệm"
