import os
import time
import wave
import struct
import math
import logging
from unittest.mock import MagicMock, patch

import pytest
from autodub.config import Settings
from autodub.utils import ProgressTracker


def _create_dummy_wav(path, duration_s=1.0, rate=24000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n_frames = int(duration_s * rate)
        w.writeframes(struct.pack(f"<{n_frames}h", *[0] * n_frames))


def test_tts_progress_tracking(tmp_path, caplog):
    """Kiểm tra khâu TTS có live progress tracking, số câu, ETA và summary."""
    from autodub.pipeline import DubPipeline
    from autodub.progress import ProgressReporter
    from autodub.languages import get_target

    seg_dir = str(tmp_path / "segs")
    os.makedirs(seg_dir, exist_ok=True)

    segments = [
        {"id": 1, "text_vi": "Câu thứ nhất rất hay"},
        {"id": 2, "text_vi": "Câu thứ hai cũng thế"},
        {"id": 3, "text_vi": "Câu thứ ba kết thúc"},
    ]

    settings = Settings()
    pipeline = DubPipeline(settings)
    pipeline._reporter = ProgressReporter()

    mock_synth = MagicMock()
    mock_synth.synthesize.return_value = MagicMock(to_dict=lambda: {"actual_duration": 1.5, "speed_adjusted": False, "rate_applied": "normal"})
    mock_synth.recommended_threads = 2

    caplog.set_level(logging.INFO, logger="autodub.pipeline")

    target = get_target("vi")
    results = pipeline._synthesize_segments(
        target=target,
        voice="male",
        segments=segments,
        seg_dir=seg_dir,
        synth=mock_synth
    )

    assert len(results) == 3
    log_text = "\n".join([rec.message for rec in caplog.records if rec.name == "autodub.pipeline"])
    assert "Tạo giọng đọc (TTS):" in log_text
    assert "3/3 câu (100.0%)" in log_text
    assert "Tạo giọng đọc (TTS) hoàn tất: 3 câu" in log_text


def test_postprocess_voice_clips_progress(tmp_path, caplog):
    """Kiểm tra khâu Hậu kỳ âm thanh có ProgressTracker hoạt động chính xác."""
    from autodub.media.audio import postprocess_voice_clips

    src_dir = str(tmp_path / "src")
    dst_dir = str(tmp_path / "dst")
    os.makedirs(src_dir, exist_ok=True)

    segments = []
    for i in range(1, 4):
        wav_path = os.path.join(src_dir, f"seg_{i:05d}.wav")
        _create_dummy_wav(wav_path, 1.0)
        segments.append({"id": i})

    caplog.set_level(logging.INFO, logger="autodub.audio")

    with patch("autodub.media.audio.postprocess_voice_clip"):
        postprocess_voice_clips(segments, src_dir, dst_dir, target_lufs=-16.0, max_workers=2)

    log_text = "\n".join([rec.message for rec in caplog.records if rec.name == "autodub.audio"])
    assert "Hậu kỳ âm thanh:" in log_text
    assert "3/3 câu (100.0%)" in log_text
    assert "Hậu kỳ âm thanh hoàn tất: 3 câu" in log_text


def test_soft_timing_atempo_progress(tmp_path, caplog):
    """Kiểm tra khâu Khớp tốc độ (Atempo) có live ProgressTracker khi cần render."""
    from autodub.media.timing import apply_soft_timing

    src_dir = str(tmp_path / "src")
    dst_dir = str(tmp_path / "dst")
    os.makedirs(src_dir, exist_ok=True)

    segments = []
    for i in range(1, 4):
        wav_path = os.path.join(src_dir, f"seg_{i:05d}.wav")
        # File âm thanh 2.0 giây nhưng slot chỉ 1.0 giây -> buộc phải atempo
        _create_dummy_wav(wav_path, 2.0)
        segments.append({"id": i, "start": float(i * 1.5), "end": float(i * 1.5 + 1.0), "duration": 1.0})

    caplog.set_level(logging.INFO, logger="autodub.timing")

    with patch("autodub.media.voice_stretch.apply_formant_preserved_stretch"):
        apply_soft_timing(segments, src_dir, dst_dir, Settings(), max_workers=2)

    log_text = "\n".join([rec.message for rec in caplog.records if rec.name == "autodub.timing"])
    assert "Khớp tốc độ giọng đọc (Atempo):" in log_text
    assert "3/3 câu (100.0%)" in log_text
    assert "Khớp tốc độ giọng đọc (Atempo) hoàn tất: 3 câu" in log_text


def test_whisper_inprocess_progress(tmp_path, caplog):
    """Kiểm tra khâu Whisper ASR in-process có live ProgressTracker."""
    from autodub.speech.transcriber import _transcribe_whisper

    wav_path = str(tmp_path / "test.wav")
    _create_dummy_wav(wav_path, 5.0)

    mock_model = MagicMock()
    mock_seg1 = MagicMock(text="Chào bạn hôm nay thế nào", start=0.0, end=2.5, words=None)
    mock_seg2 = MagicMock(text="Tôi rất vui được gặp bạn", start=2.5, end=5.0, words=None)
    mock_info = MagicMock(duration=5.0, language="vi", language_probability=0.98)
    mock_model.transcribe.return_value = ([mock_seg1, mock_seg2], mock_info)

    caplog.set_level(logging.INFO, logger="autodub.transcriber")

    with patch("autodub.speech.transcriber._load_whisper_model", return_value=(mock_model, "cpu")):
        segs = _transcribe_whisper(wav_path, "vi", Settings(), whisper_cache=None)

    assert len(segs) == 2
    log_text = "\n".join([rec.message for rec in caplog.records if rec.name == "autodub.transcriber"])
    assert "Nhận dạng giọng nói (ASR):" in log_text
    assert "5.0/5.0 s (100.0%)" in log_text
    assert "Nhận dạng giọng nói (ASR) hoàn tất: 5.0 s" in log_text


def test_merge_video_ffmpeg_progress(tmp_path, caplog):
    """Kiểm tra merge_video đọc stream stdout ffmpeg để track tiến độ thời gian thực."""
    from autodub.media.video import merge_video

    video_path = str(tmp_path / "input.mp4")
    audio_path = str(tmp_path / "audio.wav")
    output_path = str(tmp_path / "output.mp4")

    # Tạo dummy files
    with open(video_path, "wb") as f:
        f.write(b"fake video")
    _create_dummy_wav(audio_path, 10.0)

    progress_events = []
    def on_progress(ratio, msg):
        progress_events.append((ratio, msg))

    caplog.set_level(logging.INFO, logger="autodub.video_merger")

    mock_proc = MagicMock()
    mock_proc.stdout = [
        "out_time_us=5000000\n",
        "out_time_us=10000000\n",
    ]
    mock_proc.stderr = []
    mock_proc.returncode = 0
    mock_proc.wait.return_value = 0

    with patch("autodub.media.video.probe_duration_s", return_value=10.0), \
         patch("subprocess.Popen", return_value=mock_proc):
        merge_video(video_path, audio_path, output_path, progress_cb=on_progress, randomize_metadata=False)

    log_text = "\n".join([rec.message for rec in caplog.records if rec.name == "autodub.video_merger"])
    assert "Xuất video & ghép phụ đề:" in log_text
    assert "10.0/10.0 s (100.0%)" in log_text
    assert "Xuất video & ghép phụ đề hoàn tất: 10.0 s" in log_text
    assert len(progress_events) >= 1
