"""Data contracts, models and exceptions for the Smart Download Engine."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class Platform(str, enum.Enum):
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    YOUTUBE = "youtube"
    GENERIC = "generic"


class ErrorType(str, enum.Enum):
    AUTH_ERROR = "auth_error"  # HTTP 403 / expired cookie
    RANGE_NOT_SATISFIABLE = "range_not_satisfiable"  # HTTP 416
    RATE_LIMITED = "rate_limited"  # HTTP 429
    TIMEOUT = "timeout"  # Network socket timeout
    CONNECTION_RESET = "connection_reset"  # Reset by peer
    MISSING_AUDIO = "missing_audio"  # Video downloaded without expected audio
    INVALID_MEDIA = "invalid_media"  # Truncated container, 0 duration, corrupt codec
    NOT_FOUND = "not_found"  # HTTP 404
    NETWORK_ERROR = "network_error"  # Generic network failure
    CANCELLED = "cancelled"  # User cancelled
    UNKNOWN = "unknown"


class BandwidthMode(str, enum.Enum):
    AUTO = "auto"
    FAST = "fast"
    STABLE = "stable"
    LOW = "low"


@dataclass
class DownloadRequest:
    """Specification of a download task requested by downstream callers."""

    url: str
    output_dir: str
    cookie_file: str | None = None
    audio_only: bool = False
    max_retries: int = 4
    bandwidth_mode: BandwidthMode = BandwidthMode.AUTO
    cancel_event: Any | None = None
    progress_callback: Callable[[dict[str, Any]], None] | None = None
    headers: dict[str, str] | None = None
    preferred_quality: str | None = None
    custom_filename: str | None = None
    use_cache: bool = True
    concurrency_override: int | None = None

    def is_cancelled(self) -> bool:
        if self.cancel_event is None:
            return False
        if hasattr(self.cancel_event, "is_set"):
            return bool(self.cancel_event.is_set())
        return bool(self.cancel_event)


@dataclass
class PreflightResult:
    """Result of metadata probing and preflight inspection before downloading."""

    platform: Platform
    media_id: str
    title: str = ""
    has_video: bool = True
    has_audio: bool = True
    is_dash: bool = False
    estimated_size: int = 0
    candidate_cdns: list[str] = field(default_factory=list)
    recommended_backend: str = "http"
    recommended_concurrency: int = 4
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    probe_latency_ms: float = 0.0
    direct_play_url: str | None = None
    audio_stream_url: str | None = None


@dataclass
class DownloadResult:
    """Standardized download execution result contract for all backends."""

    success: bool
    path: str | None = None
    platform: str = ""
    media_id: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    file_size: int = 0
    elapsed_seconds: float = 0.0
    average_speed: float = 0.0
    peak_speed: float = 0.0
    retries: int = 0
    backend: str = ""
    cdn: str = ""
    resumed: bool = False
    cache_hit: bool = False
    validation_passed: bool = True
    error_message: str | None = None
    error_type: ErrorType | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "path": self.path,
            "platform": self.platform,
            "media_id": self.media_id,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "file_size": self.file_size,
            "elapsed_seconds": self.elapsed_seconds,
            "average_speed": self.average_speed,
            "peak_speed": self.peak_speed,
            "retries": self.retries,
            "backend": self.backend,
            "cdn": self.cdn,
            "resumed": self.resumed,
            "cache_hit": self.cache_hit,
            "validation_passed": self.validation_passed,
            "error_message": self.error_message,
            "error_type": self.error_type.value if self.error_type else None,
            "telemetry": self.telemetry,
        }

    def __getitem__(self, item: str) -> Any:
        """Allow dict-like subscripting for backward compatibility with old code."""
        return self.to_dict()[item]

    def get(self, item: str, default: Any = None) -> Any:
        return self.to_dict().get(item, default)
