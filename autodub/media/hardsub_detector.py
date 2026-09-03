"""Module Tự động Phát hiện & Tạo Vùng Che Phụ đề Cứng (Auto Hardsub Detector & Masking).

Sử dụng Computer Vision (Edge Density, Local Contrast, Horizontal Projection & Spatial-Temporal Clustering)
để tự động nhận diện các dải phụ đề cứng (burned-in subtitles) xuất hiện trên video, phân biệt với logo/watermark,
và chuyển đổi thành schema `blur_regions` chuẩn của hệ thống LPHVSub.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
import numpy as np
from scipy import ndimage

try:
    import cv2
except ImportError:
    cv2 = None

from autodub.utils import setup_logging

logger = setup_logging("autodub.hardsub_detector")


@dataclass
class HardsubRegion:
    """Đại diện cho một vùng phụ đề cứng được phát hiện trên video."""
    x: float          # [0.0 .. 1.0] Tọa độ X góc trên-trái
    y: float          # [0.0 .. 1.0] Tọa độ Y góc trên-trái
    width: float      # [0.0 .. 1.0] Chiều rộng
    height: float     # [0.0 .. 1.0] Chiều cao
    start: float      # (giây) Mốc thời gian bắt đầu xuất hiện
    end: float        # (giây) Mốc thời gian kết thúc xuất hiện
    confidence: float # [0.0 .. 1.0] Độ tin cậy

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0):
            raise ValueError(f"x must be in [0, 1], got {self.x}")
        if not (0.0 <= self.y <= 1.0):
            raise ValueError(f"y must be in [0, 1], got {self.y}")
        if not (0.0 < self.width <= 1.0):
            raise ValueError(f"width must be in (0, 1], got {self.width}")
        if not (0.0 < self.height <= 1.0):
            raise ValueError(f"height must be in (0, 1], got {self.height}")
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) cannot be less than start ({self.start})")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    def to_blur_region(self) -> dict:
        """Chuyển đổi sang schema `blur_regions` chuẩn tương thích với FFmpeg filter của hệ thống."""
        res = {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "w": round(self.width, 4),
            "h": round(self.height, 4),
        }
        if self.start > 0.0 or self.end > 0.0:
            res["t_start"] = round(self.start, 3)
            res["t_end"] = round(self.end, 3)
        return res


@dataclass
class FrameSample:
    """Mẫu khung hình trích xuất từ video kèm thông tin thời gian."""
    timestamp: float
    frame_index: int = 0
    image: np.ndarray | None = None  # Grayscale image (uint8)
    orig_w: int = 0
    orig_h: int = 0


@dataclass
class TextCandidate:
    """Ứng viên vùng văn bản thô được phát hiện trong một khung hình."""
    x: int
    y: int
    w: int
    h: int
    edge_score: float = 0.0
    contrast_score: float = 0.0
    density_score: float = 0.0
    position_score: float = 0.0
    confidence: float = field(init=False)

    def __post_init__(self) -> None:
        # Công thức tính trọng số độ tin cậy đa chiều (Multi-factor Confidence Scoring)
        self.confidence = float(np.clip(
            0.30 * self.edge_score +
            0.25 * self.contrast_score +
            0.25 * self.density_score +
            0.20 * self.position_score,
            0.0, 1.0
        ))


# --------------------------------------------------------------------------- #
# 1. Trích xuất khung hình & Tiền xử lý (Frame Sampling & Preprocessing)
# --------------------------------------------------------------------------- #

def extract_video_frames(
    video_path: str,
    sample_interval_s: float = 1.5,
    max_samples: int = 25,
    target_width: int = 640,
    target_height: int = 360,
) -> list[FrameSample]:
    """Trích xuất các khung hình cách đều thời gian (Uniform Temporal Sampling)."""
    if not os.path.exists(video_path):
        return []

    from autodub.media.video import probe_duration_s
    duration = probe_duration_s(video_path) or 10.0


    if duration <= 1.0:
        timestamps = [0.5]
    else:
        # Lấy mẫu cách đều, bỏ 3% đầu/cuối video
        start_t = max(0.5, duration * 0.03)
        end_t = min(duration - 0.5, duration * 0.97)
        total_steps = int(max(2, (end_t - start_t) / sample_interval_s))
        if max_samples and total_steps > max_samples:
            total_steps = max_samples
        timestamps = list(np.linspace(start_t, end_t, total_steps))

    samples: list[FrameSample] = []

    # Ưu tiên dùng OpenCV nếu có
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or target_width
                orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or target_height
                for idx, t in enumerate(timestamps):
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        # Chuyển xám và resize
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        resized = cv2.resize(gray, (target_width, target_height), interpolation=cv2.INTER_AREA)
                        samples.append(FrameSample(
                            timestamp=float(t),
                            frame_index=idx,
                            image=resized,
                            orig_w=orig_w,
                            orig_h=orig_h,
                        ))
                cap.release()
                if len(samples) > 0:
                    return samples
        except Exception as e:
            logger.debug(f"OpenCV sampling lỗi ({e}), chuyển sang FFmpeg fallback.")

    # Fallback FFmpeg
    frame_bytes = target_width * target_height
    for idx, t in enumerate(timestamps):
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
            res = subprocess.run(cmd, capture_output=True, check=False, timeout=8)
            if res.returncode == 0 and len(res.stdout) == frame_bytes:
                img = np.frombuffer(res.stdout, dtype=np.uint8).reshape((target_height, target_width))
                samples.append(FrameSample(
                    timestamp=float(t),
                    frame_index=idx,
                    image=img,
                    orig_w=target_width,
                    orig_h=target_height,
                ))
        except Exception:
            continue

    return samples


# --------------------------------------------------------------------------- #
# 2. Phát hiện & Lọc ứng viên văn bản (Candidate Detection & Filtering)
# --------------------------------------------------------------------------- #

def detect_text_candidates_in_frame(
    gray_img: np.ndarray,
    min_width_ratio: float = 0.15,
    min_height_ratio: float = 0.03,
    max_height_ratio: float = 0.25,
) -> list[TextCandidate]:
    """Phát hiện các khối văn bản ứng viên trong khung hình qua Sobel & Projection."""
    h, w = gray_img.shape
    if h < 50 or w < 50:
        return []

    # A. Tính Gradient cạnh (Sobel Filter)
    sx = ndimage.sobel(gray_img.astype(np.float32), axis=1)
    sy = ndimage.sobel(gray_img.astype(np.float32), axis=0)
    mag = np.hypot(sx, sy)

    max_mag = float(np.max(mag)) if len(mag) > 0 else 0.0
    if max_mag < 30.0:
        return []

    edges = (mag > 40.0).astype(np.uint8)

    # B. Phân tích hình thái học đóng nét ngang (Morphological Horizontal Closing)
    kernel_w = max(6, int(w * 0.04))
    struct_h = np.ones((1, kernel_w), dtype=np.uint8)
    closed = ndimage.binary_dilation(edges, structure=struct_h)
    closed = ndimage.binary_erosion(closed, structure=struct_h)

    labeled, num_features = ndimage.label(closed)
    if num_features == 0:
        return []

    candidates: list[TextCandidate] = []
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
        xr = x0 / float(w)

        # Loại trừ logo/watermark góc màn hình (ví dụ: góc cực nhỏ trên cùng bên trái/phải)
        is_corner_watermark = (xr < 0.12 or (xr + wr) > 0.88) and (yr < 0.15) and (wr < 0.20)
        if is_corner_watermark:
            continue

        # Subtitle Position Prior (Ưu tiên dải đáy 60-95% hoặc đỉnh 5-25%)
        if yr >= 0.58:
            pos_score = 1.0
        elif yr <= 0.25:
            pos_score = 0.85
        elif 0.40 <= yr <= 0.60:
            pos_score = 0.50
        else:
            pos_score = 0.30

        if (wr >= min_width_ratio) and (min_height_ratio <= hr <= max_height_ratio):
            sub_edges = edges[y0:y1, x0:x1]
            density = float(np.mean(sub_edges))
            sub_gray = gray_img[y0:y1, x0:x1]
            contrast = float(np.std(sub_gray) / 128.0)
            edge_score = float(np.clip(density / 0.15, 0.0, 1.0))
            contrast_score = float(np.clip(contrast, 0.0, 1.0))
            density_score = float(np.clip(density / 0.10, 0.0, 1.0))

            if density >= 0.04 and contrast_score >= 0.15:
                cand = TextCandidate(
                    x=x0, y=y0, w=reg_w, h=reg_h,
                    edge_score=edge_score,
                    contrast_score=contrast_score,
                    density_score=density_score,
                    position_score=pos_score,
                )
                if cand.confidence >= 0.45:
                    candidates.append(cand)

    return candidates


# --------------------------------------------------------------------------- #
# 3. Phân cụm Không gian & Thời gian (Spatial & Temporal Clustering)
# --------------------------------------------------------------------------- #

def spatial_merge_candidates(
    candidates: list[TextCandidate],
    img_w: int,
    img_h: int,
    x_gap_threshold_ratio: float = 0.05,
    y_overlap_threshold: float = 0.50,
) -> list[dict]:
    """Hợp nhất các khối ký tự/từ gần nhau trên cùng một dòng thành một hộp phụ đề hoàn chỉnh."""
    if not candidates:
        return []

    # Sắp xếp theo trục Y rồi tới trục X
    sorted_cands = sorted(candidates, key=lambda c: (c.y, c.x))
    merged: list[dict] = []

    for c in sorted_cands:
        matched = False
        for m in merged:
            # Kiểm tra xem có nằm trên cùng dải Y không
            overlap_y = max(0, min(c.y + c.h, m["y2"]) - max(c.y, m["y1"]))
            min_h = min(c.h, m["y2"] - m["y1"])
            y_overlap_ratio = overlap_y / float(min_h) if min_h > 0 else 0

            # Khoảng cách ngang giữa 2 khối
            x_gap = max(0, max(c.x, m["x1"]) - min(c.x + c.w, m["x2"]))
            x_gap_ratio = x_gap / float(img_w)

            if y_overlap_ratio >= y_overlap_threshold and x_gap_ratio <= x_gap_threshold_ratio:
                m["x1"] = min(m["x1"], c.x)
                m["y1"] = min(m["y1"], c.y)
                m["x2"] = max(m["x2"], c.x + c.w)
                m["y2"] = max(m["y2"], c.y + c.h)
                m["confidences"].append(c.confidence)
                matched = True
                break

        if not matched:
            merged.append({
                "x1": c.x, "y1": c.y, "x2": c.x + c.w, "y2": c.y + c.h,
                "confidences": [c.confidence],
            })

    results: list[dict] = []
    for m in merged:
        results.append({
            "x": float(m["x1"]) / img_w,
            "y": float(m["y1"]) / img_h,
            "w": float(m["x2"] - m["x1"]) / img_w,
            "h": float(m["y2"] - m["y1"]) / img_h,
            "confidence": float(np.mean(m["confidences"])),
        })
    return results


def track_temporal_regions(
    frame_samples: list[FrameSample],
    min_occurrence: float = 0.20,
    padding_x: float = 0.02,
    padding_y: float = 0.015,
) -> list[HardsubRegion]:
    """Phân cụm không gian & theo dõi xuyên suốt các mốc thời gian để sinh `HardsubRegion`."""
    if not frame_samples:
        return []

    total_samples = len(frame_samples)
    frame_detections: list[tuple[float, list[dict]]] = []

    for s in frame_samples:
        if s.image is None:
            continue
        h, w = s.image.shape
        cands = detect_text_candidates_in_frame(s.image)
        merged = spatial_merge_candidates(cands, w, h)
        frame_detections.append((s.timestamp, merged))

    # Nhóm các vùng ổn định theo vị trí Y và chiều cao H
    clusters: list[list[tuple[float, dict]]] = []

    for ts, reg_list in frame_detections:
        for reg in reg_list:
            matched = False
            for cl in clusters:
                rep_reg = cl[0][1]
                # Cùng dải độ cao Y và chiều cao H
                if abs(reg["y"] - rep_reg["y"]) <= 0.06 and abs(reg["h"] - rep_reg["h"]) <= 0.06:
                    cl.append((ts, reg))
                    matched = True
                    break
            if not matched:
                clusters.append([(ts, reg)])

    hardsub_regions: list[HardsubRegion] = []

    for cl in clusters:
        occurrence_rate = len(cl) / float(total_samples)
        if occurrence_rate >= min_occurrence:
            timestamps = [item[0] for item in cl]
            regs = [item[1] for item in cl]

            t_start = min(timestamps)
            t_end = max(timestamps)

            # Lấy bao lồi không gian (Bounding box)
            min_x = min(r["x"] for r in regs)
            min_y = min(r["y"] for r in regs)
            max_x2 = max(r["x"] + r["w"] for r in regs)
            max_y2 = max(r["y"] + r["h"] for r in regs)
            mean_conf = float(np.mean([r["confidence"] for r in regs]))

            # Áp dụng padding an toàn và kẹp [0.0 .. 1.0]
            padded_x = max(0.0, min_x - padding_x)
            padded_y = max(0.0, min_y - padding_y)
            padded_w = min(1.0 - padded_x, (max_x2 - min_x) + 2 * padding_x)
            padded_h = min(1.0 - padded_y, (max_y2 - min_y) + 2 * padding_y)

            # Nếu xuất hiện trên 65% số frame thì coi như phụ đề phủ suốt video
            if occurrence_rate >= 0.65:
                t_start = 0.0
                t_end = 0.0

            region = HardsubRegion(
                x=round(padded_x, 4),
                y=round(padded_y, 4),
                width=round(padded_w, 4),
                height=round(padded_h, 4),
                start=round(t_start, 3),
                end=round(t_end, 3),
                confidence=round(mean_conf, 3),
            )
            hardsub_regions.append(region)

    return hardsub_regions


# --------------------------------------------------------------------------- #
# 4. Giao diện Chính & Giải quyết Xung đột (Public API & Conflict Resolution)
# --------------------------------------------------------------------------- #

def detect_hardsub_regions(
    video_path: str,
    sample_interval_s: float = 1.5,
    max_samples: int = 20,
    min_confidence: float = 0.50,
) -> list[dict]:
    """Hàm API chính: Tự động quét video và trả về danh sách `blur_regions` chuẩn của hệ thống."""
    try:
        samples = extract_video_frames(
            video_path,
            sample_interval_s=sample_interval_s,
            max_samples=max_samples,
        )
    except Exception as e:
        logger.warning(f"Lỗi khi lấy mẫu khung hình từ {video_path}: {e}")
        return []

    if not samples:
        return []

    detected = track_temporal_regions(samples)
    # Lọc theo min_confidence
    filtered = [r for r in detected if r.confidence >= min_confidence]

    out_regions = [r.to_blur_region() for r in filtered]
    logger.info(f"Auto Hardsub Masking: Phát hiện {len(out_regions)} dải phụ đề cứng.")
    return out_regions


def merge_blur_regions_with_manual(
    manual_regions: list[dict] | None,
    auto_regions: list[dict] | None,
) -> list[dict]:
    """Hợp nhất các vùng che thủ công và tự động, loại bỏ các vùng trùng lặp để tránh sinh filter thừa."""
    combined: list[dict] = list(manual_regions or [])
    for auto_r in (auto_regions or []):
        duplicate = False
        for man_r in combined:
            # Nếu 2 vùng có tâm và kích thước tương tự nhau
            center_x_diff = abs((auto_r["x"] + auto_r["w"]/2) - (man_r["x"] + man_r["w"]/2))
            center_y_diff = abs((auto_r["y"] + auto_r["h"]/2) - (man_r["y"] + man_r["h"]/2))
            if center_x_diff < 0.08 and center_y_diff < 0.06:
                duplicate = True
                break
        if not duplicate:
            combined.append(auto_r)
    return combined
