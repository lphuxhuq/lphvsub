"""Media validation component using ffprobe to ensure downloaded files are intact."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Detailed result from media validation check."""

    valid: bool
    error_message: str | None = None
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    channels: int = 0
    file_size: int = 0
    has_video: bool = False
    has_audio: bool = False
    format_name: str = ""
    raw_info: dict[str, Any] | None = None


class MediaValidator:
    """Validates container integrity, streams, and duration using ffprobe."""

    def __init__(self, ffprobe_bin: str | None = None, timeout_seconds: float = 15.0):
        self.ffprobe_bin = ffprobe_bin or shutil.which("ffprobe") or "ffprobe"
        self.timeout_seconds = timeout_seconds

    def validate(
        self,
        file_path: str | Path,
        require_video: bool = True,
        require_audio: bool = False,
        min_bytes: int = 1024,
    ) -> ValidationResult:
        """Inspects and validates media file integrity.

        Args:
            file_path: Path to the media file.
            require_video: Whether a valid video stream is strictly required.
            require_audio: Whether a valid audio stream is strictly required.
            min_bytes: Minimum acceptable file size in bytes.

        Returns:
            ValidationResult with status and extracted metadata.
        """
        path = Path(file_path)
        if not path.is_file():
            return ValidationResult(
                valid=False,
                error_message=f"File does not exist or is not a regular file: {path}",
            )

        try:
            file_size = path.stat().st_size
        except OSError as e:
            return ValidationResult(
                valid=False,
                error_message=f"Cannot stat file {path}: {e}",
            )

        if file_size < min_bytes:
            return ValidationResult(
                valid=False,
                file_size=file_size,
                error_message=f"File size too small ({file_size} bytes < {min_bytes} bytes threshold). File is likely corrupted or truncated.",
            )

        # Probe file via ffprobe
        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,format_name:stream=codec_type,codec_name,width,height,r_frame_rate,channels",
            "-of",
            "json",
            str(path),
        ]

        try:
            # On Windows, hide console window
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                startupinfo=startupinfo,
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                valid=False,
                file_size=file_size,
                error_message=f"ffprobe timed out after {self.timeout_seconds}s on {path}",
            )
        except Exception as e:
            logger.warning(f"Failed to execute ffprobe: {e}")
            # If ffprobe itself cannot be executed, fallback to basic non-empty check
            return ValidationResult(
                valid=file_size >= min_bytes,
                file_size=file_size,
                error_message=f"ffprobe execution failed: {e}",
            )

        if proc.returncode != 0:
            err_text = (proc.stderr or "").strip()[:400]
            return ValidationResult(
                valid=False,
                file_size=file_size,
                error_message=f"Corrupt or invalid container (ffprobe exit {proc.returncode}): {err_text}",
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                file_size=file_size,
                error_message=f"Malformed ffprobe JSON output: {e}",
            )

        format_info = data.get("format", {})
        streams = data.get("streams", [])

        # Duration
        duration_val = 0.0
        try:
            raw_duration = format_info.get("duration")
            if raw_duration is not None:
                duration_val = float(raw_duration)
        except (ValueError, TypeError):
            duration_val = 0.0

        format_name = str(format_info.get("format_name", ""))

        has_video = False
        has_audio = False
        video_codec = ""
        audio_codec = ""
        width = 0
        height = 0
        fps = 0.0
        channels = 0

        for s in streams:
            ctype = s.get("codec_type")
            if ctype == "video" and not has_video:
                has_video = True
                video_codec = s.get("codec_name", "")
                width = int(s.get("width") or 0)
                height = int(s.get("height") or 0)
                fps = self._parse_fps(s.get("r_frame_rate"))
            elif ctype == "audio" and not has_audio:
                has_audio = True
                audio_codec = s.get("codec_name", "")
                channels = int(s.get("channels") or 0)

        # In case format duration was 0, check if video or audio stream has duration
        if duration_val <= 0.0:
            for s in streams:
                try:
                    s_dur = float(s.get("duration", 0))
                    if s_dur > 0:
                        duration_val = s_dur
                        break
                except (ValueError, TypeError):
                    pass

        # Validation rules
        if duration_val <= 0.05:
            return ValidationResult(
                valid=False,
                duration=duration_val,
                file_size=file_size,
                width=width,
                height=height,
                fps=fps,
                video_codec=video_codec,
                audio_codec=audio_codec,
                channels=channels,
                has_video=has_video,
                has_audio=has_audio,
                format_name=format_name,
                raw_info=data,
                error_message=f"Media duration is zero or invalid ({duration_val}s)",
            )

        if require_video:
            if not has_video or width <= 0 or height <= 0:
                return ValidationResult(
                    valid=False,
                    duration=duration_val,
                    file_size=file_size,
                    width=width,
                    height=height,
                    fps=fps,
                    video_codec=video_codec,
                    audio_codec=audio_codec,
                    channels=channels,
                    has_video=has_video,
                    has_audio=has_audio,
                    format_name=format_name,
                    raw_info=data,
                    error_message=f"Video stream missing or dimensions invalid (width={width}, height={height})",
                )

        if require_audio and not has_audio:
            return ValidationResult(
                valid=False,
                duration=duration_val,
                file_size=file_size,
                width=width,
                height=height,
                fps=fps,
                video_codec=video_codec,
                audio_codec=audio_codec,
                channels=channels,
                has_video=has_video,
                has_audio=has_audio,
                format_name=format_name,
                raw_info=data,
                error_message="Audio stream required but missing in downloaded media",
            )

        return ValidationResult(
            valid=True,
            duration=duration_val,
            file_size=file_size,
            width=width,
            height=height,
            fps=fps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            channels=channels,
            has_video=has_video,
            has_audio=has_audio,
            format_name=format_name,
            raw_info=data,
        )

    @staticmethod
    def _parse_fps(fps_str: Any) -> float:
        if not fps_str or not isinstance(fps_str, str):
            return 0.0
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/", 1)
                den_val = float(den)
                if den_val == 0:
                    return 0.0
                return float(num) / den_val
            return float(fps_str)
        except Exception:
            return 0.0
