"""Per-segment TTS tempo fitting (voice-sync C2).

TTS engine render natural pace — clip VI thường dài hơn slot ZH 15-25%.
Module này quyết ĐỊNH tempo cho TỪNG clip (không còn một VOICE_SPEED toàn
cục) và render bằng atempo khi thật sự cần:

- ``actual ≤ target`` → giữ natural (tempo 1.0, không tốn ffmpeg).
- ``want = actual/target`` vượt ``max_speed`` → chặn tại ``max_speed``;
  phần thiếu còn lại là quyết định của scheduler (silence/overlap/flag) —
  fit không bao giờ ép quá giới hạn.
- Mặc định KHÔNG kéo dài (tempo < 1.0): giọng đọc nhân tạo bị méo. Bật
  ``allow_stretch`` (setting VOICE_FIT_STRETCH) để cho phép đọc chậm lại
  CHẶN TẠI ``min_speed`` — lấp bớt khoảng lặng cuối câu khi clip ngắn
  hơn hẳn khung thoại gốc.

Cache theo mtime + thời lượng kỳ vọng (copy pattern segments_timed của
timing.py): đổi tempo giữa hai lần chạy thì render lại đúng clip đó.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from autodub.utils import ensure_dir, setup_logging

logger = setup_logging("autodub.voicefit")

#: Nén/kéo dưới mức này không đáng một lệnh ffmpeg (giống timing.py).
MIN_WORTHWHILE_ATEMPO = 1.02
#: Sai lệch thời lượng chấp nhận khi kiểm tra cache (giây).
CACHE_TOLERANCE_S = 0.05


@dataclass
class FitResult:
    tempo_factor: float   # 1.0 = giữ natural
    out_path: str         # wav sau fit (== input khi tempo 1.0)
    rendered: bool        # có chạy atempo không


def _decide_tempo(actual: float, target: float, min_speed: float = 0.90,
                  max_speed: float = 1.15,
                  min_worthwhile: float = MIN_WORTHWHILE_ATEMPO,
                  allow_stretch: bool = False) -> float:
    """Tempo cho clip ``actual`` giây vào slot ``target`` giây.

    Thuần toán — scheduler gọi trực tiếp để quyết định placement mà không
    đụng file. Mặc định chỉ NÉN (≥ 1.0): ``min_speed`` là chặn dưới khi
    ``allow_stretch`` bật — hàm không bao giờ trả dưới ``min_speed``.
    """
    if actual <= 0 or target <= 0:
        return 1.0
    if actual <= target:
        if not allow_stretch:
            return 1.0
        want = actual / target          # < 1.0: cần đọc chậm lại cho vừa slot
        if want > 1.0 / min_worthwhile:  # chênh lệch nhỏ quá — bỏ qua
            return 1.0
        return float(max(min_speed, want))
    want = actual / target
    if want < min_worthwhile:
        return 1.0
    return float(min(max_speed, want))


def fit_voice_to_slot(
    wav_path: str,
    target_duration: float,
    out_dir: str,
    *,
    min_speed: float = 0.90,
    max_speed: float = 1.15,
) -> FitResult:
    """Fit clip TTS vào slot — trả path wav dùng được + tempo đã áp."""
    from autodub.media.audio import apply_atempo, wav_duration_s

    actual = wav_duration_s(wav_path) or 0.0
    tempo = _decide_tempo(actual, target_duration, min_speed, max_speed)
    if tempo <= 1.0:
        return FitResult(tempo_factor=1.0, out_path=wav_path, rendered=False)

    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, os.path.basename(wav_path))
    expected = actual / tempo
    # Resume-safe: đầu ra còn mới hơn nguồn VÀ đúng thời lượng kỳ vọng.
    if (os.path.exists(out_path) and os.path.getsize(out_path) > 0
            and os.path.getmtime(out_path) >= os.path.getmtime(wav_path)):
        have = wav_duration_s(out_path) or -1.0
        if abs(have - expected) < CACHE_TOLERANCE_S:
            return FitResult(tempo_factor=tempo, out_path=out_path,
                             rendered=False)
    apply_atempo(wav_path, out_path, tempo)
    return FitResult(tempo_factor=tempo, out_path=out_path, rendered=True)
