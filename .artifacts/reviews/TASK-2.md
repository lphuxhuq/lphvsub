# Code Review — TASK-2 (asr-accuracy-boost)

## Phạm vi review
- `autodub/text/fusion.py` (NEW — chỉ phần detection + hằng số)
- `tests/test_suspect_detection.py` (NEW, 12 test)

## Requirement Compliance
| AC TASK-2 | Bằng chứng | Kết quả |
|---|---|---|
| 4 heuristic với `reason` cụ thể | `detect_suspect_segments` — empty_speech_chunk / text_too_short_for_duration (adaptive median, tắt khi <5 mẫu) / gap_anomaly (adaptive max(1.5, 3×median)) / ocr_no_asr_match | ĐẠT |
| Không false positive khi thiếu mẫu | `test_char_rate_heuristic_off_below_min_samples` | ĐẠT |
| Partition normal/suspect đúng input | `test_partition_preserves_all_segments` | ĐẠT |
| Thuần stdlib, không mutate input | chỉ statistics/dataclasses; `test_input_not_mutated` | ĐẠT |

## Findings
- Không có CRITICAL/HIGH. Trong quá trình dev có 3 test sai số học (gap 3.0s == ngưỡng không > ; OCR window đặt nhầm vào trong segment; id segment ghi nhầm 6 thay vì 5) — code chạy đúng, test đã sửa trước khi kết thúc unit.
- [INFO] gap_anomaly flag CẢ HAI câu kề (design ghi "câu sau") — chủ đích mở vùng OCR phủ lấy khoảng lặng; hai câu kề đều hợp lệ lân cận gap.
- [LOW] Ô `stats` log tổng hợp lọc theo hậu tố key — dễ vỡ khi thêm reason mới; chấp nhận vì chỉ là log.

## Test Review
12 test thật: happy path từng heuristic, adaptive off, empty/covered chunk, matched/unmatched OCR, no-mutation, partition, empty input.

## Regression Review
Module mới, chưa được ai import — 0 rủi ro regression. Full suite chạy ở cuối TASK-3 (gom cụm).

## Scope Review
Đúng scope TASK-2 (chỉ fusion.py detection + test).

## Kết luận
**PASS**
