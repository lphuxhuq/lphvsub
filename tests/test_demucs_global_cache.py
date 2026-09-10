import os
from unittest import mock
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
import pytest

from autodub.media import vocal_separator
import autodub.pipeline_cache as pc


def _make_wav(path: str, duration_ms: int = 200):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Sine(440).to_audio_segment(duration=duration_ms).export(path, format="wav")


def test_demucs_global_cache_end_to_end(tmp_path):
    input_wav = str(tmp_path / "audio_source.wav")
    _make_wav(input_wav)

    dir_project_1 = str(tmp_path / "project_1")
    dir_project_2 = str(tmp_path / "project_2")

    fake_called = []

    def fake_worker(src, vocals_out, no_vocals_out, model_name):
        fake_called.append("worker")
        _make_wav(vocals_out)
        _make_wav(no_vocals_out)
        return True

    def fake_ffmpeg(cmd, **kwargs):
        src = cmd[cmd.index("-i") + 1]
        AudioSegment.from_wav(src).export(cmd[-1], format="wav")
        return mock.Mock(returncode=0, stderr="")

    # 1. First project: Cold run (cache miss -> runs worker -> stores cache)
    with mock.patch("autodub.media.vocal_separator._run_demucs_gpu_worker", side_effect=fake_worker), \
         mock.patch("autodub.media.vocal_separator.subprocess.run", side_effect=fake_ffmpeg):
        res1 = vocal_separator.separate_vocals(input_wav, dir_project_1, model="htdemucs", sample_rate=44100, channels=2)

    assert len(fake_called) == 1
    assert os.path.exists(res1["vocals"])
    assert os.path.exists(res1["no_vocals"])

    # 2. Second project: Warm run (cache hit -> skips worker -> copies cached stems)
    fake_called.clear()
    with mock.patch("autodub.media.vocal_separator._run_demucs_gpu_worker", side_effect=fake_worker), \
         mock.patch("autodub.media.vocal_separator._run_demucs") as mock_cpu, \
         mock.patch("autodub.media.vocal_separator.subprocess.run", side_effect=fake_ffmpeg):
        res2 = vocal_separator.separate_vocals(input_wav, dir_project_2, model="htdemucs", sample_rate=44100, channels=2)

    assert len(fake_called) == 0, "Demucs worker must NOT be called on warm cache hit"
    mock_cpu.assert_not_called()
    assert os.path.exists(res2["vocals"])
    assert os.path.exists(res2["no_vocals"])
    assert res2["vocals"] == os.path.join(dir_project_2, "vocals.wav")
    assert res2["no_vocals"] == os.path.join(dir_project_2, "no_vocals.wav")


def test_demucs_global_cache_invalidation_and_fallback(tmp_path):
    input_wav = str(tmp_path / "audio_source.wav")
    _make_wav(input_wav)

    dir_project_1 = str(tmp_path / "proj_1")
    dir_project_2 = str(tmp_path / "proj_2")

    worker_count = 0

    def fake_worker(src, vocals_out, no_vocals_out, model_name):
        nonlocal worker_count
        worker_count += 1
        _make_wav(vocals_out)
        _make_wav(no_vocals_out)
        return True

    def fake_ffmpeg(cmd, **kwargs):
        src = cmd[cmd.index("-i") + 1]
        AudioSegment.from_wav(src).export(cmd[-1], format="wav")
        return mock.Mock(returncode=0, stderr="")

    with mock.patch("autodub.media.vocal_separator._run_demucs_gpu_worker", side_effect=fake_worker), \
         mock.patch("autodub.media.vocal_separator.subprocess.run", side_effect=fake_ffmpeg):
        vocal_separator.separate_vocals(input_wav, dir_project_1, model="htdemucs", sample_rate=44100, channels=2)

    assert worker_count == 1

    # Request with different model -> must invalidate and run worker
    with mock.patch("autodub.media.vocal_separator._run_demucs_gpu_worker", side_effect=fake_worker), \
         mock.patch("autodub.media.vocal_separator.subprocess.run", side_effect=fake_ffmpeg):
        vocal_separator.separate_vocals(input_wav, dir_project_2, model="htdemucs_ft", sample_rate=44100, channels=2)

    assert worker_count == 2, "Different model must invalidate cache and re-run worker"
