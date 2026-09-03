# Root Cause Analysis

## Bug

Khi chọn Phương thức 2 (AI Inpaint) trong wizard tạo dự án mới, video xuất ra vẫn che phụ đề bằng Boxblur như Phương thức 1.

## Reproduction

`PARTIALLY_REPRODUCED` bằng static execution trace và test điều phối:

- `tests/test_video_render_inpaint.py` xác nhận `merge_video(mask_method="ai_inpaint")` sẽ gọi `inpaint_video_with_cache` khi nhận được tùy chọn đúng; nhánh này pass (3/3 test).
- Đường GUI wizard không đưa lựa chọn mask vào `DubRequest`: `NewProjectPage.values()` chỉ thêm `blur_regions` và `subtitle_style`, còn `_build_request()` không truyền `mask_method`, `inpaint_engine`, hoặc `inpaint_device`.
- Vì vậy request chạy pipeline nhận giá trị mặc định từ `Settings`, thường là `mask_method="blur"`; `merge_video` không vào nhánh AI và dựng filter Boxblur.

## Symptom

Vùng phụ đề trong file xuất cuối vẫn bị làm mờ, không được tái tạo nền bằng AI.

## Root Cause

Lựa chọn Method 2 chỉ được giữ trong các thuộc tính tạm `_mask_method`, `_inpaint_engine`, `_inpaint_device` của `NewProjectPage`, nhưng không được đưa vào dữ liệu `values()`/`DubRequest` khi bấm chạy wizard. `_persist_pricing_choices()` cũng nhận `self.values()` nên không thể lưu các lựa chọn này cho Settings. Pipeline do đó rơi về mặc định Boxblur dù UI vừa chọn AI.

## Evidence

1. `autodub_gui/pages/new_project_page.py::values` (khoảng dòng 363): chỉ ghi `blur_regions` và `subtitle_style` ngoài dữ liệu các step.
2. `autodub_gui/pages/new_project_page.py::_build_request` (khoảng dòng 678): khởi tạo `DubRequest` không có ba trường mask/inpaint.
3. `autodub/pipeline.py::DubRequest` không khai báo ba trường này; pipeline dùng `getattr(req, ..., None)` rồi fallback `settings.mask_method` (mặc định `"blur"`).
4. `autodub/media/video.py::merge_video`: chỉ gọi AI khi `mask_method == "ai_inpaint"`; nếu không, `build_filter_complex` nhận `blur_regions` và tạo Boxblur.
5. Smoke test LaMa ONNX trước đó đã tải được `models/inpaint/lama.onnx` bằng ONNX Runtime CPU, nên thiếu model không phải nguyên nhân đã xác nhận trong môi trường này.

## Call Flow

`StyleDialog.mask_options()` → `NewProjectPage._mask_method` (tạm thời) → **(bị mất tại `values()`/`_build_request()`)** → `DubPipeline.run()` → `getattr(req, "mask_method", None)` = `None` → `Settings.mask_method` = `"blur"` → `merge_video()` → Boxblur filtergraph.

## Affected Files

- `autodub_gui/pages/new_project_page.py`
- `autodub/pipeline.py`
- `autodub/media/video.py` (điểm quan sát symptom; chưa cần sửa để xác nhận root cause)

## Contributing Factors

- `DubRequest` thiếu field rõ ràng cho mask/inpaint.
- Boxblur là fallback im lặng khi AI runtime lỗi, khiến hai loại lỗi khó phân biệt (đây là vấn đề thứ cấp cần xử lý sau khi sửa propagation).
- Existing tests gọi trực tiếp `merge_video`, không đi qua GUI wizard nên không phát hiện mất tùy chọn.

## Why Existing Tests Did Not Catch It

Test hiện tại mock trực tiếp `merge_video` với `mask_method="ai_inpaint"`; không có test từ `StyleDialog`/`NewProjectPage` đến `DubRequest` và pipeline export.

## Impact

Mọi lượt xuất mới từ wizard có chọn AI Inpaint nhưng không có Settings mặc định AI đều cho kết quả Boxblur. Các dự án mở lại trong editor có thể khác vì `render_opts.json` có đường lưu riêng.

## Regression Risk

Thêm field vào request/values có thể ảnh hưởng serialize draft, batch template và backward compatibility với draft cũ; cần test default vẫn là Boxblur khi người dùng không chọn Method 2.

## Proposed Fix

Bổ sung ba tùy chọn mask/inpaint vào schema `DubRequest`, `NewProjectPage.values()` và `_build_request()` (đồng thời giữ fallback tương thích cho draft cũ), sau đó thêm test integration propagation và kiểm tra export. Xem xét tách lỗi AI khỏi fallback Boxblur trong một fix design riêng hoặc cùng change budget đã duyệt.

## Alternatives Considered

- Chỉ đổi default Settings sang AI: không đúng ý người dùng và phá backward compatibility.
- Chỉ bỏ Boxblur fallback trong `merge_video`: không sửa được việc tùy chọn bị mất trước khi vào pipeline.

## Scope

Phân tích này chỉ xác nhận propagation bug của wizard tạo dự án mới; chưa thay đổi product code và chưa kết luận các vấn đề temporal mask/Telea fallback.

## Unknowns

- Các đường batch/editor có thể có propagation riêng; cần regression test sau khi root cause được duyệt.
- Khi propagation đã đúng, cần kiểm tra runtime AI failure có còn xảy ra trên video người dùng cụ thể hay không.

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT NGUYÊN NHÂN`
