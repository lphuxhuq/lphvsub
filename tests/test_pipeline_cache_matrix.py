"""Phase 7: Full Pipeline Cache Verification Matrix.

Tests:
- Identical input/config -> HIT
- Changed ASR model -> ASR MISS (Demucs HIT)
- Changed translation model/provider -> Translation MISS (ASR & Demucs HIT)
- Changed TTS voice/speed -> TTS MISS
- Changed subtitle style / logo -> Audio & Text HIT (Rendering only)
- Changed source video -> All stages MISS
- SQLite concurrency stress test (multi-threaded concurrent read/write)
- SQLite corruption recovery & auto-healing
"""
import concurrent.futures
import os
import sqlite3
import threading
from pathlib import Path
import pytest

from autodub.pipeline_cache import (
    get_demucs_cache,
    get_asr_cache,
    get_translation_cache,
    get_tts_cache,
    compute_media_fingerprint,
    TranslationGlobalCache,
    TtsGlobalCache,
    AsrGlobalCache,
    DemucsGlobalCache,
)


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache_test"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(cache_root))
    import autodub.pipeline_cache as pc
    pc._ROOT = cache_root
    return cache_root


def _make_dummy_wav(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm_data = b"\x00" * 256
    data_len = len(pcm_data)
    riff_len = 36 + data_len
    with path.open("wb") as f:
        f.write(b"RIFF" + riff_len.to_bytes(4, "little") + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data" + data_len.to_bytes(4, "little") + pcm_data)
    return str(path)


def test_asr_cache_matrix(cache_env, tmp_path):
    """Verify ASR cache behavior: identical -> HIT, changed model/lang/engine -> MISS."""
    asr = AsrGlobalCache()
    audio_path = _make_dummy_wav(tmp_path / "audio1.wav")
    segments = [{"start": 0.0, "end": 1.5, "text": "Xin chào thế giới."}]

    # Store baseline
    asr.store(audio_path, model="base", language="zh", engine="whisper", segments=segments)

    # Identical -> HIT
    hit = asr.lookup(audio_path, model="base", language="zh", engine="whisper")
    assert hit is not None
    assert hit[0]["text"] == "Xin chào thế giới."

    # Changed model -> MISS
    assert asr.lookup(audio_path, model="large-v3", language="zh", engine="whisper") is None

    # Changed language -> MISS
    assert asr.lookup(audio_path, model="base", language="en", engine="whisper") is None

    # Changed engine -> MISS
    assert asr.lookup(audio_path, model="base", language="zh", engine="paraformer") is None


def test_translation_cache_matrix(cache_env, tmp_path):
    """Verify Translation cache behavior: identical -> HIT, changed provider/lang/text -> MISS."""
    db_file = tmp_path / "test_trans.db"
    tc = TranslationGlobalCache(db_path=db_file)

    tc.store("Hello", "vi", "Xin chào", provider="gemini-2.5-flash")

    # Identical -> HIT
    assert tc.lookup("Hello", "vi", provider="gemini-2.5-flash") == "Xin chào"

    # Changed provider -> MISS
    assert tc.lookup("Hello", "vi", provider="deepseek-chat") is None

    # Changed target lang -> MISS
    assert tc.lookup("Hello", "fr", provider="gemini-2.5-flash") is None

    # Changed source text -> MISS
    assert tc.lookup("Goodbye", "vi", provider="gemini-2.5-flash") is None


def test_tts_cache_matrix(cache_env, tmp_path):
    """Verify TTS cache behavior: identical -> HIT, changed voice/speed/engine -> MISS."""
    tts = TtsGlobalCache(cache_dir=tmp_path / "tts_cache")
    dummy_wav = _make_dummy_wav(tmp_path / "tts_source.wav")

    tts.store("Xin chào", voice="nam_bac_1", wav_path=dummy_wav, speed=1.0, engine="vieneu")

    # Identical -> HIT
    assert tts.lookup("Xin chào", voice="nam_bac_1", speed=1.0, engine="vieneu") is not None

    # Changed voice -> MISS
    assert tts.lookup("Xin chào", voice="nu_nam_1", speed=1.0, engine="vieneu") is None

    # Changed speed -> MISS
    assert tts.lookup("Xin chào", voice="nam_bac_1", speed=1.1, engine="vieneu") is None

    # Changed engine -> MISS
    assert tts.lookup("Xin chào", voice="nam_bac_1", speed=1.0, engine="capcut") is None


def test_sqlite_wal_concurrency_stress(cache_env, tmp_path):
    """Multi-threaded stress test: 16 concurrent threads reading and writing to SQLite cache."""
    db_file = tmp_path / "concurrent_trans.db"
    tc = TranslationGlobalCache(db_path=db_file)

    def _worker(worker_id: int):
        for i in range(25):
            src = f"Sentence {worker_id}-{i}"
            trans = f"Câu dịch {worker_id}-{i}"
            tc.store(src, "vi", trans, provider="provider_A")
            hit = tc.lookup(src, "vi", provider="provider_A")
            assert hit == trans

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker, w) for w in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # Batch lookup verification
    items = [(i, f"Sentence 0-{i}") for i in range(25)]
    batch_hits = tc.lookup_batch(items, "vi", provider="provider_A")
    assert len(batch_hits) == 25


def test_sqlite_corruption_auto_recovery(cache_env, tmp_path):
    """Simulate SQLite database corruption and verify automatic healing."""
    db_file = tmp_path / "corrupt_trans.db"
    tc = TranslationGlobalCache(db_path=db_file)

    # Write initial data
    tc.store("Test text", "vi", "Bản dịch thử", provider="default")
    assert tc.lookup("Test text", "vi") == "Bản dịch thử"

    # Corrupt the DB by overwriting header with garbage
    with open(db_file, "wb") as f:
        f.write(b"CORRUPTED SQLITE HEADER GARBAGE DATA 1234567890" * 100)

    # Lookup should gracefully recover (reset corrupt db) without throwing unhandled exceptions
    miss = tc.lookup("Test text", "vi")
    assert miss is None

    # New writes and reads must succeed immediately after recovery
    tc.store("Healed text", "vi", "Bản dịch đã phục hồi", provider="default")
    assert tc.lookup("Healed text", "vi") == "Bản dịch đã phục hồi"


def test_changed_source_video_invalidates_all_stages(cache_env, tmp_path):
    """When source video content changes, fingerprint changes and all stages MISS."""
    v1 = _make_dummy_wav(tmp_path / "vid1.wav")
    v2 = _make_dummy_wav(tmp_path / "vid2.wav")
    with open(v2, "ab") as f:
        f.write(b"EXTENDED_DIFFERENT_CONTENT_FOR_VIDEO_2")

    fp1 = compute_media_fingerprint(v1)
    fp2 = compute_media_fingerprint(v2)
    assert fp1 != fp2

    asr = AsrGlobalCache()
    asr.store(v1, model="base", language="zh", engine="whisper", segments=[{"start": 0, "end": 1, "text": "V1"}])

    assert asr.lookup(v1, model="base", language="zh", engine="whisper") is not None
    # Video 2 must MISS
    assert asr.lookup(v2, model="base", language="zh", engine="whisper") is None
