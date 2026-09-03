# Phân tích yêu cầu — AI Subtitle Remover Integration (Phương thức che/xóa phụ đề thứ 2)

> Feature: `ai-subtitle-remover`. Nguồn: Tích hợp công nghệ AI Inpainting từ `YaoFANGUK/video-subtitle-remover` (VSR) song song với phương thức làm mờ truyền thống (FFmpeg Boxblur). Skill: `requirement-analysis`.

---

## 1. Mục tiêu

Bổ sung **Phương thức che/xóa phụ đề thứ 2** sử dụng trí tuệ nhân tạo (**AI Inpainting**) bên cạnh phương thức số 1 hiện tại (**FFmpeg Boxblur**). 
Cho phép người dùng lựa chọn giữa:
- **Phương thức 1 (Boxblur - Nhanh):** Làm mờ vùng phụ đề bằng FFmpeg trong 1 pass encode (nhẹ, nhanh, phù hợp máy yếu).
- **Phương thức 2 (AI Inpainting - Chất lượng cao):** Tái tạo và phục hồi chi tiết nền video bị che bởi chữ (không tạo vết mờ, giữ nguyên độ phân giải, kết quả tự nhiên như video gốc chưa từng có sub).

---

## 2. User Story

- **US-01 (Creator/Editor):** Người dùng muốn lấy video gốc có dính hardsub tiếng Trung/Anh từ Douyin/TikTok/YouTube để làm video lồng tiếng Việt sạch đẹp, không bị các vệt mờ loang lổ ở đáy video.
- **US-02 (Tùy chọn linh hoạt):** Người dùng có thể chọn vùng ROI cụ thể cần xóa bằng AI (để tránh xóa nhầm logo kênh) hoặc chọn tự động quét toàn màn hình.
- **US-03 (Tối ưu hiệu năng & Cache):** Khi chỉnh sửa phụ đề dịch hoặc đổi giọng đọc TTS nhiều lần, người dùng không muốn phải đợi AI xóa phụ đề lại từ đầu cho cùng 1 video.
- **US-04 (Fallback an toàn):** Nếu máy tính không có GPU mạnh hoặc chưa cài model AI Inpaint, hệ thống sẽ cảnh báo rõ ràng và tự động chuyển về phương thức Boxblur mà không làm đứt đoạn quy trình render.

---

## 3. Functional Requirements

### Nhóm A — Data Model & Configuration
- **FR-A1**: Thêm cấu hình `subtitle_mask_mode` (hoặc `mask_method`) trong `config.py` và project metadata với các giá trị:
  - `"blur"` (Mặc định: FFmpeg Boxblur hiện tại).
  - `"ai_inpaint"` (AI Subtitle Remover Inpainting).
  - `"none"` (Không che/xóa gì).
- **FR-A2**: Bổ sung các tham số cấu hình nâng cao cho AI Inpaint:
  - `ai_inpaint_backend`: `"onnx"` | `"torch"` | `"external_cli"` (hỗ trợ gọi binary VSR pre-built).
  - `ai_inpaint_model`: `"lama"` (mặc định, tối ưu cho static background & tốc độ) | `"sttn"` (cho video phức tạp).
  - `ai_inpaint_device`: `"auto"` | `"cuda"` | `"directml"` | `"cpu"`.
  - `ai_inpaint_target`: `"roi"` (xóa theo danh sách `blur_regions` người dùng chọn) | `"auto_detect"` (tự động phát hiện text qua OCR).

### Nhóm B — AI Inpainting Engine (`autodub/media/inpaint/`)
- **FR-B1**: Xây dựng module `InpaintEngine` độc lập, tách rời hoàn toàn khỏi logic ffmpeg filter:
  - Đầu vào: `video_path`, danh sách `regions` (chuẩn hóa 0..1) hoặc cờ `auto_detect`, cấu hình phần cứng.
  - Đầu ra: `clean_video_path` (video MP4 đã xóa sub sạch sẽ).
- **FR-B2**: Hỗ trợ 2 phương thức thực thi:
  - **Embedded Pipeline (ONNX / Torch):** Load model LaMa/STTN trực tiếp trong Python stream qua OpenCV / PyAV, xử lý theo chunk frame để kiểm soát VRAM.
  - **Bridge Adapter (VSR CLI):** Cho phép trỏ đường dẫn tới bản cài đặt VSR độc lập (`video-subtitle-remover`) hoặc Docker container để tái sử dụng môi trường có sẵn của người dùng.
- **FR-B3**: Quản lý tiến trình (Progress & Cancellation): Gửi callback phần trăm tiến độ `%` về GUI/CLI (`[AI-INPAINT] 45% (135/300 frames)`) và cho phép người dùng bấm Hủy an toàn.

### Nhóm C — Caching & Storage
- **FR-C1**: Video sau khi Inpaint được lưu tại `.cache/inpaint/<video_hash>_<regions_hash>_<model>.mp4` hoặc thư mục output của dự án.
- **FR-C2**: Khi chạy lại pipeline (ví dụ re-dub, đổi font chữ vietsub), hệ thống kiểm tra cache: nếu video sạch đã tồn tại và thông số không đổi, bỏ qua bước AI Inpaint (0 giây).

### Nhóm D — Pipeline Integration (`autodub/pipeline.py` & `autodub/media/video.py`)
- **FR-D1**: Trong quy trình xử lý video (`pipeline.py` / `render_final_video`):
  - Nếu `mask_method == "ai_inpaint"`:
    - **Bước 1 (Pre-process):** Thực hiện AI Inpaint trên video nguồn ➔ Thu được `clean_video.mp4`.
    - **Bước 2 (Final Render):** Áp dụng FFmpeg filtergraph (retime/speed, aspect ratio, smart flip, burn vietsub mới, mix audio dub) lên `clean_video.mp4` với `blur_regions = []` (vì đã xóa sạch ở bước 1).
  - Nếu `mask_method == "blur"`:
    - Chạy thẳng qua FFmpeg `-filter_complex` như cũ (Zero breaking change).

### Nhóm E — Preflight & Device Verification
- **FR-E1**: Kiểm tra phần cứng trong `autodub/preflight.py`:
  - Kiểm tra xem GPU CUDA / DirectML có khả dụng không.
  - Kiểm tra các file model weights (`.onnx` hoặc `.pth`) đã được tải về chưa (hỗ trợ auto-download hoặc hiển thị hướng dẫn tải).

---

## 4. Non-functional Requirements

- **NFR-01 (Bộ nhớ & VRAM):** Không để tràn VRAM (OOM) khi xử lý video dài; bắt buộc giải phóng bộ nhớ GPU sau mỗi batch frames.
- **NFR-02 (Độ trễ & Hiệu năng):** Với model LaMa ONNX trên GPU RTX, tốc độ đạt tối thiểu 15-30 FPS cho video 1080p.
- **NFR-03 (Chất lượng hình ảnh):** Không nén suy hao 2 lần (lossless hoặc CRF 17-18 khi xuất frame sạch trung gian).

---

## 5. Hành vi hiện tại

- Hiện tại chỉ có `blur_regions` áp dụng qua bộ lọc FFmpeg `crop=...boxblur=...overlay=...`.
- Ưu điểm: Tốc độ tức thì theo tốc độ encode ffmpeg.
- Nhược điểm: Để lại mảng mờ che khuất nội dung nền của video.

---

## 6. Module bị ảnh hưởng

1. `autodub/config.py`: Thêm các key cấu hình cho `mask_method` và `inpaint_*`.
2. `autodub/media/inpaint/` *(MỚI)*: Module chứa core engine inpainting và adapter gọi VSR.
3. `autodub/media/video.py`: Tách bạch luồng tiền xử lý inpaint trước khi render final.
4. `autodub/pipeline.py`: Thêm stage AI Inpaint vào luồng xử lý tổng thể.
5. `autodub/preflight.py`: Kiểm tra model files và runtime dependencies.
6. `autodub/editor.py` / GUI: Bổ sung radio button / dropdown chọn phương thức: `[x] Làm mờ (Nhanh) | [ ] Xóa AI (Chất lượng cao)`.

---

## 7. Dependency

- `onnxruntime-gpu` hoặc `torch` (tùy runtime mode).
- Model weights: LaMa Inpainting ONNX (~200MB) hoặc STTN PyTorch checkpoint.
- OpenCV (`cv2`) và `numpy` (đã có sẵn trong project).

---

## 8. Constraint

- Đảm bảo dự án vẫn chạy bình thường với chế độ Boxblur kể cả khi máy người dùng không có GPU hoặc không cài đặt model AI Inpaint.
- Không ép buộc user tải model 2GB nếu họ chỉ dùng Boxblur. Model chỉ tải theo nhu cầu (on-demand download) hoặc khi user bật tính năng.

---

## 9. Edge Cases

1. **Video độ phân giải lớn (4K):** Chia tile hoặc downscale mask để inpaint rồi upscale lại nhằm tránh OOM.
2. **Video không có âm thanh:** Giữ nguyên stream xử lý không lỗi.
3. **User hủy giữa chừng:** Đảm bảo xóa file tạm `.temp_inpaint.mp4` và giải phóng GPU tensor.
4. **Vùng ROI sát mép khung hình:** Padding an toàn chẵn pixel (yuv420p).

---

## 10. Security & Privacy

- 100% xử lý cục bộ trên máy người dùng (Local AI Processing), không gửi dữ liệu frame hay video lên bất kỳ server bên thứ 3 nào.

---

## 11. Performance

- Hỗ trợ batching nhiều frame cùng lúc trên GPU.
- Quản lý luồng bằng worker thread riêng để không gây treo (freeze) GUI.

---

## 12. Acceptance Criteria

- [ ] **AC-01:** Chạy pipeline với `mask_method="blur"` cho ra kết quả y hệt hiện tại (Regression Test 100% Pass).
- [ ] **AC-02:** Chạy pipeline với `mask_method="ai_inpaint"`:
  - Video xuất ra được xóa sạch phụ đề cũ trong vùng chỉ định, không có vệt boxblur.
  - Video có phụ đề mới (nếu có) và audio dub đồng bộ hoàn hảo.
- [ ] **AC-03:** Khi re-render cùng video và cùng tọa độ ROI, hệ thống hit cache `clean_video.mp4` và không inpaint lại.
- [ ] **AC-04:** Khi chạy trên máy không có GPU / thiếu model, hệ thống báo warning thân thiện và fallback về Boxblur an toàn.

---

## 13. Điểm chưa rõ (Cần người dùng xác nhận)

1. **Hình thức tích hợp Engine AI:**
   - **Lựa chọn A (Khuyến nghị - Hybrid):** Tích hợp sẵn engine nhẹ **LaMa ONNX** trực tiếp vào dự án (chỉ cần file model ~200MB, chạy cực nhanh với OnnxRuntime GPU/CPU/DirectML) + Cho phép cấu hình đường dẫn tới bản cài đặt **VSR ngoài** (YaoFANGUK video-subtitle-remover) nếu muốn dùng STTN/ProPainter.
   - **Lựa chọn B (Chỉ CLI Wrapper):** Chỉ làm adapter gọi file `backend/main.py` của repo `video-subtitle-remover` bên ngoài.
2. **Giao diện người dùng:** Bổ sung lựa chọn phương thức che sub tại trang Cài đặt (Settings) và hộp thoại xuất video.

---

## 14. Ngoài phạm vi (Out of Scope)

- Huấn luyện lại (training/fine-tuning) model inpainting mới từ đầu.
- Thay đổi cấu trúc của công cụ OCR phát hiện giọng nói / phụ đề (ASR/Paraformer/Whisper).

---

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
