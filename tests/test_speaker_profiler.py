import numpy as np
import pytest

from autodub.speech.speaker_profiler import (
    estimate_f0_stats,
    classify_gender_probabilistic,
    detect_narrator_role,
    profile_speakers,
    DEFAULT_DEEP_MALE_MAX_HZ,
    DEFAULT_YOUNG_MALE_MAX_HZ,
    DEFAULT_FEMALE_MAX_HZ,
)
from autodub.speech.voice_models import PitchStats, SpeakerProfile


def _generate_synthetic_tone(freq_hz: float, duration_s: float, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Fundamental + 1 harmonic
    signal = 0.8 * np.sin(2 * np.pi * freq_hz * t) + 0.2 * np.sin(2 * np.pi * 2 * freq_hz * t)
    return signal.astype(np.float32)


def test_estimate_f0_male_synthetic():
    sr = 16000
    audio = _generate_synthetic_tone(120.0, 2.0, sr=sr)
    stats = estimate_f0_stats(audio, sr=sr)

    assert isinstance(stats, PitchStats)
    assert 115.0 <= stats.pitch_median <= 125.0
    assert stats.voiced_ratio >= 0.80
    assert stats.confidence >= 0.70


def test_estimate_f0_female_synthetic():
    sr = 16000
    audio = _generate_synthetic_tone(210.0, 2.0, sr=sr)
    stats = estimate_f0_stats(audio, sr=sr)

    assert isinstance(stats, PitchStats)
    assert 200.0 <= stats.pitch_median <= 220.0
    assert stats.voiced_ratio >= 0.80
    assert stats.confidence >= 0.70


def test_estimate_f0_silence():
    sr = 16000
    audio = np.zeros(sr * 2, dtype=np.float32)
    stats = estimate_f0_stats(audio, sr=sr)

    assert stats.pitch_median == 0.0
    assert stats.voiced_ratio == 0.0
    assert stats.confidence == 0.0


def test_classify_gender_probabilistic():
    # Male test
    stats_male = PitchStats(
        pitch_median=120.0, pitch_p10=110.0, pitch_p90=130.0, pitch_std=5.0,
        voiced_ratio=0.85, confidence=0.90,
    )
    gender, conf = classify_gender_probabilistic(stats_male)
    assert gender == "male"
    assert conf >= 0.80

    # Female test
    stats_female = PitchStats(
        pitch_median=220.0, pitch_p10=200.0, pitch_p90=240.0, pitch_std=8.0,
        voiced_ratio=0.85, confidence=0.90,
    )
    gender, conf = classify_gender_probabilistic(stats_female)
    assert gender == "female"
    assert conf >= 0.80

    # Low confidence silence
    stats_silence = PitchStats(
        pitch_median=0.0, pitch_p10=0.0, pitch_p90=0.0, pitch_std=0.0,
        voiced_ratio=0.0, confidence=0.0,
    )
    gender, conf = classify_gender_probabilistic(stats_silence)
    assert gender == "unknown"
    assert conf == 0.0


def test_detect_narrator_role():
    # Narrator profile: dominant duration, large span
    role, conf = detect_narrator_role(
        total_duration_s=120.0,
        total_audio_duration_s=200.0,
        segment_count=25,
        timeline_coverage=0.90,
        avg_segment_duration_s=4.8,
    )
    assert role == "narrator"
    assert conf >= 0.80

    # Character profile: short duration, low coverage
    role2, conf2 = detect_narrator_role(
        total_duration_s=15.0,
        total_audio_duration_s=200.0,
        segment_count=4,
        timeline_coverage=0.30,
        avg_segment_duration_s=3.75,
    )
    assert role2 == "character"


def test_profile_speakers_multi_speaker(tmp_path):
    import wave
    import struct

    sr = 16000
    # Speaker 0: Nam (120Hz) - đóng vai trò Dẫn chuyện
    spk0_audio = _generate_synthetic_tone(120.0, 10.0, sr=sr)
    # Speaker 1: Nữ (210Hz)
    spk1_audio = _generate_synthetic_tone(210.0, 5.0, sr=sr)

    full_audio = np.concatenate([spk0_audio, spk1_audio])
    audio_path = str(tmp_path / "test_multi_speaker.wav")

    # Ghi WAV 16-bit PCM mono
    int16_audio = (full_audio * 32767).astype(np.int16)
    with wave.open(audio_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_audio.tobytes())

    segments = [
        {"id": 1, "speaker_id": 0, "start": 0.0, "end": 5.0, "text": "Lời dẫn chuyện phần một"},
        {"id": 2, "speaker_id": 0, "start": 5.0, "end": 10.0, "text": "Lời dẫn chuyện phần hai"},
        {"id": 3, "speaker_id": 1, "start": 10.0, "end": 15.0, "text": "Chào anh, em là nhân vật nữ"},
    ]

    profiles = profile_speakers(audio_path, segments)
    assert 0 in profiles
    assert 1 in profiles

    assert profiles[0].gender == "male"
    assert profiles[0].role == "narrator"
    assert profiles[1].gender == "female"

