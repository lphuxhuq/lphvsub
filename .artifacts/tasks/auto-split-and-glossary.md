# TASK BREAKDOWN: AUTO-SPLITTER & HARD-LOCK GLOSSARY

- **Trạng thái**: `TRẠNG THÁI: CHỜ DUYỆT TASK`
- **Mục tiêu**: Bổ sung 2 tính năng thực chiến cực mạnh cho người dùng làm nội dung: Tự động chia nhỏ video (Auto-Splitter) và Khóa cứng từ điển dịch thuật (Hard-Lock Glossary).
- **Nguyên tắc**: Bám sát kiến trúc hiện tại, không đập phá luồng core, bổ sung bằng các hàm tiện ích gọi ở cuối/đầu chu trình. Không làm chậm tốc độ render.

---

## 1. Dependency Graph

```text
TASK-001 (UI/UX cho Auto-Split và Dictionary)
   │
   ├─► TASK-002 (Hard-Lock Glossary Pre-processor trong Dịch thuật)
   │
   └─► TASK-003 (Auto-Splitter Engine chạy sau khi xuất Video)
```

---

## 2. Danh sách Unit

### TASK-001 — Cập nhật Giao diện (GUI)
- **Mục tiêu:** Thêm các điều khiển trên GUI để người dùng bật/tắt tính năng.
- **File được phép sửa:** `autodub_gui/pages/new_project_steps.py`, `autodub_gui/pages/editor_export.py`, `autodub/pipeline.py` (DubRequest).
- **Thay đổi dự kiến:**
  1. Trong thẻ **Dịch thuật** (TranslateStep), thêm một `QPlainTextEdit` (hoặc TextBox) tên là `Tự điển ép dịch (Hard-Lock Dictionary)`. Gợi ý (placeholder): `林动 = Lâm Động\n异火 = Dị Hỏa`.
  2. Trong thẻ **Xuất Video** (ExportPanel) của giao diện Editor và `NewProjectPage`, thêm tuỳ chọn `[x] Tự động chia nhỏ video để đăng TikTok/Shorts (mỗi 10 phút)`.
  3. Cập nhật `DubRequest` để truyền các thông số này xuống Core.
- **Acceptance Criteria:** Các tuỳ chọn hiện đẹp mắt trên GUI, có tooltips giải thích rõ ràng, lưu trạng thái vào metadata dự án.

### TASK-002 — Hard-Lock Glossary Pre-processor (Core Dịch thuật)
- **Mục tiêu:** Ép AI dịch đúng tên riêng bằng kỹ thuật "Mixed-Language Prompting" (trộn từ tiếng Việt thẳng vào câu tiếng Trung trước khi gửi cho AI).
- **Dependency:** TASK-001.
- **File được phép sửa:** `autodub/text/translate_hint.py`, `autodub/text/translate_direct.py`, `autodub/text/translate_browser.py`.
- **Thay đổi dự kiến:**
  1. Thêm hàm `apply_hardlock_dictionary(text_zh, dictionary_dict)`: tìm và thay thế (replace) chữ Trung Quốc bằng chữ tiếng Việt (bọc thêm dấu cách hai đầu để AI không dính chữ).
  2. Tại lúc tạo `payload_items` trong `translate_direct.py` và `translate_browser.py`, áp dụng hàm này lên biến `text` trước khi đẩy vào JSON gửi đi.
- **Acceptance Criteria:**
  - AI nhận được câu trộn: "Tên tôi là Lâm Động, tôi có Dị Hỏa." (thay vì toàn bộ tiếng Trung).
  - Không làm thay đổi file `transcript_original.json` lưu trên ổ đĩa (chỉ thay ở luồng bay lên API).
  - Hoạt động trơn tru trên cả Gemini Direct và AI Studio.

### TASK-003 — Auto-Splitter Engine (Core Video)
- **Mục tiêu:** Tự động cắt video gốc (2-3 tiếng) thành các part 10 phút ngay sau khi `merge_video` chạy xong, cắt chuẩn xác vào điểm ngắt câu (không cắt cụt tiếng).
- **Dependency:** TASK-001.
- **File được phép sửa:** `autodub/pipeline.py`, tạo mới `autodub/media/auto_split.py`.
- **Thay đổi dự kiến:**
  1. Xây dựng thuật toán trong `auto_split.py`:
     - Nhận vào `video_path`, `segments` array, `chunk_duration_s=600`.
     - Duyệt `segments`, cộng dồn thời gian. Khi vượt quá 600s, tìm khoảng hở `min_gap` giữa câu hiện tại và câu tiếp theo để làm điểm cắt (split point).
     - Chạy `ffmpeg -i ... -ss start -to end -c copy part_X.mp4` để trích xuất không giảm chất lượng (chạy mất 2 giây/phần).
  2. Kích hoạt trong `pipeline.py` ở cuối bước 7 (sau khi `merge_video` báo done).
- **Acceptance Criteria:**
  - Thuật toán tìm đúng điểm im lặng giữa các câu thoại để cắt.
  - Video xuất ra được đánh số `dubbed_video_part_1.mp4`, `part_2.mp4`...
  - Nhanh tuyệt đối nhờ cơ chế `-c copy` stream copy của FFmpeg (không encode lại).

---

## 3. Thứ tự thực hiện

1. Làm TASK-001: Khởi tạo UX trên GUI và luồng dữ liệu (DubRequest).
2. Làm TASK-002: Đắp logic thay thế từ điển vào luồng Dịch thuật.
3. Làm TASK-003: Xây dựng bộ Auto-Splitter bằng FFmpeg stream copy ở chặng cuối.

## 4. Change Budget

- Thêm 1 file mới `autodub/media/auto_split.py` (~60 dòng).
- Chỉnh sửa nhẹ các UI Step và Dialogs (~30 dòng).
- Bổ sung logic Regex Replace vào mảng dịch thuật (~15 dòng).
- Rủi ro cực thấp vì các chức năng này hoàn toàn tuỳ chọn (Opt-in), nếu tắt đi thì luồng cũ chạy không ảnh hưởng 1 bit nào.

---

`TRẠNG THÁI: CHỜ DUYỆT TASK`
