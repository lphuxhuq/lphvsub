# Báo cáo xử lý: Kích hoạt Phương thức 2 (AI Inpaint LaMa ONNX)

## 1. Vấn đề đã giải quyết
- **Hiện tượng cũ:** Khi chọn **Phương thức 2 (Xóa sạch AI Inpainting)**, video xuất ra vẫn chỉ là làm mờ hình chữ nhật cơ bản do thiếu file mô hình và fallback về OpenCV Telea / Boxblur.
- **Nguyên nhân gốc:**
  1. Chưa có file weights mô hình AI LaMa ONNX tại `models/inpaint/lama.onnx`.
  2. Chưa có cơ chế tải mô hình tự động và xử lý kích thước tensor linh hoạt (fixed shape 512x512 vs dynamic resolution).

## 2. Các thay đổi đã thực hiện
- **NEW** [`scripts/setup_inpaint.py`](file:///d:/Project/lphvsub-main/scripts/setup_inpaint.py): Tải tự động mô hình LaMa ONNX (~208MB) từ Hugging Face có thanh tiến độ và smoke test.
- **NEW** [`cai_them_inpaint.bat`](file:///d:/Project/lphvsub-main/cai_them_inpaint.bat): File batch 1-click cài đặt mô hình AI Inpaint cho người dùng Windows.
- **MODIFY** [`autodub/media/inpaint/lama_onnx.py`](file:///d:/Project/lphvsub-main/autodub/media/inpaint/lama_onnx.py): Tự động scale/pad patch về kích thước chuẩn của mô hình (ví dụ 512x512) và unscale/blend chính xác vào frame gốc.
- **MODIFY** [`cai_dat.bat`](file:///d:/Project/lphvsub-main/cai_dat.bat): Thêm tùy chọn `cai_them_inpaint.bat` vào menu cài đặt mở rộng.
- **MODIFY** [`tests/test_inpaint_engine.py`](file:///d:/Project/lphvsub-main/tests/test_inpaint_engine.py): Bổ sung unit test kiểm tra scaling 512x512.

## 3. Bằng chứng nghiệm thu
- **Model weights đã cài đặt:** [`models/inpaint/lama.onnx`](file:///d:/Project/lphvsub-main/models/inpaint/lama.onnx) (198.4 MB) đã sẵn sàng.
- **Smoke test:** `python scripts/setup_inpaint.py` chạy thành công (InferenceSession OK).
- **Full Test Suite:** **1015 / 1015 passed (100%)** trong 173s, không có lỗi regression.
