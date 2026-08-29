"""Bộ tổng hợp giọng CapCut — gọi API, không cần model trên máy.

Hỗ trợ Device Pool đa thiết bị (fake nhiều device.json) chạy đa luồng tốc độ cao.
"""
from __future__ import annotations

import os
import random
import re
import subprocess
import threading
import time
from typing import Any, Optional, Tuple

from autodub.speech.tts.base import TTSResult, write_silence
from autodub.speech.tts.capcut_device_pool import get_device_pool
from autodub.utils import setup_logging

logger = setup_logging("autodub.tts.capcut")

#: Số câu đọc song song (mặc định 8 luồng song song với Device Pool, có thể tùy chỉnh qua Settings.capcut_threads hoặc CAPCUT_THREADS).
RECOMMENDED_THREADS = min(16, max(1, int(os.environ.get("CAPCUT_THREADS", "8"))))

#: Khoảng cách tối thiểu giữa hai lần gửi toàn cục và per-device
GLOBAL_MIN_GAP_S = 0.12
MIN_GAP_S = 0.15

#: Số lần thử lại một câu khi mạng chập chờn hoặc máy chủ báo bận.
RETRIES = 6
BACKOFF_S = (0.8, 1.2, 1.8, 2.8, 3.8, 5.0)

#: Số lần đổi định danh liên tiếp mà vẫn bị chặn thì bỏ cuộc.
MAX_ROTATIONS = 2

#: Trần thời gian: chờ máy chủ tạo xong, tải file, và chạy ffmpeg cho MỘT câu.
TASK_TIMEOUT_S = 60.0
DOWNLOAD_TIMEOUT_S = 30
FFMPEG_TIMEOUT_S = 60

OFFLINE_HINT = ("Giọng CapCut cần kết nối mạng. Kiểm tra mạng rồi chạy lại, "
                "hoặc chọn một giọng offline (VieNeu) ở ô chọn giọng.")

BLOCKED_HINT = ("Máy chủ CapCut đang tạm thời bận hoặc giới hạn kết nối (system busy / shark block). "
                "Hệ thống đã tự động thử lại và điều tiết nhịp gửi nhưng máy chủ vẫn chưa phản hồi. "
                "Hãy thử lại sau ít phút hoặc chọn một giọng offline (VieNeu) để lồng tiếng ngay.")

_GLOBAL_THROTTLE_LOCK = threading.Lock()
_global_next_slot = 0.0
_global_backoff_until = 0.0

_DEVICE_LOCK = threading.Lock()
_rotations = 0
_profile: dict | None = None


def _current_profile() -> dict:
    """Hồ sơ thiết bị dùng chung / mặc định."""
    global _profile
    with _DEVICE_LOCK:
        if _profile is None:
            from autodub.speech.tts import capcut_catalog
            _profile = capcut_catalog.device_profile()
        return _profile


def _note_success() -> None:
    """Đọc trôi một câu nghĩa là định danh hiện tại lành — cho lại lượt đổi."""
    global _rotations
    if _rotations:
        with _DEVICE_LOCK:
            _rotations = 0


def _rotate_profile(seen: dict) -> dict | None:
    """Đổi định danh máy sau khi bị chặn. None nghĩa là hết lượt đổi."""
    global _profile, _rotations
    with _DEVICE_LOCK:
        if _profile is not None and _profile is not seen:
            return _profile
        if _rotations >= MAX_ROTATIONS:
            return None
        from autodub.speech.tts import capcut_catalog
        _rotations += 1
        _profile = capcut_catalog.rotate_device()
        logger.warning("CapCut chặn định danh máy — đã đổi sang định danh mới "
                       f"(lần {_rotations}/{MAX_ROTATIONS}).")
        return _profile


def _trigger_global_backoff(duration_s: float = 1.0) -> None:
    """Khi một luồng gặp system busy, phanh nhẹ các luồng khác một khoảng ngắn tránh dồn dập."""
    global _global_backoff_until
    with _GLOBAL_THROTTLE_LOCK:
        _global_backoff_until = max(_global_backoff_until, time.monotonic() + duration_s)


def _throttle(device: Optional[dict] = None) -> None:
    """Giữ nhịp gửi toàn cục và nhịp riêng theo từng thiết bị."""
    global _global_next_slot
    with _GLOBAL_THROTTLE_LOCK:
        now = time.monotonic()
        if _global_backoff_until > now:
            wait_backoff = _global_backoff_until - now
            _global_next_slot = max(_global_next_slot, _global_backoff_until) + GLOBAL_MIN_GAP_S
        else:
            wait_slot = _global_next_slot - now
            _global_next_slot = max(now, _global_next_slot) + GLOBAL_MIN_GAP_S
            wait_backoff = max(0.0, wait_slot)

    if wait_backoff > 0:
        time.sleep(wait_backoff)

    if device is not None:
        get_device_pool().throttle_device(device, min_gap_s=MIN_GAP_S)


def _is_hard_block(error: Exception) -> bool:
    """Máy chủ chặn vĩnh viễn định danh máy (shark block / ret -6) — cần đổi thiết bị."""
    text = str(error).lower()
    return (
        "shark block" in text
        or "'ret': '-6'" in text
        or '"ret": "-6"' in text
    )


def _is_rate_limited(error: Exception) -> bool:
    """Máy chủ báo bận hoặc giới hạn tần suất tạm thời (system busy / ret 1014 / 1004 / 429)."""
    text = str(error).lower()
    return (
        "'ret': '1014'" in text
        or '"ret": "1014"' in text
        or "system busy" in text
        or "'ret': '1004'" in text
        or '"ret": "1004"' in text
        or "429" in text
        or "too many requests" in text
    )


def _is_shark_block(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải do máy chủ chặn thiết bị hay quá tải."""
    return _is_hard_block(error) or _is_rate_limited(error)


def _is_invalid_text(error: Exception) -> bool:
    text = str(error)
    return (
        "TTSInvalidText" in text
        or "err_code': 40402002" in text
        or "err_code\": 40402002" in text
        or "40402002" in text and "invalid" in text.lower()
    )


_CJK_RE = re.compile(r"[\u3400-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WEIRD_RE = re.compile(r"[^\w\s.,!?;:…\-–—'\"()/%&+À-ỹ]+", re.UNICODE)


def sanitize_capcut_text(text: str) -> str:
    """Làm sạch câu trước khi gửi CapCut — tránh TTSInvalidText."""
    cleaned = _CTRL_RE.sub("", text or "")
    cleaned = _CJK_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\u200b", "").replace("\ufeff", "")
    cleaned = cleaned.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    cleaned = _WEIRD_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 280:
        cut = cleaned[:280]
        sp = cut.rfind(" ")
        cleaned = (cut[:sp] if sp > 80 else cut).rstrip(" ,;:-")
        if cleaned and cleaned[-1] not in ".!?…":
            cleaned += "."
    return cleaned


class CapCutSynthesizer:
    """Đọc từng câu bằng API CapCut rồi chuyển sang WAV cho pipeline."""

    def __init__(self, settings, voice_name: str):
        from autodub.speech.tts import capcut_catalog
        from autodub.speech.tts.capcut_api import CapCutClient

        entry = capcut_catalog.lookup(voice_name)
        if entry is None:
            raise ValueError(f"Không có giọng CapCut tên «{voice_name}»")
        self.settings = settings
        self.voice_name = voice_name
        self._voice_type = entry["voice_type"]
        self._resource_id = entry["resource_id"]
        self._pool = get_device_pool()
        self._device = _current_profile()
        self._client = CapCutClient(device=self._device)
        self._local = threading.local()

    @property
    def recommended_threads(self) -> int:
        threads = getattr(self.settings, "capcut_threads", None)
        if threads:
            return min(16, max(1, int(threads)))
        env_val = os.environ.get("CAPCUT_THREADS")
        if env_val:
            return min(16, max(1, int(env_val)))
        return RECOMMENDED_THREADS

    # -- gọi máy chủ ------------------------------------------------------

    def _get_worker_client_and_device(self) -> Tuple[Any, dict]:
        """Lấy client và hồ sơ thiết bị riêng biệt cho từng luồng thực thi."""
        # Luồng phụ trong ThreadPoolExecutor (đa luồng thực sự):
        if threading.current_thread() is not threading.main_thread():
            client = getattr(self._local, "client", None)
            device = getattr(self._local, "device", None)
            if client is None or device is None:
                from autodub.speech.tts.capcut_api import CapCutClient
                device = self._pool.get_device()
                client = CapCutClient(device=device)
                self._local.client = client
                self._local.device = device
            return client, device

        return self._client, self._device

    def _soft_rotate_device(self, used: dict) -> None:
        """Xoay nhẹ sang thiết bị khác trong pool khi server báo bận mà không phạt cooldown."""
        if getattr(self._local, "client", None) is not None:
            new_dev = self._pool.rotate_device(used)
            if new_dev.get("device_id") != used.get("device_id"):
                from autodub.speech.tts.capcut_api import CapCutClient
                try:
                    self._local.client.session.close()
                except Exception:
                    pass
                self._local.device = new_dev
                self._local.client = CapCutClient(device=new_dev)

    def _reload_device(self, used: dict) -> bool:
        """Nhận định danh mới sau khi ``used`` bị chặn thực sự (shark block). False là hết đường."""
        from autodub.speech.tts.capcut_api import CapCutClient

        # Nếu đang ở worker thread có thread-local client:
        if getattr(self._local, "client", None) is not None:
            new_dev = self._pool.report_block(used)
            try:
                self._local.client.session.close()
            except Exception:
                pass
            self._local.device = new_dev
            self._local.client = CapCutClient(device=new_dev)
            return True

        profile = _rotate_profile(used)
        if profile is None:
            return False
        self.close()
        self._device = profile
        self._client = CapCutClient(device=profile)
        return True

    def _fetch_mp3(self, text: str) -> bytes:
        """MP3 do máy chủ đọc ra. Thử lại khi mạng lỗi; hết lượt thì ném."""
        last_error: Exception | None = None
        for attempt in range(RETRIES):
            client, used = self._get_worker_client_and_device()
            try:
                try:
                    _throttle(used)
                except TypeError:
                    _throttle()
                task = client.generate_speech(
                    texts=text, voice=self._voice_type,
                    resource_id=self._resource_id, wait=True,
                    timeout=TASK_TIMEOUT_S)
                url = (task or {}).get("speech_url") or (task or {}).get("audio_url")
                if not url:
                    raise RuntimeError(f"Máy chủ không trả link audio: {task}")
                resp = client.session.get(url, timeout=DOWNLOAD_TIMEOUT_S)
                resp.raise_for_status()
                if not resp.content:
                    raise RuntimeError("Máy chủ trả file audio rỗng")
                self._pool.report_success(used)
                _note_success()
                return resp.content
            except Exception as e:  # noqa: BLE001 — lỗi nào cũng đáng thử lại
                last_error = e
                if _is_invalid_text(e):
                    raise RuntimeError(
                        f"CapCut từ chối nội dung câu (TTSInvalidText): {text!r}"
                    ) from e
                
                # 1. Hard Block (shark block / ret -6) -> Thiết bị bị ban thật, phải đổi định danh
                if _is_hard_block(e):
                    if not self._reload_device(used):
                        raise RuntimeError(BLOCKED_HINT) from e
                    sleep_s = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
                    logger.warning(
                        f"CapCut chặn định danh máy ({e}) — đã đổi thiết bị và chờ {sleep_s:.1f}s (lần {attempt + 1}/{RETRIES})..."
                    )
                    time.sleep(sleep_s)
                    continue

                # 2. Soft Rate Limit (system busy / ret 1014) -> Máy chủ bận, hoãn nhịp và thử lại
                if _is_rate_limited(e):
                    _trigger_global_backoff(1.0)
                    self._soft_rotate_device(used)
                    base_sleep = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
                    jitter = random.uniform(0.1, 0.5)
                    sleep_s = base_sleep + jitter
                    logger.warning(
                        f"CapCut máy chủ phản hồi bận (system busy / ret=1014) — tạm hoãn {sleep_s:.2f}s và thử lại (lần {attempt + 1}/{RETRIES})..."
                    )
                    time.sleep(sleep_s)
                    continue

                if attempt < RETRIES - 1:
                    logger.warning(
                        f"CapCut lỗi (lần {attempt + 1}/{RETRIES}): {e}")
                    time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        if last_error is not None and (_is_hard_block(last_error) or _is_rate_limited(last_error)):
            raise RuntimeError(BLOCKED_HINT) from last_error
        raise RuntimeError(f"Không đọc được câu bằng giọng CapCut sau "
                           f"{RETRIES} lần thử: {last_error}. {OFFLINE_HINT}")

    # -- chuyển định dạng -------------------------------------------------

    @staticmethod
    def _to_wav(mp3_bytes: bytes, output_path: str) -> None:
        """MP3 → WAV mono 44.1 kHz qua stdin pipe siêu nhanh, không ghi tệp đệm."""
        from autodub.resources import FFMPEG_SLOTS

        with FFMPEG_SLOTS:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", "pipe:0", "-ac", "1", "-ar", "44100",
                 output_path],
                input=mp3_bytes,
                capture_output=True,
                timeout=FFMPEG_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0 or not os.path.isfile(output_path):
            err_msg = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            raise RuntimeError("ffmpeg không chuyển được audio CapCut "
                               f"sang WAV: {err_msg[-300:]}")

    # -- giao diện Synthesizer -------------------------------------------

    def synthesize(
        self,
        text: str,
        output_path: str,
        target_duration: float | None = None,
    ) -> TTSResult:
        """Đọc một câu ở tốc độ tự nhiên."""
        from autodub.media.audio import wav_duration_s
        from autodub.text.vi_numbers import normalize_vi_text

        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        text = sanitize_capcut_text(normalize_vi_text(text.strip()))
        if not text.strip(".,!?;: "):
            return write_silence(output_path)

        try:
            self._to_wav(self._fetch_mp3(text), output_path)
        except RuntimeError as e:
            if _is_invalid_text(e) or "TTSInvalidText" in str(e):
                logger.warning(
                    "CapCut từ chối câu %r — ghi clip im lặng, không dừng video.",
                    text[:80],
                )
                return write_silence(output_path, duration_s=max(0.12, min(1.2, (target_duration or 0.4))))
            raise
        duration = wav_duration_s(output_path) or 0.0
        return TTSResult(
            path=output_path,
            actual_duration=round(duration, 3),
            speed_adjusted=False,
            rate_applied="1.0x",
        )

    def close(self) -> None:
        """Đóng session HTTP khi pipeline chạy xong."""
        session = getattr(self._client, "session", None)
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        local_client = getattr(self._local, "client", None)
        if local_client is not None and getattr(local_client, "session", None):
            try:
                local_client.session.close()
            except Exception:
                pass
