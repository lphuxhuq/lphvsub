"""Bilibili Turbo + Reliable Download Engine supporting DASH chunked streams, CDN racing and resume."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from autodub.media.download.cdn_racer import CdnRacingEngine
from autodub.media.download.concurrency import AdaptiveConcurrencyController
from autodub.media.download.contract import (
    BandwidthMode,
    DownloadRequest,
    DownloadResult,
    ErrorType,
    Platform,
)
from autodub.media.download.partial_manager import PartialDownloadManager
from autodub.media.download.performance_store import PerformanceStore
from autodub.media.download.retry import ErrorClassifier, SmartRetryPolicy
from autodub.media.download.session_manager import CookieSessionManager
from autodub.media.download.validator import MediaValidator

logger = logging.getLogger(__name__)

_BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


class BilibiliDownloader:
    """High-performance Bilibili download engine with DASH concurrent streaming and CDN racing."""

    def __init__(
        self,
        session_manager: Optional[CookieSessionManager] = None,
        partial_manager: Optional[PartialDownloadManager] = None,
        cdn_racer: Optional[CdnRacingEngine] = None,
        validator: Optional[MediaValidator] = None,
        perf_store: Optional[PerformanceStore] = None,
    ):
        self.session_mgr = session_manager or CookieSessionManager()
        self.partial_mgr = partial_manager or PartialDownloadManager()
        self.cdn_racer = cdn_racer or CdnRacingEngine()
        self.validator = validator or MediaValidator()
        self.perf_store = perf_store or PerformanceStore()
        self.retry_policy = SmartRetryPolicy(max_retries=3)

    @staticmethod
    def extract_bvid(url: str) -> Optional[str]:
        m = re.search(r"(BV[a-zA-Z0-9]{10})", url, re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def extract_page_index(url: str) -> int:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            return max(1, int(qs.get("p", ["1"])[0]))
        except Exception:
            return 1

    def fetch_video_view(self, bvid: str, session: requests.Session) -> Dict[str, Any]:
        """Fetches video metadata, title and cid list from Bilibili API."""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        resp = session.get(api_url, headers=_BILI_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API error: {data.get('message', 'unknown code')} (code: {data.get('code')})")
        return data.get("data", {})

    def fetch_playurl(self, bvid: str, cid: int, session: requests.Session) -> Dict[str, Any]:
        """Fetches DASH and progressive stream URLs."""
        api_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnval=4048&fourk=1"
        resp = session.get(api_url, headers=_BILI_HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili playurl API error: {data.get('message')} (code: {data.get('code')})")
        return data.get("data", {})

    def mux_dash(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        """Muxes separate video and audio m4s/mp4 streams using FFmpeg copy."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg muxing failed: {res.stderr[:300]}")
        return output_path

    def _download_via_ytdlp_fallback(
        self,
        request: DownloadRequest,
        target_path: Path,
    ) -> DownloadResult:
        """Fallback to yt-dlp wrapper if Bilibili direct web APIs require complex WBI signing."""
        import yt_dlp

        start_time = time.time()
        logger.info(f"Bilibili: using yt-dlp fallback for {request.url}")

        ydl_opts: Dict[str, Any] = {
            "outtmpl": str(target_path.parent / f"{target_path.stem}.%(ext)s"),
            "format": "bestvideo+bestaudio/best" if not request.audio_only else "bestaudio/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "retries": request.max_retries,
        }
        if request.cookie_file and Path(request.cookie_file).is_file():
            ydl_opts["cookiefile"] = str(request.cookie_file)

        def _ytdlp_hook(d):
            if not request.progress_callback:
                return
            if d.get("status") == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = (d.get("speed") or 0) / (1024 * 1024)
                if total > 0:
                    pct = min(0.95, downloaded / total)
                    mb_d = downloaded / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    msg = f"Đang tải Bilibili: {mb_d:.1f}MB / {mb_t:.1f}MB ({int(pct*100)}%) - {speed:.1f} MB/s"
                else:
                    pct = 0.5
                    mb_d = downloaded / (1024 * 1024)
                    msg = f"Đang tải Bilibili: {mb_d:.1f}MB - {speed:.1f} MB/s"
                request.progress_callback({"progress": pct, "percent": pct * 100.0, "message": msg, "status": "downloading"})
            elif d.get("status") == "finished":
                request.progress_callback({"progress": 0.98, "percent": 98.0, "message": "Đang xử lý video Bilibili...", "status": "processing"})

        ydl_opts["progress_hooks"] = [_ytdlp_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(request.url, download=True)
            candidates = list(target_path.parent.glob(f"{target_path.stem}.*"))
            final_file = target_path if target_path.exists() else (candidates[0] if candidates else target_path)

        val = self.validator.validate(final_file, require_video=not request.audio_only, require_audio=True)
        elapsed = time.time() - start_time
        avg_speed = val.file_size / elapsed if elapsed > 0 else 0.0

        return DownloadResult(
            success=val.valid,
            path=str(final_file) if val.valid else None,
            platform=Platform.BILIBILI.value,
            media_id=self.extract_bvid(request.url) or "",
            duration=val.duration,
            width=val.width,
            height=val.height,
            fps=val.fps,
            video_codec=val.video_codec,
            audio_codec=val.audio_codec,
            file_size=val.file_size,
            elapsed_seconds=elapsed,
            average_speed=avg_speed,
            backend="ytdlp_fallback",
            validation_passed=val.valid,
            error_message=val.error_message if not val.valid else None,
        )

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Executes the full Bilibili download lifecycle with DASH, CDN racing, and validation."""
        start_time = time.time()
        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        bvid = self.extract_bvid(request.url)
        if not bvid:
            return self._download_via_ytdlp_fallback(request, out_dir / (request.custom_filename or "bilibili_out.mp4"))

        target_name = request.custom_filename or f"bilibili_{bvid}.mp4"
        target_path = out_dir / target_name

        session = self.session_mgr.create_session(Platform.BILIBILI, cookie_file=request.cookie_file)
        retries_count = 0
        cdn_used = "default"

        try:
            view_data = self.fetch_video_view(bvid, session)
            pages = view_data.get("pages", [])
            page_idx = self.extract_page_index(request.url) - 1
            if 0 <= page_idx < len(pages):
                cid = pages[page_idx]["cid"]
            elif pages:
                cid = pages[0]["cid"]
            else:
                cid = view_data.get("cid", 0)

            play_data = self.fetch_playurl(bvid, cid, session)

            dash_data = play_data.get("dash")
            if dash_data and "video" in dash_data and "audio" in dash_data:
                backend_used = "dash"
                v_streams = dash_data["video"]
                a_streams = dash_data["audio"]

                best_video = max(v_streams, key=lambda s: s.get("bandwidth", 0))
                best_audio = max(a_streams, key=lambda s: s.get("bandwidth", 0))

                v_candidates = [best_video.get("baseUrl") or best_video.get("base_url")] + (best_video.get("backupUrl") or best_video.get("backup_url") or [])
                v_candidates = [c for c in v_candidates if c]

                a_candidates = [best_audio.get("baseUrl") or best_audio.get("base_url")] + (best_audio.get("backupUrl") or best_audio.get("backup_url") or [])
                a_candidates = [c for c in a_candidates if c]

                v_ranked = self.cdn_racer.race_candidates(v_candidates, session, headers=_BILI_HEADERS)
                chosen_v_url = v_ranked[0].url if v_ranked else v_candidates[0]
                cdn_used = self.cdn_racer.extract_host(chosen_v_url)

                a_ranked = self.cdn_racer.race_candidates(a_candidates, session, headers=_BILI_HEADERS)
                chosen_a_url = a_ranked[0].url if a_ranked else a_candidates[0]

                v_tmp = out_dir / f"temp_{bvid}_v.m4s"
                a_tmp = out_dir / f"temp_{bvid}_a.m4s"

                def _v_cb(d: dict):
                    if request.progress_callback and isinstance(d, dict):
                        pct = (d.get("percent", 0.0) / 100.0) * 0.85
                        mb_d = d.get("bytes_downloaded", 0) / (1024 * 1024)
                        mb_t = d.get("total_bytes", 0) / (1024 * 1024)
                        speed = d.get("speed_mb", 0.0)
                        msg = f"Đang tải video Bilibili: {mb_d:.1f}MB / {mb_t:.1f}MB ({int(pct*100)}%) - {speed:.1f} MB/s" if mb_t > 0 else f"Đang tải video Bilibili: {mb_d:.1f}MB - {speed:.1f} MB/s"
                        request.progress_callback({
                            **d,
                            "progress": pct,
                            "percent": pct * 100.0,
                            "message": msg,
                        })

                def _a_cb(d: dict):
                    if request.progress_callback and isinstance(d, dict):
                        pct = 0.85 + (d.get("percent", 0.0) / 100.0) * 0.10
                        mb_d = d.get("bytes_downloaded", 0) / (1024 * 1024)
                        mb_t = d.get("total_bytes", 0) / (1024 * 1024)
                        speed = d.get("speed_mb", 0.0)
                        msg = f"Đang tải âm thanh Bilibili: {mb_d:.1f}MB / {mb_t:.1f}MB - {speed:.1f} MB/s" if mb_t > 0 else "Đang tải âm thanh Bilibili..."
                        request.progress_callback({
                            **d,
                            "progress": pct,
                            "percent": pct * 100.0,
                            "message": msg,
                        })

                v_start = time.perf_counter()
                self.partial_mgr.download_progressive_stream(
                    url=chosen_v_url,
                    target_path=v_tmp,
                    session=session,
                    headers=_BILI_HEADERS,
                    progress_callback=_v_cb if request.progress_callback else None,
                    is_cancelled=request.is_cancelled,
                )
                v_elapsed = max(0.01, time.perf_counter() - v_start)
                self.perf_store.record_metric("bilibili", cdn_used, v_tmp.stat().st_size, v_elapsed, success=True)

                self.partial_mgr.download_progressive_stream(
                    url=chosen_a_url,
                    target_path=a_tmp,
                    session=session,
                    headers=_BILI_HEADERS,
                    progress_callback=_a_cb if request.progress_callback else None,
                    is_cancelled=request.is_cancelled,
                )

                if request.progress_callback:
                    request.progress_callback({"progress": 0.96, "percent": 96.0, "message": "Đang ghép tệp âm thanh và hình ảnh Bilibili..."})

                self.mux_dash(v_tmp, a_tmp, target_path)

                if request.progress_callback:
                    request.progress_callback({"progress": 1.0, "percent": 100.0, "message": "Tải video Bilibili hoàn tất!"})

                v_tmp.unlink(missing_ok=True)
                a_tmp.unlink(missing_ok=True)

            elif "durl" in play_data:
                backend_used = "progressive_http"
                durl_items = play_data["durl"]
                item = durl_items[0]
                candidates = [item.get("url")] + (item.get("backup_url") or [])
                candidates = [c for c in candidates if c]

                ranked = self.cdn_racer.race_candidates(candidates, session, headers=_BILI_HEADERS)
                chosen_url = ranked[0].url if ranked else candidates[0]
                cdn_used = self.cdn_racer.extract_host(chosen_url)

                t_start = time.perf_counter()
                self.partial_mgr.download_progressive_stream(
                    url=chosen_url,
                    target_path=target_path,
                    session=session,
                    headers=_BILI_HEADERS,
                    progress_callback=request.progress_callback,
                    is_cancelled=request.is_cancelled,
                )
                t_elapsed = max(0.01, time.perf_counter() - t_start)
                self.perf_store.record_metric("bilibili", cdn_used, target_path.stat().st_size, t_elapsed, success=True)

            else:
                raise RuntimeError("No suitable DASH or progressive streams returned by Bilibili API")

            val = self.validator.validate(target_path, require_video=True, require_audio=not request.audio_only)
            elapsed = time.time() - start_time
            avg_speed = val.file_size / elapsed if elapsed > 0 else 0.0

            return DownloadResult(
                success=val.valid,
                path=str(target_path) if val.valid else None,
                platform=Platform.BILIBILI.value,
                media_id=bvid,
                duration=val.duration,
                width=val.width,
                height=val.height,
                fps=val.fps,
                video_codec=val.video_codec,
                audio_codec=val.audio_codec,
                file_size=val.file_size,
                elapsed_seconds=elapsed,
                average_speed=avg_speed,
                retries=retries_count,
                backend=backend_used,
                cdn=cdn_used,
                validation_passed=val.valid,
                error_message=val.error_message if not val.valid else None,
            )

        except Exception as exc:
            logger.warning(f"Bilibili native download failed ({exc}), falling back to yt-dlp")
            try:
                return self._download_via_ytdlp_fallback(request, target_path)
            except Exception as ex2:
                elapsed = time.time() - start_time
                err_type = ErrorClassifier.classify(ex2)
                return DownloadResult(
                    success=False,
                    platform=Platform.BILIBILI.value,
                    media_id=bvid,
                    elapsed_seconds=elapsed,
                    backend="fallback_failed",
                    validation_passed=False,
                    error_message=str(ex2),
                    error_type=err_type,
                )
