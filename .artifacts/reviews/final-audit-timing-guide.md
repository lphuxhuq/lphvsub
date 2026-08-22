# FINAL AUDIT — Timing Guide / timing_report.json (commit 528357f)

## Feature

Timing Guide / Timing Report JSON — xuất `timing_report.json` sau bước TTS + Soft Timing.

## Requirement Matrix

| Requirement | Implementation | Test | Status |
|---|---|---|---|
| FR-1: Tự động sinh `timing_report.json` trong `data/` sau TTS + Soft Timing | `autodub/pipeline.py:656-666` gọi `build_timing_guide` + `save_timing_guide` sau `apply_soft_timing` | Pipeline integration không break trong full suite | PASS |
| FR-2 Summary: total_segments, tổng thời lượng gốc/TTS, ratio, segments_ok / segments_need_edit | `autodub/media/timing.py:278-290` | `test_build_timing_guide_basic` | PASS |
| FR-2 Segments list: id, start, end, original/tts duration, diff_seconds, status, edit_hint, text_original, text_target | `autodub/media/timing.py:261-272` | `test_build_timing_guide_basic` (OK / TOO_LONG / TOO_SHORT, edit_hint tiếng Việt) | PASS |
| FR-3: Không gãy `quality_report.json` | `quality_report` dùng object `TimingReport` riêng (pipeline.py:685); grep xác nhận không consumer nào đọc nhầm file mới | Full suite pass | PASS |
| NFR-1: Thuần in-memory, < 50ms | Loop O(n) + 1 `json.dump` | — | PASS |
| NFR-2: Không ảnh hưởng merge/export | Code chèn giữa bước đo duration và `merge_segments`, không mutate thêm segments | Full suite pass | PASS |
| NFR-3: Test coverage logic + export | `tests/test_timing_guide.py` (basic, empty/None, save UTF-8) | 3/3 pass | PASS |
| AC-4: 627+ test PASS | `pytest tests/` | **630 passed**, 1 warning có sẵn (audioop deprecation) | PASS |

Ghi chú schema: FR-2 gốc liệt kê key `original_duration`/`tts_duration` ở summary, nhưng design đã duyệt chuẩn hoá thành `total_original_duration`/`total_tts_duration`. Implementation theo design — chấp nhận.

## Architecture

Đúng design: hai hàm đặt trong `autodub/media/timing.py`, pipeline gọi sau bước 6 (post voice-postprocess + soft timing). Điểm tích hợp tốt: `durations` đo từ `merge_dir` (clip đã hậu kỳ + voice_speed + atempo) nên số liệu là thời lượng người nghe thật; `seg["duration"]` giữ thời lượng câu gốc (comment rõ tại timing.py:189-191) nên so sánh dub-vs-nguồn còn đúng. Thêm so với design: tham số `target_lang` (mở rộng vô hại).

## Integration

- `target.text_field`, `target.name`, `req.url` (truy cập qua `getattr` an toàn) đều tồn tại tại điểm gọi.
- Không module/UI nào tiêu thụ `timing_report.json` — file dành cho người dùng đọc, đúng requirement.
- Không đụng database hay external service.

## Regression

`pytest tests/` → **630 passed** (≥ 627 theo AC). Không regression.

## Security

Ghi file JSON cục bộ trong work dir, UTF-8; filename là constant/param nội bộ — không path traversal, không log nội dung nhạy cảm.

## Performance

Một lượt quét O(n) + 1 file JSON; tái dùng list `durations` từ vòng đo có sẵn, không gọi `wav_duration_s` thừa. Không regression.

## Code Quality

- Không duplicate, dead code, debug code, TODO mới; comment đúng convention file.
- Cải thiện nhỏ (không chặn):
  - `durations[i]` là `None` (file wav thiếu) → fallback về `orig_dur`, status "OK" — có thể che khuất clip bị mất. Nên thêm flag riêng (vd "MISSING") sau này.
  - Ngưỡng hardcode `max(0.2, tol)` tại timing.py:249 nên tách thành constant có tên.

## Database

Không áp dụng.

## Documentation

Requirement / design / task docs đầy đủ trong `.artifacts/`. Không có config mới nên không cần example.

## Rủi ro còn lại

1. File wav TTS thiếu được báo "OK" im lặng (như trên) — chỉ ảnh hưởng độ chính xác báo cáo, không ảnh hưởng pipeline.
2. `tts_duration` đo SAU voice_speed: nếu VOICE_SPEED ≠ 1, số liệu là thời lượng đã tăng tốc — đúng trải nghiệm nghe nhưng cần lưu ý khi diễn giải.

## Kết luận

**PASS**
