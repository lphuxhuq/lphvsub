import os
import threading
from pathlib import Path
import pytest

import autodub.pipeline_cache as pc
from autodub.pipeline_cache import TtsGlobalCache, _valid_wav


@pytest.fixture(autouse=True)
def setup_test_cache(tmp_path, monkeypatch):
    test_cache = tmp_path / "global_cache"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(test_cache))
    pc._ROOT = test_cache


def create_dummy_wav(path: Path, content: bytes = b"tts_audio_content_test" * 20) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"RIFF")
        total_size = len(content) + 44
        f.write((total_size - 8).to_bytes(4, "little"))
        f.write(b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data")
        f.write(len(content).to_bytes(4, "little"))
        f.write(content)
    return path


def test_tts_cache_store_and_restore(tmp_path):
    cache = TtsGlobalCache()
    sample_wav = create_dummy_wav(tmp_path / "src.wav", b"speech123_valid_bytes" * 15)

    text = "Xin chào các bạn"
    voice = "nam_bac_1"

    # Initial lookup miss
    assert cache.lookup(text, voice) is None

    # Store
    cache.store(text, voice, str(sample_wav))

    # Lookup hit
    hit_path = cache.lookup(text, voice)
    assert hit_path is not None
    assert _valid_wav(hit_path)

    # Restore to target
    dst = tmp_path / "output_segment.wav"
    ok = cache.restore_to(text, voice, str(dst))
    assert ok is True
    assert dst.exists()
    assert _valid_wav(dst)


def test_tts_cache_invalidation_on_voice_or_speed(tmp_path):
    cache = TtsGlobalCache()
    sample_wav = create_dummy_wav(tmp_path / "src.wav", b"speech456_valid_bytes" * 15)

    text = "Câu thoại thử nghiệm"
    voice = "nam_bac_1"
    cache.store(text, voice, str(sample_wav), speed=1.0)

    # Hit same voice & speed
    assert cache.lookup(text, voice, speed=1.0) is not None

    # Miss on different voice
    assert cache.lookup(text, "nu_nam_1", speed=1.0) is None

    # Miss on different speed
    assert cache.lookup(text, voice, speed=1.2) is None

    # Miss on different engine
    assert cache.lookup(text, voice, speed=1.0, engine="capcut") is None


def test_tts_cache_corruption_recovery(tmp_path):
    cache = TtsGlobalCache()
    sample_wav = create_dummy_wav(tmp_path / "src.wav", b"valid_speech_bytes" * 15)
    text = "Câu thoại lỗi"
    voice = "nam_bac_1"

    cache.store(text, voice, str(sample_wav))
    hit = cache.lookup(text, voice)
    assert hit is not None

    # Corrupt the cache file
    hit.write_bytes(b"CORRUPTED_TRUNCATED")

    # Next lookup must detect corruption, clean it up, and return None
    assert cache.lookup(text, voice) is None
    assert not hit.exists(), "Corrupted cache file should be unlinked"


def test_tts_cache_concurrency(tmp_path):
    cache = TtsGlobalCache()
    sample_wav = create_dummy_wav(tmp_path / "src.wav", b"thread_speech_bytes" * 15)
    errors = []

    def worker(idx):
        try:
            for j in range(10):
                text = f"Text_{idx}_{j}"
                voice = f"voice_{idx}"
                cache.store(text, voice, str(sample_wav))
                dst = tmp_path / f"thread_{idx}_{j}.wav"
                if not cache.restore_to(text, voice, str(dst)):
                    errors.append(f"Worker {idx} failed restore")
        except Exception as e:
            errors.append(f"Worker {idx} raised: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent TTS cache errors: {errors}"
