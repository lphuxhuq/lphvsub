"""Tự động xuất ảnh bìa / Thumbnail bắt mắt, thu hút lượt xem (High CTR Thumbnail).

Module này trích xuất khung hình tốt nhất từ video và thiết kế tự động ảnh bìa
với tiêu đề tiếng Việt nổi bật, viền tương phản cao, lớp phủ glassmorphism và
hiệu ứng ánh sáng chuẩn phong cách YouTube / TikTok / Facebook Reels (Agency Tier).
"""
from __future__ import annotations

import os
import re
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from autodub.utils import bundled_font_files, setup_logging

logger = setup_logging("autodub.thumbnail")


def _get_best_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font chữ Việt hóa chất lượng cao, ưu tiên font dày dặn, hỗ trợ 100% tiếng Việt."""
    priority_names = [
        "BarlowCondensed-Bold.ttf",
        "FrancoisOne-Regular.ttf",
        "BarlowCondensed-Medium.ttf",
        "Coiny-Regular.ttf",
        "Bangers-Regular.ttf",
        "Merienda-Bold.ttf",
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

    # Điểm cao cho khung hình tương phản cao, màu sắc rực rỡ và ánh sáng cân bằng
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
                        try:
                            os.remove(best_candidate_file)
                        except OSError:
                            pass
                    best_candidate_file = cand_file
                else:
                    try:
                        os.remove(cand_file)
                    except OSError:
                        pass
            else:
                if os.path.exists(cand_file):
                    try:
                        os.remove(cand_file)
                    except OSError:
                        pass
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


def _create_vignette_mask(width: int, height: int) -> Image.Image:
    """Tạo mặt nạ Vignette làm tối 4 góc nhẹ để kéo tập trung vào trung tâm."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    # Vẽ các hình ellipse đồng tâm mờ dần từ ngoài vào
    cx, cy = width // 2, height // 2
    max_r = int(((width / 2) ** 2 + (height / 2) ** 2) ** 0.5)
    for r in range(max_r, int(max_r * 0.4), -10):
        factor = (r - max_r * 0.4) / (max_r * 0.6)
        alpha = int(140 * factor ** 1.5)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
    return mask.filter(ImageFilter.GaussianBlur(30))


def render_thumbnail(
    frame_path: str,
    title: str,
    output_path: str,
    width: int = 1280,
    height: int = 720,
    badge_text: str = "",
) -> str:
    """Thiết kế và render đồ họa ảnh bìa High-CTR đẳng cấp Agency (YouTube / TikTok Pro)."""
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 500:
        with Image.open(frame_path) as im:
            base_img = im.convert("RGB")
    else:
        # Nền placeholder gradient tối nếu không có frame
        base_img = Image.new("RGB", (width, height), color=(15, 15, 28))

    # Nâng cấp chất lượng ảnh nền: tăng độ rực rỡ màu sắc, độ tương phản và độ nét
    base_img = ImageEnhance.Color(base_img).enhance(1.22)
    base_img = ImageEnhance.Contrast(base_img).enhance(1.15)
    base_img = ImageEnhance.Sharpness(base_img).enhance(1.25)

    # Resize & Crop theo tỷ lệ chuẩn
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
    canvas = scaled.crop((left, top, left + width, top + height)).convert("RGBA")

    # Lớp phủ Vignette làm tối viền xung quanh
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vignette_mask = _create_vignette_mask(width, height)
    vignette.paste((0, 0, 0, 200), (0, 0), vignette_mask)
    canvas = Image.alpha_composite(canvas, vignette)

    # Lớp phủ Gradient ở nửa dưới/trên để chữ nổi bật
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    is_vertical = height > width

    if is_vertical:
        # Tệp dọc (9:16 Shorts/Reels): Gradient từ 2 đầu dồn vào giữa
        grad_top = int(height * 0.30)
        for y in range(grad_top):
            alpha = int(180 * (1.0 - (y / grad_top)))
            overlay_draw.line([(0, y), (width, y)], fill=(5, 5, 12, alpha))
        grad_bot = int(height * 0.65)
        for y in range(grad_bot, height):
            alpha = int(220 * ((y - grad_bot) / (height - grad_bot)) ** 1.3)
            overlay_draw.line([(0, y), (width, y)], fill=(5, 5, 12, alpha))
    else:
        # Tệp ngang (16:9): Gradient nhẹ ở đỉnh & đậm ở nửa dưới
        grad_start = int(height * 0.40)
        for y in range(grad_start, height):
            alpha = int(225 * ((y - grad_start) / (height - grad_start)) ** 1.3)
            overlay_draw.line([(0, y), (width, y)], fill=(5, 5, 12, alpha))
        top_end = int(height * 0.22)
        for y in range(top_end):
            alpha = int(110 * (1.0 - (y / top_end)))
            overlay_draw.line([(0, y), (width, y)], fill=(5, 5, 12, alpha))

    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    # 1. Vẽ Eyebrow Badge Tag ở góc trên
    badge = badge_text.strip() if badge_text else "SIÊU PHẨM"
    badge_str = badge.strip().upper()
    badge_font_size = max(18, int(height * 0.038))
    badge_font = _get_best_font(size=badge_font_size)

    b_bbox = draw.textbbox((0, 0), badge_str, font=badge_font)
    bw = b_bbox[2] - b_bbox[0] + 28
    bh = b_bbox[3] - b_bbox[1] + 14
    bx = int(width * 0.05)
    by = int(height * 0.05 if not is_vertical else height * 0.08)

    # Vẽ nút Badge kiêu đỏ cam nổi bật với viền hairline trắng sáng
    draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=10,
        fill=(225, 29, 72, 240),      # Crimson Red Accent
        outline=(255, 255, 255, 220), # Hairline border
        width=2,
    )
    draw.text((bx + 14, by + 5), badge_str, fill=(255, 255, 255), font=badge_font)

    # 2. Xử lý Tiêu đề (Loại bỏ ký tự rác, tiếng Trung, đuôi file)
    clean_title = re.sub(r"[\u4e00-\u9fff]+", "", str(title or "")).strip()
    clean_title = re.sub(r"\.(mp4|mkv|avi|mov|flv|wmv|srt)$", "", clean_title, flags=re.I).strip()
    clean_title = re.sub(r"[\_\-]+", " ", clean_title)
    clean_title = re.sub(r"\s+", " ", clean_title)

    if not clean_title or len(clean_title) < 3:
        clean_title = "SIÊU PHẨM MỚI NHẤT"

    # Tính toán Font Size phù hợp với tỷ lệ ảnh
    font_size = max(32, int(height * (0.075 if is_vertical else 0.088)))
    font = _get_best_font(size=font_size)

    # Tự động ngắt dòng thông minh (Tối đa 2-3 dòng)
    chars_per_line = max(12, int(width / (font_size * 0.68)))
    lines = textwrap.wrap(clean_title, width=chars_per_line)[:3]

    # Tính toán kích thước khối chữ
    line_spacing = int(font_size * 0.20)
    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    max_line_w = max(b[2] - b[0] for b in line_bboxes)
    total_text_h = len(lines) * font_size + (len(lines) - 1) * line_spacing

    # Vị trí khối chữ
    if is_vertical:
        # Tệp 9:16: Đặt ở giữa khối 55% - 75% chiều cao (tránh các nút của TikTok/Reels ở cạnh phải/dưới)
        start_y = int(height * 0.58) - (total_text_h // 2)
    else:
        # Tệp 16:9: Đặt ở 1/3 dưới
        start_y = height - total_text_h - int(height * 0.08)

    # 3. Vẽ Thẻ Thủy Tinh Tối (Dark Translucent Glass Card Banner) phía sau Tiêu đề
    pad_h = int(width * 0.035)
    pad_v = int(height * 0.022)

    card_left = max(int(width * 0.04), (width - max_line_w) // 2 - pad_h)
    card_right = min(width - int(width * 0.04), (width + max_line_w) // 2 + pad_h)
    card_top = start_y - pad_v
    card_bottom = start_y + total_text_h + pad_v

    # Vẽ nền Glass Panel chìm với viền mờ cao cấp
    card_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_layer)
    card_draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=16,
        fill=(12, 12, 24, 215),          # Dark Glass Vantablack Tint
        outline=(99, 102, 241, 160),      # Hairline Indigo Glow Ring
        width=2,
    )
    canvas = Image.alpha_composite(canvas, card_layer)
    draw = ImageDraw.Draw(canvas)

    # 4. Vẽ Chữ Tiêu đề Đa Tầng 3D Nổi Bật (Multi-layer 3D Text)
    # Phối màu từng dòng: Dòng 1 (Trắng), Dòng 2 (Vàng Nghệ Rực Rỡ), Dòng 3 (Cyan/Red Accent)
    line_colors = [
        (255, 255, 255),  # Dòng 1: White Snow
        (250, 204, 21),   # Dòng 2: Electric Yellow (#FACC15)
        (56, 189, 248),   # Dòng 3: Electric Cyan (#38BDF8)
    ]
    stroke_w = max(3, int(font_size * 0.08))

    for idx, line in enumerate(lines):
        bbox = line_bboxes[idx]
        lw = bbox[2] - bbox[0]
        lx = (width - lw) // 2  # Căn giữa dòng chữ trong banner
        ly = start_y + idx * (font_size + line_spacing)

        # Lớp bóng đổ mờ (Drop Shadow 3D)
        shadow_dist = max(3, int(font_size * 0.06))
        draw.text(
            (lx + shadow_dist, ly + shadow_dist),
            line,
            font=font,
            fill=(0, 0, 0, 230),
            stroke_width=stroke_w + 2,
            stroke_fill=(0, 0, 0, 255),
        )

        # Lớp viền nét đen dày và màu chữ nổi bật
        col = line_colors[min(idx, len(line_colors) - 1)]
        draw.text(
            (lx, ly),
            line,
            font=font,
            fill=col,
            stroke_width=stroke_w,
            stroke_fill=(0, 0, 0, 255),
        )

    # Export ảnh kết quả chất lượng cao (JPEG 95)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    logger.info(f"Đã xuất Thumbnail High-CTR (Agency Tier): {output_path}")
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
