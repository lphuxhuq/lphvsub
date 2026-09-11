"""Kiểm thử hồi quy độ chính xác mốc thời gian (Accuracy Regression & Golden Dataset).

So sánh sai số giữa Greedy vs Beam 2 và Acoustic vs Ground Truth để bảo đảm
tất cả sai số nằm trong ngưỡng cho phép (MAE <= 80ms, p95 <= 120ms).
"""

import numpy as np

from autodub.speech.acoustic_align import analyze_acoustic_alignment
from autodub.speech.align import _map_words, validate_alignment


def test_golden_dataset_word_mapping_accuracy():
    """Kiểm tra độ chính xác nội suy mốc từ trên golden dataset chuẩn."""
    # Giả lập ground truth phát âm 5 từ trong 2.5s
    ground_truth = [
        ("hôm", 0.10, 0.45),
        ("nay", 0.45, 0.85),
        ("trời", 0.85, 1.30),
        ("rất", 1.30, 1.65),
        ("đẹp", 1.65, 2.10),
    ]
    text_words = [w for w, _, _ in ground_truth]

    # Mô phỏng mốc ASR có nhiễu nhẹ (jitter +/- 20ms)
    noisy_asr = [
        ("hôm", 0.12, 0.43),
        ("nay", 0.47, 0.83),
        ("trời", 0.86, 1.32),
        ("rất", 1.28, 1.67),
        ("đẹp", 1.63, 2.08),
    ]

    mapped = _map_words(text_words, noisy_asr, clip_start=10.0, clip_dur=2.5)
    assert mapped is not None
    assert validate_alignment(mapped, text_words, clip_start=10.0, clip_dur=2.5)

    errors = []
    for (gw, gs, ge), (mw, ms, me) in zip(ground_truth, mapped):
        assert gw == mw
        errors.append(abs((10.0 + gs) - ms))
        errors.append(abs((10.0 + ge) - me))

    mae = float(np.mean(errors))
    median_err = float(np.median(errors))
    p95_err = float(np.percentile(errors, 95))
    max_err = float(np.max(errors))

    print(
        f"\n[Golden Mapping Metrics] MAE: {mae * 1000:.1f}ms | Median: {median_err * 1000:.1f}ms | p95: {p95_err * 1000:.1f}ms | Max: {max_err * 1000:.1f}ms"
    )

    assert mae <= 0.05  # MAE <= 50ms
    assert p95_err <= 0.08  # p95 <= 80ms
    assert max_err <= 0.10  # Max error <= 100ms


def test_acoustic_alignment_accuracy_metric(tmp_path):
    """Kiểm tra độ chính xác phát hiện biên âm thanh của Acoustic Fast-Path."""
    from tests.test_acoustic_confidence import _write_burst_tone

    # Clip 0.5s, voice burst thật từ 0.10s đến 0.40s
    wav_file = tmp_path / "golden_burst.wav"
    _write_burst_tone(str(wav_file), total_dur=0.50, burst_dur=0.30)

    res = analyze_acoustic_alignment("vâng", str(wav_file), clip_start=0.0, clip_dur=0.50)
    assert res.method == "acoustic_high_conf"
    assert len(res.words) == 1

    word, t0, t1 = res.words[0]
    expected_t0 = 0.10
    expected_t1 = 0.40

    err_t0 = abs(t0 - expected_t0)
    err_t1 = abs(t1 - expected_t1)

    print(f"\n[Acoustic Precision] err_t0: {err_t0 * 1000:.1f}ms | err_t1: {err_t1 * 1000:.1f}ms")
    assert err_t0 <= 0.06  # Sai số biên đầu <= 60ms
    assert err_t1 <= 0.06  # Sai số biên đuôi <= 60ms
