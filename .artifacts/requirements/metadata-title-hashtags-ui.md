# Phân tích yêu cầu: Hiển thị Tiêu đề & Hashtag kèm Nút Sao chép và Nhận diện Video trên Giao diện Tool

- **Feature**: `metadata-title-hashtags-ui`
- **Ngày phân tích**: 2026-09-01
- **Trạng thái**: CHỜ DUYỆT PHÂN TÍCH

---

## 1. Mục tiêu (Objective)

Khi hệ thống tạo xong Tiêu đề (Title), Mô tả (Description) và Hashtags cho video (từ AI Content Generator / AI Studio Translation / Gemini SRT UI):
1. **Hiển thị trực quan ngay trên giao diện Tool**: Không bắt người dùng phải mở thư mục tìm file `.txt` hay `.json`.
2. **Nút sao chép 1-chạm (One-Click Copy)**: Cung cấp các nút sao chép riêng biệt cho Tiêu đề, Hashtags, và Toàn bộ (Title + Description + Tags).
3. **Phân biệt rõ ràng theo từng video**: Hiển thị rõ tên video / ID dự án tương ứng với bộ Tiêu đề & Hashtag đó để người dùng không bị nhầm lẫn khi xử lý hàng loạt video.

---

## 2. User Story

- **Là**: Nhà sáng tạo nội dung / Người dùng lphvsub
- **Tôi muốn**: Xem ngay tiêu đề và danh sách hashtag vừa được AI tạo cho từng video ngay trên màn hình tool và có nút bấm sao chép nhanh vào clipboard
- **Để**: Tôi có thể đăng ngay lên YouTube, TikTok, Facebook Reels một cách thuận tiện và chính xác cho từng video mà không bị nhầm lẫn giữa các video trong danh sách.

---

## 3. Yêu cầu chức năng (Functional Requirements)

- **FR-01 (Hiển thị thẻ Metadata trên Giao diện Web `gemini_srt_ui`)**:
  - Khi hoàn thành dịch / tạo nội dung cho từng file video/SRT, hiển thị khối **"🏷️ Tiêu đề & Hashtags Video"**.
  - Hiển thị rõ:
    - 🎥 **Tên file / Video**: Ví dụ `video_tap_1.mp4`.
    - 📌 **Tiêu đề**: Hiển thị text tiêu đề tiếng Việt nổi bật.
    - 🏷️ **Hashtags**: Hiển thị dạng tags/badges gọn gàng, đẹp mắt.
    - 📋 **Các nút sao chép**:
      - `📋 Chép Tiêu đề`
      - `🏷️ Chép Hashtags`
      - `📄 Chép Toàn bộ` (Tiêu đề + Mô tả + Hashtags).
  - Hỗ trợ xem và chuyển đổi giữa các video khi chạy chế độ Hàng loạt (Batch).

- **FR-02 (Hiển thị thẻ Metadata trên Giao diện Desktop `autodub_gui`)**:
  - Trên trang Xuất bản / Dự án ([editor_export.py](file:///d:/Project/lphvsub-main/autodub_gui/pages/editor_export.py) và trang Hoàn thành):
    - Hiển thị trực tiếp Header tên Video đang chọn.
    - Hiển thị khung xem trước Tiêu đề & Hashtags kèm các nút sao chép nhanh (`Copy Title`, `Copy Tags`, `Copy All`).
    - Thông báo Toast hiển thị tức thì khi sao chép thành công.

- **FR-03 (API & Endpoint dữ liệu metadata)**:
  - Cập nhật API backend của `gemini_srt_ui` (`/api/status/<job_id>`) để trả về `social_meta` (gồm `title`, `description`, `hashtags`, `filename`, `tiktok`, `facebook`) khi hoàn tất.

---

## 4. Yêu cầu phi chức năng (Non-Functional Requirements)

- **NFR-01 (UX & Visual Design)**: Thiết kế giao diện hiện đại, chuẩn Dark Mode / Glassmorphism, nút bấm có phản hồi thị giác khi click (chuyển sang "✓ Đã chép!" trong 1.5s).
- **NFR-02 (Hiệu năng)**: Không làm chậm quá trình render giao diện, dữ liệu metadata được nạp đồng bộ với tiến trình job.
- **NFR-03 (Tương thích)**: Hỗ trợ Clipboard API trên cả trình duyệt Web (HTTPS / localhost / fallback execCommand) và PySide6 Clipboard trên Desktop.

---

## 5. Module bị ảnh hưởng

1. `autodub/tools/gemini_srt_ui/static/index.html`: Thêm component hiển thị Metadata Card, Badge Hashtags, nút Copy.
2. `autodub/tools/gemini_srt_ui/app.py`: Trả về `social_meta` trong status endpoint và websocket/polling.
3. `autodub_gui/pages/editor_export.py`: Nâng cấp giao diện hiển thị tên video, tiêu đề, hashtags trực quan và nút copy 1-chạm.

---

## 6. Edge Cases

- **File dịch thủ công không có metadata**: Hiển thị thông báo "Chưa có metadata AI" kèm nút "Tạo lại nội dung AI".
- **Chạy hàng loạt 20+ video**: Mỗi video có một Card metadata riêng biệt có tiêu đề video rõ ràng, hoặc danh sách Accordion phân theo từng video.
- **Hashtags rỗng hoặc chứa ký tự đặc biệt**: Tự động chuẩn hóa thành chuỗi `#tag1 #tag2` liền mạch trước khi copy.

---

## 7. Tiêu chí nghiệm thu (Acceptance Criteria)

- **AC-01**: Khi job tạo xong trên `gemini_srt_ui`, màn hình hiển thị ngay tên video, tiêu đề và hashtags.
- **AC-02**: Bấm nút `📋 Chép Tiêu đề` $\rightarrow$ Clipboard chứa đúng tiêu đề của video đó, nút chuyển sang `✓ Đã chép!`.
- **AC-03**: Bấm nút `🏷️ Chép Hashtags` $\rightarrow$ Clipboard chứa danh sách hashtags cách nhau bằng dấu cách (`#tag1 #tag2`).
- **AC-04**: Bấm nút `📄 Chép Toàn bộ` $\rightarrow$ Clipboard chứa toàn bộ Tiêu đề + Mô tả + Hashtags.
- **AC-05**: Khi xử lý nhiều video hàng loạt, mỗi video hiển thị đúng tên file gốc và nội dung metadata tương ứng, không bị nhầm lẫn.

---

## 8. Ngoài phạm vi (Out of Scope)

- Tự động đăng tải (Auto-upload) trực tiếp lên kênh YouTube/TikTok (người dùng sẽ sao chép và đăng thủ công hoặc qua tool quản lý kênh).

---

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
