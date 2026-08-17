"""Video download via yt-dlp, with Douyin routed through Playwright."""
import os
import re
from urllib.parse import urlparse, parse_qs

import yt_dlp

from autodub.utils import setup_logging, ensure_dir, save_json_atomic

logger = setup_logging("autodub.downloader")


def _save_meta(output_dir: str, title: str, uploader: str = "") -> None:
    """Lưu title/uploader vào ``data/video_meta.json`` cạnh video tải về.

    Title là ngữ cảnh miễn phí, giá trị cao cho bước phân tích/dịch/metadata —
    trước đây bị vứt đi ngay sau khi tải. Best-effort: lỗi ghi không được
    làm hỏng lượt tải.
    """
    title = (title or "").strip()
    if not title:
        return
    try:
        from autodub.workdir import data_path
        save_json_atomic({"title": title, "uploader": (uploader or "").strip()},
                         data_path(output_dir, "video_meta.json",
                                   create_dir=True))
    except OSError as e:
        logger.warning(f"Không lưu được video_meta.json: {e}")


def normalize_url(url: str) -> str:
    """Rewrite non-canonical Douyin/TikTok URLs to a form yt-dlp can extract.

    Douyin's web app uses modal-style routes (e.g. /jingxuan?modal_id=<id>,
    /discover?modal_id=<id>) where the actual video id lives in the query
    string. yt-dlp's douyin extractor expects /video/<id>, so we rewrite.
    """
    if not url:
        return url
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "douyin.com" in host:
        qs = parse_qs(parsed.query)
        modal_id = qs.get("modal_id", [None])[0]
        if modal_id and modal_id.isdigit():
            return f"https://www.douyin.com/video/{modal_id}"

    return url


import shutil


def _get_optimized_opts(
    output_dir: str,
    outtmpl: str | None = None,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> dict:
    """Cấu hình yt-dlp tối ưu tốc độ tải (đa luồng, chia chunk, DASH stream, aria2c)."""
    template = outtmpl or os.path.join(output_dir, "%(id)s.%(ext)s")
    opts: dict = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
        "outtmpl": template,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        # Tăng tốc độ tải: tải 16 phân mảnh đồng thời + chunk 10MB vượt giới hạn bóp băng thông
        "concurrent_fragment_downloads": 16,
        "http_chunk_size": 10485760,
        "buffersize": 1048576,
        # Header chuẩn tránh bị CDN Bilibili bóp băng thông hoặc chặn
        "http_headers": {
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
        "extractor_args": {
            "bilibili": {
                "playback": "dash",
            }
        },
    }

    # Tự động dùng aria2c nếu có sẵn trên máy để tải tối đa băng thông
    aria2 = shutil.which("aria2c")
    if aria2:
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = {
            "aria2c": [
                "-s", "16",
                "-x", "16",
                "-k", "1M",
                "--file-allocation=none",
                "--max-connection-per-server=16",
                "--header=Referer: https://www.bilibili.com/",
                "--header=User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "--check-certificate=false",
                "--min-split-size=1M",
            ]
        }

    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookies_file:
        opts["cookiefile"] = cookies_file

    return opts


def download_video(url: str, output_dir: str) -> str:
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    # Douyin's yt-dlp extractor is broken upstream (requires `a_bogus`
    # signature). Route Douyin URLs (including v.douyin.com short links)
    # through the Playwright-based fallback.
    from autodub.media.douyin import is_douyin_url, download_douyin
    if is_douyin_url(url):
        logger.info(f"Routing to Playwright Douyin extractor: {url}")
        info = download_douyin(url, output_dir)
        _save_meta(output_dir, info.get("title", ""), info.get("uploader", ""))
        return info["filepath"]

    canonical = normalize_url(url)
    if canonical != url:
        logger.info(f"Normalized URL: {url} -> {canonical}")

    ydl_opts = _get_optimized_opts(output_dir, outtmpl=os.path.join(output_dir, "%(id)s.%(ext)s"))

    logger.info(f"Downloading video from: {canonical}")

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical, download=True)
    except Exception as e:
        if "external_downloader" in ydl_opts:
            logger.warning(f"aria2c tải gặp sự cố ({e}) — Tự động chuyển sang bộ tải native đa luồng...")
            fallback_opts = dict(ydl_opts)
            fallback_opts.pop("external_downloader", None)
            fallback_opts.pop("external_downloader_args", None)
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(canonical, download=True)
        else:
            raise

    video_id = info.get("id", "video")
    ext = info.get("ext", "mp4")
    filepath = (_ydl_reported_path(info)
                or os.path.join(output_dir, f"{video_id}.{ext}"))

    if not os.path.exists(filepath):
        for f in sorted(os.listdir(output_dir)):
            if f.startswith(video_id) and not _is_partial_name(f):
                filepath = os.path.join(output_dir, f)
                break

    if not os.path.exists(filepath):
        raise RuntimeError(f"Download failed: file not found at {filepath}")

    _save_meta(output_dir, info.get("title", ""), info.get("uploader", ""))
    logger.info(f"Downloaded: {filepath}")
    return filepath


def build_ydl_opts(
    output_dir: str,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> dict:
    """yt-dlp options for the standalone `autodub download` command."""
    opts = _get_optimized_opts(
        output_dir,
        outtmpl=os.path.join(output_dir, "%(extractor_key)s_%(id)s.%(ext)s"),
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
    )
    opts["noprogress"] = False
    return opts


def _ydl_reported_path(info: dict) -> str | None:
    """The file path yt-dlp itself reports for the finished download."""
    try:
        path = (info.get("requested_downloads") or [{}])[0].get("filepath")
    except (AttributeError, IndexError, TypeError):
        return None
    return path if path and os.path.exists(path) else None


def _is_partial_name(name: str) -> bool:
    """True for yt-dlp intermediate files (.part, .ytdl, .f299.mp4...)."""
    lower = name.lower()
    if lower.endswith((".part", ".ytdl", ".temp")):
        return True
    # Pre-merge single streams look like <id>.f<format_id>.<ext>
    return bool(re.search(r"\.f\d+\.\w+$", lower))


def _resolve_filepath(info: dict, output_dir: str) -> str:
    """yt-dlp may rename during merge; locate the actual saved file."""
    # yt-dlp tells us the real path — trust it first (also covers ids with
    # characters that were sanitized out of the filename).
    reported = _ydl_reported_path(info)
    if reported:
        return reported

    extractor = info.get("extractor_key", info.get("extractor", "video"))
    video_id = info.get("id", "video")
    ext = info.get("ext", "mp4")

    expected = os.path.join(output_dir, f"{extractor}_{video_id}.{ext}")
    if os.path.exists(expected):
        return expected

    prefix = f"{extractor}_{video_id}"
    for f in sorted(os.listdir(output_dir)):
        # .part/.fNNN là file trung gian — trả về chúng là đưa file hỏng
        # vào pipeline.
        if f.startswith(prefix) and not _is_partial_name(f):
            return os.path.join(output_dir, f)

    raise RuntimeError(f"Downloaded but file not found (prefix={prefix})")


def download_one(
    url: str,
    output_dir: str,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> dict:
    """Download a single URL and return metadata + saved filepath.

    Douyin URLs (including short-link v.douyin.com/...) are routed to a
    Playwright-based extractor because yt-dlp's Douyin path is broken upstream.
    All other sites continue through yt-dlp.
    """
    from autodub.media.douyin import is_douyin_url, download_douyin
    if is_douyin_url(url):
        logger.info(f"Routing to Playwright Douyin extractor: {url}")
        return download_douyin(url, output_dir)

    canonical = normalize_url(url)
    if canonical != url:
        logger.info(f"Normalized: {url} -> {canonical}")

    ydl_opts = build_ydl_opts(output_dir, cookies_from_browser, cookies_file)

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical, download=True)
    except Exception as e:
        if "external_downloader" in ydl_opts:
            logger.warning(f"aria2c tải gặp sự cố ({e}) — Tự động chuyển sang bộ tải native đa luồng...")
            fallback_opts = dict(ydl_opts)
            fallback_opts.pop("external_downloader", None)
            fallback_opts.pop("external_downloader_args", None)
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(canonical, download=True)
        else:
            raise

    filepath = _resolve_filepath(info, output_dir)

    return {
        "input_url": url,
        "canonical_url": canonical,
        "platform": info.get("extractor_key", info.get("extractor", "")),
        "video_id": info.get("id", ""),
        "title": info.get("title", ""),
        "uploader": info.get("uploader", ""),
        "duration": info.get("duration", 0),
        "filepath": filepath,
    }
