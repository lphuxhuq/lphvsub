# Task Breakdown: Timing Guide & Report System

---

## Danh sách Unit Tasks

### **TASK-1: Xây dựng hàm `build_timing_guide` & `save_timing_guide` + Unit Test**
- **Mô tả:** 
  - Triển khai logic tạo từ điển hướng dẫn/báo cáo thời lượng `build_timing_guide()` trong `autodub/media/timing.py`.
  - Triển khai hàm `save_timing_guide()` ghi file JSON vào `data/` của work dir.
  - Viết bộ unit test `tests/test_timing_guide.py` để kiểm thử logic phân loại `OK`, `TOO_LONG`, `TOO_SHORT`, các tính toán `diff_seconds`, `ratio`, `edit_hint`, và xử lý edge cases (mảng rỗng, giá trị None/0).
- **Files thay đổi:**
  - `autodub/media/timing.py` (MODIFY)
  - `tests/test_timing_guide.py` (NEW)
- **Acceptance Criteria:**
  - Chạy `pytest tests/test_timing_guide.py` đạt 100% pass.

---

### **TASK-2: Tích hợp vào `autodub/pipeline.py` & Kiểm thử luồng chạy**
- **Mô tả:**
  - Gọi `save_timing_guide()` trong `autodub/pipeline.py` sau bước TTS/Soft Timing.
  - Đảm bảo file `timing_report.json` được tạo tự động trong `data/` của work dir khi chạy pipeline.
- **Files thay đổi:**
  - `autodub/pipeline.py` (MODIFY)
- **Acceptance Criteria:**
  - Toàn bộ test suite 627+ tests chạy thành công.

---

`TRẠNG THÁI: CHỜ DUYỆT TASK`
