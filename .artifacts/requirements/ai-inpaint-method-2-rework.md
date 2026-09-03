# Phân tích yêu cầu - Rework Phương thức 2 (AI Inpaint xoá phụ đề)

TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH
NGÀY: 2026-09-03

## 1. Mục tiêu

Khi người dùng chọn **Phương thức 2 - Xóa sạch AI Inpainting**, pipeline phải thật sự xử lý bằng engine AI đã chọn, tạo video đầu ra ổn định, giữ đúng vùng/thời gian cần xóa, và báo lỗi rõ ràng khi AI không khả dụng. Không được âm thầm biến lỗi AI thành Boxblur mà vẫn báo thành công.

## 2. User Story

Là người dùng LPHVSub, tôi muốn xóa phụ đề cứng bằng AI Inpaint (LaMa ONNX hoặc VSR) để nền phía sau được tái tạo tự nhiên; tôi cần biết engine nào đã chạy, vùng nào đã xử lý, tiến độ, cache hit/miss và nguyên nhân nếu không thể xử lý.

## 3. Functional Requirements

- FR-01: Tôn trọng `mask_method=ai_inpaint` từ GUI/settings/pipeline tới `merge_video`.
- FR-02: Chọn đúng engine (`lama_onnx` hoặc `vsr_cli`) và truyền đủ device/model/VSR configuration.
- FR-03: Hỗ trợ model fixed-shape và dynamic-shape với patch kích thước bất kỳ, blend đúng mask và không làm thay đổi vùng ngoài mask.
- FR-04: Vùng có `t_start`/`t_end` chỉ được áp dụng trong khoảng thời gian; vùng tĩnh áp dụng toàn bộ video.
- FR-05: Cache key phải thay đổi khi video, vùng, engine, model hoặc thông số xử lý thay đổi; cache tạm phải được dọn an toàn khi lỗi/hủy.
- FR-06: Theo dõi progress, cancellation và lỗi subprocess/inference; không nuốt lỗi.
- FR-07: Nếu AI không sẵn sàng, preflight/runtime phải trả trạng thái lỗi có hướng dẫn. Fallback Boxblur chỉ xảy ra khi người dùng/setting cho phép rõ ràng và phải ghi nhận engine thực tế.
- FR-08: GUI hiển thị engine/device, trạng thái preflight, tiến độ và thông báo kết quả đúng với engine thực tế.

## 4. Non-functional Requirements

- NFR-01: Không đọc toàn bộ video vào RAM; giữ streaming/ROI optimization.
- NFR-02: Không để subprocess/pipe/worker mồ côi sau cancel hoặc exception.
- NFR-03: Không phá backward compatibility với `mask_method=blur` và `none`.
- NFR-04: Log phải phân biệt `AI_INPAINT`, `BOXBLUR_FALLBACK`, `CACHE_HIT`, `CANCELLED`, `FAILED`.
- NFR-05: Không dùng `eval` cho dữ liệu fps hoặc dữ liệu ngoại vi.

## 5. Hành vi hiện tại (đã xác minh từ source)

- `autodub/media/video.py::merge_video` gọi `inpaint_video_with_cache` khi `mask_method == "ai_inpaint"`, nhưng bắt mọi `Exception` rồi chuyển sang `effective_blur_regions = blur_regions`; đây là nguyên nhân trực tiếp khiến lỗi AI trông như Phương thức 1.
- `autodub/media/inpaint/lama_onnx.py` dùng OpenCV Telea khi thiếu model/onnxruntime; kết quả có thể nhìn như vệt mờ và không chứng minh AI đã chạy.
- `autodub/media/inpaint/lama_onnx.py::inpaint_video` tạo một `roi_mask` cố định và áp dụng cho mọi frame; schema có `t_start`/`t_end` nhưng đường AI hiện chưa lọc vùng theo thời gian.
- `autodub/media/inpaint/vsr_bridge.py` lấy `VSR_DIR` từ environment khi khởi tạo; lời gọi `merge_video` không truyền `vsr_dir` rõ ràng.
- GUI `StyleDialog` cho phép chọn `ai_inpaint`, engine và device; preflight có kiểm tra model/VSR nhưng cần đối chiếu với lỗi runtime thực tế.
- Tests hiện có mock fixed-shape, cache, fallback và config; chưa chứng minh video thật, time-window, subprocess failure/cleanup, hoặc cấm silent fallback.

## 6. Root-cause hypotheses cần kiểm chứng trong design/implementation

- H-01 (đã quan sát): catch-all fallback trong `merge_video` làm mất semantics của Phương thức 2.
- H-02 (đã quan sát): Telea fallback khi thiếu model tạo output giống blur.
- H-03 (đã quan sát): temporal regions chưa được áp dụng trong AI path.
- H-04 (cần kiểm chứng): VSR config có thể không đi đúng từ Settings/GUI tới bridge.
- H-05 (cần kiểm chứng): pipe return codes và cancellation có thể để lại lỗi/output không hợp lệ mà caller nhận không rõ.

## 7. Module bị ảnh hưởng

- Core: `autodub/media/video.py`, `autodub/media/inpaint/__init__.py`, `autodub/media/inpaint/base.py`, `autodub/media/inpaint/lama_onnx.py`, `autodub/media/inpaint/vsr_bridge.py`.
- Config/pipeline: `autodub/config.py`, `autodub/pipeline.py`, `autodub/editor.py`.
- GUI: `autodub_gui/style_dialog.py`, `autodub_gui/pages/editor_page.py`, `autodub_gui/pages/editor_export.py`, `autodub_gui/pages/batch_page.py`.
- Tests: `tests/test_video_render_inpaint.py`, `tests/test_inpaint_engine.py`, `tests/test_inpaint_cache.py`, `tests/test_preflight.py`, `tests/test_style_dialog_mask.py`.

## 8. Edge cases

- Thiếu model, onnxruntime hoặc provider GPU.
- Model fixed 512x512, model dynamic, frame/ROI lẻ kích thước.
- Vùng rỗng, ngoài khung, chồng lấp, nhiều vùng, vùng có time window.
- Video xoay metadata, VFR, không có audio, codec lỗi.
- Cancel giữa decode/inference/encode; broken pipe; output rỗng.
- Cache cũ sinh bởi implementation khác hoặc engine khác.

## 9. Acceptance Criteria

- AC-01: Với model/engine hợp lệ, log và evidence chứng minh AI engine đã chạy; output không đi qua Boxblur fallback.
- AC-02: Khi AI lỗi/thiếu dependency, export FAIL rõ ràng với hướng dẫn (hoặc chỉ fallback nếu option explicit), không báo PASS giả.
- AC-03: Fixed/dynamic input-shape tests pass và vùng ngoài mask giữ nguyên.
- AC-04: `t_start`/`t_end` được tôn trọng trong AI path, có test frame/time boundary.
- AC-05: Engine/device/model/VSR path truyền đúng từ config/GUI tới runtime.
- AC-06: Cancel/error dọn subprocess/temp output; không để file hỏng được coi là cache hợp lệ.
- AC-07: Blur/none behavior cũ không regression.
- AC-08: GUI hiển thị đúng engine thực tế và trạng thái lỗi/progress.

## 10. Ngoài phạm vi

- Không thay đổi thuật toán hardsub auto-detection nếu không cần cho AI path.
- Không đổi format `blur_regions` công khai ngoài việc bổ sung xử lý time window tương thích.
- Không nâng dependency/model URL ngoài lý do được chứng minh.

## 11. Điểm cần xác nhận sau khi duyệt phân tích

- FQ-01: Khi AI không khả dụng, mặc định phải FAIL hay cho phép fallback Boxblur qua setting riêng? Khuyến nghị: FAIL mặc định cho Phương thức 2, fallback chỉ opt-in.
- FQ-02: VSR CLI có contract time-window hay chỉ nhận bounding box tĩnh? Cần kiểm tra tool ngoài trước khi thiết kế adapter.
- FQ-03: UI có cần nút “Test AI Inpaint”/preview riêng không? Khuyến nghị: thêm preflight/test nhẹ nếu không làm phình scope.

## 12. Approval gate

Chờ người dùng xác nhận:

`DUYỆT PHÂN TÍCH`
