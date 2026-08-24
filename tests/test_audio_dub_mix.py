"""5 scenario bắt buộc của spec AUDIO_DUB (Phase 13).

Chứng minh: 2 track chồng nhau thật · TQ dip theo SPEECH SEGMENT (không
phai theo giọng Việt) · onset VI = speech_start · silence hồi mức gốc ·
không ép TTS về duration gốc, không đẩy câu theo dub-end câu trước.
"""
import os
import wave

import numpy as np

from autodub.media.audio import _duck_envelope, merge_segments
from autodub.media.timing import plan_voice_placements

_RATE = 16000


def _env_gain(t, intervals, duck_db, attack_s=0.08, release_s=0.14):
    """Gain của envelope tại thời điểm t (một mẫu)."""
    b0 = 0
    n = int(t * _RATE) + 1
    env = _duck_envelope(n, b0, _RATE, intervals, duck_db,
                         attack_s, release_s)
    return float(env[-1])


# ---------------- Test 1: hai track cùng bắt đầu, TQ nhỏ hơn --------------

def test_1_vn_longer_than_chinese_both_start_together():
    # TQ nói 10.0→12.0; TTS VI dài hơn (2.5s)
    segs = [{"id": 1, "start": 10.0, "end": 12.0, "duration": 2.0,
             "speech_start": 10.0, "speech_end": 12.0,
             "speech_duration": 2.0}]
    placements, _ = plan_voice_placements(segs, [2.5])
    assert abs(placements[0]["start"] - 10.0) < 0.001   # cùng onset
    # nền dip sâu trong lúc nói (dip −11dB trên nền tĩnh −5 = tổng −16)
    g = _env_gain(11.0, [(10.0, 12.0)], -11.0)
    assert abs(g - 10 ** (-11 / 20)) < 0.02             # ≈ 0.28


# ---------------- Test 2: VI ngắn hơn — TQ vẫn dip tới hết câu -----------

def test_2_vn_ends_early_chinese_still_ducked_until_speech_end():
    # VI 10.0→11.6 nhưng TQ nói tới 12.0: dip PHẢI tiếp tục sau 11.6
    g_at_118 = _env_gain(11.8, [(10.0, 12.0)], -11.0)
    assert g_at_118 < 10 ** (-10 / 20)                  # vẫn chìm sâu
    # (hành vi cũ duck-theo-giọng-VI đã trồi lên ở đây — regression guard)


# ---------------- Test 3: khoảng lặng — hồi mức gốc ----------------------

def test_3_silence_restores_full_volume():
    release = 0.14
    g_after = _env_gain(12.5, [(10.0, 12.0)], -11.0, release_s=release)
    assert g_after > 0.98                               # đã hồi sau release


# ---------------- Test 4: hai câu liên tiếp, onset độc lập ---------------

def test_4_consecutive_sentences_start_at_own_onsets():
    segs = [
        {"id": 1, "start": 10.0, "end": 12.0, "duration": 2.0,
         "speech_start": 10.0, "speech_end": 12.0, "speech_duration": 2.0},
        {"id": 2, "start": 12.2, "end": 14.0, "duration": 1.8,
         "speech_start": 12.2, "speech_end": 14.0, "speech_duration": 1.8},
    ]
    placements, _ = plan_voice_placements(segs, [3.0, 1.5])  # A dài 3s!
    assert abs(placements[0]["start"] - 10.0) < 0.001
    # B bắt đầu ở onset CỦA B — không phải "VN A end"
    assert abs(placements[1]["start"] - 12.2) < 0.151       # trần drift 0.15s


# ---------------- Test 5: VI dài hơn hẳn — không slow, không ép khít -----

def test_5_much_longer_vn_still_starts_together_no_forced_fit():
    segs = [{"id": 1, "start": 10.0, "end": 12.3, "duration": 2.3,
             "speech_start": 10.0, "speech_end": 12.3,
             "speech_duration": 2.3}]
    placements, report = plan_voice_placements(segs, [5.0])
    assert abs(placements[0]["start"] - 10.0) < 0.001   # KHÔNG đợi hết câu
    assert placements[0]["atempo"] <= 1.15 + 1e-9       # nén nhẹ trần 1.15
    assert placements[0]["atempo"] > 1.0                # có nén cho vừa chỗ


# ---------------- Integration: mix thật 2 track (merge_segments) ----------

def _wav_tone(path, dur_s, freq=200.0, amp=0.4, rate=44100):
    t = np.arange(int(dur_s * rate)) / rate
    x = amp * np.sin(2 * np.pi * freq * t)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _rms(path, t0, t1):
    with wave.open(path) as w:
        rate = w.getframerate()
        a, b = int(t0 * rate), int(t1 * rate)
        w.setpos(a)
        x = np.frombuffer(w.readframes(b - a), dtype=np.int16).astype(np.float32) / 32768
    return float(np.sqrt((x ** 2).mean()))


def test_integration_two_tracks_overlap_and_speech_duck(tmp_path):
    """Nền 200Hz liên tục; VI là tone 500Hz đặt đúng speech_start 2.0s,
    dài 0.5s. Đo: nền dip trong [2,4] dù VI đã dứt; hồi sau release."""
    bg = str(tmp_path / "bg.wav")
    seg_dir = str(tmp_path / "segs"); os.makedirs(seg_dir)
    _wav_tone(bg, 6.0, freq=200.0)                       # nền gốc 0dB
    _wav_tone(os.path.join(seg_dir, "seg_001.wav"), 0.5, freq=500.0)

    segments = [{"id": 1, "start": 2.0, "end": 2.5, "duration": 0.5,
                 "speech_start": 2.0, "speech_end": 4.0}]
    out = str(tmp_path / "mix.wav")
    merge_segments(segments, seg_dir, out, 6.0,
                   background_path=bg, background_gain_db=0.0,
                   speech_intervals=[(2.0, 4.0)], speech_duck_db=-16.0,
                   duck_attack_s=0.08, duck_release_s=0.14)

    pre = _rms(out, 0.5, 1.5)          # trước speech: nền đầy
    during = _rms(out, 3.2, 3.9)       # trong speech, SAU khi VI dứt (2.5)
    after = _rms(out, 5.0, 5.9)        # sau release
    # nền chìm đúng ~16dB trong speech (dù VI đã im từ 2.5s)
    assert 20 * np.log10(during / pre) < -13.0
    assert 20 * np.log10(after / pre) > -1.5            # đã hồi
    # hai track chồng nhau trong [2.0, 2.5]: năng lượng > nền dip
    both = _rms(out, 2.1, 2.4)
    assert both > during * 2                             # VI nổi trên nền
