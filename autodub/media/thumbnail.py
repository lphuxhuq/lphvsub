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
    """Nạp font chữ Việt hóa chất lượng cao, ưu tiên font dày dặn, hỗ trợ 100% tiếng Việt."""
    priority_names = [
        "BarlowCondensed-Bold.ttf",
        "FrancoisOne-Regular.ttf",
        "BarlowCondensed-Medium.ttf",
        "Coiny-Regular.ttf",
        "Merriweather-VariableFont_opsz,wdth,wght.ttf",
        "arialbd.ttf",
        "segoeuib.ttf",
        "calibrib.ttf",
        "tahomabd.ttf",
        "Arial.ttf",
        "segoeui.ttf",
    ]
    font_files = bundled_font_files()
    file_map = {os.path.basename(f).lower(): f for f in font_files}

    for name in priority_names:
        key = name.lower()
        if key in file_map:
            try:
                return ImageFont.truetype(file_map[key], size=size)
            except Exception:
                continue

    # Thử font hệ thống Windows
    win_dir = os.environ.get("WINDIR", "C:\\Windows")
    for name in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "tahomabd.ttf", "Arial.ttf"):
        win_path = os.path.join(win_dir, "Fonts", name)
        if os.path.isfile(win_path):
            try:
                return ImageFont.truetype(win_path, size=size)
            except Exception:
                continue

    for f in font_files:
        try:
            return ImageFont.truetype(f, size=size)
        except Exception:
            continue

    return ImageFont.load_default()


def _score_candidate_frame(img: Image.Image) -> float:
    """Đánh giá chất lượng thị giác của khung hình (độ sáng, tương phản, độ rực màu)."""
    from PIL import ImageStat

    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    mean_lum = stat.mean[0]
    std_lum = stat.stddev[0]

    # Loại bỏ frame đen hoàn toàn hoặc cháy sáng
    if mean_lum < 28 or mean_lum > 238:
        return -100.0

    hsv = img.convert("HSV")
    sat = ImageStat.Stat(hsv).mean[1]

    # Điểm cao cho khung hình có độ tương phản cao (chi tiết rõ nét), màu sắc rực rỡ và ánh sáng cân bằng
    lum_balance = 1.0 - abs(mean_lum - 128.0) / 128.0
    return std_lum * 2.0 + sat * 1.2 + lum_balance * 30.0


def extract_best_frame(video_path: str, output_png: str, duration_sec: float | None = None) -> str:
    """Trích xuất khung hình đắt giá nhất từ video thông qua chấm điểm đa điểm ảnh (Multi-Candidate Scoring)."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    # 1. Xác định thời lượng video
    dur = float(duration_sec or 0.0)
    if dur <= 0:
        cmd_dur = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            res_dur = subprocess.run(cmd_dur, capture_output=True, text=True, timeout=10)
            if res_dur.returncode == 0 and res_dur.stdout.strip():
                dur = float(res_dur.stdout.strip())
        except Exception:
            dur = 30.0

    # 2. Tạo danh sách các mốc thời gian ứng viên phân bố hợp lý trên toàn video
    if dur <= 5.0:
        candidates = [round(dur * 0.3, 2), round(dur * 0.6, 2)]
    else:
        # Lấy 6 mốc thời gian từ 15% đến 85% thời lượng video
        ratios = [0.15, 0.28, 0.42, 0.55, 0.70, 0.85]
        candidates = [round(max(0.5, min(dur - 0.5, r * dur)), 2) for r in ratios]

    temp_dir = os.path.dirname(os.path.abspath(output_png))
    best_score = -999.0
    best_candidate_file = None

    for idx, t_stamp in enumerate(candidates):
        cand_file = os.path.join(temp_dir, f"cand_frame_{idx}.jpg")
        cmd = [
            "ffmpeg", "-v", "error",
            "-ss", str(t_stamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            "-y", cand_file,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and os.path.exists(cand_file) and os.path.getsize(cand_file) > 1000:
                with Image.open(cand_file) as im:
                    im_rgb = im.convert("RGB")
                    score = _score_candidate_frame(im_rgb)
                if score > best_score:
                    best_score = score
                    if best_candidate_file and os.path.exists(best_candidate_file):
                        try: os.remove(best_candidate_file)
                        except OSError: pass
                    best_candidate_file = cand_file
                else:
                    try: os.remove(cand_file)
                    except OSError: pass
            else:
                if os.path.exists(cand_file):
                    try: os.remove(cand_file)
                    except OSError: pass
        except Exception:
            pass

    if best_candidate_file and os.path.exists(best_candidate_file):
        os.replace(best_candidate_file, output_png)
        logger.info(f"Đã chọn khung hình đẹp nhất (Score: {best_score:.1f})")
        return output_png

    # Fallback trích xuất frame tại giây 1.5 nếu tất cả ứng viên lỗi
    cmd_fallback = [
        "ffmpeg", "-v", "error",
        "-ss", "1.5",
        "-i", video_path,
        "-frames:v", "1",
        "-y", output_png,
    ]
    subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=15)
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
    import re
    from PIL import ImageEnhance

    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 500:
        with Image.open(frame_path) as im:
            base_img = im.convert("RGB")
    else:
        # Nền placeholder gradient tối nếu không có frame
        base_img = Image.new("RGB", (width, height), color=(20, 20, 35))

    # Nâng cấp chất lượng ảnh nền: tăng màu sắc, độ tương phản và độ sắc nét
    base_img = ImageEnhance.Color(base_img).enhance(1.15)
    base_img = ImageEnhance.Contrast(base_img).enhance(1.12)
    base_img = ImageEnhance.Sharpness(base_img).enhance(1.20)

    # Resize & Crop to cover exact (width, height)
    img_ratio = base_img.width / base_img.height
    target_ratio = width / height

    if img_ratio > target_ratio:
        new_h = height
        new_w = int(base_img.width * (height / base_img.height))
    else:
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
        alpha = int(230 * ((y - grad_start) / (height - grad_start)) ** 1.4)
        overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    # Gradient nhẹ ở đỉnh cho badge
    top_grad_end = int(height * 0.25)
    for y in range(top_grad_end):
        alpha = int(120 * (1.0 - (y / top_grad_end)))
        overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    # 1. Vẽ Badge tag ở góc trên bên trái (nếu có)
    badge = badge_text.strip() if badge_text else "SIÊU PHẨM"
    badge_str = badge.strip().upper()
    badge_font = _get_best_font(size=max(18, int(height * 0.042)))
    b_bbox = draw.textbbox((0, 0), badge_str, font=badge_font)
    bw = b_bbox[2] - b_bbox[0] + 32
    bh = b_bbox[3] - b_bbox[1] + 16
    bx, by = int(width * 0.05), int(height * 0.06)

    # Vẽ nền badge đỏ cam rực rỡ
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=(230, 40, 40, 240), outline=(255, 255, 255, 200), width=2)
    draw.text((bx + 16, by + 6), badge_str, fill=(255, 255, 255), font=badge_font)

    # 2. Xử lý tiêu đề giật tít tiếng Việt (loại bỏ sạch tiếng Trung)
    clean_title = re.sub(r"[\u4e00-\u9fff]+", "", str(title or "")).strip()
    clean_title = re.sub(r"\s+", " ", clean_title)
    if not clean_title or len(clean_title) < 4:
        clean_title = "SIÊU PHẨM MỚI NHẤT"

    # Tính kích thước font phù hợp
    font_size = max(34, int(height * 0.096))
    font = _get_best_font(size=font_size)

    # Tự động chia dòng hợp lý (tối đa 2 dòng lớn)
    chars_per_line = max(13, int(width / (font_size * 0.72)))
    lines = textwrap.wrap(clean_title, width=chars_per_line)[:2]

    # Tính toán vị trí đặt chữ ở 1/3 dưới khung hình
    line_spacing = int(font_size * 0.22)
    total_text_h = len(lines) * font_size + (len(lines) - 1) * line_spacing
    start_y = height - total_text_h - int(height * 0.07)

    # Màu sắc nổi bật (Dòng 1 trắng tuyết, dòng 2 vàng nghệ rực rỡ)
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
