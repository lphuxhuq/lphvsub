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
import subprocess
import threading
from collections import deque

from autodub.config import Settings
from autodub.utils import bundled_file, setup_logging

logger = setup_logging("autodub.paraformer")

_WORKER_SCRIPT = bundled_file("autodub", "speech", "asr_paraformer_worker.py")


def transcribe_paraformer(audio_path: str, settings: Settings,
                          meta: dict | None = None) -> list[dict]:
    """Run the Paraformer worker on ``audio_path`` (16 kHz mono WAV).

    Returns Whisper-shaped segments ``[{id, text, start, end, duration}]``.
    Raises :class:`RuntimeError` on any failure — the caller falls back to
    Whisper.

    ``meta`` (optional, mutable dict) nhận thêm ``"empty_chunks"`` — các
    khoảng VAD có tiếng nhưng decode rỗng ({"start", "end"}, giây) để bước
    suspect-detection downstream xử lý. Nhánh Whisper không ghi key này.
    """
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
