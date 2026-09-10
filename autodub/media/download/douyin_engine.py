"""Douyin Turbo + Reliable Download Engine with Direct API and BrowserPool fallback."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from autodub.media.download.browser_pool import BrowserPool, get_browser_pool
from autodub.media.download.concurrency import AdaptiveConcurrencyController
from autodub.media.download.contract import (
    BandwidthMode,
    DownloadRequest,
    DownloadResult,
    ErrorType,
    Platform,
)
from autodub.media.download.partial_manager import PartialDownloadManager
from autodub.media.download.retry import ErrorClassifier, SmartRetryPolicy
from autodub.media.download.session_manager import CookieSessionManager
from autodub.media.download.validator import MediaValidator

logger = logging.getLogger(__name__)

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

_REFERER = "https://www.douyin.com/"
_IES_REFERER = "https://www.iesdouyin.com/"

_ROUTER_DATA_RE = re.compile(r"window\s*\._ROUTER_DATA\s*=\s*(\{.*?\});", re.DOTALL)
_SSR_DATA_RE = re.compile(r"window\s*\._SSR_DATA\s*=\s*(\{.*?\});", re.DOTALL)
_RENDER_DATA_RE = re.compile(r'<script\s+id="RENDER_DATA"[^>]*>([^<]+)</script>')
_UNIVERSAL_DATA_RE = re.compile(r"window\s*\[['\"]_UNIVERSAL_DATA_FOR_REHYDRATION_['\"]\]\s*=\s*(\{.*?\});", re.DOTALL)

_CDN_HOST_RE = re.compile(
    r"(?:douyinvod\.com|zjcdn\.com|douyincdn\.com|bytecdntp\.com|zijieapi\.com|pstatp\.com|bytegoofy\.com)",
    re.IGNORECASE,
)
_DASH_VIDEO_RE = re.compile(r"/video/(?:tos|tos-cn)/[^?]*\.(?:mp4|m4s)|mime_type=video_mp4", re.IGNORECASE)
_DASH_AUDIO_RE = re.compile(r"/audio/(?:tos|tos-cn)/[^?]*\.(?:mp4|m4s|mp3)|mime_type=audio_mp4", re.IGNORECASE)
_VIDEO_MIME_RE = re.compile(r"mime_type=video_mp4", re.IGNORECASE)


class DouyinDownloader:
    """High-reliability Douyin download engine combining Direct API, Range resume, and BrowserPool."""

    def __init__(
        self,
        session_manager: Optional[CookieSessionManager] = None,
        partial_manager: Optional[PartialDownloadManager] = None,
        validator: Optional[MediaValidator] = None,
        browser_pool: Optional[BrowserPool] = None,
    ):
        self.session_mgr = session_manager or CookieSessionManager()
        self.partial_mgr = partial_manager or PartialDownloadManager()
        self.validator = validator or MediaValidator()
        self.browser_pool = browser_pool or get_browser_pool()
        self.retry_policy = SmartRetryPolicy(max_retries=3)

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        for pattern in (r"/video/(\d+)", r"/note/(\d+)", r"modal_id=(\d+)"):
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def resolve_short_url(self, url: str, session: requests.Session) -> str:
        """Resolves v.douyin.com short URLs to full canonical video URLs."""
        if "v.douyin.com" not in url:
            return url

        for ua in (_MOBILE_UA, _DESKTOP_UA):
            try:
                resp = session.get(
                    url,
                    headers={"User-Agent": ua, "Referer": _REFERER},
                    allow_redirects=True,
                    timeout=12,
                    stream=True,
                )
                final_url = resp.url
                resp.close()
                if self.extract_video_id(final_url):
                    return final_url
            except Exception as e:
                logger.debug(f"Short URL resolution attempt failed: {e}")
        return url

    def fetch_direct_api_info(self, video_id: str, session: requests.Session) -> Optional[Dict[str, Any]]:
        """Extracts direct no-watermark video play URL via mobile API and embedded JSON."""
        api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
        try:
            resp = session.get(
                api_url,
                headers={"User-Agent": _MOBILE_UA, "Referer": _IES_REFERER, "Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                items = data.get("item_list", [])
                if items:
                    item = items[0]
                    video_obj = item.get("video", {})
                    play_addr = video_obj.get("play_addr", {})
                    url_list = play_addr.get("url_list", [])
                    clean_play_url = ""
                    for u in url_list:
                        if u:
                            clean_play_url = u.replace("playwm", "play")
                            break
                    uri = play_addr.get("uri", "")
                    title = (item.get("desc") or "").strip()
                    duration = (video_obj.get("duration") or item.get("duration") or 0) / 1000.0
                    if clean_play_url or uri:
                        return {
                            "play_url": clean_play_url,
                            "uri": uri,
                            "title": title,
                            "duration": duration,
                        }
        except Exception as e:
            logger.debug(f"Douyin API endpoint failed for {video_id}: {e}")

        share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        try:
            resp = session.get(share_url, headers={"User-Agent": _MOBILE_UA}, timeout=12)
            if resp.status_code == 200:
                html = resp.text
                for pattern, name in [
                    (_ROUTER_DATA_RE, "ROUTER_DATA"),
                    (_SSR_DATA_RE, "SSR_DATA"),
                    (_RENDER_DATA_RE, "RENDER_DATA"),
                    (_UNIVERSAL_DATA_RE, "UNIVERSAL_DATA"),
                ]:
                    m = pattern.search(html)
                    if not m:
                        continue
                    try:
                        raw = m.group(1)
                        if name == "RENDER_DATA":
                            raw = urllib.parse.unquote(raw)
                        data = json.loads(raw)

                        for loader_val in data.get("loaderData", {}).values():
                            if not isinstance(loader_val, dict):
                                continue
                            items = loader_val.get("videoInfoRes", {}).get("item_list", [])
                            if items:
                                item = items[0]
                                video_obj = item.get("video", {})
                                url_list = video_obj.get("play_addr", {}).get("url_list", [])
                                clean_url = url_list[0].replace("playwm", "play") if url_list else ""
                                uri = video_obj.get("play_addr", {}).get("uri", "")
                                title = (item.get("desc") or "").strip()
                                duration = (video_obj.get("duration") or 0) / 1000.0
                                if clean_url or uri:
                                    return {
                                        "play_url": clean_url,
                                        "uri": uri,
                                        "title": title,
                                        "duration": duration,
                                    }
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Douyin share page extraction failed for {video_id}: {e}")

        return None

    def extract_via_browser_pool(self, url: str, wait_seconds: float = 15.0) -> Dict[str, Any]:
        """Sniffs direct CDN URLs using pooled Chromium page."""
        captured = {"dash_video": [], "dash_audio": [], "progressive": []}
        title = ""
        canonical_url = url

        def on_request(req):
            u = req.url
            if not _CDN_HOST_RE.search(u):
                return
            if _DASH_VIDEO_RE.search(u):
                captured["dash_video"].append(u)
            elif _DASH_AUDIO_RE.search(u):
                captured["dash_audio"].append(u)
            elif _VIDEO_MIME_RE.search(u):
                captured["progressive"].append(u)

        def on_response(resp):
            nonlocal title
            try:
                if "aweme/v1/web/aweme/detail" in resp.url:
                    data = resp.json()
                    detail = data.get("aweme_detail") or {}
                    if detail:
                        if not title:
                            desc = detail.get("desc")
                            if desc:
                                title = desc.strip()
                        vid_obj = detail.get("video") or {}
                        # 1. Bit rates (sorted highest first)
                        bit_rates = vid_obj.get("bit_rate") or []
                        if bit_rates:
                            sorted_br = sorted(bit_rates, key=lambda b: b.get("bit_rate", 0), reverse=True)
                            for br in sorted_br:
                                for play_u in br.get("play_addr", {}).get("url_list", []):
                                    if play_u and play_u not in captured["progressive"]:
                                        captured["progressive"].append(play_u)
                        # 2. General play_addr
                        for play_u in vid_obj.get("play_addr", {}).get("url_list", []):
                            if play_u and play_u not in captured["progressive"]:
                                captured["progressive"].append(play_u)
            except Exception as ex:
                logger.debug(f"Parsing aweme detail response failed: {ex}")

        with self.browser_pool.borrow_page(user_agent=_DESKTOP_UA) as page:
            page.on("request", on_request)
            page.on("response", on_response)
            logger.info(f"Loading Douyin page via BrowserPool: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)

            # Dismiss login modal dialog if present to unblock video playback
            try:
                page.wait_for_timeout(800)
                page.keyboard.press("Escape")
                page.evaluate("""() => {
                    const svgs = document.querySelectorAll('svg');
                    for (const s of svgs) {
                        const rect = s.getBoundingClientRect();
                        if (rect.width > 0 && rect.width < 50 && rect.top > 100 && rect.top < 350 && rect.left > 600 && rect.left < 1000) {
                            s.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        }
                    }
                }""")
            except Exception as e:
                logger.debug(f"Modal dismissal non-fatal: {e}")

            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if captured["progressive"] or (captured["dash_video"] and captured["dash_audio"]):
                    break
                # Inspect DOM video currentSrc directly if network sniffer hasn't registered yet
                try:
                    dom_src = page.evaluate("""() => {
                        const vids = Array.from(document.querySelectorAll('video'));
                        for (const v of vids) {
                            const s = v.currentSrc || v.src;
                            if (s && s.startsWith('http') && !s.includes('blob:') && !s.includes('uuu_265')) {
                                return s;
                            }
                        }
                        return '';
                    }""")
                    if dom_src and _CDN_HOST_RE.search(dom_src) and dom_src not in captured["progressive"]:
                        captured["progressive"].append(dom_src)
                        break
                except Exception:
                    pass
                page.wait_for_timeout(400)

            if not title:
                title = page.title() or ""
                title = re.sub(r"\s*[-–]\s*抖音\s*$", "", title).strip()
            canonical_url = page.url

        video_id = self.extract_video_id(canonical_url) or ""

        if captured["dash_video"] and captured["dash_audio"]:
            return {
                "mode": "dash",
                "video_url": captured["dash_video"][-1],
                "audio_url": captured["dash_audio"][-1],
                "title": title,
                "video_id": video_id,
            }

        if captured["progressive"]:
            return {
                "mode": "progressive",
                "video_url": captured["progressive"][-1],
                "title": title,
                "video_id": video_id,
            }

        raise RuntimeError("BrowserPool could not capture video streams from Douyin page.")

    def mux_dash_streams(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        """Muxes DASH video and audio streams using FFmpeg stream copy."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg muxing failed: {res.stderr[:300]}")
        return output_path

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Executes the full Douyin download lifecycle with fallback and validation."""
        start_time = time.time()
        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        session = self.session_mgr.create_session(Platform.DOUYIN, cookie_file=request.cookie_file)

        canonical_url = self.resolve_short_url(request.url, session)
        video_id = self.extract_video_id(canonical_url) or f"dy_{int(time.time())}"

        target_name = request.custom_filename or f"douyin_{video_id}.mp4"
        target_path = out_dir / target_name

        backend_used = "direct_api"
        retries_count = 0

        direct_info = self.fetch_direct_api_info(video_id, session) if video_id.isdigit() else None
        if direct_info and (direct_info.get("play_url") or direct_info.get("uri")):
            play_urls = []
            if direct_info.get("play_url"):
                play_urls.append(direct_info["play_url"])
            if direct_info.get("uri"):
                play_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={direct_info['uri']}&ratio=1080p&line=0")
                play_urls.append(f"https://www.iesdouyin.com/aweme/v1/play/?video_id={direct_info['uri']}&ratio=1080p&line=0")

            for p_url in play_urls:
                if request.is_cancelled():
                    return DownloadResult(success=False, error_type=ErrorType.CANCELLED, error_message="Cancelled by user")
                try:
                    self.partial_mgr.download_progressive_stream(
                        url=p_url,
                        target_path=target_path,
                        session=session,
                        headers={"User-Agent": _MOBILE_UA, "Referer": _REFERER},
                        progress_callback=request.progress_callback,
                        is_cancelled=request.is_cancelled,
                    )
                    val = self.validator.validate(target_path, require_video=True, require_audio=not request.audio_only)
                    if val.valid:
                        elapsed = time.time() - start_time
                        avg_speed = val.file_size / elapsed if elapsed > 0 else 0.0
                        return DownloadResult(
                            success=True,
                            path=str(target_path),
                            platform=Platform.DOUYIN.value,
                            media_id=video_id,
                            duration=val.duration,
                            width=val.width,
                            height=val.height,
                            fps=val.fps,
                            video_codec=val.video_codec,
                            audio_codec=val.audio_codec,
                            file_size=val.file_size,
                            elapsed_seconds=elapsed,
                            average_speed=avg_speed,
                            backend="direct_api",
                            validation_passed=True,
                        )
                except Exception as exc:
                    retries_count += 1
                    logger.warning(f"Direct API download failed for candidate {p_url}: {exc}")

        backend_used = "browser_pool"
        logger.info(f"Falling back to BrowserPool for Douyin: {canonical_url}")

        try:
            candidate_urls = []
            if video_id and video_id.isdigit():
                canonical_video = f"https://www.douyin.com/video/{video_id}"
                candidate_urls.append(canonical_video)
                modal_route = f"https://www.douyin.com/jingxuan?modal_id={video_id}"
                if modal_route not in candidate_urls:
                    candidate_urls.append(modal_route)
                discover_route = f"https://www.douyin.com/discover?modal_id={video_id}"
                if discover_route not in candidate_urls:
                    candidate_urls.append(discover_route)

            for cand in [request.url, canonical_url]:
                if cand and cand not in candidate_urls and "/user/self" not in cand:
                    candidate_urls.append(cand)

            if not candidate_urls:
                candidate_urls = [canonical_url or request.url]

            last_exc = None
            for cand_url in candidate_urls:
                try:
                    sniff_res = self.extract_via_browser_pool(cand_url)
                    mode = sniff_res.get("mode")

                    if mode == "dash":
                        v_part = out_dir / f"temp_{video_id}_v.mp4"
                        a_part = out_dir / f"temp_{video_id}_a.mp4"

                        self.partial_mgr.download_progressive_stream(
                            url=sniff_res["video_url"],
                            target_path=v_part,
                            session=session,
                            headers={"User-Agent": _DESKTOP_UA, "Referer": _REFERER},
                            is_cancelled=request.is_cancelled,
                        )
                        self.partial_mgr.download_progressive_stream(
                            url=sniff_res["audio_url"],
                            target_path=a_part,
                            session=session,
                            headers={"User-Agent": _DESKTOP_UA, "Referer": _REFERER},
                            is_cancelled=request.is_cancelled,
                        )

                        self.mux_dash_streams(v_part, a_part, target_path)

                        v_part.unlink(missing_ok=True)
                        a_part.unlink(missing_ok=True)

                    else:
                        self.partial_mgr.download_progressive_stream(
                            url=sniff_res["video_url"],
                            target_path=target_path,
                            session=session,
                            headers={"User-Agent": _DESKTOP_UA, "Referer": _REFERER},
                            progress_callback=request.progress_callback,
                            is_cancelled=request.is_cancelled,
                        )

                    val = self.validator.validate(target_path, require_video=True, require_audio=not request.audio_only)
                    elapsed = time.time() - start_time
                    avg_speed = val.file_size / elapsed if elapsed > 0 else 0.0

                    if val.valid:
                        return DownloadResult(
                            success=True,
                            path=str(target_path),
                            platform=Platform.DOUYIN.value,
                            media_id=video_id,
                            duration=val.duration,
                            width=val.width,
                            height=val.height,
                            fps=val.fps,
                            video_codec=val.video_codec,
                            audio_codec=val.audio_codec,
                            file_size=val.file_size,
                            elapsed_seconds=elapsed,
                            average_speed=avg_speed,
                            retries=retries_count,
                            backend=backend_used,
                            validation_passed=True,
                        )
                except Exception as exc:
                    last_exc = exc
                    logger.warning(f"BrowserPool attempt failed for {cand_url}: {exc}")

            if last_exc:
                raise last_exc

        except Exception as exc:
            elapsed = time.time() - start_time
            err_type = ErrorClassifier.classify(exc)
            return DownloadResult(
                success=False,
                platform=Platform.DOUYIN.value,
                media_id=video_id,
                elapsed_seconds=elapsed,
                backend=backend_used,
                validation_passed=False,
                error_message=str(exc),
                error_type=err_type,
            )
