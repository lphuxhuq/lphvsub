# Logo / Watermark Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm tùy chọn chèn Logo / Watermark thương hiệu vào video xuất ra (tùy chỉnh vị trí 4 góc, kích thước %, độ mờ opacity và khoảng cách lề) trên toàn bộ hệ thống từ FFmpeg filtergraph, Pipeline xử lý, Cài đặt và Giao diện Tạo dự án mới / Trình chỉnh sửa.

**Architecture:** Mở rộng `build_filter_complex` trong `autodub/media/subtitle.py` để chèn luồng overlay logo với tính toán tọa độ và kênh alpha (`colorchannelmixer=aa=...`), sau đó tích hợp các tham số logo vào `DubRequest`, `Settings`, `merge_video`, `editor.py` và các widget giao diện trong `autodub_gui`.

**Tech Stack:** Python 3.11, PySide6, FFmpeg Filtergraph (overlay, scale, movie/colorchannelmixer), Pytest.

## Global Constraints

- Logo overlay phải luôn nằm dưới phụ đề (`subtitles=...`) để đảm bảo chữ phụ đề luôn đọc rõ ràng.
- Nếu đường dẫn logo không tồn tại hoặc rỗng, hệ thống phải tự động bỏ qua mà không gây lỗi xuất video.
- Mọi đơn vị tọa độ và kích thước co dãn phải tương thích hoàn toàn với tất cả tỷ lệ khung hình (16:9, 9:16, 1:1).

---

### Task 1: Xây dựng FFmpeg Filtergraph Overlay Logo & Kiểm thử lõi

**Files:**
- Modify: `autodub/media/subtitle.py:263-326`
- Modify: `autodub/media/video.py:191-285`
- Test: `tests/test_subtitle.py`
- Test: `tests/test_video_merge.py`

**Interfaces:**
- `build_filter_complex(blur_regions, video_w, video_h, srt_path, style, aspect_preset, logo_path, logo_position, logo_scale, logo_opacity, logo_margin)` -> `str | None`
- `merge_video(..., logo_path=None, logo_position="top_right", logo_scale=0.12, logo_opacity=0.85, logo_margin=24)` -> `str`

- [ ] **Step 1: Viết failing test cho filtergraph logo trong `tests/test_subtitle.py`**

```python
def test_build_filter_complex_with_logo_overlay():
    from autodub.media.subtitle import build_filter_complex
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        logo_path="D:/logo.png",
        logo_position="top_right",
        logo_scale=0.15,
        logo_opacity=0.8,
        logo_margin=30,
    )
    assert graph is not None
    assert "movie=" in graph or "overlay=" in graph
    assert "colorchannelmixer=aa=0.8" in graph
    assert "scale=" in graph
```

- [ ] **Step 2: Chạy test để xác nhận test fail**

Chạy: `pytest tests/test_subtitle.py::test_build_filter_complex_with_logo_overlay -v`
Kỳ vọng: FAIL do `build_filter_complex` chưa nhận tham số `logo_path`.

- [ ] **Step 3: Triển khai tính năng logo trong `autodub/media/subtitle.py` và `autodub/media/video.py`**

Thêm logic tính toán tọa độ `overlay` theo vị trí `top_left`, `top_right`, `bottom_left`, `bottom_right`, `top_center`, `bottom_center`, `center` và tạo chuỗi filter:
```python
def _logo_overlay_coords(position: str, margin: int) -> tuple[str, str]:
    if position == "top_left":
        return f"{margin}", f"{margin}"
    if position == "bottom_left":
        return f"{margin}", f"main_h-overlay_h-{margin}"
    if position == "bottom_right":
        return f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"
    if position == "top_center":
        return f"(main_w-overlay_w)/2", f"{margin}"
    if position == "bottom_center":
        return f"(main_w-overlay_w)/2", f"main_h-overlay_h-{margin}"
    if position == "center":
        return f"(main_w-overlay_w)/2", f"(main_h-overlay_h)/2"
    # Mặc định top_right
    return f"main_w-overlay_w-{margin}", f"{margin}"
```

- [ ] **Step 4: Chạy lại test xác nhận test PASS**

Chạy: `pytest tests/test_subtitle.py tests/test_video_merge.py -v`
Kỳ vọng: PASS toàn bộ.

---

### Task 2: Cấu hình Settings, DubRequest và Pipeline

**Files:**
- Modify: `autodub/config.py:355-365`
- Modify: `autodub/pipeline.py:90-110, 950-1010`
- Modify: `autodub/editor.py:520-550, 740-800`
- Test: `tests/test_editor.py`

**Interfaces:**
- `Settings`: `logo_path: str`, `logo_position: str`, `logo_scale: float`, `logo_opacity: float`, `logo_margin: int`
- `DubRequest`: `logo_path: str | None`, `logo_position: str | None`, `logo_scale: float | None`, `logo_opacity: float | None`, `logo_margin: int | None`

- [ ] **Step 1: Viết test cho DubRequest và Editor options với logo**

```python
def test_dub_request_and_editor_with_logo():
    from autodub.pipeline import DubRequest
    req = DubRequest(
        logo_path="C:/path/logo.png",
        logo_position="bottom_right",
        logo_scale=0.10,
        logo_opacity=0.9,
        logo_margin=20,
    )
    assert req.logo_path == "C:/path/logo.png"
    assert req.logo_position == "bottom_right"
```

- [ ] **Step 2: Thêm các trường cấu hình vào `Settings`, `DubRequest`, `pipeline.py` và `editor.py`**

- Thêm vào `autodub/config.py`: `logo_path`, `logo_position`, `logo_scale`, `logo_opacity`, `logo_margin`.
- Truyền các tham số từ `req` vào `merge_video` trong `autodub/pipeline.py`.
- Hỗ trợ `logo_path`, `logo_position` trong `load_render_opts` / `save_render_opts` / `rebuild_output` trong `autodub/editor.py`.

- [ ] **Step 3: Chạy test xác nhận test PASS**

Chạy: `pytest tests/test_editor.py -v`
Kỳ vọng: PASS.

---

### Task 3: Tích hợp Giao diện Người dùng (Settings, Wizard, Editor)

**Files:**
- Modify: `autodub_gui/pages/settings_fields.py`
- Modify: `autodub_gui/pages/new_project_steps.py`
- Modify: `autodub_gui/pages/new_project_page.py`
- Modify: `autodub_gui/pages/editor_export.py`

**Interfaces:**
- `StepVoice` / `VoiceStep` trong `new_project_steps.py`: Widget chọn tệp logo, chọn vị trí hiển thị, thanh kéo độ mờ.
- `NewProjectPage`: Đọc `logo_path`, `logo_position`, `logo_scale`, `logo_opacity` từ wizard và đẩy vào `DubRequest`.

- [ ] **Step 1: Thêm nhóm Logo vào `settings_fields.py` trong thẻ `TAB_ADVANCED`**

Khai báo các trường `LOGO_PATH` (FILE), `LOGO_POSITION` (COMBO), `LOGO_SCALE` (SLIDER), `LOGO_OPACITY` (SLIDER), `LOGO_MARGIN` (NUMBER).

- [ ] **Step 2: Bổ sung khối chọn Logo vào Bước 4 (Giọng & Phụ đề) trong `new_project_steps.py`**

Thêm `CollapsibleSection("Logo & Watermark thương hiệu")` với các trường chọn ảnh, vị trí hiển thị và độ trong suốt.

- [ ] **Step 3: Cập nhật `new_project_page.py` và `editor_export.py` để kết nối dữ liệu Logo**

Đảm bảo `_build_request` và `rebuild_output` nhận đúng `logo_path`, `logo_position`, `logo_scale`, `logo_opacity`.

- [ ] **Step 4: Chạy kiểm thử toàn bộ hệ thống**

Chạy: `pytest tests/ -v`
Kỳ vọng: Toàn bộ test suite PASS.
