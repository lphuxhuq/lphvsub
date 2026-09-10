"""Partial download manager supporting HTTP Range resume, metadata tracking and crash resilience."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from autodub.media.download.contract import ErrorType
from autodub.media.download.retry import ErrorClassifier

logger = logging.getLogger(__name__)


@dataclass
class FragmentInfo:
    index: int
    start_byte: int
    end_byte: int
    completed: bool = False
    file_path: str = ""


@dataclass
class DownloadProgressState:
    url: str
    target_path: str
    part_path: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_dash: bool = False
    fragments: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DownloadProgressState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PartialDownloadManager:
    """Manages progressive and fragmented downloads with robust resume capability."""

    def __init__(self, buffer_size: int = 65536):
        self.buffer_size = buffer_size

    def get_progress_meta_path(self, target_path: Path | str) -> Path:
        p = Path(target_path)
        return p.parent / f"{p.name}.progress.json"

    def get_part_path(self, target_path: Path | str) -> Path:
        p = Path(target_path)
        return p.parent / f"{p.name}.part"

    def load_state(self, target_path: Path | str) -> Optional[DownloadProgressState]:
        meta_file = self.get_progress_meta_path(target_path)
        if not meta_file.is_file():
            return None
        try:
            content = meta_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return DownloadProgressState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to read progress metadata from {meta_file}: {e}")
            return None

    def save_state(self, state: DownloadProgressState) -> None:
        meta_file = self.get_progress_meta_path(state.target_path)
        tmp_meta = meta_file.parent / f"{meta_file.name}.tmp"
        state.updated_at = time.time()
        try:
            tmp_meta.write_text(state.to_json(), encoding="utf-8")
            if meta_file.exists():
                meta_file.unlink(missing_ok=True)
            tmp_meta.replace(meta_file)
        except Exception as e:
            logger.warning(f"Failed to atomically persist progress metadata {meta_file}: {e}")

    def cleanup_artifacts(self, target_path: Path | str) -> None:
        meta_file = self.get_progress_meta_path(target_path)
        part_file = self.get_part_path(target_path)
        try:
            if meta_file.exists():
                meta_file.unlink(missing_ok=True)
            if part_file.exists():
                part_file.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"Error cleaning up partial artifacts for {target_path}: {e}")

    def download_progressive_stream(
        self,
        url: str,
        target_path: Path | str,
        session: requests.Session,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        timeout: float = 30.0,
    ) -> Path:
        """Downloads a progressive HTTP stream with Range resume support."""
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        part_file = self.get_part_path(target)

        state = self.load_state(target)
        existing_bytes = 0
        if part_file.is_file():
            existing_bytes = part_file.stat().st_size

        req_headers = dict(headers or {})
        resumed = False

        if existing_bytes > 0:
            req_headers["Range"] = f"bytes={existing_bytes}-"
            resumed = True
            logger.info(f"Attempting to resume download from byte offset {existing_bytes} for {target.name}")

        start_time = time.time()
        resp = None
        try:
            resp = session.get(url, headers=req_headers, stream=True, timeout=timeout)

            # Handle 416 Range Not Satisfiable
            if resp.status_code == 416:
                logger.warning(f"Server returned 416 for {url}. Resetting byte offset.")
                existing_bytes = 0
                req_headers.pop("Range", None)
                resp.close()
                resp = session.get(url, headers=req_headers, stream=True, timeout=timeout)
                resumed = False

            resp.raise_for_status()

            # Determine mode: 206 Partial Content means resume accepted, 200 means full body returned
            if resp.status_code == 206:
                content_range = resp.headers.get("Content-Range", "")
                total_bytes = 0
                if "/" in content_range:
                    try:
                        total_bytes = int(content_range.split("/")[-1])
                    except ValueError:
                        pass
                if total_bytes == 0:
                    content_length = int(resp.headers.get("Content-Length", 0))
                    total_bytes = existing_bytes + content_length
                write_mode = "ab"
                bytes_downloaded = existing_bytes
            else:
                # 200 OK -> full content, start from beginning
                total_bytes = int(resp.headers.get("Content-Length", 0))
                write_mode = "wb"
                bytes_downloaded = 0
                resumed = False

            etag = resp.headers.get("ETag")
            last_modified = resp.headers.get("Last-Modified")

            # Update progress state
            current_state = DownloadProgressState(
                url=url,
                target_path=str(target),
                part_path=str(part_file),
                total_bytes=total_bytes,
                downloaded_bytes=bytes_downloaded,
                etag=etag,
                last_modified=last_modified,
            )
            self.save_state(current_state)

            last_callback_time = time.time()
            bytes_since_last_tick = 0

            with open(part_file, write_mode) as f:
                for chunk in resp.iter_content(chunk_size=self.buffer_size):
                    if is_cancelled and is_cancelled():
                        raise RuntimeError("Download cancelled by user")

                    if not chunk:
                        continue

                    f.write(chunk)
                    chunk_len = len(chunk)
                    bytes_downloaded += chunk_len
                    bytes_since_last_tick += chunk_len

                    now = time.time()
                    elapsed_tick = now - last_callback_time
                    if elapsed_tick >= 0.25: # Debounced progress reporting
                        speed = bytes_since_last_tick / elapsed_tick if elapsed_tick > 0 else 0.0
                        percent = (bytes_downloaded / total_bytes * 100.0) if total_bytes > 0 else 0.0
                        eta = (total_bytes - bytes_downloaded) / speed if (speed > 0 and total_bytes > bytes_downloaded) else 0.0

                        current_state.downloaded_bytes = bytes_downloaded
                        self.save_state(current_state)

                        if progress_callback:
                            progress_callback({
                                "status": "downloading",
                                "bytes_downloaded": bytes_downloaded,
                                "total_bytes": total_bytes,
                                "percent": percent,
                                "speed_bps": speed,
                                "speed_mb": speed / (1024 * 1024),
                                "eta_seconds": eta,
                                "resumed": resumed,
                            })

                        last_callback_time = now
                        bytes_since_last_tick = 0

            # Atomic rename from .part to final target
            if target.exists():
                target.unlink(missing_ok=True)
            part_file.replace(target)
            self.cleanup_artifacts(target)
            return target

        except Exception as e:
            if resp:
                resp.close()
            # Preserve .part file and .progress.json on error! Do not delete them!
            logger.warning(f"Download stream error for {url}: {e}. Partial file preserved at {part_file}")
            raise
