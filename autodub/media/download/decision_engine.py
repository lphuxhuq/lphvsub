"""Download Decision Engine: central orchestrator for preflight, routing, caching and validation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from autodub.media.download.bilibili_engine import BilibiliDownloader
from autodub.media.download.cache import DownloadCache
from autodub.media.download.contract import (
    DownloadRequest,
    DownloadResult,
    ErrorType,
    Platform,
)
from autodub.media.download.douyin_engine import DouyinDownloader
from autodub.media.download.performance_store import PerformanceStore
from autodub.media.download.preflight import PlatformDetector, PreflightAnalyzer
from autodub.media.download.validator import MediaValidator

logger = logging.getLogger(__name__)


class DownloadDecisionEngine:
    """Intelligently routes download requests to specialized engines with caching and validation."""

    def __init__(
        self,
        preflight: PreflightAnalyzer | None = None,
        cache: DownloadCache | None = None,
        bilibili_engine: BilibiliDownloader | None = None,
        douyin_engine: DouyinDownloader | None = None,
        validator: MediaValidator | None = None,
        perf_store: PerformanceStore | None = None,
    ):
        self.validator = validator or MediaValidator()
        self.preflight = preflight or PreflightAnalyzer()
        self.cache = cache or DownloadCache(validator=self.validator)
        self.bilibili = bilibili_engine or BilibiliDownloader(validator=self.validator)
        self.douyin = douyin_engine or DouyinDownloader(validator=self.validator)
        self.perf_store = perf_store or PerformanceStore()

    def _download_generic_ytdlp(
        self, request: DownloadRequest, target_path: Path
    ) -> DownloadResult:
        """Generic fallback download using yt-dlp wrapper."""
        import yt_dlp

        start_time = time.time()
        logger.info(f"Generic download via yt-dlp: {request.url}")

        ydl_opts: dict[str, Any] = {
            "outtmpl": str(target_path.parent / f"{target_path.stem}.%(ext)s"),
            "format": "bestvideo+bestaudio/best" if not request.audio_only else "bestaudio/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "retries": request.max_retries,
        }
        if request.cookie_file and Path(request.cookie_file).is_file():
            ydl_opts["cookiefile"] = str(request.cookie_file)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(request.url, download=True)
            candidates = list(target_path.parent.glob(f"{target_path.stem}.*"))
            final_file = (
                target_path
                if target_path.exists()
                else (candidates[0] if candidates else target_path)
            )

        val = self.validator.validate(
            final_file, require_video=not request.audio_only, require_audio=True
        )
        elapsed = time.time() - start_time
        avg_speed = val.file_size / elapsed if elapsed > 0 else 0.0

        return DownloadResult(
            success=val.valid,
            path=str(final_file) if val.valid else None,
            platform=Platform.GENERIC.value,
            media_id=PlatformDetector.extract_media_id(request.url),
            duration=val.duration,
            width=val.width,
            height=val.height,
            fps=val.fps,
            video_codec=val.video_codec,
            audio_codec=val.audio_codec,
            file_size=val.file_size,
            elapsed_seconds=elapsed,
            average_speed=avg_speed,
            backend="ytdlp_generic",
            validation_passed=val.valid,
            error_message=val.error_message if not val.valid else None,
        )

    def execute(self, request: DownloadRequest) -> DownloadResult:
        """Executes download task with preflight inspection, caching and smart routing."""
        start_time = time.time()

        if request.is_cancelled():
            return DownloadResult(
                success=False,
                error_type=ErrorType.CANCELLED,
                error_message="Download cancelled before start",
            )

        preflight_res = self.preflight.analyze(request.url)
        platform = preflight_res.platform
        media_id = preflight_res.media_id

        if request.use_cache:
            cached_path = self.cache.lookup(
                platform=platform.value,
                media_id=media_id,
                require_audio=not request.audio_only,
            )
            if cached_path and cached_path.is_file():
                val = self.validator.validate(cached_path, require_video=not request.audio_only)
                if val.valid:
                    logger.info(f"Returning cached download result for {media_id} -> {cached_path}")
                    return DownloadResult(
                        success=True,
                        path=str(cached_path),
                        platform=platform.value,
                        media_id=media_id,
                        duration=val.duration,
                        width=val.width,
                        height=val.height,
                        fps=val.fps,
                        video_codec=val.video_codec,
                        audio_codec=val.audio_codec,
                        file_size=val.file_size,
                        elapsed_seconds=time.time() - start_time,
                        cache_hit=True,
                        validation_passed=True,
                        backend="cache",
                    )

        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if platform == Platform.BILIBILI:
            result = self.bilibili.download(request)
        elif platform == Platform.DOUYIN:
            result = self.douyin.download(request)
        else:
            target_name = request.custom_filename or f"video_{media_id}.mp4"
            result = self._download_generic_ytdlp(request, out_dir / target_name)

        if result.success and result.path and Path(result.path).is_file():
            if request.use_cache:
                self.cache.store(
                    platform=platform.value,
                    media_id=media_id,
                    file_path=result.path,
                    duration=result.duration,
                )
            self.perf_store.record_metric(
                platform=platform.value,
                host=result.cdn or result.backend,
                bytes_transferred=result.file_size,
                duration=result.elapsed_seconds,
                success=True,
            )
        else:
            self.perf_store.record_metric(
                platform=platform.value,
                host=result.cdn or result.backend,
                bytes_transferred=0,
                duration=result.elapsed_seconds,
                error_type=result.error_type.value if result.error_type else "error",
                success=False,
            )

        return result


_DEFAULT_ENGINE: DownloadDecisionEngine | None = None


def get_decision_engine() -> DownloadDecisionEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = DownloadDecisionEngine()
    return _DEFAULT_ENGINE
