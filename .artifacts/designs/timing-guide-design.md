# Architecture Design: Timing Guide / Report System

**Feature:** Timing Guide Generator & Exporter
**Module:** `autodub.media.timing` & `autodub.pipeline`

---

## 1. Kiến trúc thành phần (Component Architecture)

```
[TTS Phase / Audio Generation]
               │
               ▼
   [autodub.media.timing]
   ┌───────────────────────────────────────────────────────────┐
   │ def build_timing_guide(...) -> dict                       │
   │   - So sánh original_duration vs tts_duration             │
   │   - Phân loại trạng thái: OK, TOO_LONG, TOO_SHORT        │
   │   - Tạo edit_hint (ví dụ: "VI dài hơn 0.7s")              │
   │   - Tính summary (tổng thời lượng, tỉ lệ, số câu lệch)   │
   │                                                           │
   │ def save_timing_guide(work_dir: str, guide: dict) -> str  │
   │   - Lưu file JSON ra: <work_dir>/data/timing_report.json  │
   └───────────────────────────────────────────────────────────┘
               │
               ▼
[autodub.pipeline.py]
  - Gọi build_timing_guide() sau bước TTS/Soft Timing
  - Ghi file timing_report.json vào work_dir
```

---

## 2. Chi tiết API & Hàm

### Hàm 1: `build_timing_guide` trong `autodub/media/timing.py`

```python
def build_timing_guide(
    segments: list[dict],
    durations: list[float | None],
    target_field: str = "text_vi",
    tolerance_ratio: float = 0.3,
    source_url: str = "",
) -> dict:
    """Tạo báo cáo chi tiết so khớp thời lượng từng câu thoại giữa bản gốc và TTS."""
```

**Output Schema:**
```json
{
  "summary": {
    "total_segments": 49,
    "total_original_duration": 120.5,
    "total_tts_duration": 124.2,
    "ratio": 1.03,
    "segments_ok": 44,
    "segments_need_edit": 5
  },
  "source_url": "...",
  "segments": [
    {
      "id": 1,
      "start": 0.45,
      "end": 1.25,
      "original_duration": 0.8,
      "tts_duration": 0.75,
      "diff_seconds": -0.05,
      "status": "OK",
      "edit_hint": "OK",
      "text_original": "...",
      "text_target": "..."
    }
  ]
}
```

### Hàm 2: `save_timing_guide` trong `autodub/media/timing.py`

```python
def save_timing_guide(
    work_dir: str,
    guide: dict,
    filename: str = "timing_report.json"
) -> str:
    """Ghi timing guide ra file JSON trong thư mục data của dự án."""
```

---

## 3. Tích hợp vào Pipeline (`autodub/pipeline.py`)

- Tại bước 5 (sau khi có `tts_results` và `durations` của từng câu thoại) và bước 6 (sau `apply_soft_timing`):
  - Thu thập danh sách `durations` của các file âm thanh TTS.
  - Gọi `build_timing_guide(...)` và `save_timing_guide(work_dir, guide)`.
  - Log tóm tắt (ví dụ: `Timing guide exported: 44/49 segments OK (ratio: 1.03)`).

---

## 4. Rủi ro hồi quy (Regression Risk) & Biện pháp

- **Rủi ro:** Không có rủi ro với luồng hiện tại vì đây là hàm sinh thêm dữ liệu và lưu thêm 1 file JSON độc lập.
- **Kiểm thử:** Viết unit test riêng trong `tests/test_timing_guide.py` kiểm tra:
  - Tính toán đúng `diff_seconds`, `status`, `edit_hint`.
  - Xử lý mảng rỗng, `duration = 0`, `duration = None`.
  - Tỉ lệ tính toán `ratio`.
  - Ghi file đúng định dạng JSON UTF-8.

---

`TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ`
