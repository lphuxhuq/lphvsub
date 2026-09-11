"""Tests for CdnRacingEngine and PreflightAnalyzer."""

from unittest.mock import MagicMock

from autodub.media.download.cdn_racer import CdnRacingEngine
from autodub.media.download.contract import Platform
from autodub.media.download.preflight import PlatformDetector, PreflightAnalyzer


def test_platform_detector():
    detector = PlatformDetector()

    assert detector.detect("https://www.bilibili.com/video/BV1xx411c7mD") == Platform.BILIBILI
    assert detector.detect("https://b23.tv/BV1xx411c7mD") == Platform.BILIBILI
    assert (
        detector.extract_media_id("https://www.bilibili.com/video/BV1xx411c7mD") == "BV1xx411c7mD"
    )

    assert detector.detect("https://www.douyin.com/video/7123456789012345678") == Platform.DOUYIN
    assert detector.detect("https://v.douyin.com/iJklmno/") == Platform.DOUYIN
    assert (
        detector.extract_media_id("https://www.douyin.com/video/7123456789012345678")
        == "7123456789012345678"
    )

    assert detector.detect("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == Platform.YOUTUBE
    assert detector.extract_media_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    assert detector.detect("https://example.com/stream.mp4") == Platform.GENERIC


def test_preflight_analyzer_recommendations():
    analyzer = PreflightAnalyzer()

    bili_res = analyzer.analyze("https://www.bilibili.com/video/BV1xx411c7mD")
    assert bili_res.platform == Platform.BILIBILI
    assert bili_res.media_id == "BV1xx411c7mD"
    assert bili_res.is_dash
    assert bili_res.recommended_backend == "dash"

    dy_res = analyzer.analyze("https://www.douyin.com/video/7123456789012345678")
    assert dy_res.platform == Platform.DOUYIN
    assert dy_res.recommended_backend == "direct"


def test_cdn_racing_ranks_faster_candidate_first():
    racer = CdnRacingEngine()

    candidates = [
        "https://cdn-slow.bili.com/video.m4s",
        "https://cdn-fast.bili.com/video.m4s",
        "https://cdn-error.bili.com/video.m4s",
    ]

    session = MagicMock()

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raw.read.return_value = b"M4S_HEADER"
        if "fast" in url:
            resp.status_code = 206
            resp.headers = {"Content-Length": "1000", "Accept-Ranges": "bytes"}
        elif "slow" in url:
            import time

            time.sleep(0.02)
            resp.status_code = 206
            resp.headers = {"Content-Length": "1000"}
        else:
            resp.status_code = 500
            resp.headers = {}
        return resp

    session.get.side_effect = mock_get

    ranked = racer.race_candidates(candidates, session)
    assert len(ranked) == 3
    assert ranked[0].host == "cdn-fast.bili.com"
    assert ranked[0].status_code == 206
    assert ranked[-1].host == "cdn-error.bili.com"
    assert ranked[-1].status_code == 500
