# Fix Design: Hỗ trợ nạp và tải mô hình LaMa ONNX cho Phương thức 2 (AI Inpaint)

## 1. Mục tiêu
- Cung cấp tính năng tự động tải model LaMa ONNX chuẩn chất lượng cao (~208MB) về `models/inpaint/lama.onnx`.
- Đảm bảo `LaMaOnnxEngine` trong `autodub/media/inpaint/lama_onnx.py` xử lý hoàn hảo cả model fixed-shape (`512x512`) và dynamic-shape, không bị lỗi mismatch shape.
- Cung cấp `scripts/setup_inpaint.py` và `cai_them_inpaint.bat`.

## 2. Files Thay Đổi & Thêm Mới
- **NEW** `scripts/setup_inpaint.py`: Script tải model LaMa ONNX từ Hugging Face có tiến độ và SHA256 checksum.
- **NEW** `cai_them_inpaint.bat`: Batch file cài đặt 1-click cho người dùng Windows.
- **MODIFY** `autodub/media/inpaint/lama_onnx.py`:
  - Phát hiện input shape của ONNX session (`[batch, 3, H, W]`).
  - Resize/scale linh hoạt nếu model có kích thước cố định như 512x512.
  - Tự động gọi download model nếu chưa có file weights khi người dùng bật AI Inpaint hoặc ghi log hướng dẫn chi tiết.
- **MODIFY** `tests/test_inpaint_engine.py`: Bổ sung test case cho dynamic/fixed shape scaling.

## 3. Quy trình Test-Driven Development (TDD)
1. Viết test case mới trong `tests/test_inpaint_engine.py` kiểm tra xử lý fixed shape 512x512.
2. Cập nhật implementation.
3. Chạy test xác thực.
4. Tải model thực tế về máy và chạy kiểm thử một video mẫu thực tế.
