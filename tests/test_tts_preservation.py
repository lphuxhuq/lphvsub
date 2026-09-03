import os
import wave
import numpy as np
import pytest
from autodub.speech.tts_trimmer import compute_speech_extents, trim_tts_silence
from autodub.speech.tts.capcut_vi import sanitize_capcut_text
from autodub.text.vi_numbers import normalize_vi_text
from autodub.media.audio import lead_silence_s


def test_soft_consonant_preservation():
    """Kiểm tra âm xát / phụ âm có năng lượng thấp (chỉ bằng 3% peak) không bị VAD gọt mất."""
    rate = 16000
    # 0.25s im lặng + 0.10s phụ âm xát (biên độ nhỏ 0.03) + 0.40s nguyên âm (biên độ lớn 0.8) + 0.25s im lặng
    lead_silence = np.zeros(int(0.25 * rate), dtype=np.float32)
    soft_consonant = (np.random.normal(0, 0.03, int(0.10 * rate))).astype(np.float32)
    vowel_peak = (np.sin(2 * np.pi * 300 * np.linspace(0, 0.4, int(0.40 * rate))) * 0.8).astype(np.float32)
    tail_silence = np.zeros(int(0.25 * rate), dtype=np.float32)
    
    audio = np.concatenate([lead_silence, soft_consonant, vowel_peak, tail_silence])
    
    start_s, end_s = compute_speech_extents(audio, rate)
    # Phụ âm bắt đầu từ 0.25s, với margin 80ms (0.08s), start_s phải <= 0.25s để không bao giờ xén vào phụ âm
    assert start_s <= 0.25
    # Tổng thời gian speech (0.10 + 0.40 = 0.50s) kết thúc ở 0.75s, end_s phải >= 0.75s
    assert end_s >= 0.75


def test_lead_silence_s_safety_guard():
    """Kiểm tra lead_silence_s có đệm an toàn 180ms để không xén vào âm thanh thật."""
    rate = 16000
    # 0.3s im lặng + 0.5s tiếng nói
    samples = np.concatenate([
        np.zeros(int(0.3 * rate), dtype=np.float32),
        np.ones(int(0.5 * rate), dtype=np.float32) * 0.5
    ])
    trim_s = lead_silence_s(samples, rate)
    # 0.3s im lặng - 0.18s guard = 0.12s trim (giữ lại 0.18s trước tiếng nói)
    assert 0.10 <= trim_s <= 0.13
    assert trim_s < 0.30


def test_sanitize_capcut_text_vietnamese():
    """Kiểm tra sanitize_capcut_text giữ nguyên 100% chữ tiếng Việt và làm sạch ký tự độc hại."""
    raw = "«Xin chào» [Âm nhạc] Đạt top 1 & kiếm được 100k!"
    normalized = normalize_vi_text(raw)
    cleaned = sanitize_capcut_text(normalized)
    
    assert "Xin chào" in cleaned
    assert "Âm nhạc" not in cleaned
    assert "tốp một" in cleaned
    assert "và" in cleaned
    assert "một trăm nghìn" in cleaned
    assert "«" not in cleaned
    assert "»" not in cleaned
    assert "[" not in cleaned
    assert "]" not in cleaned
