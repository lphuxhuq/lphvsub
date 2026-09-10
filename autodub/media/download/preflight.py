"""Preflight analyzer and platform detection for media URLs."""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
from typing import Optional

import requests

from autodub.media.download.contract import Platform, PreflightResult

logger = logging.getLogger(__name__)

_BILIBILI_PATTERN = re.compile(r"(?:bilibili\.com|b23\.tv)", re.IGNORECASE)
_BILI_BV_PATTERN = re.compile(r"(BV[a-zA-Z0-9]{10})", re.IGNORECASE)
_BILI_AV_PATTERN = re.compile(r"(av\d+)", re.IGNORECASE)

_DOUYIN_PATTERN = re.compile(r"(?:douyin\.com|iesdouyin\.com)", re.IGNORECASE)
_DOUYIN_VID_PATTERN = re.compile(r"(?:video|note)/(\d+)|modal_id=(\d+)", re.IGNORECASE)

_YOUTUBE_PATTERN = re.compile(r"(?:youtube\.com|youtu\.be)", re.IGNORECASE)
_YT_VID_PATTERN = re.compile(r"(?:v=|/embed/|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})", re.IGNORECASE)


class PlatformDetector:
    """Detects platform and canonical media ID from raw URL."""

    @staticmethod
    def detect(url: str) -> Platform:
        clean_url = str(url).strip()
        if _BILIBILI_PATTERN.search(clean_url):
            return Platform.BILIBILI
        if _DOUYIN_PATTERN.search(clean_url):
            return Platform.DOUYIN
        if _YOUTUBE_PATTERN.search(clean_url):
            return Platform.YOUTUBE
        return Platform.GENERIC

    @staticmethod
    def extract_media_id(url: str, platform: Optional[Platform] = None) -> str:
        clean_url = str(url).strip()
        plat = platform or PlatformDetector.detect(clean_url)

        if plat == Platform.BILIBILI:
            m_bv = _BILI_BV_PATTERN.search(clean_url)
            if m_bv:
                return m_bv.group(1)
            m_av = _BILI_AV_PATTERN.search(clean_url)
            if m_av:
                return m_av.group(1)

        elif plat == Platform.DOUYIN:
            m_dy = _DOUYIN_VID_PATTERN.search(clean_url)
            if m_dy:
                return m_dy.group(1) or m_dy.group(2)

        elif plat == Platform.YOUTUBE:
            m_yt = _YT_VID_PATTERN.search(clean_url)
            if m_yt:
                return m_yt.group(1)

        normalized = clean_url.split("?")[0] if "?" in clean_url else clean_url
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class PreflightAnalyzer:
    """Analyzes target URL properties before initiating full download."""

    def __init__(self):
        self.detector = PlatformDetector()

    def analyze(self, url: str, session: Optional[requests.Session] = None) -> PreflightResult:
        """Inspects URL metadata, platform, and recommends optimal download strategy."""
        platform = self.detector.detect(url)
        media_id = self.detector.extract_media_id(url, platform)

        recommended_backend = "http"
        is_dash = False
        recommended_concurrency = 4

        if platform == Platform.BILIBILI:
            recommended_backend = "dash"
            is_dash = True
            recommended_concurrency = 4
        elif platform == Platform.DOUYIN:
            recommended_backend = "direct"
            is_dash = False
            recommended_concurrency = 2
        elif platform == Platform.YOUTUBE:
            recommended_backend = "ytdlp"
            is_dash = True
            recommended_concurrency = 4
        else:
            recommended_backend = "http"
            is_dash = False
            recommended_concurrency = 4

        return PreflightResult(
            platform=platform,
            media_id=media_id,
            has_video=True,
            has_audio=True,
            is_dash=is_dash,
            recommended_backend=recommended_backend,
            recommended_concurrency=recommended_concurrency,
        )
