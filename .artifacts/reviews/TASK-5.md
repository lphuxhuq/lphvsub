# Code Review — TASK-5 (Fusion Engine + Scoring)

## Phạm vi review
- **Production file:** [`autodub/text/fusion.py`](file:///d:/Project/lphvsub-main/autodub/text/fusion.py) (các hằng số scoring, trọng số `W_*`, và hàm `fuse`)
- **Test files:** [`tests/test_fusion_scoring.py`](file:///d:/Project/lphvsub-main/tests/test_fusion_scoring.py), [`tests/test_fusion_invariants.py`](file:///d:/Project/lphvsub-main/tests/test_fusion_invariants.py)

## Requirement & Design Compliance
- [x] Các trọng số scoring khớp thiết kế C4: `W_ASR=0.30`, `W_OCR=0.20`, `W_ALIGN=0.20`, `W_TEMPORAL=0.15`, `W_COMPLETENESS=0.15` (tổng = 1.0).
- [x] Ngưỡng quyết định: `FUSION_OVERRIDE_MIN=0.75`, `ALIGN_MERGE_THRESHOLD=0.80`, `ALIGN_HIGH_THRESHOLD=0.85`, `ALIGN_LOW_THRESHOLD=0.60`, `OCR_SCORE_MIN_EMPTY=0.60`.
- [x] 4 quy tắc quyết định (Rule 1: OCR Standalone / Override Empty; Rule 2: Merged Prefix/Suffix; Rule 3: Keep ASR High Similarity; Rule 4: Keep ASR Fallback) hoạt động đúng thứ tự ưu tiên.
- [x] Bất biến: `0 <= start < end`, `duration >= 0.1s`, không chồng chéo thời gian giữa các câu liên tiếp, re-index `id` tuần tự 1..N, `len(fused) >= len(asr)`.
- [x] Không mutate input `segments`.
- [x] Passthrough trả về bản copy nguyên vẹn khi `not ocr_segments`.

## Findings
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO:** Schema report chứa đầy đủ metadata (phiên bản, tổng số câu, quyết định chi tiết cho từng câu, thống kê tỷ lệ merge/override).

## Test Review
- `tests/test_fusion_scoring.py` (7 tests): Kiểm tra 6 case đặc tả, tổng trọng số và passthrough.
- `tests/test_fusion_invariants.py` (1 test): Property-based testing 50 vòng random seed kiểm tra các bất biến thời gian và mảng.
- 18/18 fusion tests passed trong 0.11s.

## Regression Review
- Toàn bộ test suite không bị ảnh hưởng. Không có thay đổi ngoài scope.

## Kết luận
`PASS`
