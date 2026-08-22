# Code Review — TASK-3 (asr-accuracy-boost)

## Phạm vi review
- `autodub/media/ocr.py` (NEW), `autodub/media/ocr_worker.py` (NEW, .venv-ocr)
- `scripts/setup_ocr.py` (NEW), `autodub/config.py` (4 settings OCR + env + `ocr_venv_python_path()`)
- `tests/test_ocr_normalize.py` (13), `tests/test_ocr_cache.py` (5)

## Requirement Compliance
| AC TASK-3 | Bằng chứng | Kết quả |
|---|---|---|
| Không suspect → 0 frame extract, 0 worker call | `test_no_suspects_zero_cost` (counter) | ĐẠT |
| Window clamp biên video | `test_windows_merge_overlap_and_clamp` (margin-trước-clamp-sau) | ĐẠT |
| Normalize full→half-width, multi-line, merge không trùng, confidence filter | `test_ocr_normalize.py` 13 test | ĐẠT |
| Cache hit không chạy lại ffmpeg/worker | `test_cache_hit_avoids_rework` (counter), schema check | ĐẠT |
| Worker chết/venv thiếu → exception rõ | `test_worker_error_raises_for_caller` + check trong `_run_ocr_worker` | ĐẠT |

## Findings (đã sửa trong unit)
- [MEDIUM→đã sửa] `normalize_ocr_text` bản đầu convert TOÀN BỘ block full-width (0xFF01-0xFF5E) → punct `？！，` thành ASCII rồi bị drop. Sửa: chỉ convert full-width ALNUM, giữ punct CJK nguyên dạng.
- [MEDIUM→đã sửa] `windows_from_suspects` clamp (start,end) vào duration TRƯỚC khi cộng margin → window cuối video bị vượt biên. Sửa: margin trước, clamp sau.
- [LOW→đã sửa] 1 test kỳ vọng sai: frame dropout giữa các frame giống nhau nên gộp (chống nhấp nháy) — test đã đổi thành assert hành vi dropout-tolerant.

## Design Compliance
- RapidOCR trong `.venv-ocr` + worker standalone JSON-lines — đúng pattern ASR worker (proto_out tách stderr).
- OCR chỉ trên suspect window × fps thấp × crop region — đúng C5. Frame tạm dọn sau merge, cache JSON keyed (mtime, size, fps, region, windows) — đúng NFR-6.
- [INFO] `detect_hardsub` probe 5 frame × 10fps crop — mỗi probe 1 frame hiệu dụng; không cache probe (5 frame rẻ, tránh phức tạp schema) — chủ đích, ghi nhận.

## Test Review
Test thật với counter mock — chứng minh AC-6/NFR-6 trực tiếp. Không test worker thật (cần .venv-ocr — thuộc TASK-7/smoke khi user chạy setup).

## Regression Review
Module mới + settings mới (OCR_ENABLED=false mặc định) — không đường chạy cũ nào đụng. `config.py` thêm field/method thuần mở rộng.

## Security Review
argv là path nội bộ; tempfile TemporaryDirectory tự dọn cho probe. OK.

## Scope Review
Đúng file được phép (thêm `config.py` đã được TASK-3 cho phép trong breakdown).

## Kết luận
**PASS**
