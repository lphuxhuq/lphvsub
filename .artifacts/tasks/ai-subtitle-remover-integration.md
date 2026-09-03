# Task Breakdown: AI Subtitle Remover Integration (Phương thức che/xóa phụ đề thứ 2)

> Feature: `ai-subtitle-remover`. Nguồn: Design đã duyệt `.artifacts/designs/ai-subtitle-remover-integration.md`. Skill: `task-breakdown`.

---

## 1. Dependency Graph

```
TASK-001 (Config & Data Model)
    │
    ▼
TASK-002 (Inpaint Base & Cache Manager)
    │
    ├─────────────────────────────┐
    ▼                             ▼
TASK-003 (LaMa ONNX Engine)   TASK-004 (VSR Bridge & Preflight)
    │                             │
    └──────────────┬──────────────┘
                   ▼
TASK-005 (Video & Pipeline Integration)
    │
    ▼
TASK-006 (E2E Verification & Regression Test)
```

---

## 2. Danh sách Unit

---

### TASK-001 — Cấu hình & Mô hình dữ liệu (Config & Data Model)

**Mục tiêu:**
Bổ sung các trường cấu hình cho `mask_method`, `inpaint_engine`, `inpaint_device` trong `config.py` và hỗ trợ nạp/lưu trạng thái trong `editor.py`.

**Dependency:** Không có.

**File được phép sửa:**
- `autodub/config.py`
- `autodub/editor.py`

**File không được sửa:**
- `autodub/speech/*`, `autodub/text/*`, `autodub/media/subtitle.py`

**Thay đổi dự kiến:**
- Thêm `mask_method` (mặc định `"blur"`), `inpaint_engine` (`"lama_onnx"`), `inpaint_device` (`"auto"`), `inpaint_model_path` vào `DEFAULT_CONFIG`.
- Đảm bảo `EditorState.to_dict()` và `EditorState.from_dict()` serialize/deserialize các trường này đầy đủ, giữ tương thích ngược với các project cũ.

**Acceptance Criteria:**
- Project cũ nạp vào không có `mask_method` tự động nhận mặc định là `"blur"`.
- `config.py` export đầy đủ các hằng số và config keys.

**Test:**
- `tests/test_config.py` (hoặc test unit kiểm tra load/dump project state).

**Rủi ro:** Không có.

**Rollback:** Revert commit git của TASK-001.

---

### TASK-002 — Inpaint Base Engine & Smart Cache Manager

**Mục tiêu:**
Xây dựng interface `BaseInpaintEngine` và module `cache.py` quản lý sinh mã hash SHA256 cho video sạch đã inpaint.

**Dependency:** TASK-001

**File được phép sửa:**
- `[NEW] autodub/media/inpaint/__init__.py`
- `[NEW] autodub/media/inpaint/base.py`
- `[NEW] autodub/media/inpaint/cache.py`
- `[NEW] tests/test_inpaint_cache.py`

**File không được sửa:**
- Toàn bộ các file khác.

**Thay đổi dự kiến:**
- Định nghĩa abstract class `BaseInpaintEngine` với các phương thức `inpaint_video` và `inpaint_frame`.
- `cache.py`: Hàm `compute_inpaint_hash(video_path, regions, engine_name) -> str` và `get_cached_clean_video(cache_key) -> str | None`.

**Acceptance Criteria:**
- Hàm tính hash cho kết quả giống nhau khi cùng video + cùng danh sách ROI; khác nhau khi đổi tọa độ ROI dù chỉ 1 pixel.
- Kiểm tra tính hợp lệ của file cache (tồn tại, dung lượng > 0).

**Test:**
- `pytest tests/test_inpaint_cache.py`

**Rủi ro:** Hash file video quá lớn gây chậm ➔ Khắc phục: Hash theo kích thước + timestamp + 64KB đầu/cuối của file video.

**Rollback:** Xóa thư mục `autodub/media/inpaint/` và file test tương ứng.

---

### TASK-003 — Embedded LaMa ONNX Inpainting Engine

**Mục tiêu:**
Hiện thực hóa `LaMaOnnxEngine` sử dụng ONNX Runtime để xóa phụ đề theo vùng ROI bounding-box, đọc/ghi frame streaming qua FFmpeg pipe.

**Dependency:** TASK-002

**File được phép sửa:**
- `[NEW] autodub/media/inpaint/lama_onnx.py`
- `[NEW] tests/test_inpaint_engine.py`

**File không được sửa:**
- `autodub/pipeline.py`, `autodub/speech/*`

**Thay đổi dự kiến:**
- Khởi tạo ONNX Runtime InferenceSession với fallback provider tự động: `CUDAExecutionProvider` ➔ `DmlExecutionProvider` ➔ `CPUExecutionProvider`.
- Xử lý ROI bounding-box crop: Chỉ cắt phần khung hình chứa text đưa vào model, sau đó dán (blend) đè lại vào khung hình lớn.
- Quản lý streaming FFmpeg in/out để không ngốn RAM.
- Hỗ trợ `progress_callback` và `cancel_event`.

**Acceptance Criteria:**
- `inpaint_frame` nhận frame BGR và mask nhị phân, trả về frame đã được xóa vật thể mượt mà.
- Hỗ trợ cancel giữa chừng dọn dẹp tiến trình ffmpeg con sạch sẽ.

**Test:**
- `pytest tests/test_inpaint_engine.py` (với mock ONNX session và dummy image).

**Rủi ro:** ONNX session không tìm thấy Execution Provider trên máy test ➔ Tự động fallback về CPU.

**Rollback:** Revert commit TASK-003.

---

### TASK-004 — VSR Bridge Adapter & Preflight Check

**Mục tiêu:**
Hiện thực hóa `VSRBridgeEngine` để gọi CLI/Docker bên ngoài của `video-subtitle-remover` và hàm kiểm tra môi trường trong `preflight.py`.

**Dependency:** TASK-002

**File được phép sửa:**
- `[NEW] autodub/media/inpaint/vsr_bridge.py`
- `autodub/preflight.py`

**File không được sửa:**
- `autodub/media/subtitle.py`, `autodub/speech/*`

**Thay đổi dự kiến:**
- `vsr_bridge.py`: Dựng command line gọi `python backend/main.py -i <in> -o <out> -c <coords>` tới thư mục VSR ngoài.
- `preflight.py`: Bổ sung hàm `check_inpaint_env()` kiểm tra model ONNX và ONNX Runtime provider khả dụng.

**Acceptance Criteria:**
- Báo rõ trạng thái: Có GPU CUDA không, có file model không, có thể chạy AI Inpaint hay cần fallback về Boxblur.

**Test:**
- `tests/test_inpaint_preflight.py`

**Rủi ro:** Subprocess treo nếu VSR ngoài đợi input ➔ Đặt timeout và ngắt stdout/stderr non-blocking.

**Rollback:** Revert commit TASK-004.

---

### TASK-005 — Tích hợp Video Rendering & Pipeline

**Mục tiêu:**
Tích hợp `inpaint_video_with_cache` vào `render_final_video` (`autodub/media/video.py`) và luồng chạy của `autodub/pipeline.py`.

**Dependency:** TASK-003, TASK-004

**File được phép sửa:**
- `autodub/media/video.py`
- `autodub/pipeline.py`
- `[NEW] tests/test_video_render_inpaint.py`

**File không được sửa:**
- `autodub/speech/*`, `autodub/text/*`

**Thay đổi dự kiến:**
- `video.py`: Nếu `mask_method == "ai_inpaint"`, gọi `inpaint_video_with_cache` để tạo `clean_video.mp4`, sau đó chuyển sang `build_filter_complex` với `blur_regions = []`.
- `pipeline.py`: Thêm bước log `[AI-INPAINT]` và cập nhật progress bar cho stage inpaint.

**Acceptance Criteria:**
- Khi `mask_method == "blur"`: Luồng chạy không đổi 100%, chạy qua 1 pass ffmpeg boxblur.
- Khi `mask_method == "ai_inpaint"`: Video sạch được tạo ra trước, rồi render final không còn vệt boxblur.
- Re-render lần 2 dùng cache ngay lập tức (0 giây cho bước inpaint).

**Test:**
- `pytest tests/test_video_render_inpaint.py`

**Rủi ro:** Lỗi đường dẫn file tạm trên Windows ➔ Dùng `tempfile.NamedTemporaryFile` hoặc `.cache` an toàn.

**Rollback:** Revert commit TASK-005.

---

### TASK-006 — End-to-End Verification & Regression Test

**Mục tiêu:**
Chạy toàn bộ test suite của dự án, đảm bảo tính tương thích ngược 100% và viết tài liệu hướng dẫn sử dụng.

**Dependency:** TASK-005

**File được phép sửa:**
- `.artifacts/walkthrough.md`
- `docs/` (nếu cần)

**Acceptance Criteria:**
- Toàn bộ unit test cũ và mới đều PASS.
- Không có breaking change trên bất kỳ module nào khác.

---

## 3. Thứ tự thực hiện

1. `TASK-001`: Config & Data Model.
2. `TASK-002`: Inpaint Base & Cache Manager.
3. `TASK-003`: LaMa ONNX Engine.
4. `TASK-004`: VSR Bridge Adapter & Preflight.
5. `TASK-005`: Video & Pipeline Integration.
6. `TASK-006`: E2E Verification & Regression Test.

---

## 4. Change Budget

- Tổng số file mới: 6 files (`autodub/media/inpaint/*.py`, test files).
- Tổng số file sửa đổi: 4 files (`config.py`, `editor.py`, `video.py`, `pipeline.py`, `preflight.py`).
- Giới hạn dòng code thêm mới: ~600-800 lines.
- Tác động tới core pipeline cũ: Rất nhỏ (< 30 dòng điều hướng luồng).

---

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT TASK`
