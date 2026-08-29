import pytest
from autodub.media.scene_detector import parse_scene_cut_timestamps, find_next_scene_boundary
from autodub.media.timing import plan_voice_placements

def test_parse_scene_cut_timestamps():
    sample_ffmpeg_output = """
[Parsed_select_0 @ 000001] n:45 pts:45045 pts_time:1.5015 pos:1234
[Parsed_select_0 @ 000001] n:120 pts:120120 pts_time:4.004 pos:5678
[Parsed_select_0 @ 000001] n:250 pts:250250 pts_time:8.34167 pos:9012
"""
    cuts = parse_scene_cut_timestamps(sample_ffmpeg_output)
    assert len(cuts) == 3
    assert abs(cuts[0] - 1.5015) < 0.001
    assert abs(cuts[1] - 4.004) < 0.001
    assert abs(cuts[2] - 8.34167) < 0.001

def test_find_next_scene_boundary():
    cuts = [2.5, 5.0, 9.0]
    assert find_next_scene_boundary(1.0, cuts) == 2.5
    assert find_next_scene_boundary(2.6, cuts) == 5.0
    assert find_next_scene_boundary(9.5, cuts) is None

def test_plan_voice_placements_with_scene_cuts():
    # Clip start 1.0, speech duration 2.0s (tới 3.0s). Có scene cut ở 3.2s.
    # Clip duration TTS dài 2.5s. Thay vì tràn qua 3.5s, scheduler sẽ fit/nén để không vượt qua 3.2s - margin.
    segments = [{"start": 1.0, "end": 3.0, "speech_duration": 2.0}]
    durations = [2.4]
    scene_cuts = [3.1]
    
    placements, report = plan_voice_placements(
        segments, durations, scene_cuts=scene_cuts, max_speed=1.25
    )
    assert len(placements) == 1
    # Điểm kết thúc của câu phải trước hoặc tại scene cut
    dub_end = placements[0]["start"] + durations[0] / placements[0]["atempo"]
    assert dub_end <= 3.101
