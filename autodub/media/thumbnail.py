"""Tự động xuất ảnh bìa / Thumbnail bắt mắt, thu hút lượt xem (High CTR Thumbnail).

Module này trích xuất khung hình tốt nhất từ video và thiết kế tự động ảnh bìa
với tiêu đề tiếng Việt nổi bật, viền tương phản cao và hiệu ứng ánh sáng chuẩn
phong cách YouTube / TikTok / Facebook Reels.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from autodub.utils import bundled_font_files, setup_logging

logger = setup_logging("autodub.thumbnail")


def _get_best_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font chữ Việt hóa từ thư mục fonts/ hoặc fallback sang default."""
    font_files = bundled_font_files()
    for f in font_files:
        if f.lower().endswith((".ttf", ".otf")):
            try:
                return ImageFont.truetype(f, size=size)
            except Exception:
                continue
    # Thử các font hệ thống phổ biến trên Windows
    for win_font in ("Arial.ttf", "arialbd.ttf", "calibri.ttf", "tahoma.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(win_font, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def extract_best_frame(video_path: str, output_png: str, duration_sec: float | None = None) -> str:
    """Trích xuất khung hình đắt giá nhất từ video."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Lấy mốc thời gian khoảng 25% - 35% thời lượng
    target_time = 2.0
    if duration_sec and duration_sec > 4.0:
        target_time = min(duration_sec * 0.3, 30.0)

    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", str(round(target_time, 2)),
        "-i", video_path,
        "-frames:v", "1",
        "-y", output_png,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and os.path.exists(output_png) and os.path.getsize(output_png) > 1000:
            return output_png
    except Exception as e:
        logger.warning(f"Lỗi extract frame tại {target_time}s: {e}")

    # Fallback trích xuất frame tại giây 0
    cmd_fallback = [
        "ffmpeg", "-v", "error",
        "-ss", "0.5",
        "-i", video_path,
        "-frames:v", "1",
        "-y", output_png,
    ]
    subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=20)
    return output_png


def render_thumbnail(
    frame_path: str,
    title: str,
    output_path: str,
    width: int = 1280,
    height: int = 720,
    badge_text: str = "",
) -> str:
    """Thiết kế và render đồ họa ảnh bìa High-CTR hoàn chỉnh."""
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 500:
        with Image.open(frame_path) as im:
            base_img = im.convert("RGB")
    else:
        # Nền placeholder gradient tối nếu không có frame
        base_img = Image.new("RGB", (width, height), color=(20, 20, 35))

    # Resize & Crop to cover exact (width, height)
    img_ratio = base_img.width / base_img.height
    target_ratio = width / height

    if img_ratio > target_ratio:
        # Ảnh gốc bè hơn -> scale theo chiều cao rồi crop 2 bên
        new_h = height
        new_w = int(base_img.width * (height / base_img.height))
    else:
        # Ảnh gốc dọc hơn -> scale theo chiều rộng rồi crop trên dưới
        new_w = width
        new_h = int(base_img.height * (width / base_img.width))

    scaled = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    canvas = scaled.crop((left, top, left + width, top + height))

    # Tạo lớp phủ Gradient mờ ở nửa dưới để chữ nổi bật
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    grad_start = int(height * 0.45)
    for y in range(grad_start, height):
        alpha = int(220 * ((y - grad_start) / (height - grad_start)) ** 1.5)
        overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    # Gradient nhẹ ở đỉnh cho badge
    top_grad_end = int(height * 0.25)
    for y in range(top_grad_end):
        alpha = int(120 * (1.0 - (y / top_grad_end)))
        overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    # 1. Vẽ Badge tag ở góc trên bên trái (nếu có)
    if badge_text.strip():
        badge_str = badge_text.strip().upper()
        badge_font = _get_best_font(size=max(20, int(height * 0.045)))
        b_bbox = draw.textbbox((0, 0), badge_str, font=badge_font)
        bw = b_bbox[2] - b_bbox[0] + 32
        bh = b_bbox[3] - b_bbox[1] + 16
        bx, by = int(width * 0.05), int(height * 0.06)

        # Vẽ nền badge đỏ cam rực rỡ
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=(230, 40, 40, 240), outline=(255, 255, 255, 200), width=2)
        draw.text((bx + 16, by + 6), badge_str, fill=(255, 255, 255), font=badge_font)

    # 2. Xử lý tiêu đề giật tít tiếng Việt
    clean_title = title.strip()
    if not clean_title:
        clean_title = "VIDEO MỚI NHẤT"

    # Tính kích thước font phù hợp
    font_size = max(32, int(height * 0.095))
    font = _get_best_font(size=font_size)

    # Tự động chia dòng hợp lý (tối đa 2 dòng lớn)
    chars_per_line = max(14, int(width / (font_size * 0.75)))
    lines = textwrap.wrap(clean_title, width=chars_per_line)[:2]

    # Tính toán vị trí đặt chữ ở 1/3 dưới khung hình
    line_spacing = int(font_size * 0.25)
    total_text_h = len(lines) * font_size + (len(lines) - 1) * line_spacing
    start_y = height - total_text_h - int(height * 0.08)

    # Màu sắc nổi bật (Dòng 1 trắng, dòng 2 vàng sáng rực rỡ)
    line_colors = [(255, 255, 255), (255, 213, 74)]

    stroke_width = max(4, int(font_size * 0.09))

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        lx = (width - lw) // 2  # Căn giữa
        ly = start_y + idx * (font_size + line_spacing)

        # Drop shadow đen đậm
        shadow_offset = max(4, int(font_size * 0.07))
        draw.text((lx + shadow_offset, ly + shadow_offset), line, font=font, fill=(0, 0, 0, 220), stroke_width=stroke_width + 2, stroke_fill=(0, 0, 0, 255))

        # Viền đen dày & chữ rực rỡ
        col = line_colors[min(idx, len(line_colors) - 1)]
        draw.text((lx, ly), line, font=font, fill=col, stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))

    # Lưu ảnh kết quả chất lượng cao
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    logger.info(f"Đã xuất Thumbnail High-CTR: {output_path}")
    return output_path


def generate_high_ctr_thumbnail(
    video_path: str,
    title: str,
    output_path: str,
    aspect: str = "16:9",
    badge_text: str = "",
    duration_sec: float | None = None,
) -> str:
    """Hàm tiện ích trích xuất frame từ video và sinh Thumbnail hoàn chỉnh."""
    temp_dir = os.path.dirname(os.path.abspath(output_path))
    temp_frame = os.path.join(temp_dir, "temp_thumb_frame.png")

    try:
        extract_best_frame(video_path, temp_frame, duration_sec=duration_sec)
    except Exception as e:
        logger.warning(f"Không thể trích xuất frame từ video: {e}")

    if aspect in ("9:16", "portrait", "vertical", "tiktok", "shorts"):
        w, h = 720, 1280
    else:
        w, h = 1280, 720

    res = render_thumbnail(
        frame_path=temp_frame,
        title=title,
        output_path=output_path,
        width=w,
        height=h,
        badge_text=badge_text,
    )

    if os.path.exists(temp_frame):
        try:
            os.remove(temp_frame)
        except OSError:
            pass

    return res
