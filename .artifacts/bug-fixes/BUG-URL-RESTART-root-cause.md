# Root Cause Analysis — Bug: Nhập lại link chạy lại từ đầu dù đã có dự án cũ

**Mã lỗi:** `BUG-URL-RESTART`  
**Ngày phát hiện:** 06/09/2026  
**Mức độ nghiêm trọng:** HIGH (Gây lãng phí thời gian hàng giờ, chạy trùng lặp Demucs, ASR và tiêu tốn quota dịch API/TTS)  
**Trạng thái:** CHỜ DUYỆT NGUYÊN NHÂN  

---

## 1. Mô tả sự cố (Issue Description)
Khi người dùng nhập lại một liên kết video (YouTube / Bilibili / Douyin / TikTok) mà liên kết này **đã từng chạy hoặc đang làm dở** ở các bước trước đó (đã tách nhạc Demucs, đã nhận diện ASR, đã dịch xong 948 câu, đã sinh TTS), ứng dụng không nhận diện được dự án cũ. Thay vào đó, hệ thống tự động tạo một thư mục timestamp mới và chạy lại từ đầu toàn bộ các bước tốn kém (tải video, tách nhạc Demucs ~5-10 phút, Whisper/Paraformer ASR, gọi API dịch tự động, tổng hợp giọng đọc TTS).

---

## 2. Bằng chứng thực tế từ Log (Evidence from Runtime Logs)

Theo log `logs/voxdub.log.2026-09-05`:
1. **Lần chạy 1 (20:32:15):**
   - URL: `https://www.bilibili.com/video/BV1X4t865ECX/`
   - Thư mục dự án: `output/VN/20260905203215_vi`
   - Đã hoàn thành 100%: Tách audio HQ, Demucs, ASR, Dịch 948 câu, TTS 948 câu, Hòa trộn âm thanh 7253.5s (`audio_vi_full.wav`).
2. **Lần chạy 2 (22:34:36 - chỉ 2 tiếng sau):**
   - Người dùng dán lại cùng URL: `https://www.bilibili.com/video/BV1X4t865ECX/`
   - Hệ thống tạo mới: `output/VN/20260905223451_vi`
   - Chạy lại từ đầu:
     - Chạy lại Demucs mất **5 phút 20 giây** (từ 22:34:57 đến 22:40:18).
     - Chạy lại Paraformer ASR từ đầu (948 câu).
     - Gọi dịch lại và tổng hợp lại âm thanh.

---

## 3. Phân tích nguyên nhân gốc rễ (Root Cause Analysis)

### Điểm nghẽn 1: Giao diện Wizard ép `resume_dir = None` khi ở tab "Dán liên kết"
- **Vị trí:** `autodub_gui/pages/new_project_page.py` (hàm `_build_request`, dòng 817)
- **Cơ chế hiện tại:**
  ```python
  return DubRequest(
      url=data["url"] if source == "url" else None,
      file_path=...,
      resume_dir=data["resume_dir"] if source == "resume" else None,
  )
  ```
  Khi người dùng ở chế độ dán link (`source == "url"`), `resume_dir` luôn luôn là `None`.
- Giao diện không có bộ lắng nghe khi dán link để tự động tra cứu xem URL này đã có sẵn dự án tương ứng trong thư mục `output/` hay chưa. Người dùng muốn tiếp tục buộc phải tự bấm qua tab "Tiếp tục dang dở" và tự duyệt tìm thư mục bằng tay.

### Điểm nghẽn 2: Dữ liệu URL không được lưu vào dự án ở các bước sớm
- **Vị trí:** `autodub/pipeline.py` (hàm `_resolve_video` và `_run_impl`)
- Khi bắt đầu chạy, file `data/source_video.json` chỉ lưu duy nhất đường dẫn file tạm:
  ```json
  {"file_path": "C:\\Users\\...\\voxdub_prefetch\\BV1X4t865ECX.mp4"}
  ```
  Thông tin `url` không được ghi nhận vào `source_video.json` hay `render_opts.json`.
- `url` chỉ được ghi vào `export_state.json` (sau khi xong Step 6) và `report.json` (sau khi xong Step 8). Do đó, những dự án dừng ở Step 2, 3, 4, 5 không có metadata chuẩn về URL để tra cứu ngược.

### Điểm nghẽn 3: Pipeline luôn sinh thư mục timestamp mới khi thiếu `resume_dir`
- **Vị trí:** `autodub/pipeline.py` (dòng 354–366)
- **Cơ chế hiện tại:**
  ```python
  if req.resume_dir:
      work_dir = req.resume_dir
  else:
      output_dir = req.output_dir or self.default_output_dir(target)
      base_folder = datetime.now().strftime("%Y%m%d%H%M%S")
      candidate = f"{base_folder}{target.folder_suffix}"
      work_dir = ensure_dir(full_path)
  ```
  Pipeline không có hàm `find_existing_project_by_url(output_dir, url)`. Dù video đã tải, audio đã tách, transcript và TTS đã có đầy đủ ở thư mục trước đó, pipeline vẫn tạo thư mục mới toanh và chạy lại từ đầu.

---

## 4. Kết luận
Nguyên nhân gốc rễ là do **thiếu cơ chế tự động liên kết URL với dự án đã tồn tại**:
1. Pipeline không ghi nhận `url` vào metadata dự án ngay từ Step 1.
2. Wizard không kiểm tra URL khi dán để tự động gợi ý/kết nối `resume_dir`.
3. Pipeline mặc định sinh thư mục timestamp mới mà không kiểm tra trùng lặp URL trong `output_dir`.

---
**TRẠNG THÁI: CHỜ DUYỆT NGUYÊN NHÂN**
