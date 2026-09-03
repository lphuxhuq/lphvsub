# Báo cáo hoàn thành sửa lỗi: Hiện tượng Sub hiện nhưng không đọc / Nuốt chữ (Subtitle-TTS Fix Report)

- **Bug ID**: `subtitle-tts-swallow-words`
- **Ngày hoàn thành**: 2026-09-01
- **Trạng thái**: PASS (Đã sửa và xác minh hoàn tất)

---

## 1. Tóm tắt vấn đề & Nguyên nhân gốc rễ

- **Vấn đề**: Người dùng phản ánh phụ đề xuất hiện trên video nhưng giọng đọc bị thiếu chữ ("nuốt chữ"), đứt đoạn đầu câu, mất câu thoại hoặc đọc sót từ.
- **Nguyên nhân gốc**:
  1. `tts_trimmer.py` đặt `ENERGY_RATIO = 0.08` quá cao và `DEFAULT_MARGIN_S = 0.025` quá hẹp khiến các phụ âm xát/vô thanh năng lượng nhỏ đầu câu (`th`, `s`, `x`, `ph`, `kh`, `h`, `ch`, `tr`, `c/k`, `t`, `p`) bị VAD cắt mất. Đồng thời việc cắt lặp lại nhiều lần ở các bước hậu kỳ ffmpeg gọt sâu thêm vào âm thanh.
  2. `capcut_vi.py` gặp `TTSInvalidText` (do Unicode NFD hoặc ký tự đặc biệt) tự động fallback về `write_silence` làm câm cả câu thoại.
  3. `vi_numbers.py` chưa xử lý toàn diện các dạng `100k` (bị dính thành `một trămk`), `50k VNĐ`, `50.000đ`, `$100`, `10h30`, `1/2`, `AI`, `CPU`, `RAM`, `OK`, `TV`, `v.v.`, và các thẻ chú thích âm thanh phụ đề `[Âm nhạc]`, `(Cười)`.

---

## 2. Các thay đổi đã thực hiện

1. **`autodub/speech/tts_trimmer.py`**:
   - `ENERGY_RATIO = 0.02` (2% peak RMS) bảo vệ an toàn tuyệt đối cho mọi phụ âm yếu.
   - `DEFAULT_MARGIN_S = 0.080` (80ms đệm) giữ trọn vẹn ngữ âm mở đầu và kết thúc câu.
   - `ABS_FLOOR = 0.0015` và `min_silence_s = 0.06`.
2. **`autodub/media/audio.py`**:
   - Tăng `_LEAD_TRIM_GUARD_S = 0.18` (180ms) trong `lead_silence_s`.
   - Trong `postprocess_voice_clip`: Chỉ áp dụng `-ss` khi khoảng lặng $\ge$ 80ms, tránh cắt tỉa lặp lại gây cụt tiếng.
3. **`autodub/text/vi_numbers.py`**:
   - Thêm `unicodedata.normalize('NFC', text)`.
   - Lược bỏ các thẻ phụ đề phi thoại `[Âm nhạc]`, `(Cười)`, `*thở dài*` khi đưa vào TTS.
   - Mở rộng xử lý phân tách nhóm nghìn (`50.000` $\rightarrow$ `50000`), tiền tệ (`100k` $\rightarrow$ `một trăm nghìn`, `50k VNĐ` $\rightarrow$ `năm mươi nghìn đồng`, `$100` $\rightarrow$ `một trăm đô la`), thời gian (`10h30` $\rightarrow$ `mười giờ ba mươi phút`), phân số (`1/2` $\rightarrow$ `một phần hai`), thứ hạng (`top 1` $\rightarrow$ `tốp một`, `No.1` $\rightarrow$ `số một`), dải số (`1-2` $\rightarrow$ `1 đến 2`), từ viết tắt công nghệ/giao tiếp (`AI`, `CPU`, `RAM`, `ROM`, `PC`, `TV`, `USB`, `OK`, `v.v.`, `v/v`, `Dr.`, `Mr.`).
4. **`autodub/speech/tts/capcut_vi.py`**:
   - `sanitize_capcut_text` tích hợp NFC, làm sạch trọn vẹn các loại ngoặc `«»`, `“”`, `[]`, `_`, `~`.
   - Trong `synthesize`: Thêm cơ chế Fallback Retry cấp 2 (làm sạch sâu và thử lại) khi gặp `TTSInvalidText` trước khi ghi silence stub.

---

## 3. Kết quả Kiểm thử & Xác minh

- Đã tạo các bài test mới:
  - `tests/test_vi_numbers_extended.py` (6/6 passed)
  - `tests/test_tts_preservation.py` (3/3 passed)
- Đã chạy kiểm tra toàn bộ suite liên quan (114/114 tests passed):
  - `tests/test_vi_numbers.py`
  - `tests/test_vi_numbers_extended.py`
  - `tests/test_tts_trimmer.py`
  - `tests/test_tts_preservation.py`
  - `tests/test_capcut_tts.py`
  - `tests/test_voice_clip_trim.py`
  - `tests/test_voice_timing_fit.py`
  - `tests/test_voice_sync_benchmark.py`
  - `tests/test_voice_sync_logging.py`
  - `tests/test_audio_dub_mix.py`
  - `tests/test_audio_merger.py`
  - `tests/test_audio_fallbacks.py`
  - `tests/test_timing.py`
  - `tests/test_pipeline_wiring_voice.py`
