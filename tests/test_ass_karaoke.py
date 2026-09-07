"""Tests for karaoke subtitles: chunking, timing estimation, ASS output,
and the word-mapping half of forced alignment (no model needed).
"""
import math
import os
import struct
import wave

import pytest

from autodub.speech.align import _map_words
from autodub.text.ass_karaoke import (
    _ass_time,
    _escape_text,
    build_karaoke_ass,
    chunk_words,
    estimate_word_times,
)


# ------------------------------------------------------------ estimation --- #

def test_estimate_covers_full_duration():
    words = estimate_word_times("xin chào các bạn nhé", 10.0, 2.5)
    assert len(words) == 5
    assert words[0][1] == 10.0
    assert words[-1][2] == pytest.approx(12.5, abs=0.01)
    # Mốc đơn điệu, không chồng nhau
    for (_, s1, e1), (_, s2, _e2) in zip(words, words[1:]):
        assert e1 == pytest.approx(s2, abs=0.001)
        assert s1 < e1


def test_estimate_pause_weight_after_comma():
    # "một," được cộng trọng số nghỉ → dài hơn "hai"
    words = estimate_word_times("một, hai ba", 0.0, 3.0)
    d = {w: e - s for w, s, e in words}
    assert d["một,"] > d["hai"]


def test_estimate_empty_and_zero_duration():
    assert estimate_word_times("", 0.0, 2.0) == []
    assert estimate_word_times("xin chào", 0.0, 0.0) == []


# --------------------------------------------------------------- chunking -- #

def _mk(words):
    return [(w, i * 0.4, (i + 1) * 0.4) for i, w in enumerate(words)]


def test_chunk_size_respected():
    chunks = chunk_words(_mk(["a", "b", "c", "d", "e", "f", "g"]), 3)
    assert [len(c) for c in chunks] == [3, 3, 1]


def test_chunk_breaks_early_at_punctuation():
    chunks = chunk_words(_mk(["rồi,", "sau", "đó", "chúng", "ta"]), 3)
    # "rồi," kết thúc cụm ngay dù chưa đủ 3 chữ
    assert [w for w, _, _ in chunks[0]] == ["rồi,"]


def test_chunk_clamps_n():
    chunks = chunk_words(_mk(["a", "b", "c"]), 99)
    assert [len(c) for c in chunks] == [3]
    chunks = chunk_words(_mk(["a", "b"]), 0)
    assert [len(c) for c in chunks] == [1, 1]


# --------------------------------------------------------------- ASS text -- #

def test_ass_time_format():
    assert _ass_time(0) == "0:00:00.00"
    assert _ass_time(3661.239) == "1:01:01.24"
    assert _ass_time(-5) == "0:00:00.00"   # kẹp không âm


def test_escape_strips_override_braces():
    assert _escape_text("a {\\b1}b}\nc") == "a (\\b1)b) c"


def _write_tone(path, dur, rate=24000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        w.writeframes(struct.pack(
            f"<{n}h",
            *[int(8000 * math.sin(2 * math.pi * 440 * i / rate))
              for i in range(n)]))


class _NoAlignSettings:
    """Ước lượng thuần — không đụng model Whisper trong test."""
    karaoke_alignment = False


def test_build_karaoke_ass_end_to_end(tmp_path):
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    _write_tone(str(seg_dir / "seg_00001.wav"), 2.0)
    _write_tone(str(seg_dir / "seg_00002.wav"), 1.5)
    segments = [
        {"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0,
         "text_vi": "xin chào các bạn nhé."},
        {"id": 2, "start": 3.0, "end": 4.5, "duration": 1.5,
         "text_vi": "hẹn gặp lại."},
    ]
    out = str(tmp_path / "kara.ass")
    style = {"display": "karaoke", "words_per_cue": 3, "effect": "pop",
             "font": "Arial", "font_size": 22}
    build_karaoke_ass(segments, str(seg_dir), out, style,
                      settings=_NoAlignSettings())
    text = open(out, encoding="utf-8-sig").read()
    assert "[Script Info]" in text
    assert "Style: Kara,Arial,22," in text
    dialogues = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    # câu 1: 5 chữ → cụm 3+2 (dấu chấm cuối không tách cụm mới); câu 2: 3 chữ
    assert len(dialogues) >= 3
    # hiệu ứng pop có mặt trên từng event
    assert all("\\fscx82" in d for d in dialogues)
    # chữ tiếng Việt còn nguyên
    assert "chào" in text and "hẹn" in text


def test_build_karaoke_effect_karaoke_uses_k_tags(tmp_path):
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    _write_tone(str(seg_dir / "seg_00001.wav"), 2.0)
    segments = [{"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0,
                 "text_vi": "một hai ba bốn"}]
    out = str(tmp_path / "k.ass")
    build_karaoke_ass(segments, str(seg_dir), out,
                      {"display": "karaoke", "effect": "karaoke"},
                      settings=_NoAlignSettings())
    text = open(out, encoding="utf-8-sig").read()
    assert "\\k" in text


def test_build_karaoke_skips_missing_clip(tmp_path):
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()  # không có wav nào
    segments = [{"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0,
                 "text_vi": "vẫn ra caption."}]
    out = str(tmp_path / "k.ass")
    build_karaoke_ass(segments, str(seg_dir), out,
                      {"display": "karaoke"}, settings=_NoAlignSettings())
    # thiếu wav → dùng end-start làm thời lượng, vẫn sinh event
    text = open(out, encoding="utf-8-sig").read()
    assert "Dialogue:" in text


# --------------------------------------------------------------- mapping --- #

def test_map_words_one_to_one():
    asr = [("xin", 0.1, 0.4), ("chào", 0.4, 0.8)]
    out = _map_words(["xin", "chào"], asr, clip_start=10.0, clip_dur=1.0)
    assert out == [("xin", 10.1, 10.4), ("chào", 10.4, 10.8)]


def test_map_words_interpolates_on_count_mismatch():
    # ASR nghe 4 "chữ", văn bản có 2 — nội suy vị trí, mốc vẫn đơn điệu
    asr = [("a", 0.0, 0.2), ("b", 0.2, 0.5), ("c", 0.5, 0.7), ("d", 0.7, 1.0)]
    out = _map_words(["một", "hai"], asr, clip_start=0.0, clip_dur=1.0)
    assert len(out) == 2
    assert out[0][1] <= out[1][1]
    assert out[-1][2] <= 1.0 + 1e-9


def test_map_words_rejects_sparse_asr():
    # ASR chỉ nghe được 1 chữ trên câu 4 chữ → không tin, trả None
    asr = [("gì", 0.3, 0.5)]
    assert _map_words(["a", "b", "c", "d"], asr, 0.0, 2.0) is None


def test_map_words_monotonic_after_bad_asr_times():
    # ASR trả mốc lùi (quanh khoảng lặng) — kết quả vẫn phải đơn điệu
    asr = [("a", 0.5, 0.4), ("b", 0.3, 0.9)]
    out = _map_words(["một", "hai"], asr, 0.0, 1.0)
    assert out is not None
    for (_, s1, _e1), (_, s2, _e2) in zip(out, out[1:]):
        assert s2 >= s1
    for _, s, e in out:
        assert e >= s


def test_render_karaoke_events_pure():
    """Kiểm tra render_karaoke_events là hàm thuần, không cần audio/model AI."""
    from autodub.text.ass_karaoke import render_karaoke_events

    segments = [
        {"id": 1, "text_vi": "xin chào các bạn"},
        {"id": 2, "text_vi": "hẹn gặp lại"},
    ]
    word_times = {
        1: [("xin", 0.0, 0.3), ("chào", 0.3, 0.6), ("các", 0.6, 0.9), ("bạn", 0.9, 1.2)],
        2: [("hẹn", 2.0, 2.3), ("gặp", 2.3, 2.6), ("lại", 2.6, 2.9)],
    }
    style = {"effect": "karaoke", "words_per_cue": 2, "highlight_color": "#FFD54A"}

    events = render_karaoke_events(segments, word_times, style)
    assert len(events) >= 3
    for ev in events:
        assert ev.startswith("Dialogue:")
        assert "{\\k" in ev  # Phải có thẻ karaoke centi-giây


def test_build_karaoke_ass_with_precomputed_word_times(tmp_path):
    """Khi đã có word_times, build_karaoke_ass không cần gọi ASR hay đọc audio."""
    from autodub.text.ass_karaoke import build_karaoke_ass

    segments = [{"id": 1, "text_vi": "xin chào"}]
    word_times = {1: [("xin", 0.0, 0.4), ("chào", 0.4, 0.8)]}
    out_file = tmp_path / "kara_precomputed.ass"

    # merge_dir không tồn tại vẫn phải build thành công vì đã có precomputed word_times
    fake_merge_dir = str(tmp_path / "non_existent_dir")
    build_karaoke_ass(segments, fake_merge_dir, str(out_file), style={"effect": "pop"},
                      word_times=word_times)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8-sig")
    assert "Dialogue:" in content
    assert "xin" in content


def test_render_karaoke_events_strictly_no_overlap():
    from autodub.text.ass_karaoke import render_karaoke_events

    segments = [
        {"id": 1, "text_vi": "câu một"},
        {"id": 2, "text_vi": "câu hai kế tiếp"},
    ]
    # Simulate tight timings with potential micro-overlap
    word_times = {
        1: [("câu", 1.0, 1.15), ("một", 1.15, 1.25)],
        2: [("câu", 1.25, 1.35), ("hai", 1.35, 1.45), ("kế", 1.45, 1.55), ("tiếp", 1.55, 1.65)],
    }
    events = render_karaoke_events(segments, word_times, {"effect": "pop", "words_per_cue": 2})
    assert len(events) >= 2

    # Parse dialogue times: Dialogue: 0,H:MM:SS.cc,H:MM:SS.cc,...
    times = []
    for ev in events:
        parts = ev.split(",")
        start_str = parts[1]
        end_str = parts[2]
        times.append((start_str, end_str))

    for i in range(len(times) - 1):
        _, end_cur = times[i]
        start_nxt, _ = times[i + 1]
        # End of current dialogue must be <= start of next dialogue
        assert end_cur <= start_nxt

