"""Kiểu phụ đề và bộ lọc ffmpeg cho phần ghi chữ / che chữ lên hình.

Đây là NGUỒN DUY NHẤT định nghĩa một "kiểu phụ đề" trong toàn ứng dụng: trang
Cài đặt, hộp thoại chỉnh kiểu chữ, pipeline và trình chỉnh sửa đều đọc cùng
các khóa ở đây, nên chữ xem trước và chữ ghi vào video luôn khớp nhau.

Hai việc, gộp trong đúng một lượt mã hóa lại (:func:`build_filter_complex`):

1. **Che chữ trên hình** — phụ đề cứng của video gốc. Người dùng khoanh vùng
   trong giao diện; tọa độ lưu dạng chuẩn hóa 0..1 nên đổi độ phân giải vẫn
   đúng chỗ.
2. **Ghi phụ đề vào hình** — vẽ phụ đề tiếng Việt đè lên vùng đã che, bằng
   libass, nên chữ cũ bị giấu và chữ mới nằm đúng chỗ của nó.

Chỗ khó nhất là thoát đường dẫn cho bộ lọc ``subtitles`` trên Windows: chuỗi
đi qua bộ đọc filtergraph của ffmpeg RỒI mới tới bộ đọc tùy chọn của bộ lọc,
nên ``C:\\out\\a.srt`` phải thành ``C\\:/out/a.srt``.
"""
from __future__ import annotations

import re

# Độ mờ của vùng che: boxblur luma_radius:luma_power. Bán kính 10 xóa sạch
# chữ mà vẫn nhẹ; vùng che là chữ đục nên không mất chi tiết gì.
MAX_BLUR_RADIUS = 10
BLUR_POWER = 2

#: Kiểu phụ đề đầy đủ — mọi khóa đều có mặt để không nơi nào phải đoán.
DEFAULT_STYLE: dict = {
    "preset": "clean",
    "position": "bottom",       # "bottom" | "middle" | "top"
    "font": "Arial",
    "font_size": 22,
    "margin_v": 40,
    "outline": 2,
    "shadow": 0,
    "bold": True,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "box": "none",              # "none" (chỉ viền) | "box" (khối nền đặc)
    "box_color": "#000000",
    "box_opacity": 60,          # 0–100, chỉ dùng khi box = "box"
    "line_words": 0,            # 0 = tự xuống dòng theo bề rộng
    "max_lines": 2,
    "all_caps": False,
    "display": "sentence",      # "sentence" | "karaoke"
    "words_per_cue": 3,
    "effect": "pop",            # "pop" | "fade" | "karaoke" | "none"
    "highlight_color": "#FFD54A",
}

#: Bộ kiểu dựng sẵn — (khóa, tên hiển thị, mô tả ngắn, phần ghi đè).
#: Người dùng chọn một bộ rồi tinh chỉnh; mọi khóa không nêu giữ mặc định.
PRESETS: tuple[tuple[str, str, str, dict], ...] = (
    ("clean", "Gọn gàng", "Chữ trắng viền đen, hợp mọi loại video", {
        "font_size": 22, "outline": 2, "shadow": 0, "bold": True,
        "color": "#FFFFFF", "outline_color": "#000000", "box": "none",
        "line_words": 0, "max_lines": 2, "display": "sentence",
    }),
    ("bold_yellow", "Nổi bật", "Chữ vàng viền dày, hợp video giải trí", {
        "font_size": 26, "outline": 3, "shadow": 1, "bold": True,
        "color": "#FFE24A", "outline_color": "#101010", "box": "none",
        "line_words": 0, "max_lines": 2, "display": "sentence",
    }),
    ("box", "Nền mờ", "Khối nền tối sau chữ, dễ đọc trên nền rối", {
        "font_size": 22, "outline": 4, "shadow": 0, "bold": False,
        "color": "#FFFFFF", "box": "box", "box_color": "#000000",
        "box_opacity": 65, "line_words": 0, "max_lines": 2,
        "display": "sentence",
    }),
    ("tiktok", "Video dọc", "Chữ to, ít chữ mỗi hàng, nằm cao hơn mép dưới", {
        "font_size": 30, "outline": 3, "shadow": 0, "bold": True,
        "color": "#FFFFFF", "outline_color": "#000000", "box": "none",
        "line_words": 5, "max_lines": 2, "margin_v": 70,
        "display": "sentence",
    }),
    ("karaoke", "Cụm chữ theo lời", "Từng cụm ngắn sáng lên đúng nhịp đọc", {
        "font_size": 30, "outline": 3, "shadow": 0, "bold": True,
        "color": "#FFFFFF", "outline_color": "#000000", "box": "none",
        "margin_v": 70, "display": "karaoke", "words_per_cue": 3,
        "effect": "karaoke", "highlight_color": "#FFD54A",
    }),
    ("cinema", "Điện ảnh", "Chữ nhỏ, viền mảnh, sát mép dưới", {
        "font_size": 18, "outline": 1, "shadow": 1, "bold": False,
        "color": "#F2F2F2", "outline_color": "#000000", "box": "none",
        "line_words": 0, "max_lines": 2, "margin_v": 24,
        "display": "sentence",
    }),
    ("custom", "Tự chỉnh", "Bạn tự quyết mọi thông số bên dưới", {}),
)

_PRESET_MAP = {key: overrides for key, _label, _hint, overrides in PRESETS}

#: Danh sách (nhãn, khóa) cho ô chọn của giao diện.
PRESET_CHOICES: list[tuple[str, str]] = [
    (label, key) for key, label, _hint, _o in PRESETS
]

# Alignment của libass (theo bàn phím số): 2 = dưới-giữa, 5 = giữa, 8 = trên.
_POSITION_ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def preset_style(key: str) -> dict:
    """Kiểu đầy đủ của một bộ dựng sẵn."""
    return {**DEFAULT_STYLE, "preset": key, **_PRESET_MAP.get(key, {})}


def normalize_style(style: dict | None) -> dict:
    """Điền đủ mọi khóa còn thiếu của một kiểu phụ đề.

    Kiểu lưu trong dự án cũ chỉ có vài khóa; hàm này đắp phần còn lại từ bộ
    dựng sẵn tương ứng (nếu có) rồi tới giá trị mặc định, nên mọi nơi đọc
    kiểu đều thấy một dict hoàn chỉnh và không phải viết ``.get(..., mặc định)``.
    """
    style = dict(style or {})
    base = preset_style(str(style.get("preset", DEFAULT_STYLE["preset"])))
    base.update({k: v for k, v in style.items() if v is not None})
    return base


def blur_filter(width: int, height: int) -> str:
    """Bộ lọc boxblur có bán kính hợp lệ với kích thước vùng che.

    ffmpeg đòi bán kính nhỏ hơn nửa của MẶT PHẲNG đang làm mờ. Ở yuv420p hai
    mặt phẳng màu chỉ bằng một nửa độ phân giải, nên giới hạn thật là
    ``min(w, h) / 4`` — vùng 192x36 chỉ cho phép bán kính dưới 9. Vượt quá
    thì ffmpeg báo "Invalid chroma_param radius value".
    """
    limit = min(width, height) // 4
    radius = max(1, min(MAX_BLUR_RADIUS, limit - 1 if limit > 1 else 1))
    return f"boxblur={radius}:{BLUR_POWER}"


def hex_to_ass_color(hex_color: str, opacity: int = 100) -> str:
    """Đổi ``#RRGGBB`` sang màu ASS ``&HAABBGGRR&`` (thứ tự BGR).

    ``opacity`` tính theo phần trăm: 100 là đục hoàn toàn, 0 là trong suốt.
    Trong ASS thì kênh AA ngược lại — 00 mới là đục.
    """
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 255, 255, 255
    alpha = max(0, min(255, round((100 - max(0, min(100, opacity))) * 255 / 100)))
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


def safe_font_name(font: str) -> str:
    """Tên phông an toàn: bỏ ký tự phá cấu trúc chuỗi force_style/filtergraph."""
    return re.sub(r"[,'\"\\]", "", str(font or "")) or "Arial"


def escape_subtitles_path(path: str) -> str:
    """Thoát đường dẫn để dùng làm giá trị của bộ lọc ``subtitles=``.

    Ủy quyền cho :func:`autodub.utils.ffmpeg_escape_path` để dùng chung quy tắc
    thoát đường dẫn cho mọi bộ lọc FFmpeg.
    """
    from autodub.utils import ffmpeg_escape_path
    return ffmpeg_escape_path(path)



def build_force_style(style: dict | None = None) -> str:
    """Chuỗi ``force_style`` của libass cho phụ đề ghi vào hình.

    Theo đúng vị trí, phông, cỡ chữ, lề dọc, độ dày viền, đổ bóng, in đậm,
    màu chữ / màu viền và khối nền. Màu ASS là ``&HAABBGGRR&`` (thứ tự BGR).
    """
    s = normalize_style(style)
    align = _POSITION_ALIGN.get(str(s["position"]), 2)
    boxed = str(s["box"]) == "box"
    # BorderStyle 3 = khối nền đặc, vẽ bằng chính OutlineColour; lúc đó
    # Outline đóng vai trò khoảng đệm quanh chữ.
    border_style = 3 if boxed else 1
    outline_colour = (hex_to_ass_color(s["box_color"], int(s["box_opacity"]))
                      if boxed else hex_to_ass_color(s["outline_color"]))
    max_lines = int(s.get("max_lines", 2) or 2)
    wrap_style = 2 if max_lines == 1 else 0
    return (
        f"FontName={safe_font_name(s['font'])},"
        f"FontSize={int(s['font_size'])},"
        f"Bold={1 if s['bold'] else 0},"
        f"BorderStyle={border_style},"
        f"Outline={int(s['outline'])},"
        f"Shadow={int(s['shadow'])},"
        f"Alignment={align},"
        f"MarginV={int(s['margin_v'])},"
        f"MarginL=15,"
        f"MarginR=15,"
        f"WrapStyle={wrap_style},"
        f"PrimaryColour={hex_to_ass_color(s['color'])},"
        f"OutlineColour={outline_colour},"
        f"BackColour={hex_to_ass_color('#000000', 40)}"
    )


def _to_pixels(region: dict, video_w: int, video_h: int) -> tuple[int, int, int, int]:
    """Đổi một vùng chuẩn hóa thành số điểm ảnh chẵn, nằm gọn trong khung.

    Chiều rộng và cao chẵn để phép cắt còn hợp lệ với yuv420p.
    """
    x = int(round(float(region["x"]) * video_w))
    y = int(round(float(region["y"]) * video_h))
    w = int(round(float(region["w"]) * video_w))
    h = int(round(float(region["h"]) * video_h))

    x = max(0, min(x, video_w - 2))
    y = max(0, min(y, video_h - 2))
    w = max(2, min(w, video_w - x))
    h = max(2, min(h, video_h - y))
    return x, y, w - (w % 2), h - (h % 2)


def build_aspect_ratio_filter(
    aspect_preset: str | None,
    video_w: int,
    video_h: int,
    reframe_mode: str = "blur",
) -> tuple[str, int, int] | None:
    """Tạo filtergraph đổi tỷ lệ khung hình với các chế độ Reframe linh hoạt.

    Các chế độ:
    - 'blur': Nền làm mờ nghệ thuật + tối nhẹ và tăng bão hòa, video gốc ở giữa.
    - 'top_split': Video gốc ở nửa trên (căn top ~12%), nửa dưới thoáng cho phụ đề lớn.
    - 'center_crop': Phóng to vừa khít tỷ lệ đích và cắt chính giữa (Full canvas).

    Trả về (filter_str, target_w, target_h) hoặc None nếu giữ nguyên tỷ lệ gốc.
    """
    if not aspect_preset or aspect_preset in ("original", "none"):
        return None

    preset = aspect_preset.strip().lower()
    if preset in ("tiktok_9_16", "9:16", "vertical", "shorts"):
        target_ratio = 9.0 / 16.0
    elif preset in ("youtube_16_9", "16:9", "horizontal"):
        target_ratio = 16.0 / 9.0
    elif preset in ("square_1_1", "1:1", "square"):
        target_ratio = 1.0
    else:
        return None

    curr_ratio = float(video_w) / float(video_h)
    if abs(curr_ratio - target_ratio) < 0.02:
        return None

    if target_ratio < 1.0:  # 9:16
        th = video_h if video_h >= video_w else int(round(video_w / target_ratio))
        th = th + (th % 2)
        tw = int(round(th * target_ratio))
        tw = tw + (tw % 2)
    elif target_ratio > 1.0:  # 16:9
        tw = video_w if video_w >= video_h else int(round(video_h * target_ratio))
        tw = tw + (tw % 2)
        th = int(round(tw / target_ratio))
        th = th + (th % 2)
    else:  # 1:1
        dim = max(video_w, video_h)
        dim = dim + (dim % 2)
        tw = th = dim

    mode = (reframe_mode or "blur").strip().lower()

    if mode in ("center_crop", "crop", "fill"):
        # Phóng to vừa khít và cắt chính giữa
        flt = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}"
    elif mode in ("top_split", "top", "split"):
        # Video ở nửa trên (căn top ~12% chiều cao), nền mờ tối ở sau
        flt = (
            f"split[asp_bg][asp_fg];"
            f"[asp_bg]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=30:8,eq=brightness=-0.12:saturation=1.2[asp_bgb];"
            f"[asp_fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[asp_fg_s];"
            f"[asp_bgb][asp_fg_s]overlay=(W-w)/2:H*0.12"
        )
    else:  # 'blur' (default)
        # Nền mờ nghệ thuật cân đối ở giữa
        flt = (
            f"split[asp_bg][asp_fg];"
            f"[asp_bg]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=30:8,eq=brightness=-0.08:saturation=1.15[asp_bgb];"
            f"[asp_fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[asp_fg_s];"
            f"[asp_bgb][asp_fg_s]overlay=(W-w)/2:(H-h)/2"
        )

    return flt, tw, th


def _logo_overlay_coords(position: str, margin: int) -> tuple[str, str]:
    """Tính toán biểu thức tọa độ x, y cho bộ lọc overlay của logo."""
    pos = (position or "top_right").lower().strip()
    if pos in ("top_left", "tl"):
        return f"{margin}", f"{margin}"
    if pos in ("bottom_left", "bl"):
        return f"{margin}", f"main_h-overlay_h-{margin}"
    if pos in ("bottom_right", "br"):
        return f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"
    if pos in ("top_center", "tc"):
        return f"(main_w-overlay_w)/2", f"{margin}"
    if pos in ("bottom_center", "bc"):
        return f"(main_w-overlay_w)/2", f"main_h-overlay_h-{margin}"
    if pos in ("center", "middle"):
        return f"(main_w-overlay_w)/2", f"(main_h-overlay_h)/2"
    # Mặc định top_right
    return f"main_w-overlay_w-{margin}", f"{margin}"


def _build_drawtext_watermark_filter(
    text: str,
    opacity: float = 0.28,
    font_size: int = 26,
    color: str = "white",
    speed: int = 40,
    motion: str = "bounce",
) -> str:
    """Tạo bộ lọc drawtext cho chữ watermark chìm chuyển động quanh video."""
    from autodub.utils import bundled_font_files
    escaped_text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
    op = max(0.05, min(1.0, float(opacity if opacity is not None else 0.28)))
    fs = max(12, min(120, int(font_size if font_size is not None else 26)))
    sp_x = max(10, int(speed if speed is not None else 40))
    sp_y = max(8, int(sp_x * 0.72))
    margin = 24

    font_arg = ""
    font_files = bundled_font_files()
    if font_files:
        escaped_font = escape_subtitles_path(font_files[0])
        font_arg = f":fontfile='{escaped_font}'"

    clean_color = color.strip() if color else "white"
    if clean_color.startswith("#"):
        clean_color = clean_color[1:]

    font_color_arg = f"{clean_color}@{op:.2f}"

    if motion == "bounce":
        x_expr = f"{margin}+abs(mod(t*{sp_x},2*(w-tw-{2*margin}))-(w-tw-{2*margin}))"
        y_expr = f"{margin}+abs(mod(t*{sp_y},2*(h-th-{2*margin}))-(h-th-{2*margin}))"
    elif motion == "bottom_left":
        x_expr = f"{margin}"
        y_expr = f"h-th-{margin}"
    elif motion == "bottom_right":
        x_expr = f"w-tw-{margin}"
        y_expr = f"h-th-{margin}"
    elif motion == "top_left":
        x_expr = f"{margin}"
        y_expr = f"{margin}"
    else:  # top_right or static
        x_expr = f"w-tw-{margin}"
        y_expr = f"{margin}"

    return (f"drawtext=text='{escaped_text}'{font_arg}:fontsize={fs}"
            f":fontcolor={font_color_arg}:shadowcolor=black@{op*0.5:.2f}:shadowx=1:shadowy=1"
            f":x='{x_expr}':y='{y_expr}'")


def _build_color_filter(filter_name: str | None) -> str | None:
    """Tạo bộ lọc màu điện ảnh bằng FFmpeg."""
    if not filter_name or str(filter_name).lower().strip() in ("none", "original", ""):
        return None
    fn = str(filter_name).lower().strip()
    if fn in ("cinematic_warm", "warm"):
        return "colorbalance=rs=0.08:gs=0.02:bs=-0.06:rm=0.06:gm=0.02:bm=-0.04,eq=contrast=1.06:saturation=1.12"
    if fn in ("teal_orange", "blockbuster"):
        return "colorbalance=rs=0.12:gs=0.02:bs=-0.08:rh=-0.08:gh=0.04:bh=0.10,eq=contrast=1.10:saturation=1.15"
    if fn in ("vintage", "retro"):
        return "eq=contrast=0.96:brightness=0.02:saturation=0.86,colorbalance=rs=0.06:gs=0.03:bs=-0.04"
    if fn in ("moody_dark", "dark"):
        return "eq=contrast=1.14:brightness=-0.03:saturation=0.92,colorbalance=rs=-0.02:gs=-0.02:bs=0.04"
    if fn in ("clean_film", "sharp"):
        return "unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.04:saturation=1.08"
    return None


def build_filter_complex(
    blur_regions: list[dict] | None,
    video_w: int,
    video_h: int,
    srt_path: str | None = None,
    style: dict | None = None,
    aspect_preset: str | None = None,
    logo_path: str | None = None,
    logo_position: str = "top_right",
    logo_scale: float = 0.12,
    logo_opacity: float = 0.85,
    logo_margin: int = 24,
    logo_motion: str = "static",
    watermark_text: str | None = None,
    watermark_opacity: float = 0.28,
    watermark_font_size: int = 26,
    watermark_color: str = "white",
    watermark_speed: int = 40,
    watermark_motion: str = "bounce",
    smart_flip: bool = False,
    micro_zoom: bool = False,
    color_filter: str = "none",
    reframe_mode: str = "blur",
) -> str | None:
    """Dựng chuỗi ``-filter_complex``, hoặc None khi không cần lọc gì.

    Thứ tự áp dụng:
    1. Lật gương thông minh video gốc (smart_flip)
    2. Zoom động & trượt camera vi mô (micro_zoom)
    3. Bộ lọc màu điện ảnh (color_filter)
    4. Chuyển đổi tỷ lệ khung hình (aspect_preset) với reframe_mode
    5. Che/làm mờ các vùng phụ đề cũ (blur_regions)
    6. Chèn logo thương hiệu (logo_path)
    7. Chèn watermark chìm chuyển động (watermark_text)
    8. Ghi đè phụ đề mới (subtitles=...)
    """
    regions = list(blur_regions or [])
    asp_res = build_aspect_ratio_filter(aspect_preset, video_w, video_h, reframe_mode=reframe_mode)
    has_logo = bool(logo_path and str(logo_path).strip())
    has_wm = bool(watermark_text and str(watermark_text).strip())
    c_flt = _build_color_filter(color_filter)

    if (not regions and not srt_path and not asp_res and not has_logo
            and not has_wm and not smart_flip and not micro_zoom and not c_flt):
        return None

    parts: list[str] = []
    current = "0:v"

    # 1. Lật gương thông minh (chỉ lật hình ảnh nền, không lật chữ phụ đề/logo)
    if smart_flip:
        parts.append(f"[{current}]hflip[vflip]")
        current = "vflip"

    # 2. Phóng to nhẹ 103% và trượt camera vi mô
    if micro_zoom:
        parts.append(f"[{current}]scale=1.03*iw:1.03*ih,crop=iw/1.03:ih/1.03:(iw-ow)/2+sin(t*0.6)*6:(ih-oh)/2+cos(t*0.5)*6[vzoom]")
        current = "vzoom"

    # 3. Bộ lọc màu điện ảnh
    if c_flt:
        parts.append(f"[{current}]{c_flt}[vcolor]")
        current = "vcolor"

    # 4. Chuyển đổi tỷ lệ khung hình
    if asp_res:
        asp_flt, video_w, video_h = asp_res
        parts.append(f"[{current}]{asp_flt}[vasp]")
        current = "vasp"

    for i, region in enumerate(regions):
        x, y, w, h = _to_pixels(region, video_w, video_h)
        base, blurred = f"b{i}", f"bl{i}"
        nxt = f"v{i + 1}"

        # Tách luồng để cùng một khung vừa làm nền dán vừa làm nguồn cắt.
        parts.append(f"[{current}]split[{base}][{base}c]")
        parts.append(
            f"[{base}c]crop={w}:{h}:{x}:{y},{blur_filter(w, h)}[{blurred}]"
        )

        overlay = f"overlay={x}:{y}"
        t_start, t_end = region.get("t_start"), region.get("t_end")
        if t_start is not None and t_end is not None:
            overlay += f":enable='between(t,{float(t_start)},{float(t_end)})'"
        parts.append(f"[{base}][{blurred}]{overlay}[{nxt}]")
        current = nxt

    if has_logo:
        clean_logo = str(logo_path).strip()
        escaped_logo = escape_subtitles_path(clean_logo)
        target_w = max(16, int(video_w * float(logo_scale or 0.12)))
        if target_w % 2 != 0:
            target_w += 1
        opacity = max(0.05, min(1.0, float(logo_opacity if logo_opacity is not None else 0.85)))
        margin = int(logo_margin if logo_margin is not None else 24)

        if logo_motion == "bounce":
            sp_x = max(10, int(watermark_speed or 40))
            sp_y = max(8, int(sp_x * 0.72))
            ox = f"{margin}+abs(mod(t*{sp_x},2*(main_w-overlay_w-{2*margin}))-(main_w-overlay_w-{2*margin}))"
            oy = f"{margin}+abs(mod(t*{sp_y},2*(main_h-overlay_h-{2*margin}))-(main_h-overlay_h-{2*margin}))"
        else:
            ox, oy = _logo_overlay_coords(logo_position or "top_right", margin)

        parts.append(f"movie='{escaped_logo}',scale={target_w}:-1,format=rgba,colorchannelmixer=aa={opacity:.2f}[logo]")
        parts.append(f"[{current}][logo]overlay={ox}:{oy}[vlogo]")
        current = "vlogo"

    if has_wm:
        wm_flt = _build_drawtext_watermark_filter(
            str(watermark_text).strip(),
            opacity=watermark_opacity,
            font_size=watermark_font_size,
            color=watermark_color,
            speed=watermark_speed,
            motion=watermark_motion,
        )
        parts.append(f"[{current}]{wm_flt}[vwm]")
        current = "vwm"

    if srt_path:
        # Tệp .ass đã mang sẵn kiểu chữ và hiệu ứng của từng dòng bên trong —
        # force_style sẽ đè mất, nên chỉ áp cho tệp .srt.
        subs = f"subtitles='{escape_subtitles_path(srt_path)}'"
        # Phông đi kèm ứng dụng (<app>/fonts): libass tra thư mục này TRƯỚC
        # phông hệ thống, nên phông người dùng thả vào fonts/ hiện đúng trên
        # mọi máy mà không cần cài vào Windows.
        from autodub.utils import bundled_font_files, fonts_dir
        if bundled_font_files():
            subs += f":fontsdir='{escape_subtitles_path(fonts_dir())}'"
        if not srt_path.lower().endswith(".ass"):
            subs += f":force_style='{build_force_style(style)}'"
        parts.append(f"[{current}]{subs}[vout]")
    else:
        # Không còn gì để vẽ — đặt tên đầu ra cho bước cuối cùng.
        parts.append(f"[{current}]null[vout]")

    return ";".join(parts)

