"""Tests for CookieSessionManager."""

from autodub.media.download.contract import Platform
from autodub.media.download.session_manager import CookieSessionManager


def test_platform_headers():
    mgr = CookieSessionManager()
    bili_headers = mgr.get_headers(Platform.BILIBILI)
    assert "bilibili.com" in bili_headers["Referer"]
    assert "User-Agent" in bili_headers

    douyin_headers = mgr.get_headers(Platform.DOUYIN)
    assert "douyin.com" in douyin_headers["Referer"]


def test_load_cookie_file(tmp_path):
    mgr = CookieSessionManager()
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tabc123456789xyz\n"
        ".douyin.com\tTRUE\t/\tTRUE\t2147483647\tttwid\t1234567890\n",
        encoding="utf-8"
    )

    jar = mgr.load_cookie_file(cookie_file)
    assert mgr.has_bilibili_auth(jar)
    assert mgr.has_douyin_auth(jar)


def test_mask_sensitive_headers():
    mgr = CookieSessionManager()
    raw = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": "SESSDATA=secret_token_12345; ttwid=abc",
        "Authorization": "Bearer supersecret",
        "Accept": "*/*",
    }
    masked = mgr.mask_headers(raw)
    assert masked["User-Agent"] == "Mozilla/5.0"
    assert masked["Accept"] == "*/*"
    assert masked["Cookie"] == "***MASKED***"
    assert masked["Authorization"] == "***MASKED***"


def test_create_session_with_cookies(tmp_path):
    mgr = CookieSessionManager()
    cookie_file = tmp_path / "bili_cookie.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tvalid_sessdata_string_xyz\n",
        encoding="utf-8"
    )

    session = mgr.create_session(platform=Platform.BILIBILI, cookie_file=cookie_file)
    assert "bilibili.com" in session.headers["Referer"]
    assert any(c.name == "SESSDATA" for c in session.cookies)
