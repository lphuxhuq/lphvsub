# Design Spec: Triệt Để Khắc Phục Sub/Voice Xuất Hiện & Nói Trước Cảnh (Dual-Edge Scene Guard & Word-Level Timing Sync)

## 1. Bối cảnh & Vấn đề (Context & Problem)

Khi chuyển ngữ và lồng tiếng video, người dùng phản ánh tình trạng: **"Sub và voice chưa tới cảnh đã hiện và nói trước"** (phụ đề tiếng Việt và giọng đọc lồng tiếng xuất hiện trước khi khung hình chuyển cảnh sang đoạn hội thoại mới khoảng 0.3s – 0.6s).

### Nguyên nhân kỹ thuật gốc rễ:
1. **VAD Speech Padding quá lớn trong Whisper & Paraformer**:
   - `whisper.transcribe` đang đặt `speech_pad_ms: 500` (mở rộng 0.5s hai đầu đoạn thoại).
   - Khi mô hình ASR trả về segment, `seg.start` mang giá trị biên VAD thô (ví dụ `4.70s`) thay vì thời điểm bắt đầu phát âm của từ đầu tiên (`seg.words[0].start = 5.18s`).
2. **Thiếu Left-Edge Scene Guard (Chốt chặn cảnh phía trước)**:
   - Module `autodub/media/scene_detector.py` có hàm `detect_scene_cuts` nhưng chưa từng được gọi trong `pipeline.py` và `apply_soft_timing`.
   - Hàm `find_next_scene_boundary` chỉ chặn đuôi câu tràn sang cảnh tiếp theo (`Right-Edge Guard`), hoàn toàn thiếu cơ chế chặn đầu câu lấn ngược về cảnh trước (`Left-Edge Guard`). Ví dụ: Cảnh mới bắt đầu tại `5.00s`, nhưng ASR trả về `4.70s` do VAD padding/âm thanh nền cảnh cũ, dẫn tới voice và sub xuất hiện từ `4.70s` khi cảnh cũ vẫn đang chiếu.
3. **Cơ chế Pre-roll & Refine chưa có ranh giới bảo vệ chuyển cảnh**:
   - `dub_pre_roll_ms` có thể đẩy mốc giọng đọc sớm hơn nữa mà không kiểm tra xem có bị vượt ngược qua điểm chuyển cảnh hay không.
   - `refine_speech_boundaries` (RMS energy) có thể nhận năng lượng tiếng ồn/nhạc nền ở 0.3s cuối của cảnh trước làm điểm bắt đầu giọng nói.

---

## 2. Kiến trúc giải pháp 3 tầng (3-Tier Architecture)

```
+-----------------------------------------------------------------------------------+
| TẦNG 1: CHUẨN XÁC HÓA MỐC THỜI GIAN ĐẦU VÀO (WORD-LEVEL ONSET ANCHOR)             |
| - Giảm VAD pad từ 500ms xuống 150ms.                                             |
| - Nếu có word_timestamps (Whisper / Paraformer), neo start = words[0].start.      |
| - Nâng cấp refine_speech_boundaries: loại bỏ false-energy ở đầu câu.             |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| TẦNG 2: BỘ PHÁT HIỆN & CHỐT CHẶN CẢNH KÉP (DUAL-EDGE SCENE GUARD)                  |
| - Pipeline tự động chạy detect_scene_cuts(video_path) lấy danh sách scene_cuts.   |
| - Left-Edge Guard: Nếu segment bắt đầu trước Scene Cut <= 0.45s và kéo dài qua    |
|   cảnh mới, snap start >= Scene Cut (+0.02s). Không bao giờ nói trước cảnh mới!   |
| - Right-Edge Guard: Chặn giọng đọc câu không tràn đuôi sang cảnh tiếp theo.       |
| - Dub Pre-roll Guard: Pre-roll không được vượt ngược qua điểm Scene Cut.          |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| TẦNG 3: ĐỒNG BỘ SUITE THỜI GIAN (SRT / KARAOKE ASS / VIDEO MERGE)                 |
| - apply_soft_timing áp dụng Dual-Edge Scene Guard trước khi mutate start/end.     |
| - refresh_subtitles sinh SRT & ASS theo đúng mốc đã được bảo vệ bởi Scene Guard.  |
| - Trình chỉnh sửa (Editor) tôn trọng các điểm chuyển cảnh khi rebuild.            |
+-----------------------------------------------------------------------------------+
```

---

## 3. Chi tiết thiết kế các thành phần (Component Details)

### 3.1. `autodub/speech/transcriber.py` & `asr_whisper_worker.py`
- Giảm `speech_pad_ms` từ `500` xuống `150` ms trong `vad_parameters`.
- Khi Whisper trả về danh sách `words` hợp lệ (`seg.words`):
  - Lấy `true_start = seg.words[0].start`.
  - Nếu `seg.start < true_start` và khoảng cách <= `0.45s`, gán `segment["start"] = true_start` (neo vào từ đầu tiên phát âm thật).
  - Tương tự, nếu `seg.words[-1].end < seg.end` và khoảng cách <= `0.45s`, cập nhật `segment["end"] = seg.words[-1].end`.

### 3.2. `autodub/media/scene_detector.py`
- Bổ sung hàm `snap_to_scene_boundaries(start, end, scene_cuts, threshold_s=0.45)`:
  - **Left-Edge Snapping**: Nếu tồn tại điểm chuyển cảnh `T_cut` thỏa mãn `start < T_cut <= start + threshold_s` và `end > T_cut + 0.3s`, xác định câu thoại thuộc về cảnh mới bắt đầu tại `T_cut`. Snap `start = T_cut + 0.02s`.
  - **Right-Edge Clamping**: Nếu tồn tại điểm chuyển cảnh `T_next` ngay sau `start`, giới hạn `usable_end = min(usable_end, T_next - 0.02s)`.
- Bổ sung cache kết quả quét cảnh vào thư mục `data/scene_cuts.json` để không phải quét lại khi xuất/rebuild nhiều lần.

### 3.3. `autodub/media/timing.py` (`plan_voice_placements` & `apply_soft_timing`)
- Nhận danh sách `scene_cuts` từ video gốc trong `apply_soft_timing`.
- Trong `plan_voice_placements`:
  - Áp dụng `snap_to_scene_boundaries` cho `natural` onset của từng segment.
  - Khi tính `pre_roll_s`, đảm bảo `natural - pre_roll_s` không vượt ngược qua `prev_scene_cut`.
  - Giới hạn `usable_end` bởi `next_scene_cut`.

### 3.4. `autodub/pipeline.py` & `autodub/editor.py`
- Trong Step 6 (Audio Retiming & Merge):
  - Nếu `video_path` tồn tại và `settings.voice_scene_guard_enabled` bật (mặc định `True`), tự động gọi `detect_scene_cuts(video_path)` và lưu vào `data/scene_cuts.json`.
  - Truyền `scene_cuts` vào `apply_soft_timing`.
- Trong `autodub/editor.py`:
  - `rebuild_output` và `rebuild_subtitles` nạp `scene_cuts.json` nếu có và truyền vào `apply_soft_timing`.

---

## 4. Kế hoạch kiểm thử (Testing & Verification)

1. **Unit Tests cho Scene Guard**:
   - `test_left_edge_scene_snapping`: Kiểm tra câu thoại có ASR start `4.75s` nhưng cảnh chuyển tại `5.00s` được tự động snap lên `5.02s`.
   - `test_right_edge_scene_clamping`: Kiểm tra câu thoại không tràn đuôi sang cảnh sau.
   - `test_whisper_word_anchor_onset`: Kiểm tra Whisper segment lấy start từ `words[0].start` thay vì biên VAD thô.
2. **Integration Tests**:
   - `test_pipeline_scene_guard_integration`: Kiểm tra pipeline hoàn chỉnh quét scene cuts và truyền vào `apply_soft_timing`.
   - `test_editor_rebuild_with_scene_guard`: Kiểm tra trình chỉnh sửa giữ nguyên đồng bộ cảnh khi xuất lại video.
3. **Full Regression Suite**:
   - Đảm bảo toàn bộ 954+ unit tests tiếp tục pass 100%.
