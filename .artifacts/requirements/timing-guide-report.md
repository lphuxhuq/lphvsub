# Requirement Analysis: Tính năng Timing Guide / Timing Report JSON

**Mục tiêu:** Bổ sung tính năng sinh file báo cáo chi tiết thời lượng từng câu thoại (`timing_report.json` / `timing_guide.json`) sau bước TTS và căn chỉnh timeline, giúp người dùng dễ dàng kiểm tra độ lệch thời lượng giữa video gốc và tiếng lồng tiếng Việt (TTS).

---

## 1. Yêu cầu chức năng (Functional Requirements)

- **FR-1:** Sau khi tạo xong TTS các câu thoại (hoặc sau bước `apply_soft_timing`), hệ thống tự động tổng hợp và ghi file `timing_report.json` vào thư mục `data/` của dự án (hoặc thư mục kết quả).
- **FR-2:** Báo cáo bao gồm:
  - **Summary**:
    - `total_segments`: Tổng số câu thoại.
    - `original_duration`: Tổng thời lượng thoại gốc (giây).
    - `tts_duration`: Tổng thời lượng TTS tiếng Việt (giây).
    - `ratio`: Tỉ lệ thời lượng TTS / Gốc.
    - `segments_ok`: Số câu có thời lượng chuẩn (độ lệch trong ngưỡng chấp nhận ±30% hoặc theo budget).
    - `segments_need_edit`: Số câu bị lệch nhiều (quá dài hoặc quá ngắn).
  - **Segments list**: Chi tiết từng câu gồm:
    - `id`: Mã câu thoại.
    - `start`, `end`: Thời điểm bắt đầu/kết thúc trên timeline.
    - `original_duration`: Thời lượng thoại gốc.
    - `tts_duration`: Thời lượng file TTS thực tế.
    - `diff_seconds`: Chênh lệch thời lượng (`tts_duration - original_duration`).
    - `status`: `"OK"` | `"TOO_LONG"` | `"TOO_SHORT"`.
    - `edit_hint`: Gợi ý hành động ngắn gọn cho người dùng (ví dụ: `"VI dài hơn 0.7s"`, `"VI ngắn hơn 1.2s"`, hoặc `"OK"`).
    - `text_original`: Lời thoại gốc.
    - `text_target`: Lời thoại dịch (tiếng Việt).
- **FR-3:** Tương thích với `quality_report.json` hiện tại mà không làm gãy các luồng UI / Scanner đang phụ thuộc vào `quality_report.json`.

---

## 2. Yêu cầu phi chức năng (Non-Functional Requirements)

- **NFR-1 (Hiệu năng):** Thuần xử lý dữ liệu in-memory + ghi 1 file JSON nhẹ, không làm chậm pipeline (< 50ms).
- **NFR-2 (Tương thích ngược):** Không làm ảnh hưởng đến các hàm merge audio hay export video.
- **NFR-3 (Kiểm thử):** 100% test coverage cho logic tính toán và xuất báo cáo timing guide.

---

## 3. Acceptance Criteria

1. Khi chạy pipeline hoàn tất bước TTS + Soft Timing, file `timing_report.json` xuất hiện trong `data/` của work dir.
2. File chứa đầy đủ metadata `summary` và danh sách toàn bộ `segments`.
3. Từng câu hiển thị đúng `status`, `diff_seconds` và `edit_hint`.
4. Toàn bộ test suite 627+ tests tiếp tục PASS.

---

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
