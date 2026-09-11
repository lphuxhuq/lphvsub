"""Session and cookie manager for Bilibili and Douyin."""

from __future__ import annotations

import http.cookiejar
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from autodub.media.download.contract import Platform

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

DEFAULT_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class CookieSessionManager:
    """Manages reusable HTTP sessions, default headers, and cookie extraction."""

    def __init__(self):
        self._sessions: dict[str, requests.Session] = {}

    def get_headers(self, platform: Platform | str, mobile: bool = False) -> dict[str, str]:
        """Returns standard headers required by the platform."""
        ua = DEFAULT_MOBILE_USER_AGENT if mobile else DEFAULT_USER_AGENT
        plat_str = platform.value if isinstance(platform, Platform) else str(platform).lower()

        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,vi;q=0.6",
            "Accept-Encoding": "identity",  # Avoid compressed stream range complications
        }

        if plat_str == Platform.BILIBILI.value:
            headers["Referer"] = "https://www.bilibili.com/"
            headers["Origin"] = "https://www.bilibili.com"
        elif plat_str == Platform.DOUYIN.value:
            headers["Referer"] = "https://www.douyin.com/"
            headers["Origin"] = "https://www.douyin.com"

        return headers

    def load_cookie_file(self, cookie_path: str | Path) -> requests.cookies.RequestsCookieJar:
        """Parses a Netscape or standard cookie file into a RequestsCookieJar."""
        jar = requests.cookies.RequestsCookieJar()
        path = Path(cookie_path)
        if not path.is_file():
            logger.warning(f"Cookie file not found: {path}")
            return jar

        try:
            cj = http.cookiejar.MozillaCookieJar(str(path))
            cj.load(ignore_discard=True, ignore_expires=True)
            for c in cj:
                jar.set_cookie(c)
        except Exception as e:
            logger.warning(
                f"Standard MozillaCookieJar load failed for {path} ({e}), attempting fallback parser."
            )
            # Fallback line-by-line parsing
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        domain, _, path_val, secure, _, name, val = parts[:7]
                        jar.set(name, val, domain=domain, path=path_val)
            except Exception as ex2:
                logger.error(f"Failed to parse cookie file {path}: {ex2}")

        return jar

    def has_bilibili_auth(self, jar: requests.cookies.RequestsCookieJar) -> bool:
        """Checks if valid Bilibili session token exists in cookie jar."""
        return any(c.name == "SESSDATA" and len(c.value) > 10 for c in jar)

    def has_douyin_auth(self, jar: requests.cookies.RequestsCookieJar) -> bool:
        """Checks if valid Douyin session or tracking cookie exists."""
        names = {c.name for c in jar}
        return bool(names.intersection({"sessionid", "ttwid", "passport_csrf_token"}))

    def create_session(
        self,
        platform: Platform | str = Platform.GENERIC,
        cookie_file: str | Path | None = None,
        pool_connections: int = 10,
        pool_maxsize: int = 20,
    ) -> requests.Session:
        """Creates and tunes a requests.Session with connection pooling."""
        session = requests.Session()

        # Mount robust HTTPAdapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=Retry(total=0, connect=0, read=0),  # Retry is handled by SmartRetryPolicy
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set default headers
        session.headers.update(self.get_headers(platform))

        # Load cookies if provided
        if cookie_file:
            cookies = self.load_cookie_file(cookie_file)
            session.cookies.update(cookies)

        return session

    @staticmethod
    def mask_headers(headers: dict[str, str]) -> dict[str, str]:
        """Masks sensitive authentication and cookie values for secure logging."""
        masked = {}
        for k, v in headers.items():
            if k.lower() in ("cookie", "authorization", "x-signature"):
                masked[k] = "***MASKED***"
            else:
                masked[k] = v
        return masked
