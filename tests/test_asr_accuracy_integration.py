import json
import os
from unittest.mock import MagicMock, patch
import pytest
from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest


def test_asr_accuracy_end_to_end_integration(tmp_path):
    work_dir = str(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Tạo video và audio giả lập
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy video")
    audio_file = data_dir / "original_audio.wav"
    audio_file.write_text("dummy audio")

    # Vocals từ Demucs
    vocals_file = data_dir / "vocals.wav"
    vocals_file.write_text("dummy vocals")

    settings = Settings(
        asr_use_vocals=True,
        ocr_enabled=True,
        asr_vad_pad_s=0.3,
    )
    pipeline = DubPipeline(settings)

    mock_asr_segments = [
        {"id": 1, "start": 0.5, "end": 2.5, "text": "你为什么不告诉"},
        {"id": 2, "start": 6.0, "end": 8.0, "text": "今天天气很好"},
    ]
    mock_ocr_segments = [
        {"text": "你为什么不告诉我", "start_time": 0.4, "end_time": 2.6, "confidence": 0.95},
        {"text": "中间遗漏的一句话", "start_time": 3.0, "end_time": 5.0, "confidence": 0.92},
    ]

    mock_bg_future = MagicMock()
    mock_bg_future.result.return_value = None

    req = DubRequest(
        file_path=str(video_file),
        source_lang="zh-CN",
        target="vi",
        bg_mode="demucs",
    )

    with patch("subprocess.run") as mock_subproc, \
         patch("autodub.speech.transcriber.transcribe", return_value=mock_asr_segments), \
         patch("autodub.media.ocr.detect_hardsub", return_value=True), \
         patch("autodub.media.ocr.run_selective_ocr", return_value=mock_ocr_segments):

        mock_subproc.return_value = MagicMock(returncode=0)

        # 1. Test ASR source selection
        asr_src = pipeline._asr_source(work_dir, mock_bg_future, settings, str(audio_file), req)
        assert "asr_vocals.wav" in asr_src or asr_src == str(vocals_file)

        # 2. Test Step 3 Fusion Flow
        meta = {"empty_chunks": [{"start": 3.0, "end": 5.0}]}
        from autodub.speech.transcriber import transcribe
        segments = transcribe(asr_src, "zh-CN", settings, meta=meta)

        from autodub.media.ocr import detect_hardsub, run_selective_ocr
        from autodub.text.fusion import detect_suspect_segments, fuse
        from autodub.utils import save_json_atomic

        assert detect_hardsub(str(video_file), settings) is True
        suspects1 = detect_suspect_segments(segments, meta.get("empty_chunks"))
        assert len(suspects1.suspect) >= 1

        ocr_segs = run_selective_ocr(str(video_file), suspects1.suspect, settings, work_dir)
        assert len(ocr_segs) == 2

        suspects2 = detect_suspect_segments(segments, meta.get("empty_chunks"), ocr_segs)
        fused_segs, fusion_report = fuse(segments, ocr_segs, suspects2)

        report_path = os.path.join(str(data_dir), "asr_fusion_report.json")
        save_json_atomic(fusion_report, report_path)

        # 3. Verify invariants & outcomes
        # Câu 1 được merge thêm chữ "我"
        assert fused_segs[0]["text"] == "你为什么不告诉我"
        # Câu 2 được thêm từ OCR standalone
        assert fused_segs[1]["text"] == "中间遗漏的一句话"
        assert fused_segs[1]["start"] == 3.0
        assert fused_segs[1]["end"] == 5.0
        # Câu 3 là câu ASR 2
        assert fused_segs[2]["text"] == "今天天气很好"
        assert len(fused_segs) == 3

        # Báo cáo JSON
        assert os.path.isfile(report_path)
        assert fusion_report["total_fused"] == 3
        assert fusion_report["stats"]["merged_count"] >= 1
        assert fusion_report["stats"]["ocr_added_count"] >= 1
