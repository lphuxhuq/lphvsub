# Code Review — TASK-6 (Pipeline Wiring + Settings + ASR Source)

## Phạm vi review
- **Production files:**
  - [`autodub/config.py`](file:///d:/Project/lphvsub-main/autodub/config.py) (`asr_use_vocals` dataclass setting + `load()`)
  - [`autodub/pipeline.py`](file:///d:/Project/lphvsub-main/autodub/pipeline.py) (`_asr_source` method + Step 3 ASR / OCR / Fusion wiring)
- **Test files:**
  - [`tests/test_pipeline_asr_source.py`](file:///d:/Project/lphvsub-main/tests/test_pipeline_asr_source.py)
  - [`tests/test_pipeline_wiring.py`](file:///d:/Project/lphvsub-main/tests/test_pipeline_wiring.py)

## Requirement & Design Compliance
- [x] **FR-A1**: `_asr_source()` ưu tiên lấy `vocals.wav` từ Demucs và resample 16kHz mono sang `asr_vocals.wav` khi `asr_use_vocals=True` và `bg_mode=demucs`.
- [x] **FR-C6**: Khối `if getattr(settings, "ocr_enabled", False):` trong Step 3 gọi `detect_hardsub` → `detect_suspect_segments` → `run_selective_ocr` → `fuse()` → lưu báo cáo `asr_fusion_report.json`.
- [x] Mọi ngoại lệ của OCR/Fusion đều được bọc `try...except` an toàn và ghi warning, không làm sập pipeline (fallback về ASR gốc).
- [x] Không mutate cấu trúc transcript lưu xuống đĩa, tương thích ngược 100% với luồng dịch/TTS tiếp theo.

## Findings
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO:** Cache `asr_vocals.wav` kiểm tra mtime của `vocals.wav` giúp tránh chạy lại lệnh ffmpeg resample thừa khi resume.

## Test Review
- `tests/test_pipeline_asr_source.py`: 2 tests kiểm tra chọn audio gốc hoặc vocals đã tách.
- `tests/test_pipeline_wiring.py`: 1 test kiểm tra quy trình nối Step 3 với OCR hardsub probe và fusion.
- Kết quả: 3/3 passed trong 0.11s.

## Regression Review
- Toàn bộ test suite không bị ảnh hưởng. Không sửa ngoài scope.

## Kết luận
`PASS`
