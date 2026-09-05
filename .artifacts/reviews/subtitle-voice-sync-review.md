# CODE REVIEW — Hệ thống Canh Phụ Đề Khớp Giọng Đọc (Voice-Synchronized Subtitle & Karaoke Alignment)

**Mã đối tượng:** `autodub/speech/boundaries.py`, `autodub/media/timing.py`, `autodub/speech/align.py`, `autodub/speech/acoustic_align.py`, `autodub/text/ass_karaoke.py`, `autodub/text/subtitles.py`  
**Ngày review:** 2026-09-05  
**Reviewer:** Antigravity Orchestrator & Reviewer  
**Kết luận:** **PASS**

---

## 1. Tổng quan & Mục tiêu hệ thống

Hệ thống có nhiệm vụ tạo phụ đề chạy nhảy chữ (kiểu CapCut Karaoke) khớp từng âm tiết với giọng đọc lồng tiếng (TTS), đảm bảo:
1. **Khớp nhịp giọng thực tế:** Chữ sáng lên chính xác lúc giọng đọc phát âm, không bị trôi dần qua thời gian (drift-free).
2. **Khả năng phục hồi cao (Fault-tolerant Fallback):** Khi AI ASR không nhận diện được chữ hoặc thiếu audio, hệ thống tự động rơi về tầng phổ năng lượng âm thanh (Acoustic RMS Envelope) và tầng ước lượng trọng số âm tiết (Syllable Heuristic), không bao giờ làm gián đoạn hay hỏng video xuất ra.
3. **Hiệu năng & Tái sử dụng:** Cache thông minh theo `(sid, mtime, hash)` tránh việc nhận diện lại audio đã sinh; xử lý song song đa luồng tận dụng CPU/GPU.

---

## 2. Kiến trúc 3 tầng kỹ thuật (3-Tier Architecture)

```
[Audio Gốc / VAD]
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ TẦNG 1: BIÊN PHÁT ÂM & VOICE-SYNC SCHEDULER                │
│ • boundaries.py: refine_speech_boundaries (RMS tỷ lệ 0.12)  │
│ • timing.py: plan_voice_placements (dub_start ≈ speech_start│
│   drift ≤ 0.15s, atempo 0.90-1.15x, silence-aware)          │
└──────────────────────────────┬──────────────────────────────┘
                               │ (WAV lồng tiếng studio-sạch)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ TẦNG 2: FORCED ALIGNMENT ĐA TẦNG (MỐC THỜI GIAN TỪNG TỪ)   │
│ • Cấp 1 (Primary): Whisper base word_timestamps             │
│   → Ánh xạ _map_words 1:1 hoặc nội suy vị trí               │
│ • Cấp 2 (Secondary): acoustic_align.py                      │
│   → Quét phổ RMS 10ms WAV, phát hiện voice burst thực       │
│ • Cấp 3 (Tertiary): estimate_word_times                     │
│   → Chia âm tiết có trọng số dấu câu (_PAUSE_WEIGHT)        │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Mốc từng từ [w, t0, t1])
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ TẦNG 3: DỰNG CỤM & SINH KHUNG PHỤ ĐỀ ASS KARAOKE            │
│ • ass_karaoke.py: chunk_words (gom 2-4 từ, ngắt dấu câu)    │
│ • libass formatting: thẻ \k<centi-giây>, pop zoom (82%→100%)│
│ • Khử chồng phụ đề (Anti-overlap): cur["t1"] = max(...)     │
│ • subtitles.py: refresh_subtitles tích hợp burn re-encode   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Ma trận kiểm tra chi tiết (Inspection Matrix)

| Tiêu chí | Điểm kiểm tra thực tế | Đánh giá | Trạng thái |
|---|---|---|---|
| **Boundary Precision** | `refine_speech_boundaries`: thu hẹp VAD bằng năng lượng RMS, biên an toàn lead/tail 60ms, không cắt mất phụ âm đầu/cuối. | Chuẩn xác, loại bỏ khoảng tĩnh giả của VAD. | **PASS** |
| **Drift-free Scheduling** | `plan_voice_placements`: neo mỗi câu vào `speech_start`, khống chế trôi ≤ 0.15s, tính `atempo` cục bộ, không dồn tích luỹ sang các câu sau. | Độc lập từng slot, không có hiện tượng "domino drift". | **PASS** |
| **Forced Alignment** | `align.py`: dùng `Whisper base` trên WAV sạch với `initial_prompt`, chạy song song `ThreadPoolExecutor`. | Tận dụng tốt CPU đa nhân / GPU CUDA. | **PASS** |
| **Word Mapping** | `_map_words`: xử lý khớp 1:1, nội suy khi lệch từ, vá thứ tự thời gian đơn điệu (`fixed.append((token, t0, t1))`). | Không bị thời gian âm, không nhảy lùi thời gian. | **PASS** |
| **Acoustic Fallback** | `acoustic_align.py`: quét RMS 10ms frame, ngưỡng `0.08 * peak` và sàn `0.003`. | Bù đắp hoàn hảo khi Whisper bỏ sót câu ngắn dưới 40% từ. | **PASS** |
| **Chunking & Rhythm** | `chunk_words`: gom 2-4 từ, ưu tiên ngắt tại `,.!?…;:`. | Cụm từ tự nhiên, ngắt đúng hơi thở người xem. | **PASS** |
| **Karaoke Coloring** | Thẻ ASS `\k<cs>`: hoán đổi `PrimaryColour` (màu highlight `#FFD54A`) và `SecondaryColour` (màu chữ gốc). | Chuẩn đặc tả SubStation Alpha v4.00+. | **PASS** |
| **Anti-Overlap** | `cur["t1"] = max(cur["t0"] + 0.10, nxt["t0"])`. | Không có hiện tượng chữ cụm này đè lên cụm sau. | **PASS** |
| **Cache & Resume** | Cache lưu theo `sid:mtime:hash(text)` dưới dạng JSON atomic. | Chỉ câu sửa lời hoặc re-TTS mới phải align lại. | **PASS** |

---

## 4. Phân tích rủi ro & Phát hiện (Findings)

### Phân loại lỗi:
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 1
- **INFO:** 2

### Chi tiết các mục cần ghi nhận:
1. **[LOW] Hash key trong bộ nhớ cache:**
   - *Vị trí:* `autodub/speech/align.py` dòng 182: `key = f"{sid}:{int(os.path.getmtime(wav))}:{hash(text) & 0xFFFFFFFF}"`
   - *Phân tích:* Hàm `hash()` nội tại của Python có cơ chế ngẫu nhiên hóa hạt giống (SipHash randomization) giữa các tiến trình khác nhau nếu không thiết lập `PYTHONHASHSEED`. Do đó, nếu người dùng tắt app và mở lại ở tiến trình khác, một số key trong `align_cache.json` có thể không hit mà phải tính lại một lần.
   - *Đánh giá tác động:* Rất thấp. Key vẫn có `sid` và `mtime`, nếu trượt cache thì Whisper chỉ chạy lại trong vài giây rồi cập nhật key mới; không gây sai lệch dữ liệu hay crash. Có thể nâng cấp dùng `hashlib.md5(text.encode()).hexdigest()[:8]` ở đợt dọn dẹp tiếp theo.

2. **[INFO] Tốc độ khi chạy trên CPU không có card đồ họa rời:**
   - Với các video tài liệu dài 600–700 câu trên máy tính CPU yếu, lượt align đầu tiên có thể mất 15–30 giây. Hệ thống đã có `progress_cb` cập nhật tiến trình rõ ràng và cơ chế đa luồng `_align_workers()` nên trải nghiệm người dùng vẫn mượt mà.

3. **[INFO] Phụ đề ghi đè (Subtitle Override):**
   - Trong `ass_karaoke.py` (dòng 120), khi người dùng cố ý nhập nội dung phụ đề tiếng Việt khác với lời đọc TTS (`has_subtitle_override == True`), hệ thống tự động ngắt mốc ASR và chuyển sang ước lượng theo thời lượng câu. Đây là thiết kế chính xác để tránh tình trạng chữ hiển thị không khớp với từ phát âm.

---

## 5. Bằng chứng kiểm thử tự động (Test Verification Evidence)

Tất cả các bộ test kiểm tra subtitle, ASS karaoke, timing, và speech boundaries đều đạt **100% PASS**:

1. **Test ASS Karaoke (`tests/test_ass_karaoke.py`):**
   - `test_estimate_covers_full_duration`: PASS (mốc phủ trọn thời lượng, đơn điệu không chồng lấn).
   - `test_estimate_pause_weight_after_comma`: PASS (dấu phẩy ngân dài hơn từ thường).
   - `test_chunk_size_respected` & `test_chunk_breaks_early_at_punctuation`: PASS (ngắt cụm chuẩn xác).
   - `test_ass_time_format` & `test_escape_strips_override_braces`: PASS (chuẩn định dạng centi-giây).
   - `test_build_karaoke_ass_end_to_end`: PASS (sinh file `.ass` hoàn chỉnh).
   - **Kết quả:** `15 passed in 0.42s`.

2. **Test Subtitle & Timing (`tests/test_subtitle.py`, `tests/test_timing.py`, `tests/test_speech_boundaries.py`):**
   - **Kết quả:** `51 passed in 0.82s`.

---

## 6. Kết luận

Hệ thống canh phụ đề chạy khớp giọng đọc (`voice-sync & ass-karaoke`) có kiến trúc vững chắc, xử lý ranh giới âm thanh tỉ mỉ, có đầy đủ 3 tầng fallback chống lỗi, đạt chuẩn chất lượng cao và vận hành ổn định.

**KẾT QUẢ ĐÁNH GIÁ:** **PASS**
