"""Unit test cho align_texts — ASR↔OCR character alignment (TASK-4)."""
from autodub.text.fusion import align_texts


def test_spec_case_missing_tail():
    """ASR thiếu cuối: 你为什么不告诉 + 你为什么不告诉我 → merge có 我."""
    al = align_texts("你为什么不告诉", "你为什么不告诉我")
    assert al.merged == "你为什么不告诉我"
    assert al.added_suffix == "我"
    assert al.added_prefix == ""
    assert al.similarity >= 0.8


def test_spec_case_missing_head():
    """ASR thiếu đầu: 为什么不告诉我 + 你为什么不告诉我 → OCR bổ sung 你."""
    al = align_texts("为什么不告诉我", "你为什么不告诉我")
    assert al.merged == "你为什么不告诉我"
    assert al.added_prefix == "你"
    assert al.added_suffix == ""


def test_identical_texts():
    al = align_texts("你为什么不告诉我", "你为什么不告诉我！？")
    # Normalize bỏ punct → hai chuỗi giống hệt
    assert al.similarity == 1.0
    assert al.merged == "你为什么不告诉我"
    assert al.added_prefix == "" and al.added_suffix == ""


def test_ocr_errors_few_chars_keeps_asr():
    """Case 5: OCR sai vài ký tự (không phải substring) → merged giữ ASR."""
    al = align_texts("你到底在干什么", "你到底在干嘛")
    assert al.merged == "你到底在干什么"
    assert al.added_prefix == "" and al.added_suffix == ""
    assert al.similarity < 1.0


def test_completely_different():
    """Case 6: khác hoàn toàn → merged giữ ASR, similarity thấp."""
    al = align_texts("今天天气很好", "我想吃苹果了")
    assert al.merged == "今天天气很好"
    assert al.similarity < 0.6


def test_no_duplicate_in_merged():
    """Bất biến: merged không chứa substring chung hai lần do ghép."""
    asr = "为什么"
    ocr = "你为什么不告诉我"
    al = align_texts(asr, ocr)
    assert al.merged == "你为什么不告诉我"
    # "为什么" xuất hiện đúng 1 lần trong merged
    assert al.merged.count("为什么") == 1


def test_empty_inputs():
    assert align_texts("", "").similarity == 1.0
    al = align_texts("", "你好吗")
    assert al.merged == "你好吗"
    al2 = align_texts("你好吗", "")
    assert al2.merged == "你好吗"
    assert al2.similarity == 0.0


def test_all_punctuation_normalized_to_empty():
    assert align_texts("。！？", "，").similarity == 1.0


def test_fullwidth_and_mixed_alnum():
    # Full-width alnum được chuẩn hoá giống nhau hai bên
    al = align_texts("第1集", "第１集")
    assert al.similarity == 1.0


def test_asr_longer_than_ocr_substring():
    """ASR DÀI hơn OCR (OCR thiếu cuối) → không cắt ASR, giữ nguyên."""
    al = align_texts("你为什么不告诉我", "你为什么不告诉")
    assert al.merged == "你为什么不告诉我"
    assert al.similarity >= 0.8
