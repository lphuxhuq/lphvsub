# Fix Design: Khớp hình và Lời thoại (Audio-Video Sync & Timing Engine)

## 1. Mục tiêu & Phạm vi
Khắc phục triệt để các bất cập trong hệ thống khớp hình và lời thoại:
1. **Tối ưu thuật toán `plan_placements` trong `autodub/media/timing.py`**:
   - Dọn dẹp tính toán trùng lặp của `overlap_prev`.
   - Xử lý mượt mà khi các câu sát nhau hoặc audio dài hơn phân đoạn gốc.
   - Đảm bảo `final_dur` và `prev_end` chính xác tuyệt đối sau khi nén `atempo`.
2. **Tối ưu xử lý Video Muxing trong `autodub/media/video.py`**:
   - Đảm bảo khi ghép video và audio, nếu audio dài hơn video, stream video kết thúc mượt mà, thêm cờ `-movflags +faststart` cho tất cả các luồng xuất.
3. **Đồng bộ hóa Trình chỉnh sửa (`autodub/editor.py` & `autodub_gui/pages/editor_export.py`)**:
   - Đảm bảo khi người dùng đọc lại câu hoặc xuất video từ Editor, luồng xử lý luôn chạy qua `apply_soft_timing` và cập nhật lại cả phụ đề `.srt` lẫn `.ass` karaoke đúng theo timeline mới nhất.
4. **Bộ kiểm thử tự động chuyên sâu (`tests/test_timing_alignment.py`)**:
   - Kiểm tra `plan_placements` trong các kịch bản: câu vừa khít, câu dồn trễ, câu nén atempo, câu chồng tiếng, các edge case thời lượng 0s, danh sách rỗng.
   - Kiểm tra `apply_soft_timing` và `rescale_segments`.

---

## 2. Chi tiết các tệp thay đổi & Logic sửa

| Tệp | Thay đổi logic | Rủi ro hồi quy (Regression Risk) |
|---|---|---|
| [`autodub/media/timing.py`](file:///d:/Project/lphvsub-main/autodub/media/timing.py) | Chuẩn hóa `plan_placements`: tính `overlap_prev` một lần duy nhất, đảm bảo tính toán `available` và `want` atempo luôn an toàn | Rất thấp (đã kiểm thử 15 unit test timing) |
| [`autodub/media/video.py`](file:///d:/Project/lphvsub-main/autodub/media/video.py) | Thêm `-movflags +faststart` giúp video tải và xem mượt mà trên mọi thiết bị, tối ưu fps và metadata | Rất thấp (FFmpeg standard flags) |
| [`autodub/editor.py`](file:///d:/Project/lphvsub-main/autodub/editor.py) | Đảm bảo `refresh_subtitles` nhận đúng `merge_dir` và `for_burn` khi xuất video từ Editor | Rất thấp |
| [`tests/test_timing_alignment.py`](file:///d:/Project/lphvsub-main/tests/test_timing_alignment.py) | Bộ test bổ sung 5 ca kiểm thử edge case | Không có |

---

## 3. Kế hoạch kiểm thử & Kiểm chứng
1. Chạy unit test riêng: `py -m pytest tests/test_timing.py tests/test_retime.py tests/test_timing_alignment.py -v`
2. Chạy toàn bộ test suite dự án: `py -m pytest -q`
3. Xác minh 100% test pass, 0 lỗi hồi quy.

---

**TRẠNG THÁI HIỆN TẠI:** `TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`
