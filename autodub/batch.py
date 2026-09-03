"""Batch dubbing: process a list of videos typed one per line, with crash-safe
status tracking.

The user pastes URLs — one per line — and the batch runner does the rest. An
optional voice name may follow the URL after ``|``, ``,`` or a tab::

    https://youtu.be/aaa
    https://youtu.be/bbb | Trúc Ly
    https://youtu.be/ccc | Phạm Tuyên

Progress is persisted to ``batch_state.json`` inside the output directory after
every video, so an interrupted batch can be resumed by pasting the same list
again: videos already marked ``success`` are skipped automatically.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from typing import Callable, Iterable

from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest
from autodub.progress import PipelineCancelled
from autodub.utils import save_json_atomic, setup_logging

logger = setup_logging("autodub.batch")

STATE_FILENAME = "batch_state.json"

# Tách một dòng thành liên kết + TÊN GIỌNG tùy chọn. Chỉ tách ở các dấu rõ
# ràng (| , ; tab, hoặc từ hai khoảng trắng trở lên) vì tên giọng tiếng Việt
# có khoảng trắng bên trong — tách ở một dấu cách sẽ cắt đôi «Trúc Ly».
_SPLIT_RE = re.compile(r"[|,;\t]|\s{2,}")


@dataclass
class BatchItem:
    """One video in a batch: a URL or a local file, plus per-video options."""
    url: str | None = None
    file_path: str | None = None
    voice: str | None = None
    blur_regions: list = None          # per-video blur rectangles (or None)
    subtitle_mode: str | None = None   # per-video override (or None = template)
    subtitle_style: dict | None = None  # per-video style (or None = template)
    logo_opts: dict | None = None      # per-video logo options (or None = template)
    watermark_opts: dict | None = None # per-video watermark options (or None = template)
    reframe_opts: dict | None = None   # per-video reframe options (or None = template)
    sfx_opts: dict | None = None       # per-video sfx options (or None = template)
    ref: object = None  # backend-specific handle (state dict entry)

    @property
    def key(self) -> str:
        """Stable identity for state tracking (URL or absolute file path)."""
        return self.url or os.path.abspath(self.file_path or "")

    @property
    def label(self) -> str:
        """Short display name for tables/logs."""
        if self.url:
            return self.url
        return os.path.basename(self.file_path or "")


@dataclass
class BatchSummary:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0


# Observer signature: (index, total, item, status, detail)
# status: "start" | "success" | "failed"
BatchObserver = Callable[[int, int, BatchItem, str, str], None]


class _Prefetcher:
    """Tải trước video theo CỬA SỔ TRƯỢT trong khi các video trước xử lý.

    Tải mạng hoàn toàn độc lập với các bước GPU/CPU của video đang chạy —
    chồng lấn hai việc là thời gian tải gần như miễn phí. Một thread tải
    TUẦN TỰ hàng đợi tới ``depth`` video kế tiếp (mặc định 2): sâu hơn về
    phía trước mà KHÔNG thêm kết nối CDN song song. Tốn đĩa tối đa ~depth
    video (1-2GB với video dài) — chỉnh qua ``BATCH_PREFETCH_DEPTH``
    (1 = hành vi cũ, chỉ video kế tiếp).

    File tải trước nằm ở ``<output_dir>/_prefetch/<n>/``; khi video chạy
    xong thành công, file được dọn vào work_dir của chính video đó (resume
    tự tìm thấy như video tải bình thường).
    """

    def __init__(self, root_dir: str, depth: int = 2):
        self._root = os.path.join(root_dir, "_prefetch")
        self._depth = max(1, int(depth))
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._queue: dict[int, BatchItem] = {}   # index -> item chờ tải
        self._events: dict[int, threading.Event] = {}
        self._results: dict[int, dict] = {}

    def ensure_window(self, current_index: int,
                      items: list[BatchItem]) -> None:
        """Lên lịch tải ``current+1 .. current+depth`` (bỏ qua file local)."""
        with self._lock:
            # Mục đã đi qua mà chưa kịp tải → bỏ; đánh thức ai đang chờ nó.
            for idx in [k for k in self._queue if k <= current_index]:
                self._queue.pop(idx, None)
                ev = self._events.pop(idx, None)
                if ev is not None:
                    ev.set()
            for idx in range(current_index + 1,
                             min(current_index + 1 + self._depth,
                                 len(items))):
                item = items[idx]
                if (not item.url or item.file_path
                        or idx in self._queue or idx in self._events):
                    continue
                self._queue[idx] = item
                self._events[idx] = threading.Event()
            if self._queue and self._worker is None:
                self._worker = threading.Thread(
                    target=self._work, daemon=True, name="batch-prefetch")
                self._worker.start()

    def _work(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                idx = min(self._queue)   # luôn tải theo thứ tự video
                item = self._queue.pop(idx)
                ev = self._events[idx]
            try:
                from autodub.media.downloader import download_video
                dest = os.path.join(self._root, str(idx))
                path = download_video(item.url, dest)
                with self._lock:
                    self._results[idx] = {"path": path}
            except Exception as e:  # noqa: BLE001 — video này sẽ tải lại bình thường
                logger.warning(f"Tải trước thất bại ({item.label}): {e}")
                with self._lock:
                    self._results[idx] = {"error": str(e)}
            finally:
                ev.set()

    def take(self, index: int, timeout: float = 3600.0) -> str | None:
        """Chờ đúng ``index`` tải xong; trả đường dẫn file hoặc None."""
        with self._lock:
            ev = self._events.get(index)
        if ev is None:
            return None   # không được lên lịch (file local / ngoài cửa sổ)
        if not ev.wait(timeout):
            logger.warning("Tải trước quá lâu — video sẽ tự tải lại")
            return None
        with self._lock:
            return self._results.get(index, {}).get("path")

    @staticmethod
    def adopt(prefetched: str, work_dir: str) -> None:
        """Dọn file đã tải trước vào work_dir của video (best-effort)."""
        try:
            if os.path.isfile(prefetched) and os.path.isdir(work_dir):
                target = os.path.join(work_dir,
                                      os.path.basename(prefetched))
                if not os.path.exists(target):
                    shutil.move(prefetched, target)
                parent = os.path.dirname(prefetched)
                # video_meta.json (title) đi kèm video — dọn vào data/ của
                # work_dir để các bước dịch/metadata đọc được.
                meta = os.path.join(parent, "data", "video_meta.json")
                if os.path.isfile(meta):
                    from autodub.workdir import data_path
                    meta_target = data_path(work_dir, "video_meta.json",
                                            create_dir=True)
                    if not os.path.exists(meta_target):
                        shutil.move(meta, meta_target)
                    else:
                        os.remove(meta)  # _resolve_video đã chép sẵn
                    meta_dir = os.path.dirname(meta)
                    if os.path.isdir(meta_dir) and not os.listdir(meta_dir):
                        os.rmdir(meta_dir)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
        except OSError as e:
            logger.warning(f"Không dọn được file tải trước: {e}")

    def cleanup(self) -> None:
        """Xoá các file tải trước còn sót (video lỗi giữ nguyên để resume)."""
        with self._lock:
            self._queue.clear()
            for ev in self._events.values():
                ev.set()
            self._events.clear()
            self._results.clear()
        try:
            if os.path.isdir(self._root) and not os.listdir(self._root):
                os.rmdir(self._root)
        except OSError:
            pass


def parse_lines(text: str | Iterable[str]) -> list[BatchItem]:
    """Turn pasted text (or a list of lines) into batch items.

    Dòng trống và dòng bắt đầu bằng ``#`` bị bỏ qua, liên kết trùng chỉ lấy
    lần đầu. Tên giọng được giữ nguyên như người dùng gõ; giọng không có
    trong danh mục sẽ tự rơi về giọng mặc định lúc chạy chứ không làm hỏng
    cả danh sách."""
    lines = text.splitlines() if isinstance(text, str) else list(text)
    items: list[BatchItem] = []
    seen: set[str] = set()

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in _SPLIT_RE.split(line, maxsplit=1) if p and p.strip()]
        if not parts:
            continue  # dòng chỉ có ký tự phân tách ("|", ",") — bỏ qua
        url = parts[0]
        voice = parts[1] if len(parts) > 1 else None

        if url in seen:
            logger.info(f"Skipping duplicate URL: {url}")
            continue
        seen.add(url)
        items.append(BatchItem(url=url, voice=voice))

    return items


def _build_item_request(
    item: BatchItem,
    req_template: DubRequest,
    file_path: str | None = None,
    resume_dir: str | None = None,
) -> DubRequest:
    """Tạo DubRequest cho một video trong batch, hòa trộn tùy chỉnh riêng của video đó."""
    sub_style = item.subtitle_style if item.subtitle_style is not None else req_template.subtitle_style
    blur_regs = item.blur_regions if item.blur_regions is not None else req_template.blur_regions

    logo_p = getattr(req_template, "logo_path", None)
    logo_pos = getattr(req_template, "logo_position", "top_right")
    logo_sc = getattr(req_template, "logo_scale", 0.12)
    logo_op = getattr(req_template, "logo_opacity", 0.85)
    logo_mot = getattr(req_template, "logo_motion", "static")
    if item.logo_opts:
        if item.logo_opts.get("enabled", True) and (item.logo_opts.get("path") or item.logo_opts.get("logo_path")):
            logo_p = item.logo_opts.get("path") or item.logo_opts.get("logo_path") or ""
            logo_pos = item.logo_opts.get("position") or item.logo_opts.get("logo_position") or logo_pos
            logo_sc = item.logo_opts.get("scale") or item.logo_opts.get("logo_scale") or logo_sc
            logo_op = item.logo_opts.get("opacity") or item.logo_opts.get("logo_opacity") or logo_op
            logo_mot = item.logo_opts.get("motion") or item.logo_opts.get("logo_motion") or logo_mot
        elif not item.logo_opts.get("enabled", True):
            logo_p = None

    wm_t = getattr(req_template, "watermark_text", None)
    wm_mot = getattr(req_template, "watermark_motion", "bounce")
    wm_op = getattr(req_template, "watermark_opacity", 0.28)
    wm_fs = getattr(req_template, "watermark_font_size", 26)
    wm_sp = getattr(req_template, "watermark_speed", 40)
    if item.watermark_opts:
        if item.watermark_opts.get("enabled", True) and (item.watermark_opts.get("text") or item.watermark_opts.get("watermark_text")):
            wm_t = item.watermark_opts.get("text") or item.watermark_opts.get("watermark_text") or ""
            wm_mot = item.watermark_opts.get("motion") or item.watermark_opts.get("watermark_motion") or wm_mot
            wm_op = item.watermark_opts.get("opacity") or item.watermark_opts.get("watermark_opacity") or wm_op
            wm_fs = item.watermark_opts.get("font_size") or item.watermark_opts.get("watermark_font_size") or wm_fs
            wm_sp = item.watermark_opts.get("speed") or item.watermark_opts.get("watermark_speed") or wm_sp
        elif not item.watermark_opts.get("enabled", True):
            wm_t = None

    asp_preset = getattr(req_template, "aspect_preset", "original")
    ref_mode = getattr(req_template, "reframe_mode", "blur")
    if item.reframe_opts:
        asp_preset = item.reframe_opts.get("aspect_preset", asp_preset)
        ref_mode = item.reframe_opts.get("reframe_mode", ref_mode)

    sfx_en = getattr(req_template, "auto_sfx_enabled", False)
    sfx_pres = getattr(req_template, "sfx_preset", "whoosh")
    sfx_vol = getattr(req_template, "sfx_volume_db", -4.0)
    if item.sfx_opts:
        sfx_en = item.sfx_opts.get("auto_sfx_enabled", sfx_en)
        sfx_pres = item.sfx_opts.get("sfx_preset", sfx_pres)
        sfx_vol = item.sfx_opts.get("sfx_volume_db", sfx_vol)

    return DubRequest(
        url=item.url,
        file_path=file_path or item.file_path,
        source_lang=req_template.source_lang,
        voice=item.voice or req_template.voice,
        bg_mode=req_template.bg_mode,
        bg_duck_db=req_template.bg_duck_db,
        skip_video=req_template.skip_video,
        subtitle_mode=item.subtitle_mode or req_template.subtitle_mode,
        subtitle_style=sub_style,
        blur_regions=blur_regs,
        output_dir=req_template.output_dir,
        resume_dir=resume_dir,
        logo_path=logo_p,
        logo_position=logo_pos,
        logo_scale=logo_sc,
        logo_opacity=logo_op,
        logo_motion=logo_mot,
        watermark_text=wm_t,
        watermark_motion=wm_mot,
        watermark_opacity=wm_op,
        watermark_font_size=wm_fs,
        watermark_speed=wm_sp,
        smart_flip=getattr(req_template, "smart_flip", False),
        micro_zoom=getattr(req_template, "micro_zoom", False),
        color_filter=getattr(req_template, "color_filter", "none"),
        aspect_preset=asp_preset,
        reframe_mode=ref_mode,
        auto_sfx_enabled=sfx_en,
        sfx_preset=sfx_pres,
        sfx_volume_db=sfx_vol,
    )


def _copy_to_export_dir(report: dict | None, export_dir: str | None) -> None:
    """Sao chép video thành phẩm ra một thư mục đích chung nếu được chỉ định."""
    if not export_dir or not os.path.isdir(export_dir) or not report:
        return
    dubbed = report.get("dubbed_video") or ""
    if dubbed and os.path.isfile(dubbed):
        import shutil
        title = report.get("title") or os.path.splitext(os.path.basename(dubbed))[0]
        safe_title = "".join(c for c in title if c not in '<>:"/\\|?*').strip()
        if not safe_title:
            safe_title = report.get("session_id", "dubbed_video")
        dest_name = f"{safe_title}.mp4"
        dest_path = os.path.join(export_dir, dest_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(export_dir, f"{safe_title}_{counter:02d}.mp4")
            counter += 1
        try:
            shutil.copy2(dubbed, dest_path)
            logger.info(f"Đã sao chép video thành phẩm ra thư mục chung: {dest_path}")
        except Exception as ex:
            logger.warning(f"Không thể sao chép ra thư mục xuất gom: {ex}")


def _run_items(
    items: list[BatchItem],
    pipeline: DubPipeline,
    req_template: DubRequest,
    on_result: Callable[[BatchItem, dict | None, str | None], None],
    on_start: Callable[[BatchItem], None] | None = None,
    observer: BatchObserver | None = None,
    export_dir: str | None = None,
) -> BatchSummary:
    """Process items sequentially; call ``on_result(item, report, error)`` after
    each one (report on success, error message on failure) so the caller can
    persist status crash-safely. ``observer`` (if given) receives display-only
    per-item events — used by the GUI. A :class:`PipelineCancelled` from the
    pipeline aborts the whole batch (it is not recorded as a failure)."""
    summary = BatchSummary(total=len(items))
    # req_template.output_dir có thể None — dùng default của pipeline để
    # thư mục _prefetch nằm cạnh các work_dir.
    from autodub.languages import get_target
    prefetch_root = (req_template.output_dir
                     or pipeline.default_output_dir(get_target(req_template.target)))
    # FakePipeline của test không có settings — depth 2 là mặc định hợp lý.
    pf_settings = getattr(pipeline, "settings", None)
    prefetcher = _Prefetcher(
        prefetch_root,
        depth=getattr(pf_settings, "batch_prefetch_depth", 2),
    )

    for i, item in enumerate(items):
        logger.info(f"[{i + 1}/{len(items)}] Processing: {item.label}")
        if on_start:
            on_start(item)
        if observer:
            observer(i, len(items), item, "start", "")
        # Video này đã được tải trước trong lúc các video trước xử lý?
        prefetched = prefetcher.take(i)
        # Lên lịch tải nền cửa sổ các video kế tiếp ngay khi video này khởi động.
        prefetcher.ensure_window(i, items)
        try:
            # Video này từng chạy dở (lỗi, thiếu Vox…)? Chạy TIẾP đúng thư
            # mục cũ: phần đã tải/nghe-chép/dịch được dùng lại, không tạo
            # thư mục mới — job_id giữ nguyên nên không bị trừ Vox lần nữa.
            resume_dir = None
            if isinstance(item.ref, dict):
                prev_dir = item.ref.get("work_dir") or ""
                if prev_dir and os.path.isdir(prev_dir):
                    resume_dir = prev_dir
            req = _build_item_request(item, req_template, file_path=prefetched, resume_dir=resume_dir)
            result = pipeline.run(req)
            if result.status != "completed":
                # Vietnamese-first: this string lands in the batch table and
                # the user's log, not just the console.
                reasons = {
                    "translate_pending": (
                        "Video chờ bản dịch tay — mở video này ở trang Tạo "
                        "dự án để dịch rồi chạy tiếp."),
                    "credit_blocked": (
                        "Không đủ Vox cho video này — nạp thêm rồi chạy lại; "
                        "phần đã nghe-chép được dùng lại, chưa bị trừ Vox."),
                }
                raise RuntimeError(reasons.get(
                    result.status,
                    f"Pipeline dừng ở trạng thái {result.status} "
                    f"(work_dir={result.work_dir})."))
            summary.success += 1
            logger.info(f"[{i + 1}/{len(items)}] SUCCESS → {result.report['session_id']}")
            if prefetched:
                # Dọn file tải trước vào work_dir để resume tự tìm thấy.
                _Prefetcher.adopt(prefetched, result.report.get("output_dir", ""))
            _copy_to_export_dir(result.report, export_dir)
            on_result(item, result.report, None)
            if observer:
                observer(i, len(items), item, "success", result.report["session_id"])
        except PipelineCancelled:
            logger.info("Batch cancelled by user")
            # Nhớ thư mục dở dang để lần chạy lại đi tiếp từ chỗ dừng.
            if isinstance(item.ref, dict) and getattr(pipeline, "last_work_dir", ""):
                item.ref["work_dir"] = pipeline.last_work_dir
            prefetcher.cleanup()
            raise
        except Exception as e:
            summary.failed += 1
            error_msg = str(e)[:200]
            logger.error(f"[{i + 1}/{len(items)}] FAILED: {error_msg}")
            # Ghi lại thư mục của lượt chạy hỏng — chạy lại sẽ resume đúng
            # thư mục này thay vì tải + nghe-chép lại từ đầu.
            if isinstance(item.ref, dict) and getattr(pipeline, "last_work_dir", ""):
                item.ref["work_dir"] = pipeline.last_work_dir
            on_result(item, None, error_msg)
            if observer:
                observer(i, len(items), item, "failed", error_msg)

    prefetcher.cleanup()
    logger.info("=" * 60)
    logger.info("BATCH COMPLETE")
    logger.info(f"  Total:   {summary.total}")
    logger.info(f"  Success: {summary.success}")
    logger.info(f"  Failed:  {summary.failed}")
    if summary.skipped:
        logger.info(f"  Skipped: {summary.skipped} (already done)")
    logger.info("=" * 60)
    return summary


def _save_json_atomic(data: object, path: str) -> None:
    """Crash-safe save: write to temp file then replace."""
    save_json_atomic(data, path)


def _load_state(state_path: str) -> dict[str, dict]:
    """Read the per-URL status map from a previous run (empty if none)."""
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        return {v["video_url"]: v for v in data.get("videos", []) if v.get("video_url")}
    except Exception as e:  # noqa: BLE001 — a corrupt state file must not block a run
        logger.warning(f"Ignoring unreadable {STATE_FILENAME}: {e}")
        return {}


def _run_items_concurrent(
    items: list[BatchItem],
    settings: Settings,
    req_template: DubRequest,
    on_result: Callable[[BatchItem, dict | None, str | None], None],
    on_start: Callable[[BatchItem], None] | None = None,
    observer: BatchObserver | None = None,
    concurrency: int = 2,
    export_dir: str | None = None,
) -> BatchSummary:
    """Xử lý đồng thời nhiều video trong danh sách bằng ThreadPoolExecutor với continuous prefetching."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    summary = BatchSummary(total=len(items))
    lock = threading.Lock()
    
    # Setup prefetcher
    prefetch_root = req_template.output_dir or settings.output_dir
    prefetcher = _Prefetcher(prefetch_root, depth=max(2, concurrency))
    # Pre-schedule all
    for i, item in enumerate(items):
        prefetcher.ensure_window(i, items)

    def _process_one(idx: int, item: BatchItem):
        with lock:
            if on_start:
                on_start(item)
            if observer:
                observer(idx, len(items), item, "start", "")
        
        prefetched = prefetcher.take(idx)
        logger.info(f"[{idx + 1}/{len(items)}] [Đa luồng] Bắt đầu: {item.label}")

        pipeline = DubPipeline(settings)
        try:
            resume_dir = None
            if isinstance(item.ref, dict):
                prev_dir = item.ref.get("work_dir") or ""
                if prev_dir and os.path.isdir(prev_dir):
                    resume_dir = prev_dir

            req = _build_item_request(item, req_template, file_path=prefetched, resume_dir=resume_dir)
            result = pipeline.run(req)
            if result.status != "completed":
                raise RuntimeError(f"Pipeline dừng ở trạng thái {result.status}")

            if prefetched:
                _Prefetcher.adopt(prefetched, result.report.get("output_dir", ""))
            _copy_to_export_dir(result.report, export_dir)

            with lock:
                summary.success += 1
                on_result(item, result.report, None)
                if observer:
                    observer(idx, len(items), item, "success", result.report.get("session_id", ""))
            logger.info(f"[{idx + 1}/{len(items)}] [Đa luồng] SUCCESS → {result.report.get('session_id', '')}")
            return True
        except PipelineCancelled:
            logger.info("Batch item cancelled")
            raise
        except Exception as e:
            error_msg = str(e)[:200]
            logger.error(f"[{idx + 1}/{len(items)}] [Đa luồng] FAILED: {error_msg}")
            with lock:
                summary.failed += 1
                if isinstance(item.ref, dict) and getattr(pipeline, "last_work_dir", ""):
                    item.ref["work_dir"] = pipeline.last_work_dir
                on_result(item, None, error_msg)
                if observer:
                    observer(idx, len(items), item, "failed", error_msg)
            return False

    workers_n = max(1, min(concurrency, len(items)))
    try:
        with ThreadPoolExecutor(max_workers=workers_n, thread_name_prefix="dub-batch") as pool:
            futures = {pool.submit(_process_one, i, item): item for i, item in enumerate(items)}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except PipelineCancelled:
                    break
                except Exception as e:
                    logger.error(f"Concurrent item error: {e}")
    finally:
        prefetcher.cleanup()

    return summary


def run_batch(
    lines: str | Iterable[str] | list[BatchItem],
    settings: Settings,
    req_template: DubRequest,
    pipeline: DubPipeline | None = None,
    observer: BatchObserver | None = None,
    state_path: str | None = None,
    retry_done: bool = False,
    reuse_tts: bool = True,
    concurrency: int = 1,
    export_dir: str | None = None,
) -> BatchSummary:
    """Dub every video in the batch."""
    if (isinstance(lines, list) and lines
            and all(isinstance(x, BatchItem) for x in lines)):
        items = lines
    else:
        items = parse_lines(lines)
    if not items:
        logger.info("No videos in the batch list.")
        return BatchSummary()

    state_path = state_path or os.path.join(
        req_template.output_dir or settings.output_dir, STATE_FILENAME)
    previous = _load_state(state_path)

    pending: list[BatchItem] = []
    skipped = 0
    for item in items:
        done = previous.get(item.key, {}).get("status") == "success"
        if done and not retry_done:
            logger.info(f"Already done, skipping: {item.label}")
            skipped += 1
            continue
        pending.append(item)

    # Rebuild the state file around this run's list so the on-disk order matches
    # what the user provided, keeping results for videos they kept in the list.
    pending_keys = {item.key for item in pending}
    videos: list[dict] = []
    for item in items:
        entry = dict(previous.get(item.key, {}))
        entry["video_url"] = item.key
        entry["voice"] = item.voice or req_template.voice
        if item.key in pending_keys or not entry.get("status"):
            entry["status"] = "waiting"
        videos.append(entry)
    by_key = {v["video_url"]: v for v in videos}
    for item in pending:
        item.ref = by_key[item.key]

    state = {"output_dir": os.path.dirname(os.path.abspath(state_path)), "videos": videos}

    def flush() -> None:
        _save_json_atomic(state, state_path)

    if not pending:
        logger.info(f"Nothing to do: all {len(items)} video(s) already completed.")
        flush()
        return BatchSummary(total=len(items), skipped=skipped)

    logger.info(f"{len(pending)} video(s) to process, {skipped} already done (concurrency={concurrency})")
    logger.info("=" * 60)
    flush()

    def on_start(item: BatchItem) -> None:
        item.ref["status"] = "processing"
        item.ref.pop("error", None)
        flush()

    def on_result(item: BatchItem, report: dict | None, error: str | None) -> None:
        entry = item.ref
        if report:
            entry["status"] = "success"
            entry["output_folder"] = report.get("session_id", "")
            entry["segments"] = report.get("total_segments", 0)
            entry["duration_original"] = report.get("total_original_duration", 0)
            entry["duration_dub"] = report.get("total_tts_duration", 0)
            entry["processing_time"] = report.get("processing_time_seconds", 0)
            entry.pop("error", None)
        else:
            entry["status"] = "failed"
            entry["error"] = error
        flush()

    if concurrency > 1:
        try:
            summary = _run_items_concurrent(
                pending, settings, req_template, on_result,
                on_start=on_start, observer=observer, concurrency=concurrency,
                export_dir=export_dir,
            )
        finally:
            flush()
        summary.skipped = skipped
        return summary

    synth_cache = None
    demucs_cache = None
    whisper_cache = None
    if pipeline is None:
        if reuse_tts and len(pending) > 1:
            from autodub.speech.tts import SynthCache
            synth_cache = SynthCache()
        if len(pending) > 1:
            from autodub.media.vocal_separator import DemucsCache
            demucs_cache = DemucsCache()
            from autodub.speech.transcriber import WhisperCache
            whisper_cache = WhisperCache()
        pipeline = DubPipeline(settings, synth_cache=synth_cache,
                               demucs_cache=demucs_cache,
                               whisper_cache=whisper_cache)
    try:
        summary = _run_items(pending, pipeline, req_template, on_result,
                             on_start=on_start, observer=observer,
                             export_dir=export_dir)
    finally:
        flush()
        if synth_cache is not None:
            synth_cache.close()
        if demucs_cache is not None:
            demucs_cache.close()
        if whisper_cache is not None:
            whisper_cache.close()
    summary.skipped = skipped
    return summary

