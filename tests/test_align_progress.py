import os
import wave
import struct
import math
import logging
from unittest.mock import MagicMock, patch

import pytest
from autodub.speech.align import align_segments, _MIN_CLIP_S


def _write_tone(path, dur, rate=24000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        w.writeframes(struct.pack(
            f"<{n}h",
            *[int(8000 * math.sin(2 * math.pi * 440 * i / rate))
              for i in range(n)]))


def test_align_segments_detailed_progress_and_callback(tmp_path, caplog):
    """Bảo đảm align_segments đếm và log chi tiết tiến độ (số câu, %, tốc độ, ETA)
    và kích hoạt progress_cb đúng chuẩn.
    """
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()

    # Tạo 5 file wav giả lập
    segments = []
    for i in range(1, 6):
        wav_path = str(seg_dir / f"seg_{i:05d}.wav")
        _write_tone(wav_path, 1.5)
        segments.append({
            "id": i,
            "start": float((i - 1) * 2.0),
            "end": float((i - 1) * 2.0 + 1.5),
            "text_vi": f"đây là câu số {i} rất chi tiết"
        })

    mock_model = MagicMock()
    # Mock _asr_words trả về danh sách từ hợp lệ
    def mock_asr(model, wav):
        return [
            ("đây", 0.1, 0.3),
            ("là", 0.3, 0.5),
            ("câu", 0.5, 0.7),
            ("số", 0.7, 0.9),
            ("x", 0.9, 1.1),
            ("rất", 1.1, 1.3),
            ("chi", 1.3, 1.4),
            ("tiết", 1.4, 1.5)
        ]

    progress_events = []
    def on_progress(ratio, msg):
        progress_events.append((ratio, msg))

    caplog.set_level(logging.INFO, logger="autodub.align")

    with patch("autodub.speech.align._load_align_model", return_value=(mock_model, "cpu", 2)), \
         patch("autodub.speech.align._asr_words", side_effect=mock_asr):
        out = align_segments(
            segments,
            str(seg_dir),
            "text_vi",
            cache_path=str(tmp_path / "align_cache.json"),
            progress_cb=on_progress
        )

    # 1. Kiểm tra kết quả alignment đầy đủ cả 5 câu
    assert len(out) == 5
    for i in range(1, 6):
        assert i in out
        assert len(out[i]) > 0

    # 2. Kiểm tra log có đếm chi tiết tiến độ
    logs = [rec.message for rec in caplog.records if rec.name == "autodub.align"]
    log_text = "\n".join(logs)

    # Phải có log khởi động
    assert "Đang canh phụ đề nhảy đúng nhịp giọng đọc (5 câu)" in log_text
    assert "Đã nạp Whisper base (CPU, 2 luồng). Bắt đầu canh nhịp chi tiết 5 câu:" in log_text

    # Phải có log từng mốc câu và phần trăm
    assert "Canh nhịp:" in log_text
    assert "5/5 câu (100.0%)" in log_text
    assert "Khớp:" in log_text
    assert "câu/s" in log_text

    # Phải có log tổng kết hoàn tất
    assert "Canh phụ đề xong: 5/5 câu khớp chính xác" in log_text

    # 3. Kiểm tra progress_cb được gọi
    assert len(progress_events) >= 2
    assert progress_events[0][0] == 0.0  # Khởi đầu
    assert progress_events[-1][0] == 1.0  # Kết thúc 100%


def test_align_segments_sparse_fallback_logged(tmp_path, caplog):
    """Kiểm tra khi ASR nghe được quá ít từ so với văn bản, hệ thống ghi nhận ước lượng rõ ràng."""
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    wav_path = str(seg_dir / "seg_00001.wav")
    _write_tone(wav_path, 2.0)
    segments = [{
        "id": 1,
        "start": 0.0,
        "end": 2.0,
        "text_vi": "câu này có rất nhiều chữ nhưng ASR chỉ nghe được một chữ"
    }]

    mock_model = MagicMock()
    # ASR chỉ nghe được 1 từ trong khi câu có 12 từ (sparse)
    mock_asr = lambda model, wav: [("ừ", 0.1, 0.3)]

    caplog.set_level(logging.INFO, logger="autodub.align")

    with patch("autodub.speech.align._load_align_model", return_value=(mock_model, "cpu", 1)), \
         patch("autodub.speech.align._asr_words", side_effect=mock_asr):
        out = align_segments(segments, str(seg_dir), "text_vi")

    logs = [rec.message for rec in caplog.records if rec.name == "autodub.align"]
    log_text = "\n".join(logs)

    assert "ước lượng" in log_text
    assert "0/1 câu khớp chính xác" in log_text
    assert "1 câu chia đều theo thời lượng" in log_text
