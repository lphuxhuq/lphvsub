import os
from unittest.mock import MagicMock, patch
import pytest

from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest
from autodub.speech.voice_models import PitchStats, SpeakerProfile


def test_pipeline_step3_7_voice_director_wiring(tmp_path):
    settings = Settings(
        auto_voice_director_enabled=True,
        diarization_enabled=True,
    )
    pipeline = DubPipeline(settings)

    mock_segments = [
        {"id": 1, "speaker_id": 0, "start": 0.0, "end": 5.0, "text": "Câu 1"},
        {"id": 2, "speaker_id": 1, "start": 5.0, "end": 10.0, "text": "Câu 2"},
    ]
    mock_profiles = {
        0: SpeakerProfile(
            speaker_id=0, gender="male", gender_confidence=0.9,
            pitch_stats=PitchStats(120.0, 100.0, 140.0, 5.0, 0.9, 0.9),
            role="narrator", role_confidence=0.9, total_duration_s=5.0,
            segment_count=1, timeline_coverage=0.5, avg_segment_duration_s=5.0,
        ),
        1: SpeakerProfile(
            speaker_id=1, gender="female", gender_confidence=0.9,
            pitch_stats=PitchStats(210.0, 190.0, 230.0, 8.0, 0.85, 0.9),
            role="character", role_confidence=0.8, total_duration_s=5.0,
            segment_count=1, timeline_coverage=0.5, avg_segment_duration_s=5.0,
        ),
    }

    req = DubRequest(file_path="dummy.mp4", voice="nam_bac_1")

    with patch("autodub.speech.speaker_profiler.profile_speakers", return_value=mock_profiles):
        from autodub.speech.voice_catalog import UnifiedVoiceCatalog
        from autodub.speech.voice_director import cast_voices

        catalog = UnifiedVoiceCatalog.create_default(settings)
        casting = cast_voices(mock_profiles, catalog, current_voice=req.voice, auto_enabled=True)

        assert len(casting.assignments) == 2
        assert 0 in casting.assignments
        assert 1 in casting.assignments
        assert casting.assignments[0].voice_id != casting.assignments[1].voice_id
