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


def test_get_optimized_opts_prefers_smaller_codecs():
    """Level 0 ưu tiên HEVC/AV1 (nhỏ hơn ~30-50%) trước chuỗi cũ; an toàn CDN
    giữ nguyên (retries/timeout/headers không đổi)."""
    opts = _get_optimized_opts("/tmp/dummy")
    fmt = opts["format"]
    hev = fmt.index("[vcodec^=hev]")
    av01 = fmt.index("[vcodec^=av01]")
    plain = fmt.index("bestvideo[height<=1080]+bestaudio[abr<=100]")
    assert hev < av01 < plain
    # concurrent fragments cho format phân mảnh (HLS); vô hại với DASH.
    assert opts["concurrent_fragment_downloads"] >= 2


def test_get_optimized_opts_fallback_level_unchanged():
    """Đường cứu lỗi 720p (fallback_level >= 1) giữ nguyên đúng chuỗi cũ."""
    opts = _get_optimized_opts("/tmp/dummy", fallback_level=1)
    assert opts["format"] == (
        "bestvideo[height<=720]+30232/"
        "bestvideo[height<=720]+30216/"
        "bestvideo[height<=720]+bestaudio/"
        "best[height<=720]/best"
    )
    assert opts["retries"] == 3
    assert opts["socket_timeout"] == 60


def test_download_one_isolated_moves_file_and_meta(tmp_path, monkeypatch):
    """Isolated download: file + video_meta.json về output_dir, tmp được dọn."""
    from autodub.media import downloader

    def fake_download_one(url, output_dir, cookies_from_browser=None,
                          cookies_file=None):
        tmp_dir = os.path.join(str(tmp_path), ".dl_tmp")
        video = os.path.join(tmp_dir, "BiliBili_BV1xx411c7mD.mp4")
        with open(video, "w") as f:
            f.write("data")
        meta_dir = os.path.join(tmp_dir, "data")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "video_meta.json"), "w") as f:
            f.write('{"title": "t"}')
        return {"input_url": url, "filepath": video}

    monkeypatch.setattr(downloader, "download_one", fake_download_one)
    entry = downloader.download_one_isolated(
        "https://www.bilibili.com/video/BV1xx411c7mD", str(tmp_path))

    dst = os.path.join(str(tmp_path), "BiliBili_BV1xx411c7mD.mp4")
    assert entry["filepath"] == dst
    assert os.path.isfile(dst)
    assert os.path.isfile(os.path.join(str(tmp_path), "data",
                                       "video_meta.json"))
    assert not os.path.exists(os.path.join(str(tmp_path), ".dl_tmp"))


def test_download_one_isolated_name_collision_no_overwrite(tmp_path,
                                                           monkeypatch):
    """Trùng tên (tải lại cùng video) → hậu tố thời gian, không ghi đè."""
    from autodub.media import downloader

    existing = os.path.join(str(tmp_path), "BiliBili_BV1xx411c7mD.mp4")
    with open(existing, "w") as f:
        f.write("old")

    def fake_download_one(url, output_dir, cookies_from_browser=None,
                          cookies_file=None):
        tmp_dir = os.path.join(str(tmp_path), ".dl_tmp")
        video = os.path.join(tmp_dir, "BiliBili_BV1xx411c7mD.mp4")
        with open(video, "w") as f:
            f.write("new")
        return {"input_url": url, "filepath": video}

    monkeypatch.setattr(downloader, "download_one", fake_download_one)
    entry = downloader.download_one_isolated("https://x", str(tmp_path))

    with open(existing) as f:
        assert f.read() == "old"          # bản gốc còn nguyên
    assert os.path.isfile(entry["filepath"])   # bản mới bên cạnh, tên khác
    assert entry["filepath"] != existing


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


def test_update_ytdlp_success(monkeypatch):
    from autodub.media.downloader import update_ytdlp
    class Ok:
        returncode = 0
        stderr = ""
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: Ok())
    assert update_ytdlp() is True


def test_update_ytdlp_failure(monkeypatch):
    from autodub.media.downloader import update_ytdlp
    class Bad:
        returncode = 1
        stderr = "error"
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: Bad())
    assert update_ytdlp() is False

