import json
import os
import threading
from pathlib import Path

import pytest

import autodub.pipeline_cache as pc
from autodub.pipeline_cache import (
    CACHE_VERSION,
    AsrGlobalCache,
    DemucsGlobalCache,
    _valid_wav,
    compute_media_fingerprint,
)


@pytest.fixture(autouse=True)
def setup_test_cache(tmp_path, monkeypatch):
    test_cache = tmp_path / "global_cache"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(test_cache))
    pc._ROOT = test_cache


def create_dummy_wav(path: Path, content: bytes = b"testdata") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"RIFF")
        total_size = len(content) + 44
        f.write((total_size - 8).to_bytes(4, "little"))
        f.write(b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data")
        f.write(len(content).to_bytes(4, "little"))
        f.write(content)
    return path


def test_fingerprint_is_deterministic(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"A" * 1024 * 100)
    fp1 = compute_media_fingerprint(str(path))
    fp2 = compute_media_fingerprint(str(path))
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA256 hex


def test_fingerprint_stable_across_mtime(tmp_path):
    path = tmp_path / "media.bin"
    path.write_bytes(b"header" + b"x" * 200_000 + b"footer")
    fp1 = compute_media_fingerprint(str(path))
    os.utime(path, (1234567890, 1234567890))
    fp2 = compute_media_fingerprint(str(path))
    assert fp1 == fp2


def test_fingerprint_detects_middle_content_changes(tmp_path):
    # Large file (> 4MB) to trigger multi-point sampling
    size = 6 * 1024 * 1024
    path1 = tmp_path / "media1.bin"
    path2 = tmp_path / "media2.bin"

    data1 = bytearray(b"0" * size)
    data2 = bytearray(b"0" * size)
    # Modify in the middle (50% mark)
    mid = size // 2
    data2[mid:mid + 100] = b"1" * 100

    path1.write_bytes(data1)
    path2.write_bytes(data2)

    fp1 = compute_media_fingerprint(str(path1))
    fp2 = compute_media_fingerprint(str(path2))
    assert fp1 != fp2, "Middle modification must change media fingerprint"


def test_fingerprint_detects_size_change(tmp_path):
    path1 = tmp_path / "file1.bin"
    path2 = tmp_path / "file2.bin"
    path1.write_bytes(b"abc" * 1000)
    path2.write_bytes(b"abc" * 1001)
    assert compute_media_fingerprint(str(path1)) != compute_media_fingerprint(str(path2))


def test_fingerprint_handles_empty_file(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    fp = compute_media_fingerprint(str(path))
    assert isinstance(fp, str) and len(fp) == 64


def test_fingerprint_raises_on_missing_file(tmp_path):
    missing = tmp_path / "non_existent.bin"
    with pytest.raises(FileNotFoundError):
        compute_media_fingerprint(str(missing))


def test_valid_wav_verification(tmp_path):
    # Valid WAV
    valid = create_dummy_wav(tmp_path / "valid.wav", b"x" * 200)
    assert _valid_wav(valid) is True

    # Truncated / tiny file
    tiny = tmp_path / "tiny.wav"
    tiny.write_bytes(b"RIFF1234")
    assert _valid_wav(tiny) is False

    # Corrupted header (starts with RIFF but not WAVE)
    not_wave = tmp_path / "not_wave.wav"
    not_wave.write_bytes(b"RIFF\x00\x00\x00\x00AVI \x00\x00" + b"x" * 200)
    assert _valid_wav(not_wave) is False

    # Missing file
    assert _valid_wav(tmp_path / "nonexistent.wav") is False


def test_cache_invalidation_on_config_change(tmp_path):
    audio = create_dummy_wav(tmp_path / "audio.wav", b"test_audio" * 100)
    vocals = create_dummy_wav(tmp_path / "vocals.wav", b"vocals" * 100)
    no_vocals = create_dummy_wav(tmp_path / "no_vocals.wav", b"no_vocals" * 100)

    cache = DemucsGlobalCache()
    cache.store_result(str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2)

    # Same config -> HIT
    hit = cache.lookup_and_restore(str(audio), str(tmp_path / "out1"), "htdemucs", 44100, 2)
    assert hit is not None

    # Different model -> MISS (invalidation)
    miss_model = cache.lookup_and_restore(str(audio), str(tmp_path / "out2"), "htdemucs_ft", 44100, 2)
    assert miss_model is None

    # Different sample rate -> MISS (invalidation)
    miss_sr = cache.lookup_and_restore(str(audio), str(tmp_path / "out3"), "htdemucs", 22050, 2)
    assert miss_sr is None

    # Different channels -> MISS (invalidation)
    miss_ch = cache.lookup_and_restore(str(audio), str(tmp_path / "out4"), "htdemucs", 44100, 1)
    assert miss_ch is None


def test_asr_cache_invalidation_and_corruption_recovery(tmp_path):
    audio = create_dummy_wav(tmp_path / "asr_audio.wav", b"audio" * 200)
    segments = [{"id": 0, "start": 0.0, "end": 1.5, "text": "hello"}]
    cache = AsrGlobalCache()

    # Store
    cache.store(str(audio), "paraformer", "zh", "funasr", segments)

    # Hit
    hit = cache.lookup(str(audio), "paraformer", "zh", "funasr")
    assert hit == segments

    # Miss on language change
    assert cache.lookup(str(audio), "paraformer", "en", "funasr") is None

    # Miss on model change
    assert cache.lookup(str(audio), "whisper-large", "zh", "funasr") is None

    # Corrupt the cache file directly
    cache_file = cache._path(str(audio), "paraformer", "zh", "funasr")
    assert cache_file.exists()
    cache_file.write_text("{invalid json garbage...", encoding="utf-8")

    # Lookup should detect corruption, remove the bad file, and return None safely
    recovered = cache.lookup(str(audio), "paraformer", "zh", "funasr")
    assert recovered is None
    assert not cache_file.exists(), "Corrupted cache file must be unlinked"


def test_demucs_corruption_recovery_truncated_wav(tmp_path):
    audio = create_dummy_wav(tmp_path / "audio.wav", b"test_audio" * 100)
    vocals = create_dummy_wav(tmp_path / "vocals.wav", b"vocals" * 100)
    no_vocals = create_dummy_wav(tmp_path / "no_vocals.wav", b"no_vocals" * 100)

    cache = DemucsGlobalCache()
    cache.store_result(str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2)

    # Locate stored cache bucket
    key = cache._key(str(audio), "htdemucs", 44100, 2)
    bucket = pc._ROOT / "demucs" / key
    assert bucket.exists()

    # Corrupt vocals.wav in cache
    (bucket / "vocals.wav").write_bytes(b"CORRUPTED_NOT_A_WAV")

    out_dir = tmp_path / "restored_out"
    hit = cache.lookup_and_restore(str(audio), str(out_dir), "htdemucs", 44100, 2)
    assert hit is None, "Corrupted cache item must result in a cache MISS"


def test_concurrent_access_thread_safety(tmp_path):
    audio = create_dummy_wav(tmp_path / "thread_audio.wav", b"audio" * 500)
    vocals = create_dummy_wav(tmp_path / "thread_vocals.wav", b"vocals" * 500)
    no_vocals = create_dummy_wav(tmp_path / "thread_no_vocals.wav", b"no_vocals" * 500)

    cache = DemucsGlobalCache()
    errors = []

    def worker(idx):
        try:
            cache.store_result(str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2)
            out = tmp_path / f"thread_out_{idx}"
            res = cache.lookup_and_restore(str(audio), str(out), "htdemucs", 44100, 2)
            if not res or not Path(res["vocals"]).exists():
                errors.append(f"Worker {idx} failed to lookup/restore")
        except Exception as e:
            errors.append(f"Worker {idx} raised exception: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent access had errors: {errors}"
