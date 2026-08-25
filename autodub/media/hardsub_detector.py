"""Tự động phát hiện vị trí phụ đề cứng (Hardcoded Subtitles / Hardsub) trên Video.

Sử dụng phương pháp thị giác máy tính nhẹ (Gradient Density, Horizontal Projection &
Morphological Text Profiling) để tự động nhận diện các dải phụ đề xuất hiện thường xuyên
ở đáy/đỉnh khung hình, sinh ra danh sách `blur_regions` chuẩn hoá [0..1].
"""
from __future__ import annotations

import os
import subprocess
import numpy as np
from scipy import ndimage

from autodub.utils import setup_logging

logger = setup_logging("autodub.hardsub_detector")


def extract_video_sample_frames(
    video_path: str,
    max_frames: int = 10,
    target_width: int = 640,
    target_height: int = 360,
) -> list[tuple[float, np.ndarray]]:
    """Trích xuất một số frame mẫu từ video dưới dạng ảnh xám (Grayscale numpy array).

    Trả về danh sách các tuple: (timestamp_giây, ma_trận_ảnh_2d_uint8).
    """
    if not os.path.exists(video_path):
        return []

    # Đọc thời lượng video
    from autodub.media.video import probe_duration
    duration = probe_duration(video_path) or 10.0
    if duration <= 1.0:
        timestamps = [0.5]
    else:
        # Lấy mẫu cách đều, tránh 5% đầu và cuối video (intro/outro)
        start_t = max(0.5, duration * 0.05)
        end_t = min(duration - 0.5, duration * 0.95)
        timestamps = list(np.linspace(start_t, end_t, max_frames))

    frames: list[tuple[float, np.ndarray]] = []
    frame_bytes = target_width * target_height

    for t in timestamps:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{t:.2f}",
            "-i", video_path,
            "-vframes", "1",
            "-s", f"{target_width}x{target_height}",
            "-pix_fmt", "gray",
            "-f", "rawvideo",
            "-",
        ]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0 and len(res.stdout) == frame_bytes:
                img = np.frombuffer(res.stdout, dtype=np.uint8).reshape((target_height, target_width))
                frames.append((float(t), img))
        except Exception as e:
            logger.debug(f"Không thể trích xuất frame tại t={t:.2f}s: {e}")
            continue

    return frames


def detect_text_regions_in_image(
    gray_img: np.ndarray,
    min_edge_density: float = 0.08,
    min_width_ratio: float = 0.25,
    min_height_ratio: float = 0.035,
    max_height_ratio: float = 0.25,
) -> list[dict]:
    """Phát hiện các dải hình chữ nhật chứa phụ đề trong một khung hình ảnh xám."""
    h, w = gray_img.shape
    if h < 50 or w < 50:
        return []

    # 1. Tính gradient cạnh theo trục ngang và trục dọc (Sobel Filter)
    sx = ndimage.sobel(gray_img.astype(np.float32), axis=1)
    sy = ndimage.sobel(gray_img.astype(np.float32), axis=0)
    mag = np.hypot(sx, sy)

    # 2. Ngưỡng phát hiện cạnh sắc nét
    max_mag = float(np.max(mag)) if len(mag) > 0 else 0.0
    if max_mag < 30.0:
        return []
    edges = (mag > 40.0).astype(np.uint8)


    # 3. Phân tích hình thái học: Đóng nét ngang (Morphological horizontal closing)
    # Phụ đề gồm các ký tự san sát nhau trên một hoặc hai dòng ngang
    kernel_w = max(5, int(w * 0.035))
    struct_h = np.ones((1, kernel_w), dtype=np.uint8)
    closed = ndimage.binary_dilation(edges, structure=struct_h)
    closed = ndimage.binary_erosion(closed, structure=struct_h)

    # 4. Gắn nhãn các vùng liên thông (Connected Components)
    labeled, num_features = ndimage.label(closed)
    if num_features == 0:
        return []

    regions: list[dict] = []
    objects = ndimage.find_objects(labeled)

    for slc in objects:
        if slc is None:
            continue
        y_slc, x_slc = slc
        y0, y1 = y_slc.start, y_slc.stop
        x0, x1 = x_slc.start, x_slc.stop

        reg_h = y1 - y0
        reg_w = x1 - x0
        hr = reg_h / float(h)
        wr = reg_w / float(w)
        yr = y0 / float(h)

        # Phụ đề video phổ biến:
        # - Nằm ở 35% phía dưới (yr > 0.65) hoặc 25% phía trên (yr < 0.25)
        # - Bề rộng tối thiểu ~25% khung hình
        # - Chiều cao từ 3.5% đến 25% khung hình
        is_sub_zone = (yr >= 0.60) or (yr <= 0.25) or (0.40 <= yr <= 0.60 and hr <= 0.15)
        if is_sub_zone and (wr >= min_width_ratio) and (min_height_ratio <= hr <= max_height_ratio):
            # Tính mật độ cạnh thật sự bên trong bounding box
            sub_edges = edges[y0:y1, x0:x1]
            density = np.mean(sub_edges)
            if density >= min_edge_density:
                # Chuẩn hoá toạ độ [0..1] kèm padding nhẹ an toàn
                pad_x = min(0.02, wr * 0.05)
                pad_y = min(0.015, hr * 0.10)
                norm_x = max(0.0, float(x0 / w) - pad_x)
                norm_y = max(0.0, float(y0 / h) - pad_y)
                norm_w = min(1.0 - norm_x, float(reg_w / w) + 2 * pad_x)
                norm_h = min(1.0 - norm_y, float(reg_h / h) + 2 * pad_y)

                regions.append({
                    "x": round(norm_x, 3),
                    "y": round(norm_y, 3),
                    "w": round(norm_w, 3),
                    "h": round(norm_h, 3),
                })

    return regions


def merge_similar_regions(
    regions_across_frames: list[list[dict]],
    min_occurrence: float = 0.30,
) -> list[dict]:
    """Gộp các vùng phụ đề xuất hiện ổn định ở cùng một vị trí qua các khung hình."""
    all_regs: list[dict] = []
    for fl in regions_across_frames:
        all_regs.extend(fl)

    if not all_regs:
        return []

    total_frames = max(1, len(regions_across_frames))
    clusters: list[list[dict]] = []

    for reg in all_regs:
        matched = False
        for cl in clusters:
            rep = cl[0]
            # Kiểm tra độ tương đồng vị trí y và chiều cao h (phụ đề thường giữ cố định độ cao y)
            if abs(reg["y"] - rep["y"]) < 0.06 and abs(reg["h"] - rep["h"]) < 0.06:
                cl.append(reg)
                matched = True
                break
        if not matched:
            clusters.append([reg])

    final_regions: list[dict] = []
    for cl in clusters:
        occurrence_rate = len(cl) / float(total_frames)
        if occurrence_rate >= min_occurrence:
            # Lấy bounding box bao trùm các lần xuất hiện
            min_x = min(r["x"] for r in cl)
            min_y = min(r["y"] for r in cl)
            max_x2 = max(r["x"] + r["w"] for r in cl)
            max_y2 = max(r["y"] + r["h"] for r in cl)

            final_regions.append({
                "x": round(max(0.0, min_x), 3),
                "y": round(max(0.0, min_y), 3),
                "w": round(min(1.0, max_x2 - min_x), 3),
                "h": round(min(1.0, max_y2 - min_y), 3),
            })

    return final_regions


def detect_hardsub_regions(
    video_path: str,
    max_samples: int = 12,
    min_occurrence: float = 0.25,
) -> list[dict]:
    """Hàm chính: Tự động quét video và trả về danh sách các vùng che phụ đề cứng `blur_regions`."""
    try:
        sample_frames = extract_video_sample_frames(video_path, max_frames=max_samples)
    except Exception as e:
        logger.warning(f"Lỗi khi trích xuất frame từ video {video_path}: {e}")
        return []

    if not sample_frames:
        return []

    frame_regions: list[list[dict]] = []
    for _ts, frame in sample_frames:
        regs = detect_text_regions_in_image(frame)
        frame_regions.append(regs)

    merged = merge_similar_regions(frame_regions, min_occurrence=min_occurrence)
    logger.info(f"Tự động phát hiện {len(merged)} vùng phụ đề cứng trong video: {merged}")
    return merged
