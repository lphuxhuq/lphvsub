# LPH VSub (VoxDub Studio)

**Ứng dụng lồng tiếng và tạo phụ đề tiếng Việt tự động cho video nước ngoài — nhanh chóng, chính xác, giữ nguyên nhạc nền.**

Ứng dụng desktop cho Windows: Dán link video (YouTube / TikTok / Douyin / Bilibili / Kuaishou / Facebook...) hoặc chọn file video trên máy, chọn giọng đọc tiếng Việt (CapCut TTS / VieNeu-TTS), bấm chạy — nhận về video đã lồng tiếng Việt chuẩn ngữ cảnh, **giữ nguyên âm thanh và nhạc nền gốc**, kèm phụ đề đẹp mắt và trình chỉnh sửa trực quan.

```
Link / File video
   ├─► Tải về (hỗ trợ aria2 16 luồng)  ──►  Tách âm thanh  ──►  Tách nhạc nền (Demucs AI)
   │                                              │
   │                                              └──►  Nhận dạng lời thoại gốc (Whisper / Paraformer)
   │                                                            │
   │                                                            └──►  Dịch AI (Gemini / OpenRouter / SaaS / Thủ công)
   │                                                                          │
   │                                                                          └──►  Đọc giọng tiếng Việt (CapCut / VieNeu)
   │                                                                                        │
   └────────────────────────────────────────────────────────────────────────►  Khớp thời gian  ┘
                                                                                    │
                                                              Trộn nhạc nền + phụ đề + che chữ gốc
                                                                                    │
                                                                              dubbed_video.mp4
```

---

## 🌟 Tính năng nổi bật

- 🎙️ **Đa dạng giọng đọc AI:**
  - **CapCut TTS tiếng Việt:** Giọng đọc tự nhiên, biểu cảm đa dạng (*Cô gái hoạt ngôn, Anh thanh niên, Người kể chuyện, Em bé...*).
  - **VieNeu-TTS:** Bộ 120 giọng đọc offline chạy trực tiếp trên CPU/GPU, không cần mạng.
  - **Clone giọng cá nhân:** Tự nạp file WAV mẫu ngắn để tạo giọng đọc riêng.
- 🤖 **Dịch thuật AI thông minh & Đa chế độ:**
  - **Dịch trực tiếp (Direct AI):** Hỗ trợ nạp **danh sách nhiều API Key** (Gemini, OpenRouter) xoay vòng tự động (Round-robin pool), tự động retry khi gặp giới hạn rate-limit (429).
  - **Dịch qua Control Server:** Quản lý tập trung qua server trung gian.
  - **Dịch thủ công (Offline):** Hỗ trợ xuất prompt dịch tối ưu để dán vào ChatGPT / Claude / Gemini web.
  - **Bảng thuật ngữ (Glossary):** Tự động áp dụng quy tắc xưng hô, dịch tên riêng, nhân vật, thuật ngữ kỹ thuật cố định.
- 🎵 **Tách nhạc nền & Lồng tiếng chuyên nghiệp:**
  - Sử dụng AI **Demucs** để tách sạch lời thoại gốc, giữ nguyên toàn bộ nhạc nền và hiệu ứng âm thanh (SFX).
  - Tự động điều chỉnh tốc độ đọc và thời lượng video để khớp thời gian hoàn hảo.
- 🎬 **Trình chỉnh sửa & Xem trước video trực quan:**
  - Trình phát video tích hợp sẵn trong ứng dụng.
  - Chỉnh sửa từng câu phụ đề / lời dịch, nghe thử câu đơn, bấm đọc lại tức thì cho câu đã sửa.
  - Kéo thả phụ đề, tuỳ chỉnh font chữ, màu sắc, viền, hiệu ứng Karaoke.
  - Công cụ khoanh vùng che chữ/watermark gốc trên video.
- 🌐 **Gemini SRT Translator Pro (Tích hợp sẵn):**
  - Giao diện web dịch phụ đề `.srt`, `.ass`, `.vtt` và video/audio chuyên sâu.
  - Multi-Key Pooling thông minh, tự động hậu xử lý chống sót chữ (Auto CJK) và Live Subtitle Editor với đo tốc độ CPS.
  - Khởi chạy trực tiếp từ thanh **CÔNG CỤ** của app hoặc nhấp đúp file **`chay_dich_srt.bat`**.
- ⚡ **Tốc độ cao & Bền bỉ (Crash-Safe):**
  - Tích hợp công cụ tải đa luồng `aria2` tối đa băng thông mạng.
  - Lưu tiến độ theo từng bước — nếu tắt app giữa chừng, mở lại sẽ tiếp tục từ bước vừa dừng mà không phải chạy lại từ đầu.

---

## 📋 Mục lục

1. [Yêu cầu hệ thống & Cài đặt](#1-yêu-cầu-hệ-thống--cài-đặt)
2. [Hướng dẫn sử dụng nhanh](#2-hướng-dẫn-sử-dụng-nhanh)
3. [Cấu hình dịch thuật AI](#3-cấu-hình-dịch-thuật-ai)
4. [Kho giọng đọc & Cấu hình TTS](#4-kho-giọng-đọc--cấu-hình-tts)
5. [Cấu trúc thư mục kết quả](#5-cấu-trúc-thư-mục-kết-quả)
6. [Công cụ cài thêm (Tùy chọn)](#6-công-cụ-cài-thêm-tùy-chọn)
7. [Dành cho lập trình viên](#7-dành-cho-lập-trình-viên)
8. [Câu hỏi thường gặp (FAQ)](#8-câu-hỏi-thường-gặp-faq)

---

## 1. Yêu cầu hệ thống & Cài đặt

### Yêu cầu cơ bản:
| Phần mềm | Link tải | Lưu ý |
|---|---|---|
| **Windows** | Windows 10 / 11 (64-bit) | |
| **Python 3.10 trở lên** | <https://www.python.org/downloads/> | **Bắt buộc tích chọn ô "Add Python to PATH"** khi cài đặt |
| **ffmpeg (bản full)** | <https://www.gyan.dev/ffmpeg/builds/> (`ffmpeg-release-full.7z`) | Giải nén vào `C:\ffmpeg` và thêm `C:\ffmpeg\bin` vào **PATH** Windows |
| **aria2 (Khuyên dùng)** | Mở PowerShell gõ `winget install aria2.aria2` | Tối ưu tải video Bilibili, YouTube, Douyin bằng 16 kết nối song song |

<details>
<summary><b>📖 Hướng dẫn chi tiết thêm ffmpeg vào PATH</b></summary>

1. Tải file `ffmpeg-release-full.7z` từ gyan.dev và giải nén (dùng 7-Zip).
2. Đổi tên thư mục thành `ffmpeg` rồi chuyển vào ổ `C:\` (đường dẫn dạng `C:\ffmpeg\bin\ffmpeg.exe`).
3. Bấm phím **Windows**, gõ `env` $\rightarrow$ chọn **Edit the system environment variables**.
4. Bấm nút **Environment Variables...** $\rightarrow$ ở mục *System variables* chọn dòng **Path** $\rightarrow$ bấm **Edit** $\rightarrow$ **New** $\rightarrow$ điền `C:\ffmpeg\bin` $\rightarrow$ bấm **OK**.
5. Mở Command Prompt mới, gõ `ffmpeg -version` nếu hiện thông tin phiên bản là thành công.
</details>

---

### Cài đặt tự động trong 1 bước:

1. Tải mã nguồn về máy (bấm **Code $\rightarrow$ Download ZIP** hoặc dùng lệnh `git clone https://github.com/lphuxhuq/lphvsub.git`).
2. Giải nén vào thư mục bạn muốn.
3. Chạy file:
   > **`cai_dat.bat`** (Nhấp đúp chuột để chạy)

File này sẽ tự động:
- Kiểm tra Python và ffmpeg.
- Cài đặt đầy đủ các thư viện phụ thuộc (`requirements.txt`).
- Tạo file cấu hình `.env` từ `.env.example`.
- Tải bộ mô hình nghe chép **Whisper** và giọng đọc **VieNeu**.

---

### Khởi động ứng dụng:

> **Nhấp đúp vào `chay_app.bat`** để mở giao diện phần mềm.

---

## 2. Hướng dẫn sử dụng nhanh

1. Mở ứng dụng $\rightarrow$ Chọn tab **Tạo dự án** ở thanh menu bên trái.
2. **Dán link video** (YouTube, Douyin, TikTok, Bilibili...) hoặc bấm nút chọn file video trên máy tính.
3. Chọn **ngôn ngữ gốc** (tiếng Trung, Anh, Nhật, Hàn...).
4. Chọn **giọng đọc** (chọn giọng CapCut tiếng Việt hoặc giọng VieNeu offline).
5. Bấm **Bắt đầu lồng tiếng**.
6. Sau khi hoàn tất:
   - Bấm **Mở video** để xem thành phẩm.
   - Bấm **Mở thư mục** để lấy video, phụ đề `.srt`, `.ass` hoặc audio lồng tiếng.
   - Bấm **Chỉnh sửa từng câu** để mở Editor tùy chỉnh câu thoại, nghe thử và đọc lại câu nếu muốn.

---

## 3. Cấu hình dịch thuật AI

Ứng dụng hỗ trợ 3 phương thức dịch linh hoạt:

### 🔹 Cách 1: Dịch trực tiếp qua API (Khuyên dùng — Tiện lợi nhất)
Vào trang **Cài đặt** $\rightarrow$ mục **Dịch thuật AI**:
- Chọn Provider: **Gemini** hoặc **OpenRouter**.
- Điền API Key (hỗ trợ dán **nhiều key** cách nhau bằng dấu phẩy hoặc xuống dòng để tự động chia tải xoay vòng).
- Chọn model (ví dụ: `gemini-2.5-flash`, `gemini-2.0-flash` hoặc các model qua OpenRouter).

### 🔹 Cách 2: Dịch qua Control Server
Dành cho hệ thống máy chủ riêng hoặc quản lý nhiều thiết bị:
- Chạy backend trong thư mục `control_server/`.
- Cấu hình biến `VOXDUB_API_URL=http://localhost:3001` trong file `.env`.

### 🔹 Cách 3: Dịch thủ công (Hoàn toàn miễn phí, không cần key)
- Khi pipeline chạy đến bước dịch, ứng dụng sẽ tạo file hướng dẫn `TRANSLATE_PENDING.txt` trong thư mục dự án.
- Bạn chỉ cần sao chép nội dung prompt kèm phụ đề và dán vào ChatGPT / Claude / Gemini trên trình duyệt web, sau đó lưu kết quả vào file `transcript_vi.json` và bấm **Tiếp tục**.

---

## 4. Kho giọng đọc & Cấu hình TTS

### 1. Giọng đọc CapCut tiếng Việt (Online):
- Đa dạng ngữ điệu và cảm xúc: Giọng thanh niên, thiếu nữ, người dẫn truyện, review hài hước, hoạt hình...
- Tự động gọi API tạo giọng chất lượng cao, tốc độ sinh giọng cực nhanh.

### 2. Giọng đọc VieNeu-TTS (Offline):
- 120 giọng mẫu tiếng Việt chất lượng cao đi kèm trong thư mục `voices/preset_voices_vn/`.
- Chạy hoàn toàn offline trên CPU/GPU.

### 3. Tự thêm giọng đọc mẫu của bạn:
- Chuẩn bị file `.wav` dài khoảng 5–10 giây (giọng nói rõ ràng, không lẫn tạp âm/nhạc nền).
- Thả file vào thư mục `voices/custom/` và chạy `nap_giong_doc.bat` để nạp vào hệ thống.

---

## 5. Cấu trúc thư mục kết quả

Mỗi video xử lý xong sẽ được lưu trong thư mục `output/`:

```
output/VN/YYYYMMDD_HHMMSS_vi/
├── dubbed_video.mp4                ← Video thành phẩm đã lồng tiếng & ghép phụ đề
├── transcript_vi.srt               ← File phụ đề tiếng Việt chuẩn
├── transcript_vi.ass               ← File phụ đề nâng cao (hỗ trợ karaoke/style)
├── youtube/                        ← Gợi ý tiêu đề, mô tả, hashtag, prompt thumbnail
└── data/                           ← Dữ liệu trung gian & cache
    ├── transcript_original.json    ← Lời gốc AI nhận dạng
    ├── transcript_vi.json          ← Bản dịch tiếng Việt
    ├── original_audio.wav          ← Âm thanh gốc
    ├── vocals.wav / no_vocals.wav  ← Tách giọng và tách nhạc nền (Demucs)
    ├── audio_vi_full.wav           ← Toàn bộ giọng đọc tiếng Việt đã ghép
    ├── segments/                   ← Từng câu đọc riêng lẻ (phục vụ sửa & cache)
    └── quality_report.json         ← Báo cáo đánh giá độ khớp thời gian
```

---

## 6. Công cụ cài thêm (Tùy chọn)

| File / Lệnh | Công dụng |
|---|---|
| `winget install aria2.aria2` | Cài đặt công cụ tăng tốc tải video đa luồng `aria2` |
| `cai_them_paraformer.bat` | Bộ nhận dạng tiếng Trung **Paraformer** (nhanh và chính xác hơn Whisper đối với tiếng Trung) |
| `cai_them_douyin.bat` | Cài đặt trình duyệt tự động để tải video Douyin chất lượng gốc |
| `nap_giong_doc.bat` | Nạp hoặc cập nhật lại danh sách giọng đọc trong `voices/` |

---

## 7. Dành cho lập trình viên

### Cấu trúc mã nguồn:

```
lphvsub/
├── autodub/                 # Lõi xử lý chính (Core Pipeline)
│   ├── pipeline.py          # Quản lý luồng xử lý toàn diện
│   ├── editor.py            # Logic chỉnh sửa từng câu, đọc lại & xuất video
│   ├── batch.py             # Xử lý video hàng loạt (Crash-safe)
│   ├── config.py            # Đọc & kiểm tra cấu hình .env
│   ├── diskspace.py         # Kiểm tra dung lượng ổ đĩa & dọn dẹp
│   ├── media/               # Tải video, xử lý audio, video, phụ đề, che chữ, Demucs
│   ├── speech/              # Nhận dạng giọng nói (ASR) & Tổng hợp giọng nói (TTS)
│   │   ├── asr/             # Whisper, Paraformer
│   │   └── tts/             # VieNeu-TTS, CapCut TTS
│   └── text/                # Dịch thuật (Direct AI, SaaS), bảng thuật ngữ Glossary
│
├── autodub_gui/             # Giao diện người dùng PySide6 (Qt)
│   ├── app.py               # Cửa sổ chính & điều hướng trang
│   ├── workers.py           # Luồng xử lý nền (QThread)
│   ├── pages/               # Giao diện các trang chức năng
│   └── video/               # Trình phát video & timeline tích hợp
│
├── control_server/          # Backend Node.js điều khiển & Gateway AI (Tùy chọn)
├── website/                 # Landing page & trang quản trị web
├── scripts/                 # Kịch bản cài đặt, đóng gói build .exe
└── tests/                   # Bộ kiểm thử tự động (Unit tests)
```

### Chạy kiểm thử:
```bash
py -m pytest -q
```

### Đóng gói file `.exe` cho Windows:
```bash
py scripts/build_exe.py
```

---

## 8. Câu hỏi thường gặp (FAQ)

<details>
<summary><b>1. Máy tính không có card rời (GPU NVIDIA) có dùng được không?</b></summary>
Hoàn toàn dùng được! Toàn bộ pipeline (Whisper, VieNeu, Demucs, FFmpeg) đều hỗ trợ chạy tốt trên CPU. Nếu có GPU NVIDIA với CUDA, phần mềm sẽ tự động nhận diện và tăng tốc xử lý.
</details>

<details>
<summary><b>2. Giọng đọc tiếng Việt bị nhanh hoặc tràn sang câu sau?</b></summary>
Tiếng Việt khi dịch từ tiếng Trung/Anh thường dài hơn 15–25%. Bạn có thể:
1. Vào **Trình chỉnh sửa** để rút gọn lại câu văn cho súc tích.
2. Hoặc trong phần Cài đặt nâng cao, chỉnh `VIDEO_SPEED=0.9` để làm chậm nhẹ video tạo khoảng trống cho giọng đọc.
</details>

<details>
<summary><b>3. Báo lỗi khi ghi phụ đề trực tiếp vào video (sub cứng)?</b></summary>
Hãy chắc chắn rằng bạn đã cài bản **ffmpeg full** (có hỗ trợ libass) theo đúng hướng dẫn ở Mục 1, hoặc tạm thời chọn chế độ xuất phụ đề **rời** (`.srt`).
</details>

---

## 📄 Giấy phép & Điều khoản

- Mã nguồn phát triển theo giấy phép **MIT** — xem chi tiết tại [LICENSE](LICENSE).
- Vui lòng tuân thủ bản quyền nội dung gốc và **không sử dụng phần mềm để giả mạo giọng nói của người khác**.

---

⭐ **Nếu thấy dự án hữu ích, hãy tặng 1 Star trên GitHub để ủng hộ đội ngũ phát triển nhé!**
