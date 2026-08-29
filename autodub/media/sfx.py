"""Tự động sinh hiệu ứng âm thanh chuyển cảnh (Procedural SFX Generator).

Module này tạo trực tiếp các hiệu ứng âm thanh chuyển cảnh điện ảnh (Whoosh, Pop,
Swish, Cinematic Boom) bằng thuật toán sóng âm PCM chất lượng cao (NumPy) mà không
cần tải tệp nhị phân bên ngoài, hoạt động 100% offline.
"""
from __future__ import annotations

import os
import wave
import numpy as np


def generate_sfx(
    preset: str = "whoosh",
    sample_rate: int = 44100,
    duration_s: float | None = None,
    gain_db: float = -14.0,
) -> np.ndarray:
    """Sinh mảng sóng âm PCM int16 cho hiệu ứng chuyển cảnh.

    Các preset:
    - 'whoosh': Tiếng vút gió êm dịu (chuyển cảnh điện ảnh mượt mà).
    - 'pop': Tiếng pop nhẹ nhàng, hiện đại (phong cách Shorts/TikTok).
    - 'swish': Tiếng lướt nhanh gọn gàng.
    - 'cinematic': Tiếng trầm ấm tạo điểm nhấn kịch tính (Sub-bass drop).
    """
    preset_key = (preset or "whoosh").strip().lower()

    if preset_key == "pop":
        dur = duration_s if duration_s is not None else 0.09
        t = np.linspace(0, dur, int(dur * sample_rate), endpoint=False)
        # Tần số quét nhanh từ 650Hz xuống 130Hz
        freq = 650.0 * np.exp(-t * 22.0) + 130.0
        phase = 2.0 * np.pi * np.cumsum(freq) / sample_rate
        # Envelope decay mềm
        env = np.exp(-t * 35.0)
        signal = np.sin(phase) * env

    elif preset_key == "swish":
        dur = duration_s if duration_s is not None else 0.22
        n_samples = int(dur * sample_rate)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        # Noise lọc dải tần với envelope hình chuông đối xứng
        np.random.seed(42)
        noise = np.random.normal(0, 1, n_samples)
        # Tần số trung tâm quét từ 300Hz lên 1800Hz rồi hạ xuống 400Hz
        center_f = 300.0 + 1500.0 * np.sin(np.pi * (t / dur))
        # Điều chế AM
        mod = np.sin(2.0 * np.pi * center_f * t)
        env = np.sin(np.pi * (t / dur)) ** 2.5
        signal = noise * mod * env

    elif preset_key == "cinematic":
        dur = duration_s if duration_s is not None else 0.45
        t = np.linspace(0, dur, int(dur * sample_rate), endpoint=False)
        # Tần số quét từ 95Hz xuống 45Hz
        freq = 95.0 * np.exp(-t * 4.0) + 45.0
        phase = 2.0 * np.pi * np.cumsum(freq) / sample_rate
        # Envelope đánh mạnh đầu câu và ngân dài
        env = np.exp(-t * 5.5)
        # Thêm hài âm bậc 2 nhẹ
        signal = (np.sin(phase) + 0.3 * np.sin(phase * 2.0)) * env

    else:  # 'whoosh' (default)
        dur = duration_s if duration_s is not None else 0.32
        n_samples = int(dur * sample_rate)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        np.random.seed(123)
        noise = np.random.normal(0, 1, n_samples)
        # Envelope quét mượt mà: êm đầu, cao trào ở giữa, tắt dần ở đuôi
        env = np.sin(np.pi * (t / dur)) ** 3.0
        # Lowpass filter mô phỏng luồng gió lướt
        sweep_freq = 200.0 + 1200.0 * (np.sin(np.pi * (t / dur)) ** 1.5)
        carrier = np.sin(2.0 * np.pi * np.cumsum(sweep_freq) / sample_rate)
        signal = (0.7 * noise + 0.3 * carrier) * env

    # Chuẩn hóa biên độ cực đại về [-1.0, 1.0]
    peak = np.max(np.abs(signal))
    if peak > 1e-6:
        signal = signal / peak

    # Áp dụng gain dB
    linear_gain = 10.0 ** (gain_db / 20.0)
    scaled = np.clip(signal * linear_gain, -1.0, 1.0)

    # Chuyển sang định dạng int16
    return (scaled * 32767).astype(np.int16)


def write_sfx_wav(
    output_path: str,
    preset: str = "whoosh",
    sample_rate: int = 44100,
    duration_s: float | None = None,
    gain_db: float = -14.0,
) -> str:
    """Ghi âm thanh SFX ra tệp .wav."""
    arr = generate_sfx(
        preset=preset,
        sample_rate=sample_rate,
        duration_s=duration_s,
        gain_db=gain_db,
    )
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with wave.open(output_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(arr.tobytes())
    return output_path
