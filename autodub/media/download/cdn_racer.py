"""Lightweight CDN Racing Engine to probe, score and rank multiple media CDN candidates."""

from __future__ import annotations

import concurrent.futures
import logging
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class CdnProbeResult:
    url: str
    host: str
    latency_ms: float
    status_code: int
    accepts_ranges: bool
    content_length: int = 0
    error: Optional[str] = None
    score: float = 0.0


class CdnRacingEngine:
    """Probes candidate CDN URLs concurrently with minimal bandwidth to pick the fastest and most reliable."""

    def __init__(self, probe_timeout: float = 2.0, max_probes: int = 4):
        self.probe_timeout = probe_timeout
        self.max_probes = max_probes

    @staticmethod
    def extract_host(url: str) -> str:
        try:
            return urllib.parse.urlparse(url).netloc
        except Exception:
            return "unknown"

    def probe_candidate(
        self,
        url: str,
        session: requests.Session,
        headers: Optional[Dict[str, str]] = None,
    ) -> CdnProbeResult:
        """Sends a lightweight byte-range probe (first 1024 bytes) to measure TTFB and range support."""
        host = self.extract_host(url)
        probe_headers = dict(headers or {})
        probe_headers["Range"] = "bytes=0-1023"

        start_time = time.perf_counter()
        try:
            resp = session.get(url, headers=probe_headers, timeout=self.probe_timeout, stream=True)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            status = resp.status_code
            accepts_ranges = (status == 206) or ("bytes" in resp.headers.get("Accept-Ranges", "").lower())
            content_length = int(resp.headers.get("Content-Length", 0))

            _ = resp.raw.read(1024)
            resp.close()

            if status in (200, 206):
                score = (10000.0 / max(1.0, latency_ms))
                if accepts_ranges:
                    score += 50.0
            else:
                score = -100.0

            return CdnProbeResult(
                url=url,
                host=host,
                latency_ms=latency_ms,
                status_code=status,
                accepts_ranges=accepts_ranges,
                content_length=content_length,
                score=score,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return CdnProbeResult(
                url=url,
                host=host,
                latency_ms=latency_ms,
                status_code=0,
                accepts_ranges=False,
                error=str(e),
                score=-500.0,
            )

    def race_candidates(
        self,
        candidate_urls: List[str],
        session: requests.Session,
        headers: Optional[Dict[str, str]] = None,
    ) -> List[CdnProbeResult]:
        """Races top candidates concurrently and returns results sorted from best to worst."""
        if not candidate_urls:
            return []

        if len(candidate_urls) == 1:
            res = self.probe_candidate(candidate_urls[0], session, headers)
            return [res]

        probes_to_run = candidate_urls[:self.max_probes]
        results: List[CdnProbeResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(probes_to_run), 4)) as executor:
            future_to_url = {
                executor.submit(self.probe_candidate, u, session, headers): u
                for u in probes_to_run
            }
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    u = future_to_url[future]
                    results.append(CdnProbeResult(
                        url=u,
                        host=self.extract_host(u),
                        latency_ms=9999.0,
                        status_code=0,
                        accepts_ranges=False,
                        error=str(e),
                        score=-1000.0,
                    ))

        tested_urls = {r.url for r in results}
        for u in candidate_urls:
            if u not in tested_urls:
                results.append(CdnProbeResult(
                    url=u,
                    host=self.extract_host(u),
                    latency_ms=500.0,
                    status_code=200,
                    accepts_ranges=True,
                    score=0.0,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results
