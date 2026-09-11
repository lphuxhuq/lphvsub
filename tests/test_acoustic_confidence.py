"""Unit tests cho Acoustic Alignment Confidence và Fallback Routing."""

import math
import struct
import wave

from autodub.speech.acoustic_align import (
    AcousticAlignmentResult,
    acoustic_word_times,
    analyze_acoustic_alignment,
)


def _write_burst_tone(path: str, total_dur: float = 0.5, burst_dur: float = 0.3, rate: int = 16000):
    """Ghi file WAV có khoảng lặng đầu/đuôi và tiếng phát âm rõ nét ở giữa (voice burst)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        total_frames = int(total_dur * rate)
        burst_frames = int(burst_dur * rate)
        lead_frames = (total_frames - burst_frames) // 2

        frames = []
        for i in range(total_frames):
            if lead_frames <= i < lead_frames + burst_frames:
                t = i / rate
                val = math.sin(2 * math.pi * 300 * t)
                frames.append(int(val * 16000))
            else:
                frames.append(0)  # Silence
        w.writeframes(struct.pack(f"<{total_frames}h", *frames))


def _write_silence(path: str, dur: float = 0.5, rate: int = 16000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        w.writeframes(b"\x00\x00" * n)


def test_acoustic_alignment_high_confidence(tmp_path):
    """File có tiếng phát âm rõ, 1-2 từ, ngắn <= 0.6s -> confidence HIGH (>= 0.70)."""
    wav_file = tmp_path / "burst.wav"
    _write_burst_tone(str(wav_file), total_dur=0.45, burst_dur=0.3)

    res = analyze_acoustic_alignment("vâng", str(wav_file), clip_start=1.0, clip_dur=0.45)
    assert isinstance(res, AcousticAlignmentResult)
    assert len(res.words) == 1
    assert res.confidence >= 0.70
    assert res.method == "acoustic_high_conf"
    assert res.start >= 1.0
    assert res.end <= 1.45


def test_acoustic_alignment_low_confidence_on_silence(tmp_path):
    """File im lặng -> confidence LOW (< 0.70) và method = acoustic_low_conf."""
    wav_file = tmp_path / "silence.wav"
    _write_silence(str(wav_file), dur=0.5)

    res = analyze_acoustic_alignment("xin chào", str(wav_file), clip_start=0.0, clip_dur=0.5)
    assert isinstance(res, AcousticAlignmentResult)
    assert res.confidence < 0.70
    assert res.method == "acoustic_low_conf"


def test_acoustic_word_times_backward_compatible(tmp_path):
    """Hàm acoustic_word_times cũ vẫn trả về list[tuple[str, float, float]]."""
    wav_file = tmp_path / "burst.wav"
    _write_burst_tone(str(wav_file), total_dur=0.4, burst_dur=0.25)

    words = acoustic_word_times("đồng ý", str(wav_file), clip_start=2.0, clip_dur=0.4)
    assert len(words) == 2
    assert words[0][0] == "đồng"
    assert words[1][0] == "ý"
    assert words[0][1] >= 2.0
