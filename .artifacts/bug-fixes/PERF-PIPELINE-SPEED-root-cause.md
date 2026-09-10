# BÁO CÁO NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)
## Vấn đề: Tối ưu hoá tốc độ xuất và xử lý của các bước trong Pipeline

- **Mã lỗi / Vấn đề**: `PERF-PIPELINE-SPEED`
- **Mức độ nghiêm trọng**: CAO (Video 2 tiếng mất hơn 1.5 tiếng để hoàn thành, trong đó Render video chiếm hơn 70 phút).
- **Môi trường**: Windows 11, Python 3.11, NVIDIA GPU (CUDA), NVENC.

---

### 1. Phân tích Dữ liệu Thực tế từ Log (`logs/voxdub.log`)
Từ log dự án thực tế `20260906002906_vi` (Video dài 7.248 giây ~ 2 giờ 0 phút 48 giây, 974 câu thoại):

| Bước (Step) | Tên chức năng | Thời gian thực tế | % Thời gian | Đánh giá |
| :--- | :--- | :---: | :---: | :--- |
| **STEP 3** | Transcribing audio (ASR) | **744.3s (12.4 phút)** | ~13.5% | Chạy Whisper tuần tự (single chunk), chưa dùng Batched Inference GPU. |
| **STEP 3.6** | Diarization | *0s (đã cache)* | 0% | Đã tối ưu skip cache ở turn trước. |
| **STEP 4** | Translation | *0s - 146s (đã cache)* | ~2.5% | Đã tối ưu incremental checkpointing ở turn trước. |
| **STEP 5** | Synthesizing audio (TTS) | **333.4s (5.56 phút)** | ~6.0% | CapCut API / VieNeu với 6-8 threads (tương đối nhanh: ~2.9 câu/s). |
| **STEP 6a** | Voice postprocess | **122.9s (2.05 phút)** | ~2.2% | Bị nghẽn do spawn 974 tiến trình ffmpeg con riêng lẻ và bị chặn bởi semaphore 6 slot. |
| **STEP 6** | Audio merge & Timing | **122.9s (2.05 phút)** | ~2.2% | Xử lý streaming audio 2 tiếng. |
| **STEP 7** | Creating dubbed video (Render) | **~4.260s (71 phút)** | **~75.6%** | **NÚT THẮT CỔ CHAI LỚN NHẤT**. Tốc độ chỉ đạt 1.7x realtime! |

---

### 2. Nguyên nhân gốc rễ (Root Causes)

#### NGUYÊN NHÂN 1 (Trọng yếu nhất): Tốc độ Render Video ở STEP 7 bị tụt từ 12x xuống 1.7x
- **Hiện tượng**: Khi benchmark video thuần không filter trên GPU NVENC đạt **12.0x**. Khi gộp filtergraph thì tốc độ sụt giảm nghiêm trọng còn **1.7x** (tốn 71 phút cho video 2 tiếng).
- **Nguyên nhân kỹ thuật**:
  1. **Nhiều lần `split + crop + boxblur + overlay`**: Khi có nhiều vùng che phụ đề (ví dụ 2 vùng ROI), FFmpeg phải copy toàn bộ frame 1080x1920 qua 2 lần `split`, 2 lần `crop`, 2 lần `boxblur` và 2 lần `overlay` (Alpha blending per-pixel trên 2 triệu điểm ảnh x 2).
  2. **Giải pháp thay thế nhanh gấp 3-5 lần**: Filter chuẩn của FFmpeg là `delogo=x=X:y=Y:w=W:h=H:show=0` cho phép làm mờ/che phụ đề nội tại (in-place) ngay trên cùng frame mà KHÔNG cần `split` stream hay `overlay` stream!
  3. **Thiếu Hardware Decode Acceleration**: Lệnh ffmpeg hiện tại giải mã video nguồn 1080p hoàn toàn bằng CPU software decoder, làm CPU luôn ở mức 100%, gây nghẽn trước khi frame tới NVENC.

#### NGUYÊN NHÂN 2: Nút thắt cổ chai ở STEP 6a (Voice postprocess - 122 giây)
- **Hiện tượng**: 974 câu thoại cần loudnorm, highpass và fade mất hơn 2 phút.
- **Nguyên nhân kỹ thuật**:
  1. `FFMPEG_SLOTS` trong `autodub/resources.py` đang dùng chung một trần cho cả video encode lẫn audio filter: `max(2, min(6, _CPU - 1)) = 6 slots`.
  2. Mỗi tiến trình ffmpeg lọc âm thanh chỉ tốn ~5MB RAM và < 3% của 1 core CPU, nhưng lại bị kẹp chỉ chạy 6 câu cùng lúc.
  3. Với 974 câu, thời gian chờ slot và overhead tạo process trên Windows (30-50ms/process) chiếm hơn 50% thời gian chạy.

#### NGUYÊN NHÂN 3: STEP 3 (ASR) chưa tận dụng Batched Inference trên GPU (744 giây)
- **Hiện tượng**: Whisper transcribe video 2 tiếng mất 12.4 phút (tốc độ ~9.7x).
- **Nguyên nhân kỹ thuật**:
  1. `WhisperModel.transcribe` chạy tuần tự từng đoạn audio 30s.
  2. Thư viện `faster-whisper >= 1.0` đã tích hợp sẵn `BatchedInferencePipeline(model)` hỗ trợ gom batch (batch_size=8 đến 16) đẩy vào GPU CUDA cùng lúc, tăng throughput lên 20x - 30x realtime (giảm thời gian xuống còn 4-5 phút).

---

### 3. Kế hoạch Tối ưu hoá (Fix Design Plan)
1. **Tối ưu STEP 7 (Video Render)**:
   - Thay thế cơ chế `split + crop + boxblur + overlay` đa tầng bằng `delogo` in-place hoặc chuỗi filter tinh gọn: loại bỏ hoàn toàn việc nhân bản stream và overlay nặng nề.
   - Thêm `-hwaccel auto` vào trước input video để GPU hỗ trợ decode video nguồn.
   - Tinh chỉnh preset NVENC (`p1` hoặc `p2` tối ưu) và buffer I/O pipe.
2. **Tối ưu STEP 6a (Voice Postprocess)**:
   - Tách riêng `FFMPEG_AUDIO_SLOTS = threading.BoundedSemaphore(min(16, max(4, (_CPU - 1) * 2)))` chuyên dụng cho xử lý âm thanh siêu nhẹ.
   - Tăng tốc độ hậu kỳ âm thanh gấp 2.5 - 3 lần (từ 122s xuống ~35s).
3. **Tối ưu STEP 3 (ASR - Whisper)**:
   - Kích hoạt `BatchedInferencePipeline` khi chạy trên CUDA GPU để tận dụng song song các tensor cores.
