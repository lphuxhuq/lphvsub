from pathlib import Path

import pytest

import autodub.pipeline_cache as pc
from autodub.pipeline_cache import (
    get_pipeline_orchestrator,
)


@pytest.fixture(autouse=True)
def setup_test_cache(tmp_path, monkeypatch):
    test_cache = tmp_path / "global_cache"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(test_cache))
    pc._ROOT = test_cache


def create_dummy_wav(path: Path, content: bytes = b"wav_orchestrator_bytes" * 15) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"RIFF")
        total_size = len(content) + 44
        f.write((total_size - 8).to_bytes(4, "little"))
        f.write(
            b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data"
        )
        f.write(len(content).to_bytes(4, "little"))
        f.write(content)
    return path


def test_orchestrator_inspect_video_cache(tmp_path):
    orch = get_pipeline_orchestrator()

    audio = create_dummy_wav(tmp_path / "video_audio.wav")
    status = orch.inspect_cache(str(audio), lang="zh", asr_model="base", voice="nam_bac_1")
    assert status["demucs"] is False
    assert status["asr"] is False

    # Populate demucs
    vocals = create_dummy_wav(tmp_path / "v.wav")
    no_vocals = create_dummy_wav(tmp_path / "nv.wav")
    pc.get_demucs_cache().store_result(
        str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2
    )

    # Populate asr
    pc.get_asr_cache().store(
        str(audio), "base", "zh", "whisper", [{"start": 0, "end": 1, "text": "hello"}]
    )

    status2 = orch.inspect_cache(str(audio), lang="zh", asr_model="base", voice="nam_bac_1")
    assert status2["demucs"] is True
    assert status2["asr"] is True
    assert "fingerprint" in status2


def test_orchestrator_cache_stats_and_clean(tmp_path):
    orch = get_pipeline_orchestrator()

    audio = create_dummy_wav(tmp_path / "video_audio.wav")
    vocals = create_dummy_wav(tmp_path / "v.wav")
    no_vocals = create_dummy_wav(tmp_path / "nv.wav")
    pc.get_demucs_cache().store_result(
        str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2
    )

    stats = orch.cache_stats()
    assert stats["demucs_entries"] >= 1
    assert stats["total_bytes"] > 0

    # Prune/clean
    cleaned = orch.clean_cache(category="demucs", max_age_seconds=0)
    assert cleaned["removed_entries"] >= 1


def test_orchestrator_validate_and_heal(tmp_path):
    orch = get_pipeline_orchestrator()

    # Create corrupted demucs bucket
    corrupt_bucket = pc.cache_root() / "demucs" / "bad_bucket"
    corrupt_bucket.mkdir(parents=True, exist_ok=True)
    (corrupt_bucket / "vocals.wav").write_bytes(b"BAD_WAV_HEADER")
    (corrupt_bucket / "no_vocals.wav").write_bytes(b"BAD_WAV_HEADER")

    # Create corrupted asr json
    corrupt_asr = pc.cache_root() / "asr" / "bad_asr.json"
    corrupt_asr.parent.mkdir(parents=True, exist_ok=True)
    corrupt_asr.write_text("INVALID_JSON_CONTENT{", encoding="utf-8")

    # Create corrupted tts wav
    corrupt_tts = pc.cache_root() / "tts" / "bad_tts.wav"
    corrupt_tts.parent.mkdir(parents=True, exist_ok=True)
    corrupt_tts.write_bytes(b"NOT_WAV")

    res = orch.validate_and_heal()
    assert res["scanned"] >= 3
    assert res["corrupted_cleaned"] >= 3
    assert not corrupt_bucket.exists()
    assert not corrupt_asr.exists()
    assert not corrupt_tts.exists()
