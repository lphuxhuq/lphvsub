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

# --- Trọng số scoring và ngưỡng quyết định Fusion (TASK-5) -----------------
W_ASR = 0.30
W_OCR = 0.20
W_ALIGN = 0.20
W_TEMPORAL = 0.15
W_COMPLETENESS = 0.15

FUSION_OVERRIDE_MIN = 0.75
ALIGN_MERGE_THRESHOLD = 0.80
ALIGN_HIGH_THRESHOLD = 0.85
ALIGN_LOW_THRESHOLD = 0.60
OCR_SCORE_MIN_EMPTY = 0.60



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


def fuse(
    segments: list[dict],
    ocr_segments: list[dict] | None = None,
    suspects: SuspectResult | None = None,
) -> tuple[list[dict], dict]:
    """Kết hợp (fuse) transcript ASR và OCR dựa trên chấm điểm và quy tắc ưu tiên.

    Bảo toàn bất biến:
    - Sắp xếp theo start, 0 <= start < end, duration >= 0.1s.
    - Không chồng chéo thời gian giữa các câu kề.
    - len(fused_segments) >= len(segments).
    - Không mutate input.

    Trả về: (fused_segments, report_dict)
    """
    if not ocr_segments:
        # Passthrough hoàn toàn nếu không có OCR
        copied = [dict(s) for s in segments]
        for idx, s in enumerate(copied):
            s["id"] = idx + 1
        report = {
            "version": 1,
            "total_fused": len(copied),
            "total_asr": len(segments),
            "total_ocr": 0,
            "decisions": [],
            "stats": {"passthrough": True},
        }
        return copied, report

    suspect_ids = set()
    if suspects and getattr(suspects, "suspect", None):
        for s in suspects.suspect:
            suspect_ids.add(s.get("id"))

    # Chuẩn hoá danh sách OCR segments
    parsed_ocr = []
    for ocr in ocr_segments:
        otext = str(ocr.get("text", "")).strip()
        ostart = float(ocr.get("start_time", ocr.get("start", 0.0)) or 0.0)
        oend = float(ocr.get("end_time", ocr.get("end", 0.0)) or 0.0)
        oconf = float(ocr.get("confidence", 0.9) or 0.9)
        if oend <= ostart:
            oend = ostart + 0.5
        parsed_ocr.append({
            "text": otext,
            "start": ostart,
            "end": oend,
            "confidence": oconf,
            "used": False,
        })

    decisions = []
    fused_raw = []

    # 1. Ghép từng câu ASR với OCR
    for seg in sorted(segments, key=lambda s: float(s.get("start", 0.0))):
        seg_id = seg.get("id")
        asr_text = str(seg.get("text", "")).strip()
        asr_start = float(seg.get("start", 0.0))
        asr_end = float(seg.get("end", asr_start + 0.5))

        # Tìm các đoạn OCR có giao thời gian với câu ASR này
        matched_ocrs = []
        for ocr in parsed_ocr:
            overlap = max(0.0, min(asr_end, ocr["end"]) - max(asr_start, ocr["start"]))
            if overlap >= 0.2 or (asr_end >= ocr["start"] and asr_start <= ocr["end"]):
                matched_ocrs.append(ocr)
                ocr["used"] = True

        if not matched_ocrs:
            # Không có OCR khớp
            fused_raw.append({
                "text": asr_text,
                "start": asr_start,
                "end": asr_end,
                "orig": seg,
            })
            decisions.append({
                "segment_id": seg_id,
                "decision": "keep_asr_no_ocr",
                "rule": 0,
                "scores": {"asr": 1.0, "ocr": 0.0, "align": 1.0, "temporal": 0.0, "completeness": 1.0, "final": 1.0},
                "asr_text": asr_text,
                "ocr_text": "",
                "final_text": asr_text,
                "start": asr_start,
                "end": asr_end,
            })
            continue

        # Gộp text OCR khớp
        matched_ocrs.sort(key=lambda o: o["start"])
        ocr_text = "".join(o["text"] for o in matched_ocrs)
        ocr_start = min(o["start"] for o in matched_ocrs)
        ocr_end = max(o["end"] for o in matched_ocrs)
        ocr_conf = sum(o["confidence"] for o in matched_ocrs) / len(matched_ocrs)

        # Tính toán Scoring components
        align_res = align_texts(asr_text, ocr_text)

        # ASR Score
        asr_score = 0.6 if asr_text else 0.0
        if seg_id not in suspect_ids:
            asr_score += 0.2
        dur = max(0.1, asr_end - asr_start)
        cjk_count = _cjk_len(asr_text)
        if 0.5 <= (cjk_count / dur) <= 6.0:
            asr_score += 0.2
        asr_score = min(1.0, asr_score)

        # OCR Score
        ocr_score = max(0.0, min(1.0, ocr_conf))

        # Alignment Score
        align_score = align_res.similarity

        # Temporal Score (IoU)
        inter = max(0.0, min(asr_end, ocr_end) - max(asr_start, ocr_start))
        union = max(1e-6, max(asr_end, ocr_end) - min(asr_start, ocr_start))
        temporal_score = max(0.0, min(1.0, inter / union))

        # Completeness Score
        norm_a = _normalize_for_align(asr_text)
        norm_o = _normalize_for_align(ocr_text)
        if (norm_a and norm_a in norm_o) or (norm_o and norm_o in norm_a):
            completeness_score = 1.0
        elif align_score >= 0.5:
            completeness_score = align_score
        else:
            completeness_score = 0.0

        final_score = (
            W_ASR * asr_score
            + W_OCR * ocr_score
            + W_ALIGN * align_score
            + W_TEMPORAL * temporal_score
            + W_COMPLETENESS * completeness_score
        )

        scores_dict = {
            "asr": round(asr_score, 3),
            "ocr": round(ocr_score, 3),
            "align": round(align_score, 3),
            "temporal": round(temporal_score, 3),
            "completeness": round(completeness_score, 3),
            "final": round(final_score, 3),
        }

        # Áp dụng 4 Quy tắc quyết định
        # Quy tắc 1: ASR rỗng + OCR có text >= 3 CJK chars và ocr_score >= 0.6
        if not norm_a and _cjk_len(ocr_text) >= 3 and ocr_score >= OCR_SCORE_MIN_EMPTY:
            final_text = ocr_text
            f_start = ocr_start
            f_end = ocr_end
            decision_name = "ocr_override_empty"
            rule_num = 1

        # Quy tắc 2: ALIGN >= 0.80 và OCR bổ sung prefix hoặc suffix
        elif (
            align_score >= ALIGN_MERGE_THRESHOLD
            and (len(align_res.added_prefix) >= 1 or len(align_res.added_suffix) >= 1)
        ):
            final_text = align_res.merged
            f_start = asr_start
            f_end = asr_end
            decision_name = "merged_prefix_suffix"
            rule_num = 2

        # Quy tắc 3: ALIGN >= 0.85 (tương đồng cao, OCR chỉ sai khác vài chữ) -> Giữ ASR
        elif align_score >= ALIGN_HIGH_THRESHOLD:
            final_text = asr_text
            f_start = asr_start
            f_end = asr_end
            decision_name = "keep_asr_high_similarity"
            rule_num = 3

        # Quy tắc 4: ALIGN < 0.60 hoặc final_score < 0.75 -> Giữ ASR + flag suspect
        elif align_score < ALIGN_LOW_THRESHOLD or final_score < FUSION_OVERRIDE_MIN:
            final_text = asr_text
            f_start = asr_start
            f_end = asr_end
            decision_name = "keep_asr_fallback"
            rule_num = 4

        else:
            # Mặc định giữ ASR
            final_text = asr_text
            f_start = asr_start
            f_end = asr_end
            decision_name = "keep_asr"
            rule_num = 0

        fused_raw.append({
            "text": final_text,
            "start": f_start,
            "end": f_end,
            "orig": seg,
        })
        decisions.append({
            "segment_id": seg_id,
            "decision": decision_name,
            "rule": rule_num,
            "scores": scores_dict,
            "asr_text": asr_text,
            "ocr_text": ocr_text,
            "final_text": final_text,
            "start": f_start,
            "end": f_end,
        })

    # 2. Xử lý các đoạn OCR độc lập (không trùng với câu ASR nào) — Quy tắc 1 OCR Standalone
    for ocr in parsed_ocr:
        if not ocr["used"] and _cjk_len(ocr["text"]) >= 3 and ocr["confidence"] >= OCR_SCORE_MIN_EMPTY:
            fused_raw.append({
                "text": ocr["text"],
                "start": ocr["start"],
                "end": ocr["end"],
                "orig": None,
            })
            decisions.append({
                "segment_id": None,
                "decision": "ocr_standalone",
                "rule": 1,
                "scores": {"asr": 0.0, "ocr": round(ocr["confidence"], 3), "align": 0.0, "temporal": 0.0, "completeness": 1.0, "final": 0.8},
                "asr_text": "",
                "ocr_text": ocr["text"],
                "final_text": ocr["text"],
                "start": ocr["start"],
                "end": ocr["end"],
            })

    # 3. Sắp xếp và đảm bảo tính bất biến thời gian
    fused_raw.sort(key=lambda x: float(x["start"]))

    fused_segments = []
    last_end = 0.0
    for idx, item in enumerate(fused_raw):
        s_start = max(0.0, float(item["start"]))
        s_end = max(s_start + 0.1, float(item["end"]))

        # Chặn chồng chéo với câu liền trước
        if s_start < last_end:
            s_start = last_end
            s_end = max(s_end, s_start + 0.1)

        seg_dict = dict(item["orig"]) if item["orig"] else {}
        seg_dict["id"] = idx + 1
        seg_dict["start"] = round(s_start, 3)
        seg_dict["end"] = round(s_end, 3)
        seg_dict["text"] = str(item["text"])

        fused_segments.append(seg_dict)
        last_end = seg_dict["end"]

    report = {
        "version": 1,
        "total_fused": len(fused_segments),
        "total_asr": len(segments),
        "total_ocr": len(ocr_segments),
        "decisions": decisions,
        "stats": {
            "merged_count": sum(1 for d in decisions if d["decision"] == "merged_prefix_suffix"),
            "ocr_added_count": sum(1 for d in decisions if d["decision"] in ("ocr_override_empty", "ocr_standalone")),
            "asr_kept_count": sum(1 for d in decisions if "keep_asr" in d["decision"]),
        },
    }

    return fused_segments, report

