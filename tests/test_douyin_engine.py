"""Tests for DouyinDownloader engine."""

from unittest.mock import MagicMock

from autodub.media.download.contract import DownloadRequest
from autodub.media.download.douyin_engine import DouyinDownloader
from autodub.media.download.validator import ValidationResult


def test_douyin_extract_video_id():
    assert (
        DouyinDownloader.extract_video_id("https://www.douyin.com/video/7123456789012345678")
        == "7123456789012345678"
    )
    assert (
        DouyinDownloader.extract_video_id("https://www.douyin.com/note/7987654321098765432")
        == "7987654321098765432"
    )
    assert (
        DouyinDownloader.extract_video_id(
            "https://www.douyin.com/user/MS4w?modal_id=7111222333444555666"
        )
        == "7111222333444555666"
    )


def test_douyin_download_direct_api_success(tmp_path):
    mock_val = MagicMock()
    mock_val.validate.return_value = ValidationResult(
        valid=True,
        duration=15.0,
        width=1080,
        height=1920,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        file_size=5_000_000,
        has_video=True,
        has_audio=True,
    )

    downloader = DouyinDownloader(validator=mock_val)

    downloader.fetch_direct_api_info = MagicMock(
        return_value={
            "play_url": "https://aweme.snssdk.com/play/video.mp4",
            "uri": "v0200fg10000abc",
            "title": "Test Douyin Video",
            "duration": 15.0,
        }
    )

    downloader.partial_mgr.download_progressive_stream = MagicMock()

    req = DownloadRequest(
        url="https://www.douyin.com/video/7123456789012345678",
        output_dir=str(tmp_path),
    )

    result = downloader.download(req)
    assert result.success
    assert result.media_id == "7123456789012345678"
    assert result.backend == "direct_api"
    assert result.duration == 15.0
    assert result.validation_passed


def test_douyin_download_fallback_to_browser_pool(tmp_path):
    mock_val = MagicMock()
    mock_val.validate.return_value = ValidationResult(
        valid=True,
        duration=20.0,
        width=720,
        height=1280,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        file_size=4_000_000,
        has_video=True,
        has_audio=True,
    )

    downloader = DouyinDownloader(validator=mock_val)

    downloader.fetch_direct_api_info = MagicMock(return_value=None)

    downloader.extract_via_browser_pool = MagicMock(
        return_value={
            "mode": "progressive",
            "video_url": "https://v3-dy-y.douyinvod.com/stream.mp4",
            "title": "Captured Video",
            "video_id": "7123456789012345678",
        }
    )
    downloader.partial_mgr.download_progressive_stream = MagicMock()

    req = DownloadRequest(
        url="https://www.douyin.com/video/7123456789012345678",
        output_dir=str(tmp_path),
    )

    result = downloader.download(req)
    assert result.success
    assert result.backend == "browser_pool"
    assert result.duration == 20.0
    assert result.validation_passed
