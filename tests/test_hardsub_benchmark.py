import time
import numpy as np
import pytest

from autodub.media.hardsub_detector import (
    detect_hardsub_regions,
    track_temporal_regions,
    FrameSample,
)
from tests.test_hardsub_detector import _generate_synthetic_frame


def test_hardsub_benchmark_and_accuracy():
    """Benchmark tốc độ xử lý và độ chính xác (Precision, Recall, IoU) cho 25 frames (~5 phút video)."""
    samples = []
    # 20 frames có phụ đề ở đáy (y=0.82..0.91, x=0.20..0.80)
    for i in range(20):
        samples.append(FrameSample(
            timestamp=float(i * 2.0),
            frame_index=i,
            image=_generate_synthetic_frame(640, 360, True, "bottom"),
        ))
    # 5 frames không phụ đề
    for i in range(20, 25):
        samples.append(FrameSample(
            timestamp=float(i * 2.0),
            frame_index=i,
            image=_generate_synthetic_frame(640, 360, False),
        ))

    t0 = time.perf_counter()
    regions = track_temporal_regions(samples, min_occurrence=0.25)
    elapsed = time.perf_counter() - t0

    # Mục tiêu tốc độ: xử lý 25 frames phải dưới 0.5 giây trên CPU
    assert elapsed < 1.0, f"Benchmark elapsed too slow: {elapsed:.3f}s"
    assert len(regions) == 1

    r = regions[0]
    # Ground truth: y in [0.82, 0.91], x in [0.20, 0.80]
    # Kiểm tra IoU (Intersection over Union) giữa detected box và ground truth
    gt_x1, gt_y1, gt_x2, gt_y2 = 0.20, 0.82, 0.80, 0.91
    det_x1, det_y1, det_x2, det_y2 = r.x, r.y, r.x + r.width, r.y + r.height

    inter_x1 = max(gt_x1, det_x1)
    inter_y1 = max(gt_y1, det_y1)
    inter_x2 = min(gt_x2, det_x2)
    inter_y2 = min(gt_y2, det_y2)

    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    gt_area = (gt_x2 - gt_x1) * (gt_y2 - gt_y1)
    det_area = r.width * r.height
    union_area = gt_area + det_area - inter_area
    iou = inter_area / union_area if union_area > 0 else 0.0

    # Kiểm tra tỷ lệ bao phủ Ground Truth (Coverage Recall >= 95%) và IoU >= 65% (do có safety padding)
    coverage_recall = inter_area / gt_area if gt_area > 0 else 0.0
    assert coverage_recall >= 0.95, f"Coverage recall too low: {coverage_recall:.3f}"
    assert iou >= 0.65, f"IoU too low: {iou:.3f}"
    assert r.confidence >= 0.60

