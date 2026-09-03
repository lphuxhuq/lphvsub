import random
import pytest
from autodub.text.fusion import fuse


def test_fusion_invariants_property_test():
    # Test ngẫu nhiên với seed cố định
    random.seed(42)

    for _ in range(50):
        num_asr = random.randint(1, 10)
        num_ocr = random.randint(0, 5)

        asr_segs = []
        cur_t = 0.5
        for i in range(num_asr):
            dur = random.uniform(0.5, 3.0)
            asr_segs.append({
                "id": i + 1,
                "start": round(cur_t, 3),
                "end": round(cur_t + dur, 3),
                "text": f"语音文本{i}"
            })
            cur_t += dur + random.uniform(0.1, 1.0)

        ocr_segs = []
        for j in range(num_ocr):
            ostart = random.uniform(0.0, cur_t)
            odur = random.uniform(0.5, 2.0)
            ocr_segs.append({
                "start_time": round(ostart, 3),
                "end_time": round(ostart + odur, 3),
                "text": f"字幕文字{j}",
                "confidence": round(random.uniform(0.5, 0.99), 2)
            })

        fused, report = fuse(asr_segs, ocr_segs)

        # Invariant 1: Số lượng segment kết quả >= số lượng ASR gốc
        assert len(fused) >= len(asr_segs)

        # Invariant 2: Đã sắp xếp theo start và start < end
        for idx, seg in enumerate(fused):
            assert seg["id"] == idx + 1
            assert float(seg["start"]) >= 0.0
            assert float(seg["end"]) > float(seg["start"])
            assert float(seg["end"]) - float(seg["start"]) >= 0.099  # ít nhất 0.1s

            # Invariant 3: Không chồng lấn ngược với segment trước
            if idx > 0:
                prev = fused[idx - 1]
                assert float(seg["start"]) >= float(prev["start"])
                assert float(seg["start"]) >= float(prev["end"]) - 1e-4

        # Invariant 4: Report hợp lệ
        assert report["version"] == 1
        assert report["total_fused"] == len(fused)
