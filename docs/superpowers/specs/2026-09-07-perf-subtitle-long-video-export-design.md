# Thiết Kế Kỹ Thuật: Tối Ưu Tốc Độ Ghi Phụ Đề & Xuất Video Dài (PERF-SUBTITLE-LONG-VIDEO-EXPORT)

- **Ngày lập**: 2026-09-07
- **Mã thiết kế**: `PERF-SUBTITLE-LONG-VIDEO-EXPORT`
- **Mục tiêu**: Tối ưu hóa tốc độ ghi phụ đề (cả phụ đề thông thường lẫn Karaoke nhấp nháy từ) và tăng tốc độ xuất video dài (15m - 2h) trên các tỷ lệ khung hình (16:9 gốc, 9:16 TikTok có nền mờ nghệ thuật).

---

## 1. Bối Cảnh & Vấn Đề

Khi xử lý các video dài (từ 30 phút đến 1-2 tiếng), quá trình xuất video (`merge_video`) và ghi đè phụ đề (`subtitle_mode="burn"`) gặp phải các điểm nghẽn hiệu năng lớn:
1. **Thiếu đa luồng trong Filtergraph FFmpeg**: `-threads 0` chỉ được đặt trước `-i` (áp dụng cho decoder), trong khi bộ lọc phức tạp `subtitles` (libass), `boxblur`, `overlay` bị giới hạn số luồng mặc định, không tận dụng hết các nhân CPU hiện đại.
2. **Nền mờ chuyển tỷ lệ 9:16 (Background Blur) quá nặng**: Trước đây áp dụng `boxblur` trực tiếp trên độ phân giải đầy đủ (1080x1920 hoặc cao hơn), tiêu tốn hàng triệu phép tính điểm ảnh trên mỗi khung hình.
3. **Phụ đề Karaoke (`ass_karaoke.py`) gây quá tải CPU cho libass**: Hiệu ứng phóng to/thu nhỏ font liên tục trên từng cụm từ (`\t(0,110,\fscx100\fscy100)`) buộc libass phải liên tục rasterize lại vector glyph outline trên mỗi frame của video dài hàng nghìn câu.
4. **Nghẽn ghi đĩa cuối tệp (`-movflags +faststart`)**: Việc dời `moov` atom lên đầu file MP4 sau khi encode xong buộc FFmpeg phải đọc và ghi lại toàn bộ file nhiều GB, gây độ trễ lớn khi thanh tiến độ đã chạm 100%.
5. **Nhiều vùng che phụ đề cũ (Multi-region Blur)**: Xử lý nhiều vùng che tuần tự bằng các lệnh `split -> crop -> boxblur -> overlay` liên tiếp trên toàn khung hình.

---

## 2. Mục Tiêu & Tiêu Chí Thành Công

1. **Tăng tốc độ xuất video**: Tăng tốc độ render tổng thể từ $2.5\times$ đến $5\times$ đối với video dài.
2. **Tận dụng tối đa phần cứng**: Khai thác tối đa GPU NVENC (`h264_nvenc -preset p1`) kết hợp với đa luồng CPU cho libass (`-filter_complex_threads 0`).
3. **Chất lượng hiển thị nguyên vẹn**: Giữ nguyên độ sắc nét của chữ phụ đề, độ mượt mà của hiệu ứng Karaoke CapCut, và hiệu ứng mờ nghệ thuật của nền canvas.
4. **Không phát sinh lỗi hồi quy (Zero Regression)**: Toàn bộ 46 tests trong `tests/test_subtitle.py` và `tests/test_video_merge.py`, cùng các tests trong `test_render_plan_v2.py`, `test_ass_karaoke.py` đều đạt 100% PASS.

---

## 3. Thiết Kế Kiến Trúc & Chi Tiết Triển Khai

### 3.1. Tích Hợp `RenderPlan` v2 & `BlurStrategy` vào `merge_video()`
- `merge_video()` trong `autodub/media/video.py` sẽ sử dụng `RenderPlan` và `OutputProfile` để xác định kích thước chuẩn:
  - Nếu chuyển tỷ lệ sang 9:16, chuẩn hóa về `1080x1920` (khống chế `pixel_budget <= 2_073_600`), tránh bị phóng đại độ phân giải.
  - Sử dụng `BlurStrategy.build_background_filter()` với chế độ `FAST`: Downscale hệ số $6\times$ (giảm $36\times$ số lượng pixel tính toán), áp dụng `boxblur=4:1` rồi upscale bilinear.
  - Tích hợp liền mạch với `build_filter_complex()` trong `autodub/media/subtitle.py` để giữ trọn vẹn khả năng tương thích ngược.

### 3.2. Cấu Hình Đa Luồng Toàn Diện Cho FFmpeg
- Bổ sung `-filter_complex_threads 0` vào tham số dòng lệnh FFmpeg khi có `filter_complex`.
- Đặt cờ `-threads 0` ở cả đầu vào lẫn bộ mã hóa đầu ra.
- Đối với GPU NVENC, đảm bảo cấu hình tối ưu độ trễ thấp: `-preset p1 -cq 23 -b:v 0 -multipass 0`.

### 3.3. Tối Ưu Libass Karaoke Event Stream (`autodub/text/ass_karaoke.py`)
- Chuẩn hóa và làm sạch chuỗi Dialogue sự kiện:
  - Tối ưu thẻ hiệu ứng: Rút ngắn chu kỳ scale font và loại bỏ các transform vi mô không cần thiết trên video dài.
  - Đảm bảo các mốc `t0` và `t1` không bị giao thoa (micro-overlap) gây giật lag glyph cache của libass.
  - Cơ chế tạo style và dialogue nhẹ nhàng, tiêu thụ ít bộ nhớ RAM và CPU trong quá trình libass rasterization.

### 3.4. Tối Ưu Hóa Multi-Region Blur
- Cải tiến hàm `blur_filter()` và các bước crop/blur trong `build_filter_complex()`:
  - Tinh chỉnh bán kính làm mờ phù hợp với diện tích vùng crop để tránh lặp pass không cần thiết.
  - Giảm thiểu số lượng nhánh copy buffer trong filtergraph.

### 3.5. Tối Ưu Hóa Ghi Tệp & Kết Thúc Render
- Thêm cờ điều khiển `faststart` trong `merge_video()`:
  - Mặc định giữ `faststart=True` cho các video vừa và nhỏ.
  - Cho phép bỏ qua hoặc tối ưu bước dời atom đối với các video xuất cục bộ rất dài để hoàn thành việc xuất file ngay tức thì khi encode xong.

---

## 4. Kế Hoạch Kiểm Thử & Đo Lường (Verification Plan)

1. **Automated Unit Tests**:
   - Chạy toàn bộ test suite hiện có:
     `pytest tests/test_subtitle.py tests/test_video_merge.py tests/test_ass_karaoke.py tests/test_render_plan_v2.py -v`
   - Bổ sung unit test kiểm tra tham số `-filter_complex_threads 0` và downscale blur trong `tests/test_video_merge.py` và `tests/test_subtitle.py`.
2. **Benchmark Đo Lường Thực Tế**:
   - Chạy kiểm thử xuất video thực tế trên file test (đo FPS, thời gian render trước và sau khi tối ưu).
   - Xác nhận file xuất ra xem được tốt, phụ đề chuẩn khớp, âm thanh hình ảnh đồng bộ.
