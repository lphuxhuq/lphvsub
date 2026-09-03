# Thiết kế Kiến trúc: AI Viral Shorts & Reels Clipper

## 1. Requirement đã duyệt
- Tự động phân tích kịch bản / transcript video để tìm các đoạn cao trào ngắn (25s - 65s) chuẩn TikTok, YouTube Shorts, Facebook Reels.
- Chấm điểm Viral Score (1-100), tạo Tiêu đề Hook hấp dẫn và đánh giá mức độ giữ chân người xem (Retention).
- Căn chỉnh mốc thời gian thông minh (Boundary Snapping) vào ranh giới câu thoại và điểm chuyển cảnh, không cắt ngang câu.
- Cắt lát phụ đề ASS tương ứng, áp dụng Smart Reframe 9:16 (Blur / Top-Split / Center-Crop) và xuất video chất lượng cao.
- Giao diện `ViralClipperDialog` hiển thị danh sách các thẻ Clip trực quan, có preview và 1-click export.

## 2. Kiến trúc hiện tại liên quan
- `autodub/content/generator.py`: Sinh nội dung đăng bài qua Direct AI API.
- `autodub/text/translate_direct.py`: `get_direct_client(settings)` gọi AI linh hoạt (Gemini, OpenAI, Claude, DeepSeek, Ollama).
- `autodub/media/subtitle.py`: `build_aspect_ratio_filter` tạo bộ lọc Smart Auto-Reframe 9:16.
- `autodub/media/sfx.py`: Sinh âm thanh chuyển cảnh tự động.
- `autodub/editor.py`: Quản lý `EditorState`, `segments`, `render_opts`.

## 3. Kiến trúc đề xuất
- **Module `autodub/content/viral_clipper.py`**:
  - `analyze_viral_highlights()`: AI Hybrid Analyzer (Direct AI + Heuristic Fallback khi offline).
  - `snap_to_segment_boundaries()`: Căn mốc thời gian không cắt đứt câu nói.
- **Module `autodub/media/clipper.py`**:
  - `slice_ass_subtitles()`: Trích xuất và dịch chuyển thời gian phụ đề ASS cho đoạn con.
  - `export_short_clip()`: Render clip 9:16 hoàn chỉnh bằng FFmpeg kết hợp video, audio, sub và filter.
- **Giao diện `autodub_gui/viral_clipper_dialog.py`**:
  - Hộp thoại hiển thị danh sách clip, điểm số, nút preview và export.

## 4. Component thay đổi / thêm mới
- `[NEW]` `autodub/content/viral_clipper.py`
- `[NEW]` `autodub/media/clipper.py`
- `[NEW]` `autodub_gui/viral_clipper_dialog.py`
- `[MODIFY]` `autodub/editor.py` (Thêm API gọi clipper và lưu `viral_clips.json`)
- `[MODIFY]` `autodub_gui/editor_page.py` hoặc `autodub_gui/app.py` (Thêm nút mở Viral Clipper Dialog)
- `[NEW]` `tests/test_viral_clipper.py`
- `[NEW]` `tests/test_clipper_media.py`
- `[NEW]` `tests/test_viral_clipper_dialog.py`

## 5. Data Flow
1. User mở dự án trong Editor -> Bấm nút "🔥 Tạo Shorts Viral".
2. Hệ thống truyền `segments` và `settings` vào `analyze_viral_highlights()`.
3. AI phân tích kịch bản -> Trả về danh sách clip (mốc thời gian, tiêu đề hook, viral score).
4. `ViralClipperDialog` hiển thị danh sách thẻ clip cho người dùng lựa chọn.
5. Khi người dùng bấm "Xuất Clip" -> `export_short_clip()` tiến hành render video 9:16 và thông báo hoàn thành.

## 6. Control Flow & Error Handling
- Nếu không có mạng hoặc không có API Key, tự động chuyển sang chế độ Heuristic Speech Density Analyzer (100% offline, không báo lỗi gây gián đoạn).
- Nếu mốc thời gian nằm ngoài dải video, tự động clamp vào `[0, total_duration]`.

## 7. Performance & Security
- Không chạy lại toàn bộ pipeline; chỉ render đoạn nhỏ 30-60s nên tốc độ render cực nhanh (vài giây mỗi clip).
- Không gửi dữ liệu ngoài đoạn kịch bản tới AI API. Toàn bộ quá trình cắt ghép media thực hiện offline cục bộ.

## 8. Approval Gate
TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ
