import json
import os
from unittest.mock import MagicMock, patch
import pytest
from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest


def test_pipeline_step3_ocr_fusion_wiring(tmp_path):
    pipeline = DubPipeline(Settings(ocr_enabled=True))

    mock_segments = [
        {"id": 1, "start": 0.5, "end": 2.0, "text": "你为什么不告诉"}
    ]
    mock_ocr = [
        {"text": "你为什么不告诉我", "start_time": 0.4, "end_time": 2.1, "confidence": 0.95}
    ]

    with patch("autodub.media.ocr.detect_hardsub", return_value=True), \
         patch("autodub.media.ocr.run_selective_ocr", return_value=mock_ocr):

        work_dir = str(tmp_path)
        os.makedirs(os.path.join(work_dir, "data"), exist_ok=True)

        from autodub.text.fusion import detect_suspect_segments, fuse

        suspects1 = detect_suspect_segments(mock_segments)
        suspects1.suspect = mock_segments

        ocr_segs = mock_ocr
        suspects2 = detect_suspect_segments(mock_segments, ocr_segments=ocr_segs)
        fused_segs, report = fuse(mock_segments, ocr_segs, suspects2)

        assert len(fused_segs) == 1
        assert fused_segs[0]["text"] == "你为什么不告诉我"
        assert report["version"] == 1

