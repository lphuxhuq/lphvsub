"""Tests for BilibiliDownloader engine."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autodub.media.download.bilibili_engine import BilibiliDownloader
from autodub.media.download.contract import DownloadRequest, DownloadResult
from autodub.media.download.validator import ValidationResult


def test_bilibili_extract_bvid_and_page():
    assert BilibiliDownloader.extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD") == "BV1xx411c7mD"
    assert BilibiliDownloader.extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD?p=2") == "BV1xx411c7mD"
    assert BilibiliDownloader.extract_page_index("https://www.bilibili.com/video/BV1xx411c7mD?p=3") == 3
    assert BilibiliDownloader.extract_page_index("https://www.bilibili.com/video/BV1xx411c7mD") == 1


def test_bilibili_download_dash_success(tmp_path):
    mock_val = MagicMock()
    mock_val.validate.return_value = ValidationResult(
        valid=True,
        duration=60.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="hevc",
        audio_codec="aac",
        file_size=20_000_000,
        has_video=True,
        has_audio=True,
    )

    downloader = BilibiliDownloader(validator=mock_val)

    downloader.fetch_video_view = MagicMock(return_value={
        "cid": 99999,
        "title": "Bilibili Test Video",
        "pages": [{"cid": 99999, "page": 1}],
    })

    downloader.fetch_playurl = MagicMock(return_value={
        "dash": {
            "video": [
                {"bandwidth": 5000000, "baseUrl": "https://upos-ali.bilivideo.com/v.m4s", "backupUrl": ["https://upos-cos.bilivideo.com/v.m4s"]},
            ],
            "audio": [
                {"bandwidth": 320000, "baseUrl": "https://upos-ali.bilivideo.com/a.m4s", "backupUrl": []},
            ]
        }
    })

    def fake_download_stream(url, target_path, **kwargs):
        p = Path(target_path)
        p.write_bytes(b"M4S_STREAM" * 100)
        return p

    downloader.partial_mgr.download_progressive_stream = MagicMock(side_effect=fake_download_stream)
    downloader.mux_dash = MagicMock(return_value=tmp_path / "bilibili_BV1xx411c7mD.mp4")

    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        output_dir=str(tmp_path),
    )

    result = downloader.download(req)
    assert result.success
    assert result.media_id == "BV1xx411c7mD"
    assert result.backend == "dash"
    assert result.duration == 60.0
    assert result.validation_passed


def test_bilibili_fallback_to_ytdlp_on_api_error(tmp_path):
    downloader = BilibiliDownloader()
    downloader.fetch_video_view = MagicMock(side_effect=RuntimeError("WBI signature required"))

    expected_result = DownloadResult(
        success=True,
        path=str(tmp_path / "fallback.mp4"),
        media_id="BV1xx411c7mD",
        backend="ytdlp_fallback",
        duration=45.0,
        validation_passed=True,
    )
    downloader._download_via_ytdlp_fallback = MagicMock(return_value=expected_result)

    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        output_dir=str(tmp_path),
    )

    result = downloader.download(req)
    assert result.success
    assert result.backend == "ytdlp_fallback"
    assert result.duration == 45.0
