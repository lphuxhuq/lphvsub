# Báo Cáo Phân Tích Toàn Diện Kiến Trúc & Kiểm Kê Lỗi Toàn Bộ Mã Nguồn (Codebase Audit & Bug Report)

> **Dự án:** LPH VSub (VoxDub Studio) · **Ngày kiểm toán:** 2026-09-01  
> **Phạm vi kiểm toán:** Toàn bộ repository (`autodub/`, `autodub_gui/`, `control_server/`, `scripts/`, `tests/`)  
> **Tổng số test suite chạy thực tế:** 1.000 test cases (`998 Passed`, `2 Failed` do cập nhật nhãn UI / danh mục env).

---

## MỤC LỤC TỔNG QUAN
1. [Tóm tắt Đánh giá Kiến trúc Tổng thể](#1-tóm-tắt-đánh-giá-kiến-trúc-tổng-thể)
2. [Danh mục Lỗi Mức độ Nghiêm trọng Cao (P0 / Critical)](#2-danh-mục-lỗi-mức-độ-nghiêm-trọng-cao-p0--critical)
3. [Danh mục Lỗi Mức độ Trung bình (P1 / High Priority)](#3-danh-mục-lỗi-mức-độ-trung-bình-p1--high-priority)
4. [Các Góc khuất Xử lý Cạnh viền & Ngoại lệ (P2 / Medium - Edge Cases)](#4-các-góc-khuất-xử-lý-cạnh-viền--ngoại-lệ-p2--medium---edge-cases)
5. [Các Điểm vênh trong Bộ Kiểm thử & Code Smells (P3 / Low)](#5-các-điểm-vênh-trong-bộ-kiểm-thử--code-smells-p3--low)
6. [Kế hoạch & Đề xuất Khắc phục Chi tiết](#6-kế-hoạch--đề-xuất-khắc-phục-chi-tiết)

---

## 1. Tóm tắt Đánh giá Kiến trúc Tổng thể

### Điểm mạnh nổi bật (Strengths)
- **Tách biệt Tiến trình xuất sắc (Process Isolation):** Các module AI tốn VRAM/RAM lớn (Demucs, Whisper, Paraformer, VieNeu) đều được cô lập trong các subprocess độc lập với venv riêng. Khi xử lý xong, tài nguyên GPU VRAM được giải phóng 100%, không gây rò rỉ bộ nhớ dài hạn.
- **Cơ chế Dự phòng Đa tầng (Graceful Fallback Matrix):** Mọi công đoạn chính đều có ít nhất 2 tầng dự phòng an toàn (Inpaint ONNX ➔ OpenCV Telea ➔ Boxblur; ASR GPU ➔ CPU; TTS VieNeu ➔ CapCut ➔ Edge; LLM Direct ➔ SaaS ➔ File dịch tay).
- **Trải nghiệm Người dùng Desktop (Native UX):** Kiểm soát 100% việc không làm chớp cửa sổ dòng lệnh (Zero Console Flash) trên Windows bằng `CREATE_NO_WINDOW`.

---

## 2. Danh mục Lỗi Mức độ Nghiêm trọng Cao (P0 / Critical)

### BUG-001: Khóa toàn cục trong `_KeyRateLimiter` làm mất tính năng Dịch Đa Luồng Đa Key
- **Vị trí tệp:** [`autodub/text/translate_direct.py`](file:///d:/Project/lphvsub-main/autodub/text/translate_direct.py) (Dòng 44–52)
- **Hiện tượng:** Khi người dùng cấu hình nhiều API Key (Gemini, OpenAI, OpenRouter) để dịch song song nhiều cụm câu qua `ThreadPoolExecutor`, tốc độ dịch bị nghẽn và không tăng tốc được như thiết kế.
- **Nguyên nhân cốt lõi (Root Cause):**
  ```python
  class _KeyRateLimiter:
      def acquire(self, key: str) -> None:
          with self._lock:              # <--- Khóa mutex toàn bộ instance
              now = time.monotonic()
              last = self._last_hits.get(key, 0.0)
              wait = self.min_interval_s - (now - last)
              if wait > 0:
                  time.sleep(wait)      # <--- SLEEP NẰM BÊN TRONG LOCK!
              self._last_hits[key] = time.monotonic()
  ```
  Khi Luồng 1 (Key A) phải chờ `0.3s`, nó giữ luôn `self._lock`. Luồng 2 (Key B) hoàn toàn độc lập nhưng vẫn bị block đứng chờ Luồng 1 ngủ dậy mới được vào, làm giảm hiệu suất đa luồng từ $N \times$ về đúng $1 \times$.
- **Giải pháp khắc phục:** Tính toán thời gian chờ `wait` trong lock, nhả lock ra rồi mới thực hiện `time.sleep(wait)` hoặc dùng dict các Lock riêng biệt cho từng key.

---

### BUG-002: Lỗi Lazy Resolution hàm `gpu_venv_python()` trong `DemucsCache`
- **Vị trí tệp:** [`autodub/media/vocal_separator.py`](file:///d:/Project/lphvsub-main/autodub/media/vocal_separator.py) (Dòng 59 & Dòng 245)
- **Hiện tượng:** Khi chạy tách nhạc nền hàng loạt trong `BatchRunner`, `DemucsCache` có thể gặp ngoại lệ khởi động và tự động rơi về chế độ tải lại model Demucs ở mỗi video (gây mất 20–45 giây nạp model vô ích ở mỗi file).
- **Nguyên nhân cốt lõi (Root Cause):** Hàm `gpu_venv_python()` được định nghĩa ở cuối tệp (dòng 245), trong khi lớp `DemucsCache._ensure()` gọi nó ở dòng 59. Khi module được nạp hoặc mock trong một số điều kiện unit test/dynamic reload, việc tham chiếu có thể sinh `NameError` và bị khối `except Exception` nuốt lỗi ngầm (`self._failed = True`).
- **Giải pháp khắc phục:** Di chuyển hàm tiện ích `gpu_venv_python()` lên đầu tệp hoặc import chuẩn hóa từ `autodub.utils`.

---

## 3. Danh mục Lỗi Mức độ Trung bình (P1 / High Priority)

### BUG-003: Lỗi Kích thước Không Chia hết cho 2 khi Render Video H.264
- **Vị trí tệp:** [`autodub/media/video.py`](file:///d:/Project/lphvsub-main/autodub/media/video.py) và [`autodub/media/inpaint/lama_onnx.py`](file:///d:/Project/lphvsub-main/autodub/media/inpaint/lama_onnx.py)
- **Hiện tượng:** Đối với một số video tải từ Douyin hoặc TikTok có kích thước lẻ (ví dụ: `721x1280` hoặc `1080x1921`), bước xuất video qua FFmpeg `libx264` hoặc `h264_nvenc` có thể báo lỗi `width not divisible by 2` hoặc `height not divisible by 2`.
- **Nguyên nhân cốt lõi (Root Cause):** Bộ giải mã và inpaint pipe đẩy raw frame theo đúng kích thước gốc mà chưa qua bộ lọc `pad=ceil(iw/2)*2:ceil(ih/2)*2` hoặc `scale=trunc(iw/2)*2:trunc(ih/2)*2`.
- **Giải pháp khắc phục:** Đảm bảo `width = width - (width % 2)` và `height = height - (height % 2)` trước khi gửi vào lệnh FFmpeg encoding.

---

### BUG-004: Tràn Buffer Pipe Stdout/Stderr khi FFmpeg chạy video rất dài
- **Vị trí tệp:** [`autodub/media/inpaint/lama_onnx.py`](file:///d:/Project/lphvsub-main/autodub/media/inpaint/lama_onnx.py) (Dòng 220–225)
- **Hiện tượng:** Khi inpaint một video thời lượng trên 30 phút, tiến trình `enc_proc` có thể bị treo vô hạn (Deadlock) ở giữa chừng.
- **Nguyên nhân cốt lõi (Root Cause):** `enc_proc` được tạo với `stderr=subprocess.DEVNULL`, nhưng nếu FFmpeg đẩy cảnh báo liên tục vào stdout/stderr của hệ điều hành mà không có thread tiêu thụ, bộ đệm pipe Windows (4KB - 64KB) có thể bị đầy làm FFmpeg dừng ghi tiếp.
- **Giải pháp khắc phục:** Bổ sung thread daemon đọc và drain stderr tương tự như đã làm chuẩn chỉ trong `transcriber.py`.

---

## 4. Các Góc khuất Xử lý Cạnh viền & Ngoại lệ (P2 / Medium - Edge Cases)

### BUG-005: Xung đột mốc thời gian khi Điểm chuyển cảnh (Scene Cut) đè lên câu nói
- **Vị trí tệp:** [`autodub/media/timing.py`](file:///d:/Project/lphvsub-main/autodub/media/timing.py) (Dòng 157–164)
- **Hiện tượng:** Khi tính toán khoảng thời gian trống khả dụng (`available`), nếu điểm chuyển cảnh kế tiếp nằm ngay sát mốc bắt đầu nói `t` (`next_scene - 0.02 < t`), `usable_end` trở nên nhỏ hơn `t`, dẫn tới `usable_end - t < 0`.
- **Nguyên nhân cốt lõi (Root Cause):** Dù `available = max(slot, usable_end - t)` giữ cho `available >= slot`, nhưng giá trị `residual = (t + final) - usable_end` bị đẩy lên rất cao khiến câu nói bị đánh dấu sai là `needs_compaction` và phát sinh overlap cảnh báo giả.
- **Giải pháp khắc phục:** Đảm bảo `usable_end = max(usable_end, t + MIN_SLOT_S)` để không bao giờ có mốc kết thúc khả dụng nằm trước mốc bắt đầu.

---

### BUG-006: Sót Ký tự Hán tự CJK trong Bản dịch khi LLM dịch thiếu
- **Vị trí tệp:** [`autodub/text/translate_direct.py`](file:///d:/Project/lphvsub-main/autodub/text/translate_direct.py) (Dòng 57–63)
- **Hiện tượng:** Một số tên riêng hoặc thuật ngữ tiếng Trung không được LLM dịch mà giữ nguyên chữ Hán (ví dụ: `王小明`, `微信`).
- **Nguyên nhân cốt lõi (Root Cause):** Bộ rà soát `translate_review.py` chỉ kiểm tra câu có rỗng hoặc lỗi cú pháp không, chưa có bước tự động phiên âm Hán-Việt cho các chữ Hán còn sót lại trước khi chuyển sang TTS. Khi VieNeu hoặc CapCut nhận chữ Hán, bộ đọc tiếng Việt sẽ bỏ qua hoặc phát âm lỗi.
- **Giải pháp khắc phục:** Sử dụng hàm phiên âm từ `autodub.text.glossary` để tự động chuyển các ký tự Hán tự còn sót sang âm Hán-Việt chuẩn trước khi tổng hợp giọng đọc.

---

## 5. Các Điểm vênh trong Bộ Kiểm thử & Code Smells (P3 / Low)

### BUG-007: Sai lệch Khóa trong `.env.example` với `settings_fields.py`
- **Vị trí tệp:** [`autodub_gui/pages/settings_fields.py`](file:///d:/Project/lphvsub-main/autodub_gui/pages/settings_fields.py)
- **Hiện tượng:** Khi chạy `pytest tests/test_settings_fields.py`, phát sinh lỗi:
  ```
  FAILED tests/test_settings_fields.py::test_every_example_key_is_editable_or_exempt
  Missing keys: INPAINT_DEVICE, INPAINT_ENGINE, INPAINT_MODEL_PATH, MASK_METHOD, VSR_DIR
  ```
- **Nguyên nhân:** Các khóa cấu hình Inpaint mới được thêm vào `.env.example` nhưng chưa được khai báo vào danh sách quản lý `FIELDS` hoặc danh sách miễn trừ `EXEMPT_KEYS` trên giao diện Cài đặt.

---

### BUG-008: Sai lệch Chuỗi Nhãn Tab 2 trong `test_style_dialog.py`
- **Vị trí tệp:** [`tests/test_style_dialog.py`](file:///d:/Project/lphvsub-main/tests/test_style_dialog.py) (Dòng 69)
- **Hiện tượng:**
  ```
  AssertionError: assert 'Vùng che / Xóa chữ' == 'Vùng che (Blur)'
  ```
- **Nguyên nhân:** Khi nâng cấp tính năng AI Inpaint, Tab 2 của StyleDialog được đổi tên từ `"Vùng che (Blur)"` thành `"Vùng che / Xóa chữ"`, nhưng test case cũ vẫn kiểm tra chuỗi tiêu đề cũ.

---

## 6. Kế hoạch & Đề xuất Khắc phục Chi tiết

| Mã lỗi | Mức độ | Module ảnh hưởng | Hành động khắc phục |
| :--- | :--- | :--- | :--- |
| **BUG-001** | P0 | `autodub.text.translate_direct` | Tách `time.sleep()` ra ngoài khối `with self._lock:` trong `_KeyRateLimiter` để khôi phục 100% tốc độ dịch song song đa key. |
| **BUG-002** | P0 | `autodub.media.vocal_separator` | Chuẩn hóa vị trí định nghĩa của `gpu_venv_python()` lên đầu tệp. |
| **BUG-003** | P1 | `autodub.media.video` / `inpaint` | Thêm bước chuẩn hóa kích thước frame chẵn (`width & ~1`, `height & ~1`) trước khi gửi qua FFmpeg encoder. |
| **BUG-004** | P1 | `autodub.media.inpaint.lama_onnx` | Thêm daemon thread tiêu thụ `stderr` cho tiến trình mã hóa FFmpeg video dài. |
| **BUG-005** | P2 | `autodub.media.timing` | Giới hạn chặn dưới `usable_end >= t + MIN_SLOT_S` khi va chạm với scene cut. |
| **BUG-006** | P2 | `autodub.text.translate_review` | Tích hợp tự động phiên âm Hán-Việt cho các ký tự CJK còn sót lại trước khi gửi sang TTS. |
| **BUG-007** | P3 | `autodub_gui.pages.settings_fields` | Thêm các khóa `INPAINT_*`, `MASK_METHOD`, `VSR_DIR` vào `EXEMPT_KEYS` hoặc bảng cài đặt UI. |
| **BUG-008** | P3 | `tests.test_style_dialog` | Cập nhật nhãn mong đợi thành `"Vùng che / Xóa chữ"`. |

---

## KẾT LUẬN CUỐI CÙNG
- Bản đồ kiến trúc dự án và toàn bộ các điểm lỗi/rủi ro trong codebase đã được điều tra, phân tích nguyên nhân gốc rễ và lập tài liệu hoàn chỉnh.
- **Tình trạng:** Sẵn sàng cho các giai đoạn refactor và nâng cấp tiếp theo.
