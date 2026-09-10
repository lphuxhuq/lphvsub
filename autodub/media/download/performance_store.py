"""Telemetry and performance store for tracking download speeds, errors and CDN health."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Optional

from autodub.pipeline_cache import cache_root

logger = logging.getLogger(__name__)


class PerformanceStore:
    """Stores download metrics and calculates CDN health scores across sessions."""

    _instance: Optional[PerformanceStore] = None
    _init_lock = threading.Lock()

    def __new__(cls, db_path: Optional[Path | str] = None):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: Optional[Path | str] = None):
        if getattr(self, "_initialized", False):
            return

        if db_path is None:
            base_dir = cache_root().parent / "downloads"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "performance.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdn_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    platform TEXT,
                    host TEXT,
                    bytes_transferred INTEGER,
                    duration REAL,
                    speed REAL,
                    status_code INTEGER,
                    error_type TEXT,
                    success INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cdn_host ON cdn_metrics(platform, host);")
            conn.commit()

    def record_metric(
        self,
        platform: str,
        host: str,
        bytes_transferred: int,
        duration: float,
        status_code: int = 200,
        error_type: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """Records a single download transaction or chunk transfer metric."""
        speed = (bytes_transferred / duration) if duration > 0 else 0.0
        now = time.time()
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO cdn_metrics 
                    (timestamp, platform, host, bytes_transferred, duration, speed, status_code, error_type, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now, platform, host, bytes_transferred, duration, speed, status_code, error_type or "", 1 if success else 0),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record metric in PerformanceStore: {e}")

    def get_health_score(self, platform: str, host: str) -> float:
        """Computes health score from 0.0 to 100.0 based on recent transaction history."""
        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT success, speed, error_type FROM cdn_metrics
                    WHERE platform = ? AND host = ?
                    ORDER BY id DESC LIMIT 50
                    """,
                    (platform, host),
                )
                rows = cursor.fetchall()
                if not rows:
                    return 80.0

                success_count = sum(1 for r in rows if r[0] == 1)
                success_rate = (success_count / len(rows)) * 100.0

                rate_limit_count = sum(1 for r in rows if "rate_limit" in (r[2] or ""))
                penalty = rate_limit_count * 10.0

                score = max(0.0, min(100.0, success_rate - penalty))
                return score
        except Exception as e:
            logger.warning(f"Error computing health score for {host}: {e}")
            return 75.0

    def get_fastest_cdns(self, platform: str, limit: int = 3) -> List[str]:
        """Returns the top hosts ranked by average transfer speed."""
        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT host, AVG(speed) as avg_speed, SUM(success)*1.0 / COUNT(*) as succ_rate
                    FROM cdn_metrics
                    WHERE platform = ?
                    GROUP BY host
                    HAVING succ_rate >= 0.7
                    ORDER BY avg_speed DESC
                    LIMIT ?
                    """,
                    (platform, limit),
                )
                return [r[0] for r in cursor.fetchall() if r[0]]
        except Exception as e:
            logger.warning(f"Error getting fastest CDNs: {e}")
            return []
