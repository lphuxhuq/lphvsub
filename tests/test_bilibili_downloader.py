"""Tests for Bilibili and general video downloader improvements."""
import os
import tempfile
import pytest

from autodub.media.downloader import (
    normalize_url,
    _get_optimized_opts,
    _is_partial_name,
    _resolve_filepath,
)


def test_normalize_url_bilibili_raw_text():
    """Test extracting clean URL from raw Bilibili app share text with Chinese characters."""
    raw = "【某某精彩视频】https://www.bilibili.com/video/BV1xx411c7mD 复制此链接，打开B站"
    res = normalize_url(raw)
    assert res == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_normalize_url_bilibili_tracking_params():
    """Test stripping tracking parameters while keeping essential params like pagination."""
    url = "https://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.999.0.0&vd_source=abc1234&p=2&share_source=copy_web"
    res = normalize_url(url)
    assert "BV1xx411c7mD" in res
    assert "p=2" in res
    assert "spm_id_from" not in res
    assert "vd_source" not in res
    assert "share_source" not in res


def test_normalize_url_douyin_regression():
    """Test Douyin modal URL normalization still works as expected."""
    raw = "https://www.douyin.com/jingxuan?modal_id=7123456789012345678"
    res = normalize_url(raw)
    assert res == "https://www.douyin.com/video/7123456789012345678"


def test_normalize_url_youtube():
    """Test standard YouTube URL is preserved."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    res = normalize_url(url)
    assert res == url


def test_get_optimized_opts_headers():
    """Test that _get_optimized_opts includes proper User-Agent and Referer headers."""
    opts = _get_optimized_opts("/tmp/dummy")
    assert "http_headers" in opts
    assert "User-Agent" in opts["http_headers"]
    assert "Referer" in opts["http_headers"]
    assert "bilibili.com" in opts["http_headers"]["Referer"]
    assert opts["noplaylist"] is True
    assert "merge_output_format" in opts


def test_is_partial_name():
    """Test detection of partial/intermediate download files."""
    assert _is_partial_name("video.part") is True
    assert _is_partial_name("video.ytdl") is True
    assert _is_partial_name("video.temp") is True
    assert _is_partial_name("BV1xx411c7mD.f100023.mp4") is True
    assert _is_partial_name("BV1xx411c7mD.f30232.m4a") is True
    assert _is_partial_name("BV1xx411c7mD.mp4") is False
    assert _is_partial_name("BV1xx411c7mD_p1.mp4") is False
    assert _is_partial_name("BiliBili_BV1xx411c7mD.mp4") is False


def test_resolve_filepath_direct_and_multipart(tmp_path):
    """Test filepath resolution with exact match and multi-part _p1 fallback."""
    out_dir = str(tmp_path)

    # 1. Exact match with extractor prefix
    target_file = os.path.join(out_dir, "BiliBili_BV1xx411c7mD.mp4")
    with open(target_file, "w") as f:
        f.write("dummy")

    info = {
        "extractor_key": "BiliBili",
        "id": "BV1xx411c7mD",
        "ext": "mp4",
    }
    resolved = _resolve_filepath(info, out_dir)
    assert resolved == target_file

    # 2. Multi-part file resolution (_p1 suffix)
    os.remove(target_file)
    p1_file = os.path.join(out_dir, "BiliBili_BV17x411w7KC_p1.mp4")
    with open(p1_file, "w") as f:
        f.write("dummy")

    info_p1 = {
        "extractor_key": "BiliBili",
        "id": "BV17x411w7KC",
        "ext": "mp4",
    }
    resolved_p1 = _resolve_filepath(info_p1, out_dir)
    assert resolved_p1 == p1_file
