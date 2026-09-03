import pytest
from autodub.text.fusion import (
    fuse,
    align_texts,
    W_ASR,
    W_OCR,
    W_ALIGN,
    W_TEMPORAL,
    W_COMPLETENESS,
    FUSION_OVERRIDE_MIN,
    ALIGN_MERGE_THRESHOLD,
    ALIGN_HIGH_THRESHOLD,
    ALIGN_LOW_THRESHOLD,
)


def test_fusion_constants_sum_to_one():
    total_w = W_ASR + W_OCR + W_ALIGN + W_TEMPORAL + W_COMPLETENESS
    assert pytest.approx(total_w, abs=1e-5) == 1.0


def test_fusion_passthrough_when_no_ocr():
    asr = [
        {"id": 1, "start": 0.5, "end": 2.0, "text": "你好世界"},
        {"id": 2, "start": 2.5, "end": 4.0, "text": "今天天气很好"},
    ]
    fused, report = fuse(asr, [], suspects=None)
    assert len(fused) == 2
    assert fused[0]["text"] == "你好世界"
    assert fused[1]["text"] == "今天天气很好"
    assert report["total_fused"] == 2


def test_fusion_case_2_added_suffix():
    # ASR: 你为什么不告诉 (0.5s - 2.5s)
    # OCR: 你为什么不告诉我 (0.4s - 2.6s)
    # Expected: merge thành "你为什么不告诉我", giữ timestamp ASR [0.5, 2.5]
    asr = [{"id": 1, "start": 0.5, "end": 2.5, "text": "你为什么不告诉"}]
    ocr = [{"text": "你为什么不告诉我", "start_time": 0.4, "end_time": 2.6, "confidence": 0.95}]

    fused, report = fuse(asr, ocr)
    assert len(fused) == 1
    assert fused[0]["text"] == "你为什么不告诉我"
    assert fused[0]["start"] == 0.5
    assert fused[0]["end"] == 2.5
    assert report["decisions"][0]["decision"] == "merged_prefix_suffix"


def test_fusion_case_3_added_prefix():
    # ASR: 为什么不告诉我 (0.5s - 2.5s)
    # OCR: 你为什么不告诉我 (0.4s - 2.6s)
    # Expected: merge thành "你为什么不告诉我"
    asr = [{"id": 1, "start": 0.5, "end": 2.5, "text": "为什么不告诉我"}]
    ocr = [{"text": "你为什么不告诉我", "start_time": 0.4, "end_time": 2.6, "confidence": 0.95}]

    fused, report = fuse(asr, ocr)
    assert len(fused) == 1
    assert fused[0]["text"] == "你为什么不告诉我"
    assert report["decisions"][0]["decision"] == "merged_prefix_suffix"


def test_fusion_case_4_ocr_standalone_empty_asr():
    # ASR bị mất câu thoại giữa khoảng 3.0s - 5.0s
    # OCR bắt được câu "这是一段被遗漏的语音"
    asr = [
        {"id": 1, "start": 0.5, "end": 2.0, "text": "第一句话"},
        {"id": 2, "start": 6.0, "end": 8.0, "text": "第二句话"},
    ]
    ocr = [
        {"text": "这是一段被遗漏的语音", "start_time": 3.0, "end_time": 5.0, "confidence": 0.92}
    ]

    fused, report = fuse(asr, ocr)
    assert len(fused) == 3
    assert fused[0]["text"] == "第一句话"
    assert fused[1]["text"] == "这是一段被遗漏的语音"
    assert fused[1]["start"] == 3.0
    assert fused[1]["end"] == 5.0
    assert fused[2]["text"] == "第二句话"


def test_fusion_case_5_high_similarity_keep_asr():
    # ASR đúng nhưng OCR sai nhẹ 1 ký tự (similarity >= 0.85, không phải prefix/suffix thuần)
    asr = [{"id": 1, "start": 0.5, "end": 2.5, "text": "今天天气真好啊"}]
    ocr = [{"text": "今天天气真好呀", "start_time": 0.5, "end_time": 2.5, "confidence": 0.88}]

    fused, report = fuse(asr, ocr)
    assert len(fused) == 1
    # Giữ ASR
    assert fused[0]["text"] == "今天天气真好啊"
    assert report["decisions"][0]["decision"] == "keep_asr_high_similarity"


def test_fusion_case_6_low_similarity_keep_asr():
    # ASR và OCR khác nhau hoàn toàn trong cùng khoảng thời gian (similarity < 0.6)
    asr = [{"id": 1, "start": 0.5, "end": 2.5, "text": "这是苹果"}]
    ocr = [{"text": "完全无关的文字内容", "start_time": 0.5, "end_time": 2.5, "confidence": 0.70}]

    fused, report = fuse(asr, ocr)
    assert len(fused) == 1
    assert fused[0]["text"] == "这是苹果"
    assert report["decisions"][0]["decision"] == "keep_asr_fallback"
