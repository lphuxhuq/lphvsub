# Goal

Đảm bảo lựa chọn Phương thức 2 (AI Inpaint) từ wizard tạo dự án mới được truyền nguyên vẹn tới pipeline và `merge_video`, để export thực sự chạy AI thay vì mặc định Boxblur.

# Current Architecture

`StyleDialog.mask_options()` cập nhật thuộc tính tạm trên `NewProjectPage`; `values()` tạo dữ liệu wizard; `_build_request()` tạo `DubRequest`; `DubPipeline.run()` chọn tùy chọn và gọi `merge_video()`.

# Existing Behavior

Mask options bị bỏ qua trong `values()`/`_build_request()`. `DubRequest` không có field tương ứng, nên pipeline dùng `Settings.mask_method` mặc định `blur`.

# Requested Behavior

Ba tùy chọn `mask_method`, `inpaint_engine`, `inpaint_device` phải đi từ GUI → request → pipeline → media layer; draft cũ và mặc định không chọn AI vẫn tương thích.

# Gaps

Thiếu field request, thiếu serialization wizard, thiếu regression test end-to-end propagation.

# Risks

Backward compatibility với draft JSON cũ và các flow batch/editor; không mở rộng thay đổi runtime inpaint fallback.

# Dependencies

Không thêm dependency. Antigravity phải làm việc trong workspace hiện tại và giữ thay đổi ngoài phạm vi.

# Implementation Strategy

Sửa tối thiểu schema `DubRequest` và `NewProjectPage`; thêm test request propagation/default; chạy test hẹp rồi regression liên quan.

# What Will Not Change

Không sửa `media/video.py`, engine LaMa/VSR, cache, semantics Boxblur/none, hoặc cơ chế fallback runtime.

# Antigravity Delegation Strategy

Một task READY duy nhất, handoff render deterministic từ plan + task. Antigravity chỉ sửa file trong scope, báo cáo files/tests/blockers; Codex đối chiếu diff và tự chạy verification.

# Computer Use Control Strategy

Xác nhận cửa sổ Antigravity và workspace `D:\Project\lphvsub-main`, gửi handoff nguyên văn, kiểm tra TASK ID acknowledgement và lưu capture evidence.

# Task Graph

TASK-003 (propagation fix + regression tests) → Codex verification → review.

# Acceptance Criteria

- `DubRequest` có default tương thích và nhận ba tùy chọn mask/inpaint.
- `NewProjectPage.values()` và `_build_request()` giữ đúng lựa chọn AI.
- Draft cũ thiếu key vẫn chạy với default Boxblur.
- Regression tests chứng minh explicit AI reaches pipeline/media call.
- Existing inpaint tests pass.

# Test Strategy

Chạy test mới cho GUI/request, `tests/test_video_render_inpaint.py`, rồi pytest pipeline/config liên quan nếu môi trường hỗ trợ.

# UI/UX Verification Strategy

Sau implementation, kiểm tra tối thiểu bằng Computer Use nếu có thể: chọn AI trong StyleDialog, mở lại summary/export và xác nhận log/task state; không coi screenshot là bằng chứng code-level.

# Rollback Strategy

Revert chỉ các file trong task nếu test/review fail; không xóa cache hay thay đổi cấu hình người dùng.

# Completion Criteria

Diff đúng scope, test pass, evidence đầy đủ, Codex review PASS.

# Evidence Plan

`.codex/evidence/handoff-TASK-003.md`, capture acknowledgement/progress, `.codex/state/test-results.md`, và review report.
