# Phân Tích Yêu Cầu — PERF-FFMPEG-EXPORT-V2

- **Mã yêu cầu**: `PERF-FFMPEG-EXPORT-V2`
- **Mục tiêu**: Tối ưu triệt để toàn diện pipeline FFmpeg export của LPHVSub (Refactor thành pipeline render tự động thích ứng: Resolution, Filter Graph, Blur Strategy, Subtitle/ASS, Hardware/NVENC, Dirty-layer Caching, Profiling).

---

## 1. Mục Tiêu Tổng Thể
Xây dựng một kiến trúc Export Video hoàn chỉnh, mô-đun hóa, hiệu năng cao, ổn định và có khả năng tự thích ứng (`adaptive`):
- Giữ vững tính đúng đắn về mặt thẩm mỹ, tỷ lệ khung hình, chất lượng âm thanh và hiệu ứng Karaoke ASS.
- Nâng tốc độ xuất video thực tế (30–60 phút) đạt mục tiêu $\le$ 4–5 phút (tốc độ trung bình **$\ge$ 10x – 15x** Realtime).
- Cung cấp cơ chế đo kiểm bóc tách chi tiết (Render Profiler) và phát hiện sớm các bất thường về độ phân giải (Resolution Budget).

---

## 2. Functional Requirements (FR)

- **FR-01: OutputProfile & Resolution Normalization**:
  - Quản lý kích thước canvas chuẩn hóa theo tỷ lệ: `9:16` (1080x1920), `16:9` (1920x1080), `1:1` (1080x1080), hoặc custom nếu user chỉ định.
  - Có cơ chế `pixel_budget` (mặc định max $1920 \times 1080 \approx 2.073.600$ pixels) để ngăn chặn hoàn toàn việc canvas bị thổi phồng lên 3.4K (1920x3414) hay 4K/8K không mong muốn.
- **FR-02: RenderPlan & Filter Graph Builder**:
  - Xây dựng abstraction `RenderPlan` tổng hợp: InputInfo, OutputProfile, FilterStrategy, BlurStrategy, SubtitleStrategy, HardwareStrategy, CacheStrategy.
  - Tối ưu hóa thứ tự áp dụng các bộ lọc, loại bỏ các bước scale/crop dư thừa hoặc chuyển đổi format/không gian màu không cần thiết.
- **FR-03: Adaptive BlurStrategy**:
  - Hỗ trợ 3 chế độ làm mờ nền: `FAST`, `BALANCED`, `QUALITY`.
  - Tính toán độ phân giải làm mờ thích ứng dựa trên kích thước khung hình đích, độ mạnh làm mờ (strength), thay vì hard-code giá trị cố định.
- **FR-04: Subtitle / ASS libass Optimization**:
  - Đảm bảo phụ đề Karaoke ASS được render đúng hệ quy chiếu và độ phân giải của canvas đích (1080x1920).
  - Có hàm đánh giá độ phức tạp phụ đề `subtitle_complexity_score()` (FAST, NORMAL, HEAVY, EXTREME) để cảnh báo hoặc điều chỉnh pipeline phù hợp.
  - Giữ nguyên 100% hiệu ứng chữ, màu sắc, font chữ và hiệu ứng Karaoke đổi màu.
- **FR-05: EncoderProfile (NVENC / HW / CPU)**:
  - Cung cấp `EncoderProfile` (`FAST`, `BALANCED`, `QUALITY`) cho các bộ mã hóa (NVENC, QSV, AMF, libx264).
  - Khai thác tối đa thông lượng GPU khi khả dụng mà vẫn bảo toàn chất lượng hình ảnh (CRF/CQ 23 chuẩn).
- **FR-06: Render Profiler (Zero Overhead khi tắt)**:
  - Thiết kế module `RenderProfiler` ghi nhận chi tiết thời gian: Decode, Background Blur, Subtitles, Composition, Encode, Mux, Speed.
  - Log chi tiết dạng `[PERF]` khi bật cờ đo lường debug/perf mode, không gây chậm khi chạy production bình thường.
- **FR-07: Composition Dirty Tracking & Layer Cache**:
  - Cho phép cache các thành phần bất biến giữa các lần xuất (static background, watermark, logo, rendered ASS).
  - Theo dõi `dirty_layers` / `clean_layers` để tránh tính toán lại những gì không thay đổi.

---

## 3. Non-Functional Requirements (NFR)

- **NFR-01: Performance**:
  - Benchmark 15s, 60s, 5m, và video thực tế 37 phút đạt tốc độ $\ge$ 10x – 12x Realtime với video 1080x1920 kèm phụ đề ASS và nền mờ.
- **NFR-02: Backward Compatibility**:
  - 100% các test hiện tại (46/46 unit tests trong `test_subtitle.py`, `test_video_merge.py`, `test_editor.py`) phải tiếp tục PASS.
  - Public interface của `merge_video()` và `build_filter_complex()` phải được giữ tương thích hoàn toàn.
- **NFR-03: Quality & Sync**:
  - Không làm lệch tiếng (audio sync), không làm vỡ hình ảnh, không làm méo tỷ lệ (aspect ratio) hay lệch vị trí phụ đề.

---

## 4. Phạm Vi & Giới Hạn (Scope Control)

- **Trong phạm vi (IN SCOPE)**:
  - Tối ưu hóa module `autodub/media/video.py`, `autodub/media/subtitle.py`.
  - Tạo các module kiến trúc mới: `output_profile.py`, `blur_strategy.py`, `encoder_profile.py`, `render_profiler.py`, `render_plan.py`, `render_cache.py`.
  - Thêm comprehensive regression tests & benchmark scripts.
- **Ngoài phạm vi (OUT OF SCOPE)**:
  - KHÔNG thay đổi pipeline âm thanh / AI: ASR (Whisper/Paraformer), Dịch thuật (Gemini/OpenAI), TTS (VieNeu/EdgeTTS), Audio Ducking, Vocal Separation (Demucs).
  - KHÔNG xóa hay thay đổi chức năng của Composition Editor, Logo, Watermark, Banner, Anti-Content ID.

---

## 5. Acceptance Criteria (Tiêu Chí Nghiệm Thu)

1. `OutputProfile` chuẩn hóa 9:16 = 1080x1920, 16:9 = 1920x1080, 1:1 = 1080x1080, có pixel budget bảo vệ.
2. `RenderPlan` xây dựng filter graph tinh gọn, không có scale dư thừa.
3. `BlurStrategy` hỗ trợ `FAST`, `BALANCED`, `QUALITY` với downscale adaptive.
4. `RenderProfiler` bóc tách được thời gian từng khâu khi bật debug/perf.
5. 46/46 unit tests cũ PASS 100% + bộ tests mới cho các profile đều PASS.
6. Benchmark thực tế 15s, 60s, 5m và video đầy đủ 37 phút đạt tốc độ $\ge$ 10x Realtime (thời gian render video 37 phút $\le$ 4-5 phút).

---

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
