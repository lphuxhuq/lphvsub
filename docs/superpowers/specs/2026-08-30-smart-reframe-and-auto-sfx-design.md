# Design Spec: Smart Auto-Reframe (9:16 Shorts/TikTok) & Auto Scene Cut SFX

## 1. Overview
Thiết kế và triển khai 2 tính năng nâng cao phục vụ sản xuất video ngắn (Shorts / TikTok / Reels) và tăng độ lôi cuốn (Retention Rate) của video:
1. **Smart Auto-Reframe (9:16 / 1:1 / 16:9)**: Chuyển đổi linh hoạt tỷ lệ khung hình video với 3 chế độ:
   - *Blur Background*: Nền mờ nghệ thuật chiều sâu điện ảnh.
   - *Top / Split*: Nửa trên hiển thị video, nửa dưới dành cho phụ đề / banner.
   - *Center Crop*: Phóng to lấp đầy màn hình 9:16.
2. **Auto Scene Cut SFX**: Tự động nhận diện điểm chuyển cảnh từ `scene_detector` và chèn hiệu ứng âm thanh chuyển cảnh (*Whoosh, Pop, Swish, Cinematic*) tinh tế, êm ái, hoàn toàn tự động và offline.

---

## 2. Architecture & Modules

### Module 1: Smart Auto-Reframe (`autodub/media/subtitle.py` & `autodub_gui/style_dialog.py`)
- Mở rộng `build_aspect_ratio_filter(aspect_preset, video_w, video_h, reframe_mode="blur_background")`:
  - Mode `blur`: `split[bg][fg]; [bg]scale=tw:th:force_original_aspect_ratio=increase,crop=tw:th,boxblur=30:8,eq=brightness=-0.08:saturation=1.2[bgb]; [fg]scale=tw:th:force_original_aspect_ratio=decrease[fg_s]; [bgb][fg_s]overlay=(W-w)/2:(H-h)/2`
  - Mode `top_split`: Đặt `overlay=(W-w)/2:(H*0.15)` giúp video nằm ở 1/3 - 1/2 trên, nửa dưới thoáng đãng cho phụ đề lớn.
  - Mode `center_crop`: Scale fill toàn bộ canvas `tw:th` và crop chính giữa.
- Thêm điều khiển chọn Tỷ lệ & Chế độ trong `StyleDialog` (Giao diện cài đặt kiểu video).

### Module 2: Auto Scene Cut SFX Generator & Mixer (`autodub/media/sfx.py` & `autodub/media/audio.py`)
- Module `autodub/media/sfx.py`:
  - `generate_sfx_audio(preset="whoosh", sample_rate=44100, duration_s=0.35) -> np.ndarray`
  - Hỗ trợ các preset: `whoosh` (vút gió êm dịu), `pop` (tiếng pop hiện đại), `swish` (chuyển cảnh lướt nhanh), `cinematic` (tiếng trầm điện ảnh).
  - Tự động sinh sóng âm PCM float32/int16 sạch sẽ, không cần bất kỳ tệp nhị phân bên ngoài.
- Tích hợp vào `merge_segments` trong `autodub/media/audio.py`:
  - Nhận danh sách `scene_cuts: list[float] | None` và `sfx_preset: str`, `sfx_volume_db: float`.
  - Tự động lọc các điểm cut quá sát nhau (khoảng cách tối thiểu 3.0s).
  - Hòa trộn SFX mượt mà vào luồng âm thanh tổng hợp.

### Module 3: Cấu hình & Trình chỉnh sửa (`config.py`, `pipeline.py`, `editor.py`)
- Cấu hình trong `Settings`:
  - `video_aspect_preset: str = "original"`
  - `video_reframe_mode: str = "blur"`
  - `auto_sfx_enabled: bool = False`
  - `sfx_preset: str = "whoosh"`
  - `sfx_volume_db: float = -14.0`
- Pipeline & Editor nạp và lưu các tùy chọn vào `render_opts.json` và `export_state`.
