# Dynamic Moving Watermark Design Spec

> **Feature:** Watermark chìm di chuyển tự do / chạy xung quanh khung hình video (Dynamic Bouncing Watermark)
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goal)

Cung cấp tính năng Watermark bản quyền chìm chạy chuyển động quanh khung hình video (cả dạng chữ động `drawtext` và dạng hình ảnh logo `overlay` chuyển động). Watermark di chuyển liên tục theo quỹ đạo nảy 2D mượt mà (`bounce` / `float`) hoặc nhảy chu kỳ (`stealth jump`) với độ trong suốt tùy chỉnh ($10\% - 40\%$), giúp chống reup / cắt ghép video bản quyền mà không làm che khuất trải nghiệm xem của khán giả.

---

## 2. Thiết kế Kỹ thuật (Technical Design)

### 2.1. Tầng FFmpeg Filter Engine (`autodub/media/subtitle.py`)

#### A. Chuyển động Bouncing (Nảy 2D quanh khung hình)
Sử dụng công thức toán học hàm tuần hoàn tam giác / sóng nảy trong FFmpeg:
- Tọa độ $X(t)$:
  $$X(t) = \text{margin} + \left| \left( (t \cdot s_x) \pmod{2 \cdot W_{\text{bound}}} \right) - W_{\text{bound}} \right|$$
  với $W_{\text{bound}} = W_{\text{video}} - W_{\text{element}} - 2 \cdot \text{margin}$.
- Tọa độ $Y(t)$:
  $$Y(t) = \text{margin} + \left| \left( (t \cdot s_y) \pmod{2 \cdot H_{\text{bound}}} \right) - H_{\text{bound}} \right|$$
  với $H_{\text{bound}} = H_{\text{video}} - H_{\text{element}} - 2 \cdot \text{margin}$.

#### B. Text Watermark chuyển động (`drawtext`)
Khi có `watermark_text`:
```
drawtext=text='@TenKenh':fontsize=28:fontcolor=white@0.28:x='24+abs(mod(t*45,2*(w-tw-48))-(w-tw-48))':y='24+abs(mod(t*32,2*(h-th-48))-(h-th-48))'
```
Có bóng mờ nhẹ hoặc viền nhẹ để dễ nhìn trên mọi nền sáng/tối.

#### C. Logo ảnh chuyển động (`overlay` motion)
Nếu logo có `logo_motion == "bounce"`:
```
[current][logo]overlay=x='24+abs(mod(t*45,2*(main_w-overlay_w-48))-(main_w-overlay_w-48))':y='24+abs(mod(t*32,2*(main_h-overlay_h-48))-(main_h-overlay_h-48))'[vlogo]
```

### 2.2. Tầng Cấu hình & Pipeline

- **`Settings` & `DubRequest`**:
  - `watermark_text: str = ""` (Chuỗi chữ watermark, ví dụ `@KênhCủaBạn`)
  - `watermark_opacity: float = 0.28` (Độ mờ chìm $0.10 - 0.60$)
  - `watermark_font_size: int = 26` (Cỡ chữ)
  - `watermark_color: str = "#FFFFFF"` (Màu chữ)
  - `watermark_speed: int = 40` (Tốc độ pixel/giây)
  - `watermark_motion: str = "bounce"` (`"bounce"`, `"static"`)

### 2.3. Tầng Giao diện Người dùng (GUI)

- **Trang Cài đặt (`settings_fields.py`)**: Thêm các trường cấu hình Watermark chữ chìm trong Thẻ Nâng cao.
- **Trình tạo dự án mới (`new_project_steps.py` - Bước 4: Giọng & Phụ đề)**:
  - Thêm khối `Watermark chữ chìm chuyển động`:
    - Ô nhập chữ watermark (ví dụ: `@KênhCủaTôi`)
    - Chọn kiểu chuyển động (Nảy quanh video / Cố định góc)
    - Thanh trượt độ mờ chìm (10% - 60%) và tốc độ chạy.
