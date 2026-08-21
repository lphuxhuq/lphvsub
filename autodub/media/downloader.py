"""Video download via yt-dlp, with Douyin routed through Playwright."""
import os
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
import yt_dlp

from autodub.utils import setup_logging, ensure_dir, save_json_atomic

logger = setup_logging("autodub.downloader")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
_BILIBILI_REFERER = "https://www.bilibili.com/"

_BILIBILI_TRACKING_PARAMS = {
    "spm_id_from", "vd_source", "share_source", "from_spmid",
    "share_medium", "share_plat", "share_session_id", "share_tag",
    "bbid", "ts", "buvid", "mid",
}


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


def _resolve_b23_shortlink(url: str) -> str:
    """Follow HTTP redirect for b23.tv shortlinks to get the target Bilibili URL."""
    try:
        resp = requests.head(
            url,
            headers={"User-Agent": _UA, "Referer": _BILIBILI_REFERER},
            allow_redirects=True,
            timeout=8.0,
        )
        if resp.url and "b23.tv" not in urlparse(resp.url).netloc.lower():
            return resp.url
    except Exception as e:
        logger.debug(f"Không giải mã được b23.tv redirect ({e})")
    return url


def normalize_url(url: str) -> str:
    """Clean and rewrite Douyin/Bilibili/TikTok URLs to a form yt-dlp can extract."""
    if not url:
        return ""
    from autodub.media.douyin import extract_clean_url
    url = extract_clean_url(str(url).strip())
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # 1. Bilibili shortlink (b23.tv)
    if host == "b23.tv" or host.endswith(".b23.tv"):
        url = _resolve_b23_shortlink(url)
        parsed = urlparse(url)
        host = parsed.netloc.lower()

    # 2. Bilibili cleaning: remove tracking query params, keep pagination (?p=...)
    if "bilibili.com" in host or "b23.tv" in host:
        qs = parse_qs(parsed.query)
        cleaned_qs = {k: v for k, v in qs.items() if k.lower() not in _BILIBILI_TRACKING_PARAMS}
        new_query = urlencode(cleaned_qs, doseq=True)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        parsed = urlparse(url)
        host = parsed.netloc.lower()

    # 3. Douyin modal route rewrite
    if "douyin.com" in host:
        qs = parse_qs(parsed.query)
        modal_id = qs.get("modal_id", [None])[0]
        if modal_id and modal_id.isdigit():
            return f"https://www.douyin.com/video/{modal_id}"

    return url


def _clean_broken_partials(directory: str) -> None:
    """Xóa CHỈ các file dở dang (.part, .aria2, .temp, .ytdl) để tránh HTTP 416.

    GIỮ LẠI các stream đã tải xong (.f*.mp4, .f*.m4a) vì yt-dlp sẽ tự
    nhận ra "already downloaded" và bỏ qua, chỉ tải lại stream bị hỏng.
    """
    if not os.path.isdir(directory):
        return
    for fname in os.listdir(directory):
        lower = fname.lower()
        if lower.endswith((".part", ".ytdl", ".temp")) or lower.endswith(".aria2"):
            try:
                os.remove(os.path.join(directory, fname))
                logger.info(f"Dọn tệp dở dang: {fname}")
            except OSError:
                pass


def _get_optimized_opts(
    output_dir: str,
    outtmpl: str | None = None,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
    fallback_level: int = 0,
) -> dict:
    """Cấu hình yt-dlp tối ưu tốc độ tải (native, không aria2c, không chunk).

    - Bilibili Akamai CDN bóp băng thông audio ~800KB/s và ngắt kết nối sau 85MB (~100s).
    - Ưu tiên audio <=100kbps (như 30232 84kbps / 30216 64kbps) để dung lượng <70MB,
      tải hoàn tất trong <80s trước khi signed token CDN hết hạn (chất lượng hoàn hảo cho ASR).
    - fallback_level >= 1 chuyển sang độ phân giải <=720p và stream phụ an toàn.
    - Dùng bộ tải native single-stream + outer retry lấy URL mới.
    - Bổ sung HTTP headers (User-Agent, Referer) chuẩn để CDN không bóp băng thông.
    """
    template = outtmpl or os.path.join(output_dir, "%(id)s.%(ext)s")

    if fallback_level == 0:
        fmt = (
            "bestvideo[height<=1080]+bestaudio[abr<=100]/"
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080]/best"
        )
    else:
        fmt = (
            "bestvideo[height<=720]+30232/"
            "bestvideo[height<=720]+30216/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        )

    opts: dict = {
        "format": fmt,
        "outtmpl": template,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 60,
        "http_headers": {
            "User-Agent": _UA,
            "Referer": _BILIBILI_REFERER,
        },
    }

    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookies_file:
        opts["cookiefile"] = cookies_file

    return opts


_MAX_OUTER_RETRIES = 3


def download_video(url: str, output_dir: str) -> str:
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    # Douyin's yt-dlp extractor is broken upstream (requires `a_bogus`
    # signature). Route Douyin URLs (including v.douyin.com short links)
    # through the Playwright-based fallback.
    from autodub.media.douyin import is_douyin_url, download_douyin, extract_clean_url
    clean_url = extract_clean_url(url)
    if is_douyin_url(clean_url):
        logger.info(f"Routing to Douyin extractor: {clean_url}")
        info = download_douyin(clean_url, output_dir)
        _save_meta(output_dir, info.get("title", ""), info.get("uploader", ""))
        return info["filepath"]

    canonical = normalize_url(clean_url)
    if canonical != url:
        logger.info(f"Normalized URL: {url} -> {canonical}")

    logger.info(f"Downloading video from: {canonical}")

    # Dọn dẹp tệp dở dang (.part) từ phiên trước TRƯỚC KHI bắt đầu lần 1
    # để tránh bị HTTP 416 khi resume token đã hết hạn.
    _clean_broken_partials(output_dir)

    # Outer retry: mỗi lần gọi extract_info() lấy URL CDN MỚI với deadline mới.
    # Giữ lại stream đã tải xong (.f*.mp4) — yt-dlp tự skip "already downloaded".
    info = None
    last_error = None
    for attempt in range(1, _MAX_OUTER_RETRIES + 1):
        try:
            if attempt > 1:
                _clean_broken_partials(output_dir)
                logger.info(f"Lần thử {attempt}/{_MAX_OUTER_RETRIES}: "
                            f"Lấy link tải mới từ server...")
            ydl_opts = _get_optimized_opts(
                output_dir,
                outtmpl=os.path.join(output_dir, "%(id)s.%(ext)s"),
                fallback_level=attempt - 1,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical, download=True)
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Lần thử {attempt}/{_MAX_OUTER_RETRIES} thất bại: {e}")

    if last_error is not None:
        raise RuntimeError(
            f"Tải video thất bại sau {_MAX_OUTER_RETRIES} lần thử: {last_error}"
        ) from last_error

    if info and "entries" in info and info["entries"]:
        entries = [e for e in info["entries"] if e]
        if entries:
            info = entries[0]

    video_id = info.get("id", "video") if info else "video"
    ext = info.get("ext", "mp4") if info else "mp4"
    filepath = (_ydl_reported_path(info)
                or os.path.join(output_dir, f"{video_id}.{ext}"))

    if not os.path.exists(filepath):
        base_id = video_id.split("_p")[0] if "_p" in video_id else video_id
        for f in sorted(os.listdir(output_dir)):
            if (f.startswith(video_id) or f.startswith(base_id)) and not _is_partial_name(f):
                filepath = os.path.join(output_dir, f)
                break

    if not os.path.exists(filepath):
        raise RuntimeError(f"Download failed: file not found at {filepath}")

    if info:
        _save_meta(output_dir, info.get("title", ""), info.get("uploader", ""))
    logger.info(f"Downloaded: {filepath}")
    return filepath


def build_ydl_opts(
    output_dir: str,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
    fallback_level: int = 0,
) -> dict:
    """yt-dlp options for the standalone `autodub download` command."""
    opts = _get_optimized_opts(
        output_dir,
        outtmpl=os.path.join(output_dir, "%(extractor_key)s_%(id)s.%(ext)s"),
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        fallback_level=fallback_level,
    )
    opts["noprogress"] = False
    return opts


def _ydl_reported_path(info: dict) -> str | None:
    """The file path yt-dlp itself reports for the finished download."""
    if not info or not isinstance(info, dict):
        return None
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
    return bool(re.search(r"\.f\w+\.\w+$", lower))


def _resolve_filepath(info: dict, output_dir: str) -> str:
    """yt-dlp may rename during merge; locate the actual saved file."""
    if not info:
        raise RuntimeError("No download info returned by yt-dlp")

    reported = _ydl_reported_path(info)
    if reported:
        return reported

    if "entries" in info and info["entries"]:
        entries = [e for e in info["entries"] if e]
        if entries:
            info = entries[0]
            reported = _ydl_reported_path(info)
            if reported:
                return reported

    extractor = info.get("extractor_key", info.get("extractor", "video"))
    video_id = info.get("id", "video")
    ext = info.get("ext", "mp4")

    expected = os.path.join(output_dir, f"{extractor}_{video_id}.{ext}")
    if os.path.exists(expected):
        return expected

    prefix = f"{extractor}_{video_id}".lower()
    base_id = video_id.split("_p")[0].lower() if "_p" in video_id else ""
    for f in sorted(os.listdir(output_dir)):
        f_lower = f.lower()
        if not _is_partial_name(f):
            if f_lower.startswith(prefix) or (base_id and f_lower.startswith(f"{extractor.lower()}_{base_id}")):
                return os.path.join(output_dir, f)

    for f in sorted(os.listdir(output_dir)):
        f_lower = f.lower()
        if not _is_partial_name(f):
            if f_lower.startswith(video_id.lower()) or (base_id and f_lower.startswith(base_id)):
                return os.path.join(output_dir, f)

    raise RuntimeError(f"Downloaded but file not found (prefix={extractor}_{video_id})")


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
    from autodub.media.douyin import is_douyin_url, download_douyin, extract_clean_url
    clean_url = extract_clean_url(url)
    if is_douyin_url(clean_url):
        logger.info(f"Routing to Douyin extractor: {clean_url}")
        return download_douyin(clean_url, output_dir)

    canonical = normalize_url(clean_url)
    if canonical != url:
        logger.info(f"Normalized: {url} -> {canonical}")

    _clean_broken_partials(output_dir)

    info = None
    last_error = None
    for attempt in range(1, _MAX_OUTER_RETRIES + 1):
        try:
            if attempt > 1:
                _clean_broken_partials(output_dir)
                logger.info(f"Lần thử {attempt}/{_MAX_OUTER_RETRIES}: "
                            f"Lấy link tải mới từ server...")
            ydl_opts = build_ydl_opts(
                output_dir,
                cookies_from_browser=cookies_from_browser,
                cookies_file=cookies_file,
                fallback_level=attempt - 1,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical, download=True)
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Lần thử {attempt}/{_MAX_OUTER_RETRIES} thất bại: {e}")

    if last_error is not None:
        raise RuntimeError(
            f"Tải video thất bại sau {_MAX_OUTER_RETRIES} lần thử: {last_error}"
        ) from last_error

    filepath = _resolve_filepath(info, output_dir)
    target_info = info
    if target_info and "entries" in target_info and target_info["entries"]:
        entries = [e for e in target_info["entries"] if e]
        if entries:
            target_info = entries[0]

    return {
        "input_url": url,
        "canonical_url": canonical,
        "platform": target_info.get("extractor_key", target_info.get("extractor", "")),
        "video_id": target_info.get("id", ""),
        "title": target_info.get("title", ""),
        "uploader": target_info.get("uploader", ""),
        "duration": target_info.get("duration", 0),
        "filepath": filepath,
    }
