"""AI & Heuristic Viral Shorts & Reels Clipper.

Tự động phân tích kịch bản transcript, phát hiện các phân đoạn cao trào (highlights),
chấm điểm Viral Score (1-100), tạo tiêu đề giật tít thu hút (Hook) và căn chỉnh
khớp chính xác với ranh giới câu thoại và điểm chuyển cảnh.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from autodub.utils import setup_logging

logger = setup_logging("autodub.viral_clipper")

# Các từ khóa kích thích cảm xúc và tăng độ kịch tính trong tiếng Việt
VIRAL_KEYWORDS_VI = [
    "bất ngờ", "không ngờ", "sốc", "bí mật", "sự thật", "kinh hoàng", "nguy hiểm",
    "cứu", "chết", "tiền", "phản bội", "lật mặt", "âm mưu", "kinh ngạc", "kỳ lạ",
    "tại sao", "lý do", "cảnh báo", "sợ hãi", "bi kịch", "cảm động", "nước mắt",
    "triệu đô", "đại gia", "nghèo khó", "trả giá", "hối hận", "sát thủ", "thảm kịch"
]


def snap_to_segment_boundaries(
    start_sec: float,
    end_sec: float,
    segments: list[dict[str, Any]],
    min_duration: float = 25.0,
    max_duration: float = 65.0,
) -> tuple[float, float, int, int]:
    """Căn chỉnh mốc thời gian bắt đầu và kết thúc vào ranh giới câu thoại gần nhất.
    
    Đảm bảo không bao giờ cắt cụt câu nói ở giữa.
    Trả về: (start_time, end_time, start_segment_idx, end_segment_idx)
    """
    if not segments:
        return max(0.0, start_sec), max(start_sec + min_duration, end_sec), 0, 0

    # Tìm câu thoại có điểm bắt đầu gần nhất với start_sec
    start_idx = 0
    min_diff_start = float("inf")
    for i, seg in enumerate(segments):
        diff = abs(seg.get("start", 0.0) - start_sec)
        if diff < min_diff_start:
            min_diff_start = diff
            start_idx = i

    # Tìm câu thoại kết thúc sao cho thời lượng nằm trong khoảng [min_duration, max_duration]
    actual_start = segments[start_idx].get("start", 0.0)
    end_idx = start_idx
    best_end_time = actual_start

    for j in range(start_idx, len(segments)):
        seg_end = segments[j].get("end", 0.0)
        dur = seg_end - actual_start
        end_idx = j
        best_end_time = seg_end
        if dur >= min_duration:
            if dur <= max_duration:
                # Thời lượng lý tưởng
                break
            else:
                # Đã vượt quá max_duration -> nếu j > start_idx thì lùi lại 1 câu nếu vẫn >= min_duration
                if j > start_idx:
                    prev_end = segments[j - 1].get("end", 0.0)
                    if prev_end - actual_start >= min_duration:
                        end_idx = j - 1
                        best_end_time = prev_end
                break

    actual_duration = best_end_time - actual_start
    if actual_duration < min_duration and end_idx + 1 < len(segments):
        end_idx = min(len(segments) - 1, end_idx + 1)
        best_end_time = segments[end_idx].get("end", best_end_time)

    return round(actual_start, 2), round(best_end_time, 2), start_idx, end_idx


def heuristic_viral_analysis(
    segments: list[dict[str, Any]],
    video_title: str = "",
    min_duration: float = 25.0,
    max_duration: float = 65.0,
    max_clips: int = 5,
    scene_cuts: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Phân tích tìm đoạn cao trào bằng thuật toán Heuristic khi Offline / không có AI API.
    
    Dựa trên:
    - Mật độ từ cảm xúc / kịch tính.
    - Nhịp điệu thoại (Speech rate & Speaker transition).
    - Điểm chuyển cảnh (Scene cuts).
    """
    if not segments:
        return []

    scored_windows = []
    n = len(segments)

    for i in range(n):
        seg_start = segments[i].get("start", 0.0)
        accum_text = []
        speaker_changes = 0
        last_spk = segments[i].get("speaker")

        for j in range(i, n):
            cur_seg = segments[j]
            seg_end = cur_seg.get("end", 0.0)
            dur = seg_end - seg_start
            accum_text.append(cur_seg.get("text", "") or cur_seg.get("vi", ""))

            spk = cur_seg.get("speaker")
            if spk and last_spk and spk != last_spk:
                speaker_changes += 1
                last_spk = spk

            if dur >= min_duration:
                if dur <= max_duration:
                    full_text = " ".join(accum_text)
                    # Tính điểm từ khóa viral
                    kw_matches = sum(1 for kw in VIRAL_KEYWORDS_VI if kw in full_text.lower())
                    words = len(full_text.split())
                    speech_rate = words / max(1.0, dur)

                    # Điểm số kết hợp
                    score = 60 + min(25, kw_matches * 6) + min(10, speaker_changes * 3)
                    if 2.5 <= speech_rate <= 4.5:
                        score += 5  # Nhịp điệu thoại nhanh, lôi cuốn

                    # Tạo tiêu đề gợi ý
                    first_sentence = accum_text[0].strip()
                    if len(first_sentence) > 60:
                        first_sentence = first_sentence[:57] + "..."
                    title = f"Khoảnh khắc cao trào: {first_sentence}" if first_sentence else f"Đoạn kịch tính #{len(scored_windows)+1}"

                    scored_windows.append({
                        "id": len(scored_windows) + 1,
                        "title": title,
                        "hook_text": accum_text[0] if accum_text else "",
                        "start": round(seg_start, 2),
                        "end": round(seg_end, 2),
                        "duration": round(dur, 2),
                        "viral_score": min(98, score),
                        "reason": f"Mật độ từ cảm xúc cao ({kw_matches} từ khóa), nhịp thoại dồn dập.",
                        "start_segment_idx": i,
                        "end_segment_idx": j,
                    })
                break

    # Sắp xếp theo viral_score giảm dần và lọc các clip bị trùng lặp thời gian quá nhiều (>50%)
    scored_windows.sort(key=lambda x: x["viral_score"], reverse=True)
    selected: list[dict[str, Any]] = []

    for item in scored_windows:
        overlap = False
        for chosen in selected:
            # Kiểm tra khoảng giao nhau
            max_s = max(item["start"], chosen["start"])
            min_e = min(item["end"], chosen["end"])
            if min_e > max_s and (min_e - max_s) > 0.5 * item["duration"]:
                overlap = True
                break
        if not overlap:
            item["id"] = len(selected) + 1
            selected.append(item)
            if len(selected) >= max_clips:
                break

    # Nếu kịch bản quá ngắn chưa đủ min_duration, lấy toàn bộ video làm 1 clip
    if not selected and segments:
        s0 = segments[0].get("start", 0.0)
        e0 = segments[-1].get("end", 0.0)
        selected.append({
            "id": 1,
            "title": video_title or "Clip nổi bật chính",
            "hook_text": segments[0].get("text", "") or segments[0].get("vi", ""),
            "start": round(s0, 2),
            "end": round(e0, 2),
            "duration": round(e0 - s0, 2),
            "viral_score": 85,
            "reason": "Phân đoạn chính trích xuất từ kịch bản.",
            "start_segment_idx": 0,
            "end_segment_idx": len(segments) - 1,
        })

    return selected


def analyze_viral_highlights(
    segments: list[dict[str, Any]],
    settings: Any = None,
    video_title: str = "",
    min_duration: float = 25.0,
    max_duration: float = 65.0,
    max_clips: int = 5,
    scene_cuts: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Phân tích các đoạn kịch bản tìm các mốc cao trào viral.
    
    Ưu tiên sử dụng Direct AI Client (Gemini, OpenAI, DeepSeek, v.v.).
    Tự động fallback sang Heuristic Analyzer nếu không có API Key hoặc lỗi mạng.
    """
    if not segments:
        return []

    # 1. Thử gọi AI trực tiếp nếu settings hợp lệ
    if settings is not None:
        try:
            from autodub.text.translate_direct import (
                get_direct_client,
                _slice_to_payload,
                _strip_fences_and_citations,
            )

            client, provider_name = get_direct_client(settings)
            
            # Chuẩn bị transcript có đánh số dòng và mốc thời gian
            script_lines = []
            for idx, seg in enumerate(segments):
                txt = (seg.get("text") or seg.get("vi") or "").strip()
                s = seg.get("start", 0.0)
                e = seg.get("end", 0.0)
                script_lines.append(f"[{idx}] ({s:.1f}s -> {e:.1f}s): {txt}")

            transcript_payload = "\n".join(script_lines)
            if len(transcript_payload) > 10000:
                transcript_payload = transcript_payload[:10000] + "\n..."

            system_instruction = (
                "Bạn là chuyên gia phân tích nội dung video triệu view hàng đầu trên TikTok, YouTube Shorts và Facebook Reels. "
                "Nhiệm vụ của bạn là đọc kịch bản video (kèm mốc thời gian) và tìm ra 3-5 đoạn cao trào, nút thắt kịch tính "
                "hoặc khoảnh khắc viral nhất của video để cắt thành các video ngắn (Shorts/Reels).\n"
                "YÊU CẦU BẮT BUỘC:\n"
                "1. Thời lượng mỗi clip phải nằm trong khoảng từ 25 giây đến 65 giây.\n"
                "2. start và end BẮT BUỘC phải khớp chính xác với mốc thời gian của một câu thoại cụ thể trong danh sách.\n"
                "3. Tiêu đề (title) 100% bằng TIẾNG VIỆT, cực kỳ hấp dẫn, gây tò mò kích thích người xem dừng lại xem ngay.\n"
                "4. Chấm điểm viral_score từ 75 đến 99."
            )

            user_prompt = f"""Dưới đây là kịch bản video tiếng Việt:
Tiêu đề tham khảo: {video_title or 'Video'}

Danh sách câu thoại và mốc thời gian:
\"\"\"
{transcript_payload}
\"\"\"

Hãy chọn ra top {max_clips} đoạn kịch tính/viral nhất (thời lượng 25s - 65s) và trả về duy nhất định dạng JSON sau:
[
  {{
    "title": "Tiêu đề giật tít tiếng Việt...",
    "hook_text": "Câu thoại mở đầu hook...",
    "start": 12.5,
    "end": 55.0,
    "viral_score": 95,
    "reason": "Lý do đoạn này sẽ viral..."
  }}
]
Chỉ trả về JSON thuần túy, không giải thích thêm."""

            raw = client.call_ai(system_instruction, user_prompt)
            clean = _strip_fences_and_citations(raw)
            data = json.loads(_slice_to_payload(clean))

            if isinstance(data, list) and len(data) > 0:
                validated_clips = []
                for item in data:
                    raw_s = float(item.get("start", 0.0))
                    raw_e = float(item.get("end", raw_s + 30.0))
                    snap_s, snap_e, s_idx, e_idx = snap_to_segment_boundaries(
                        raw_s, raw_e, segments, min_duration=min_duration, max_duration=max_duration
                    )
                    score = int(item.get("viral_score", 90))
                    score = max(50, min(99, score))
                    validated_clips.append({
                        "id": len(validated_clips) + 1,
                        "title": str(item.get("title", f"Short Clip #{len(validated_clips)+1}")).strip(),
                        "hook_text": str(item.get("hook_text", "")).strip(),
                        "start": snap_s,
                        "end": snap_e,
                        "duration": round(snap_e - snap_s, 2),
                        "viral_score": score,
                        "reason": str(item.get("reason", "Điểm cao trào được AI phát hiện.")).strip(),
                        "start_segment_idx": s_idx,
                        "end_segment_idx": e_idx,
                    })

                if validated_clips:
                    logger.info(f"AI đã phân tích thành công {len(validated_clips)} đoạn Viral Shorts via {provider_name}")
                    return validated_clips
        except Exception as e:
            logger.warning(f"Phân tích Viral Shorts bằng AI lỗi ({e}) — chuyển sang Heuristic Analyzer")

    # 2. Fallback sang Heuristic Analyzer
    return heuristic_viral_analysis(
        segments,
        video_title=video_title,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
        scene_cuts=scene_cuts,
    )
