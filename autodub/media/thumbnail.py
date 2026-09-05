"""Bộ máy đồ họa & sinh Thumbnail High-CTR đẳng cấp Agency (Headless 100%).

Chuyên dụng cho phong cách YouTube Review Phim / Manhwa Cổ Đại & Quân Sư:
- Chữ 3D nổi khối đa tầng (Isometric Extrusion).
- Viền kép tương phản cao (Double Stroke: viền trong sáng + viền ngoài đen dày).
- Hiệu ứng phát quang mờ Neon Outer Glow rực rỡ.
- Thuật toán Frame Analyzer chấm điểm nét, rực màu, cân bằng sáng và bố cục thực tế.
- 3 Style Presets thực tế: Cổ Đại Làm Giàu, Quân Sư Hiện Đại, Chiến Thần Rực Lửa.
- Hỗ trợ tỷ lệ 16:9 (YouTube) và 9:16 (Shorts/TikTok/Reels).

QUY TẮC BẤT BIẾN:
100% Headless. Tuyệt đối không import PyQt, PySide hoặc bất kỳ thư viện GUI nào.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import re
import subprocess
import textwrap
from typing import Sequence
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

from autodub.utils import bundled_font_files, setup_logging

logger = setup_logging("autodub.thumbnail")


# ==============================================================================
# DATA MODELS & PRESETS
# ==============================================================================

@dataclass
class StylePresetConfig:
    """Cấu hình phong cách đồ họa cho Thumbnail."""
    name: str
    label: str
    # Dòng trên (Eyebrow / Header)
    top_text_color: tuple[int, int, int]
    top_stroke_inner: tuple[int, int, int] | None
    top_stroke_outer: tuple[int, int, int]
    top_glow_color: tuple[int, int, int, int] | None
    top_font_priority: list[str]
    # Dòng dưới (Main Hook / Punchline)
    bottom_gradient: list[tuple[int, int, int]]
    bottom_stroke_inner: tuple[int, int, int] | None
    bottom_stroke_outer: tuple[int, int, int]
    bottom_glow_color: tuple[int, int, int, int] | None
    bottom_3d_depth: int
    bottom_3d_color: tuple[int, int, int]
    bottom_font_priority: list[str]
    # Huy hiệu (Badge)
    badge_bg: tuple[int, int, int]
    badge_text: tuple[int, int, int]
    badge_border: tuple[int, int, int]
    # Hiệu ứng môi trường
    vignette_intensity: float = 0.35


PRESETS: dict[str, StylePresetConfig] = {
    "co_dai": StylePresetConfig(
        name="co_dai",
        label="Cổ Đại Làm Giàu",
        top_text_color=(255, 220, 40),          # Vàng hoàng kim
        top_stroke_inner=(185, 45, 15),         # Đỏ nâu tương phản
        top_stroke_outer=(5, 5, 8),             # Viền ngoài đen tuyền
        top_glow_color=(255, 180, 0, 190),      # Hào quang vàng cam
        top_font_priority=[
            "Merienda-Bold.ttf",
            "StoryScript-Regular.ttf",
            "Coiny-Regular.ttf",
            "BarlowCondensed-Bold.ttf",
        ],
        bottom_gradient=[
            (255, 255, 140),                    # Đỉnh: Vàng sáng chanh
            (255, 210, 0),                      # Giữa: Vàng nghệ rực rỡ
            (255, 140, 0),                      # Đáy: Vàng cam ấm
        ],
        bottom_stroke_inner=(255, 255, 255),    # Viền trong trắng sáng
        bottom_stroke_outer=(0, 0, 0),          # Viền ngoài đen đậm dày
        bottom_glow_color=(255, 190, 0, 160),   # Ánh sáng tỏa vàng gold
        bottom_3d_depth=10,
        bottom_3d_color=(15, 8, 2),             # Khối 3D đổ bóng sâu
        bottom_font_priority=[
            "BarlowCondensed-Bold.ttf",
            "Bangers-Regular.ttf",
            "FrancoisOne-Regular.ttf",
        ],
        badge_bg=(255, 215, 0),                 # Huy hiệu vàng rực
        badge_text=(0, 0, 0),                   # Chữ đen đanh thép
        badge_border=(0, 0, 0),
        vignette_intensity=0.38,
    ),
    "quan_su": StylePresetConfig(
        name="quan_su",
        label="Quân Sư Hiện Đại",
        top_text_color=(255, 255, 255),         # Trắng tuyết tinh khiết
        top_stroke_inner=None,
        top_stroke_outer=(20, 5, 35),           # Đen tím huyền ảo
        top_glow_color=(236, 72, 153, 230),     # Neon Tím Hồng / Magenta Glow cực mạnh
        top_font_priority=[
            "BarlowCondensed-Bold.ttf",
            "FrancoisOne-Regular.ttf",
            "Coiny-Regular.ttf",
        ],
        bottom_gradient=[
            (255, 255, 255),                    # Trắng pha vàng chanh
            (255, 245, 10),                     # Vàng điện quang cực sáng
            (250, 204, 21),                     # Vàng rực
        ],
        bottom_stroke_inner=(255, 255, 255),    # Viền trong trắng sắc nét
        bottom_stroke_outer=(0, 0, 0),          # Viền đen 3D đanh thép
        bottom_glow_color=(192, 38, 211, 170),  # Tỏa neon violet / purple
        bottom_3d_depth=10,
        bottom_3d_color=(12, 10, 25),           # Khối 3D xanh đêm
        bottom_font_priority=[
            "BarlowCondensed-Bold.ttf",
            "FrancoisOne-Regular.ttf",
            "Bangers-Regular.ttf",
        ],
        badge_bg=(15, 23, 42),                  # Huy hiệu nền đêm sâu
        badge_text=(255, 255, 255),             # Chữ trắng
        badge_border=(236, 72, 153),            # Viền Neon Pink 2px
        vignette_intensity=0.40,
    ),
    "chien_than": StylePresetConfig(
        name="chien_than",
        label="Chiến Thần Rực Lửa",
        top_text_color=(255, 130, 45),          # Cam lửa rực sáng
        top_stroke_inner=(150, 20, 0),          # Đỏ sẫm lửa
        top_stroke_outer=(5, 2, 2),             # Đen
        top_glow_color=(255, 69, 0, 220),       # Hào quang lửa đỏ rực
        top_font_priority=[
            "BarlowCondensed-Bold.ttf",
            "Bangers-Regular.ttf",
            "FrancoisOne-Regular.ttf",
        ],
        bottom_gradient=[
            (255, 235, 120),                    # Đỉnh: Vàng lửa
            (245, 75, 20),                      # Giữa: Cam đỏ rực lửa
            (190, 18, 18),                      # Đáy: Đỏ thẫm chiến binh
        ],
        bottom_stroke_inner=(255, 255, 255),    # Viền trong trắng tương phản
        bottom_stroke_outer=(0, 0, 0),          # Viền ngoài đen đậm
        bottom_glow_color=(239, 68, 68, 175),   # Ánh lửa rực xung quanh
        bottom_3d_depth=11,
        bottom_3d_color=(20, 4, 4),             # Đổ bóng 3D than hồng
        bottom_font_priority=[
            "BarlowCondensed-Bold.ttf",
            "Bangers-Regular.ttf",
            "FrancoisOne-Regular.ttf",
        ],
        badge_bg=(225, 29, 72),                 # Huy hiệu đỏ tươi Crimson
        badge_text=(255, 255, 255),             # Chữ trắng
        badge_border=(250, 204, 21),            # Viền vàng kim loại
        vignette_intensity=0.42,
    ),
}


@dataclass
class FrameScore:
    """Kết quả phân tích thị giác của một khung hình."""
    timestamp: float
    total_score: float
    sharpness: float
    contrast: float
    saturation: float
    exposure_balance: float
    is_valid: bool = True
    reason: str = "OK"


@dataclass
class ThumbnailConfig:
    """Cấu hình render thumbnail đầy đủ."""
    top_title: str = ""
    bottom_title: str = ""
    badge_text: str = ""
    preset: str = "co_dai"
    aspect: str = "16:9"
    width: int = 1280
    height: int = 720
    custom_frame_path: str | None = None
    timestamp_sec: float | None = None
    enhance_image: bool = True


# ==============================================================================
# SMART BADGE & EPISODE DETECTOR (LINK, TIÊU ĐỀ & THỜI LƯỢNG)
# ==============================================================================

_CN_NUMS = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
}


def _parse_chinese_numeral(s: str) -> int | None:
    """Chuyển đổi số Hán tự (ví dụ: 十七 -> 17, 二十五 -> 25, 一百零五 -> 105) sang số nguyên."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s:
        return None
    val = 0
    if '百' in s:
        parts = s.split('百', 1)
        hundred = _CN_NUMS.get(parts[0], 1) if parts[0] else 1
        val += hundred * 100
        s = parts[1]
    if '十' in s:
        parts = s.split('十', 1)
        ten = _CN_NUMS.get(parts[0], 1) if parts[0] else 1
        val += ten * 10
        s = parts[1]
    for ch in s:
        if ch in _CN_NUMS:
            val += _CN_NUMS[ch]
    return val if val > 0 else None


def _download_youtube_thumbnail(url: str, output_dir: str) -> str | None:
    """Tải ảnh bìa gốc phân giải cao nhất từ link YouTube nếu có thể."""
    m = re.search(r"(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", url)
    if not m:
        return None
    video_id = m.group(1)
    import requests
    os.makedirs(output_dir, exist_ok=True)
    for res_name in ("maxresdefault.jpg", "hqdefault.jpg"):
        thumb_url = f"https://img.youtube.com/vi/{video_id}/{res_name}"
        try:
            resp = requests.get(thumb_url, timeout=5.0)
            if resp.status_code == 200 and len(resp.content) > 1000:
                dest = os.path.join(output_dir, "thumbnail_original.jpg")
                with open(dest, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Đã tải thumbnail gốc từ YouTube: {dest}")
                return dest
        except Exception:
            continue
    return None


def detect_badge_from_context(
    title: str = "",
    source_url: str = "",
    filename: str = "",
    duration_sec: float = 0.0,
) -> str:
    """Tự động nhận diện huy hiệu số tập (tập lẻ hoặc dải tập video dài) từ link, tiêu đề hoặc thời lượng."""
    combined = f"{title} {source_url} {filename}"

    # 1. Nhận diện từ Query URL (Bilibili ?p=12, YouTube &index=12, ?ep=12, ?part=15)
    if source_url:
        p_match = re.search(r'[?&](?:p|index|ep|episode|part)=(\d+)', source_url, re.IGNORECASE)
        if p_match:
            return f"TẬP {int(p_match.group(1))}"

    # 2. Nhận diện Dải tập Video dài (Range: 1-100, 1~50, 01-30, 1_100, 全100集, 全50话)
    range_match = re.search(r'(?:full|tập|tap|ep|part)?\s*(\d+)\s*[-–~到至_]\s*(\d+)', combined, re.IGNORECASE)
    if range_match:
        start_ep = int(range_match.group(1))
        end_ep = int(range_match.group(2))
        if start_ep < end_ep and end_ep <= 2000:
            return f"{start_ep}-{end_ep}"

    # Tiếng Trung: 全100集, 全12话 -> "1-100", "1-12"
    cn_full_match = re.search(r'全\s*(\d+)\s*[集话話]', combined)
    if cn_full_match:
        return f"1-{cn_full_match.group(1)}"

    # Từ khóa Full bộ / Trọn bộ
    if re.search(r'(?i)(trọn bộ|toàn tập|full bộ|full season|合集)', combined):
        return "TRỌN BỘ"

    # 3. Nhận diện Tập cuối / Kết thúc
    if re.search(r'(?i)(tập cuối|đại kết cục|kết thúc|final|the end|大结局|结局)', combined):
        return "TẬP CUỐI"

    # 4. Nhận diện Tập lẻ tiếng Trung / Anime (第17集, 第十七回, 第42话, 第105期)
    cn_ep_match = re.search(r'第\s*([0-9零一二两三四五六七八九十百]+)\s*[集话話回期]', combined)
    if cn_ep_match:
        num = _parse_chinese_numeral(cn_ep_match.group(1))
        if num is not None:
            return f"TẬP {num}"

    # 5. Nhận diện Tập lẻ tiếng Việt / tiếng Anh (Tập 12, Tap 12, EP12, Ep.05, E12, Part 3)
    single_match = re.search(r'(?i)(?:tập|tap|ep|e|chương|chuong|part)\s*[\.\_\-\s]*0*([1-9]\d*)', combined)
    if single_match:
        return f"TẬP {single_match.group(1)}"

    # Số tập độc lập trong dấu ngoặc: [12], (12), 【12】
    bracket_match = re.search(r'[\[\(【]0*([1-9]\d*)[\]\)】]', combined)
    if bracket_match:
        return f"TẬP {bracket_match.group(1)}"

    # 6. Fallback thông minh theo thời lượng video nếu không tìm thấy số tập trong text
    dur = float(duration_sec or 0.0)
    if dur >= 3600:  # Video dài hơn 1 tiếng
        return "1-100"
    elif dur >= 1800:  # Video dài hơn 30 phút
        return "TRỌN BỘ"

    # Video ngắn
    return "TẬP 1"


def extract_info_from_link_or_text(text_or_url: str, output_dir: str = "") -> dict:
    """Rút trích toàn diện thông tin (Badge, Tiêu đề gợi ý, Nền tảng, URL, Thumbnail) từ Link hoặc văn bản chia sẻ."""
    text = (text_or_url or "").strip()
    result: dict = {
        "badge": "",
        "suggested_title": "",
        "url": "",
        "platform": "",
        "thumbnail_path": None,
    }
    if not text:
        return result

    # 1. Trích xuất URL nếu có trong văn bản
    url_m = re.search(r'https?://[^\s<>"]+', text)
    extracted_url = url_m.group(0).rstrip('.,;!?') if url_m else ""
    result["url"] = extracted_url

    # 2. Xác định nền tảng (Platform)
    u_lower = extracted_url.lower()
    if "youtube.com" in u_lower or "youtu.be" in u_lower:
        result["platform"] = "YouTube"
    elif "bilibili.com" in u_lower or "b23.tv" in u_lower:
        result["platform"] = "Bilibili"
    elif "douyin.com" in u_lower or "iesdouyin.com" in u_lower:
        result["platform"] = "Douyin"
    elif "tiktok.com" in u_lower:
        result["platform"] = "TikTok"
    elif "kuaishou.com" in u_lower:
        result["platform"] = "Kuaishou"
    elif extracted_url:
        result["platform"] = "Web"

    # 3. Nhận diện Huy hiệu (Badge: Tập lẻ hoặc Dải tập)
    result["badge"] = detect_badge_from_context(
        title=text,
        source_url=extracted_url,
    )

    # 4. Trích xuất Tiêu đề gợi ý từ dấu ngoặc vuông 【...】 hoặc tiêu đề text
    bracket_m = re.search(r'【([^】]+)】', text)
    if bracket_m:
        raw_t = bracket_m.group(1).strip()
        clean_t = re.sub(r'第\s*[0-9零一二两三四五六七八九十百]+\s*[集话話回期]', '', raw_t)
        clean_t = re.sub(r'全\s*\d+\s*[集话話]', '', clean_t)
        clean_t = re.sub(r'的作品', '', clean_t).strip()
        if clean_t:
            result["suggested_title"] = clean_t

    # 5. Nếu là YouTube và có output_dir, tải thử thumbnail gốc
    if result["platform"] == "YouTube" and extracted_url and output_dir:
        result["thumbnail_path"] = _download_youtube_thumbnail(extracted_url, output_dir)

    return result


# ==============================================================================
# FONT LOADER
# ==============================================================================

def _get_best_font(size: int, priority_names: list[str] | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font chữ Việt hóa chất lượng cao, ưu tiên font nét đậm, hỗ trợ 100% tiếng Việt."""
    default_priorities = [
        "BarlowCondensed-Bold.ttf",
        "FrancoisOne-Regular.ttf",
        "BarlowCondensed-Medium.ttf",
        "Coiny-Regular.ttf",
        "Bangers-Regular.ttf",
        "Merienda-Bold.ttf",
        "StoryScript-Regular.ttf",
        "Merriweather-VariableFont_opsz,wdth,wght.ttf",
        "arialbd.ttf",
        "segoeuib.ttf",
        "calibrib.ttf",
        "tahomabd.ttf",
        "Arial.ttf",
        "segoeui.ttf",
    ]
    candidates = (priority_names or []) + [f for f in default_priorities if f not in (priority_names or [])]

    font_files = bundled_font_files()
    file_map = {os.path.basename(f).lower(): f for f in font_files}

    for name in candidates:
        key = name.lower()
        if key in file_map:
            try:
                return ImageFont.truetype(file_map[key], size=size)
            except Exception:
                continue

    # Thử font hệ thống Windows
    win_dir = os.environ.get("WINDIR", "C:\\Windows")
    for name in candidates:
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


# ==============================================================================
# FRAME ANALYZER (SCORING THỰC TẾ)
# ==============================================================================

def score_frame_quality(img: Image.Image, timestamp: float = 0.0) -> FrameScore:
    """Chấm điểm chất lượng thị giác của khung hình qua độ nét, độ tương phản, rực màu và ánh sáng.

    Tiêu chuẩn:
    - Sắc nét (Sharpness): Phân tích biên độ cạnh viền lọc qua Laplacian/FIND_EDGES (tránh motion blur).
    - Phơi sáng (Exposure): Phạt nặng khung hình tối đen (< 25) hoặc cháy sáng (> 238).
    - Tương phản (Contrast): Độ lệch chuẩn kênh xám std_lum.
    - Rực màu (Saturation): Điểm cao cho khung hình sống động, màu sắc tươi tắn của Manhwa/Anime.
    """
    gray = img.convert("L")
    stat_gray = ImageStat.Stat(gray)
    mean_lum = float(stat_gray.mean[0])
    std_lum = float(stat_gray.stddev[0])

    # 1. Kiểm tra giới hạn phơi sáng (Hard penalty cho cảnh đen/cháy)
    if mean_lum < 25.0:
        return FrameScore(
            timestamp=timestamp, total_score=-250.0, sharpness=0.0,
            contrast=std_lum, saturation=0.0, exposure_balance=0.0,
            is_valid=False, reason="Quá tối (cảnh đen / chuyển cảnh)"
        )
    if mean_lum > 238.0:
        return FrameScore(
            timestamp=timestamp, total_score=-250.0, sharpness=0.0,
            contrast=std_lum, saturation=0.0, exposure_balance=0.0,
            is_valid=False, reason="Cháy sáng (overexposed / flash trắng)"
        )

    # 2. Kiểm tra độ tương phản tối thiểu (Tránh cảnh màu bệt, phẳng lì)
    if std_lum < 16.0:
        return FrameScore(
            timestamp=timestamp, total_score=-150.0, sharpness=0.0,
            contrast=std_lum, saturation=0.0, exposure_balance=0.0,
            is_valid=False, reason="Độ tương phản quá thấp (ảnh phẳng)"
        )

    # 3. Tính độ sắc nét (Sharpness / Clarity qua viền cạnh)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat_edges = ImageStat.Stat(edges)
    sharpness = float(stat_edges.stddev[0])

    # 4. Tính độ rực rỡ màu sắc (HSV Saturation)
    hsv = img.convert("HSV")
    stat_hsv = ImageStat.Stat(hsv)
    saturation = float(stat_hsv.mean[1])

    # 5. Độ cân bằng sáng (Lý tưởng quanh mốc 115 - 145)
    lum_balance = max(0.0, 1.0 - abs(mean_lum - 128.0) / 128.0)

    # Điểm tổng hợp có trọng số
    total = (sharpness * 3.2) + (std_lum * 2.0) + (saturation * 1.4) + (lum_balance * 35.0)

    # Phạt nếu độ nét dưới ngưỡng chuẩn (motion blur)
    if sharpness < 8.0:
        total -= 75.0

    return FrameScore(
        timestamp=timestamp,
        total_score=round(total, 2),
        sharpness=round(sharpness, 2),
        contrast=round(std_lum, 2),
        saturation=round(saturation, 2),
        exposure_balance=round(lum_balance, 2),
        is_valid=True,
        reason="Đạt chuẩn",
    )


def extract_frame_at_timestamp(video_path: str, timestamp_sec: float, output_path: str) -> str:
    """Trích xuất chính xác khung hình tại thời điểm timestamp_sec bằng ffmpeg."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video không tồn tại: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", f"{max(0.0, float(timestamp_sec)):.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y", output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 500:
        raise RuntimeError(f"Không thể trích xuất frame tại giây {timestamp_sec}: {res.stderr}")

    return output_path


def get_video_duration(video_path: str) -> float:
    """Lấy thời lượng video tính bằng giây."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return max(1.0, float(res.stdout.strip()))
    except Exception:
        pass
    return 30.0


def find_best_frame(
    video_path: str,
    output_png: str,
    duration_sec: float | None = None,
    num_candidates: int = 10,
) -> tuple[str, float]:
    """Tự động phân tích nhiều thời điểm và chọn ra khung hình sắc nét, bắt mắt nhất."""
    dur = float(duration_sec or 0.0)
    if dur <= 0:
        dur = get_video_duration(video_path)

    # Phân bổ các mốc ứng viên hợp lý từ 12% đến 88% thời lượng video (tránh intro đen/logo)
    if dur <= 6.0:
        candidates = [dur * 0.3, dur * 0.6]
    else:
        step = (dur * 0.76) / max(2, num_candidates)
        start = dur * 0.12
        candidates = [round(start + i * step, 2) for i in range(num_candidates)]

    temp_dir = os.path.dirname(os.path.abspath(output_png))
    best_score = -999.0
    best_file = None
    best_time = candidates[0] if candidates else 1.5

    for idx, t_stamp in enumerate(candidates):
        cand_file = os.path.join(temp_dir, f"cand_frame_{idx}.jpg")
        try:
            extract_frame_at_timestamp(video_path, t_stamp, cand_file)
            with Image.open(cand_file) as im:
                im_rgb = im.convert("RGB")
                score_obj = score_frame_quality(im_rgb, timestamp=t_stamp)

            if score_obj.total_score > best_score:
                best_score = score_obj.total_score
                best_time = t_stamp
                if best_file and os.path.exists(best_file):
                    try:
                        os.remove(best_file)
                    except OSError:
                        pass
                best_file = cand_file
            else:
                if os.path.exists(cand_file):
                    try:
                        os.remove(cand_file)
                    except OSError:
                        pass
        except Exception:
            if os.path.exists(cand_file):
                try:
                    os.remove(cand_file)
                except OSError:
                    pass

    if best_file and os.path.exists(best_file):
        os.replace(best_file, output_png)
        logger.info(f"Đã chọn frame đắt giá nhất tại {best_time:.1f}s (Điểm: {best_score:.1f})")
        return output_png, best_time

    # Fallback an toàn
    fallback_time = min(max(1.0, dur * 0.25), dur - 0.5)
    extract_frame_at_timestamp(video_path, fallback_time, output_png)
    return output_png, fallback_time


def extract_best_frame(video_path: str, output_png: str, duration_sec: float | None = None) -> str:
    """Tương thích ngược với các module cũ."""
    out, _ = find_best_frame(video_path, output_png, duration_sec=duration_sec)
    return out


# ==============================================================================
# GRAPHIC RENDERER (3D EXTRUSION, DOUBLE STROKE & NEON GLOW)
# ==============================================================================

def _create_vignette_layer(width: int, height: int, intensity: float = 0.35) -> Image.Image:
    """Tạo lớp mờ tối nhẹ quanh 4 viền mép để tôn nhân vật và chữ ở trung tâm."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = width // 2, height // 2
    max_r = int(((width / 2) ** 2 + (height / 2) ** 2) ** 0.5)
    inner_r = int(max_r * 0.45)

    for r in range(max_r, inner_r, -15):
        factor = (r - inner_r) / (max_r - inner_r)
        alpha = int(255 * (factor ** 1.6) * min(1.0, intensity))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)

    blurred_mask = mask.filter(ImageFilter.GaussianBlur(35))
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vignette.paste((5, 5, 12, 230), (0, 0), blurred_mask)
    return vignette


def _create_vertical_gradient_image(
    width: int,
    height: int,
    colors: list[tuple[int, int, int]],
) -> Image.Image:
    """Tạo ảnh gradient tuyến tính dọc từ danh sách màu."""
    grad = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(grad)

    if len(colors) == 1:
        c = colors[0]
        return Image.new("RGBA", (width, height), (c[0], c[1], c[2], 255))

    n_segments = len(colors) - 1
    seg_height = height / max(1, n_segments)

    for i in range(n_segments):
        c1, c2 = colors[i], colors[i + 1]
        y_start = int(i * seg_height)
        y_end = int((i + 1) * seg_height) if i < n_segments - 1 else height

        for y in range(y_start, y_end):
            t = (y - y_start) / max(1, (y_end - y_start))
            r = int(c1[0] + t * (c2[0] - c1[0]))
            g = int(c1[1] + t * (c2[1] - c1[1]))
            b = int(c1[2] + t * (c2[2] - c1[2]))
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    return grad


def _render_3d_text_block(
    canvas: Image.Image,
    text: str,
    pos: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    gradient_colors: list[tuple[int, int, int]],
    inner_stroke: tuple[int, int, int] | None,
    outer_stroke: tuple[int, int, int],
    glow_color: tuple[int, int, int, int] | None,
    extrusion_depth: int = 10,
    extrusion_color: tuple[int, int, int] = (10, 10, 10),
    is_center: bool = True,
    canvas_w: int = 1280,
    stroke_w_outer: int = 8,
    stroke_w_inner: int = 3,
) -> tuple[int, int, int, int]:
    """Vẽ khối chữ 3D đa tầng: Neon Glow -> 3D Extrusion -> Outer Stroke -> Inner Stroke -> Gradient Fill."""
    draw_temp = ImageDraw.Draw(canvas)
    bbox = draw_temp.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    lx = (canvas_w - tw) // 2 if is_center else pos[0]
    ly = pos[1]

    # Vùng đệm bao quanh khối chữ
    pad = 40 + extrusion_depth + stroke_w_outer
    box_w = tw + pad * 2
    box_h = th + pad * 2
    off_x = lx - pad
    off_y = ly - pad

    text_layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(text_layer)
    tx = pad - bbox[0]
    ty = pad - bbox[1]

    # 1. Hiệu ứng Neon Glow (Hào quang phát sáng rực rỡ quanh chữ)
    if glow_color:
        glow_layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        glow_stroke = stroke_w_outer + 10
        g_draw.text((tx, ty), text, font=font, fill=glow_color, stroke_width=glow_stroke, stroke_fill=glow_color)
        glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(14))
        text_layer = Image.alpha_composite(text_layer, glow_blurred)

    # 2. Hiệu ứng 3D Extrusion (Khối nổi 3D xéo xuống góc dưới bên phải)
    if extrusion_depth > 0:
        ext_draw = ImageDraw.Draw(text_layer)
        for d in range(extrusion_depth, 0, -1):
            dx = int(d * 0.7)
            dy = int(d * 0.9)
            ext_draw.text(
                (tx + dx, ty + dy),
                text,
                font=font,
                fill=extrusion_color,
                stroke_width=stroke_w_outer,
                stroke_fill=extrusion_color,
            )

    # 3. Viền ngoài (Outer Stroke - Đen đậm dứt khoát)
    t_draw = ImageDraw.Draw(text_layer)
    t_draw.text(
        (tx, ty),
        text,
        font=font,
        fill=outer_stroke,
        stroke_width=stroke_w_outer,
        stroke_fill=outer_stroke,
    )

    # 4. Viền trong (Inner Stroke - Trắng hoặc màu sáng tương phản)
    if inner_stroke:
        t_draw.text(
            (tx, ty),
            text,
            font=font,
            fill=inner_stroke,
            stroke_width=stroke_w_inner,
            stroke_fill=inner_stroke,
        )

    # 5. Màu ruột chữ Gradient (Tạo dải màu đổ rực rỡ từ trên xuống)
    mask_layer = Image.new("L", (box_w, box_h), 0)
    m_draw = ImageDraw.Draw(mask_layer)
    m_draw.text((tx, ty), text, font=font, fill=255)

    grad_img = _create_vertical_gradient_image(box_w, box_h, gradient_colors)
    text_fill_layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    text_fill_layer.paste(grad_img, (0, 0), mask_layer)

    # Ghép ruột chữ lên khối chữ
    text_layer = Image.alpha_composite(text_layer, text_fill_layer)

    # Dán toàn bộ khối chữ hoàn chỉnh lên canvas chính
    canvas.paste(text_layer, (off_x, off_y), text_layer)

    return (lx, ly, tw, th)


def _draw_badge_box(
    canvas: Image.Image,
    text: str,
    pos: tuple[int, int],
    preset: StylePresetConfig,
    height: int,
) -> tuple[int, int, int, int]:
    """Vẽ huy hiệu Badge số tập sắc cạnh, bắt mắt chuẩn phong cách Manhwa."""
    badge_str = str(text or "").strip().upper()
    if not badge_str:
        return (pos[0], pos[1], 0, 0)

    font_size = max(18, int(height * 0.038))
    font = _get_best_font(font_size, priority_names=preset.bottom_font_priority)

    draw = ImageDraw.Draw(canvas)
    b_bbox = draw.textbbox((0, 0), badge_str, font=font)
    bw = (b_bbox[2] - b_bbox[0]) + 30
    bh = (b_bbox[3] - b_bbox[1]) + 16

    bx, by = pos

    # Đổ bóng nhẹ cho huy hiệu
    badge_layer = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge_layer)

    # Bóng đen
    b_draw.rounded_rectangle(
        [bx + 4, by + 4, bx + bw + 4, by + bh + 4],
        radius=8,
        fill=(0, 0, 0, 180),
    )
    # Khối huy hiệu chính
    b_draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=8,
        fill=preset.badge_bg + (255,),
        outline=preset.badge_border + (255,),
        width=3,
    )
    # Chữ bên trong huy hiệu
    tx = bx + (bw - (b_bbox[2] - b_bbox[0])) // 2 - b_bbox[0]
    ty = by + (bh - (b_bbox[3] - b_bbox[1])) // 2 - b_bbox[1] - 1
    b_draw.text((tx, ty), badge_str, font=font, fill=preset.badge_text)

    canvas.paste(badge_layer, (0, 0), badge_layer)
    return (bx, by, bw, bh)


# ==============================================================================
# MAIN RENDER FUNCTION
# ==============================================================================

def render_thumbnail(
    frame_path: str,
    title: str,
    output_path: str,
    width: int = 1280,
    height: int = 720,
    badge_text: str = "",
    top_title: str = "",
    bottom_title: str = "",
    preset: str = "co_dai",
    enhance_image: bool = True,
) -> str:
    """Thiết kế và render đồ họa ảnh bìa High-CTR chuẩn YouTube Review Phim / Manhwa.

    Hỗ trợ đầy đủ:
    - 3 Style Presets thực tế (Cổ Đại Làm Giàu, Quân Sư Hiện Đại, Chiến Thần Rực Lửa).
    - Typography 3D Extrusion, viền kép tương phản cao, phát sáng Neon Glow.
    - Huy hiệu Badge số tập sắc cạnh.
    - Cân đối bố cục theo tỉ lệ 16:9 (ngang) và 9:16 (dọc).
    """
    preset_cfg = PRESETS.get(preset, PRESETS["co_dai"])

    # 1. Nạp và xử lý ảnh nền
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 500:
        try:
            with Image.open(frame_path) as im:
                base_img = im.convert("RGB")
        except Exception:
            base_img = Image.new("RGB", (width, height), color=(18, 16, 28))
    else:
        base_img = Image.new("RGB", (width, height), color=(18, 16, 28))

    # Tăng cường chất lượng hình ảnh (Clarity & Vibrance)
    if enhance_image:
        base_img = ImageEnhance.Color(base_img).enhance(1.24)
        base_img = ImageEnhance.Contrast(base_img).enhance(1.16)
        base_img = ImageEnhance.Sharpness(base_img).enhance(1.35)

    # Scale & Crop theo tỷ lệ chuẩn không méo hình
    img_w, img_h = base_img.size
    img_ratio = img_w / img_h
    target_ratio = width / height

    if img_ratio > target_ratio:
        new_h = height
        new_w = int(img_w * (height / img_h))
    else:
        new_w = width
        new_h = int(img_h * (width / img_w))

    scaled = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    crop_x = (new_w - width) // 2
    crop_y = (new_h - height) // 2
    canvas = scaled.crop((crop_x, crop_y, crop_x + width, crop_y + height)).convert("RGBA")

    # 2. Lớp Vignette viền mép để gom thị giác
    vignette = _create_vignette_layer(width, height, intensity=preset_cfg.vignette_intensity)
    canvas = Image.alpha_composite(canvas, vignette)

    # 3. Lớp gradient bóng đổ tinh tế chỉ ở chân/đỉnh chữ (Không che khuất nhân vật)
    is_vertical = height > width
    shadow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_overlay)

    if is_vertical:
        # 9:16 (Shorts/TikTok): Gradient nhẹ đỉnh và gradient đậm 50% - 90%
        top_h = int(height * 0.25)
        for y in range(top_h):
            alpha = int(140 * (1.0 - (y / top_h)))
            s_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        bot_start = int(height * 0.45)
        for y in range(bot_start, height):
            alpha = int(195 * ((y - bot_start) / (height - bot_start)) ** 1.2)
            s_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    else:
        # 16:9 (YouTube): Gradient nhẹ ở đỉnh & nửa dưới đậm dần
        top_h = int(height * 0.22)
        for y in range(top_h):
            alpha = int(120 * (1.0 - (y / top_h)))
            s_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        bot_start = int(height * 0.42)
        for y in range(bot_start, height):
            alpha = int(210 * ((y - bot_start) / (height - bot_start)) ** 1.3)
            s_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    canvas = Image.alpha_composite(canvas, shadow_overlay)

    # 4. Chuẩn hóa tiêu đề trên / dưới
    raw_top = top_title.strip()
    raw_bottom = bottom_title.strip()

    if not raw_top and not raw_bottom:
        # Phân tách từ title nếu chưa chia top/bottom
        clean_raw = re.sub(r"[\u4e00-\u9fff]+", "", str(title or "")).strip()
        clean_raw = re.sub(r"\.(mp4|mkv|avi|mov|flv|wmv|srt)$", "", clean_raw, flags=re.I).strip()
        clean_raw = re.sub(r"[\_\-]+", " - ", clean_raw)
        clean_raw = re.sub(r"\s+", " ", clean_raw)

        if " - " in clean_raw:
            parts = clean_raw.split(" - ", 1)
            raw_top = parts[0].strip()
            raw_bottom = parts[1].strip()
        else:
            raw_top = "XUYÊN KHÔNG VỀ THỜI CỔ ĐẠI"
            raw_bottom = clean_raw or "DÙNG TƯ DUY HIỆN ĐẠI ĐỂ LÀM GIÀU"

    top_text = raw_top or "SIÊU PHẨM MỚI NHẤT"
    bottom_text = raw_bottom or "DÙNG TƯ DUY HIỆN ĐẠI LÀM GIÀU"

    # 5. Tính toán và vẽ Tiêu đề trên (Eyebrow / Header)
    top_font_size = max(22, int(height * (0.046 if is_vertical else 0.060)))
    top_font = _get_best_font(top_font_size, priority_names=preset_cfg.top_font_priority)
    top_draw = ImageDraw.Draw(canvas)

    top_chars = max(14, int(width / (top_font_size * 0.62)))
    top_lines = textwrap.wrap(top_text, width=top_chars)[:2]

    # Tự động co kích thước font nếu bất kỳ dòng nào vượt quá 88% bề ngang canvas
    for _ in range(10):
        max_w = max(top_draw.textbbox((0, 0), line, font=top_font)[2] - top_draw.textbbox((0, 0), line, font=top_font)[0] for line in top_lines)
        if max_w <= width * 0.88:
            break
        top_font_size -= 2
        top_font = _get_best_font(top_font_size, priority_names=preset_cfg.top_font_priority)

    top_line_h = int(top_font_size * 1.25)
    top_y = int(height * 0.10 if is_vertical else height * 0.055)

    for idx, t_line in enumerate(top_lines):
        _render_3d_text_block(
            canvas=canvas,
            text=t_line,
            pos=(0, top_y + idx * top_line_h),
            font=top_font,
            gradient_colors=[preset_cfg.top_text_color],
            inner_stroke=preset_cfg.top_stroke_inner,
            outer_stroke=preset_cfg.top_stroke_outer,
            glow_color=preset_cfg.top_glow_color,
            extrusion_depth=4,
            extrusion_color=(0, 0, 0),
            is_center=True,
            canvas_w=width,
            stroke_w_outer=max(4, int(top_font_size * 0.10)),
            stroke_w_inner=max(2, int(top_font_size * 0.04)),
        )

    # 6. Vẽ Huy hiệu Badge (Không đè lên tiêu đề trên)
    badge_label = badge_text.strip() or "1-100"
    if is_vertical:
        # 9:16: Đặt ngay trên đỉnh, căn giữa
        badge_y = int(height * 0.038)
        badge_x = int(width * 0.06)
    else:
        # 16:9: Đặt ở góc phải bên dưới tiêu đề trên (chuẩn vị trí tập truyện YouTube)
        top_end_y = top_y + len(top_lines) * top_line_h
        badge_y = max(top_end_y + 10, int(height * 0.32))
        badge_x = int(width * 0.84)

    _draw_badge_box(canvas, badge_label, (badge_x, badge_y), preset_cfg, height)

    # 7. Vẽ Tiêu đề dưới (Main Hook / Punchline - Chữ to bản 3D nổi bật)
    bot_font_size = max(30, int(height * (0.072 if is_vertical else 0.088)))
    bot_font = _get_best_font(bot_font_size, priority_names=preset_cfg.bottom_font_priority)

    bot_chars = max(10, int(width / (bot_font_size * 0.60)))
    bot_lines = textwrap.wrap(bottom_text.upper(), width=bot_chars)[:3]

    # Tự động co kích thước font nếu bất kỳ dòng nào vượt quá 88% bề ngang canvas
    for _ in range(12):
        max_bw = max(top_draw.textbbox((0, 0), line, font=bot_font)[2] - top_draw.textbbox((0, 0), line, font=bot_font)[0] for line in bot_lines)
        if max_bw <= width * 0.88:
            break
        bot_font_size -= 2
        bot_font = _get_best_font(bot_font_size, priority_names=preset_cfg.bottom_font_priority)

    bot_line_h = int(bot_font_size * 1.22)
    total_bot_h = len(bot_lines) * bot_line_h

    if is_vertical:
        # 9:16: Vùng giữa 60% - 80% (tránh khu vực comment và thanh tua dưới)
        start_bot_y = int(height * 0.68) - (total_bot_h // 2)
    else:
        # 16:9: Vùng 1/3 dưới
        start_bot_y = height - total_bot_h - int(height * 0.065)

    for idx, b_line in enumerate(bot_lines):
        _render_3d_text_block(
            canvas=canvas,
            text=b_line,
            pos=(0, start_bot_y + idx * bot_line_h),
            font=bot_font,
            gradient_colors=preset_cfg.bottom_gradient,
            inner_stroke=preset_cfg.bottom_stroke_inner,
            outer_stroke=preset_cfg.bottom_stroke_outer,
            glow_color=preset_cfg.bottom_glow_color,
            extrusion_depth=preset_cfg.bottom_3d_depth,
            extrusion_color=preset_cfg.bottom_3d_color,
            is_center=True,
            canvas_w=width,
            stroke_w_outer=max(5, int(bot_font_size * 0.12)),
            stroke_w_inner=max(2, int(bot_font_size * 0.04)),
        )

    # 8. Lưu file kết quả JPEG chất lượng 95
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    logger.info(f"Đã render xong Thumbnail High-CTR ({preset}): {output_path}")
    return output_path


def generate_high_ctr_thumbnail(
    video_path: str,
    title: str,
    output_path: str,
    aspect: str = "16:9",
    badge_text: str = "",
    top_title: str = "",
    bottom_title: str = "",
    preset: str = "co_dai",
    timestamp_sec: float | None = None,
    duration_sec: float | None = None,
) -> str:
    """Hàm tiện ích trích xuất frame từ video và sinh Thumbnail hoàn chỉnh."""
    temp_dir = os.path.dirname(os.path.abspath(output_path))
    temp_frame = os.path.join(temp_dir, f"temp_thumb_{os.getpid()}.jpg")

    try:
        if timestamp_sec is not None and timestamp_sec >= 0:
            extract_frame_at_timestamp(video_path, timestamp_sec, temp_frame)
        else:
            find_best_frame(video_path, temp_frame, duration_sec=duration_sec)
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
        top_title=top_title,
        bottom_title=bottom_title,
        preset=preset,
    )

    if os.path.exists(temp_frame):
        try:
            os.remove(temp_frame)
        except OSError:
            pass

    return res
