import pytest
from unittest.mock import MagicMock

from autodub.speech.voice_models import PitchStats, SpeakerProfile, VoiceProfile
from autodub.speech.voice_catalog import UnifiedVoiceCatalog
from autodub.speech.voice_director import VoiceDirector, cast_voices


@pytest.fixture
def sample_catalog():
    voices = [
        VoiceProfile(voice_id="nam_bac_1", name="Nam Bắc 1", provider="vieneu", gender="male", style="tin_tuc", narrator_suitability=0.95, pitch_tag="deep_male"),
        VoiceProfile(voice_id="nam_nam_1", name="Nam Nam 1", provider="vieneu", gender="male", style="tu_nhien", narrator_suitability=0.70, pitch_tag="young_male"),
        VoiceProfile(voice_id="nu_bac_1", name="Nữ Bắc 1", provider="vieneu", gender="female", style="tu_nhien", narrator_suitability=0.80, pitch_tag="female"),
        VoiceProfile(voice_id="nu_nam_1", name="Nữ Nam 1", provider="vieneu", gender="female", style="tu_nhien", narrator_suitability=0.75, pitch_tag="female"),
    ]
    mock_provider = MagicMock()
    mock_provider.get_voices.return_value = voices
    mock_provider.is_available.return_value = True

    return UnifiedVoiceCatalog(providers={"vieneu": mock_provider})


def test_voice_director_auto_casting_multi_speaker(sample_catalog):
    # 3 speakers: Speaker 0 (Nam Dẫn chuyện), Speaker 1 (Nữ), Speaker 2 (Nam)
    profiles = {
        0: SpeakerProfile(
            speaker_id=0, gender="male", gender_confidence=0.92,
            pitch_stats=PitchStats(115.0, 100.0, 130.0, 8.0, 0.9, 0.95),
            role="narrator", role_confidence=0.90, total_duration_s=80.0, segment_count=20,
            timeline_coverage=0.90, avg_segment_duration_s=4.0,
        ),
        1: SpeakerProfile(
            speaker_id=1, gender="female", gender_confidence=0.90,
            pitch_stats=PitchStats(215.0, 195.0, 235.0, 10.0, 0.85, 0.90),
            role="character", role_confidence=0.80, total_duration_s=30.0, segment_count=8,
            timeline_coverage=0.50, avg_segment_duration_s=3.75,
        ),
        2: SpeakerProfile(
            speaker_id=2, gender="male", gender_confidence=0.85,
            pitch_stats=PitchStats(145.0, 130.0, 160.0, 9.0, 0.80, 0.88),
            role="character", role_confidence=0.80, total_duration_s=25.0, segment_count=6,
            timeline_coverage=0.40, avg_segment_duration_s=4.16,
        ),
    }

    result = cast_voices(profiles, sample_catalog, auto_enabled=True)

    assert result.director_enabled is True
    assert len(result.assignments) == 3

    # Speaker 0 (Nam Dẫn chuyện) -> nam_bac_1
    assert result.assignments[0].voice_id == "nam_bac_1"
    assert result.assignments[0].source == "auto"

    # Speaker 1 (Nữ) -> nu_bac_1 hoặc nu_nam_1
    assert result.assignments[1].voice_id in ("nu_bac_1", "nu_nam_1")

    # Speaker 2 (Nam) -> nam_nam_1 (khác với speaker 0 do Uniqueness Penalty)
    assert result.assignments[2].voice_id == "nam_nam_1"
    assert result.assignments[2].voice_id != result.assignments[0].voice_id


def test_voice_director_manual_override(sample_catalog):
    profiles = {
        0: SpeakerProfile(
            speaker_id=0, gender="male", gender_confidence=0.90,
            pitch_stats=PitchStats(120.0, 100.0, 130.0, 8.0, 0.9, 0.9),
            role="narrator", role_confidence=0.90, total_duration_s=50.0, segment_count=10,
            timeline_coverage=0.8, avg_segment_duration_s=5.0,
        ),
        1: SpeakerProfile(
            speaker_id=1, gender="female", gender_confidence=0.90,
            pitch_stats=PitchStats(210.0, 190.0, 230.0, 10.0, 0.85, 0.9),
            role="character", role_confidence=0.80, total_duration_s=20.0, segment_count=5,
            timeline_coverage=0.4, avg_segment_duration_s=4.0,
        ),
    }

    # Người dùng khóa speaker 1 sang "nu_nam_1"
    manual = {1: "nu_nam_1"}
    result = cast_voices(profiles, sample_catalog, manual_overrides=manual, auto_enabled=True)

    assert result.assignments[1].voice_id == "nu_nam_1"
    assert result.assignments[1].source == "manual_override"
    assert result.assignments[0].source == "auto"


def test_voice_director_toggle_disabled(sample_catalog):
    profiles = {
        0: SpeakerProfile(
            speaker_id=0, gender="male", gender_confidence=0.90,
            pitch_stats=PitchStats(120.0, 100.0, 130.0, 8.0, 0.9, 0.9),
            role="narrator", role_confidence=0.90, total_duration_s=50.0, segment_count=10,
            timeline_coverage=0.8, avg_segment_duration_s=5.0,
        ),
        1: SpeakerProfile(
            speaker_id=1, gender="female", gender_confidence=0.90,
            pitch_stats=PitchStats(210.0, 190.0, 230.0, 10.0, 0.85, 0.9),
            role="character", role_confidence=0.80, total_duration_s=20.0, segment_count=5,
            timeline_coverage=0.4, avg_segment_duration_s=4.0,
        ),
    }

    # Khi auto_enabled=False -> gán tất cả về current_voice "nam_bac_1"
    result = cast_voices(profiles, sample_catalog, current_voice="nam_bac_1", auto_enabled=False)

    assert result.director_enabled is False
    assert result.assignments[0].voice_id == "nam_bac_1"
    assert result.assignments[1].voice_id == "nam_bac_1"
    assert result.assignments[0].source == "fallback"
    assert result.assignments[1].source == "fallback"
