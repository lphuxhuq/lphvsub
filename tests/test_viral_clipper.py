import pytest
from unittest.mock import MagicMock
from autodub.content.viral_clipper import (
    snap_to_segment_boundaries,
    heuristic_viral_analysis,
    analyze_viral_highlights,
)


def _mock_segments():
    return [
        {"id": 1, "start": 0.0, "end": 5.0, "text": "Xin chào các bạn đã quay trở lại với kênh.", "speaker": "SPEAKER_00"},
        {"id": 2, "start": 5.2, "end": 12.0, "text": "Hôm nay chúng ta sẽ khám phá một bí mật kinh hoàng.", "speaker": "SPEAKER_00"},
        {"id": 3, "start": 12.5, "end": 22.0, "text": "Kẻ đứng sau toàn bộ âm mưu này chính là người bạn thân nhất.", "speaker": "SPEAKER_01"},
        {"id": 4, "start": 22.5, "end": 35.0, "text": "Không ai có thể ngờ được một cú lật mặt sốc và bất ngờ đến thế.", "speaker": "SPEAKER_01"},
        {"id": 5, "start": 35.5, "end": 48.0, "text": "Hắn ta đã lấy hết số tiền và bỏ trốn trong sự tuyệt vọng của mọi người.", "speaker": "SPEAKER_00"},
        {"id": 6, "start": 48.5, "end": 60.0, "text": "Liệu công lý có được thực thi hay kẻ ác sẽ thoát tội?", "speaker": "SPEAKER_00"},
        {"id": 7, "start": 60.5, "end": 75.0, "text": "Hãy theo dõi diễn biến tiếp theo trong video này nhé.", "speaker": "SPEAKER_00"},
    ]


def test_snap_to_segment_boundaries():
    segments = _mock_segments()
    # Requested range 6.0 -> 40.0 (~34s)
    start_s, end_s, start_idx, end_idx = snap_to_segment_boundaries(
        6.0, 40.0, segments, min_duration=20.0, max_duration=65.0
    )
    # Segment 2 starts at 5.2, Segment 5 ends at 48.0 or Segment 4 ends at 35.0
    assert start_s == 5.2
    assert start_idx == 1
    assert end_s == 48.0 or end_s == 35.0
    assert end_idx >= start_idx
    assert end_s - start_s >= 20.0


def test_heuristic_viral_analysis():
    segments = _mock_segments()
    clips = heuristic_viral_analysis(segments, video_title="Bí mật kinh hoàng", max_clips=3)
    assert len(clips) > 0
    for clip in clips:
        assert "title" in clip
        assert "start" in clip
        assert "end" in clip
        assert "duration" in clip
        assert "viral_score" in clip
        assert 1 <= clip["viral_score"] <= 100
        assert clip["duration"] >= 20.0


def test_analyze_viral_highlights_offline_fallback():
    segments = _mock_segments()
    # Empty settings / no client should fallback smoothly to heuristic
    clips = analyze_viral_highlights(segments, settings=None, video_title="Bí mật", max_clips=3)
    assert isinstance(clips, list)
    assert len(clips) > 0
    assert clips[0]["viral_score"] > 0


def test_analyze_viral_highlights_with_mock_ai(monkeypatch):
    segments = _mock_segments()

    mock_client = MagicMock()
    mock_ai_response = """
    [
      {
        "title": "Cú lật mặt kinh hoàng của người bạn thân",
        "hook_text": "Kẻ đứng sau toàn bộ âm mưu này...",
        "start": 5.2,
        "end": 48.0,
        "viral_score": 95,
        "reason": "Tình tiết kịch tính cao trào và sốc"
      }
    ]
    """
    mock_client.call_ai.return_value = mock_ai_response

    class MockSettings:
        pass

    monkeypatch.setattr(
        "autodub.text.translate_direct.get_direct_client",
        lambda settings: (mock_client, "gemini")
    )

    clips = analyze_viral_highlights(segments, settings=MockSettings(), video_title="Review Phim Hay", max_clips=2)
    assert len(clips) >= 1
    assert clips[0]["viral_score"] == 95
    assert "Cú lật mặt" in clips[0]["title"]
