import os
from unittest.mock import MagicMock, patch
import pytest
from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest


def test_asr_source_default_without_vocals(tmp_path):
    pipeline = DubPipeline(Settings(asr_use_vocals=False))
    default_audio = str(tmp_path / "original_audio.wav")
    with open(default_audio, "w") as f:
        f.write("dummy")

    req = DubRequest(file_path="dummy.mp4", bg_mode="duck")
    source = pipeline._asr_source(str(tmp_path), None, pipeline.settings, default_audio, req)
    assert source == default_audio


def test_asr_source_with_demucs_vocals(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vocals_wav = data_dir / "vocals.wav"
    vocals_wav.write_text("vocals")
    default_audio_file = data_dir / "original_audio.wav"
    default_audio_file.write_text("audio")
    default_audio = str(default_audio_file)

    pipeline = DubPipeline(Settings(asr_use_vocals=True))
    mock_future = MagicMock()
    mock_future.result.return_value = None

    req = DubRequest(file_path="dummy.mp4", bg_mode="demucs")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        source = pipeline._asr_source(str(tmp_path), mock_future, pipeline.settings, default_audio, req)
        assert "asr_vocals.wav" in source or source == str(vocals_wav)

