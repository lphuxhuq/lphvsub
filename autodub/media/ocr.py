"""Selective OCR hard-sub — fallback lấy lại text cho các câu ASR nghi ngờ.

Chỉ chạy khi video có hard-sub VÀ có suspect segment (design asr-accuracy-boost
C5): mỗi suspect window → ffmpeg trích frame FPS thấp ở vùng phụ đề dưới
cùng → worker OCR trong .venv-ocr (JSON-lines protocol) → normalize → merge
frame liên tiếp trùng text → ``OcrSegment``. Kết quả cache theo
(video mtime, region, fps, windows) để resume không OCR lại.

Không bao giờ OCR toàn bộ video. Mọi lỗi OCR đều raise để caller (pipeline)
catch và tiếp tục bằng ASR thuần.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess

from autodub.resources import FFMPEG_SLOTS
from autodub.utils import ensure_dir, setup_logging

logger = setup_logging("autodub.ocr")

_OCR_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "ocr_worker.py")

#: Đệm hai bên mỗi suspect window (giây) — phủ mất đầu/cuối câu.
WINDOW_MARGIN_S = 1.0
#: Hai frame liên tiếp giống nhau ≥ ngưỡng này → cùng một phụ đề.
FRAME_MERGE_SIMILARITY = 0.9
#: Điểm OCR dưới mức này coi dòng là rác (đã lọc ở worker, lọc lại cho chắc).
LINE_MIN_SCORE = 0.3

_OCR_SPECS_HINT = "py scripts/setup_ocr.py"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def normalize_ocr_text(text: str) -> str:
    """Làm sạch text OCR: full-width → half-width cho chữ/số Latin, bỏ ký tự
    ngoài CJK + punctuation CJK cơ bản, bỏ khoảng trắng/xuống dòng."""
    out = []
    for ch in str(text or ""):
        code = ord(ch)
        # Full-width ALNUM (ＡＢＣ１２３) → half-width; full-width punct
        # (？！，) giữ nguyên vì là punct CJK.
        if (0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A
                or 0xFF41 <= code <= 0xFF5A):
            out.append(chr(code - 0xFEE0))
        elif "\u4e00" <= ch <= "\u9fff" or ch in "，。！？；：、…—“”‘’（）":
            out.append(ch)
        elif ch.isalnum():  # chữ/số half-width — giữ lại
            out.append(ch)
    return "".join(out).strip()


def join_frame_lines(lines: list[dict]) -> tuple[str, float]:
    """Ghép các dòng OCR của MỘT frame (đã sort top→bottom ở worker) thành
    text một dòng + điểm trung bình. Trả ("", 0) khi không dòng nào sống sót."""
    kept = [l for l in lines if l.get("score", 0) >= LINE_MIN_SCORE]
    if not kept:
        return "", 0.0
    text = "".join(str(l.get("text", "")) for l in kept).strip()
    score = sum(float(l.get("score", 0)) for l in kept) / len(kept)
    return text, score


def merge_frame_texts(frame_items: list[dict], fps: float,
                       total_frames: int) -> list[dict]:
    """Gộp các frame kề nhau trùng phụ đề thành OcrSegment.

    ``frame_items``: [{"t": giây, "text": normalized, "score": float}] theo
    thứ tự thời gian. Trả về list ``{"text", "start_time", "end_time",
    "confidence", "stability"}`` — stability = tỉ lệ frame trong window cùng
    nhóm (đo độ "đứng yên" của phụ đề để scoring fusion dùng).
    """
    frame_dur = 1.0 / max(1e-6, fps)
    groups: list[list[dict]] = []
    for item in frame_items:
        if not item.get("text"):
            continue
        if groups:
            prev = groups[-1][-1]
            sim = difflib.SequenceMatcher(
                None, prev["text"], item["text"]).ratio()
            if sim >= FRAME_MERGE_SIMILARITY:
                groups[-1].append(item)
                continue
        groups.append([item])

    total = max(1, total_frames)
    out = []
    for group in groups:
        # Text đại diện: của frame có score cao nhất (chống lỗi 1 frame).
        best = max(group, key=lambda g: g.get("score", 0))
        out.append({
            "text": best["text"],
            "start_time": round(group[0]["t"], 3),
            "end_time": round(group[-1]["t"] + frame_dur, 3),
            "confidence": round(
                sum(g["score"] for g in group) / len(group), 3),
            "stability": round(len(group) / total, 3),
        })
    return out


def _probe_duration(video_path: str) -> float:
    """Độ dài video (giây) bằng ffprobe — để clamp window và chia probe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def windows_from_suspects(suspects: list[dict], duration_s: float,
                          margin: float = WINDOW_MARGIN_S) -> list[tuple[float, float]]:
    """Suspect segments → các window [start, end] đã ghi đè lẫn nhau.

    Gộp window giao nhau để không OCR trùng vùng, clamp vào [0, duration].
    """
    raw = []
    for s in suspects:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", start))
        if end <= start:
            continue
        # Margin trước, clamp sau — window có thể ăn vào biên video nhưng
        # không vượt ra ngoài.
        start = max(0.0, start - margin)
        end = end + margin
        if duration_s > 0:
            end = min(end, duration_s)
        if end <= start:
            continue
        raw.append((start, end))
    raw.sort()
    merged: list[list[float]] = []
    for start, end in raw:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _crop_filter(region_height: float) -> str:
    """crop vùng phụ đề dưới cùng theo chiều cao ``region_height`` (tỷ lệ)."""
    return (f"crop=iw:ih*{region_height:.4f}:0:ih*(1-{region_height:.4f})")


def _extract_frames(video_path: str, start: float, end: float, fps: int,
                    region_height: float, out_dir: str) -> list[tuple[str, float]]:
    """ffmpeg trích frame FPS thấp của window (đã crop region) → JPEG.

    Trả về [(path, thời điểm giây)] theo thứ tự — frame k (1-based) ở thời
    điểm ``start + (k-1)/fps``.
    """
    ensure_dir(out_dir)
    for old in os.listdir(out_dir):
        if old.endswith(".jpg"):
            os.remove(os.path.join(out_dir, old))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.0, end - start):.3f}",
           "-i", video_path,
           "-vf", f"{_crop_filter(region_height)},fps={fps}",
           "-q:v", "2", os.path.join(out_dir, "frame_%05d.jpg")]
    with FFMPEG_SLOTS:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction lỗi: {r.stderr[-400:]}")
    paths = sorted(p for p in os.listdir(out_dir) if p.endswith(".jpg"))
    return [(os.path.join(out_dir, p), start + i / fps)
            for i, p in enumerate(paths)]


def _run_ocr_worker(image_paths: list[str], venv_python: str) -> list[dict]:
    """Chạy worker .venv-ocr trên danh sách ảnh → các message frame."""
    if not image_paths:
        return []
    if not os.path.isfile(venv_python):
        raise RuntimeError(f"venv OCR chưa cài ({_OCR_SPECS_HINT}): "
                           f"{venv_python}")
    list_file = os.path.join(os.path.dirname(image_paths[0]), "frames.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("\n".join(image_paths))
    try:
        proc = subprocess.run(
            [venv_python, _OCR_WORKER, "--list", list_file],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1800)
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"OCR worker chết: {e}") from e
    frames: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("error"):
            raise RuntimeError(f"OCR worker: {msg['error']}")
        if msg.get("frame"):
            frames.append(msg)
    if proc.returncode != 0 and not frames:
        raise RuntimeError(f"OCR worker lỗi (exit {proc.returncode}): "
                           f"{proc.stderr[-400:]}")
    return frames


def _windows_key(video_path: str, windows, settings) -> str:
    stat = os.stat(video_path)
    payload = json.dumps({
        "mtime": int(stat.st_mtime), "size": stat.st_size,
        "fps": settings.ocr_fps,
        "region": round(float(settings.ocr_region_height), 4),
        "windows": [[round(s, 3), round(e, 3)] for s, e in windows],
    }, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()


def _cache_path(work_dir: str) -> str:
    from autodub.workdir import data_path
    return data_path(work_dir, "ocr_result.json", create_dir=False)


def _load_cached(work_dir: str, key: str) -> list[dict] | None:
    try:
        with open(_cache_path(work_dir), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("key") == key and isinstance(data.get("segments"), list):
            return data["segments"]
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def _save_cache(work_dir: str, key: str, segments: list[dict]) -> None:
    from autodub.utils import save_json_atomic
    save_json_atomic({"key": key, "segments": segments},
                     _cache_path(work_dir))


def run_selective_ocr(video_path: str, suspects: list[dict], settings,
                      work_dir: str, duration_s: float | None = None
                      ) -> list[dict]:
    """OCR chỉ trên các suspect window → list OcrSegment (đã merge/cache).

    Không suspect → trả [] mà không mở ffmpeg/worker (AC-6).
    """
    if not suspects:
        return []
    duration = duration_s if duration_s else _probe_duration(video_path)
    windows = windows_from_suspects(suspects, duration)
    if not windows:
        return []

    key = _windows_key(video_path, windows, settings)
    cached = _load_cached(work_dir, key)
    if cached is not None:
        logger.info("OCR: dùng cache %d segment cho %d window(s)",
                    len(cached), len(windows))
        return cached

    venv_python = settings.ocr_venv_python_path()
    all_segments: list[dict] = []
    for wi, (start, end) in enumerate(windows):
        out_dir = os.path.join(os.path.dirname(_cache_path(work_dir)),
                               "ocr_frames", f"w{wi}")
        frames = _extract_frames(video_path, start, end, settings.ocr_fps,
                                 settings.ocr_region_height, out_dir)
        if not frames:
            continue
        msgs = _run_ocr_worker([p for p, _t in frames], venv_python)
        frame_items = []
        by_path = {m["frame"]: m for m in msgs}
        for path, t in frames:
            text, score = join_frame_lines(by_path.get(path, {}).get("lines", []))
            frame_items.append({"t": t, "text": normalize_ocr_text(text),
                                "score": score})
        segs = merge_frame_texts(frame_items, settings.ocr_fps,
                                 total_frames=len(frames))
        all_segments.extend(segs)
        # Frame tạm đã dùng xong — dọn để không phình disk (cache là JSON).
        for path, _t in frames:
            try:
                os.remove(path)
            except OSError:
                pass

    _save_cache(work_dir, key, all_segments)
    logger.info("OCR: %d window(s) → %d phụ đề", len(windows),
                len(all_segments))
    return all_segments


def detect_hardsub(video_path: str, settings,
                   duration_s: float | None = None) -> bool:
    """Probe 5 frame rải đều video — ≥3/5 frame có text CJK ở vùng dưới."""
    duration = duration_s if duration_s else _probe_duration(video_path)
    if duration <= 0:
        logger.warning("OCR: không đo được độ dài video — bỏ probe hard-sub")
        return False
    venv_python = settings.ocr_venv_python_path()
    if not os.path.isfile(venv_python):
        logger.warning(f"OCR chưa cài — bỏ probe hard-sub ({_OCR_SPECS_HINT})")
        return False

    import tempfile
    hits = 0
    probes = 4  # 5 frame (i + 0.5)/5
    with tempfile.TemporaryDirectory(prefix="hardsub_") as tmp:
        for i in range(probes + 1):
            t = duration * (i + 0.5) / (probes + 1)
            frames = _extract_frames(video_path, t, t + 0.2, 10,
                                     settings.ocr_region_height, tmp)
            if not frames:
                continue
            msgs = _run_ocr_worker([p for p, _tt in frames], venv_python)
            for m in msgs:
                text, _ = join_frame_lines(m.get("lines", []))
                if _has_cjk(normalize_ocr_text(text)):
                    hits += 1
                    break
    is_hardsub = hits >= 3
    logger.info("OCR hard-sub probe: %d/%d frame có phụ đề → %s",
                hits, probes + 1, "CÓ hard-sub" if is_hardsub else "không có")
    return is_hardsub
