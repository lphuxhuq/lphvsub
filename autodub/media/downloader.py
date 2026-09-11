"""Video download via yt-dlp, with Douyin routed through Playwright."""

import os
import re
import shutil
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
import yt_dlp

from autodub.utils import ensure_dir, save_json_atomic, setup_logging

logger = setup_logging("autodub.downloader")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
_BILIBILI_REFERER = "https://www.bilibili.com/"

_BILIBILI_TRACKING_PARAMS = {
    "spm_id_from",
    "vd_source",
    "share_source",
    "from_spmid",
    "share_medium",
    "share_plat",
    "share_session_id",
    "share_tag",
    "bbid",
    "ts",
    "buvid",
    "mid",
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

        save_json_atomic(
            {"title": title, "uploader": (uploader or "").strip()},
            data_path(output_dir, "video_meta.json", create_dir=True),
        )
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
        url = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )
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
    """Xóa CHỈ các file dở dang không thể khôi phục (.aria2, .temp) hoặc .part quá cũ.

    GIỮ LẠI các file có .progress.json để cơ chế Smart Resume có thể tiếp tục tải.
    """
    if not os.path.isdir(directory):
        return
    now = time.time()
    for fname in os.listdir(directory):
        lower = fname.lower()
        full_path = os.path.join(directory, fname)
        # Never delete active progress metadata
        if lower.endswith(".progress.json"):
            continue
        if lower.endswith(".part"):
            meta_path = os.path.join(directory, f"{fname.replace('.part', '')}.progress.json")
            # If progress meta exists and was touched in the last 24 hours, preserve it!
            if os.path.exists(meta_path):
                try:
                    if (now - os.path.getmtime(meta_path)) < 86400:
                        continue
                except OSError:
                    logger.debug("Bỏ qua lỗi OSError trong downloader.py", exc_info=True)
        if lower.endswith((".temp", ".ytdl")) or lower.endswith(".aria2"):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.debug(f"Không xóa được file tạm {fname}: {e}")


def _make_ydl_progress_hook(progress_cb):
    def _ydl_hook(d):
        if not progress_cb or not isinstance(d, dict):
            return
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0.0
            speed_mb = speed / (1024 * 1024) if speed else 0.0
            pct = (downloaded / total) if total > 0 else 0.0
            down_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024) if total > 0 else 0.0
            if total > 0:
                msg = f"Đang tải: {down_mb:.1f}MB / {tot_mb:.1f}MB ({int(pct * 100)}%) - {speed_mb:.1f} MB/s"
            else:
                msg = f"Đang tải: {down_mb:.1f}MB - {speed_mb:.1f} MB/s"
            progress_cb(min(0.95, max(0.0, pct)), msg)
        elif status == "finished":
            progress_cb(0.96, "Đang xử lý tệp video...")

    return _ydl_hook


def _get_optimized_opts(
    output_dir: str,
    outtmpl: str | None = None,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
    fallback_level: int = 0,
    progress_cb: Any = None,
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
        # Ưu tiên codec nén tốt trước (HEVC/AV1 nhỏ hơn AVC ~30-50% ở cùng
        # 1080p): ít byte hơn không chỉ nhanh hơn mà còn tải xong TRƯỚC ngưỡng
        # CDN ngắt kết nối (~85MB/~100s) → giảm cả lỗi retry. ``vcodec^=hev``
        # khớp cả "hev1" lẫn "hevc1" (bilibili ghi "hev1.1.6...").
        fmt = (
            "bestvideo[height<=1080][vcodec^=hev]+bestaudio[abr<=100]/"
            "bestvideo[height<=1080][vcodec^=av01]+bestaudio[abr<=100]/"
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
        # Chỉ tác dụng với format phân mảnh (HLS...) — tải song song các mảnh;
        # vô hại với bilibili DASH (file đơn). Giữ single-stream mỗi file.
        "concurrent_fragment_downloads": 4,
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
    if progress_cb:
        opts["progress_hooks"] = [_make_ydl_progress_hook(progress_cb)]

    return opts


def update_ytdlp() -> bool:
    """Tự động cập nhật yt-dlp lên phiên bản mới nhất qua pip."""
    import subprocess
    import sys

    logger.info("Đang kiểm tra và nâng cấp yt-dlp lên phiên bản mới nhất...")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=flags,
        )
        if res.returncode == 0:
            logger.info("Đã cập nhật yt-dlp thành công.")
            return True
        logger.warning(f"Cập nhật yt-dlp không thành công: {res.stderr[:200]}")
    except Exception as e:
        logger.warning(f"Lỗi khi cập nhật yt-dlp: {e}")
    return False


_MAX_OUTER_RETRIES = 3


def download_video(url: str, output_dir: str, progress_cb: Any = None) -> str:
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    def _engine_cb(status_dict):
        if not progress_cb or not isinstance(status_dict, dict):
            return
        pct = status_dict.get("progress")
        if pct is None and "percent" in status_dict:
            pct = status_dict["percent"] / 100.0
        pct = pct or 0.0
        msg = status_dict.get("message")
        if not msg:
            mb_d = status_dict.get("bytes_downloaded", 0) / (1024 * 1024)
            mb_t = status_dict.get("total_bytes", 0) / (1024 * 1024)
            speed = status_dict.get("speed_mb", 0.0)
            if mb_t > 0:
                msg = (
                    f"Đang tải: {mb_d:.1f}MB / {mb_t:.1f}MB ({int(pct * 100)}%) - {speed:.1f} MB/s"
                )
            else:
                msg = f"Đang tải: {mb_d:.1f}MB - {speed:.1f} MB/s"
        progress_cb(min(1.0, max(0.0, pct)), msg)

    # 1. Try Turbo + Reliable Smart Download Engine first
    try:
        from autodub.media.download.contract import DownloadRequest
        from autodub.media.download.decision_engine import get_decision_engine

        engine = get_decision_engine()
        req = DownloadRequest(
            url=url,
            output_dir=output_dir,
            progress_callback=_engine_cb if progress_cb else None,
        )
        res = engine.execute(req)
        if res.success and res.path and os.path.exists(res.path):
            _save_meta(output_dir, res.media_id, "")
            logger.info(f"Smart Download Engine succeeded: {res.path} ({res.backend})")
            if progress_cb:
                progress_cb(1.0, "Tải video hoàn tất!")
            return res.path
        logger.info(
            f"Smart Download Engine returned unsuccessful ({res.error_message}), trying fallback..."
        )
    except Exception as e:
        logger.warning(
            f"Smart Download Engine encountered error ({e}), falling back to standard path..."
        )

    # Douyin's yt-dlp extractor is broken upstream (requires `a_bogus`
    # signature). Route Douyin URLs (including v.douyin.com short links)
    # through the Playwright-based fallback.
    from autodub.media.douyin import download_douyin, extract_clean_url, is_douyin_url

    clean_url = extract_clean_url(url)
    if is_douyin_url(clean_url):
        logger.info(f"Routing to Douyin extractor: {clean_url}")
        info = download_douyin(clean_url, output_dir, progress_cb=progress_cb)
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
                logger.info(
                    f"Lần thử {attempt}/{_MAX_OUTER_RETRIES}: Lấy link tải mới từ server..."
                )
            ydl_opts = _get_optimized_opts(
                output_dir,
                outtmpl=os.path.join(output_dir, "%(id)s.%(ext)s"),
                fallback_level=attempt - 1,
                progress_cb=progress_cb,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical, download=True)
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Lần thử {attempt}/{_MAX_OUTER_RETRIES} thất bại: {e}")
            if attempt == _MAX_OUTER_RETRIES - 1:
                # Thử tự cập nhật yt-dlp trước lượt thử cuối cùng nếu lỗi do extractor cũ
                update_ytdlp()

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
    filepath = _ydl_reported_path(info) or os.path.join(output_dir, f"{video_id}.{ext}")

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
    progress_cb: Any = None,
) -> dict:
    """yt-dlp options for the standalone `autodub download` command."""
    opts = _get_optimized_opts(
        output_dir,
        outtmpl=os.path.join(output_dir, "%(extractor_key)s_%(id)s.%(ext)s"),
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        fallback_level=fallback_level,
        progress_cb=progress_cb,
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

    if info.get("entries"):
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
            if f_lower.startswith(prefix) or (
                base_id and f_lower.startswith(f"{extractor.lower()}_{base_id}")
            ):
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
    progress_cb: Any = None,
) -> dict:
    """Download a single URL and return metadata + saved filepath.

    Routes through Turbo + Reliable Smart Download Engine first,
    with automatic fallback to legacy extractors.
    """
    ensure_dir(output_dir)

    def _engine_cb(status_dict):
        if not progress_cb or not isinstance(status_dict, dict):
            return
        pct = status_dict.get("progress")
        if pct is None and "percent" in status_dict:
            pct = status_dict["percent"] / 100.0
        pct = pct or 0.0
        msg = status_dict.get("message")
        if not msg:
            mb_d = status_dict.get("bytes_downloaded", 0) / (1024 * 1024)
            mb_t = status_dict.get("total_bytes", 0) / (1024 * 1024)
            speed = status_dict.get("speed_mb", 0.0)
            if mb_t > 0:
                msg = (
                    f"Đang tải: {mb_d:.1f}MB / {mb_t:.1f}MB ({int(pct * 100)}%) - {speed:.1f} MB/s"
                )
            else:
                msg = f"Đang tải: {mb_d:.1f}MB - {speed:.1f} MB/s"
        progress_cb(min(1.0, max(0.0, pct)), msg)

    # 1. Try Turbo + Reliable Smart Download Engine first
    try:
        from autodub.media.download.contract import DownloadRequest
        from autodub.media.download.decision_engine import get_decision_engine

        engine = get_decision_engine()
        req = DownloadRequest(
            url=url,
            output_dir=output_dir,
            cookie_file=cookies_file,
            progress_callback=_engine_cb if progress_cb else None,
        )
        res = engine.execute(req)
        if res.success and res.path and os.path.exists(res.path):
            _save_meta(output_dir, res.media_id, "")
            logger.info(f"Smart Download Engine download_one succeeded: {res.path} ({res.backend})")
            if progress_cb:
                progress_cb(1.0, "Tải video hoàn tất!")
            return {
                "input_url": url,
                "canonical_url": url,
                "platform": res.platform or "video",
                "video_id": res.media_id,
                "title": res.media_id,
                "uploader": "",
                "duration": res.duration,
                "filepath": res.path,
            }
        logger.info(
            f"Smart Download Engine download_one returned unsuccessful ({res.error_message}), falling back..."
        )
    except Exception as e:
        logger.warning(f"Smart Download Engine download_one error ({e}), falling back...")

    from autodub.media.douyin import download_douyin, extract_clean_url, is_douyin_url

    clean_url = extract_clean_url(url)
    if is_douyin_url(clean_url):
        logger.info(f"Routing to Douyin extractor: {clean_url}")
        return download_douyin(clean_url, output_dir, progress_cb=progress_cb)

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
                logger.info(
                    f"Lần thử {attempt}/{_MAX_OUTER_RETRIES}: Lấy link tải mới từ server..."
                )
            ydl_opts = build_ydl_opts(
                output_dir,
                cookies_from_browser=cookies_from_browser,
                cookies_file=cookies_file,
                fallback_level=attempt - 1,
                progress_cb=progress_cb,
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


def download_one_isolated(
    url: str,
    output_dir: str,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
    progress_cb: Any = None,
) -> dict:
    """``download_one`` vào thư mục riêng rồi gỡ file về ``output_dir``.

    An toàn khi NHIỀU URL tải song song vào cùng ``output_dir``:
    ``_clean_broken_partials`` xóa mọi ``.part`` trong thư mục nó thấy nên
    hai lượt tải chung thư mục sẽ giết file đang dở của nhau — mỗi lượt tải
    trong ``.dl_tmp`` riêng, xong mới move kết quả ra ngoài.

    Trade-off đã biết: đường này bỏ qua cơ chế "already downloaded" của
    yt-dlp giữa các lần chạy (file hoàn tất vẫn nằm ở ``output_dir`` như
    thường). Trùng tên file (tải lại cùng video trong một lượt) → thêm hậu
    tố thời gian thay vì ghi đè.
    """
    ensure_dir(output_dir)
    tmp_dir = os.path.join(output_dir, ".dl_tmp")
    ensure_dir(tmp_dir)
    kwargs = {}
    if progress_cb is not None:
        kwargs["progress_cb"] = progress_cb
    entry = download_one(
        url, tmp_dir, cookies_from_browser=cookies_from_browser, cookies_file=cookies_file, **kwargs
    )
    try:
        src = entry["filepath"]
        dst = os.path.join(output_dir, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst):
            if os.path.exists(dst):
                base, ext = os.path.splitext(os.path.basename(src))
                dst = os.path.join(output_dir, f"{base}_{int(time.time())}{ext}")
            shutil.move(src, dst)
            entry["filepath"] = dst
        # video_meta.json (title/uploader) theo video về chỗ cũ của nó.
        meta_src = os.path.join(tmp_dir, "data", "video_meta.json")
        if os.path.isfile(meta_src):
            from autodub.workdir import data_path

            meta_dst = data_path(output_dir, "video_meta.json", create_dir=True)
            try:
                if os.path.exists(meta_dst):
                    os.remove(meta_dst)
                shutil.move(meta_src, meta_dst)
            except OSError as e:
                logger.warning(f"Không chuyển được video_meta.json: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return entry
