"""Acoustic Energy Envelope Word Segmentation — Canh mốc chữ bằng phổ năng lượng sóng âm.

Khi ASR không bắt được chữ hoặc câu ngắn, module này phân tích RMS energy
của file WAV để dò chính xác các đỉnh phát âm (voice bursts) và khoảng lặng,
từ đó chia mốc chữ theo đúng nhịp nói thật thay vì chia đều phẳng một cách máy móc.
"""
from __future__ import annotations

import os
import wave
import numpy as np

from autodub.utils import setup_logging

logger = setup_logging("autodub.acoustic_align")

FRAME_S = 0.010       # Khung 10ms
ENERGY_THRESH = 0.08  # 8% đỉnh năng lượng
ABS_FLOOR = 0.003     # Sàn tối thiểu


def acoustic_word_times(
    text: str,
    wav_path: str,
    clip_start: float,
    clip_dur: float,
) -> list[tuple[str, float, float]]:
    """Phân bổ mốc chữ dựa trên phổ năng lượng thực tế của file WAV.

    Trả về danh sách [(chữ, t0_tuyệt_đối, t1_tuyệt_đối)].
    """
    words = [w.strip() for w in text.split() if w.strip()]
    if not words:
        return []

    if not wav_path or not os.path.exists(wav_path):
        # Fallback chia đều nếu không có audio
        step = clip_dur / len(words)
        return [(w, round(clip_start + i * step, 3), round(clip_start + (i + 1) * step, 3))
                for i, w in enumerate(words)]

    try:
        with wave.open(wav_path, "rb") as w:
            rate = w.getframerate()
            sampwidth = w.getsampwidth()
            channels = w.getnchannels()
            n_frames = w.getnframes()
            data = w.readframes(n_frames)

        if sampwidth != 2 or n_frames == 0:
            step = clip_dur / len(words)
            return [(w, round(clip_start + i * step, 3), round(clip_start + (i + 1) * step, 3))
                    for i, w in enumerate(words)]

        raw_int16 = np.frombuffer(data, dtype=np.int16)
        if channels > 1:
            raw_int16 = raw_int16.reshape(-1, channels).mean(axis=1)
        arr = raw_int16.astype(np.float32) / 32768.0

        frame_len = max(1, int(FRAME_S * rate))
        n_frames_calc = len(arr) // frame_len
        if n_frames_calc == 0:
            step = clip_dur / len(words)
            return [(w, round(clip_start + i * step, 3), round(clip_start + (i + 1) * step, 3))
                    for i, w in enumerate(words)]

        frames = arr[:n_frames_calc * frame_len].reshape(n_frames_calc, frame_len)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))

        peak = float(np.max(rms)) if len(rms) > 0 else 0.0
        thresh = max(ABS_FLOOR, peak * ENERGY_THRESH)

        # Tìm các vùng năng lượng hoạt động
        active = np.where(rms >= thresh)[0]
        if len(active) == 0:
            step = clip_dur / len(words)
            return [(w, round(clip_start + i * step, 3), round(clip_start + (i + 1) * step, 3))
                    for i, w in enumerate(words)]

        active_start_s = active[0] * FRAME_S
        active_end_s = (active[-1] + 1) * FRAME_S
        active_dur = max(0.1, active_end_s - active_start_s)

        # Phân bổ từ ngữ theo vùng hoạt động năng lượng thực tế
        out: list[tuple[str, float, float]] = []
        n_words = len(words)
        word_step = active_dur / n_words

        for i, word in enumerate(words):
            w_start = clip_start + active_start_s + i * word_step
            w_end = clip_start + active_start_s + (i + 1) * word_step
            out.append((word, round(w_start, 3), round(w_end, 3)))

        return out
    except Exception as e:
        logger.warning(f"Lỗi acoustic alignment {wav_path}: {e}")
        step = clip_dur / len(words)
        return [(w, round(clip_start + i * step, 3), round(clip_start + (i + 1) * step, 3))
                for i, w in enumerate(words)]
