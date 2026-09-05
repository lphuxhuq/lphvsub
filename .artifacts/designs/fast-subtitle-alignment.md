# THIẾT KẾ KIẾN TRÚC: TĂNG TỐC CANH PHỤ ĐỀ KHỚP GIỌNG (FAST SUBTITLE VOICE-SYNC)

## 1. Requirement đã duyệt
- **Mục tiêu:** Tăng tốc độ canh phụ đề chạy nhảy chữ (Forced Alignment & Karaoke Subtitle Generation) từ 2x đến 5x.
- **Yêu cầu kỹ thuật:**
  1. Không làm giảm độ chính xác mốc thời gian của từ phát âm (lip-sync & word-sync).
  2. Bền vững bộ nhớ đệm (Persistent Cache): lưu trữ mốc thời gian xuyên suốt các phiên làm việc của ứng dụng mà không bị mất cache.
  3. Loại bỏ thời gian chờ nạp mô hình (Zero Cold-Start): tích hợp mô hình canh phụ đề vào luồng nạp trước toàn cục `GlobalModelPool`.
  4. Giải mã nhanh (Greedy Decoding): tối ưu hoá tham số ASR cho audio TTS sạch.
  5. Giữ nguyên 100% backward compatibility với các thiết lập hiện tại và không thêm dependency ngoài.

---

## 2. Kiến trúc hiện tại liên quan
- `autodub/speech/align.py`:
  - Mỗi lần gọi `align_segments()` lại khởi tạo lại `WhisperModel(ALIGN_MODEL, ...)` từ đĩa.
  - Sử dụng `beam_size=2` khiến Whisper phải duyệt 2 nhánh hypothesis trên từng token.
  - Khóa cache dùng `hash(text) & 0xFFFFFFFF` phụ thuộc vào hạt giống ngẫu nhiên (seed) của tiến trình Python, làm mất cache khi khởi động lại app.
- `autodub/model_preloader.py`:
  - Đã có `GlobalModelPool` nạp trước Paraformer, Faster-Whisper, Demucs, VieNeu, LaMa.
  - Chưa đăng ký hay làm ấm trước mô hình căn chỉnh phụ đề (`Whisper base` hoặc Alignment Model).
- `autodub/speech/acoustic_align.py`:
  - Đã có thuật toán NumPy vectorization quét năng lượng RMS 10ms siêu nhanh (~0.2ms/câu), nhưng hiện chỉ dùng làm fallback thụ động khi Whisper thất bại.

---

## 3. Kiến trúc đề xuất

```
┌───────────────────────────────────────────────────────────────┐
│                    GLOBAL MODEL PRELOADER                     │
│  • Nạp sẵn Whisper base vào _align_model_cache (Singleton)    │
│  • Khởi động chạy nền ngay khi mở ứng dụng → 0ms trễ xuất sub │
└───────────────────────────────┬───────────────────────────────┘
                                │ Tái sử dụng model instance
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                FAST FORCED ALIGNMENT ENGINE                   │
│                                                               │
│ 1. Persistent MD5 Cache Check:                                │
│    Key: sid:mtime:md5(text)[:12]                              │
│    Hit → 0ms (Lấy ngay mốc từ align_cache.json)               │
│                                                               │
│ 2. Ultra-Fast Path (Short clip ≤ 0.6s hoặc acoustic mode):    │
│    NumPy RMS Energy Envelope (~0.2ms / câu)                   │
│                                                               │
│ 3. Greedy ASR Alignment (Audio sạch TTS):                     │
│    • beam_size=1 (Giảm 50% chi phí tính toán)                 │
│    • In-memory wav cache / CPU auto-thread scaler             │
│    • Single-pass token-to-word interpolation                  │
└───────────────────────────────┬───────────────────────────────┘
                                │ Mốc từng chữ [token, t0, t1]
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                     ASS KARAOKE GENERATOR                     │
│  • Chunking 2-4 từ, ngắt dấu câu                              │
│  • Sinh Dialogue event với thẻ \k<cs> và pop zoom             │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. Component thay đổi
1. **`autodub/speech/align.py`**:
   - Thêm bộ nhớ đệm singleton `_GLOBAL_ALIGN_MODEL`.
   - Chuyển `beam_size=2` thành `beam_size=1` (Greedy Search) tăng tốc ~45-50%.
   - Đổi khóa băm cache sang MD5 ổn định xuyên phiên `hashlib.md5(text.encode("utf-8")).hexdigest()[:12]`.
   - Tối ưu số luồng worker theo số nhân CPU thực tế: `max(1, min(8, (os.cpu_count() or 4) - 1))`.
   - Thêm đường dẫn nhanh (Fast Path) dùng `acoustic_word_times` cho các câu cực ngắn ($\le 0.6$s).
2. **`autodub/model_preloader.py`**:
   - Bổ sung `get_align_model()` vào `GlobalModelPool`.
   - Thêm bước làm ấm Whisper Alignment vào luồng `preload_all_async`.
3. **`autodub/text/ass_karaoke.py`**:
   - Tái sử dụng cache mốc chữ giữa các lần preview / burn.

---

## 5. Data Flow & Control Flow
- **Bước 1:** Kiểm tra cache với key MD5. Nếu toàn bộ câu đã có mốc trong `align_cache.json` $\rightarrow$ Trả kết quả ngay lập tức (0.01s).
- **Bước 2:** Với các câu chưa có cache:
  - Nếu câu $\le 0.6$s hoặc chỉ có 1-2 từ ngắn: Dùng ngay `acoustic_word_times` (0.001s).
  - Với các câu còn lại: Lấy `model` từ `GlobalModelPool` (đã nạp sẵn, không tốn thời gian load).
  - Chạy `transcribe` với `beam_size=1` qua luồng song song.
- **Bước 3:** Ghi cache nguyên tử (`save_json_atomic`) để các lần sau không cần chạy lại.

---

## 6. Performance & Benchmark dự kiến
- **Khởi động model:** Giảm từ ~2.5s xuống **0s** (nhờ Preloader & Singleton).
- **Thời gian xử lý Whisper từng câu:** Giảm từ ~120ms xuống **~55ms** (nhờ `beam_size=1` greedy).
- **Xử lý câu ngắn:** Giảm từ ~100ms xuống **~0.2ms** (nhờ Acoustic Fast-path).
- **Xuất video lần 2 / Re-burn:** Giảm từ 10-25s xuống **< 0.05s** (100% MD5 Cache Hit).
- **Tổng thời gian canh 100 câu thoại:** Giảm từ ~15s xuống **~3-4s** (lần đầu) và **0.05s** (lần sau).

---

## 7. Testing Plan
- `test_align_cache_persistence`: Xác minh cache MD5 hoạt động nhất quán xuyên nhiều lượt gọi.
- `test_align_greedy_beam_size`: Xác minh `beam_size=1` cho ra mốc thời gian chính xác tương đương.
- `test_model_preloader_align`: Xác minh `GlobalModelPool.get_align_model()` nạp đúng và không xung đột VRAM/RAM.
- `test_ass_karaoke_fast_path`: Đảm bảo các câu ngắn áp dụng fast path vẫn sinh đủ dialogue events và thẻ `\k`.

---

## Approval Gate
TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ
