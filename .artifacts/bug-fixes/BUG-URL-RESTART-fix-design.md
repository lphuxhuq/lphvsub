# Fix Design — Bug: Tự động tiếp tục dự án khi nhập lại liên kết cũ (BUG-URL-RESTART)

**Mã lỗi:** `BUG-URL-RESTART`  
**Mục tiêu:** Khi người dùng dán lại link video đã từng chạy (hoặc đang làm dở), hệ thống tự động nhận diện dự án cũ trong thư mục `output/`, tái sử dụng toàn bộ các bước đã xong (video, audio, Demucs, ASR, bản dịch, file giọng đọc TTS) thay vì chạy lại từ đầu.  
**Trạng thái:** CHỜ DUYỆT CÁCH SỬA  

---

## 1. Nguyên lý giải pháp (Ponytail: Đơn giản, triệt để, không cồng kềnh)

1. **Lưu vết URL ngay từ Step 1:**
   - Khi pipeline khởi động với `req.url`, lập tức ghi thông tin URL vào `data/source_info.json` và `data/source_video.json`.
   - Bất kỳ dự án nào dù dừng ở bất kỳ bước nào cũng sẽ mang metadata URL để tra cứu ngược.

2. **Hàm tra cứu dự án cũ theo URL (`find_existing_project_by_url`):**
   - Vị trí: `autodub/pipeline.py` (dùng chung cho cả lõi Pipeline, CLI, Batch và GUI).
   - Cơ chế so khớp thông minh:
     - So khớp URL gốc hoặc URL sau chuẩn hóa (bỏ các tham số rác như `spm_id_from`, `tracking`, `vd_source`).
     - So khớp theo Video ID (vd: Bilibili `BV1X4t865ECX`, YouTube ID 11 ký tự, Douyin ID...).
     - Quét nhanh các thư mục `*_vi` trong `output_dir` (ưu tiên thư mục mới nhất).

3. **Cơ chế Auto-Resume thông minh tại Pipeline (`autodub/pipeline.py`):**
   - Nếu `req.url` được truyền mà `req.resume_dir` chưa có:
     - Tự động gọi `find_existing_project_by_url(output_dir, req.url)`.
     - Nếu tìm thấy dự án cũ: gán `work_dir = existing_dir`, ghi log thông báo rõ ràng cho người dùng:
       `"Phát hiện dự án đã có sẵn cho liên kết này: <thư_mục> — tự động tiếp tục các bước dang dở."`
     - Các bước đã hoàn thành trong thư mục cũ (`original_audio.wav`, `no_vocals.wav`, `transcript_original.json`, `transcript_vi.json`, `segments/*.wav`) sẽ được tự động bỏ qua (skip), tiết kiệm 100% thời gian chạy lại.
     - Hỗ trợ cờ `req.force_new = True` khi người dùng chủ động muốn tạo mới hoàn toàn từ đầu.

4. **Gợi ý trực quan trên giao diện (`new_project_page.py`):**
   - Khi người dùng dán link vào ô URL, GUI lập tức tra cứu trong `output_dir`.
   - Nếu đã có dự án cũ: Hiển thị thông báo Toast / Badge màu xanh:
     `"✓ Tìm thấy dự án đã chạy trước đó: <tên_thư_mục>. Hệ thống sẽ tự động tiếp tục các bước dang dở."`
   - Gán sẵn `resume_dir` để đảm bảo đồng bộ hoàn hảo.

---

## 2. Danh sách các tệp thay đổi (Files to Modify)

| Tệp | Thay đổi chính |
| :--- | :--- |
| `autodub/pipeline.py` | 1. Thêm `find_existing_project_by_url(output_dir, url)`.<br>2. Thêm cờ `force_new: bool = False` trong `DubRequest`.<br>3. Tự động liên kết `work_dir` với dự án cũ nếu tìm thấy.<br>4. Lưu `url` vào `source_video.json` và `source_info.json` ngay Step 1. |
| `autodub_gui/pages/new_project_page.py` | Khi dán URL, kiểm tra dự án cũ và gắn `resume_dir` hoặc bật badge thông báo cho người dùng. |
| `tests/test_url_resume.py` | Thêm unit test kiểm tra tự động resume khi nhập lại URL cũ. |

---

## 3. Kế hoạch kiểm thử (Test Plan)

1. **Unit Test (`tests/test_url_resume.py`):**
   - Tạo thư mục dự án giả lập chứa `transcript_original.json` và `transcript_vi.json` với URL Bilibili/YouTube.
   - Gọi pipeline với cùng URL (không truyền `resume_dir`).
   - Xác nhận: Pipeline tự động chọn đúng thư mục cũ, không tạo timestamp mới, và không gọi ASR/Dịch lại.
   - Thử nghiệm với `force_new=True`: Xác nhận tạo thư mục mới khi được yêu cầu.
2. **Kiểm tra hồi quy (Regression Test):**
   - Chạy toàn bộ 94 unit tests hiện tại để đảm bảo không ảnh hưởng đến bất kỳ tính năng nào khác.

---

## 4. Đánh giá rủi ro (Regression Risk)
- **Rủi ro:** Cực thấp. Nếu URL chưa từng chạy, hệ thống hoạt động 100% như cũ (tạo thư mục timestamp mới).
- **An toàn dữ liệu:** Không xóa bất kỳ dữ liệu nào của dự án cũ.

---
**TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA**
