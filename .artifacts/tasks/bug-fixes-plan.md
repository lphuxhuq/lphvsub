# TASK BREAKDOWN: FIX CRASH BUGS & LOGIC ERRORS (VOXDUB STUDIO V3.0.0)

- **Trạng thái**: `TRẠNG THÁI: CHỜ DUYỆT TASK`
- **Mục tiêu**: Kế hoạch khắc phục triệt để 8 bug crash và lỗi logic đã phát hiện qua kiểm toán toàn diện.
- **Nguyên tắc**: Từng unit độc lập, có acceptance criteria rõ ràng, có unit test tự động xác minh chống regression, không phá vỡ bất kỳ test nào trong 1337 test cases hiện có.

---

## 1. Dependency Graph

```
TASK-001 (P0: Fix Parallel Export Audio & Subtitle Sync)
   │
TASK-002 (P0: Fix translate_segments_direct Empty Segments Crash)
   │
TASK-003 (P1: Fix QTimer Context trong Editor AI Retranslate)
   │
TASK-004 (P1: Scikit-learn Dependency & Lazy Fallback trong Diarization)
   │
TASK-005 (P2: Fix sub_vi Splitting & Merging trong Editor)
   │
TASK-006 (P2: Fix ZeroDivisionError trong _apply_slowdown)
   │
TASK-007 (P2: Fix payosOrderCode: 0 trong Keycode Generator)
   │
TASK-008 (P3: Fix .env Root Path Traversal trong SaaS AI Gateway)
   │
   ▼
TASK-009 (Integration Verification: Run Full Test Suites & Ruff)
```

---

## 2. Danh sách Unit

### TASK-001 — Fix Parallel Export Audio Desync & Subtitle PTS Misalignment (P0)
- **Mục tiêu:**
  1. Khắc phục lỗi video >= 45s bị phình thời lượng gấp 4 lần (video 60s thành 240s) và tiếng bị lặp lại trong `autodub/media/video.py`.
  2. Đảm bảo âm thanh trong từng chunk được cắt chính xác từ `start_s` đến `end_s`.
  3. Bảo vệ phụ đề cứng (`burn_srt`) và các bộ lọc phụ thuộc thời gian (`between(t, ...)`) không bị lệch mốc hiển thị do reset PTS.
- **Dependency:** Không.
- **File được phép sửa:** `autodub/media/video.py`, `tests/test_video_merge.py`.
- **File không được sửa:** `autodub/media/parallel_export.py`, `autodub/media/subtitle.py`.
- **Thay đổi chi tiết:**
  1. Trong hàm `_build_chunk_cmd` (`autodub/media/video.py`):
     Thêm `-ss {start_s:.3f} -to {end_s:.3f}` ngay trước `-i audio_path`.
     Nếu `subtitle_mode == "soft"`, thêm `-ss {start_s:.3f} -to {end_s:.3f}` trước `-i srt_path`.
  2. Trong điều kiện kích hoạt `parallel_enabled`:
     Nếu `subtitle_mode == "burn"` hoặc có vùng làm mờ theo khoảng thời gian (`has_timed_blur`), phụ đề đọc theo PTS (bị reset về 0 trong chunk) sẽ gây lệch phụ đề. Khi đó tự động chuyển sang luồng 1-process tuần hoàn tin cậy để đảm bảo 100% khớp sub và âm thanh.
- **Acceptance Criteria:**
  1. Xuất video 60s có re-encode ra đúng thời lượng 60.0s (cả video stream và audio stream đều đúng 60.0s, không bị phình thành 240s).
  2. Âm thanh từng đoạn khớp chính xác với hình ảnh.
  3. Video có phụ đề cứng hiển thị đúng mốc thời gian của từng câu.
- **Test:**
  - `py -m pytest tests/test_video_merge.py tests/test_parallel_export.py`
  - Thêm integration test kiểm tra thời lượng stream audio và video sau khi merge bằng parallel export.
- **Rủi ro:** Không có.

---

### TASK-002 — Fix `translate_segments_direct` Crash khi `segments` Rỗng (P0)
- **Mục tiêu:** Ngăn chặn crash `ValueError: max_workers must be greater than 0` khi video không có lời thoại hoặc danh sách segments rỗng.
- **Dependency:** Không.
- **File được phép sửa:** `autodub/text/translate_direct.py`, `tests/test_translate_direct.py`.
- **File không được sửa:** `autodub/text/translate_saas.py`, `autodub/text/translate_hint.py`.
- **Thay đổi chi tiết:**
  Thêm early return guard tại đầu hàm `translate_segments_direct`:
  ```python
  if not segments:
      return []
  ```
- **Acceptance Criteria:**
  1. `translate_segments_direct([], ...)` trả về `[]` ngay lập tức, không ném exception.
  2. Pipeline tiếp tục xử lý mượt mà khi video không có lời thoại.
- **Test:**
  - Thêm test case `test_translate_segments_direct_empty_segments` trong `tests/test_translate_direct.py`.
- **Rủi ro:** Cực thấp.

---

### TASK-003 — Fix QTimer Context trong Editor AI Retranslate (P1)
- **Mục tiêu:** Đảm bảo callback `_done` và `_err` trong `_ai_translate_one` và `_ai_retranslate_all` được gửi về main thread Qt và thực thi, thay vì bị drop âm thầm.
- **Dependency:** TASK-002.
- **File được phép sửa:** `autodub_gui/pages/editor_page.py`.
- **File không được sửa:** `autodub_gui/pages/editor_panels.py`, `autodub/editor.py`.
- **Thay đổi chi tiết:**
  Trong `autodub_gui/pages/editor_page.py`:
  - Dòng 1171 & 1178: Đổi `QTimer.singleShot(0, _done)` thành `QTimer.singleShot(0, self, _done)` và `QTimer.singleShot(0, self, _err)`.
  - Dòng 1242 & 1250: Đổi `QTimer.singleShot(0, _done)` thành `QTimer.singleShot(0, self, _done)` và `QTimer.singleShot(0, self, _err)`.
- **Acceptance Criteria:**
  1. Khi người dùng bấm "Dịch lại câu bằng AI" hoặc "Dịch lại toàn bộ bằng AI", sau khi dịch xong, bảng Editor cập nhật nội dung mới, banner lưu trạng thái và toast notification thành công/thất bại hiển thị trên giao diện.
- **Test:**
  - `py -m pytest tests/test_timeline_waveform.py -k "test_editor_page"`
- **Rủi ro:** Cực thấp.

---

### TASK-004 — Khai báo `scikit-learn` & Fallback An toàn trong Diarization (P1)
- **Mục tiêu:** Đảm bảo môi trường cài mới không bị lỗi `ModuleNotFoundError: No module named 'sklearn'` khi chạy bước 3.6 (phân cụm người nói).
- **Dependency:** Không.
- **File được phép sửa:** `requirements.txt`, `pyproject.toml`, `autodub/speech/diarization.py`.
- **File không được sửa:** `autodub/pipeline.py`.
- **Thay đổi chi tiết:**
  1. Thêm `scikit-learn>=1.3.0` vào `requirements.txt` và `pyproject.toml`.
  2. Bọc import `sklearn` trong `diarization.py` với try/except; nếu thiếu thư viện, tự động ghi warning và fallback về chế độ 1 speaker (`speaker_id = 0`) thay vì làm sập pipeline.
- **Acceptance Criteria:**
  1. File `requirements.txt` và `pyproject.toml` có đủ dependency.
  2. `diarization.py` chạy mượt mà ngay cả khi môi trường không có `sklearn`.
- **Test:**
  - `py -m pytest tests/test_speaker_diarization.py`
- **Rủi ro:** Cực thấp.

---

### TASK-005 — Fix `sub_vi` Splitting & Merging trong Editor (P2)
- **Mục tiêu:** Khắc phục lỗi tách câu trong Editor làm nhân bản 100% dòng phụ đề tuỳ biến sang cả 2 câu con, và lỗi gộp câu làm rơi phụ đề tuỳ biến.
- **Dependency:** Không.
- **File được phép sửa:** `autodub/editor.py`, `tests/test_subtitle_text.py`.
- **File không được sửa:** `autodub/text/srt.py`.
- **Thay đổi chi tiết:**
  1. Trong `split_segment`:
     Kiểm tra nếu câu cha có `SUBTITLE_FIELD` (`sub_vi`):
     - Dùng `_split_text(sub_text, ratio)` để chia tương ứng cho `left` và `right`, hoặc xóa `SUBTITLE_FIELD` để 2 câu con tự động hiển thị theo lời đọc mới cắt.
  2. Trong `merge_segments`:
     Nếu các câu con có `SUBTITLE_FIELD`, gộp lại bằng dấu cách hoặc cập nhật đồng bộ với lời đọc đã gộp.
- **Acceptance Criteria:**
  1. Sau khi tách câu, câu trái chỉ chứa phụ đề nửa trái, câu phải chỉ chứa phụ đề nửa phải.
  2. Sau khi gộp câu, phụ đề hiển thị đầy đủ nội dung của toàn bộ các câu được gộp.
- **Test:**
  - Thêm unit test `test_split_segment_preserves_subtitles` và `test_merge_segments_preserves_subtitles` trong `tests/test_subtitle_text.py`.
- **Rủi ro:** Cực thấp.

---

### TASK-006 — Fix ZeroDivisionError trong `_apply_slowdown` (P2)
- **Mục tiêu:** Ngăn chặn lỗi chia cho 0 khi đọc file marker `deferred_speed.json` chứa giá trị speed không hợp lệ hoặc bằng 0.
- **Dependency:** Không.
- **File được phép sửa:** `autodub/editor.py`.
- **File không được sửa:** `autodub/media/retime.py`.
- **Thay đổi chi tiết:**
  Trong `autodub/editor.py:765`:
  Đổi:
  ```python
  if speed < 0.999:
  ```
  Thành:
  ```python
  if 0.1 <= speed < 0.999:
  ```
- **Acceptance Criteria:**
  1. Nếu `speed <= 0` hoặc `speed < 0.1`, hệ thống bỏ qua và không bị lỗi `ZeroDivisionError`.
- **Test:**
  - `py -m pytest tests/test_retime.py`
- **Rủi ro:** Cực thấp.

---

### TASK-007 — Fix `payosOrderCode: 0` trong Keycode Generator (P2)
- **Mục tiêu:** Ngăn chặn việc sinh mã đơn hàng ánh xạ ra số 0 khiến PayOS từ chối tạo link thanh toán.
- **Dependency:** Không.
- **File được phép sửa:** `control_server/src/utils/keycode.js`, `control_server/tests/utils.test.js`.
- **File không được sửa:** `control_server/src/services/billing.service.js`.
- **Thay đổi chi tiết:**
  Trong `control_server/src/utils/keycode.js:55`:
  Đổi `crypto.randomInt(0, 1_000_000)` thành `crypto.randomInt(1, 1_000_000)`.
- **Acceptance Criteria:**
  1. `generateOrderCode()` luôn sinh số từ 1 đến 999,999.
  2. `payosOrderCode` luôn $\ge 1$, 100% hợp lệ với PayOS.
- **Test:**
  - Chạy `npm test` trong `control_server/` (đảm bảo 59/59 test pass).
- **Rủi ro:** Không có.

---

### TASK-008 — Fix `.env` Root Path Traversal trong SaaS AI Gateway (P3)
- **Mục tiêu:** Sửa lỗi lùi thừa 1 cấp thư mục khiến server chạy từ thư mục `control_server/` không đọc được file `.env` gốc của repository.
- **Dependency:** Không.
- **File được phép sửa:** `control_server/src/services/ai-gateway.service.js`.
- **File không được sửa:** `control_server/server.js`.
- **Thay đổi chi tiết:**
  Trong `control_server/src/services/ai-gateway.service.js:44`:
  Đổi:
  ```javascript
  path.join(__dirname, '../../../../.env'),      // sai: 4 cấp lùi ra ngoài repo
  ```
  Thành:
  ```javascript
  path.join(__dirname, '../../../.env'),        // đúng: 3 cấp từ src/services trỏ về repo root
  ```
- **Acceptance Criteria:**
  1. Server tự động đọc được API keys từ root `.env` khi khởi động từ bất kỳ thư mục nào.
- **Test:**
  - `npm test` trong `control_server/`.
- **Rủi ro:** Cực thấp.

---

### TASK-009 — Integration Verification & Regression Check
- **Mục tiêu:** Chạy toàn bộ test suites của Python, Node.js và linter Ruff để đảm bảo không có bất kỳ regression nào sau khi áp dụng các fix.
- **Dependency:** TASK-001 đến TASK-008.
- **Scope:** Toàn bộ test suite.
- **Acceptance Criteria:**
  1. `py -m pytest` vượt qua 100% test cases (>= 1337 passed).
  2. `control_server` chạy `npm test` vượt qua 100% (>= 59 passed).
  3. `py -m ruff check .` báo `All checks passed!`.
  4. Video 60s xuất ra có thời lượng khớp 100% giữa video và audio.

---

## 3. Thứ tự Thực hiện

1. **Nhóm P0 & P1 (Lõi & Crash):** TASK-001 $\rightarrow$ TASK-002 $\rightarrow$ TASK-004
2. **Nhóm GUI & Editor (Trải nghiệm người dùng):** TASK-003 $\rightarrow$ TASK-005 $\rightarrow$ TASK-006
3. **Nhóm SaaS Backend:** TASK-007 $\rightarrow$ TASK-008
4. **Kiểm tra tích hợp:** TASK-009

---

## 4. Change Budget

- Tổng số file thay đổi: **9 file mã nguồn** + **3 file test / cấu hình**.
- Mỗi sửa đổi chỉ tác động cục bộ tại đúng vị trí phát sinh bug, không refactor lan man.
- Không thay đổi interface hay breaking changes đối với các module khác.

---

`TRẠNG THÁI: CHỜ DUYỆT TASK`
