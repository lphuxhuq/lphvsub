import os
import pytest
from autodub.media.clipper import (
    slice_ass_subtitles,
    build_short_export_command,
)


def test_slice_ass_subtitles():
    ass_sample = """[Script Info]
Title: Sample
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour
Style: Default, Arial, 20, &H00FFFFFF

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:02.00,0:00:06.00,Default,,0,0,0,,Câu số 1 ngoài dải trước
Dialogue: 0,0:00:10.00,0:00:15.00,Default,,0,0,0,,Câu số 2 trong dải
Dialogue: 0,0:00:18.00,0:00:22.50,Default,,0,0,0,,Câu số 3 trong dải
Dialogue: 0,0:00:45.00,0:00:50.00,Default,,0,0,0,,Câu số 4 ngoài dải sau
"""
    # Slice từ 8.0s đến 25.0s
    sliced = slice_ass_subtitles(ass_sample, start_time=8.0, end_time=25.0)
    assert "[Script Info]" in sliced
    assert "[V4+ Styles]" in sliced
    assert "[Events]" in sliced
    assert "Câu số 1 ngoài dải trước" not in sliced
    assert "Câu số 4 ngoài dải sau" not in sliced
    assert "Câu số 2 trong dải" in sliced
    assert "Câu số 3 trong dải" in sliced

    # Câu số 2 (gốc 10.0 -> 15.0) khi shift trừ 8.0s sẽ thành 2.0s -> 7.0s (0:00:02.00 -> 0:00:07.00)
    assert "0:00:02.00,0:00:07.00" in sliced
    # Câu số 3 (gốc 18.0 -> 22.5) khi shift trừ 8.0s sẽ thành 10.0s -> 14.5s (0:00:10.00 -> 0:00:14.50)
    assert "0:00:10.00,0:00:14.50" in sliced


def test_build_short_export_command():
    cmd = build_short_export_command(
        source_video="test_video.mp4",
        source_audio="test_audio.wav",
        ass_sub_path="sub_slice.ass",
        start_time=10.0,
        end_time=40.0,
        output_path="out_short.mp4",
        aspect_preset="tiktok_9_16",
        reframe_mode="blur",
    )
    assert isinstance(cmd, list)
    assert "ffmpeg" in cmd[0] or "ffmpeg" in cmd[0].lower()
    assert "-ss" in cmd
    assert "10.00" in cmd
    assert "-t" in cmd
    assert "30.00" in cmd
    assert "out_short.mp4" in cmd[-1]
