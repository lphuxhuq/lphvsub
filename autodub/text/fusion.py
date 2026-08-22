"""Suspect detection & ASR↔OCR fusion cho transcript tiếng Trung.

Ba lớp (theo design asr-accuracy-boost):
1. ``detect_suspect_segments`` — gắn cờ những câu ASR có dấu hiệu sai/thiếu
   (chunk rỗng, char-rate bất thường, gap bất thường, OCR không khớp ASR).
2. ``align_texts`` — so khớp mức ký tự giữa text ASR và OCR, phát hiện phần
   OCR bổ sung đầu/cuối câu (TASK-4).
3. ``fuse`` — quyết định từng segment bằng scoring tổng hợp, không đè một
   engine (TASK-5).

Module thuần stdlib, không mutate input — mọi thay đổi trả về bản copy.
"""
from __future__ import annotations

import difflib
import statistics
from dataclasses import dataclass, field

from autodub.utils import setup_logging

logger = setup_logging("autodub.fusion")

# --- Hằng số heuristic — named để chỉnh không đụng logic ------------------
CHAR_RATE_MIN_RATIO = 0.4      # chậm hơn 0.4× median → text nghi thiếu
CHAR_RATE_MAX_RATIO = 3.0      # nhanh hơn 3× median → duration nghi sai
CHAR_RATE_MIN_SAMPLES = 5      # dưới ngưỡng này median chưa đáng tin
CHAR_RATE_MIN_DURATION_S = 0.5  # câu quá ngắn không tính vào median
GAP_ANOMALY_MIN_S = 1.5        # khoảng lặng tối thiểu để coi là bất thường
GAP_ANOMALY_MEDIAN_MULT = 3.0  # ... hoặc 3× gap trung vị (adaptive)
OCR_MATCH_MAX_DIST_S = 3.0     # OCR lệch bao xa thì còn "gần" một câu ASR
EMPTY_CHUNK_COVER_RATIO = 0.5  # empty chunk bị ASR segment phủ ≥50% → OK

REASON_EMPTY_CHUNK = "empty_speech_chunk"
REASON_TEXT_TOO_SHORT = "text_too_short_for_duration"
REASON_GAP_ANOMALY = "gap_anomaly"
REASON_OCR_NO_ASR = "ocr_no_asr_match"


def _normalize_for_align(text: str) -> str:
    """Chuẩn hoá để so khớp: bỏ punctuation/khoảng trắng, giữ CJK + alnum.
    (Riêng với align — normalize_ocr_text của OCR là chuẩn hoá xuất khẩu.)"""
    out = []
    for ch in str(text or ""):
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A \
                or 0xFF41 <= code <= 0xFF5A:
            ch = chr(code - 0xFEE0)
        if "\u4e00" <= ch <= "\u9fff" or ch.isalnum():
            out.append(ch)
    return "".join(out)


@dataclass
class Alignment:
    """Kết quả so khớp text ASR ↔ OCR mức ký tự (đã normalize)."""
    similarity: float = 0.0          # SequenceMatcher.ratio() trên normalized
    merged: str = ""                 # text merge an toàn (không duplicate)
    added_prefix: str = ""           # phần OCR có mà ASR thiếu (đầu câu)
    added_suffix: str = ""           # phần OCR có mà ASR thiếu (cuối câu)


def align_texts(asr_text: str, ocr_text: str) -> Alignment:
    """So khớp ASR và OCR mức ký tự — phát hiện OCR bổ sung đầu/cuối câu.

    Chỉ merge khi chuỗi ASR (đã normalize) LÀ substring của OCR: khi đó
    phần thêm được tách chính xác thành prefix/suffix — không có ký tự chung
    nào bị lặp. Các trường hợp còn lại (khác nhau ở giữa) không tự ghép,
    merged ưu tiên giữ ASR; similarity thấp sẽ chặn ở rule fusion.
    """
    a = _normalize_for_align(asr_text)
    o = _normalize_for_align(ocr_text)
    if not a and not o:
        return Alignment(similarity=1.0, merged="")
    if not a:
        return Alignment(similarity=0.0, merged=o, added_suffix=o)
    if not o:
        return Alignment(similarity=0.0, merged=a)

    similarity = difflib.SequenceMatcher(None, a, o).ratio()
    if a == o:
        return Alignment(similarity=similarity, merged=a)
    if a in o:
        i = o.index(a)
        return Alignment(similarity=similarity, merged=o,
                         added_prefix=o[:i], added_suffix=o[i + len(a):])
    return Alignment(similarity=similarity, merged=a)


def _cjk_len(text: str) -> int:
    """Số ký tự CJK (bỏ punctuation/khoảng trắng/số Latin)."""
    return sum(1 for ch in str(text or "")
               if "\u4e00" <= ch <= "\u9fff")


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


@dataclass
class SuspectResult:
    """Kết quả chia transcript: normal (yên tâm) và suspect (cần soi)."""
    normal: list[dict] = field(default_factory=list)
    suspect: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def detect_suspect_segments(
    segments: list[dict],
    empty_chunks: list[dict] | None = None,
    ocr_segments: list[dict] | None = None,
) -> SuspectResult:
    """Gắn cờ nghi vấn cho các câu ASR — input KHÔNG bị mutate.

    ``segments``: list[{"id","text","start","end",...}] (giây).
    ``empty_chunks``: [{"start","end"}] — khoảng VAD có tiếng nhưng decode
    rỗng (từ worker Paraformer, có thể vắng mặt khi engine là Whisper).
    ``ocr_segments``: [{"text","start_time"/"start","end_time"/"end",
    "confidence"}] — kết quả OCR (lần gọi thứ hai, sau khi OCR xong).
    """
    flagged: dict[int, list[str]] = {}
    stats: dict[str, int | float] = {"total": len(segments)}
    ordered = sorted(segments, key=lambda s: float(s.get("start", 0.0)))

    def _flag(idx: int, reason: str) -> None:
        if idx < 0 or idx >= len(ordered):
            return
        flagged.setdefault(idx, [])
        if reason not in flagged[idx]:
            flagged[idx].append(reason)

    # 1) Char-rate bất thường (adaptive theo median của chính transcript).
    rates = [(_cjk_len(s.get("text")) /
              max(1e-6, float(s.get("end", 0)) - float(s.get("start", 0))))
             for s in ordered
             if (float(s.get("end", 0)) - float(s.get("start", 0))
                 >= CHAR_RATE_MIN_DURATION_S)]
    med_rate = _median(rates) if len(rates) >= CHAR_RATE_MIN_SAMPLES else None
    stats["median_char_rate"] = round(med_rate, 3) if med_rate else None
    if med_rate:
        for i, seg in enumerate(ordered):
            dur = float(seg.get("end", 0)) - float(seg.get("start", 0))
            if dur < CHAR_RATE_MIN_DURATION_S:
                continue
            rate = _cjk_len(seg.get("text")) / max(1e-6, dur)
            if rate < med_rate * CHAR_RATE_MIN_RATIO:
                _flag(i, REASON_TEXT_TOO_SHORT)
            elif rate > med_rate * CHAR_RATE_MAX_RATIO:
                _flag(i, REASON_TEXT_TOO_SHORT)

    # 2) Gap bất thường giữa hai câu kề (adaptive × median gap).
    gaps = [float(ordered[i + 1]["start"]) - float(ordered[i]["end"])
            for i in range(len(ordered) - 1)]
    med_gap = _median([g for g in gaps if g > 0])
    gap_threshold = max(GAP_ANOMALY_MIN_S,
                        (med_gap or 0.0) * GAP_ANOMALY_MEDIAN_MULT)
    stats["gap_threshold_s"] = round(gap_threshold, 3)
    for i, gap in enumerate(gaps):
        if gap > gap_threshold:
            _flag(i, REASON_GAP_ANOMALY)
            _flag(i + 1, REASON_GAP_ANOMALY)

    # 3) Chunk có tiếng nhưng decode rỗng mà không câu nào phủ lấy.
    for chunk in (empty_chunks or []):
        cs = float(chunk.get("start", 0.0))
        ce = float(chunk.get("end", 0.0))
        span = max(1e-6, ce - cs)
        covered = max(
            (max(0.0, min(ce, float(s.get("end", 0)))
                 - max(cs, float(s.get("start", 0)))) for s in ordered),
            default=0.0,
        ) / span
        if covered >= EMPTY_CHUNK_COVER_RATIO:
            continue
        nearest = min(
            range(len(ordered)),
            key=lambda i: min(abs(float(ordered[i].get("start", 0)) - ce),
                              abs(float(ordered[i].get("end", 0)) - cs)),
            default=-1,
        )
        _flag(nearest, REASON_EMPTY_CHUNK)

    # 4) OCR có text nhưng không khớp câu ASR nào (lần gọi sau khi có OCR).
    ocr_unmatched = 0
    for ocr in (ocr_segments or []):
        if _cjk_len(ocr.get("text")) < 3:
            continue
        os_ = float(ocr.get("start_time", ocr.get("start", 0.0)) or 0.0)
        oe_ = float(ocr.get("end_time", ocr.get("end", 0.0)) or 0.0)
        overlap = max(
            (max(0.0, min(oe_, float(s.get("end", 0)))
                 - max(os_, float(s.get("start", 0)))) for s in ordered),
            default=0.0,
        )
        if overlap >= 0.2:
            continue
        ocr_unmatched += 1
        mid = (os_ + oe_) / 2
        nearest = min(
            range(len(ordered)),
            key=lambda i: abs((float(ordered[i].get("start", 0))
                               + float(ordered[i].get("end", 0))) / 2 - mid),
            default=-1,
        )
        if nearest >= 0 and abs(
                (float(ordered[nearest].get("start", 0))
                 + float(ordered[nearest].get("end", 0))) / 2 - mid
        ) <= OCR_MATCH_MAX_DIST_S:
            _flag(nearest, REASON_OCR_NO_ASR)
    stats["ocr_unmatched"] = ocr_unmatched

    # Partition: suspect (kèm suspect_reasons) vs normal — dict copy.
    normal: list[dict] = []
    suspect: list[dict] = []
    for i, seg in enumerate(ordered):
        out = dict(seg)
        if i in flagged:
            out["suspect_reasons"] = flagged[i]
            suspect.append(out)
        else:
            normal.append(out)
    stats["suspect"] = len(suspect)
    res = SuspectResult(normal=normal, suspect=suspect, stats=stats)
    if suspect:
        logger.info("Suspect detection: %d/%d câu có dấu hiệu cần soi "
                    "(%s)", len(suspect), len(ordered),
                    ", ".join(f"{k}={v}" for k, v in stats.items()
                              if k.endswith(("chunk", "duration", "anomaly",
                                             "asr_match"))))
    return res
