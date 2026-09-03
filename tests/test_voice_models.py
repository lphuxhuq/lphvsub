import pytest
from dataclasses import asdict

from autodub.speech.voice_models import (
    PitchStats,
    SpeakerProfile,
    VoiceProfile,
    VoiceAssignment,
    CastingResult,
)


def test_pitch_stats_dataclass():
    stats = PitchStats(
        pitch_median=150.5,
        pitch_p10=120.0,
        pitch_p90=180.0,
        pitch_std=15.2,
        voiced_ratio=0.85,
        confidence=0.92,
    )
    assert stats.pitch_median == 150.5
    assert stats.pitch_p10 == 120.0
    assert stats.pitch_p90 == 180.0
    assert stats.pitch_std == 15.2
    assert stats.voiced_ratio == 0.85
    assert stats.confidence == 0.92

    # Immutable test
    with pytest.raises(Exception):
        stats.pitch_median = 200.0


def test_speaker_profile_serialization():
    stats = PitchStats(
        pitch_median=210.0,
        pitch_p10=190.0,
        pitch_p90=230.0,
        pitch_std=12.0,
        voiced_ratio=0.90,
        confidence=0.95,
    )
    profile = SpeakerProfile(
        speaker_id=1,
        gender="female",
        gender_confidence=0.88,
        pitch_stats=stats,
        role="character",
        role_confidence=0.80,
        total_duration_s=45.2,
        segment_count=12,
        timeline_coverage=0.75,
        avg_segment_duration_s=3.76,
    )

    data = asdict(profile)
    assert data["speaker_id"] == 1
    assert data["gender"] == "female"
    assert data["pitch_stats"]["pitch_median"] == 210.0
    assert data["total_duration_s"] == 45.2


def test_voice_profile_and_assignment():
    vp = VoiceProfile(
        voice_id="nu_bac_1",
        name="Nữ Bắc 1",
        provider="vieneu",
        gender="female",
        region="bac",
        style="tu_nhien",
        narrator_suitability=0.85,
        pitch_tag="female",
    )
    assert vp.voice_id == "nu_bac_1"
    assert vp.provider == "vieneu"

    va = VoiceAssignment(
        speaker_id=1,
        voice_id="nu_bac_1",
        source="auto",
        score=0.94,
        reason="Khớp giới tính Nữ và cao độ female",
    )
    assert va.speaker_id == 1
    assert va.voice_id == "nu_bac_1"
    assert va.source == "auto"


def test_casting_result():
    stats = PitchStats(
        pitch_median=110.0,
        pitch_p10=95.0,
        pitch_p90=130.0,
        pitch_std=10.0,
        voiced_ratio=0.80,
        confidence=0.90,
    )
    sp = SpeakerProfile(
        speaker_id=0,
        gender="male",
        gender_confidence=0.95,
        pitch_stats=stats,
        role="narrator",
        role_confidence=0.90,
        total_duration_s=60.0,
        segment_count=15,
        timeline_coverage=0.90,
        avg_segment_duration_s=4.0,
    )
    va = VoiceAssignment(
        speaker_id=0,
        voice_id="nam_bac_1",
        source="auto",
        score=0.98,
        reason="Dẫn chuyện Nam",
    )
    res = CastingResult(
        assignments={0: va},
        profiles={0: sp},
        director_enabled=True,
    )
    assert res.director_enabled is True
    assert 0 in res.assignments
    assert res.assignments[0].voice_id == "nam_bac_1"
