# Thiết kế cách sửa lỗi: Hiện tượng Sub hiện nhưng không đọc / Nuốt chữ (Subtitle-TTS Fix Design)

- **Bug ID**: `subtitle-tts-swallow-words`
- **Ngày thiết kế**: 2026-09-01
- **Dựa trên**: Root Cause Analysis tại [.artifacts/bug-fixes/subtitle-tts-swallow-words-root-cause.md](file:///d:/Project/lphvsub-main/.artifacts/bug-fixes/subtitle-tts-swallow-words-root-cause.md)

---

## 1. Mục tiêu và Tiêu chí nghiệm thu (Acceptance Criteria)

1. **AC-1 (Bảo vệ âm đầu)**: Các câu bắt đầu bằng phụ âm vô thanh, âm xát, âm bật (`th`, `s`, `x`, `ph`, `kh`, `h`, `ch`, `tr`, `c/k`, `t`, `p`) không bị xén mất âm đầu.
2. **AC-2 (Không nuốt cả câu)**: Các câu có chứa ký tự đặc biệt, emoji, từ tiếng Anh, hoặc chú thích ngoặc đơn không bị CapCut từ chối (tránh `TTSInvalidText`), không bị rơi vào file im lặng `write_silence` làm mất cả câu thoại.
3. **AC-3 (Phiên âm đầy đủ chữ số, viết tắt, tiền tệ)**: Các dạng `100k`, `500k`, `200tr`, `50.000đ`, `$100`, `10h30`, `1/2`, `AI`, `CPU`, `RAM`, `OK`, `TV`, `USB`, `v.v.`, `v/v`, `top 1`, `No.1` được chuyển thành câu đọc trôi chảy, không dính chữ, không ngọng, không sót chữ.
4. **AC-4 (Unicode NFD $\rightarrow$ NFC)**: Mọi chuỗi văn bản đầu vào đều được chuẩn hóa Unicode NFC để bảo toàn dấu tiếng Việt qua các bộ lọc regex.
5. **AC-5 (Bảo vệ đuôi câu dài)**: Các câu thoại dài được xử lý phân đoạn khéo léo để cả CapCut lẫn VieNeu đọc trọn vẹn 100% nội dung đến từ cuối cùng.

---

## 2. Chi tiết các file và Logic cần sửa

### 📁 File 1: `autodub/speech/tts_trimmer.py`
- **Mục đích**: Chống gọt lẹm phụ âm đầu và âm đuôi câu.
- **Thay đổi logic**:
  - `ENERGY_RATIO`: Giảm từ `0.08` (8%) xuống `0.02` (2% peak RMS) $\rightarrow$ nhận diện được năng lượng nhỏ của phụ âm vô thanh / âm xát đầu câu.
  - `DEFAULT_MARGIN_S`: Tăng từ `0.025` (25ms) lên `0.080` (80ms) $\rightarrow$ tạo vùng đệm an toàn tuyệt đối trước khi phát âm.
  - `ABS_FLOOR`: Giảm từ `0.003` xuống `0.0015` để không nhầm lời thì thầm là khoảng lặng.
  - `min_silence_s`: Đặt `0.06` (chỉ cắt khi khoảng lặng thật sự $\ge$ 60ms).

---

### 📁 File 2: `autodub/media/audio.py`
- **Mục đích**: Loại bỏ việc cắt lặp lại nhiều lần (Double-trimming) làm hỏng âm thanh.
- **Thay đổi logic**:
  - `_LEAD_TRIM_GUARD_S`: Tăng từ `0.12` lên `0.18` (180ms) trong `lead_silence_s`.
  - Trong `postprocess_voice_clip`: Chỉ áp dụng `-ss` nếu `trim_s >= 0.080` (tránh cắt li ti nhiều lần trên file đã qua VAD).

---

### 📁 File 3: `autodub/text/vi_numbers.py`
- **Mục đích**: Mở rộng bộ chuẩn hóa văn bản tiếng Việt toàn diện trước khi đưa vào TTS.
- **Thay đổi logic**:
  1. `unicodedata.normalize('NFC', text)` ngay đầu hàm `normalize_vi_text`.
  2. Lược bỏ / chuẩn hóa các thẻ âm thanh phụ đề: `[Âm nhạc]`, `[tiếng cười]`, `(Cười)`, `(thở dài)`, `*vỗ tay*` $\rightarrow$ loại bỏ khỏi chuỗi đọc TTS để không đọc ngoặc hoặc gây lỗi cú pháp.
  3. Mở rộng bộ quy tắc Regex:
     - Tiền tệ & đơn vị số lượng: `(\d+)\s*(k|K)\b` $\rightarrow$ `\1 nghìn` (ví dụ: `100k` $\rightarrow$ `100 nghìn` $\rightarrow$ `một trăm nghìn`), `(\d+)\s*(tr|triệu|củ)\b` $\rightarrow$ `\1 triệu`, `(\d+)\s*(đ|vnđ|vnd|VND)\b` $\rightarrow$ `\1 đồng`, `\$\s*(\d+)` hoặc `(\d+)\s*\$` $\rightarrow$ `\1 đô la`.
     - Thời gian: `(\d{1,2})h(\d{1,2})` $\rightarrow$ `\1 giờ \2 phút`, `(\d{1,2})h` $\rightarrow$ `\1 giờ`.
     - Phân số: `(\d+)/(\d+)` $\rightarrow$ `\1 phần \2`.
     - Khoảng / dải: `(\d+)\s*[-–—]\s*(\d+)` $\rightarrow$ `\1 đến \2`.
     - Thứ hạng: `\b(top|Top|TOP)\s*(\d+)` $\rightarrow$ `tốp \2`, `\b(No|no|Số)\.?\s*(\d+)` $\rightarrow$ `số \2`, `\b1st\b` $\rightarrow$ `thứ nhất`, `\b2nd\b` $\rightarrow$ `thứ hai`, `\b3rd\b` $\rightarrow$ `thứ ba`.
     - Từ viết tắt công nghệ / giao tiếp: `AI` $\rightarrow$ `A I`, `CPU` $\rightarrow$ `C P U`, `GPU` $\rightarrow$ `G P U`, `RAM` $\rightarrow$ `Ram`, `ROM` $\rightarrow$ `Rom`, `PC` $\rightarrow$ `P C`, `TV` $\rightarrow$ `ti vi`, `USB` $\rightarrow$ `U S B`, `OK` / `ok` $\rightarrow$ `ô kê`, `v.v.` $\rightarrow$ `vân vân`, `v/v` $\rightarrow$ `về việc`, `Dr.` $\rightarrow$ `bác sĩ`, `Mr.` $\rightarrow$ `ông`, `Ms.` $\rightarrow$ `bà`.
     - Ký tự toán / đặc biệt: `@` $\rightarrow$ `a còng`, `&` $\rightarrow$ `và`, `+` $\rightarrow$ `cộng`, `=` $\rightarrow$ `bằng`, `~` $\rightarrow$ `khoảng`, `/` $\rightarrow$ `trên`.

---

### 📁 File 4: `autodub/speech/tts/capcut_vi.py`
- **Mục đích**: Loại bỏ triệt để lỗi `TTSInvalidText` và loại bỏ fallback câm `write_silence`.
- **Thay đổi logic**:
  - `sanitize_capcut_text`:
    - Áp dụng `unicodedata.normalize('NFC', text)`.
    - Thay thế các ký tự ngoặc kép, ngoặc vuông, ngoặc nhọn, gạch dưới, ngã, mũ thành khoảng trắng hoặc dấu phẩy tự nhiên.
    - Đảm bảo regex `_WEIRD_RE` hỗ trợ đầy đủ toàn bộ bảng mã Unicode tiếng Việt dựng sẵn.
  - `synthesize`:
    - Nếu gặp `TTSInvalidText`, tiến hành làm sạch sâu cấp 2 (Aggressive Sanitization: chỉ giữ chữ cái tiếng Việt, số đã đọc và dấu câu chuẩn `. , ! ?`) rồi retry tự động thay vì ghi clip im lặng.

---

### 📁 File 5: `autodub/speech/tts/vieneu_vi.py`
- **Mục đích**: Đảm bảo VieNeu nhận chuỗi đã NFC và chia nhỏ câu siêu dài nếu cần.
- **Thay đổi logic**:
  - Đảm bảo text qua `normalize_vi_text` luôn sạch, không còn ký tự lạ gây ngắt quãng âm thanh trong model VieNeu ONNX.

---

## 3. Kế hoạch Kiểm thử (Test Plan)

1. **Unit Tests mới**:
   - `tests/test_vi_numbers_extended.py`: Kiểm tra toàn diện mọi case chuẩn hóa: `100k`, `50k/kg`, `$200`, `10h30`, `1/2`, `top 1`, `AI`, `CPU`, `OK`, `v.v.`, Unicode NFD $\rightarrow$ NFC, loại bỏ `[Âm nhạc]`, `(Cười)`.
   - `tests/test_tts_trimmer_speech_preservation.py`: Kiểm tra VAD trimmer không làm mất phụ âm đầu của các từ âm xát/bật (`th`, `s`, `x`, `ph`, `kh`, `ch`, `tr`).
   - `tests/test_capcut_sanitizer.py`: Kiểm tra `sanitize_capcut_text` làm sạch hoàn hảo chuỗi chứa emoji, ngoặc, ký tự đặc biệt mà không làm mất nội dung từ vựng.
2. **Regression Tests**:
   - Chạy toàn bộ test suite: `pytest tests/ -v`

---

## 4. Đánh giá Rủi ro (Regression Risk)

- **Rủi ro phụ đề bị đổi theo?**: KHÔNG. Hàm `normalize_vi_text` chỉ được gọi trong tầng TTS (`synthesize`), phụ đề hiển thị (.srt/.ass) vẫn giữ nguyên format gốc của người dùng hoặc translator.
- **Rủi ro hiệu năng?**: TỐI THIỂU. Các phép chuẩn hóa regex và VAD margin 80ms chỉ tốn dưới 1 miligiây mỗi câu, không ảnh hưởng tốc độ pipeline.

---

`TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`
