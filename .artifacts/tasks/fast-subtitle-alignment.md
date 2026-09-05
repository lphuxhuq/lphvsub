# TASK BREAKDOWN: TĂNG TỐC CANH PHỤ ĐỀ KHỚP GIỌNG (FAST SUBTITLE VOICE-SYNC)

## 1. Dependency Graph

```
TASK-001 (Persistent MD5 Cache & Greedy Beam Size=1 trong align.py)
   │
   ▼
TASK-002 (Tích hợp Alignment Model Singleton vào GlobalModelPool & Preloader)
   │
   ▼
TASK-003 (Acoustic Fast-Path cho câu ngắn ≤ 0.6s & CPU Worker Scaling)
   │
   ▼
TASK-004 (Kiểm thử hồi quy, Benchmark tốc độ thực tế & Cập nhật tài liệu)
```

---

## 2. Danh sách Unit

### TASK-001 — Persistent MD5 Cache & Greedy Beam Size=1 trong `align.py`
- **Mục tiêu:** Thay thế hàm `hash()` dễ trôi bằng `hashlib.md5()`, đồng thời chuyển `beam_size=2` thành `beam_size=1` cho chế độ greedy ASR trên audio TTS studio sạch.
- **Dependency:** Không.
- **File được phép sửa:** `autodub/speech/align.py`, `tests/test_ass_karaoke.py`.
- **File không được sửa:** `autodub/speech/boundaries.py`, `autodub/media/timing.py`.
- **Thay đổi dự kiến:**
  - Dùng `hashlib.md5(text.encode('utf-8')).hexdigest()[:12]` trong `key`.
  - Cấu hình `beam_size=1` trong `_asr_words`.
- **Acceptance Criteria:**
  1. Key cache hoàn toàn nhất quán giữa các phiên process khác nhau.
  2. Thời gian chạy `_asr_words` giảm ít nhất 35-50%.
  3. Mốc thời gian xuất ra vẫn đạt độ chuẩn xác từng chữ.
- **Test:** `pytest tests/test_ass_karaoke.py`.
- **Rủi ro:** Không có rủi ro thuật toán.

---

### TASK-002 — Tích hợp Alignment Model Singleton vào `GlobalModelPool` & Preloader
- **Mục tiêu:** Nạp trước mô hình Whisper Alignment và duy trì singleton instance trong bộ nhớ, loại bỏ 2-3s cold start mỗi lần xuất video/preview.
- **Dependency:** TASK-001.
- **File được phép sửa:** `autodub/model_preloader.py`, `autodub/speech/align.py`, `tests/test_model_preloader.py`.
- **File không được sửa:** `autodub/media/*`.
- **Thay đổi dự kiến:**
  - Thêm `get_align_model()` vào `GlobalModelPool` trả về `(model, device, workers)`.
  - `_load_align_model()` trong `align.py` sẽ kiểm tra singleton trước khi nạp mới.
  - Tích hợp vào luồng `preload_all_async` sau các model chính.
- **Acceptance Criteria:**
  1. Khi gọi `align_segments()`, nếu model đã có trong pool thì không tốn thời gian khởi tạo (0ms load latency).
  2. Model được giải phóng sạch khi ứng dụng đóng.
- **Test:** `pytest tests/test_model_preloader.py`.

---

### TASK-003 — Acoustic Fast-Path cho câu ngắn & CPU Worker Scaling
- **Mục tiêu:** Với các câu cực ngắn ($\le 0.6$s hoặc $\le 2$ từ), chuyển thẳng sang `acoustic_word_times` (0.2ms) thay vì gọi Whisper; đồng thời scale số luồng CPU lên tối đa khả năng máy.
- **Dependency:** TASK-001.
- **File được phép sửa:** `autodub/speech/align.py`, `autodub/text/ass_karaoke.py`.
- **File không được sửa:** `autodub/media/vocal_separator.py`.
- **Thay đổi dự kiến:**
  - Thêm điều kiện bypass Whisper với câu cực ngắn trong `align_segments()`.
  - Tối ưu `_align_workers()` lên `max(1, min(8, (os.cpu_count() or 4) - 1))`.
- **Acceptance Criteria:**
  1. Các câu ngắn như "Ừ", "Đúng vậy", "Chào bạn" được xử lý trong < 1ms.
  2. Số worker đa luồng CPU tận dụng tốt CPU đa nhân.
- **Test:** `pytest tests/test_ass_karaoke.py`.

---

### TASK-004 — Kiểm thử hồi quy, Benchmark tốc độ thực tế & Cập nhật tài liệu
- **Mục tiêu:** Chạy toàn bộ test suite (71+ bài test), benchmark so sánh tốc độ trước và sau, ghi báo cáo đánh giá hoàn tất.
- **Dependency:** TASK-001, TASK-002, TASK-003.
- **File được phép sửa:** `docs/*`, `.artifacts/reviews/*`.
- **Acceptance Criteria:**
  1. 100% bài test PASS, không hồi quy.
  2. Đo đạc số liệu tốc độ thực tế trước/sau.
- **Test:** Chạy toàn bộ test suite.

---

## 3. Thứ tự thực hiện
`TASK-001` $\rightarrow$ `TASK-002` $\rightarrow$ `TASK-003` $\rightarrow$ `TASK-004`.

## 4. Change Budget
- Tổng số file sửa: $\le 4$ files.
- Tổng số dòng thêm/sửa: $\le 150$ dòng.

---

## Approval Gate
TRẠNG THÁI: CHỜ DUYỆT TASK
