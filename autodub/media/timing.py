"""Voice-sync scheduler — đặt dub TIỆN speech thật, không drift tích luỹ.

Chiến lược (voice-sync design C3, thay cho shift→compress→overlap cũ):

1. **``dub_start ≈ speech_start``** (refined; fallback ``start``): drift
   start mỗi câu bị chặn bởi ``timing_max_start_drift_s`` (0.15s — ngưỡng
   lip-sync cảm nhận, thay cho 1.5s của scheduler cũ). Mỗi câu đối chiếu
   timeline NGUỒN nên drift không bao giờ cộng dồn qua các câu.
2. **Slot = speech_duration** (fallback ``duration``/``end-start``; câu
   không biết slot → giữ natural, không fit).
3. **Silence-aware**: clip dài hơn slot được mượn khoảng lặng TRƯỚC câu
   kế (không ăn vào speech của câu kế) — câu cuối được đuôi 1s.
4. **Per-segment tempo** qua ``_decide_tempo`` (media/voice_timing.py):
   trần ``voice_fit_max_speed`` (1.15), KHÔNG stretch. Phần thiếu sau khi
   đã chặn trần được chấp nhận rất nhỏ (≤150ms) hoặc flag
   ``needs_compaction`` — KHÔNG ép quá giới hạn, KHÔNG shift dây chuyền.

Timestamp emit: mutate ``start/end`` = dub (một nguồn sự thật cho SRT/
merge) + gán field ``dub_*``, ``tempo_factor``, ``timing_adjustment``;
``duration`` giữ nguyên = thời lượng câu GỐC cho report/timing_guide.
"""
from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from autodub.utils import ensure_dir, seg_wav_path, setup_logging

logger = setup_logging("autodub.timing")

# Nén dưới mức này không bõ một lệnh ffmpeg (chia sẻ với voice_timing).
_MIN_WORTHWHILE_ATEMPO = 1.02
#: Đuôi silence tối đa mượn cho câu CUỐI video (giây).
TAIL_SILENCE_S = 1.0
#: Phần thừa sau khi tempo đã chặn trần, nhỏ hơn đây thì chấp nhận (giây).
ALLOWED_RESIDUAL_S = 0.150
#: Slot tối thiểu (giây) — chống slot 0 làm tempo vô nghĩa.
MIN_SLOT_S = 0.3


@dataclass
class TimingReport:
    """Kết quả đặt timeline — nguồn cho quality_report.json."""
    segments_total: int = 0
    segments_shifted: int = 0        # câu bị dồn trễ > 50 ms
    max_shift_s: float = 0.0
    segments_compressed: int = 0     # câu phải nén atempo (bất khả kháng)
    segments_stretched: int = 0      # câu được kéo dài atempo (VOICE_FIT_STRETCH)
    segments_overlapped: int = 0     # câu vẫn còn chồng sau mọi biện pháp
    total_overlap_s: float = 0.0
    details: list[dict] = field(default_factory=list)  # per-segment issues

    def to_dict(self) -> dict:
        return {
            "segments_total": self.segments_total,
            "segments_shifted": self.segments_shifted,
            "max_shift_s": round(self.max_shift_s, 3),
            "segments_compressed": self.segments_compressed,
            "segments_stretched": self.segments_stretched,
            "segments_overlapped": self.segments_overlapped,
            "total_overlap_s": round(self.total_overlap_s, 3),
            "details": self.details,
        }


def _resolve_slot(seg: dict) -> float | None:
    """Slot mục tiêu của một câu: speech_duration > duration > end-start.

    ``None`` khi không có thông tin gì (transcript legacy chỉ có start) —
    caller bỏ qua fitting, giữ natural cho câu đó.
    """
    if seg.get("speech_duration"):
        slot = float(seg["speech_duration"])
    elif seg.get("duration"):
        slot = float(seg["duration"])
    else:
        end, start = float(seg.get("end", 0) or 0), float(seg.get("start", 0) or 0)
        slot = end - start if end > start else None
    return max(MIN_SLOT_S, slot) if slot is not None else None


def plan_voice_placements(
    segments: list[dict],
    durations: list[float | None],
    *,
    max_start_drift_s: float = 0.15,
    min_gap_s: float = 0.12,
    min_speed: float = 0.90,
    max_speed: float = 1.15,
    allow_stretch: bool = False,
    pre_roll_s: float = 0.0,
    scene_cuts: list[float] | None = None,
) -> tuple[list[dict], TimingReport]:
    """Tính vị trí đặt + tempo từng clip — THUẦN TOÁN, không đụng file.

    Trả ``(placements, report)`` — ``placements[i]`` gồm ``{"start",
    "atempo", "drift", "adjustment", "reason", "slot", "available"}``.
    ``allow_stretch`` (VOICE_FIT_STRETCH) cho phép clip NGẮN hơn slot được
    kéo dài (atempo < 1.0, chặn ``min_speed``) lấp bớt khoảng lặng cuối câu.
    ``pre_roll_s`` (DUB_PRE_ROLL_MS) đẩy onset giọng Việt sớm hơn
    ``speech_start`` bấy nhiêu (mặc định 0 — dubbing thực tế bật 0…80ms).
    ``scene_cuts`` danh sách điểm chuyển cảnh để chặn tràn giọng sang cảnh khác.
    Render nằm ở :func:`apply_soft_timing`.
    """
    from autodub.media.voice_timing import _decide_tempo
    from autodub.media.scene_detector import (find_next_scene_boundary,
                                              find_prev_scene_boundary,
                                              snap_to_scene_boundaries)

    rep = TimingReport(segments_total=len(segments))
    placements: list[dict] = []
    prev_end = float("-inf")

    def _natural(seg: dict) -> float:
        raw_s = float(seg.get("speech_start", seg.get("start", 0.0)) or 0.0)
        raw_e = float(seg.get("speech_end", seg.get("end", raw_s)) or raw_s)
        if scene_cuts:
            snap_s, _ = snap_to_scene_boundaries(raw_s, raw_e, scene_cuts)
        else:
            snap_s = raw_s

        t_cand = snap_s - pre_roll_s
        if pre_roll_s > 0 and scene_cuts:
            prev_cut = find_prev_scene_boundary(snap_s, scene_cuts)
            if prev_cut is not None and t_cand < prev_cut:
                t_cand = max(t_cand, prev_cut + 0.02)
        return max(0.0, t_cand)

    for i, seg in enumerate(segments):
        natural = _natural(seg)
        dur = durations[i] or 0.0

        # 1) Onset: giữ mốc speech, chỉ trượt khi clip trước còn đang nói
        #    — và không trượt quá max_start_drift_s (tham chiếu nguồn,
        #    drift không cộng dồn).
        t = max(natural, prev_end + min_gap_s) if dur > 0 else natural
        t = min(t, natural + max_start_drift_s)
        drift = t - natural
        if drift > 0.05:
            rep.segments_shifted += 1
            rep.max_shift_s = max(rep.max_shift_s, drift)

        # 2) Slot + silence-aware availability: mượn khoảng lặng TRƯỚC
        #    speech của câu kế, không bao giờ ăn vào speech kế.
        slot = _resolve_slot(seg)
        next_natural = _natural(segments[i + 1]) if i + 1 < len(segments) \
            else None
        if next_natural is not None:
            usable_end = next_natural - min_gap_s
        else:
            usable_end = t + (slot if slot else TAIL_SILENCE_S) \
                + TAIL_SILENCE_S

        # Giới hạn bởi điểm chuyển cảnh video kế tiếp (Scene Drift Guard)
        if scene_cuts:
            next_scene = find_next_scene_boundary(t, scene_cuts)
            if next_scene is not None:
                usable_end = min(usable_end, next_scene - 0.02)

        available = max(slot, usable_end - t) if slot is not None else None

        # 3) Per-segment tempo. Clip TRÀN slot → nén theo ``available``
        #    (mượn khoảng lặng trước câu kế). Clip NGẮN hơn slot → chỉ
        #    stretch tới SLOT (không lấn khoảng lặng trước câu kế) và chỉ
        #    khi VOICE_FIT_STRETCH bật.
        tempo = 1.0
        adjustment = "none"
        reason = ""
        if available is not None and dur > 0:
            if dur > available:
                tempo = _decide_tempo(dur, available, min_speed, max_speed,
                                      _MIN_WORTHWHILE_ATEMPO)
            elif allow_stretch and slot is not None and slot > dur:
                # Stretch chỉ hướng tới SLOT (không lấn khoảng lặng trước
                # câu kế) và chỉ khi VOICE_FIT_STRETCH bật.
                tempo = _decide_tempo(dur, slot, min_speed, max_speed,
                                      _MIN_WORTHWHILE_ATEMPO,
                                      allow_stretch=True)
            else:
                tempo = 1.0
            final = dur / tempo if tempo != 1.0 else dur
            residual = (t + final) - usable_end
            if dur <= slot:
                adjustment = "stretch" if tempo < 1.0 else "none"
            elif tempo > 1.0:
                if residual > ALLOWED_RESIDUAL_S:
                    adjustment = "overlap"
                    reason = "needs_compaction"
                elif available > slot + 1e-9:
                    adjustment = "silence+tempo"
                else:
                    adjustment = "tempo"
            else:
                # tempo 1.0 mà vẫn tràn → lấp đầy bằng silence thôi.
                adjustment = "silence" if residual <= 0 else (
                    "overlap" if residual <= ALLOWED_RESIDUAL_S
                    else "silence+overlap")
                if residual > ALLOWED_RESIDUAL_S:
                    reason = "needs_compaction"
        if tempo > 1.0:
            rep.segments_compressed += 1
        elif tempo < 1.0:
            rep.segments_stretched += 1

        final_dur = dur / tempo if tempo != 1.0 else dur

        # Chồng còn lại với clip trước (sau khi đã giới hạn drift onset).
        overlap_prev = max(0.0, (prev_end + min_gap_s) - t) if dur > 0 else 0.0

        issue: dict = {}
        if overlap_prev > 0.01:
            rep.segments_overlapped += 1
            rep.total_overlap_s += overlap_prev
            issue["overlap_prev_s"] = round(overlap_prev, 3)
        if drift > 0.05:
            issue["shift_s"] = round(drift, 3)
        if tempo != 1.0:
            issue["atempo"] = round(tempo, 3)
        if issue:
            issue["id"] = seg.get("id")
            rep.details.append(issue)

        placements.append({
            "start": round(t, 3),
            "atempo": round(tempo, 4),
            "drift": round(drift, 3),
            "adjustment": adjustment,
            "reason": reason,
            "slot": round(slot, 3) if slot is not None else None,
            "available": round(available, 3) if available is not None else None,
        })
        if dur > 0:
            prev_end = max(prev_end, t + final_dur)

    return placements, rep


def apply_soft_timing(
    segments: list[dict],
    src_dir: str,
    dst_dir: str,
    settings,
    max_workers: int = 4,
    scene_cuts: list[float] | None = None,
) -> tuple[str, TimingReport]:
    """Đặt lại timeline cho các clip trong ``src_dir`` (mutate ``segments``).

    - Mọi clip đều được tham chiếu từ MỘT thư mục kết quả (merge đọc một
      chỗ): clip không nén được copy sang, clip nén chạy atempo.
    - ``segments`` được cập nhật ``start``/``end``/``duration`` theo vị trí
      đặt thật — SRT và bước merge dùng đúng timeline người nghe sẽ nghe.
    - Trả về ``(dir_dùng_để_merge, report)``. Khi không có gì phải làm
      (mọi câu nằm gọn trong chỗ của nó) trả về ``(src_dir, report)`` —
      không copy vô ích.
    """
    from autodub.media.audio import wav_duration_s
    from autodub.media.voice_stretch import apply_formant_preserved_stretch
    from autodub.speech.tts_trimmer import trim_tts_silence

    # 1) Cắt tỉa khoảng lặng thừa đầu/đuôi file TTS nếu được bật
    if getattr(settings, "voice_vad_trim_enabled", True):
        for s in segments:
            wav_file = seg_wav_path(src_dir, s["id"])
            if os.path.exists(wav_file):
                trim_tts_silence(wav_file, wav_file)

    durations = [wav_duration_s(seg_wav_path(src_dir, s["id"]))
                 for s in segments]
    placements, report = plan_voice_placements(
        segments, durations,
        max_start_drift_s=settings.timing_max_start_drift_s,
        min_gap_s=settings.timing_min_gap_s,
        min_speed=settings.voice_fit_min_speed,
        max_speed=settings.voice_fit_max_speed,
        allow_stretch=bool(getattr(settings, "voice_fit_stretch", False)),
        pre_roll_s=(getattr(settings, "dub_pre_roll_ms", 0) or 0) / 1000.0,
        scene_cuts=scene_cuts,
    )

    needs_render = any(p["atempo"] != 1.0 for p in placements)
    out_dir = src_dir
    if needs_render:
        out_dir = ensure_dir(dst_dir)

        def _one(i: int) -> None:
            seg = segments[i]
            src = seg_wav_path(src_dir, seg["id"])
            if not os.path.exists(src):
                return
            dst = os.path.join(out_dir, os.path.basename(src))
            atempo = placements[i]["atempo"]
            # Resume-safe: đầu ra còn mới hơn nguồn VÀ đúng thời lượng kỳ
            # vọng (hệ số nén có thể đổi giữa hai lần chạy) thì bỏ qua.
            if (os.path.exists(dst) and os.path.getsize(dst) > 0
                    and os.path.getmtime(dst) >= os.path.getmtime(src)):
                want = (durations[i] or 0.0) / atempo
                have = wav_duration_s(dst) or -1.0
                if abs(have - want) < 0.05:
                    return
            if atempo != 1.0:
                apply_formant_preserved_stretch(src, dst, atempo)
            else:
                # Copy thay vì link: dst_dir có thể bị xoá độc lập.
                shutil.copyfile(src, dst)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(_one, range(len(segments))))

    # Mutate start/end lên timeline THẬT (dub) — SRT, merge và
    # total_duration cùng nhìn một sự thật. GIỮ NGUYÊN seg["duration"] (thời
    # lượng câu GỐC) — report/timing_guide vẫn so được dub với nguồn.
    from autodub.media.audio import wav_duration_s as _dur
    total = len(segments)
    log_every = 1 if total <= 60 else max(10, total // 100)
    for i, seg in enumerate(segments):
        p = placements[i]
        t = p["start"]
        final = _dur(seg_wav_path(out_dir, seg["id"])) or durations[i] or \
            float(seg.get("duration", 0) or 0)
        seg["start"] = round(t, 3)
        seg["end"] = round(t + final, 3)
        seg["dub_start"] = round(t, 3)
        seg["dub_end"] = round(t + final, 3)
        seg["dub_duration"] = round(final, 3)
        seg["tempo_factor"] = p["atempo"]
        seg["timing_adjustment"] = p["adjustment"]
        seg["timing_reason"] = p["reason"]
        natural = float(seg.get("speech_start",
                                seg.get("vad_start", t)) or t)
        if (i % log_every == 0 or p["atempo"] != 1.0
                or p["adjustment"] == "overlap"):
            logger.info(
                "[VOICE-SYNC] segment=%s source: %.3f→%.3f (d=%.3f) "
                "tts: natural=%.3f available=%s tempo=%.3f final: "
                "%.3f→%.3f adjustment=%s drift=%.3f%s",
                seg.get("id"), natural,
                float(seg.get("speech_end", seg.get("vad_end", t)) or t),
                float(seg.get("speech_duration",
                              seg.get("duration", 0)) or 0),
                durations[i] or 0.0,
                f"{p['available']:.3f}" if p["available"] is not None
                else "n/a",
                p["atempo"], t, t + final, p["adjustment"], p["drift"],
                f" ({p['reason']})" if p["reason"] else "")

    if report.segments_shifted or report.segments_compressed \
            or report.segments_stretched or report.segments_overlapped:
        parts = []
        if report.segments_shifted:
            parts.append(f"{report.segments_shifted} câu được lùi nhẹ vào "
                         f"khoảng lặng (nhiều nhất {report.max_shift_s:.1f} "
                         "giây)")
        if report.segments_compressed:
            parts.append(f"{report.segments_compressed} câu đọc nhanh hơn "
                         "một chút cho vừa chỗ")
        if report.segments_stretched:
            parts.append(f"{report.segments_stretched} câu đọc chậm nhẹ để "
                         "lấp bớt khoảng lặng cuối câu")
        if report.segments_overlapped:
            parts.append(f"{report.segments_overlapped} câu vẫn còn chồng "
                         "tiếng nhẹ")
        logger.info("Sắp xếp thời gian các câu: " + ", ".join(parts) + ".")
    else:
        logger.info("Sắp xếp thời gian các câu: mọi câu đều vừa khít, "
                    "không phải chỉnh gì")
    return out_dir, report


def build_timing_guide(
    segments: list[dict],
    durations: list[float | None],
    target_field: str = "text_vi",
    tolerance_ratio: float = 0.3,
    source_url: str = "",
    target_lang: str = "vi-VN",
) -> dict:
    """Tạo báo cáo chi tiết so khớp thời lượng từng câu thoại giữa bản gốc và TTS."""
    total_original = 0.0
    total_tts = 0.0
    need_edit = 0
    seg_items = []

    for i, seg in enumerate(segments):
        orig_dur = float(seg.get("duration") or 0.0)
        if orig_dur <= 0.0 and "end" in seg and "start" in seg:
            orig_dur = max(0.0, float(seg["end"]) - float(seg["start"]))

        actual_dur = durations[i] if (i < len(durations) and durations[i] is not None) else orig_dur
        actual_dur = round(float(actual_dur), 2)
        orig_dur = round(orig_dur, 2)

        total_original += orig_dur
        total_tts += actual_dur

        diff = round(actual_dur - orig_dur, 2)
        tol = orig_dur * tolerance_ratio

        if abs(diff) <= max(0.2, tol):
            status = "OK"
            edit_hint = "OK"
        elif diff > 0:
            status = "TOO_LONG"
            need_edit += 1
            edit_hint = f"Dài hơn {abs(diff):.1f}s"
        else:
            status = "TOO_SHORT"
            need_edit += 1
            edit_hint = f"Ngắn hơn {abs(diff):.1f}s"

        seg_items.append({
            "id": seg.get("id", i + 1),
            "text_original": str(seg.get("text", "")),
            "text_target": str(seg.get(target_field, seg.get("text", ""))),
            "start": round(float(seg.get("start", 0.0)), 2),
            "end": round(float(seg.get("end", 0.0)), 2),
            "original_duration": orig_dur,
            "tts_duration": actual_dur,
            "diff_seconds": diff,
            "status": status,
            "edit_hint": edit_hint,
        })

    total_original = round(total_original, 2)
    total_tts = round(total_tts, 2)
    ratio = round(total_tts / total_original, 2) if total_original > 0 else 1.0

    return {
        "summary": {
            "total_segments": len(segments),
            "total_original_duration": total_original,
            "total_tts_duration": total_tts,
            "ratio": ratio,
            "segments_ok": len(segments) - need_edit,
            "segments_need_edit": need_edit,
        },
        "source_url": source_url,
        "target_language": target_lang,
        "segments": seg_items,
    }


def save_timing_guide(
    work_dir: str,
    guide: dict,
    filename: str = "timing_report.json",
) -> str:
    """Ghi timing guide ra file JSON trong thư mục data của dự án."""
    import json
    from autodub.workdir import data_path

    out_path = data_path(work_dir, filename)
    ensure_dir(os.path.dirname(out_path))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)
    logger.info("Timing report exported: %s (%d/%d OK)",
                out_path, guide["summary"]["segments_ok"], guide["summary"]["total_segments"])
    return out_path

