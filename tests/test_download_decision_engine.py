"""Tests for DownloadDecisionEngine."""

from unittest.mock import MagicMock

from autodub.media.download.contract import (
    DownloadRequest,
    DownloadResult,
    ErrorType,
    Platform,
)
from autodub.media.download.decision_engine import DownloadDecisionEngine
from autodub.media.download.validator import ValidationResult


def test_decision_engine_cancellation():
    engine = DownloadDecisionEngine()
    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        output_dir="tmp",
        cancel_event=True,  # immediately cancelled
    )
    res = engine.execute(req)
    assert not res.success
    assert res.error_type == ErrorType.CANCELLED


def test_decision_engine_cache_hit(tmp_path):
    mock_val = MagicMock()
    mock_val.validate.return_value = ValidationResult(
        valid=True,
        duration=30.0,
        file_size=10_000,
        width=1280,
        height=720,
    )

    mock_cache = MagicMock()
    cached_file = tmp_path / "cached_video.mp4"
    cached_file.write_bytes(b"CACHED_CONTENT" * 50)
    mock_cache.lookup.return_value = cached_file

    engine = DownloadDecisionEngine(validator=mock_val, cache=mock_cache)

    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        output_dir=str(tmp_path),
        use_cache=True,
    )

    res = engine.execute(req)
    assert res.success
    assert res.cache_hit
    assert res.path == str(cached_file)
    assert res.backend == "cache"
    assert res.duration == 30.0


def test_decision_engine_routes_to_bilibili(tmp_path):
    mock_bili = MagicMock()
    expected_bili_res = DownloadResult(
        success=True,
        path=str(tmp_path / "bili.mp4"),
        platform=Platform.BILIBILI.value,
        media_id="BV1xx411c7mD",
        duration=120.0,
        backend="dash",
    )
    mock_bili.download.return_value = expected_bili_res

    # Create the dummy file so cache/perf can record it
    (tmp_path / "bili.mp4").write_bytes(b"DATA" * 50)

    engine = DownloadDecisionEngine(bilibili_engine=mock_bili)
    engine.cache.lookup = MagicMock(return_value=None)  # Cache miss

    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        output_dir=str(tmp_path),
    )

    res = engine.execute(req)
    assert res.success
    assert res.platform == Platform.BILIBILI.value
    assert res.backend == "dash"
    mock_bili.download.assert_called_once()


def test_decision_engine_routes_to_douyin(tmp_path):
    mock_dy = MagicMock()
    expected_dy_res = DownloadResult(
        success=True,
        path=str(tmp_path / "dy.mp4"),
        platform=Platform.DOUYIN.value,
        media_id="7123456789",
        duration=15.0,
        backend="direct_api",
    )
    mock_dy.download.return_value = expected_dy_res

    (tmp_path / "dy.mp4").write_bytes(b"DATA" * 50)

    engine = DownloadDecisionEngine(douyin_engine=mock_dy)
    engine.cache.lookup = MagicMock(return_value=None)

    req = DownloadRequest(
        url="https://www.douyin.com/video/7123456789",
        output_dir=str(tmp_path),
    )

    res = engine.execute(req)
    assert res.success
    assert res.platform == Platform.DOUYIN.value
    assert res.backend == "direct_api"
    mock_dy.download.assert_called_once()
