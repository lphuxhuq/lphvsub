"""Tests for DownloadCache and PerformanceStore."""

from unittest.mock import MagicMock

from autodub.media.download.cache import DownloadCache
from autodub.media.download.performance_store import PerformanceStore
from autodub.media.download.validator import MediaValidator, ValidationResult


def test_performance_store(tmp_path):
    db_file = tmp_path / "perf.db"
    store = PerformanceStore(db_path=db_file)

    store.record_metric(
        platform="bilibili",
        host="cdn-fast.bili.com",
        bytes_transferred=10_000_000,
        duration=1.0,
        success=True,
    )
    store.record_metric(
        platform="bilibili",
        host="cdn-fast.bili.com",
        bytes_transferred=10_000_000,
        duration=1.0,
        success=True,
    )

    store.record_metric(
        platform="bilibili",
        host="cdn-slow.bili.com",
        bytes_transferred=1_000_000,
        duration=1.0,
        success=True,
    )
    store.record_metric(
        platform="bilibili",
        host="cdn-slow.bili.com",
        bytes_transferred=0,
        duration=0.5,
        success=False,
        error_type="rate_limit",
        status_code=429,
    )

    fast_score = store.get_health_score("bilibili", "cdn-fast.bili.com")
    assert fast_score == 100.0

    slow_score = store.get_health_score("bilibili", "cdn-slow.bili.com")
    assert slow_score < 50.0

    fastest = store.get_fastest_cdns("bilibili")
    assert len(fastest) >= 1
    assert fastest[0] == "cdn-fast.bili.com"


def test_download_cache_hit_and_eviction(tmp_path):
    cache_db = tmp_path / "cache.db"
    mock_validator = MagicMock(spec=MediaValidator)

    cache = DownloadCache(db_path=cache_db, validator=mock_validator)

    assert cache.lookup("douyin", "12345") is None

    media_file = tmp_path / "test_media.mp4"
    media_file.write_bytes(b"DATA" * 500)

    cache.store("douyin", "12345", media_file, duration=10.0)

    mock_validator.validate.return_value = ValidationResult(valid=True, duration=10.0)
    hit_path = cache.lookup("douyin", "12345")
    assert hit_path == media_file

    mock_validator.validate.return_value = ValidationResult(valid=False, error_message="Corrupted")
    hit_corrupted = cache.lookup("douyin", "12345")
    assert hit_corrupted is None

    mock_validator.validate.return_value = ValidationResult(valid=True)
    assert cache.lookup("douyin", "12345") is None
