import os
import wave
import numpy as np
import pytest

from autodub.config import Settings
from autodub.speech.diarization import (
    estimate_frame_f0,
    extract_acoustic_embedding,
    estimate_num_speakers,
    cluster_speaker_embeddings,
    diarize_segments,
)


def _create_synthetic_audio(path: str, duration_s: float = 4.0, freq: float = 200.0, sr: int = 16000):
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)
    sig_int16 = (sig * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(sig_int16.tobytes())


def test_estimate_frame_f0():
    sr = 16000
    t = np.linspace(0, 0.025, int(sr * 0.025), endpoint=False)
    sig = np.sin(2 * np.pi * 220.0 * t)
    f0 = estimate_frame_f0(sig, sr=sr)
    assert 200.0 <= f0 <= 240.0


def test_extract_acoustic_embedding_shape():
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = np.sin(2 * np.pi * 150.0 * t).astype(np.float32)
    emb = extract_acoustic_embedding(sig, sr=sr)
    assert isinstance(emb, np.ndarray)
    assert len(emb) == 100
    assert not np.all(emb == 0)


def test_estimate_num_speakers():
    rng = np.random.RandomState(42)
    c1 = rng.randn(5, 100) + 5.0
    c2 = rng.randn(5, 100) - 5.0
    emb_mat = np.vstack([c1, c2]).astype(np.float32)
    k, conf = estimate_num_speakers(emb_mat, min_speakers=1, max_speakers=4)
    assert k == 2
    assert conf > 0.0


def test_cluster_speaker_embeddings():
    rng = np.random.RandomState(42)
    c1 = rng.randn(4, 100) + 10.0
    c2 = rng.randn(4, 100) - 10.0
    emb_mat = np.vstack([c1, c2]).astype(np.float32)
    durations = [1.0] * 8
    labels = cluster_speaker_embeddings(emb_mat, num_speakers=2, segment_durations=durations)
    assert len(labels) == 8
    assert labels[0] == labels[1] == labels[2] == labels[3]
    assert labels[4] == labels[5] == labels[6] == labels[7]
    assert labels[0] != labels[4]


def test_diarize_segments_fallback_on_bad_audio(tmp_path):
    bad_wav = str(tmp_path / "empty.wav")
    with open(bad_wav, "wb") as f:
        f.write(b"not a wav")
    segs = [{"id": 1, "start": 0.0, "end": 1.0, "text": "test"}]
    res = diarize_segments(bad_wav, segs)
    assert len(res) == 1
    assert res[0]["speaker_id"] == 0


def test_diarize_segments_two_speakers(tmp_path):
    wav_path = str(tmp_path / "dialogue.wav")
    sr = 16000
    t1 = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    t2 = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    s1 = 0.6 * np.sin(2 * np.pi * 120.0 * t1)
    s2 = 0.6 * np.sin(2 * np.pi * 280.0 * t2)
    audio = np.concatenate([s1, s2])
    sig_int16 = (audio * 32767).astype(np.int16)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(sig_int16.tobytes())

    segments = [
        {"id": 1, "start": 0.2, "end": 1.8, "text": "Speaker 1 part 1"},
        {"id": 2, "start": 2.2, "end": 3.8, "text": "Speaker 2 part 1"},
    ]
    res = diarize_segments(wav_path, segments, num_speakers=2)
    assert len(res) == 2
    assert res[0]["speaker_id"] != res[1]["speaker_id"]


def test_speaker_voices_map_settings():
    s = Settings(speaker_voices='{"0": "male_1", "1": "female_1"}')
    spk_map = s.speaker_voices_map()
    assert spk_map == {0: "male_1", 1: "female_1"}


def test_dub_request_diarization_and_speaker_voices():
    from autodub.pipeline import DubRequest
    req = DubRequest(
        diarization_enabled=True,
        diarization_num_speakers=2,
        diarization_max_speakers=5,
        speaker_voices={0: "male_voice", 1: "female_voice"},
        aspect_preset="tiktok_9_16",
    )
    assert req.diarization_enabled is True
    assert req.diarization_num_speakers == 2
    assert req.diarization_max_speakers == 5
    assert req.speaker_voices[1] == "female_voice"
    assert req.aspect_preset == "tiktok_9_16"

