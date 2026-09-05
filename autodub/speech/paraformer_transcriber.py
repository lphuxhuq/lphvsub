"""Paraformer ASR driver — runs the worker in .venv-asr as a one-shot subprocess.

Unlike the TTS engines (hundreds of small requests → persistent worker pool),
ASR is one request per pipeline run, so the worker starts, streams one JSON
line per recognized segment (progress shows up in the GUI log live) and exits.

The worker script (:mod:`autodub.speech.asr_paraformer_worker`) is standalone
and executes with the .venv-asr interpreter — sherpa-onnx never has to be
installed in (or bundled with) the main app.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from collections import deque

from autodub.config import Settings
from autodub.utils import bundled_file, setup_logging

logger = setup_logging("autodub.paraformer")

_WORKER_SCRIPT = bundled_file("autodub", "speech", "asr_paraformer_worker.py")


class ParaformerCache:
    """Quản lý một tiến trình asr_paraformer_worker.py --serve sống suốt phiên làm việc.

    Tương tự như DemucsCache hay SynthCache: model sherpa-onnx được nạp trước
    trong RAM. Khi cần nhận dạng, chỉ cần gửi path audio qua stdin và đọc kết quả,
    tiết kiệm thời gian khởi động tiến trình con và nạp model lặp lại.
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._failed = False
        self._lock = threading.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=20)

    def _ensure(self, settings: Settings) -> bool:
        """Khởi động worker nếu chưa chạy; False khi không dùng được."""
        if self._failed:
            return False
        if self._proc is not None and self._proc.poll() is None:
            return True
        if not settings.paraformer_configured():
            self._failed = True
            return False

        python = settings.asr_venv_python_path()
        model_dir = settings.paraformer_model_dir_path()
        cmd = [
            python,
            _WORKER_SCRIPT,
            "--serve",
            "--model-dir", model_dir,
            "--num-threads", str(settings.asr_num_threads),
            "--vad-pad", str(settings.asr_vad_pad_s),
        ]
        if not getattr(settings, "asr_gap_rescan", True):
            cmd.append("--no-gap-rescan")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
            )

            def _drain():
                p = self._proc
                if not p or not p.stderr:
                    return
                try:
                    for line in p.stderr:
                        line = line.rstrip()
                        if line:
                            self._stderr_tail.append(line)
                except (ValueError, OSError):
                    pass

            threading.Thread(target=_drain, daemon=True).start()

            ready_line = self._proc.stdout.readline().strip()
            ready = json.loads(ready_line) if ready_line else {}
        except Exception as e:
            logger.warning(f"Paraformer cache không khởi động được ({e}) — fallback one-shot")
            self._shutdown()
            self._failed = True
            return False

        if not ready.get("ready"):
            logger.warning(f"Paraformer cache từ chối chạy ({ready.get('error')})")
            self._shutdown()
            self._failed = True
            return False

        logger.info("Paraformer cache sẵn sàng (worker thường trú) — nhận diện tiếng Trung tức thì")
        return True

    def transcribe(self, audio_path: str, settings: Settings,
                   meta: dict | None = None) -> list[dict] | None:
        with self._lock:
            if not self._ensure(settings):
                return None
            req = {
                "audio": os.path.abspath(audio_path),
                "vad_pad": settings.asr_vad_pad_s,
                "no_gap_rescan": not getattr(settings, "asr_gap_rescan", True),
                "gap_min": 1.0,
            }
            try:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                logger.warning(f"Gửi việc tới Paraformer cache lỗi ({e}) — fallback")
                self._shutdown()
                self._failed = True
                return None

            from autodub.media.audio import wav_duration_s
            from autodub.utils import format_eta
            import time

            total_audio_dur = wav_duration_s(audio_path) or 0.0
            t0 = time.time()
            segments: list[dict] = []
            empty_chunks: list[dict] | None = (
                meta.setdefault("empty_chunks", []) if meta is not None else None)
            done = False

            while True:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("error"):
                    logger.warning(f"Paraformer worker lỗi: {msg['error']}")
                    return None
                if msg.get("seg"):
                    start = float(msg["start"])
                    end = float(msg["end"])
                    seg = {
                        "id": len(segments) + 1,
                        "text": str(msg["text"]).strip(),
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "duration": round(end - start, 3),
                    }
                    if msg.get("rescan"):
                        seg["rescan"] = True
                    segments.append(seg)
                    elapsed = time.time() - t0
                    eta_text = ""
                    if total_audio_dur > 0 and end > 0:
                        pct = min(99, int((end / total_audio_dur) * 100))
                        rate = end / elapsed if elapsed > 0 else 1.0
                        rem_s = max(0.0, total_audio_dur - end) / rate
                        eta_text = f" [{pct}% | ⏱ Đã chạy: {format_eta(elapsed)} | ETA: ~{format_eta(rem_s)}]"
                    logger.info(f"Segment {len(segments)}: "
                                f"[{start:.1f}s-{end:.1f}s]{eta_text} {msg['text'][:40]}...")
                elif msg.get("empty"):
                    if empty_chunks is not None:
                        empty_chunks.append({
                            "start": round(float(msg["start"]), 3),
                            "end": round(float(msg["end"]), 3),
                        })
                    logger.warning(
                        f"Paraformer: đoạn [{float(msg['start']):.1f}s-"
                        f"{float(msg['end']):.1f}s] có tiếng nhưng không nhận "
                        "dạng được chữ")
                elif msg.get("done"):
                    done = True
                    break

            if not done or not segments:
                logger.warning("Paraformer cache không trả kết quả hoàn chỉnh — fallback")
                return None

            segments.sort(key=lambda s: s["start"])
            for i, seg in enumerate(segments, start=1):
                seg["id"] = i

            return segments

    def _shutdown(self) -> None:
        p, self._proc = self._proc, None
        if p is None:
            return
        try:
            if p.poll() is None:
                if p.stdin:
                    p.stdin.close()
                p.wait(timeout=5)
        except Exception:
            p.kill()
        finally:
            for s in (p.stdin, p.stdout, p.stderr):
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass

    def close(self) -> None:
        with self._lock:
            self._shutdown()


def transcribe_paraformer(audio_path: str, settings: Settings,
                          meta: dict | None = None,
                          paraformer_cache: ParaformerCache | None = None) -> list[dict]:
    """Run the Paraformer worker on ``audio_path`` (16 kHz mono WAV).

    Returns Whisper-shaped segments ``[{id, text, start, end, duration}]``.
    Raises :class:`RuntimeError` on any failure — the caller falls back to
    Whisper.
    """
    if paraformer_cache is not None:
        cached_result = paraformer_cache.transcribe(audio_path, settings, meta=meta)
        if cached_result is not None:
            logger.info("Paraformer nhận dạng thành công (dùng lại worker cache)")
            return cached_result
        logger.warning("Paraformer cache thất bại — thử đường một phát thường")

    cmd = [
        settings.asr_venv_python_path(),
        _WORKER_SCRIPT,
        "--audio", audio_path,
        "--model-dir", settings.paraformer_model_dir_path(),
        "--num-threads", str(settings.asr_num_threads),
        "--vad-pad", str(settings.asr_vad_pad_s),
    ]
    if not getattr(settings, "asr_gap_rescan", True):
        cmd.append("--no-gap-rescan")
    logger.info("Nhận dạng tiếng Trung bằng Paraformer (sherpa-onnx, CPU)...")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )

    stderr_tail: deque[str] = deque(maxlen=20)

    def _drain() -> None:
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    stderr_tail.append(line)
        except (ValueError, OSError):
            pass

    threading.Thread(target=_drain, daemon=True).start()

    from autodub.media.audio import wav_duration_s
    from autodub.utils import format_eta
    import time

    total_audio_dur = wav_duration_s(audio_path) or 0.0
    t0 = time.time()
    segments: list[dict] = []
    empty_chunks: list[dict] | None = (
        meta.setdefault("empty_chunks", []) if meta is not None else None)
    done = False
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("error"):
                raise RuntimeError(f"Paraformer worker: {msg['error']}")
            if msg.get("seg"):
                start = float(msg["start"])
                end = float(msg["end"])
                seg = {
                    "id": len(segments) + 1,
                    "text": str(msg["text"]).strip(),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(end - start, 3),
                }
                if msg.get("rescan"):
                    seg["rescan"] = True   # bắt ở pass 3 (khoảng trống VAD)
                segments.append(seg)
                elapsed = time.time() - t0
                eta_text = ""
                if total_audio_dur > 0 and end > 0:
                    pct = min(99, int((end / total_audio_dur) * 100))
                    rate = end / elapsed if elapsed > 0 else 1.0
                    rem_s = max(0.0, total_audio_dur - end) / rate
                    eta_text = f" [{pct}% | ⏱ Đã chạy: {format_eta(elapsed)} | ETA: ~{format_eta(rem_s)}]"
                logger.info(f"Segment {len(segments)}: "
                            f"[{start:.1f}s-{end:.1f}s]{eta_text} {msg['text'][:40]}...")
            elif msg.get("empty"):
                if empty_chunks is not None:
                    empty_chunks.append({
                        "start": round(float(msg["start"]), 3),
                        "end": round(float(msg["end"]), 3),
                    })
                logger.warning(
                    f"Paraformer: đoạn [{float(msg['start']):.1f}s-"
                    f"{float(msg['end']):.1f}s] có tiếng nhưng không nhận "
                    "dạng được chữ")
            elif msg.get("done"):
                done = True
        # Thời lượng phụ thuộc độ dài video — chờ tiến trình kết thúc hẳn
        # (stdout đã EOF nên wait không thể treo vô hạn vì pipe đầy).
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
        for s in (proc.stdout, proc.stderr):
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    # Gap-rescan (pass 3 của worker) phát segment SAU các chunk thường nên
    # thứ tự arrival lệch thứ tự thời gian — chốt theo mốc bắt đầu, đánh lại
    # id tăng dần (mọi consumer dưới stream đều giả định thứ tự thời gian).
    segments.sort(key=lambda s: s["start"])
    for i, seg in enumerate(segments, start=1):
        seg["id"] = i

    tail = "\n".join(stderr_tail)
    if not done:
        raise RuntimeError(
            f"Paraformer worker thoát bất thường (exit {proc.returncode})"
            + (f"\n{tail}" if tail else ""))
    if not segments:
        raise RuntimeError("Paraformer không nhận dạng được câu nào"
                           + (f"\n{tail}" if tail else ""))
    if empty_chunks:
        logger.warning(f"Paraformer bỏ lỡ {len(empty_chunks)} đoạn có tiếng "
                       "không decode được — xem empty_chunks trong ASR meta")
    return segments
