# Integrated Logo & Watermark in StyleDialog Design Spec

> **Feature:** Tích hợp Cấu hình & Xem trước Trực quan Logo / Watermark vào StyleDialog (Phụ đề & Che chữ)
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goals)

Gom toàn bộ các yếu tố đồ họa đè lên video vào một nơi duy nhất trực quan và mạnh mẽ — Hộp thoại `StyleDialog` ("Phụ đề & che chữ"):
1. **Kiểu chữ & Phụ đề** (Typography, Colors, Effects, Karaoke).
2. **Vùng làm mờ** (Multiple Blur Regions, Quick Presets, Auto-detect).
3. **Logo & Watermark Chống Reup** (Logo thương hiệu & Watermark chữ chìm chuyển động, hỗ trợ tải ảnh, chỉnh vị trí, kích thước, độ mờ, tốc độ và xem trước trực tiếp trên Canvas video).

---

## 2. Thiết kế Giao diện (UI Layout)

### 2.1. Cấu trúc Tab bên phải
Sử dụng `QTabWidget` 3 thẻ hiện đại:
- **Thẻ 1: `Kiểu chữ`**: Trọn bộ tùy chỉnh phông chữ, màu sắc, viền, vị trí, hộp nền, cách ngắt dòng, hiệu ứng karaoke.
- **Thẻ 2: `Vùng che (Blur)`**: Bộ nút tạo mẫu che nhanh (+ Dải đáy, + Dải đỉnh, + Góc phải, + Góc trái), danh sách vùng đánh số thứ tự, nút Dò tự động, Xoá vùng chọn, Xoá tất cả.
- **Thẻ 3: `Logo & Watermark`**:
  - Nhóm **Logo thương hiệu**: Bật/tắt logo, chọn tệp ảnh, vị trí góc, kích thước ($4\%-40\%$), độ rõ ($10\%-100\%$), hiệu ứng tĩnh / bouncing.
  - Nhóm **Watermark chống reup**: Bật/tắt watermark chữ chìm, nội dung chữ (@Kenh, SĐT...), kiểu chuyển động (nảy 4 góc / cố định), độ mờ chìm ($8\%-60\%$), cỡ chữ ($14-72\text{px}$), tốc độ chạy ($10-150\text{px/s}$).

### 2.2. Vẽ trực quan trên `_FrameCanvas`
- **Logo Preview**: Nếu có ảnh logo (hoặc tệp logo đã chọn), vẽ ảnh logo với kích thước và độ trong suốt tương ứng ở góc đã chọn trên Canvas.
- **Watermark Preview**: Vẽ dòng chữ watermark mờ chìm với kích thước và độ mờ thực tế.
- Khi người dùng thay đổi bất kỳ thông số nào trong thẻ `Logo & Watermark`, Canvas lập tức vẽ lại (`update()`) trong thời gian thực.
