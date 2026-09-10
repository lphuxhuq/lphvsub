"""Smart Download Engine package for LPHVSub / VoxDub Studio."""

from autodub.media.download.contract import (
    BandwidthMode,
    DownloadRequest,
    DownloadResult,
    ErrorType,
    Platform,
    PreflightResult,
)

__all__ = [
    "Platform",
    "ErrorType",
    "BandwidthMode",
    "DownloadRequest",
    "PreflightResult",
    "DownloadResult",
]
