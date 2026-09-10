import os
import sqlite3
import threading
from pathlib import Path
import pytest

import autodub.pipeline_cache as pc
from autodub.pipeline_cache import TranslationGlobalCache


@pytest.fixture(autouse=True)
def setup_test_cache(tmp_path, monkeypatch):
    test_cache = tmp_path / "global_cache"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(test_cache))
    pc._ROOT = test_cache


def test_translation_cache_roundtrip(tmp_path):
    cache = TranslationGlobalCache()
    assert cache.lookup("Hello world", "vi", "gemini") is None

    cache.store("Hello world", "vi", "Xin chào thế giới", "gemini")
    hit = cache.lookup("Hello world", "vi", "gemini")
    assert hit == "Xin chào thế giới"


def test_translation_cache_batch(tmp_path):
    cache = TranslationGlobalCache()
    items_to_store = [
        ("Good morning", "Chào buổi sáng"),
        ("Good afternoon", "Chào buổi chiều"),
        ("Good night", "Chúc ngủ ngon"),
    ]
    cache.store_batch(items_to_store, "vi", "gemini")

    query_items = [
        (0, "Good morning"),
        (1, "Unknown phrase"),
        (2, "Good night"),
    ]
    hits = cache.lookup_batch(query_items, "vi", "gemini")
    assert len(hits) == 2
    assert hits[0] == "Chào buổi sáng"
    assert hits[2] == "Chúc ngủ ngon"
    assert 1 not in hits


def test_translation_cache_invalidation(tmp_path):
    cache = TranslationGlobalCache()
    cache.store("One", "vi", "Một", "gemini")

    # Hit
    assert cache.lookup("One", "vi", "gemini") == "Một"
    # Miss on target language
    assert cache.lookup("One", "fr", "gemini") is None
    # Miss on provider
    assert cache.lookup("One", "vi", "deepseek") is None


def test_translation_cache_corruption_recovery(tmp_path):
    cache = TranslationGlobalCache()
    cache.store("Test", "vi", "Thử nghiệm", "gemini")
    assert cache.lookup("Test", "vi", "gemini") == "Thử nghiệm"

    # Corrupt database file
    db_file = pc.cache_root() / "translate" / "translations.db"
    assert db_file.exists()
    db_file.write_bytes(b"CORRUPTED_GARBAGE_SQLITE_HEADER")

    # Should detect corruption, safely reset, and return None without crash
    res = cache.lookup("Test", "vi", "gemini")
    assert res is None

    # Should allow storing again after recovery
    cache.store("Test2", "vi", "Thử nghiệm 2", "gemini")
    assert cache.lookup("Test2", "vi", "gemini") == "Thử nghiệm 2"


def test_translation_cache_concurrent_access(tmp_path):
    cache = TranslationGlobalCache()
    errors = []

    def worker(idx):
        try:
            for j in range(20):
                text = f"Sentence_{idx}_{j}"
                trans = f"Cau_{idx}_{j}"
                cache.store(text, "vi", trans, "gemini")
                val = cache.lookup(text, "vi", "gemini")
                if val != trans:
                    errors.append(f"Mismatch: got {val}, expected {trans}")
        except Exception as e:
            errors.append(f"Worker {idx} error: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent translation errors: {errors}"
