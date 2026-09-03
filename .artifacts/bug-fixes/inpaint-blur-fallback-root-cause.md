# Root Cause Analysis: Video xuất ra vẫn bị làm mờ Boxblur dù đã chọn Phương thức 2 (AI Inpaint)

## 1. Bug
Người dùng cấu hình **Phương thức 2 (Xóa sạch AI Inpainting)** trong hộp thoại Tùy biến kiểu phụ đề (`mask_method = "ai_inpaint"`), nhưng video xuất ra thực tế vẫn chỉ là làm mờ hình chữ nhật cơ bản (Boxblur / Smudge).

## 2. Reproduction & Evidence
- **Kiểm tra file weights:** Thư mục `models/inpaint/` và file `models/inpaint/lama.onnx` chưa tồn tại trên đĩa (`os.path.exists('models/inpaint/lama.onnx') == False`).
- **Phân tích mã nguồn:** Trong [`autodub/media/inpaint/lama_onnx.py`](file:///d:/Project/lphvsub-main/autodub/media/inpaint/lama_onnx.py#L47-L54):
  Khi không tìm thấy file weights `lama.onnx`, `LaMaOnnxEngine` không khởi tạo được session ONNX và tự động rơi vào nhánh:
  ```python
  if self._session is None:
      import cv2
      mask_uint8 = (mask > 0).astype(np.uint8) * 255
      kernel = np.ones((3, 3), np.uint8)
      mask_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
      return cv2.inpaint(frame_bgr, mask_dilated, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
  ```
- **Hành vi thực tế:** Thuật toán `cv2.INPAINT_TELEA` với vùng chữ nhật phụ đề rộng chỉ nội suy màu các điểm ảnh ở biên vào tâm, tạo thành một vệt mờ nhòe (smudge) nhìn không khác gì bộ lọc làm mờ (Boxblur).
- **Vấn đề tương thích kích thước:** Các model LaMa ONNX chuẩn (như `Carve/LaMa-ONNX` `lama_fp32.onnx` ~208MB) có kích thước cố định `512x512`. Code cũ của `lama_onnx.py` chỉ làm tròn kích thước theo bội số của 8 (`(8 - h % 8) % 8`), do đó nếu nạp model `512x512` sẽ bị lỗi Shape Mismatch và `merge_video` sẽ catch exception rồi fallback hẳn về Boxblur.
- **Thiếu script cài đặt:** Chưa có `scripts/setup_inpaint.py` và `cai_them_inpaint.bat` trong bộ cài của dự án.

## 3. Root Cause
1. **Thiếu weights model AI LaMa:** Chưa có cơ chế tải tự động model LaMa ONNX về `models/inpaint/lama.onnx`.
2. **Khả năng thích ứng kích thước tensor:** `LaMaOnnxEngine.inpaint_frame` cần hỗ trợ tự động scale/pad patch về đúng input shape của mô hình (ví dụ 512x512) và unscale/crop trả về đúng kích thước frame gốc.
3. **Thiếu script tải độc lập:** Cần cung cấp script `scripts/setup_inpaint.py` và `cai_them_inpaint.bat` để người dùng hoặc hệ thống tải model chỉ bằng 1 lệnh.

## 4. Proposed Fix
1. **Thêm `scripts/setup_inpaint.py`:** Tự động tải `lama.onnx` (~208MB) từ Hugging Face mirror (`https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx`) với thanh tiến độ, SHA256 validation và retry.
2. **Thêm `cai_them_inpaint.bat`:** Script Windows 1-click để cài đặt model AI Inpaint.
3. **Nâng cấp `autodub/media/inpaint/lama_onnx.py`:**
   - Xử lý dynamic và fixed input size (512x512): tự động resize patch/mask sang `(target_w, target_h)`, chạy inference ONNX, rồi resize kết quả trở lại kích thước gốc trước khi dán mask.
   - Thêm auto-download nếu người dùng chạy mà chưa có model (hoặc hướng dẫn rõ ràng).
4. **Viết unit test & regression test:** Đảm bảo test độ phân giải bất kỳ, test mock session, test fallback, test preflight check.
