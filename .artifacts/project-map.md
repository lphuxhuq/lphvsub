# Project Map — LPH VSub (VoxDub Studio)

> Phiên bản: 2026-08-21 · Trạng thái: **HOÀN THÀNH**

---

## 1. Tổng quan

**LPH VSub (VoxDub Studio)** là ứng dụng desktop Windows tự động lồng tiếng và tạo phụ đề tiếng Việt cho video nước ngoài. Pipeline xử lý: **Tải video → Tách audio → Tách nhạc nền (Demucs) → Nhận dạng lời thoại (ASR) → Dịch AI → Tạo giọng đọc tiếng Việt (TTS) → Khớp thời gian → Ghép video thành phẩm**.

Hệ thống gồm 4 thành phần chính:
1. **`autodub/`** — Core pipeline Python (thư viện, không UI)
2. **`autodub_gui/`** — Giao diện desktop PySide6 (Qt)
3. **`control_server/`** — Backend Node.js/Fastify (SaaS: ví Vox, AI gateway, quản trị) — **TÙY CHỌN**
4. **`website/`** — Landing page + admin panel (React/Vite/Tailwind)

Version: `autodub 2.1.0` (pyproject.toml), `autodub_gui 3.0.0` (app.py), `voxdub-api 3.0.0` (control_server)

**`ĐÃ XÁC MINH`** — xác nhận từ README.md, pyproject.toml, package.json, source code.

---

## 2. Technology Stack

| Lớp | Công nghệ | Ghi chú |
|-----|-----------|---------|
| **Core Pipeline** | Python ≥3.10 | `autodub/` package |
| **GUI** | PySide6 ≥6.6.0 (Qt6) | Desktop Windows |
| **ASR** | faster-whisper ≥1.0, Paraformer (ONNX) | Venv riêng `.venv-whisper`, `.venv-asr` |
| **TTS** | VieNeu (ONNX, CPU, offline, venv `.venv-vieneu`) | 120 giọng mẫu |
| **TTS Online** | CapCut TTS API | Device pool, multi-threaded |
| **Tách nhạc** | Demucs ≥4.0 | Venv riêng `.venv-gpu`, GPU ưu tiên |
| **Download** | yt-dlp, aria2 (optional), Playwright (Douyin) | |
| **Dịch AI** | Gemini, OpenRouter, OpenAI, DeepSeek, Custom AI | Direct hoặc qua Control Server |
| **Audio** | pydub, ffmpeg (external), numpy | |
| **Mã hóa** | cryptography (AES-256-GCM) | securestore.py |
| **Backend** | Node.js ≥20, Fastify 5, Mongoose 8 | control_server/ |
| **Database** | MongoDB | Chỉ backend |
| **Auth** | JWT (jsonwebtoken) | Device fingerprint |
| **Payment** | PayOS | billing, orders |
| **Email** | nodemailer | Thông báo |
| **Website** | React 18, Vite 5, Tailwind 3, Zustand, Framer Motion | SPA |
| **Build** | PyInstaller (autodub.spec) | Đóng gói .exe |
| **Test (Python)** | pytest ≥8.0 | 53 test files |
| **Test (Node)** | node --test, mongodb-memory-server | |
| **Config** | python-dotenv (.env) | |

**`ĐÃ XÁC MINH`** — từ pyproject.toml, requirements.txt, package.json (2 files), source code imports.

---

## 3. Cấu trúc Project

```
lphvsub/
├── autodub/                     # Core pipeline (Python library)
│   ├── __init__.py              # Public API: Settings, DubPipeline, DubRequest, DubResult
│   ├── pipeline.py              # 2013 dòng — trung tâm xử lý (6+ bước)
│   ├── editor.py                # Chỉnh sửa từng câu, đọc lại, xuất video
│   ├── batch.py                 # Xử lý hàng loạt (crash-safe, prefetch)
│   ├── config.py                # Settings dataclass, đọc .env
│   ├── saas_client.py           # Kết nối control_server (tùy chọn)
│   ├── securestore.py           # Mã hóa AES-256-GCM file trung gian
│   ├── preflight.py             # Kiểm tra hệ thống trước khi chạy
│   ├── media/                   # Xử lý audio/video/subtitle
│   │   ├── audio.py             # Extract, merge, postprocess, loudnorm
│   │   ├── video.py             # FFmpeg video operations, NVENC
│   │   ├── downloader.py        # yt-dlp + aria2 downloader
│   │   ├── douyin.py            # Playwright-based Douyin extractor
│   │   ├── demucs_worker.py     # Demucs subprocess
│   │   ├── vocal_separator.py   # BGM separation dispatcher
│   │   ├── subtitle.py          # SRT/ASS generation
│   │   ├── retime.py            # Video speed, soft timing
│   │   └── timing.py            # Anti-overlap timing engine
│   ├── speech/                  # ASR + TTS
│   │   ├── transcriber.py       # Whisper/Paraformer dispatcher
│   │   ├── asr_whisper_worker.py
│   │   ├── asr_paraformer_worker.py
│   │   ├── align.py             # Karaoke alignment
│   │   └── tts/                 # Synthesizer registry
│   │       ├── __init__.py      # get_synthesizer(), SynthCache
│   │       ├── vieneu_vi.py     # VieNeu offline (multiprocess)
│   │       ├── capcut_vi.py     # CapCut TTS API
│   │       ├── voices.py        # Voice catalog
│   │       └── voice_library.py # Voice management
│   ├── text/                    # Dịch thuật
│   │   ├── translate_direct.py  # Direct API (Gemini/OpenRouter/…)
│   │   ├── translate_saas.py    # Dịch qua control_server
│   │   ├── translate_browser.py # Dịch qua Google AI Studio (browser)
│   │   ├── translate_hint.py    # Dịch thủ công (TRANSLATE_PENDING.txt)
│   │   ├── translate_common.py  # Shared: USAGE tracker, HOLD state
│   │   ├── translate_review.py  # Rà soát + dịch lại câu lỗi
│   │   ├── glossary.py          # Bảng thuật ngữ
│   │   └── srt.py               # SRT file generator
│   ├── content/                 # Tạo metadata (title, desc, hashtags)
│   │   └── generator.py
│   └── tools/                   # Gemini SRT UI (Flask web tool)
│       └── gemini_srt_ui/
│
├── autodub_gui/                 # Desktop GUI (PySide6)
│   ├── app.py                   # MainWindow, sidebar, page routing
│   ├── workers.py               # QThread workers (dub, batch, download)
│   ├── shell.py                 # Header, sidebar, notifications
│   ├── theme.py / tokens.py     # Design system
│   ├── pages/                   # 24 page files
│   │   ├── home_page.py
│   │   ├── new_project_page.py  # Wizard tạo dự án (58KB!)
│   │   ├── editor_page.py       # Trình chỉnh sửa (47KB)
│   │   ├── batch_page.py
│   │   ├── settings_page.py
│   │   └── ...
│   ├── video/                   # Video player + timeline
│   │   ├── player.py
│   │   └── timeline.py
│   └── ui/                      # 23 reusable UI components
│       ├── cards.py, buttons.py, inputs.py, modal.py, toast.py...
│
├── control_server/              # Backend SaaS (Node.js/Fastify)
│   ├── server.js                # Entry point + sweeper timers
│   ├── src/
│   │   ├── app.js               # Fastify factory, route registration
│   │   ├── routes/              # 6 route files
│   │   │   ├── ai.js            # AI gateway (/v1/ai)
│   │   │   ├── device.js        # Device registration (/v1/device)
│   │   │   ├── holds.js         # Credit holds (/v1/holds)
│   │   │   ├── billing.js       # Payment/orders (/v1/billing)
│   │   │   ├── admin.js         # Admin panel API (/v1/admin)
│   │   │   └── config.js        # Dynamic config (/v1/config)
│   │   ├── services/            # 10 service files
│   │   ├── models/              # 10 Mongoose models
│   │   ├── middleware/           # auth + admin middleware
│   │   └── plugins/             # MongoDB plugin
│
├── website/                     # Landing page + admin (React/Vite)
│   └── src/
│       ├── pages/               # Landing, Buy, Checkout, Pricing, Docs, FAQ, Download
│       │   └── admin/           # Dashboard, Devices, Keys, Orders, Providers, Config...
│
├── scripts/                     # Setup + build scripts
│   ├── build_exe.py             # PyInstaller build
│   ├── setup_vieneu.py
│   ├── setup_whisper.py
│   ├── setup_paraformer.py
│   └── setup_voices.py
│
├── tests/                       # 53 Python test files
├── voices/                      # Voice samples (preset + custom)
├── models/                      # ML model storage
├── fonts/                       # Font files
├── docs/                        # Documentation
└── *.bat                        # Windows batch scripts (install, run, etc.)
```

**`ĐÃ XÁC MINH`** — trực tiếp từ directory listing + file contents.

---

## 4. Kiến trúc

### 4.1 Kiến trúc tổng thể

```
┌────────────────────────────────────────────────────────────┐
│                    Desktop App (Python)                      │
│  ┌──────────────┐        ┌───────────────────────────────┐  │
│  │ autodub_gui  │───────>│         autodub (core)        │  │
│  │  PySide6 GUI │ DubReq │  pipeline / batch / editor    │  │
│  │  15 pages    │<───────│  media / speech / text        │  │
│  └──────────────┘ DubRes └──────────┬────────────────────┘  │
│                                     │ saas_client.py        │
└─────────────────────────────────────┼───────────────────────┘
                                      │ HTTP (optional)
┌─────────────────────────────────────┼───────────────────────┐
│                    Control Server (Node.js)                  │
│  ┌──────────┐  ┌──────────┐  ┌─────┴────┐  ┌────────────┐  │
│  │  Routes   │──│ Services │──│ MongoDB  │  │  Website   │  │
│  │ /v1/ai    │  │ credit   │  │ 10 coll  │  │ React SPA  │  │
│  │ /v1/device│  │ hold     │  └──────────┘  │ Admin panel│  │
│  │ /v1/admin │  │ gateway  │                └────────────┘  │
│  └──────────┘  └──────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Mô hình phân lớp

- **Presentation**: `autodub_gui/` (PySide6) + `website/` (React)
- **Application**: `autodub/pipeline.py`, `autodub/batch.py`, `autodub/editor.py`
- **Domain**: `autodub/media/`, `autodub/speech/`, `autodub/text/`
- **Infrastructure**: `autodub/config.py`, `autodub/saas_client.py`, `autodub/securestore.py`, `control_server/`

### 4.3 Kiến trúc backend

- **Pattern**: Fastify + service layer + Mongoose models
- **Auth**: JWT device token (fingerprint-based, không có user/password)
- **Monetization**: Credit wallet (Vox), hold system, PayOS payment
- **AI Gateway**: Server proxy AI calls, idempotent via jobId

**`ĐÃ XÁC MINH`** — từ source code pipeline.py, app.js, auth.middleware.js.

---

## 5. Entry Points

| Entry Point | File | Cách chạy |
|-------------|------|-----------|
| **GUI chính** | `autodub_gui/app.py` `main()` | `chay_app.bat` hoặc `py -m autodub_gui` |
| **Library API** | `autodub/__init__.py` | `from autodub import DubPipeline, Settings` |
| **Backend** | `control_server/server.js` | `npm start` hoặc `npm run dev` |
| **Website** | `website/src/main.jsx` | `npm run dev` |
| **Tests** | `tests/` | `py -m pytest -q` |
| **Build exe** | `scripts/build_exe.py` | `py scripts/build_exe.py` |
| **Gemini SRT** | `chay_dich_srt.bat` | Flask web tool |
| **Install** | `cai_dat.bat` | One-click setup |

**`ĐÃ XÁC MINH`** — từ pyproject.toml `[project.gui-scripts]`, README, batch files.

---

## 6. Module quan trọng

### 6.1 `autodub/pipeline.py` (2013 dòng) — `ĐÃ XÁC MINH`

File lớn nhất và quan trọng nhất. Chứa `DubPipeline`, `DubRequest`, `DubResult`. Pipeline 7+ bước với crash-safe resume (kiểm tra file đã có trước khi chạy lại bước).

**Trạng thái kết quả**: `"completed"` | `"translate_pending"` | `"export_pending"` | `"credit_blocked"`

### 6.2 `autodub/config.py` (599 dòng) — `ĐÃ XÁC MINH`

`Settings` dataclass ~60 fields, đọc từ `.env` qua python-dotenv. Quality preset system (`fast`/`balanced`/`quality`). Auto-scaling workers theo RAM/CPU.

### 6.3 `autodub/editor.py` (61KB) — `SUY LUẬN`

Chỉnh sửa từng câu dịch, đọc lại, xuất video. Tương tác với render_opts.json.

### 6.4 `autodub/saas_client.py` (507 dòng) — `ĐÃ XÁC MINH`

Kết nối TÙY CHỌN tới control_server. Device fingerprint + JWT token. Idempotent job_id. Fail-closed: có cấu hình mà không kết nối được thì dừng, không bỏ qua.

### 6.5 `autodub/securestore.py` (224 dòng) — `ĐÃ XÁC MINH`

AES-256-GCM mã hóa file trung gian (bản dịch, audio ghép) khi hold chưa chốt. Format: VOXENC1\0 + nonce 12B + ciphertext. Khóa do server cấp.

### 6.6 `autodub_gui/app.py` (831 dòng) — `ĐÃ XÁC MINH`

MainWindow PySide6 với 15 trang. Lazy page loading + prewarm. Responsive sidebar breakpoints. Name: "NovaSub" (internal), "VoxDub Studio" (public).

### 6.7 `control_server/src/routes/ai.js` (683 dòng) — `ĐÃ XÁC MINH`

AI gateway: idempotent jobId → credit check → model call → charge. Hold system cho wizard flow. Không leak provider/model/cost ra response.

---

## 7. Call Flow

### 7.1 Luồng lồng tiếng chính (Wizard)

```
User (GUI)
  → new_project_page.py — chọn URL/file, giọng, ngôn ngữ
    → DubWorker (QThread)
      → DubPipeline.run(DubRequest)
        → Step 1: _resolve_video() — yt-dlp/aria2/Playwright → video.mp4
        → Step 2: extract_audio() — ffmpeg → original_audio.wav + HQ wav
        → Step 2.5: _resolve_background() — Demucs (async ThreadPoolExecutor)
        → Step 3: transcribe() — Whisper/Paraformer subprocess → transcript_original.json
        → Hold: _setup_hold() — saas_client → server creates CreditHold
        → Step 4: _auto_translate() → translate_saas/translate_direct → transcript_vi.json
          (hoặc translate_pending → DỪNG, user dịch tay)
        → Step 5: _synthesize_segments() → VieNeu (multiprocess) / CapCut (API)
        → Step 5.5: video speed (optional)
        → Step 6: merge_segments() — audio merge + timing + loudnorm
        → [Wizard] _stop_for_export() — mã hóa → DubResult(status="export_pending")
          → User bấm Xuất video → commit_hold → giải mã → _export_phase()
        → [Batch/Legacy] _settle_hold_inline() → _export_phase()
        → Step 7: _export_phase() — mux video + subtitle + blur → dubbed_video.mp4
      → DubResult → GUI hiện kết quả
```

**`ĐÃ XÁC MINH`** — trace trực tiếp từ pipeline.py L152-800+.

### 7.2 Luồng đăng ký thiết bị

```
App khởi động
  → saas_client.ensure_session()
    → POST /v1/device/register { fingerprint, name, appVersion }
      → device.service.registerDevice() → Device upsert → JWT sign
    ← { token, device, creditEnabled }
  → Token lưu vào OS keyring (keystore.py)
  → Mỗi API call: Authorization: Bearer <token>
    → auth.middleware.requireDevice → verify JWT + check blocked + tokenVersion
```

**`ĐÃ XÁC MINH`** — từ device.js, auth.middleware.js, saas_client.py.

### 7.3 Luồng dịch AI (qua server)

```
Pipeline Step 4
  → translate_saas.py — gọi saas_client
    → POST /v1/ai/translate { segments, jobId, holdId }
      → replay(jobId) — đã dịch rồi? trả lại
      → precheck(fingerprint, holdId, cost) — đủ Vox?
      → gateway.translate(segments, provider) — Gemini/OpenRouter/...
      → finalize(credit charge, UsageLog, JobResult save)
    ← { translations }
```

**`ĐÃ XÁC MINH`** — từ ai.js, ai-gateway.service.js.

---

## 8. Database/Data Model

### 8.1 MongoDB (Control Server) — `ĐÃ XÁC MINH`

| Model | Mục đích | Key fields |
|-------|----------|------------|
| **Device** | Thiết bị | fingerprint (unique), balance, status, tokenVersion, trialGranted |
| **CreditLedger** | Sổ cái ví | fingerprint, delta, balanceAfter, type, idempotencyKey |
| **CreditHold** | Giữ chỗ Vox | fingerprint, status, estimatedVox, key (mã hóa) |
| **JobResult** | Cache kết quả AI | jobId (unique), fingerprint, action, result |
| **ActivationKey** | Mã kích hoạt | code, vox, maxUses, usedBy |
| **AiProvider** | Cấu hình AI | name, models, apiKey (encrypted), priority |
| **AppConfig** | Dynamic config | key, value |
| **AuditLog** | Nhật ký kiểm toán | fingerprint, action, detail |
| **Order** | Đơn hàng | fingerprint, amount, status, payosData |
| **UsageLog** | Log sử dụng AI | fingerprint, action, model, tokensUsed |

### 8.2 File-based Data (Desktop) — `ĐÃ XÁC MINH`

Mỗi dự án lưu trong `output/VN/YYYYMMDD_HHMMSS_vi/`:

| File | Mục đích |
|------|----------|
| `dubbed_video.mp4` | Video thành phẩm |
| `transcript_vi.srt` / `.ass` | Phụ đề |
| `data/transcript_original.json` | Lời thoại gốc (ASR) |
| `data/transcript_vi.json` | Bản dịch |
| `data/original_audio.wav` | Audio gốc |
| `data/vocals.wav` / `no_vocals.wav` | Demucs output |
| `data/audio_vi_full.wav` | Audio lồng tiếng |
| `data/segments/` | TTS từng câu |
| `data/render_opts.json` | Tùy chọn render |
| `data/export_state.json` | Trạng thái xuất (có thể mã hóa) |
| `data/voxdub_lock.json` | Marker hold đang khóa |
| `data/quality_report.json` | Báo cáo chất lượng |
| `batch_state.json` | Trạng thái batch (crash-safe) |

---

## 9. API/External Services

### 9.1 Control Server API — `ĐÃ XÁC MINH`

| Endpoint | Method | Mục đích |
|----------|--------|----------|
| `/v1/device/register` | POST | Đăng ký / nhận diện thiết bị |
| `/v1/device/me` | GET | Thông tin + số dư |
| `/v1/device/refresh` | POST | Đổi token mới |
| `/v1/device/activate` | POST | Kích hoạt mã |
| `/v1/ai/translate` | POST | Dịch qua AI gateway |
| `/v1/ai/analyze` | POST | Phân tích ngữ cảnh video |
| `/v1/ai/review` | POST | Rà soát bản dịch |
| `/v1/ai/generate-post` | POST | Tạo nội dung đăng bài |
| `/v1/holds/*` | POST | Tạo/commit/release hold |
| `/v1/billing/*` | POST | PayOS checkout, webhook |
| `/v1/admin/*` | Various | CRUD quản trị |
| `/v1/config` | GET | Dynamic config |
| `/health` | GET | Health check |

### 9.2 External APIs — `ĐÃ XÁC MINH`

| Service | Module | Ghi chú |
|---------|--------|---------|
| Gemini API | translate_direct.py | Multi-key round-robin pool |
| OpenRouter | translate_direct.py | |
| OpenAI | translate_direct.py | |
| DeepSeek | translate_direct.py | |
| Custom AI endpoint | translate_direct.py | Base URL configurable |
| CapCut TTS API | capcut_vi.py | Device pool, cookie-based |
| YouTube/TikTok/etc | yt-dlp | |
| Douyin | douyin.py | Playwright browser |
| PayOS | payos.service.js | Payment gateway |
| GitHub API | updates.py | Check for updates |

---

## 10. Authentication/Security

### 10.1 Desktop ↔ Server Auth — `ĐÃ XÁC MINH`

- **Nhận dạng**: Device fingerprint (SHA-256, 64 hex chars) — hardware-based
- **Token**: JWT signed với JWT_SECRET, chứa `{ fp, v (tokenVersion) }`
- **Lưu trữ**: OS keyring (Windows Credential Manager) qua `keystore.py`
- **Token revocation**: Admin tăng tokenVersion → token cũ bị từ chối
- **Device blocking**: status = 'blocked' → 403

### 10.2 Admin Panel — `ĐÃ XÁC MINH`

- Header `X-Admin-Token` so sánh với env `ADMIN_TOKEN`
- Thiếu ADMIN_TOKEN → /v1/admin/* trả 503

### 10.3 File Encryption (Hold system) — `ĐÃ XÁC MINH`

- AES-256-GCM (cryptography library)
- Khóa do server sinh per-hold, chỉ sống trong RAM
- Mã hóa: bản dịch, audio ghép, export_state — cho tới khi commit hold
- Magic: `VOXENC1\0` + 12B nonce + ciphertext

### 10.4 Server Security — `ĐÃ XÁC MINH`

- APP_ENCRYPTION_KEY (64 hex) mã hóa API key của AI providers
- Rate limiting: 5000 req/min global, 20/min cho register, 10/min cho activate
- Helmet enabled, CSP disabled
- Log redaction: authorization header
- Error handler: không leak stack trace

---

## 11. Testing

### Python (53 test files) — `ĐÃ XÁC MINH`

- Framework: pytest
- Chạy: `py -m pytest -q`
- Phạm vi test: config, audio, video, ASR, TTS, translate, editor, batch, UI tokens, securestore, glossary, timing, waveform, voices, subtitle, diskspace, preflight, projects scan, etc.
- Mức test: Chủ yếu unit test, mock external dependencies

### Node.js (Control Server) — `ĐÃ XÁC MINH`

- Framework: Node.js built-in test runner
- Database: mongodb-memory-server (in-memory)
- Chạy: `npm test`

### Thiếu — `SUY LUẬN`

- Không thấy integration test end-to-end cho pipeline đầy đủ
- Không thấy test cho website (React)
- Không thấy CI/CD configuration

---

## 12. Coding Convention

### Python — `ĐÃ XÁC MINH`

- **Naming**: snake_case cho functions/variables, PascalCase cho classes
- **Docstring**: Module-level docstring (Vietnamese + English), Google style
- **Logging**: `setup_logging("autodub.module")` → unified logger
- **Error handling**: Custom exceptions (`ConfigError`, `SaasError`, `SecureStoreError`), fail-closed
- **Config**: `Settings` dataclass + `.env` → `Settings.load()`
- **Imports**: `from __future__ import annotations`, lazy imports (heavy modules)
- **I18N**: Comments và user-facing strings bằng tiếng Việt
- **Threading**: `threading.Event` cho cancellation, `QThread` cho GUI
- **File I/O**: `save_json_atomic()` (atomic write), encoding="utf-8"
- **Path handling**: `data_dir()`, `data_path()`, `app_root()` — utilities
- **Progress**: Callback-based `ProgressFn`, `ProgressReporter`

### Node.js — `ĐÃ XÁC MINH`

- **Style**: `'use strict'`, CommonJS modules
- **Naming**: camelCase, PascalCase cho models
- **DB**: Mongoose schemas, lean queries
- **Error handling**: Fastify error handler, status codes có code field
- **Comments**: Vietnamese doc comments

### GUI — `ĐÃ XÁC MINH`

- **Design system**: `theme.py` + `tokens.py` — centralized
- **Components**: `ui/` directory — 23 reusable widgets
- **Page pattern**: Lazy-loaded, QStackedWidget navigation
- **Workers**: QThread + Qt signals

---

## 13. Rủi ro

### 13.1 Độ phức tạp cao — `ĐÃ XÁC MINH`

- **`pipeline.py` = 2013 dòng** — God file, chứa toàn bộ logic pipeline trong 1 class. Khó test, khó maintain.
- **`new_project_page.py` = 58KB** — GUI page rất lớn.
- **`editor_panels.py` = 60KB** — Editor panels rất lớn.
- Nhiều file > 20KB cho thấy thiếu decomposition.

### 13.2 Coupling — `SUY LUẬN`

- Pipeline phụ thuộc trực tiếp vào saas_client, securestore, editor (load_render_opts) — domain logic lẫn infrastructure.
- GUI workers import trực tiếp từ core — không có interface trung gian rõ ràng.

### 13.3 Venv Management — `ĐÃ XÁC MINH`

- 4 venv riêng biệt (`.venv-whisper`, `.venv-asr`, `.venv-vieneu`, `.venv-gpu`) + venv chính
- ASR, TTS, Demucs chạy qua subprocess với venv riêng — phức tạp, khó debug

### 13.4 Security concerns — `ĐÃ XÁC MINH`

- `.env` file chứa API keys → có trong .gitignore nhưng cần cẩn thận
- Client-side encryption chỉ chặn user thường (code ghi rõ limitation trong securestore.py)
- CapCut TTS: sử dụng API không chính thức (device pool, cookie-based)

### 13.5 Thiếu CI/CD — `SUY LUẬN`

- Không thấy `.github/workflows/`, Dockerfile, hay CI configuration nào
- Build thủ công qua `scripts/build_exe.py`

### 13.6 Performance risks — `SUY LUẬN`

- Pipeline xử lý tuần tự các bước nặng (có một số song song hóa Demucs/ASR)
- TTS là bottleneck lớn nhất (multiprocess VieNeu)

### 13.7 Technical debt — `SUY LUẬN`

- Module names mâu thuẫn: "LPH VSub" vs "VoxDub Studio" vs "NovaSub" vs "autodub"
- Version mismatch: `__init__.py` ghi `1.0.0`, pyproject.toml ghi `2.1.0`, app.py ghi `3.0.0`

---

## 14. Những điều chưa xác định

| Mục | Trạng thái | Ghi chú |
|-----|-----------|---------|
| CI/CD pipeline | `CHƯA XÁC ĐỊNH` | Không thấy config file nào |
| Deployment strategy (backend) | `CHƯA XÁC ĐỊNH` | Có nginx config nhưng không rõ hosting |
| Monitoring/alerting | `CHƯA XÁC ĐỊNH` | Chỉ thấy log, không thấy APM |
| Database backup/migration strategy | `CHƯA XÁC ĐỊNH` | |
| CapCut API stability | `CHƯA XÁC ĐỊNH` | API không chính thức, có thể thay đổi |
| Rate limit behavior under load | `CHƯA XÁC ĐỊNH` | |
| Actual GPU memory requirements | `CHƯA XÁC ĐỊNH` | Code tự detect nhưng chưa test |
| Website SEO/analytics | `CHƯA XÁC ĐỊNH` | |
| Error recovery trong editor flow | `SUY LUẬN` | Có export_state nhưng chưa trace hết |
| Content generator (autodub/content/) | `SUY LUẬN` | Nhỏ (1 file), tạo metadata đăng bài |

---

## 15. File đã kiểm tra

### Đọc toàn bộ
- `README.md`, `pyproject.toml`, `requirements.txt`, `.env.example` (80 dòng đầu)
- `autodub/__init__.py`, `autodub/config.py` (350 dòng), `autodub/securestore.py` (60 dòng)
- `autodub/saas_client.py` (80 dòng), `autodub/batch.py` (80 dòng)
- `autodub/speech/tts/__init__.py`
- `autodub_gui/app.py` (120 dòng), `autodub_gui/workers.py` (80 dòng)
- `control_server/server.js`, `control_server/src/app.js`, `control_server/package.json`
- `control_server/src/models/Device.js`, `control_server/src/models/CreditLedger.js`
- `control_server/src/routes/device.js` (80 dòng), `control_server/src/routes/ai.js` (80 dòng)
- `control_server/src/middleware/auth.middleware.js`
- `website/package.json`

### Đọc một phần (>= 100 dòng)
- `autodub/pipeline.py` (800/2013 dòng — bao phủ toàn bộ luồng chính)

### Liệt kê cấu trúc
- Root, `autodub/`, `autodub/media/`, `autodub/speech/`, `autodub/speech/tts/`, `autodub/text/`, `autodub/tools/`, `autodub/content/`
- `autodub_gui/`, `autodub_gui/pages/`, `autodub_gui/video/`, `autodub_gui/ui/`
- `control_server/`, `control_server/src/`, `control_server/src/routes/`, `control_server/src/services/`, `control_server/src/models/`, `control_server/src/middleware/`, `control_server/src/plugins/`
- `website/`, `website/src/`, `website/src/pages/`, `website/src/pages/admin/`
- `scripts/`, `tests/`

---

## 16. Mức độ tin cậy

| Phần | Mức độ |
|------|--------|
| Cấu trúc project | `ĐÃ XÁC MINH` |
| Technology stack | `ĐÃ XÁC MINH` |
| Entry points | `ĐÃ XÁC MINH` |
| Pipeline steps (7 bước) | `ĐÃ XÁC MINH` |
| Call flows chính | `ĐÃ XÁC MINH` |
| Database models | `ĐÃ XÁC MINH` |
| API endpoints | `ĐÃ XÁC MINH` |
| Auth/Security | `ĐÃ XÁC MINH` |
| Config system | `ĐÃ XÁC MINH` |
| Coding conventions | `ĐÃ XÁC MINH` |
| Editor flow chi tiết | `SUY LUẬN` |
| Rủi ro coupling | `SUY LUẬN` |
| CI/CD | `CHƯA XÁC ĐỊNH` |
| Deployment | `CHƯA XÁC ĐỊNH` |
| Performance profile thực tế | `CHƯA XÁC ĐỊNH` |

---

**TRẠNG THÁI: HOÀN THÀNH**
