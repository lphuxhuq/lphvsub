"""Unit test cho padded_range — logic đệm VAD của worker Paraformer.

Pure function, không cần .venv-asr (numpy/sherpa chỉ import trong main()).
"""
import pytest

from autodub.speech.asr_paraformer_worker import padded_range

SR = 16000
PAD = int(0.3 * SR)  # 4800


def _range(seg_start, seg_end, prev_end=0, next_start=10 * SR, n=10 * SR,
           pad=PAD):
    return padded_range(seg_start, seg_end, prev_end, next_start, n, pad)


def test_basic_expansion():
    # Chunk 1s-2s trong file 10s → mở rộng đúng pad mỗi bên.
    s, e = _range(SR, 2 * SR)
    assert (s, e) == (SR - PAD, 2 * SR + PAD)


def test_clamp_to_file_start():
    s, e = _range(0, 8000)
    assert s == 0
    assert e == 8000 + PAD


def test_clamp_to_file_end():
    n = 10 * SR
    s, e = _range(n - 8000, n, next_start=n, n=n)
    assert s == n - 8000 - PAD
    assert e == n


def test_prev_end_blocks_left_pad():
    # Chunk trước kết thúc ở 20000 > biên pad trái → s bị đẩy lên prev_end.
    s, e = _range(SR, 2 * SR, prev_end=20000)
    assert s == 20000
    assert e == 2 * SR + PAD


def test_next_start_blocks_right_pad():
    # Chunk sau bắt đầu sớm (force-split 20s, gap = 0) → e không vượt vào
    # speech của chunk sau.
    s, e = _range(SR, 2 * SR, next_start=2 * SR)
    assert e == 2 * SR
    assert s == SR - PAD


def test_zero_pad_returns_exact_range():
    s, e = _range(SR, 2 * SR, pad=0)
    assert (s, e) == (SR, 2 * SR)


def test_tiny_chunk_still_valid():
    s, e = _range(100, 200, pad=0)
    assert s == 100 and e == 200


@pytest.mark.parametrize("seg_start,seg_end,prev_end,next_start,n,pad", [
    (0, 100, 0, 100, 100, 4800),           # chunk chiếm trọn file
    (50000, 50001, 49000, 60000, 60000, 0),  # chunk 1 sample, pad 0
    (0, 1, 0, 1, 1, 10),                   # file 1 sample
    (100, 200, 100, 200, 300, 4800),       # force-split hai bên gap 0
])
def test_invariants_always_hold(seg_start, seg_end, prev_end, next_start,
                               n, pad):
    s, e = padded_range(seg_start, seg_end, prev_end, next_start, n, pad)
    assert 0 <= s < e <= n
    assert s >= prev_end
    assert e <= max(next_start, s + 1)
    # Mở rộng mỗi bên không vượt pad
    assert s >= seg_start - pad
    assert e <= seg_end + pad


def test_no_chunk_speech_decoded_twice():
    """Bất biến cốt lõi: speech [start,end) của MỌI chunk chỉ nằm trong decode
    range của chính nó — chunk kề (dù padding bao nhiêu) không decode trùng,
    và cũng không bỏ sót audio nào của chunk này."""
    # Bao gồm cặp force-split (gap = 0) và các gap dài ngắn khác nhau.
    chunks = [(0, 320000), (320000, 352000), (500000, 640000),
              (656000, 700000)]
    n = 900000
    ranges = []
    for idx, (cs, ce) in enumerate(chunks):
        pe = chunks[idx - 1][1] if idx > 0 else 0
        ns = chunks[idx + 1][0] if idx + 1 < len(chunks) else n
        s, e = padded_range(cs, ce, pe, ns, n, PAD)
        ranges.append((s, e))
        # speech của chunk nằm trọn trong decode range của chính nó
        assert s <= cs and e >= ce
    for j, (s_j, e_j) in enumerate(ranges):
        for i, (ci_start, ci_end) in enumerate(chunks):
            if i == j:
                continue
            # decode của chunk j không chạm vào speech của chunk i
            assert e_j <= ci_start or s_j >= ci_end, \
                f"chunk {j} decode trùng speech chunk {i}"
