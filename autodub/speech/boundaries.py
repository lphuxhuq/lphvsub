"""Refine biên VAD thô thành biên speech thật bằng RMS energy (voice-sync C1).

Paraformer/Whisper đưa ra segment boundary theo VAD — coarse: onset speech
thật thường TRƯỚC biên VAD ~100-400ms (VAD cần vài window để vượt ngưỡng).
Module này thu hẹp biên về chỗ có năng lượng thật:

- Frame RMS (25 ms cửa, 10 ms hop) trên từng window ``[vad_start, vad_end]``.
- Ngưỡng ``peak_rms × ENERGY_RATIO`` — adaptive theo đỉnh của chính window.
- CHỈ THU HẸP (speech_start ≥ vad_start, speech_end ≤ vad_end): side nào
  thu hẹp dưới ``REFINE_MIN_DELTA_S`` coi như "đã tốt", giữ nguyên.
- Margin an toàn hai đầu để không cắt mất attack/breath.
- Guard: window gần im (peak < ABS_FLOOR) hoặc thu hẹp còn quá ngắn
  (speech_duration < max(0.2s, 25% vad_duration)) → giữ nguyên biên VAD.

Output: bản copy của segments với thêm ``vad_start/vad_end`` (coarse) và
``speech_start/speech_end/speech_duration`` (refined). Field
``start/end/duration`` KHÔNG bị đụng — mọi consumer cũ giữ nguyên ý nghĩa.
"""
from __future__ import annotations

import wave

import numpy as np

from autodub.utils import setup_logging

logger = setup_logging("autodub.boundaries")

# --- Hằng số refine — named để chỉnh không đụng logic ---------------------
FRAME_S = 0.025            # cửa sổ RMS
HOP_S = 0.010              # bước nhảy frame
ENERGY_RATIO = 0.12        # ngưỡng = peak × 0.12 (≈ -18 dB dưới đỉnh)
ABS_FLOOR = 0.004          # peak dưới đây coi như window im lặng
LEAD_MARGIN_S = 0.06       # giữ thêm trước speech đầu tiên
TAIL_MARGIN_S = 0.06       # giữ thêm sau speech cuối cùng
REFINE_MIN_DELTA_S = 0.08  # thu hẹp ít hơn thế này → biên "đã tốt"
MIN_SPEECH_S = 0.2         # speech_duration tối thiểu sau refine
MIN_SPEECH_RATIO = 0.25    # ... hoặc ≥ 25% vad_duration


def _load_mono16k(path: str) -> tuple[np.ndarray, int]:
    """Đọc WAV bất kỳ → float32 mono trong [-1, 1] (giữ rate gốc)."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        data = w.readframes(w.getnframes())
    if sampwidth != 2:
        raise ValueError(f"expected 16-bit PCM, got {sampwidth * 8}-bit")
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        arr = arr.reshape(-1, channels).mean(axis=1)
    return arr, rate


def _frame_rms(arr: np.ndarray, rate: int, t0: float, t1: float
               ) -> tuple[np.ndarray, np.ndarray] | None:
    """Frame RMS trên [t0, t1] giây. Trả (frame_start_times, rms) hoặc None
    khi window ngắn hơn một frame."""
    win = int(FRAME_S * rate)
    hop = int(HOP_S * rate)
    s = max(0, int(t0 * rate))
    e = min(len(arr), int(t1 * rate))
    if e - s < win:
        return None
    starts = np.arange(s, e - win + 1, hop)
    idx = starts[:, None] + np.arange(win)[None, :]
    rms = np.sqrt((arr[idx] ** 2).mean(axis=1))
    return starts / rate, rms


def refine_speech_boundaries(segments: list[dict], wav_path: str,
                             settings=None) -> list[dict]:
    """Thu hẹp biên mỗi segment về biên speech thật (không mutate input).

    ``wav_path``: WAV dùng cho ASR (16 kHz mono). Lỗi đọc file → warning +
    trả lại segments (copy) không có field mới — caller dùng biên VAD như cũ.
    """
    try:
        arr, rate = _load_mono16k(wav_path)
    except (OSError, EOFError, wave.Error, ValueError) as e:
        logger.warning(f"Boundary refine: không đọc được audio ({e}) — "
                       "giữ biên VAD")
        return [dict(s) for s in segments]

    out: list[dict] = []
    n_refined = 0
    for seg in segments:
        new = dict(seg)
        v0 = float(seg.get("start", 0.0) or 0.0)
        v1 = float(seg.get("end", v0) or v0)
        vad_dur = v1 - v0
        if vad_dur <= 0:
            out.append(new)
            continue

        framed = _frame_rms(arr, rate, v0, v1)
        if framed is not None:
            times, rms = framed
            peak = float(rms.max())
            if peak >= ABS_FLOOR:
                thresh = peak * ENERGY_RATIO
                above = np.nonzero(rms >= thresh)[0]
                if len(above):
                    s0 = max(v0, float(times[above[0]]) - LEAD_MARGIN_S)
                    e1 = min(v1, float(times[above[-1]]) + FRAME_S
                             + TAIL_MARGIN_S)
                    # Side nào "đã tốt" (delta nhỏ) → giữ biên VAD của side đó.
                    if s0 - v0 < REFINE_MIN_DELTA_S:
                        s0 = v0
                    if v1 - e1 < REFINE_MIN_DELTA_S:
                        e1 = v1
                    if e1 - s0 >= max(MIN_SPEECH_S,
                                      MIN_SPEECH_RATIO * vad_dur):
                        new["vad_start"] = round(v0, 3)
                        new["vad_end"] = round(v1, 3)
                        new["speech_start"] = round(s0, 3)
                        new["speech_end"] = round(e1, 3)
                        new["speech_duration"] = round(e1 - s0, 3)
                        n_refined += 1
        out.append(new)

    if n_refined:
        logger.info("Boundary refine: %d/%d câu thu hẹp biên về speech thật",
                    n_refined, len(segments))
    return out
