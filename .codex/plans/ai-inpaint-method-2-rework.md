# Draft Plan - Rework Phương thức 2 (AI Inpaint xoá phụ đề)

STATUS: DRAFT - CHỜ DUYỆT PHÂN TÍCH
SOURCE REQUIREMENT: `.artifacts/requirements/ai-inpaint-method-2-rework.md`

## Goal

Khôi phục semantics đúng của Phương thức 2: AI Inpaint phải chạy thật, có engine/device/model rõ ràng, xử lý đúng temporal mask, cleanup an toàn và không silent fallback sang Boxblur.

## Current Architecture

GUI `StyleDialog` lưu `mask_method`, `inpaint_engine`, `inpaint_device`; `pipeline/editor` truyền options; `media/video.py::merge_video` điều phối; `media/inpaint/` có cache + LaMa ONNX/VSR engines; `subtitle.py` vẫn dựng Boxblur filtergraph.

## Existing Behavior / Gaps

Chi tiết đã ghi trong requirement analysis. Gap lớn nhất là catch-all fallback trong `merge_video`, Telea fallback không phân biệt AI, temporal regions chưa chạy trong AI path, và đường truyền VSR config/cleanup cần kiểm chứng.

## Proposed Strategy (sau khi analysis/design được duyệt)

1. Viết regression tests trước: cấm silent fallback, engine/config propagation, temporal masks, process cleanup, fixed/dynamic shape.
2. Tách kết quả runtime thành trạng thái có cấu trúc (`engine_used`, `cache_hit`, `fallback_used`, `frames_processed`, `error_code`) thay vì chỉ trả path.
3. Sửa `merge_video` để Phương thức 2 FAIL rõ ràng mặc định; fallback Boxblur chỉ khi option explicit và phải log/evidence.
4. Chuẩn hóa ROI/mask theo từng frame/time window; giữ tối ưu bounding box nhưng không áp dụng vùng ngoài thời gian.
5. Hardening LaMa/VSR: truyền đủ cấu hình, validate model/provider, kiểm tra return code/pipe, cancel cleanup và atomic cache commit.
6. Cập nhật preflight/GUI để hiển thị khả dụng, engine thực tế, progress và lỗi hướng dẫn được.
7. Chạy test hẹp → integration/export fixture → regression; sau đó Computer Use UI verification cho chọn Phương thức 2, thiếu model, progress, error và thành công.

## What Will Not Change

`mask_method=blur`/`none`, schema normalized `blur_regions`, subtitle burn pipeline và auto-detection không đổi ngoài compatibility cần thiết.

## Proposed Task Graph (chưa tạo task cho tới khi duyệt analysis/design)

```text
T1 Characterize current AI/fallback behavior + fixtures
  ↓
T2 Define runtime result/error contract and config propagation
  ↓
T3 Implement temporal mask + engine cleanup hardening
  ↓
T4 Remove silent fallback; add explicit opt-in fallback/preflight
  ↓
T5 GUI status/progress/error integration
  ↓
T6 Integration/regression tests
  ↓
T7 Computer Use UI verification + Codex review
```

## Acceptance / Test Strategy

Map to AC-01..AC-08 in the requirement file. Use existing pytest suites first, add deterministic mocks for ONNX/VSR/FFmpeg, then a small real-video fixture if available. Record actual output and engine markers; do not rely on historical “1015 passed” claims without rerunning.

## Antigravity Delegation

After `DUYỆT PHÂN TÍCH` and `DUYỆT THIẾT KẾ`, create one READY task at a time. Codex renders each handoff from this plan + task, saves SHA-256 evidence, sends via Computer Use, parses TASK ID/STATUS/PROGRESS, verifies diff, and reviews before advancing.

## Rollback

Keep fallback behavior behind an explicit option during migration; preserve blur/none paths; revert only scoped files with user authorization. Never discard unrelated changes.

## Completion Criteria

All tasks DONE, AC-01..AC-08 evidenced, tests/regression pass, UI verification pass or not applicable, Antigravity reports match diff, and Codex review PASS.
