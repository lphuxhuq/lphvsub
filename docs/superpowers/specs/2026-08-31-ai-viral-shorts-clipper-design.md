# Design Spec: AI Viral Shorts & Reels Clipper

## 1. Mục tiêu (Goals)
Xây dựng tính năng **AI Viral Shorts & Reels Clipper** cho phép tự động:
1. **Phân tích ngữ nghĩa kịch bản** (thông qua Direct AI API - Gemini / OpenAI / DeepSeek hoặc quy tắc Offline Energy/Scene Density):
   - Nhận diện 3-5 đoạn cao trào, nút thắt kịch tính hoặc khoảnh khắc viral nhất của video dài.
   - Mỗi đoạn có độ dài lý tưởng từ 25s - 65s (chuẩn TikTok / YouTube Shorts / Facebook Reels).
   - Chấm điểm **Viral Score (1-100)** kèm đánh giá **Hook Strength**, **Retention Rate**, và đề xuất **Tiêu đề giật tít (Viral Title)**.
2. **Thuật toán Snapping thông minh (Boundary Snapping)**:
   - Tự động căn chỉnh mốc thời gian bắt đầu và kết thúc vào ranh giới câu thoại (`segments[i]['start']` đến `segments[j]['end']`) và mốc chuyển cảnh (`scene_cuts`), tuyệt đối không cắt cụt câu nói ở giữa.
3. **Engine Trích xuất & Dựng Shorts 9:16 (`autodub/media/clipper.py`)**:
   - Cắt video con, trích xuất đoạn âm thanh tổng hợp tương ứng.
   - Cắt lát (Slice) và căn lại mốc thời gian phụ đề ASS (`Dialogue: 0,0:00:00.00...`).
   - Tự động áp dụng Smart Reframe (9:16 với nền Blur, Top-Split hoặc Center-Crop) và chèn Auto SFX chuyển cảnh.
4. **Giao diện người dùng (GUI Dialog)**:
   - Thêm `ViralClipperDialog` với các thẻ trực quan (Cards): hiển thị Video Thumbnail, Tiêu đề Hook, Điểm số Viral 🔥, mốc thời gian, nút Xem trước (Preview) và nút 1-Click Xuất Shorts.

---

## 2. Kiến trúc & Module chi tiết

### Module 1: AI Highlight Analyzer (`autodub/content/viral_clipper.py`)
- **Hàm phân tích chính**:
  ```python
  def analyze_viral_highlights(
      segments: list[dict],
      settings: Settings,
      video_title: str = "",
      min_duration: float = 25.0,
      max_duration: float = 65.0,
      max_clips: int = 5,
      scene_cuts: list[float] | None = None
  ) -> list[dict]:
      """Phân tích các đoạn kịch bản tìm các mốc cao trào viral.
      
      Trả về danh sách các clip metadata:
      [
          {
              "id": 1,
              "title": "Bất ngờ với cú lật mặt của trùm phản diện",
              "hook_text": "Không ai ngờ rằng chính người anh em chí cốt...",
              "start": 42.5,
              "end": 88.2,
              "duration": 45.7,
              "viral_score": 95,
              "reason": "Tình huống kịch tính, nhịp đối thoại dồn dập, có cú twist cao trào.",
              "start_segment_idx": 12,
              "end_segment_idx": 24
          }, ...
      ]
      """
  ```
- **Prompt Engineering**:
  - Hướng dẫn AI đóng vai chuyên gia sáng tạo nội dung ngắn triệu view.
  - Phân tích transcript tiếng Việt, chỉ định cụ thể các mốc câu thoại có độ kịch tính cao nhất.
  - Trả về JSON có cấu trúc (Strict JSON schema).
- **Offline Fallback / Heuristic Analyzer**:
  - Khi không có API Key, tự động tính toán điểm số dựa trên:
    - Mật độ câu thoại (Speech density: số từ / giây).
    - Tần suất chuyển cảnh (Scene cut density).
    - Các từ khóa kích thích cảm xúc tiếng Việt ("bất ngờ", "không thể tin", "bí mật", "sự thật", "nguy hiểm", "cứu", "chết", "tiền").

### Module 2: Subtitle Slicer & Media Clipper Engine (`autodub/media/clipper.py`)
- **Cắt phụ đề ASS tương ứng**:
  ```python
  def slice_ass_subtitles(
      ass_content: str,
      start_time: float,
      end_time: float
  ) -> str:
      """Cắt và shift timestamp của các dòng thoại ASS nằm trong khoảng [start_time, end_time]."""
  ```
- **Xuất video Shorts 9:16**:
  ```python
  def export_short_clip(
      source_video: str,
      source_audio: str,
      ass_sub_path: str | None,
      start_time: float,
      end_time: float,
      output_path: str,
      aspect_preset: str = "tiktok_9_16",
      reframe_mode: str = "blur",
      reporter: ProgressReporter | None = None
  ) -> str:
      """Render clip 9:16 độc lập bằng FFmpeg."""
  ```

### Module 3: Giao diện `ViralClipperDialog` (`autodub_gui/viral_clipper_dialog.py`)
- Kế thừa `QDialog` với theme Dark hiện đại, thiết kế chuẩn thẩm mỹ cao:
  - Header: Tên video + Nút "Phân tích lại bằng AI" + Badge trạng thái.
  - Vùng nội dung: QScrollArea chứa danh sách các Clip Cards.
  - Mỗi Clip Card gồm:
    - Thumbnail mốc thời gian tương ứng.
    - Điểm số Viral Score với Gradient Badge đỏ/vàng cam nổi bật.
    - Tiêu đề Hook tiếng Việt + Thời lượng (VD: `00:42 -> 01:28 (46s)`).
    - Nút `▶ Xem trước` (mở video player nội bộ).
    - Nút `🎬 Xuất 9:16 (Shorts/TikTok)` và nút `📁 Mở thư mục`.
  - Bottom Bar: Nút `⚡ Xuất tất cả các Clip` và thanh tiến trình xuất.

---

## 3. Data & File Contracts
- Đầu vào: `EditorState` hoặc thư mục dự án gồm `segments.json`, `dubbed.wav` (hoặc `audio_merged.wav`), `final_sub.ass`, `video.mp4`.
- Đầu ra:
  - `viral_clips.json` lưu cache kết quả phân tích trong thư mục dự án.
  - Các tệp video xuất: `exports/shorts/{project_name}_short_{idx}.mp4`.

---

## 4. Test & Verification Plan
- Unit tests:
  - `tests/test_viral_clipper.py`: Test heuristic phân tích, prompt formatting, JSON parsing, snapping logic.
  - `tests/test_clipper_media.py`: Test cắt lát phụ đề ASS, tính toán thời gian `slice_ass_subtitles`, ffmpeg clip exporter.
- GUI tests:
  - `tests/test_viral_clipper_dialog.py`: Test khởi tạo dialog, hiển thị cards, xử lý sự kiện xuất clip.
- Full regression test: Chạy toàn bộ test suite đảm bảo 100% PASS.
