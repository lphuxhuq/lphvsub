"""Bộ điều phối nạp trước toàn cục cho các Model AI (Model Preloader Pool).

Giúp tải và làm ấm (pre-warm) trước các mô hình AI trong luồng nền (background thread):
1. Paraformer (ĐẦU TIÊN): khởi động worker sherpa-onnx CPU (.venv-asr) nhận diện tiếng Trung.
2. Faster-Whisper: nạp model vào VRAM/RAM qua WhisperCache.
3. Demucs: khởi động worker --serve trong .venv-gpu, sau đó tự trả VRAM về CPU.
(Các model khác như VieNeu-TTS, LaMa ONNX được nạp on-demand khi có tác vụ yêu cầu).
"""
from __future__ import annotations

import os
import threading
from typing import Callable

from autodub.config import Settings
from autodub.resources import GPU_LOCK
from autodub.utils import setup_logging

logger = setup_logging("autodub.model_preloader")


class GlobalModelPool:
    """Singleton quản lý các cache và session AI dùng chung cho toàn bộ ứng dụng."""

    def __init__(self):
        self._lock = threading.Lock()
        self._paraformer_cache = None
        self._whisper_cache = None
        self._demucs_cache = None
        self._synth_cache = None
        self._lama_engine = None
        self._align_model = None

        self._status: dict[str, str] = {
            "paraformer": "idle",
            "whisper": "idle",
            "demucs": "idle",
            "vieneu": "idle",
            "lama": "idle",
            "align": "idle",
        }
        self._preload_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._is_preloading = False

    def get_paraformer_cache(self):
        with self._lock:
            if self._paraformer_cache is None:
                from autodub.speech.paraformer_transcriber import ParaformerCache
                self._paraformer_cache = ParaformerCache()
            return self._paraformer_cache

    def get_whisper_cache(self):
        with self._lock:
            if self._whisper_cache is None:
                from autodub.speech.transcriber import WhisperCache
                self._whisper_cache = WhisperCache()
            return self._whisper_cache

    def get_demucs_cache(self):
        with self._lock:
            if self._demucs_cache is None:
                from autodub.media.vocal_separator import DemucsCache
                self._demucs_cache = DemucsCache()
            return self._demucs_cache

    def get_synth_cache(self):
        with self._lock:
            if self._synth_cache is None:
                from autodub.speech.tts import SynthCache
                self._synth_cache = SynthCache()
            return self._synth_cache

    def get_lama_engine(self):
        with self._lock:
            if self._lama_engine is None:
                from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine
                self._lama_engine = LaMaOnnxEngine()
            return self._lama_engine

    def get_align_model(self):
        with self._lock:
            if self._align_model is None:
                from autodub.speech.align import _create_whisper_align_model
                self._align_model = _create_whisper_align_model()
            return self._align_model

    def status(self) -> dict[str, str]:
        with self._lock:
            return dict(self._status)

    def is_all_ready(self) -> bool:
        with self._lock:
            active = [self._status[k] for k in ("paraformer", "whisper", "demucs") if self._status.get(k) != "unsupported"]
            return len(active) > 0 and all(v in ("ready", "skipped") for v in active)

    def preload_all_async(
        self,
        settings: Settings,
        on_step: Callable[[str, str], None] | None = None,
        on_done: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        """Kích hoạt nạp trước tất cả các model sẵn có trong background thread."""
        with self._lock:
            if self._is_preloading:
                logger.info("Tiến trình nạp trước model đang chạy dở — bỏ qua gọi trùng")
                return
            self._is_preloading = True
            self._cancel_event.clear()

        def _worker():
            logger.info("Bắt đầu tiến trình nạp trước các model AI (Paraformer, Whisper, Demucs)...")

            if self._cancel_event.is_set():
                with self._lock:
                    self._is_preloading = False
                return

            # -------------------------------------------------------------
            # 1. PARAFORMER (ĐẦU TIÊN): Nhẹ, nhanh (~1s, CPU), nhận diện tiếng Trung
            # -------------------------------------------------------------
            if settings.paraformer_configured():
                try:
                    self._set_status("paraformer", "loading", on_step)
                    logger.info("⚡ [1/3] Nạp trước Paraformer (tiếng Trung, CPU)...")
                    pf_cache = self.get_paraformer_cache()
                    ok = pf_cache._ensure(settings)
                    self._set_status("paraformer", "ready" if ok else "failed", on_step)
                    if ok:
                        logger.info("✓ Paraformer đã sẵn sàng!")
                except Exception as e:
                    logger.warning(f"Nạp trước Paraformer gặp lỗi ({e})")
                    self._set_status("paraformer", "failed", on_step)
            else:
                self._set_status("paraformer", "unsupported", on_step)

            if self._cancel_event.is_set():
                with self._lock:
                    self._is_preloading = False
                return

            # -------------------------------------------------------------
            # 2. FASTER-WHISPER: Nạp model nhận diện/alignment vào GPU/CPU
            # -------------------------------------------------------------
            try:
                self._set_status("whisper", "loading", on_step)
                logger.info("⚡ [2/3] Nạp trước Faster-Whisper...")
                w_cache = self.get_whisper_cache()
                w_cache.get(settings)
                self._set_status("whisper", "ready", on_step)
                logger.info("✓ Faster-Whisper đã sẵn sàng!")
            except Exception as e:
                logger.warning(f"Nạp trước Faster-Whisper gặp lỗi ({e})")
                self._set_status("whisper", "failed", on_step)

            if self._cancel_event.is_set():
                with self._lock:
                    self._is_preloading = False
                return

            # -------------------------------------------------------------
            # 3. DEMUCS: Khởi động worker phục vụ tách nhạc nền (GPU worker)
            # -------------------------------------------------------------
            from autodub.media.vocal_separator import gpu_venv_python
            if gpu_venv_python():
                try:
                    self._set_status("demucs", "loading", on_step)
                    logger.info("⚡ [3/3] Nạp trước Demucs vocal separator (GPU worker)...")
                    d_cache = self.get_demucs_cache()
                    ok = d_cache._ensure()
                    self._set_status("demucs", "ready" if ok else "failed", on_step)
                    if ok:
                        logger.info("✓ Demucs worker đã sẵn sàng!")
                except Exception as e:
                    logger.warning(f"Nạp trước Demucs gặp lỗi ({e})")
                    self._set_status("demucs", "failed", on_step)
            else:
                self._set_status("demucs", "unsupported", on_step)

            with self._lock:
                self._is_preloading = False
                final_status = dict(self._status)

            logger.info(f"Hoàn tất nạp trước các model AI: {final_status}")
            if on_done and not self._cancel_event.is_set():
                try:
                    on_done(final_status)
                except Exception as e:
                    logger.warning(f"on_done callback lỗi ({e})")

        t = threading.Thread(target=_worker, name="model-preloader", daemon=True)
        self._preload_thread = t
        t.start()

    def _set_status(self, key: str, val: str, cb: Callable[[str, str], None] | None = None) -> None:
        with self._lock:
            self._status[key] = val
        if cb:
            try:
                cb(key, val)
            except Exception:
                pass

    def close_all(self) -> None:
        """Đóng toàn bộ session và dừng mọi tiến trình worker khi thoát ứng dụng."""
        self._cancel_event.set()
        t = self._preload_thread
        if t is not None and t.is_alive() and t != threading.current_thread():
            t.join(timeout=1.5)

        with self._lock:
            logger.info("Dọn dẹp và đóng toàn bộ Model Preloader Pool...")
            if self._paraformer_cache is not None:
                try:
                    self._paraformer_cache.close()
                except Exception as e:
                    logger.warning(f"Đóng ParaformerCache lỗi ({e})")
                self._paraformer_cache = None

            if self._demucs_cache is not None:
                try:
                    self._demucs_cache.close()
                except Exception as e:
                    logger.warning(f"Đóng DemucsCache lỗi ({e})")
                self._demucs_cache = None

            if self._synth_cache is not None:
                try:
                    self._synth_cache.close()
                except Exception as e:
                    logger.warning(f"Đóng SynthCache lỗi ({e})")
                self._synth_cache = None

            if self._whisper_cache is not None:
                try:
                    self._whisper_cache.close()
                except Exception as e:
                    logger.warning(f"Đóng WhisperCache lỗi ({e})")
                self._whisper_cache = None

            if self._align_model is not None:
                try:
                    from autodub.speech.align import unload_align_model
                    unload_align_model()
                except Exception as e:
                    logger.warning(f"Unload align model lỗi ({e})")

            self._lama_engine = None
            self._align_model = None
            for k in self._status:
                self._status[k] = "idle"
            self._is_preloading = False
            self._preload_thread = None


# Global Pool Instance
_GLOBAL_POOL = GlobalModelPool()


def get_global_model_pool() -> GlobalModelPool:
    return _GLOBAL_POOL


def get_global_paraformer_cache():
    return _GLOBAL_POOL.get_paraformer_cache()


def get_global_whisper_cache():
    return _GLOBAL_POOL.get_whisper_cache()


def get_global_demucs_cache():
    return _GLOBAL_POOL.get_demucs_cache()


def get_global_synth_cache():
    return _GLOBAL_POOL.get_synth_cache()


def get_global_lama_engine():
    return _GLOBAL_POOL.get_lama_engine()


def get_global_align_model():
    return _GLOBAL_POOL.get_align_model()


def preload_models_async(settings: Settings, on_step=None, on_done=None) -> None:
    _GLOBAL_POOL.preload_all_async(settings, on_step=on_step, on_done=on_done)


def close_global_models() -> None:
    _GLOBAL_POOL.close_all()
