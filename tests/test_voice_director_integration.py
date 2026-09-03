import wave
import numpy as np
import pytest

from autodub.config import Settings
from autodub.speech.speaker_profiler import profile_speakers
from autodub.speech.voice_catalog import UnifiedVoiceCatalog
from autodub.speech.voice_director import cast_voices


def _generate_synthetic_tone(freq_hz: float, duration_s: float, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    signal = 0.8 * np.sin(2 * np.pi * freq_hz * t) + 0.2 * np.sin(2 * np.pi * 2 * freq_hz * t)
    return signal.astype(np.float32)


def test_voice_director_full_integration(tmp_path):
    sr = 16000
    # Speaker 0: Nam trầm 120Hz, 10s (Dẫn chuyện)
    spk0_audio = _generate_synthetic_tone(120.0, 10.0, sr=sr)
    # Speaker 1: Nữ cao 215Hz, 5s (Nhân vật)
    spk1_audio = _generate_synthetic_tone(215.0, 5.0, sr=sr)

    full_audio = np.concatenate([spk0_audio, spk1_audio])
    audio_path = str(tmp_path / "integration_multi_spk.wav")

    int16_audio = (full_audio * 32767).astype(np.int16)
    with wave.open(audio_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_audio.tobytes())

    segments = [
        {"id": 1, "speaker_id": 0, "start": 0.0, "end": 5.0, "text": "Hôm nay chúng ta cùng tìm hiểu"},
        {"id": 2, "speaker_id": 0, "start": 5.0, "end": 10.0, "text": "về thế giới động vật hoang dã"},
        {"id": 3, "speaker_id": 1, "start": 10.0, "end": 15.0, "text": "Tuyệt vời quá anh ơi!"},
    ]

    settings = Settings(auto_voice_director_enabled=True)

    # 1. Trích xuất đặc trưng âm học & F0
    profiles = profile_speakers(audio_path, segments, settings=settings)
    assert 0 in profiles
    assert 1 in profiles

    assert profiles[0].gender == "male"
    assert profiles[0].role == "narrator"
    assert profiles[0].pitch_stats.pitch_median < 140.0

    assert profiles[1].gender == "female"
    assert profiles[1].pitch_stats.pitch_median > 190.0

    # 2. Khởi tạo Catalog & Chạy Auto Voice Casting
    catalog = UnifiedVoiceCatalog.create_default(settings)
    casting = cast_voices(profiles, catalog, current_voice="Trần Hải", auto_enabled=True)

    assert casting.director_enabled is True
    assert len(casting.assignments) == 2

    # Speaker 0 (Nam) và Speaker 1 (Nữ) phải nhận 2 giọng khác nhau
    spk0_voice_id = casting.assignments[0].voice_id
    spk1_voice_id = casting.assignments[1].voice_id
    assert spk0_voice_id != spk1_voice_id

    # 3. Kiểm tra tính năng Manual Override
    manual = {1: "Tùy chỉnh Nữ Đặc biệt"}
    casting_manual = cast_voices(profiles, catalog, current_voice="Trần Hải", manual_overrides=manual, auto_enabled=True)
    assert casting_manual.assignments[1].voice_id == "Tùy chỉnh Nữ Đặc biệt"
    assert casting_manual.assignments[1].source == "manual_override"

    # 4. Kiểm tra Toggle Bật/Tắt
    casting_disabled = cast_voices(profiles, catalog, current_voice="Trần Hải", auto_enabled=False)
    assert casting_disabled.director_enabled is False
    assert casting_disabled.assignments[0].voice_id == "Trần Hải"
    assert casting_disabled.assignments[1].voice_id == "Trần Hải"
    assert casting_disabled.assignments[0].source == "fallback"
