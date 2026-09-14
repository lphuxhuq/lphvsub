# Project Map — LPH VSub (VoxDub Studio / NovaSub)

- **Trạng thái**: `TRẠNG THÁI: HOÀN THÀNH`
- **Phiên bản hệ thống**: `3.0.0` (`ĐÃ XÁC MINH`: `pyproject.toml`, `autodub/__init__.py`, `control_server/package.json`, `website/package.json`)
- **Ngày kiểm toán**: 2026-09-14
- **Phạm vi kiểm toán**: Toàn bộ dự án (`autodub/`, `autodub_gui/`, `control_server/`, `website/`, `tests/`, `scripts/`)

---

## 1. Tổng quan

**LPH VSub** (tên thương mại: **VoxDub Studio** / **NovaSub**) là một nền tảng hoàn chỉnh bao gồm ứng dụng desktop Windows, dịch vụ SaaS backend trung tâm và trang web thương mại/quản trị phục vụ việc tự động hoá quy trình lồng tiếng (dubbing) và làm phụ đề video đa ngôn ngữ sang tiếng Việt:

```
Video (URL / Local File)
   │
   ├─► 1. Tải video (Smart Downloader: aria2 / yt-dlp / Douyin Playwright)
   ├─► 2. Tách âm thanh (HQ 44.1kHz Stereo mix + 16kHz Mono ASR)
   ├─► 2.5 Tách nhạc nền & lời nói (Demucs AI qua .venv-gpu IPC Worker hoặc Ducking)
   ├─► 3. Nhận dạng lời thoại ASR (Whisper / Paraformer ONNX + VAD + Acoustic Alignment)
   ├─► 3.6 Phân cụm người nói & Phân vai (Diarization F0 + Voice Director Auto-Casting)
   ├─► 4. Dịch thuật thông minh (Gemini / OpenRouter Direct Multi-Key / SaaS Gateway / Browser)
   ├─► 5. Tổng hợp giọng đọc TTS (VieNeu-TTS Offline ONNX / CapCut TTS Online Multi-Voice)
   ├─► 5.5 / 6. Canh chỉnh nhịp & Khớp thời gian (Atempo Stretch, Scene Cut Snapping, No Overlap)
   ├─► 7. Biên tập & Xuất video (Parallel Chunked NVENC/QSV/AMF/CPU, Subtitles ASS/SRT, Logo, Watermark, Inpaint)
   └─► 8. Tạo siêu dữ liệu mạng xã hội (YouTube Title/Description/Tags, Thumbnail Studio, Viral Clipper)
```

**`ĐÃ XÁC MINH`** — Đã kiểm chứng qua mã nguồn `autodub/pipeline.py`, `autodub_gui/app.py`, `control_server/src/app.js`, và toàn bộ bộ test suite (1337 test cases passed).

---

## 2. Technology Stack

### 2.1. Python Desktop Core (`autodub` + `autodub_gui`)
- **Ngôn ngữ**: Python 3.10+ (đang chạy trên môi trường Python 3.14 / PySide6 6.11) (`ĐÃ XÁC MINH`)
- **Desktop GUI**: PySide6 (Qt 6.6+), kiến trúc đa luồng `QThread`, custom design token & stylesheet dark mode (`ĐÃ XÁC MINH`)
- **ASR (Speech-to-Text)**:
  - `faster-whisper` (CTranslate2, GPU CUDA / CPU) (`ĐÃ XÁC MINH`)
  - `sherpa-onnx` Paraformer tiếng Trung (chạy IPC worker riêng) (`ĐÃ XÁC MINH`)
- **TTS (Text-to-Speech)**:
  - `VieNeu-TTS` (120 giọng tiếng Việt offline ONNX, chạy subprocess độc lập) (`ĐÃ XÁC MINH`)
  - `CapCut TTS` (API online tiếng Việt với cơ chế device pool và proxy) (`ĐÃ XÁC MINH`)
- **Tách âm thanh (Source Separation)**: Meta Demucs (`htdemucs`), chạy trong virtualenv chuyên dụng GPU `.venv-gpu` (`ĐÃ XÁC MINH`)
- **Xử lý Video & Audio**:
  - `ffmpeg` & `ffprobe` (gọi qua subprocess bảo vệ tràn buffer, HW acceleration: `h264_nvenc`, `h264_qsv`, `h264_amf`, `libx264`) (`ĐÃ XÁC MINH`)
  - `pydub`, `numpy`, `audioop-lts` (`ĐÃ XÁC MINH`)
  - `opencv-python-headless` cho image processing & watermark/inpaint mask (`ĐÃ XÁC MINH`)
- **Tải video**: `yt-dlp`, `aria2` (16 luồng song song), `playwright` cho Douyin gốc (`ĐÃ XÁC MINH`)
- **Lưu trữ & Cache**:
  - Universal Pipeline Cache: SQLite (chế độ WAL, thread-safe, SHA256 content fingerprinting) (`ĐÃ XÁC MINH`)
  - `securestore`: Mã hoá AES-256-GCM bảo vệ file trung gian (`ĐÃ XÁC MINH`)
- **Testing**: `pytest 9.1+`, `pytest-qt` (1337 tests) (`ĐÃ XÁC MINH`)
- **Linting & Formatting**: `ruff` ( cấu hình trong `pyproject.toml`, 100% pass) (`ĐÃ XÁC MINH`)

### 2.2. SaaS Backend (`control_server`)
- **Runtime**: Node.js 20+ (`ĐÃ XÁC MINH`)
- **Framework**: Fastify 5.1 (`ĐÃ XÁC MINH`)
- **Plugins & Middleware**: `@fastify/cors`, `@fastify/helmet`, `@fastify/rate-limit`, `@fastify/static` (`ĐÃ XÁC MINH`)
- **Cơ sở dữ liệu**: MongoDB 7+ qua `mongoose 8.8` (`ĐÃ XÁC MINH`)
- **Mã hoá & Bảo mật**: AES-256-CBC (`APP_ENCRYPTION_KEY` 64 hex), JWT device tokens, timing-safe equality (`ĐÃ XÁC MINH`)
- **Thanh toán**: PayOS API & Webhook (HMAC SHA-256 checksum) (`ĐÃ XÁC MINH`)
- **AI Gateway**: Proxy Gemini / OpenAI / DeepSeek / OpenRouter có bảo vệ ví tín dụng (Credit Hold / Commit) (`ĐÃ XÁC MINH`)
- **Kiểm thử**: Node.js test runner (`node --test tests/*.test.js`, 59/59 tests pass) (`ĐÃ XÁC MINH`)

### 2.3. Web Frontend (`website`)
- **Build tool**: Vite 5.4 (`ĐÃ XÁC MINH`)
- **UI Framework**: React 18.3, React Router DOM 6.28 (`ĐÃ XÁC MINH`)
- **State Management**: Zustand 5.0 (`ĐÃ XÁC MINH`)
- **Styling**: Tailwind CSS 3.4, `@fontsource/be-vietnam-pro` (`ĐÃ XÁC MINH`)
- **Animations & Effects**: Framer Motion 13, `canvas-confetti`, `qrcode.react` (`ĐÃ XÁC MINH`)

---

## 3. Cấu trúc Project

```
lphvsub-main/
├── autodub/                         # Lõi xử lý nghiệp vụ chính (Core)
│   ├── __init__.py                  # Public API v3.0.0
│   ├── pipeline.py                  # Orchestrator chính: 12 bước xử lý DubPipeline
│   ├── pipeline_cache.py            # Universal SQLite Cache (ASR, Demucs, TTS, Translation)
│   ├── editor.py                    # Logic hậu kỳ, sửa câu, re-TTS, re-export
│   ├── config.py                    # Cấu hình hệ thống từ .env (Settings dataclass)
│   ├── checkpoint_store.py          # Quản lý preset cấu hình dự án
│   ├── saas_client.py               # Kết nối HTTP client tới Control Server
│   ├── securestore.py               # Mã hoá AES-256-GCM file trung gian
│   ├── model_preloader.py           # Pre-warm mô hình AI trong background
│   ├── speech/                      # Gói ASR & TTS
│   │   ├── transcriber.py           # Faster-Whisper wrapper
│   │   ├── paraformer_transcriber.py# Paraformer wrapper
│   │   ├── diarization.py           # Speaker diarization & clustering
│   │   ├── speaker_profiler.py      # Phân tích F0 pitch & giới tính
│   │   ├── voice_director.py        # Tự động gán giọng theo nhân vật
│   │   └── tts/                     # VieNeu-TTS & CapCut TTS engines
│   ├── media/                       # Gói xử lý Media & Video
│   │   ├── video.py                 # Ghép video, filter complex, HW encode
│   │   ├── parallel_export.py       # Xuất video song song theo chunk keyframe
│   │   ├── audio.py                 # Chuẩn hoá âm thanh, loudnorm, mix nhạc nền
│   │   ├── vocal_separator.py       # Tách vocal qua Demucs
│   │   ├── subtitle.py              # Xây dựng filtergraph ASS/SRT, blur, banner
│   │   ├── timing.py                # Thuật toán canh nhịp và scene cut guard
│   │   ├── downloader.py            # Smart Downloader (yt-dlp, aria2)
│   │   ├── douyin.py                # Douyin Playwright engine
│   │   ├── dimension.py             # Chuẩn hoá kích thước chẵn (Even Dimensions)
│   │   └── inpaint/                 # LaMa ONNX & VSR inpainting
│   ├── text/                        # Dịch thuật & xử lý văn bản
│   │   ├── translate_direct.py      # Dịch trực tiếp multi-key (Gemini, OpenRouter)
│   │   ├── translate_saas.py        # Dịch qua SaaS Control Server
│   │   ├── translate_hint.py        # Tính toán CPS budget & slot timing
│   │   ├── glossary.py              # Bảng thuật ngữ xưng hô cố định
│   │   └── fusion.py                # Ghép lời ASR và OCR phụ đề gốc
│   ├── content/                     # Tạo siêu dữ liệu mạng xã hội
│   │   ├── generator.py             # Sinh tiêu đề, mô tả, hashtag qua AI
│   │   └── viral_clipper.py         # Tìm đoạn viral highlight và cắt clip ngắn
│   └── tools/gemini_srt_ui/         # Web tool dịch file phụ đề rời (Flask)
│
├── autodub_gui/                     # Giao diện người dùng PySide6
│   ├── app.py                       # MainWindow, router, pre-warming, update check
│   ├── workers.py                   # QThread background workers (DubWorker, BatchWorker)
│   ├── shell.py                     # Sidebar, header, notification, status card
│   ├── theme.py & tokens.py         # Design system, màu sắc, font, spacing
│   ├── pages/                       # 15 trang chức năng (Tạo dự án, Editor, Batch,...)
│   ├── ui/                          # 25+ Qt widgets dùng chung (cards, modal, table...)
│   └── video/                       # Trình phát video, timeline kéo thả phụ đề
│
├── control_server/                  # Backend Node.js SaaS API Gateway
│   ├── server.js                    # Entry point kiểm tra env & khởi động timers
│   ├── src/app.js                   # Fastify app factory, rate limit, static serve
│   ├── src/routes/                  # Các endpoint /v1/ (ai, billing, device, holds, config)
│   ├── src/services/                # Nghiệp vụ: payos, credit, hold, device, ai-gateway
│   └── src/models/                  # Mongoose models: Device, CreditHold, Order,...
│
├── website/                         # Giao diện Web (Landing page & Admin portal)
│   ├── src/App.jsx                  # Router chính
│   ├── src/pages/                   # Trang bán hàng, thanh toán PayOS, tài liệu, admin
│   └── src/store/                   # Quản lý state Zustand (orders, admin)
│
├── tests/                           # Bộ 151 files kiểm thử tự động (1337 test cases)
├── scripts/                         # Kịch bản build exe, benchmark, cài đặt môi trường
├── .env.example                     # File mẫu cấu hình desktop app
├── pyproject.toml                   # Cấu hình project Python, dependencies, ruff, pytest
└── README.md                        # Hướng dẫn sử dụng & kiến trúc tổng thể
```

**`ĐÃ XÁC MINH`** — Đã quét toàn bộ cây thư mục và cấu trúc file.

---

## 4. Kiến trúc Hệ thống

### 4.1. Mô hình Phân tách Trách nhiệm (Decoupled Layered Architecture)
1. **Lớp Giao diện (Presentation Layer)**: `autodub_gui/` thuần tuý lắng nghe và phát tín hiệu Qt signals. Không chứa logic xử lý nặng.
2. **Lớp Điều phối Công việc (Worker / Thread Layer)**: `autodub_gui/workers.py` bọc pipeline trong `QThread`, chuyển đổi exception thành signal `failed`, emit tiến độ tới thanh `QProgressBar`.
3. **Lớp Điều hành Xử lý (Orchestration Layer)**: `DubPipeline` trong `autodub/pipeline.py` nhận `DubRequest` bất biến, quản lý trạng thái chuyển tiếp qua các step.
4. **Lớp Xử lý Chuyên biệt (Domain Services)**:
   - `speech/`: ASR, Diarization, TTS
   - `media/`: FFmpeg rendering, Parallel chunking, Vocal separation, Downloader
   - `text/`: Translation pooling, Glossary, OCR fusion
5. **Lớp Lưu trữ & Hạ tầng (Infrastructure Layer)**:
   - `PipelineCache` (SQLite WAL) lưu vết và tái sử dụng kết quả giữa các dự án.
   - `SecureStore` (AES-256-GCM) bảo vệ tài sản số nếu cần khoá dự án.

### 4.2. Cơ chế Cách ly Tiến trình (Process Isolation Strategy)
Để tránh xung đột thư viện C++/CUDA nặng (PyTorch CUDA vs ONNX Runtime CPU vs FFmpeg vs Qt):
- **Demucs**: Chạy subprocess trỏ tới `.venv-gpu/Scripts/python.exe` giao tiếp qua JSON lines IPC (`demucs_worker.py`).
- **VieNeu-TTS**: Chạy subprocess trỏ tới `.venv-vieneu/Scripts/python.exe` (`vieneu_worker.py`).
- **Paraformer ASR**: Chạy subprocess trỏ tới `.venv-asr/Scripts/python.exe` (`asr_paraformer_worker.py`).
- **Inpaint LaMa / VSR**: Quản lý qua thread pool có luồng hút `stderr` riêng ngăn chặn pipe buffer deadlock.

**`ĐÃ XÁC MINH`** — Đã kiểm tra code thực thi tại `vocal_separator.py`, `vieneu_vi.py`, `paraformer_transcriber.py`, `lama_onnx.py`.

---

## 5. Entry Points

| Hệ thống | Entry Point | Cách khởi động | Mô tả |
|---|---|---|---|
| **Desktop GUI** | `autodub_gui.app:main` | `chay_app.bat` hoặc `py -m autodub_gui` | Mở ứng dụng desktop PySide6 |
| **Dịch phụ đề rời** | `autodub.tools.gemini_srt_ui:main` | `chay_dich_srt.bat` hoặc `py -m autodub.tools.gemini_srt_ui` | Chạy web tool dịch phụ đề Flask |
| **SaaS Server** | `control_server/server.js` | `cd control_server && npm start` | Chạy backend API Fastify & serve website |
| **Website Frontend** | `website/index.html` | `cd website && npm run dev` | Chạy máy chủ dev Vite hoặc build static |
| **Đóng gói Exe** | `scripts/build_exe.py` | `py scripts/build_exe.py` | PyInstaller đóng gói `dist/VoxDub/VoxDub.exe` |

**`ĐÃ XÁC MINH`** — Đã xác nhận trong `pyproject.toml`, `package.json`, và các file `.bat`.

---

## 6. Module quan trọng — Đánh giá Chi tiết

### 6.1. `autodub/pipeline.py` (3,110 dòng)
- **Chức năng**: Trái tim của quá trình lồng tiếng. Quản lý luồng từ `DubRequest` đến `DubResult`.
- **Điểm mạnh**:
  - Hỗ trợ resume chi tiết (`resume_dir`), kiểm tra tính toàn vẹn của từng file kết quả trung gian (`data/` directory).
  - Tích hợp `UniversalPipelineCache` chống chạy lại các bước nặng (ASR, Demucs, TTS).
  - Bắt lỗi huỷ tiến trình (`check_cancelled()`) tại mỗi đầu bước.
- **Điểm cần lưu ý**: Kích thước file lớn (~3,110 dòng). Nên cân nhắc module hoá dần thành các `pipeline_steps/` trong tương lai khi mở rộng thêm tính năng mới.

### 6.2. `autodub/media/video.py` & `parallel_export.py` (745 dòng & 250 dòng)
- **Chức năng**: Biên dịch filter complex của FFmpeg và thực thi xuất video hoàn chỉnh.
- **Tối ưu nổi bật**:
  - **Parallel Chunked Export**: Chia video theo mốc keyframe, render song song các chunk với HW NVENC sessions cap (tối đa 5), sau đó ghép lại bằng `concat -c copy` không tốn thời gian re-encode. Đã đo kiểm đạt tốc độ 1.9x–2.36x.
  - **Filter complex script file**: Tự động chuyển chuỗi filter sang `-filter_complex_script <tmp_file>` khi độ dài > 1024 ký tự hoặc có > 2 vùng làm mờ, vượt qua giới hạn 32,767 ký tự của lệnh dòng Windows.
  - **Dimension Guard**: Tự động đưa kích thước khung hình về số chẵn (chống lỗi YUV420p / NVENC).

### 6.3. `autodub/media/timing.py` (375 dòng)
- **Chức năng**: Khớp độ dài giọng đọc tiếng Việt vào khung thời gian của video.
- **Bất biến an toàn (Invariant)**: Đảm bảo `usable_end = max(usable_end, t + min_slot_floor)` và `usable_end > t`. Không bao giờ để scene cut làm xuất hiện khoảng thời gian âm gây chồng chéo giọng đọc.

### 6.4. `autodub/text/translate_direct.py` (1,009 dòng)
- **Chức năng**: Dịch lời thoại đa luồng với cơ chế multi-key pooling.
- **Tối ưu an toàn**:
  - `_KeyRateLimiter`: Đặt lịch trong lock nhưng `time.sleep` NGOÀI lock, cho phép các API key khác chạy song song mà không bị chặn.
  - Tự động phát hiện và xử lý sót ký tự Hán/Nhật/Hàn (`_has_cjk`) qua retry và fallback.

---

## 7. Call Flow — Luồng Xử lý Chính

### 7.1. Luồng Tạo Dự Án & Xử lý (New Project Flow)
```
User (GUI: NewProjectPage)
  │ Bấm "Bắt đầu lồng tiếng"
  ▼
app.py -> DubWorker(req) -> QThread.start()
  │
  ▼
pipeline.py: DubPipeline.run()
  ├─► Step 1: downloader.resolve_video()
  ├─► Step 2: audio.extract_audio() (HQ + ASR mono)
  ├─► Step 2.5: Demucs.separate_vocals() (Cache check -> GPU venv)
  ├─► Step 3: Transcriber.transcribe() (Whisper/Paraformer -> VAD)
  ├─► Step 3.6: Diarization & Voice Director (Phân vai giọng đọc)
  ├─► Step 4: Translator.translate() (Direct multi-key / SaaS / Glossary)
  ├─► Step 5: TTS.synthesize() (VieNeu / CapCut -> segments/*.wav)
  ├─► Step 6: timing.align() & audio.mix() (Atempo stretch, Scene snap)
  ├─► Step 7: video.merge_video() (Parallel chunked export + NVENC)
  └─► Step 8: generator.generate_metadata() (Viral tags & Thumbnail)
  │
  ▼
DubWorker emit finished(result) -> GUI hiển thị trang hoàn tất & mở video/thư mục
```

### 7.2. Luồng SaaS AI Gateway & Thanh toán
```
Desktop Client (saas_client.py)               Control Server (Fastify)               PayOS / AI Provider
     │                                                │                                       │
     │── 1. Đăng ký/Xác thực thiết bị ───────────────►│                                       │
     │   (Lấy JWT Device Token)                       │                                       │
     │                                                │                                       │
     │── 2. Giữ tín dụng trước (Acquire Hold) ───────►│                                       │
     │   POST /v1/holds/acquire                       │                                       │
     │                                                │── 3. Gọi mô hình AI đã mã hoá ───────►│
     │                                                │   (Gemini/OpenRouter)                 │
     │                                                │◄─ Kết quả bản dịch ───────────────────│
     │                                                │                                       │
     │── 4. Chốt trừ tiền (Commit Hold) ─────────────►│                                       │
     │   POST /v1/holds/commit                        │                                       │
     │                                                │                                       │
Web User (website/src/pages/Buy.jsx)                  │                                       │
     │── 5. Tạo đơn mua nạp Vox ─────────────────────►│── 6. Tạo link thanh toán QR ─────────►│
     │   POST /v1/billing/order                       │◄─ Link QR PayOS ──────────────────────│
     │◄─ Hiển thị mã QR PayOS ────────────────────────│                                       │
     │                                                │                                       │
     │                                                │◄─ 7. Webhook thanh toán thành công ───│
     │                                                │   (Xác minh HMAC SHA256)              │
     │                                                │   Cộng Vox vào tài khoản & sinh Key   │
```

**`ĐÃ XÁC MINH`** — Đã kiểm chứng qua các file route `control_server/src/routes/` và test cases `control_server/tests/`.

---

## 8. Database / Data Model

### 8.1. Client-side Data Models
- **SQLite Universal Pipeline Cache** (`pipeline_cache.py`):
  - Bảng `asr_cache`: `(audio_fingerprint, model, language, beam_size) -> transcript_json`
  - Bảng `demucs_cache`: `(audio_fingerprint, model) -> vocals_path, no_vocals_path`
  - Bảng `translation_cache`: `(source_hash, target_lang, model) -> translated_text`
  - Bảng `tts_cache`: `(text_hash, voice, speed) -> wav_blob`
- **Tập tin trạng thái dự án** (`output/VN/YYYYMMDD_HHMMSS_vi/data/`):
  - `transcript_original.json`: Lời nhận dạng gốc
  - `transcript_vi.json`: Lời dịch tiếng Việt
  - `render_opts.json`: Cấu hình ghim (font, style, vùng che, giọng đọc)
  - `quality_report.json`: Đánh giá độ khớp thời gian và tốc độ CPS

### 8.2. Server-side MongoDB Models (`control_server/src/models/`)
- `Device`: Quản lý định danh thiết bị phần cứng, số dư ví Vox, trạng thái kích hoạt.
- `CreditLedger`: Sổ cái ghi nhận từng biến động tài khoản (nạp tiền, trừ dịch, hoàn tiền).
- `CreditHold`: Phiếu giữ tiền tạm trong suốt thời gian render video, tự động hết hạn và chốt sau TTL.
- `Order`: Đơn mua gói nạp qua PayOS (trạng thái: `pending`, `paid`, `expired`, `cancelled`).
- `ActivationKey`: Kho mã khoá kích hoạt phần mềm.
- `AiProvider`: Cấu hình nhà cung cấp AI (API key được mã hoá AES-256-CBC).
- `AppConfig`: Cấu hình động toàn hệ thống (bảng giá Vox, tỷ lệ quy đổi, thông báo bảo trì).
- `AuditLog` & `UsageLog`: Ghi vết mọi thao tác quản trị và nhật ký gọi AI.

**`ĐÃ XÁC MINH`** — Xác nhận từ schema Mongoose trong `control_server/src/models/`.

---

## 9. API / External Services

| Service | Protocol | Mục đích | Quản lý lỗi / Retry |
|---|---|---|---|
| **Google Gemini API** | HTTPS REST | Dịch thuật, sinh metadata, phân tích viral | Multi-key round-robin, retry với backoff, rate limiter |
| **OpenRouter API** | HTTPS REST | Dịch thuật dự phòng đa mô hình | Retry khi gặp 429/500 |
| **CapCut TTS API** | HTTPS REST | Sinh giọng nói tiếng Việt chất lượng cao | Device pool xoay vòng, retry fallback |
| **PayOS Gateway** | HTTPS REST / Webhook | Cổng thanh toán ngân hàng tự động | HMAC SHA256 checksum, đối soát 1-1 |
| **Brevo SMTP** | SMTP | Gửi email thông báo mã kích hoạt | Tự động bỏ qua nếu không cấu hình |
| **YouTube / TikTok / Douyin** | HTTP/Playwright | Tải video chất lượng gốc | Aria2 16 luồng, CDN racing, auto retry |

**`ĐÃ XÁC MINH`** — Đã kiểm chứng trong `translate_direct.py`, `downloader.py`, `payos.service.js`, `capcut_vi.py`.

---

## 10. Authentication / Security

1. **Mã hoá API Key của AI Provider**: Server mã hoá khoá bí mật bằng thuật ngữ AES-256-CBC với IV ngẫu nhiên cho mỗi bản ghi; khoá giải mã `APP_ENCRYPTION_KEY` chỉ lưu trong biến môi trường.
2. **Xác thực Thiết bị (Device Token)**: Desktop app nhận JWT token có thời hạn 30 ngày, tự động làm mới khi còn dưới nửa hạn.
3. **Bảo vệ Endpoint Quản trị**: `/v1/admin/*` yêu cầu `X-Admin-Token` và so sánh chuỗi bằng `crypto.timingSafeEqual` ngăn chặn timing attack.
4. **Bảo vệ Log Server**: Fastify logger tự động redact các header nhạy cảm (`Authorization`, `X-Admin-Token`).
5. **Giới hạn Tần suất (Rate Limiting)**: Fastify rate-limit phân biệt theo Bearer token, IP client và Admin IP để chống DoS.
6. **Mã hoá File Cục bộ (SecureStore)**: Hỗ trợ mã hoá file trung gian bằng AES-256-GCM.
7. **Quản lý Secrets trong Repo**: Toàn bộ file cấu hình thật `.env` đều được đưa vào `.gitignore`, không có bất kỳ API key nào bị rò rỉ trong git history.

**`ĐÃ XÁC MINH`** — Đã chạy grep tìm pattern API key và kiểm tra logic trong `crypto.js`, `server.js`, `app.js`.

---

## 11. Testing

- **Python Test Suite**:
  - Công cụ: `pytest 9.1.1` + `pytest-qt`
  - Quy mô: **151 test files**, **1337 test cases**
  - Kết quả kiểm toán: **1337/1337 PASSED (100%)**, thời gian chạy ~118 giây.
  - Phạm vi bao phủ: Video merge, parallel export, timing alignment, ASR acoustic align, speech boundaries, translation cache, GUI tokens, timeline canvas, adversarial input edge cases.
- **Node.js Backend Test Suite**:
  - Công cụ: `node --test`
  - Quy mô: **59 test cases**
  - Kết quả kiểm toán: **59/59 PASSED (100%)**, thời gian chạy ~6.5 giây.
  - Phạm vi bao phủ: PayOS signature, credit hold/commit, JSON repair, keycode normalization, AES encryption.
- **Website Frontend**:
  - Build test: `npm run build` chạy thành công, không lỗi TypeScript/JSX, bundle tối ưu 475 modules.
- **Code Quality**:
  - `ruff check .`: **All checks passed!** (Không còn lỗi cú pháp hay cảnh báo chưa xử lý).

**`ĐÃ XÁC MINH`** — Đã chạy trực tiếp toàn bộ các lệnh test trên môi trường hiện tại.

---

## 12. Coding Convention

- **Python**:
  - Tuân thủ PEP 8 và định dạng chuẩn Ruff với độ dài dòng tối đa 100 ký tự.
  - Toàn bộ exception bắt được trong khối `except Exception:` đều được ghi log rõ ràng qua `logger.debug(exc_info=...)` thay vì nuốt lỗi bằng `pass`.
  - Không import trực tiếp tầng GUI (`autodub_gui`) vào lõi Core (`autodub`).
  - Giao diện PySide6 sử dụng design tokens tập trung (`autodub_gui/tokens.py`, `theme.py`).
- **Node.js**:
  - Sử dụng chế độ nghiêm ngặt `'use strict'`.
  - Xử lý bất đồng bộ bằng `async/await`.
  - Tách bạch service layer (`services/`) và controller layer (`routes/`).
- **React**:
  - Sử dụng React Function Components và React Hooks.
  - Trạng thái toàn cục tập trung trong Zustand stores.

**`ĐÃ XÁC MINH`** — Đã đối chiếu mã nguồn và cấu hình Ruff trong `pyproject.toml`.

---

## 13. Rủi ro & Technical Debt

### 13.1. Rủi ro Cần Lưu ý
1. **Dung lượng Ổ đĩa Môi trường Đa venv**: Dự án sử dụng nhiều venv độc lập (`.venv-gpu`, `.venv-vieneu`, `.venv-asr`) để cách ly thư viện AI. Người dùng cần chuẩn bị tối thiểu 15-20 GB dung lượng trống trên ổ đĩa. Đã có công cụ `autodub/diskspace.py` và preflight check cảnh báo sớm.
2. **Kích thước các Module Lớn (God Files)**:
   - `autodub/pipeline.py` (3,110 dòng)
   - `autodub_gui/style_dialog.py` (2,527 dòng)
   - `autodub/editor.py` (1,806 dòng)
   Mặc dù các file này được bọc test rất kỹ, nhưng kích thước lớn khiến việc đọc hiểu và bảo trì đòi hỏi sự cẩn trọng cao.

### 13.2. Cảnh báo Nhẹ (Minor Warnings)
- **Deprecation trong PySide6**:
  - Tại `autodub_gui/style_dialog.py:2151` (và 3 vị trí khác), hàm `QColor.isValidColor(hex)` sinh `DeprecationWarning` trên Qt 6. Nên cập nhật sang `QColor.isValidColorName(hex)`.

### 13.3. Thay đổi chưa commit trên Working Tree
- Hiện có 2 file đã chỉnh sửa unstaged:
  - `autodub/media/video.py`: Khởi tạo `filter_script_file = None` để phòng tránh `UnboundLocalError` trong nhánh finally khi video dài gặp filter ngắn chạy parallel export.
  - `tests/test_video_merge.py`: Bổ sung regression tests tương ứng.
  - Đã kiểm tra: cả 2 thay đổi này hoàn toàn chính xác và toàn bộ test suite đều pass.

---

## 14. Những điều Chưa xác định

| # | Hạng mục | Trạng thái hiện tại | Hướng xác minh khi cần |
|---|---|---|---|
| 1 | Tính khả dụng thời gian thực của CapCut TTS API bên thứ ba | `SUY LUẬN` hoạt động bình thường qua device pool, nhưng phụ thuộc server bên thứ ba | Kiểm tra trực tiếp khi có kết nối internet thực tế |
| 2 | Card màn hình chuyên dụng của người dùng cuối | `ĐÃ XÁC MINH` hệ thống tự nhận diện CUDA/NVENC và tự động chuyển về CPU nếu không có GPU | Tự động thích ứng trong `sysinfo.py` và `pipeline.py` |

---

## 15. File đã kiểm tra

- `README.md`, `full_source_audit.md`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`
- `autodub/__init__.py`, `pipeline.py`, `pipeline_cache.py`, `config.py`, `editor.py`, `checkpoint_store.py`, `progress.py`
- `autodub/media/video.py`, `parallel_export.py`, `timing.py`, `subtitle.py`, `audio.py`, `dimension.py`, `vocal_separator.py`
- `autodub/speech/transcriber.py`, `paraformer_transcriber.py`, `diarization.py`, `speaker_profiler.py`, `voice_director.py`
- `autodub/text/translate_direct.py`, `translate_saas.py`, `translate_hint.py`, `glossary.py`
- `autodub_gui/app.py`, `workers.py`, `shell.py`, `theme.py`, `tokens.py`, `style_dialog.py`
- `control_server/server.js`, `src/app.js`, `package.json`, các routes và services
- `website/package.json`, `src/App.jsx`, `vite.config.js`
- Toàn bộ 151 files trong thư mục `tests/`

---

## 16. Mức độ Tin cậy

- **Kiến trúc & Luồng dữ liệu**: `ĐÃ XÁC MINH` (100% dựa trên source code thực tế)
- **Chất lượng mã nguồn & Test Suite**: `ĐÃ XÁC MINH` (1337 tests Python pass, 59 tests Node.js pass, build frontend thành công, ruff pass)
- **Bảo mật & Cấu hình môi trường**: `ĐÃ XÁC MINH` (Không lộ bí mật, kiểm soát mã hoá chuẩn)

---

`TRẠNG THÁI: HOÀN THÀNH`
