# Fix Design

## Root Cause Đã Duyệt

Wizard tạo dự án mới làm mất `mask_method`, `inpaint_engine` và `inpaint_device` trước khi tạo `DubRequest`, khiến pipeline dùng mặc định Boxblur.

## Cách Sửa

1. Bổ sung các trường tùy chọn mask/inpaint vào `DubRequest` với default tương thích (`mask_method="blur"`, `inpaint_engine="lama_onnx"`, `inpaint_device="auto"`).
2. Cho `NewProjectPage.values()` xuất ba giá trị hiện tại từ `_mask_method`, `_inpaint_engine`, `_inpaint_device`.
3. Cho `_build_request()` truyền ba giá trị vào `DubRequest`.
4. Giữ fallback cho draft/consumer cũ không có key; không thay đổi hành vi mặc định khi người dùng chưa chọn AI.
5. Bổ sung test propagation từ `values()`/request đến lời gọi `merge_video`, và test default Boxblur để tránh regression.

Không thay đổi semantics fallback runtime AI→Boxblur trong change này nếu chưa có yêu cầu/duyệt mở rộng; đó là vấn đề độc lập cần được log rõ ở đợt sau.

## Files Được Phép Sửa

- `autodub/pipeline.py` — schema `DubRequest`.
- `autodub_gui/pages/new_project_page.py` — serialize values và xây request.
- `tests/` — test unit/integration propagation liên quan.

## Files Không Được Sửa

- `autodub/media/video.py` và `autodub/media/inpaint/*` (không cần cho root cause này).
- Các file orchestration/state/evidence, trừ cập nhật trạng thái do Codex thực hiện.

## Logic Trước

`StyleDialog.mask_options()` → thuộc tính tạm của `NewProjectPage` → `values()` bỏ qua → `DubRequest` không có field → pipeline fallback `Settings.mask_method` → Boxblur.

## Logic Sau

`StyleDialog.mask_options()` → `values()[mask_method/inpaint_engine/inpaint_device]` → `DubRequest` fields → pipeline truyền explicit options → `merge_video(mask_method="ai_inpaint", ...)` gọi AI Inpaint.

## Validation

- Khi chọn AI/LaMa/CPU, request phải giữ đúng ba giá trị.
- Khi không chọn hoặc draft cũ thiếu key, default vẫn là Boxblur/LaMa/auto.
- Existing direct media tests tiếp tục pass.
- Test pipeline mock xác nhận `merge_video` nhận `mask_method="ai_inpaint"` và không bị thay bằng blur.

## Regression Tests

- Test `NewProjectPage.values()` với thuộc tính mask AI.
- Test `_build_request()` tạo `DubRequest` giữ các giá trị mask.
- Test default request không cấu hình vẫn là `blur`.
- `tests/test_video_render_inpaint.py`.
- Bộ pytest liên quan GUI/pipeline nếu môi trường PySide6 cho phép.

## Existing Tests

`tests/test_video_render_inpaint.py` hiện pass 3/3 nhưng chỉ kiểm tra media layer; phải giữ nguyên kết quả.

## Risks

- Draft JSON cũ không có key; xử lý bằng `getattr(..., default)`/default dataclass.
- Batch flow có thể cần kiểm tra vì dùng `DubRequest`; không mở rộng sửa nếu không có failing evidence.
- Đây chỉ sửa propagation, không đảm bảo mọi lỗi runtime AI hoặc chất lượng inpaint.

## Rollback

Hoàn nguyên ba file code/test trong phạm vi change; không đụng cache video hay cấu hình người dùng.

## Change Budget

Tối đa 2 file product và các test tối thiểu cần thiết; không refactor pipeline/media.

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`
