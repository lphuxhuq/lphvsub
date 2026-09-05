import pytest
import os
import re

from autodub.text.srt import generate_srt
from autodub.media.timing import plan_voice_placements, apply_soft_timing
from autodub.config import Settings


def _parse_srt_cues(srt_content: str):
    pattern = re.compile(
        r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)',
        re.DOTALL
    )
    matches = pattern.findall(srt_content)
    def ts_to_sec(ts):
        h, m, s = ts.split(':')
        s, ms = s.split(',')
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
    return [(ts_to_sec(m[1]), ts_to_sec(m[2]), m[3].strip()) for m in matches]


def test_generate_srt_never_has_overlapping_cues(tmp_path):
    """Bảo đảm tệp .srt sinh ra không bao giờ có 2 cue phụ đề bị chồng thời gian."""
    # Giả lập 2 segment có mốc bị chồng lấn (segment 1 kết thúc ở 3.5s, segment 2 bắt đầu ở 3.2s)
    segments = [
        {"id": 1, "start": 0.0, "end": 3.5, "text": "Câu thứ nhất rất dài và nhiều chữ"},
        {"id": 2, "start": 3.2, "end": 5.0, "text": "Câu thứ hai bắt đầu sớm"},
    ]
    out_srt = str(tmp_path / "test_no_overlap.srt")
    generate_srt(segments, out_srt)

    with open(out_srt, "r", encoding="utf-8") as f:
        content = f.read()

    cues = _parse_srt_cues(content)
    assert len(cues) >= 2

    for i in range(len(cues) - 1):
        cur_start, cur_end, cur_text = cues[i]
        nxt_start, nxt_end, nxt_text = cues[i + 1]
        assert cur_end <= nxt_start, (
            f"Phụ đề bị chồng: Cue {i+1} kết thúc lúc {cur_end}s "
            f"nhưng Cue {i+2} đã bắt đầu lúc {nxt_start}s"
        )


def test_apply_soft_timing_prevents_voice_and_sub_overlap(tmp_path):
    """Bảo đảm apply_soft_timing gán mốc start của câu sau không bao giờ nhỏ hơn end của câu trước."""
    # Tạo 2 file wav giả lập
    src_dir = str(tmp_path / "segments")
    dst_dir = str(tmp_path / "segments_speed")
    os.makedirs(src_dir, exist_ok=True)

    from tests.test_timing import _write_tone
    # Clip 1 dài 3.0s, Clip 2 dài 2.0s
    _write_tone(os.path.join(src_dir, "seg_00001.wav"), 3.0)
    _write_tone(os.path.join(src_dir, "seg_00002.wav"), 2.0)

    # Segment 1 gốc từ 0.0 -> 2.0, Segment 2 gốc từ 2.2 -> 4.2
    # TTS của Seg 1 dài 3.0s (vượt quá slot 2.0s và khoảng cách 2.2s)
    segments = [
        {"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0, "speech_start": 0.0, "speech_end": 2.0},
        {"id": 2, "start": 2.2, "end": 4.2, "duration": 2.0, "speech_start": 2.2, "speech_end": 4.2},
    ]

    settings = Settings()
    settings.timing_max_start_drift_s = 0.15
    settings.voice_fit_max_speed = 1.15

    out_dir, report = apply_soft_timing(segments, src_dir, dst_dir, settings)

    # Invariant: Câu 2 không bao giờ bắt đầu trước khi câu 1 kết thúc
    assert segments[1]["start"] >= segments[0]["end"], (
        f"Chồng tiếng/sub: Seg 1 kết thúc lúc {segments[0]['end']}s "
        f"nhưng Seg 2 bắt đầu lúc {segments[1]['start']}s"
    )


def test_merge_segments_prevents_voice_overlap(tmp_path):
    """Kiểm tra merge_segments tự động bảo vệ không cộng đè 2 clip tiếng nói nếu mốc đầu vào bị chồng."""
    from autodub.media.audio import merge_segments, wav_duration_s
    from tests.test_timing import _write_tone

    seg_dir = str(tmp_path / "raw_segs")
    os.makedirs(seg_dir, exist_ok=True)
    _write_tone(os.path.join(seg_dir, "seg_00001.wav"), 2.0)
    _write_tone(os.path.join(seg_dir, "seg_00002.wav"), 2.0)

    # Đầu vào cố tình bị lỗi chồng mốc (seg 1 từ 0-2s, seg 2 bắt đầu từ 1.0s)
    segments = [
        {"id": 1, "start": 0.0, "end": 2.0},
        {"id": 2, "start": 1.0, "end": 3.0},
    ]

    out_wav = str(tmp_path / "merged_out.wav")
    merge_segments(segments, seg_dir, out_wav, total_duration=6.0)

    assert os.path.exists(out_wav)
    # File ra phải có thời lượng đủ cho cả 2 clip tuần tự (ít nhất 4.0s)
    assert wav_duration_s(out_wav) >= 4.0


def test_sanitize_srt_file(tmp_path):
    """Bảo đảm sanitize_srt_file sửa các file SRT đã bị chồng cue trên đĩa thành chuẩn không chồng."""
    from autodub.text.srt import sanitize_srt_file

    bad_srt = tmp_path / "bad.srt"
    bad_srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nCâu 1 dài\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\nCâu 2 bị đè lên câu 1 500ms\n\n",
        encoding="utf-8"
    )

    fixed = sanitize_srt_file(str(bad_srt))
    assert fixed == 1

    content = bad_srt.read_text(encoding="utf-8")
    cues = _parse_srt_cues(content)
    assert len(cues) == 2
    assert cues[0][1] <= cues[1][0]  # Cue 1 end <= Cue 2 start

