# Danh sách Task: Hiển thị Tiêu đề & Hashtags trên Giao diện Tool kèm Nút Sao chép và Phân biệt Video

- **Feature**: `metadata-title-hashtags-ui`
- **Ngày lập task**: 2026-09-01
- **Dựa trên**: Design tại [.artifacts/designs/metadata-title-hashtags-ui.md](file:///d:/Project/lphvsub-main/.artifacts/designs/metadata-title-hashtags-ui.md)

---

## 1. Dependency Graph

```
TASK-001 (Backend API Metadata endpoint)
    │
    ├────────────────────────┐
    ▼                        ▼
TASK-002 (Web UI Card)   TASK-003 (Desktop GUI Card)
    │                        │
    └───────────┬────────────┘
                ▼
      TASK-004 (Integration & Verification)
```

---

## 2. Danh sách Unit Tasks

### 📌 TASK-001 — Backend API: Trả về `social_metadata` trong API Status

- **Mục tiêu**: Bổ sung trường `social_metadata` trong API `/api/status/<job_id>` và batch status của `gemini_srt_ui/app.py`.
- **Dependency**: Không.
- **File được phép sửa**:
  - `autodub/tools/gemini_srt_ui/app.py`
- **File không được sửa**:
  - `autodub/pipeline.py`
  - Các module ngoài phạm vi
- **Thay đổi dự kiến**:
  - Hàm `get_social_metadata_safe(job_info)`: Đọc `youtube_metadata.json` hoặc trích xuất từ file JSON kết quả dịch nếu có.
  - Thêm `social_metadata` vào dictionary response của `/api/status/<job_id>`.
- **Acceptance Criteria**:
  - Khi job hoàn tất có metadata, response `/api/status/<job_id>` trả về `social_metadata` chứa `filename`, `title`, `description`, `hashtags`, `hashtags_str`, `full_text`.
- **Test**: `pytest tests/test_gemini_srt_social_metadata.py`
- **Rủi ro**: Không có metadata $\rightarrow$ trả về `None`, không gây lỗi server.

---

### 📌 TASK-002 — Web UI: Thêm Card Tiêu đề & Hashtags với Nút Sao chép 1-chạm

- **Mục tiêu**: Xây dựng giao diện Thẻ Metadata hiển thị tên Video, Tiêu đề, danh sách Hashtags dạng badge và 3 nút Sao chép trực quan trên `gemini_srt_ui/static/index.html`.
- **Dependency**: TASK-001.
- **File được phép sửa**:
  - `autodub/tools/gemini_srt_ui/static/index.html`
- **File không được sửa**: Các file ngoài `gemini_srt_ui/static/`
- **Thay đổi dự kiến**:
  - Thêm phần tử HTML `#socialMetaCard` thiết kế hiện đại (Glassmorphism Dark Mode).
  - Hiển thị rõ tên video (`🎬 Video: <filename>`).
  - Hộp Tiêu đề to rõ + nút `📋 Sao chép Tiêu đề`.
  - Hộp Hashtags hiển thị từng tag bằng Pill Badge + nút `🏷️ Sao chép Hashtags`.
  - Nút `📄 Sao chép Toàn bộ`.
  - Hàm JavaScript `copyToClipboard(text, btnElement)` với hiệu ứng đổi màu và text `✓ Đã chép!` trong 1.5s.
  - Tự động cập nhật dữ liệu khi polling status job.
- **Acceptance Criteria**:
  - Khi job hoàn tất, Thẻ Metadata tự động hiển thị.
  - Bấm nút sao chép nào thì chép đúng nội dung đó vào Clipboard và có hiệu ứng phản hồi.
- **Test**: Kiểm tra manual và frontend DOM structure.

---

### 📌 TASK-003 — Desktop GUI: Nâng cấp Metadata Card & Nút Sao chép trên trang Xuất bản

- **Mục tiêu**: Hoàn thiện hiển thị tên video, hashtags dạng badge và 3 nút sao chép 1-chạm trên `autodub_gui/pages/editor_export.py`.
- **Dependency**: Không.
- **File được phép sửa**:
  - `autodub_gui/pages/editor_export.py`
- **File không được sửa**: Các file ngoài `autodub_gui/pages/`
- **Thay đổi dự kiến**:
  - Hiển thị rõ ràng tên video nguồn tương ứng.
  - Bổ sung 3 nút bấm riêng biệt: `📋 Chép Tiêu đề`, `🏷️ Chép Hashtags`, `📄 Chép Toàn bộ`.
  - Hiển thị danh sách hashtags bằng styled label/badges.
- **Acceptance Criteria**:
  - Người dùng bấm nút là sao chép được ngay vào clipboard và hiện Toast thông báo.
- **Test**: `pytest tests/test_editor_export_metadata_ui.py`

---

### 📌 TASK-004 — Integration & Verification

- **Mục tiêu**: Chạy kiểm thử tích hợp toàn bộ luồng, đảm bảo không có lỗi hồi quy.
- **Dependency**: TASK-001, TASK-002, TASK-003.
- **Acceptance Criteria**:
  - Toàn bộ test suite chạy PASS 100%.
- **Test**: `pytest tests/ -v`

---

## 3. Thứ tự thực hiện

1. Thực hiện TASK-001 (Backend API)
2. Thực hiện TASK-002 (Web UI)
3. Thực hiện TASK-003 (Desktop GUI)
4. Thực hiện TASK-004 (Integration & Verification)

---

`TRẠNG THÁI: CHỜ DUYỆT TASK`
