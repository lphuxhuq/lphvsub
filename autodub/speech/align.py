"""Forced alignment cho phụ đề karaoke — mốc THẬT của từng chữ tiếng Việt.

CapCut lấy mốc chữ bằng cách chạy ASR trên audio. Ở đây điều kiện còn tốt
hơn: audio là giọng TTS studio-sạch (không nhạc nền) và VĂN BẢN ĐÃ BIẾT
TRƯỚC (chính là bản dịch) — chỉ cần mốc thời gian, không cần đoán chữ.

Cách làm: Whisper ``base`` (đã có sẵn qua faster-whisper trong app, ~150 MB,
tự tải lần đầu) nghe TỪNG clip WAV với ``word_timestamps=True``, rồi khớp
chuỗi chữ Whisper nghe được với chuỗi chữ của bản dịch:

- Số chữ hai bên bằng nhau (đa số — tiếng Việt đơn âm tiết) → map 1:1.
- Lệch nhau → nội suy vị trí (chữ thứ i của bản dịch lấy mốc của chữ
  ``i * n_asr / n_text`` phía Whisper). Nhịp vẫn đúng vì tổng thời lượng và
  các mốc neo là thật; chỉ ranh giới giữa các chữ bị nhòe nhẹ.

Mỗi clip độc lập — một clip khớp hỏng chỉ mất alignment của đúng clip đó
(caller tự rơi về ước lượng). Kết quả cache JSON trong work_dir nên resume
và rebuild không phải nghe lại.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from autodub.utils import save_json_atomic, seg_wav_path, setup_logging

logger = setup_logging("autodub.align")

# Lock đồng bộ ghi cache đa luồng
_CACHE_LOCK = threading.Lock()


@dataclass
class AlignmentStats:
    """Bảng ghi nhận số liệu profiling và hiệu năng canh phụ đề."""

    total_segments: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    model_load_time: float = 0.0
    asr_time: float = 0.0
    acoustic_time: float = 0.0
    mapping_time: float = 0.0
    cache_load_time: float = 0.0
    cache_write_time: float = 0.0
    total_time: float = 0.0
    ok_count: int = 0
    est_count: int = 0
    segments_per_sec: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_segments": self.total_segments,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "model_load_time": round(self.model_load_time, 4),
            "asr_time": round(self.asr_time, 4),
            "acoustic_time": round(self.acoustic_time, 4),
            "mapping_time": round(self.mapping_time, 4),
            "cache_load_time": round(self.cache_load_time, 4),
            "cache_write_time": round(self.cache_write_time, 4),
            "total_time": round(self.total_time, 4),
            "ok_count": self.ok_count,
            "est_count": self.est_count,
            "segments_per_sec": round(self.segments_per_sec, 2),
        }


# Phiên bản thuật toán cache - tăng khi cấu trúc/kết quả timing thay đổi
ALIGN_CACHE_VERSION = 2

# Model alignment: "base" đủ cho audio TTS sạch; đổi chỉ khi có lý do đo được.
ALIGN_MODEL = "base"

# Clip ngắn hơn mức này không đáng chạy model — ước lượng là đủ.
_MIN_CLIP_S = 0.15


def build_cache_key(
    wav_path: str,
    text: str,
    model_name: str = ALIGN_MODEL,
    language: str = "vi",
    version: int = ALIGN_CACHE_VERSION,
) -> str:
    """Tạo khóa cache tất định dựa trên audio fingerprint, text và cấu hình alignment.

    Sử dụng compute_media_fingerprint (kết hợp kích thước và nội dung file WAV) để đảm bảo
    khóa cache 100% tất định giữa các lần chạy, không phụ thuộc vào st_mtime_ns.
    """
    try:
        from autodub.pipeline_cache import compute_media_fingerprint

        audio_fp = compute_media_fingerprint(wav_path)[:16]
    except Exception:
        try:
            st = os.stat(wav_path)
            audio_fp = f"{st.st_size}"
        except OSError:
            audio_fp = "0_0"

    raw_payload = f"{audio_fp}|{text.strip()}|{model_name}|{language}|v{version}"
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:24]
    return f"v{version}_{digest}"


def compute_align_workers_and_threads(
    device: str = "cpu", cpu_count: int | None = None
) -> tuple[int, int]:
    """Tính số worker song song và số threads CTranslate2 tránh oversubscription.

    Trả về (n_workers, cpu_threads).
    - GPU (CUDA): Luôn dùng 1 worker, 1 thread vì GPU là tài nguyên tập trung.
    - CPU: Tự động cân bằng giữa pool workers và intra-op threads để không vượt quá tổng số nhân CPU.
    """
    env_workers = os.getenv("ALIGN_WORKERS")
    env_threads = os.getenv("ALIGN_CPU_THREADS")

    if str(device).lower() == "cuda":
        if env_workers is not None:
            try:
                return max(1, int(env_workers)), 1
            except ValueError:
                logger.debug("Bỏ qua lỗi ValueError trong align.py", exc_info=True)
        return 4, 1

    if env_workers is not None and env_threads is not None:
        try:
            return max(1, int(env_workers)), max(1, int(env_threads))
        except ValueError:
            logger.debug("Bỏ qua lỗi ValueError trong align.py", exc_info=True)

    if cpu_count <= 2:
        workers = 1
        threads = max(1, cpu_count)
    elif cpu_count <= 4:
        workers = 2
        threads = 2
    elif cpu_count <= 8:
        workers = 2
        threads = 3
    else:
        workers = max(2, min(4, cpu_count // 4))
        threads = max(2, min(4, (cpu_count - 2) // workers))

    if env_workers is not None:
        try:
            workers = max(1, int(env_workers))
        except ValueError:
            logger.debug("Bỏ qua lỗi ValueError trong align.py", exc_info=True)

    if env_threads is not None:
        try:
            threads = max(1, int(env_threads))
        except ValueError:
            logger.debug("Bỏ qua lỗi ValueError trong align.py", exc_info=True)

    return workers, threads


_CACHED_ALIGN_MODEL = None


def _create_whisper_align_model():
    """Khởi tạo Whisper base cho alignment. Trả (model, device, n_workers)."""
    from faster_whisper import WhisperModel

    from autodub.resources import GPU_LOCK
    from autodub.speech.transcriber import _enable_cuda_dlls

    if _enable_cuda_dlls():
        workers, _ = compute_align_workers_and_threads("cuda")
        with GPU_LOCK:
            for compute in ("float16", "int8_float16", "int8"):
                try:
                    model = WhisperModel(
                        ALIGN_MODEL, device="cuda", compute_type=compute, num_workers=workers
                    )
                    return model, "cuda", workers
                except Exception as e:
                    logger.debug(f"Alignment GPU {compute} không chạy ({e})")
        logger.info("Alignment dùng CPU")
    workers, threads = compute_align_workers_and_threads("cpu")
    model = WhisperModel(
        ALIGN_MODEL, device="cpu", compute_type="int8", cpu_threads=threads, num_workers=workers
    )
    return model, "cpu", workers


def _load_align_model():
    """Whisper base cho alignment. Ưu tiên tái sử dụng Singleton từ GlobalModelPool."""
    global _CACHED_ALIGN_MODEL
    if _CACHED_ALIGN_MODEL is not None:
        return _CACHED_ALIGN_MODEL

    try:
        from autodub.model_preloader import get_global_align_model

        _CACHED_ALIGN_MODEL = get_global_align_model()
        return _CACHED_ALIGN_MODEL
    except Exception:
        logger.debug("Bỏ qua lỗi Exception trong align.py", exc_info=True)

    _CACHED_ALIGN_MODEL = _create_whisper_align_model()
    return _CACHED_ALIGN_MODEL


def unload_align_model():
    """Giải phóng mô hình alignment khi cần tiết kiệm bộ nhớ."""
    global _CACHED_ALIGN_MODEL
    _CACHED_ALIGN_MODEL = None
    try:
        from autodub.model_preloader import get_global_model_pool

        pool = get_global_model_pool()
        with pool._lock:
            pool._align_model = None
            if "align" in pool._status:
                pool._status["align"] = "idle"
    except Exception:
        logger.debug("Bỏ qua lỗi Exception trong align.py", exc_info=True)


# Beam size cho ASR alignment: 1 (greedy) nhanh gấp đôi, 2 (beam search) khi cần
ALIGN_BEAM_SIZE = int(os.getenv("ALIGN_BEAM_SIZE", "1"))


def _asr_words(
    model,
    wav_path: str,
    beam_size: int = ALIGN_BEAM_SIZE,
    expected_word_count: int | None = None,
    **kwargs,
) -> list[tuple[str, float, float]]:
    """Chữ + mốc (tương đối trong clip) Whisper nghe được từ một clip."""
    transcribe_kwargs = {
        "language": "vi",
        "word_timestamps": True,
        "beam_size": beam_size,
        "best_of": 1,
        "temperature": 0.0,
        "repetition_penalty": 1.2,
        "no_repeat_ngram_size": 3,
        "condition_on_previous_text": False,
        "vad_filter": False,
    }
    if expected_word_count and expected_word_count > 0:
        transcribe_kwargs["max_new_tokens"] = max(32, min(448, expected_word_count * 3 + 16))

    segments, _info = model.transcribe(wav_path, **transcribe_kwargs)
    out: list[tuple[str, float, float]] = []
    for seg in segments:
        for w in seg.words or []:
            token = w.word.strip()
            if token:
                out.append((token, float(w.start), float(w.end)))
    return out


def _map_words(
    text_words: list[str],
    asr_words: list[tuple[str, float, float]],
    clip_start: float,
    clip_dur: float,
) -> list[tuple[str, float, float]] | None:
    """Gán mốc cho từng chữ của bản dịch từ mốc Whisper nghe được.

    Trả về mốc TUYỆT ĐỐI (đã cộng ``clip_start``), hoặc None khi không có mốc nào.
    """
    nt, na = len(text_words), len(asr_words)
    if nt == 0 or na == 0:
        return None
    # Khi ASR quá thưa thớt (ví dụ 1 từ / 4 từ), trả None để fallback sang acoustic RMS energy
    if na < nt * 0.4 or (na == 1 and nt >= 3):
        return None

    out: list[tuple[str, float, float]] = []
    if na == nt:
        pairs = zip(text_words, asr_words)
        for token, (_w, t0, t1) in pairs:
            out.append((token, clip_start + t0, clip_start + t1))
    else:
        # Nội suy vị trí: khớp theo tỷ lệ hoặc neo theo khoảng phát âm thực tế của ASR
        first_t0 = asr_words[0][1]
        last_t1 = asr_words[-1][2]
        effective_dur = max(0.1, last_t1 - first_t0)

        for i, token in enumerate(text_words):
            j0 = min(na - 1, int(i * na / nt))
            j1 = min(na - 1, int((i + 1) * na / nt))
            t0 = asr_words[j0][1]
            t1 = asr_words[j1][2] if j1 > j0 else asr_words[j0][2]

            # Nếu chênh lệch số lượng từ quá lớn, phân bổ đều theo khoảng hoạt động của ASR
            if na < nt * 0.5 or na > nt * 2.0:
                t0 = first_t0 + (i / nt) * effective_dur
                t1 = first_t0 + ((i + 1) / nt) * effective_dur

            out.append((token, clip_start + t0, clip_start + max(t1, t0)))

    # Vá đơn điệu: mốc phải không lùi và nằm trong clip
    hi = clip_start + clip_dur
    prev = clip_start
    fixed: list[tuple[str, float, float]] = []
    for token, t0, t1 in out:
        t0 = min(max(t0, prev), hi)
        t1 = min(max(t1, t0 + 0.02), hi)
        fixed.append((token, round(t0, 3), round(t1, 3)))
        prev = t0
    return fixed


def validate_alignment(
    words: list[tuple[str, float, float]],
    text_words: list[str],
    clip_start: float,
    clip_dur: float,
) -> bool:
    """Xác thực tính hợp lệ tuyệt đối của mốc thời gian phụ đề trước khi xuất ra.

    Kiểm tra:
    - Đúng số lượng từ
    - Không timestamp âm
    - Không đảo ngược thời gian (t0 <= t1)
    - Thứ tự thời gian tiến dần đều (từ sau không bắt đầu trước từ trước)
    - Nằm trong phạm vi cho phép của clip
    """
    if not words or len(words) != len(text_words):
        return False

    max_allowed_end = clip_start + clip_dur + 0.35  # Chừa dung sai tail
    prev_t0 = clip_start - 0.05

    for token, t0, t1 in words:
        if t0 < 0 or t1 < 0:
            return False
        if t0 > t1:
            return False
        if t0 < prev_t0 - 0.001:  # Mốc bắt đầu phải đơn điệu tiến dần
            return False
        if t1 > max_allowed_end:
            return False
        prev_t0 = t0

    return True


def align_segments(
    segments: list[dict],
    merge_dir: str,
    text_field: str,
    cache_path: str | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    stats: AlignmentStats | None = None,
) -> dict[int, list[tuple[str, float, float]]]:
    """Alignment thật cho mọi segment. Trả ``{id: [(chữ, t0, t1), ...]}``.

    Mốc trả về TUYỆT ĐỐI theo timeline video (clip đặt tại ``seg["start"]``).
    Segment thiếu file/khớp hỏng thì vắng mặt trong kết quả — caller bù bằng
    ước lượng. Cache theo (mtime clip, text) nên chỉ câu bị re-TTS/sửa chữ
    mới phải nghe lại.
    """
    from autodub.media.audio import wav_duration_s

    t0_total = time.perf_counter()
    if stats is None:
        stats = AlignmentStats()

    cache: dict = {}
    if cache_path and os.path.exists(cache_path):
        t0_c = time.perf_counter()
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}
        stats.cache_load_time += time.perf_counter() - t0_c

    # UPC: Tra cứu thêm từ AlignGlobalCache cho các câu đã canh nhịp trước đó
    global_hits: dict = {}
    use_upc = os.environ.get("LPHVSub_DISABLE_CACHE", "0") != "1"  # noqa: SIM112 — giữ tên env cũ
    if use_upc:
        try:
            from autodub.pipeline_cache import get_align_cache

            candidate_keys = []
            for s in segments:
                w_path = seg_wav_path(merge_dir, s["id"])
                if os.path.exists(w_path):
                    candidate_keys.append(build_cache_key(w_path, str(s.get(text_field, ""))))
            if candidate_keys:
                global_hits = get_align_cache().lookup_batch(candidate_keys)
        except Exception as ex:
            logger.debug(f"AlignGlobalCache lookup error: {ex}")

    out: dict[int, list[tuple[str, float, float]]] = {}
    todo: list[tuple[dict, str, float, str]] = []  # (seg, wav, dur, key)
    for seg in segments:
        sid = seg.get("id")
        text = str(seg.get(text_field, "")).strip()
        if not text:
            continue
        stats.total_segments += 1
        wav = seg_wav_path(merge_dir, sid)
        if not os.path.exists(wav):
            continue
        dur = wav_duration_s(wav)
        if not dur or dur < _MIN_CLIP_S:
            continue
        key = build_cache_key(
            wav, text, model_name=ALIGN_MODEL, language="vi", version=ALIGN_CACHE_VERSION
        )
        hit = cache.get(key) or global_hits.get(key)
        if hit:
            stats.cache_hits += 1
            base = float(seg["start"])
            out[sid] = [(w, round(base + t0, 3), round(base + t1, 3)) for w, t0, t1 in hit]
            continue
        stats.cache_misses += 1
        todo.append((seg, wav, dur, key))

    if not todo:
        stats.total_time = time.perf_counter() - t0_total
        stats.ok_count = len(out)
        stats.segments_per_sec = (
            stats.total_segments / stats.total_time if stats.total_time > 0 else 0.0
        )
        return out

    total = len(todo)
    n_cached = len(out)
    cached_info = f", {n_cached} câu dùng lại từ bộ nhớ đệm" if n_cached else ""
    logger.info(
        f"Đang canh phụ đề nhảy đúng nhịp giọng đọc ({total} câu{cached_info}) "
        f"— đang khởi động mô hình Whisper {ALIGN_MODEL}..."
    )
    if progress_cb:
        try:
            progress_cb(0.0, f"Khởi động mô hình canh nhịp phụ đề ({total} câu)...")
        except Exception:
            logger.debug("Bỏ qua lỗi Exception trong align.py", exc_info=True)

    t0_model = time.perf_counter()
    try:
        model, device, n_workers = _load_align_model()
        stats.model_load_time += time.perf_counter() - t0_model
    except Exception as e:
        stats.model_load_time += time.perf_counter() - t0_model
        logger.warning(
            f"Không canh được phụ đề theo giọng đọc ({e}) — chữ sẽ chia đều theo thời lượng câu"
        )
        stats.total_time = time.perf_counter() - t0_total
        stats.segments_per_sec = (
            stats.total_segments / stats.total_time if stats.total_time > 0 else 0.0
        )
        return out

    dev_name = str(device).upper()
    logger.info(
        f"Đã nạp Whisper {ALIGN_MODEL} ({dev_name}, {n_workers} luồng). "
        f"Bắt đầu canh nhịp chi tiết {total} câu:"
    )

    def _one(item):
        seg, wav, dur, key = item
        sid = seg.get("id")
        text = str(seg.get(text_field, "")).strip()
        text_words = text.split()
        t_asr = 0.0
        t_map = 0.0
        t_acoustic = 0.0

        # Fast-path router: Câu ngắn (<=1.20s, <=4 từ) hoặc câu 1-2 từ (<=1.8s) thử Acoustic Energy trước!
        if (dur <= 1.20 and len(text_words) <= 4) or (dur <= 1.80 and len(text_words) <= 2):
            try:
                t0_ac = time.perf_counter()
                from autodub.speech.acoustic_align import analyze_acoustic_alignment

                ac_res = analyze_acoustic_alignment(text, wav, float(seg["start"]), dur)
                t_acoustic = time.perf_counter() - t0_ac
                if ac_res.confidence >= 0.70 and validate_alignment(
                    ac_res.words, text_words, float(seg["start"]), dur
                ):
                    return (
                        sid,
                        key,
                        float(seg["start"]),
                        ac_res.words,
                        "acoustic",
                        len(ac_res.words),
                        text,
                        0.0,
                        0.0,
                        t_acoustic,
                    )
            except Exception as e:
                logger.debug(f"Acoustic fast-path câu {sid} bỏ qua ({e})")

        # Normal-path: Whisper ASR
        try:
            t0_a = time.perf_counter()
            try:
                asr = _asr_words(
                    model, wav, beam_size=ALIGN_BEAM_SIZE, expected_word_count=len(text_words)
                )
            except TypeError:
                asr = _asr_words(model, wav)
            t_asr = time.perf_counter() - t0_a
        except Exception as e:
            logger.debug(f"ASR alignment câu {sid} lỗi ({e}) — ước lượng")
            return (
                sid,
                key,
                float(seg["start"]),
                None,
                "error",
                str(e),
                text,
                t_asr,
                0.0,
                t_acoustic,
            )

        t0_m = time.perf_counter()
        mapped = _map_words(text_words, asr, float(seg["start"]), dur)
        t_map = time.perf_counter() - t0_m

        if mapped is not None and not validate_alignment(
            mapped, text_words, float(seg["start"]), dur
        ):
            logger.debug(f"Mốc timing câu {sid} không vượt qua validator — fallback")
            mapped = None

        if mapped is None:
            n_asr = len(asr) if asr is not None else 0
            return (
                sid,
                key,
                float(seg["start"]),
                None,
                "sparse",
                f"{n_asr}/{len(text_words)} từ",
                text,
                t_asr,
                t_map,
                t_acoustic,
            )

        return (
            sid,
            key,
            float(seg["start"]),
            mapped,
            "ok",
            len(mapped),
            text,
            t_asr,
            t_map,
            t_acoustic,
        )

    start_time = time.perf_counter()
    last_log_time = start_time
    done_cnt = 0
    ok_cnt = 0
    est_cnt = 0
    done = []

    # Tần suất log chi tiết:
    if total <= 20:
        log_step = 2
    elif total <= 100:
        log_step = 10
    elif total <= 300:
        log_step = 20
    else:
        log_step = 25

    new_cache_entries: dict = {}
    pending_flush_entries: dict = {}

    def _flush_cache_incremental():
        nonlocal pending_flush_entries
        if not pending_flush_entries:
            return
        to_save = dict(pending_flush_entries)
        pending_flush_entries.clear()
        if use_upc:
            try:
                from autodub.pipeline_cache import get_align_cache

                get_align_cache().store_batch(list(to_save.items()))
            except Exception as ex:
                logger.debug(f"AlignGlobalCache incremental store error: {ex}")
        if cache_path:
            t0_w = time.perf_counter()
            try:
                with _CACHE_LOCK:
                    disk_cache = {}
                    if os.path.exists(cache_path):
                        try:
                            with open(cache_path, encoding="utf-8") as f:
                                disk_cache = json.load(f)
                        except Exception:
                            disk_cache = {}
                    merged_cache = {**disk_cache, **cache, **new_cache_entries}
                    save_json_atomic(merged_cache, cache_path)
            except OSError:
                logger.debug("Bỏ qua lỗi OSError trong align.py", exc_info=True)
            stats.cache_write_time += time.perf_counter() - t0_w

    actual_workers = min(n_workers, max(1, total))
    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
        futures = {pool.submit(_one, item): item for item in todo}
        for fut in as_completed(futures):
            res = fut.result()
            done.append(res)
            done_cnt += 1
            sid, key, base, mapped, status, detail, text, t_asr, t_map, t_acoustic = res
            stats.asr_time += t_asr
            stats.mapping_time += t_map
            stats.acoustic_time += t_acoustic
            if mapped is not None:
                ok_cnt += 1
                out[sid] = mapped
                entry = [[w, round(t0 - base, 3), round(t1 - base, 3)] for w, t0, t1 in mapped]
                new_cache_entries[key] = entry
                pending_flush_entries[key] = entry
            else:
                est_cnt += 1

            now = time.perf_counter()
            elapsed = now - start_time
            is_milestone = (
                (done_cnt == 1)
                or (done_cnt % log_step == 0)
                or (done_cnt == total)
                or (now - last_log_time >= 3.0)
            )

            # Làm tới đâu cache tới đó: flush định kỳ vào Global Cache và đĩa
            if len(pending_flush_entries) >= 20 or (is_milestone and pending_flush_entries):
                _flush_cache_incremental()

            if is_milestone:
                last_log_time = now
                pct = (done_cnt / total) * 100.0
                speed = done_cnt / elapsed if elapsed > 0 else 0.0
                eta = (total - done_cnt) / speed if speed > 0 else 0.0
                eta_str = f"{eta:.0f}s" if eta < 60 else f"{int(eta // 60)}m{int(eta % 60):02d}s"
                preview = text[:32] + ("..." if len(text) > 32 else "")
                tag = (
                    f"OK ({detail} từ)"
                    if status == "ok"
                    else (
                        f"Acoustic ({detail} từ)"
                        if status == "acoustic"
                        else f"ước lượng ({detail})"
                    )
                )

                logger.info(
                    f"Canh nhịp: {done_cnt}/{total} câu ({pct:.1f}%) | "
                    f"Khớp: {ok_cnt} | Ước lượng: {est_cnt} | "
                    f"Tốc độ: {speed:.1f} câu/s (còn ~{eta_str}) | "
                    f'Câu {sid}: "{preview}" → {tag}'
                )
                if progress_cb:
                    try:
                        progress_cb(
                            done_cnt / total,
                            f"Canh nhịp phụ đề: {done_cnt}/{total} ({pct:.0f}%)",
                        )
                    except Exception:
                        logger.debug("Bỏ qua lỗi Exception trong align.py", exc_info=True)

    # Flush nốt các câu còn lại trong buffer
    _flush_cache_incremental()

    # Giữ model trong Singleton cache cho các lần xuất video / preview tiếp theo (0ms cold start)

    elapsed_total = time.perf_counter() - start_time
    speed_total = total / elapsed_total if elapsed_total > 0 else 0.0
    pct_ok = (ok_cnt / total) * 100.0 if total > 0 else 0.0
    logger.info(
        f"Canh phụ đề xong: {ok_cnt}/{total} câu khớp chính xác ({pct_ok:.1f}%)"
        + (f", {est_cnt} câu chia đều theo thời lượng" if est_cnt else "")
        + f" trong {elapsed_total:.1f}s (trung bình {speed_total:.1f} câu/s)"
    )
    if progress_cb:
        try:
            progress_cb(1.0, f"Canh nhịp xong ({ok_cnt}/{total} câu chuẩn)")
        except Exception:
            logger.debug("Bỏ qua lỗi Exception trong align.py", exc_info=True)

    stats.total_time = time.perf_counter() - t0_total
    stats.ok_count = ok_cnt + n_cached
    stats.est_count = est_cnt
    stats.segments_per_sec = (
        stats.total_segments / stats.total_time if stats.total_time > 0 else 0.0
    )
    return out
