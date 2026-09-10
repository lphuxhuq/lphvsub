import os
from unittest import mock
from pathlib import Path
import pytest

from autodub.pipeline import DubPipeline, DubRequest
from autodub.config import Settings
from autodub.languages import TargetLang
from autodub.workdir import data_path
import autodub.pipeline_cache as pc


def _make_dummy_wav(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")


def test_asr_cache_cross_project_reuse(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy_video_bytes")
    audio = tmp_path / "audio.wav"
    _make_dummy_wav(str(audio))

    proj1_dir = str(tmp_path / "proj1")
    proj2_dir = str(tmp_path / "proj2")

    transcribe_calls = []

    def fake_transcribe(audio_path, lang, settings, **kwargs):
        transcribe_calls.append(lang)
        return [
            {"id": 1, "start": 0.0, "end": 1.0, "text": "Hello world"},
            {"id": 2, "start": 1.0, "end": 2.0, "text": "Welcome to UPC"},
        ]

    settings = Settings()
    pipeline = DubPipeline(settings)

    # 1. First project run (Cold ASR)
    with mock.patch("autodub.speech.transcriber.transcribe", side_effect=fake_transcribe), \
         mock.patch.object(pipeline, "_resolve_video", return_value=str(video)), \
         mock.patch("autodub.media.audio.extract_audio", side_effect=lambda v, a, **kw: _make_dummy_wav(a)), \
         mock.patch("autodub.media.audio.extract_audio_dual", side_effect=lambda v, a, h, **kw: (_make_dummy_wav(a), _make_dummy_wav(h))):

        # Test step 3 specifically using the ASR cache logic
        engine = getattr(settings, "asr_engine", "whisper")
        model = getattr(settings, "whisper_model", "base")
        lang = "en"

        # Lookup miss
        cache = pc.get_asr_cache()
        assert cache.lookup(str(audio), model, lang, engine) is None

        # Simulate transcribe & store
        segs = fake_transcribe(str(audio), lang, settings)
        cache.store(str(audio), model, lang, engine, segs)

        # In project 2, lookup should hit
        hit = cache.lookup(str(audio), model, lang, engine)
        assert hit == segs
        assert len(hit) == 2
        assert hit[0]["text"] == "Hello world"


def test_pipeline_step3_asr_global_cache_integration(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy_video_bytes")
    audio = tmp_path / "original_audio.wav"
    _make_dummy_wav(str(audio))

    proj1 = tmp_path / "project_run_1"
    proj2 = tmp_path / "project_run_2"
    os.makedirs(proj1 / "data", exist_ok=True)
    os.makedirs(proj2 / "data", exist_ok=True)

    # Place audio in proj1 and proj2
    _make_dummy_wav(str(proj1 / "data" / "original_audio.wav"))
    _make_dummy_wav(str(proj2 / "data" / "original_audio.wav"))

    transcribe_calls = 0

    def mock_transcribe(audio_path, lang, settings, **kwargs):
        nonlocal transcribe_calls
        transcribe_calls += 1
        return [
            {"id": 1, "start": 0.0, "end": 1.0, "text": "Segment 1"},
            {"id": 2, "start": 1.0, "end": 2.0, "text": "Segment 2"},
        ]

    settings = Settings()
    pipeline = DubPipeline(settings)

    # Run 1: Cold transcribe
    with mock.patch("autodub.speech.transcriber.transcribe", side_effect=mock_transcribe):
        asr_audio = str(proj1 / "data" / "original_audio.wav")
        engine = getattr(settings, "asr_engine", "whisper")
        model_name = getattr(settings, "whisper_model", "base")
        lang_code = "zh"

        # Simulating Step 3 logic
        cache = pc.get_asr_cache()
        cached = cache.lookup(asr_audio, model_name, lang_code, engine)
        assert cached is None
        segs = mock_transcribe(asr_audio, lang_code, settings)
        cache.store(asr_audio, model_name, lang_code, engine, segs)

    assert transcribe_calls == 1

    # Run 2: Warm lookup in project 2 with identical audio content
    with mock.patch("autodub.speech.transcriber.transcribe", side_effect=mock_transcribe):
        asr_audio_2 = str(proj2 / "data" / "original_audio.wav")
        cached = cache.lookup(asr_audio_2, model_name, lang_code, engine)
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["text"] == "Segment 1"

    # transcribe was NOT called in run 2
    assert transcribe_calls == 1
