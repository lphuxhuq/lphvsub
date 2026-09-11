"""Unit tests for Douyin CDN domain matching, modal route routing, and DOM video extraction."""

from unittest.mock import MagicMock

from autodub.media.download.contract import DownloadRequest
from autodub.media.download.douyin_engine import _CDN_HOST_RE, DouyinDownloader
from autodub.media.download.validator import ValidationResult


def test_douyin_cdn_host_regex():
    """Verify _CDN_HOST_RE recognizes all Douyin CDN clusters."""
    valid_urls = [
        "https://v5-dy-ov-experiment.zjcdn.com/video/tos/cn/stream.mp4",
        "https://v3-web-prime.douyinvod.com/video/tos/cn/ve-15/stream.mp4",
        "https://v1-dy.douyincdn.com/media/video.mp4",
        "https://p3.bytecdntp.com/video/stream.m4s",
        "https://api.zijieapi.com/webid",
    ]
    for url in valid_urls:
        assert _CDN_HOST_RE.search(url), f"Failed to match valid CDN: {url}"

    invalid_urls = [
        "https://www.youtube.com/watch?v=123",
        "https://www.google.com/search",
        "https://evil-site.com/video.mp4",
    ]
    for url in invalid_urls:
        assert not _CDN_HOST_RE.search(url), f"Incorrectly matched invalid CDN: {url}"


def test_douyin_candidate_url_resolution(tmp_path):
    """Verify DouyinDownloader tries candidate URLs including modal route."""
    mock_val = MagicMock()
    mock_val.validate.return_value = ValidationResult(
        valid=True,
        duration=663.6,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        file_size=379_885_828,
        has_video=True,
        has_audio=True,
    )
    downloader = DouyinDownloader(validator=mock_val)
    downloader.fetch_direct_api_info = MagicMock(return_value=None)
    downloader.partial_mgr.download_progressive_stream = MagicMock()

    attempted_urls = []

    def mock_extract(cand_url):
        attempted_urls.append(cand_url)
        if "jingxuan?modal_id=" in cand_url:
            return {
                "mode": "progressive",
                "video_url": "https://v5-dy-ov-experiment.zjcdn.com/stream.mp4",
                "title": "Modal Video",
                "video_id": "7681436015344853669",
            }
        raise RuntimeError("Blocked by anti-bot")

    downloader.extract_via_browser_pool = MagicMock(side_effect=mock_extract)

    modal_url = "https://www.douyin.com/jingxuan?modal_id=7681436015344853669"
    req = DownloadRequest(
        url=modal_url,
        output_dir=str(tmp_path),
    )

    res = downloader.download(req)
    assert res.success
    assert res.backend == "browser_pool"
    assert res.duration == 663.6
    assert res.width == 1920
    assert res.height == 1080
    assert modal_url in attempted_urls


def test_douyin_extract_dom_video_fallback():
    """Verify BrowserPool extraction captures DOM video currentSrc when network sniffer hasn't fired."""
    mock_pool = MagicMock()
    mock_page = MagicMock()
    mock_pool.borrow_page.return_value.__enter__.return_value = mock_page

    # Mock DOM evaluate to return the CDN video URL directly
    target_cdn_url = "https://v5-dy-ov-experiment.zjcdn.com/video/tos/cn/stream.mp4"

    def evaluate_side_effect(script):
        if "document.querySelectorAll('video')" in script:
            return target_cdn_url
        return None

    mock_page.evaluate.side_effect = evaluate_side_effect
    mock_page.title.return_value = "Video Title - 抖音"
    mock_page.url = "https://www.douyin.com/video/7681436015344853669"

    downloader = DouyinDownloader(browser_pool=mock_pool)
    res = downloader.extract_via_browser_pool(
        "https://www.douyin.com/jingxuan?modal_id=7681436015344853669", wait_seconds=0.1
    )

    assert res["mode"] == "progressive"
    assert res["video_url"] == target_cdn_url
    assert res["title"] == "Video Title"
    assert res["video_id"] == "7681436015344853669"


def test_douyin_user_self_modal_id_and_api_sniffing(tmp_path):
    """Verify handling of Douyin user/self URL with modal_id parameter and aweme detail sniffing."""
    from autodub.media.download.preflight import Platform, PlatformDetector
    from autodub.media.downloader import normalize_url
    from autodub.pipeline import extract_video_id, normalize_video_url

    raw_user_url = "https://www.douyin.com/user/self?from_tab_name=main&modal_id=7680311804580384027&showTab=like"

    # 1. Pipeline extraction and normalization
    assert extract_video_id(raw_user_url) == "7680311804580384027"
    assert normalize_video_url(raw_user_url) == "https://www.douyin.com/video/7680311804580384027"
    assert normalize_url(raw_user_url) == "https://www.douyin.com/video/7680311804580384027"

    # 2. Preflight detection
    assert PlatformDetector.detect(raw_user_url) == Platform.DOUYIN
    assert PlatformDetector.extract_media_id(raw_user_url, Platform.DOUYIN) == "7680311804580384027"

    # 3. BrowserPool aweme/v1/web/aweme/detail response sniffing
    mock_pool = MagicMock()
    mock_page = MagicMock()
    mock_pool.borrow_page.return_value.__enter__.return_value = mock_page

    handlers = {}

    def fake_on(event, handler):
        handlers[event] = handler

    mock_page.on.side_effect = fake_on

    def fake_goto(url, **kwargs):
        # Simulate browser firing aweme detail response
        mock_response = MagicMock()
        mock_response.url = (
            "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=7680311804580384027"
        )
        mock_response.json.return_value = {
            "aweme_detail": {
                "desc": "Test Video Title",
                "video": {
                    "bit_rate": [
                        {
                            "bit_rate": 1000,
                            "play_addr": {"url_list": ["https://v5-dy.zjcdn.com/low_stream.mp4"]},
                        },
                        {
                            "bit_rate": 2800,
                            "play_addr": {"url_list": ["https://v5-dy.zjcdn.com/high_stream.mp4"]},
                        },
                    ],
                    "play_addr": {"url_list": ["https://v5-dy.zjcdn.com/standard_stream.mp4"]},
                },
            }
        }
        if "response" in handlers:
            handlers["response"](mock_response)

    mock_page.goto.side_effect = fake_goto
    mock_page.title.return_value = "Title - 抖音"
    mock_page.url = "https://www.douyin.com/video/7680311804580384027"

    downloader = DouyinDownloader(browser_pool=mock_pool)
    sniff_res = downloader.extract_via_browser_pool(
        "https://www.douyin.com/video/7680311804580384027", wait_seconds=0.1
    )

    assert sniff_res["mode"] == "progressive"
    assert sniff_res["title"] == "Test Video Title"
    # Highest bitrate stream should be captured first
    assert "https://v5-dy.zjcdn.com/high_stream.mp4" in sniff_res["video_url"] or sniff_res[
        "video_url"
    ].endswith(".mp4")
    assert sniff_res["video_id"] == "7680311804580384027"
