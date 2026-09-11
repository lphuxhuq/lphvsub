"""Download Cache integrated with MediaValidator and SQLite persistence."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import time
from pathlib import Path

from autodub.media.download.validator import MediaValidator
from autodub.pipeline_cache import cache_root

logger = logging.getLogger(__name__)


class DownloadCache:
    """Caches validated downloaded media files by platform and media_id."""

    def __init__(self, db_path: Path | str | None = None, validator: MediaValidator | None = None):
        if db_path is None:
            base_dir = cache_root().parent / "downloads"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "download_cache.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.validator = validator or MediaValidator()
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS download_cache (
                    cache_key TEXT PRIMARY KEY,
                    platform TEXT,
                    media_id TEXT,
                    quality TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    duration REAL,
                    created_at REAL,
                    last_accessed REAL
                )
            """)
            conn.commit()

    @staticmethod
    def make_key(platform: str, media_id: str, quality: str = "default") -> str:
        raw = f"{platform}:{media_id}:{quality}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def lookup(
        self,
        platform: str,
        media_id: str,
        quality: str = "default",
        require_audio: bool = False,
    ) -> Path | None:
        """Looks up a previously downloaded media file and verifies it with MediaValidator."""
        key = self.make_key(platform, media_id, quality)
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_path, file_size, duration FROM download_cache WHERE cache_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            file_path = Path(row[0])
            if not file_path.is_file():
                cursor.execute("DELETE FROM download_cache WHERE cache_key = ?", (key,))
                conn.commit()
                return None

            val_res = self.validator.validate(
                file_path, require_video=True, require_audio=require_audio
            )
            if not val_res.valid:
                logger.warning(
                    f"Cache entry corrupted ({val_res.error_message}), evicting {file_path}"
                )
                cursor.execute("DELETE FROM download_cache WHERE cache_key = ?", (key,))
                conn.commit()
                return None

            cursor.execute(
                "UPDATE download_cache SET last_accessed = ? WHERE cache_key = ?",
                (time.time(), key),
            )
            conn.commit()
            logger.info(f"DownloadCache HIT: {platform}:{media_id} -> {file_path}")
            return file_path

    def store(
        self,
        platform: str,
        media_id: str,
        file_path: Path | str,
        quality: str = "default",
        duration: float = 0.0,
    ) -> None:
        """Stores a validated media file into the download cache."""
        path = Path(file_path)
        if not path.is_file():
            return

        size = path.stat().st_size
        key = self.make_key(platform, media_id, quality)
        now = time.time()

        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO download_cache
                    (cache_key, platform, media_id, quality, file_path, file_size, duration, created_at, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (key, platform, media_id, quality, str(path), size, duration, now, now),
                )
                conn.commit()
                logger.info(f"DownloadCache STORED: {platform}:{media_id} -> {path}")
        except Exception as e:
            logger.warning(f"Failed to store entry in DownloadCache: {e}")
