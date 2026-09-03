"""TTS VAD silence trimmer — tự động cắt tỉa khoảng lặng thừa đầu/đuôi file TTS.

TTS thường sinh ra 100-300ms khoảng lặng hoặc tiếng lấy hơi ở đầu và cuối clip.
Module này tính toán RMS energy trên các frame 10ms để phát hiện chính xác
thời điểm bắt đầu và kết thúc phát âm thật, sau đó cắt bớt khoảng lặng thừa
(có giữ lại margin an toàn 80ms để bảo vệ các phụ âm đầu/đuôi có năng lượng thấp).
"""
from __future__ import annotations

import os
import wave
import numpy as np

from autodub.utils import ensure_dir, setup_logging

logger = setup_logging("autodub.tts_trimmer")

FRAME_S = 0.010          # Khung RMS 10ms
ENERGY_RATIO = 0.02      # Ngưỡng năng lượng = 2% peak RMS (bảo vệ phụ âm xát/vô thanh th, s, x, ph, kh)
ABS_FLOOR = 0.0015       # Ngưỡng sàn năng lượng tối thiểu (không nuốt tiếng thì thầm)
DEFAULT_MARGIN_S = 0.080 # Margin an toàn giữ lại hai đầu (80ms)


def compute_speech_extents(
    arr: np.ndarray,
    rate: int,
    *,
    threshold_ratio: float = ENERGY_RATIO,
    abs_floor: float = ABS_FLOOR,
    margin_s: float = DEFAULT_MARGIN_S,
) -> tuple[float, float]:
    """Tìm thời điểm bắt đầu và kết thúc speech thật trong mảng âm thanh float32."""
    if len(arr) == 0:
        return 0.0, 0.0

    frame_len = max(1, int(FRAME_S * rate))
    n_frames = len(arr) // frame_len
    if n_frames == 0:
        return 0.0, len(arr) / rate

    frames = arr[:n_frames * frame_len].reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))

    peak = float(np.max(rms)) if len(rms) > 0 else 0.0
    if peak < abs_floor:
        # Toàn bộ file quá nhỏ hoặc im lặng — giữ nguyên
        return 0.0, len(arr) / rate

    thresh = max(abs_floor, peak * threshold_ratio)
    active_indices = np.where(rms >= thresh)[0]
    if len(active_indices) == 0:
        return 0.0, len(arr) / rate

    first_frame = active_indices[0]
    last_frame = active_indices[-1]

    raw_start = first_frame * FRAME_S
    raw_end = (last_frame + 1) * FRAME_S

    total_dur = len(arr) / rate
    start_s = max(0.0, raw_start - margin_s)
    end_s = min(total_dur, raw_end + margin_s)

    if end_s <= start_s:
        return 0.0, total_dur
    return start_s, end_s


def trim_tts_silence(
    wav_path: str,
    out_path: str,
    *,
    min_silence_s: float = 0.06,
    margin_s: float = DEFAULT_MARGIN_S,
) -> tuple[str, float, float]:
    """Cắt tỉa khoảng lặng thừa đầu/đuôi của file WAV.

    Trả về (out_path, lead_trimmed_s, tail_trimmed_s).
    Nếu không cắt được hoặc cắt quá ít (< min_silence_s) thì giữ nguyên file gốc.
    """
    if not os.path.exists(wav_path):
        return wav_path, 0.0, 0.0

    try:
        with wave.open(wav_path, "rb") as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            rate = w.getframerate()
            n_frames = w.getnframes()
            data = w.readframes(n_frames)

        if sampwidth != 2 or n_frames == 0:
            return wav_path, 0.0, 0.0

        raw_int16 = np.frombuffer(data, dtype=np.int16)
        if channels > 1:
            raw_int16 = raw_int16.reshape(-1, channels)
            arr_float = raw_int16.mean(axis=1).astype(np.float32) / 32768.0
        else:
            arr_float = raw_int16.astype(np.float32) / 32768.0

        total_dur = n_frames / rate
        start_s, end_s = compute_speech_extents(arr_float, rate, margin_s=margin_s)

        lead_trim = start_s
        tail_trim = total_dur - end_s

        # Chỉ xuất file mới nếu cắt được lượng khoảng lặng đáng kể
        if lead_trim < min_silence_s and tail_trim < min_silence_s:
            return wav_path, 0.0, 0.0

        start_frame = int(start_s * rate)
        end_frame = int(end_s * rate)

        if channels > 1:
            trimmed_int16 = raw_int16[start_frame:end_frame, :]
        else:
            trimmed_int16 = raw_int16[start_frame:end_frame]

        ensure_dir(os.path.dirname(out_path))
        with wave.open(out_path, "wb") as out_w:
            out_w.setnchannels(channels)
            out_w.setsampwidth(sampwidth)
            out_w.setframerate(rate)
            out_w.writeframes(trimmed_int16.tobytes())

        logger.debug(f"Trimmed {os.path.basename(wav_path)}: -{lead_trim:.3f}s lead, -{tail_trim:.3f}s tail")
        return out_path, lead_trim, tail_trim
    except Exception as e:
        logger.warning(f"Không trim được khoảng lặng {wav_path}: {e}")
        return wav_path, 0.0, 0.0
