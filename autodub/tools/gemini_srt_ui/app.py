import os
import sys
import math
import json
import subprocess
import threading
import uuid
import time
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
import pysubs2

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=STATIC_DIR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB for video uploads

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

jobs = {}
batch_queues = {}

ALLOWED_EXTENSIONS = {"srt", "ass", "vtt", "mp4", "mkv", "avi", "mov", "mp3", "wav", "aac", "m4a", "webm", "flac"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac"}
ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

JOBS_MAX_LOG_LINES = 1000
JOB_RETENTION_SECONDS = 60 * 60 * 24
UPLOAD_RETENTION_SECONDS = 60 * 60 * 24
CLEANUP_INTERVAL_SECONDS = 10 * 60

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_PARALLEL_FILES = 8
SPEED_MODES = {
    "turbo": {"model": "gemini-2.5-flash", "batch_size": 100, "no_context": True, "parallel": 8},
    "fast": {"model": "gemini-2.5-flash", "batch_size": 60, "no_context": True, "parallel": 4},
    "balanced": {"model": "gemini-2.5-flash", "batch_size": 50, "no_context": False, "parallel": 2},
    "quality": {"model": "gemini-2.5-pro", "batch_size": 30, "no_context": False, "parallel": 1},
}
DEFAULT_SPEED_MODE = "balanced"

KEY_COOLDOWN_SECONDS = 60
CHUNK_MIN_LINES = 60
CHUNK_OVERLAP = 2

_stats_lock = threading.Lock()
_log_lock = threading.Lock()

# Find gst executable path
GST_EXE = shutil.which("gst") or shutil.which("gst.exe")
if not GST_EXE:
    scripts = os.path.join(os.path.dirname(sys.executable), "Scripts")
    for name in ("gst.exe", "gst"):
        candidate = os.path.join(scripts, name)
        if os.path.exists(candidate):
            GST_EXE = candidate
            break


def strip_ansi(text):
    return ANSI_RE.sub("", text).replace("\r", "")


def append_log(job_id, line):
    with _log_lock:
        log = jobs[job_id]["log"]
        log.append(line)
        if len(log) > JOBS_MAX_LOG_LINES:
            del log[:len(log) - JOBS_MAX_LOG_LINES]


def validate_batch_files(files):
    if not isinstance(files, list):
        return None, "files must be a list"
    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            return None, f"files[{idx}] must be an object with filename"
        if not str(item.get("filename") or "").strip():
            return None, f"files[{idx}] must include filename"
    return files, None


def resolve_batch_size(batch_size, total_lines, default_batch=100):
    if isinstance(batch_size, str) and batch_size.strip().isdigit() and int(batch_size) > 0:
        return int(batch_size)
    if total_lines <= 0:
        return default_batch
    return min(default_batch, total_lines)


def get_speed_preset(speed_mode):
    return SPEED_MODES.get((speed_mode or DEFAULT_SPEED_MODE).strip().lower(), SPEED_MODES[DEFAULT_SPEED_MODE])


def resolve_parallel_workers(speed_mode, keys):
    preset = get_speed_preset(speed_mode)
    keys_count = max(1, len(keys) if keys else 1)
    return max(1, min(preset["parallel"], keys_count, MAX_PARALLEL_FILES))


def _run_batch_job(item, index, key_pool):
    job_id = item["job_id"]
    job_data = dict(item["data"])

    job = jobs[job_id]
    if job.get("stop_requested"):
        job["status"] = "stopped"
        return

    if key_pool:
        primary = key_pool.next_key()
        secondary = key_pool.next_key() if key_pool.alive_count() > 1 else None
        job_data["api_key"] = primary
        job_data["api_key2"] = secondary
        append_log(job_id, f"Key được gán: {KeyPool.mask(primary)}" + (f" + {KeyPool.mask(secondary)}" if secondary else ""))

    job_data["key_pool"] = key_pool
    job_data["_batch"] = True

    job["status"] = "running"
    job["start_time"] = time.time()
    _run_translation(job_id, job_data)


def _referenced_paths(now):
    cutoff = now - JOB_RETENTION_SECONDS
    paths = set()
    for job in jobs.values():
        status = job.get("status")
        keep = status not in ("done", "error") or job.get("start_time", 0) >= cutoff
        if keep:
            for key in ("input_file_path", "out_file_path"):
                path = job.get(key)
                if path:
                    paths.add(os.path.normcase(os.path.abspath(path)))
    return paths


def cleanup_old_state():
    now = time.time()
    cutoff = now - JOB_RETENTION_SECONDS
    active_paths = _referenced_paths(now)

    for job_id in list(jobs):
        job = jobs[job_id]
        if job.get("status") in ("done", "error") and job.get("start_time", 0) < cutoff:
            del jobs[job_id]

    for batch_id in list(batch_queues):
        batch = batch_queues[batch_id]
        if batch.get("status") == "done" and batch.get("start_time", 0) < cutoff:
            del batch_queues[batch_id]

    file_cutoff = now - UPLOAD_RETENTION_SECONDS
    for folder in (UPLOAD_FOLDER, OUTPUT_FOLDER):
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            if os.path.normcase(os.path.abspath(path)) in active_paths:
                continue
            if folder == OUTPUT_FOLDER and not name.startswith("temp_"):
                continue
            try:
                if os.path.getmtime(path) < file_cutoff:
                    os.remove(path)
            except OSError:
                pass


def _cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cleanup_old_state()


threading.Thread(target=_cleanup_loop, daemon=True).start()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def format_timestamp(ms):
    td = max(0, int(ms))
    hours = td // 3600000
    minutes = (td % 3600000) // 60000
    seconds = (td % 60000) // 1000
    millis = td % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def load_subtitles_safe(filepath):
    """Load subtitle file using pysubs2 with encoding fallbacks."""
    if not os.path.exists(filepath):
        return []
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "gb18030"]:
        try:
            subs = pysubs2.load(filepath, encoding=enc)
            return subs
        except Exception:
            continue
    return []


# --- Routes -------------------------------------------------------------------

@app.route("/")
def index():
    response = send_from_directory(STATIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/voxdub/config", methods=["GET"])
def get_voxdub_config_endpoint():
    try:
        from autodub.tools.gemini_srt_ui.server_manager import GeminiSrtServerManager
        cfg = GeminiSrtServerManager.get_voxdub_config()
        return jsonify({"ok": True, "config": cfg})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/voxdub/pending_project", methods=["GET"])
def get_voxdub_pending_project_endpoint():
    """Lấy thông tin file phụ đề từ dự án đang chờ dịch."""
    try:
        from autodub.tools.gemini_srt_ui.server_manager import get_server_manager
        mgr = get_server_manager()
        preload = request.args.get("preload")
        if preload:
            safe_name = secure_filename(preload)
            fpath = os.path.join(UPLOAD_FOLDER, safe_name)
            if os.path.exists(fpath):
                subs = load_subtitles_safe(fpath)
                display_name = safe_name[33:] if len(safe_name) > 33 else safe_name
                return jsonify({
                    "ok": True,
                    "file": {
                        "filename": safe_name,
                        "original": display_name,
                        "line_count": len(subs),
                        "file_type": "subtitle",
                        "work_dir": (mgr.pending_file or {}).get("work_dir", ""),
                    }
                })
        if mgr.pending_file:
            return jsonify({"ok": True, "file": mgr.pending_file})
        return jsonify({"ok": False, "file": None})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    filename = secure_filename(file.filename)
    unique_name = uuid.uuid4().hex + "_" + filename
    filepath = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(filepath)

    ext = os.path.splitext(filename)[1].lower()
    line_count = 0
    file_type = "subtitle"
    if ext in SUBTITLE_EXTENSIONS:
        subs = load_subtitles_safe(filepath)
        line_count = len(subs)
    elif ext in VIDEO_EXTENSIONS:
        file_type = "video"
    elif ext in AUDIO_EXTENSIONS:
        file_type = "audio"

    return jsonify({
        "filename": unique_name,
        "original": filename,
        "line_count": line_count,
        "file_type": file_type,
        "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2)
    })


def extract_api_keys(raw_input):
    """Cleanly parse multiple API keys from text or list with newline/comma/escaped split."""
    if not raw_input:
        return []
    if isinstance(raw_input, list):
        items = raw_input
    else:
        text = str(raw_input).replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n")
        text = text.replace(",", "\n").replace(";", "\n").replace("|", "\n")
        items = text.splitlines()

    keys = []
    for line in items:
        k = line.strip().strip("\"'").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def collect_keys(data):
    """Merge API keys from api_keys/api_key/api_key2 fields into a deduped list."""
    keys = []
    for src in (data.get("api_keys"), data.get("api_key"), data.get("api_key2")):
        for k in extract_api_keys(src):
            if k not in keys:
                keys.append(k)
    return keys


def is_valid_key_format(key):
    """Check whether a key looks like a valid Gemini API key (AI Studio or Enterprise)."""
    k = (key or "").strip()
    return k.startswith("AIza") or k.startswith("AQ.")


def _test_key(key):
    """Test whether a single key authenticates against Google Gemini.

    AQ. (express) keys work as plain API keys via the standard endpoint; the
    enterprise flag requires OAuth/project credentials, so it is not used here.
    """
    try:
        from google import genai
        client = genai.Client(api_key=key)
        for _ in client.models.list():
            break
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def validate_keys(keys):
    """Validate keys against Google in parallel, returning (valid_list, invalid_list)."""
    targets = [k for k in (keys or []) if is_valid_key_format(k)]
    valid = []
    invalid = []
    seen = set()
    for k in (keys or []):
        if k in seen:
            continue
        seen.add(k)
        if not is_valid_key_format(k):
            invalid.append((k, "Sai định dạng (phải bắt đầu bằng AIza... hoặc AQ.)"))
    if not targets:
        return valid, invalid

    with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as ex:
        futures = {ex.submit(_test_key, k): k for k in targets}
        for fut in futures:
            k = futures[fut]
            ok, err = fut.result()
            if ok:
                valid.append(k)
            else:
                invalid.append((k, err))
    return valid, invalid


class KeyPool:
    """Thread-safe pool of Gemini API keys.

    Distributes keys round-robin by least-recently-used, cools down keys on
    rate-limit (429) errors, and permanently drops keys on auth errors (401/403).
    """

    def __init__(self, keys):
        self.keys = list(keys or [])
        self.total_entered = len(self.keys)
        self._lock = threading.Lock()
        self._last_used = {}
        self._cooldown_until = {}
        self._dead = set()

    def next_key(self):
        with self._lock:
            now = time.time()
            candidates = [
                k for k in self.keys
                if k not in self._dead and self._cooldown_until.get(k, 0.0) <= now
            ]
            if not candidates:
                candidates = [k for k in self.keys if k not in self._dead]
            if not candidates:
                return None
            candidates.sort(key=lambda k: self._last_used.get(k, 0.0))
            key = candidates[0]
            self._last_used[key] = now
            return key

    def mark_error(self, key, err_str):
        if not key:
            return
        lower = (err_str or "").lower()
        with self._lock:
            if any(t in lower for t in ("401", "unauthenticated", "api_key_invalid",
                                         "access_token_type_unsupported", "permission_denied")):
                self._dead.add(key)
            elif any(t in lower for t in ("429", "resource_exhausted", "quota", "rate limit")):
                self._cooldown_until[key] = time.time() + KEY_COOLDOWN_SECONDS

    def alive_count(self):
        with self._lock:
            return sum(1 for k in self.keys if k not in self._dead)

    @staticmethod
    def mask(key):
        if not key:
            return "(none)"
        return key[:6] + "..." + key[-4:]


@app.route("/api/models", methods=["POST"])
def list_models():
    data = request.json or {}
    keys = collect_keys(data)
    if not keys:
        return jsonify({"error": "Vui lòng nhập ít nhất 1 Gemini API Key hợp lệ"}), 400

    valid_keys, invalid_results = validate_keys(keys)
    if not valid_keys:
        return jsonify({"error": "Không có API Key hoạt động. Tất cả key đều không hợp lệ, sai định dạng hoặc hết quota."}), 400

    test_key = valid_keys[0]

    try:
        from google import genai
        client = genai.Client(api_key=test_key)
        raw_models = client.models.list()

        models = []
        for m in raw_models:
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" in actions:
                name = (m.name or "").replace("models/", "").strip()
                if name and name not in models:
                    models.append(name)

        priority_order = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        sorted_models = []
        for p in priority_order:
            if p in models:
                sorted_models.append(p)
        for m in models:
            if m not in sorted_models:
                sorted_models.append(m)

        if not sorted_models:
            sorted_models = priority_order

        return jsonify({
            "models": sorted_models,
            "submitted_keys_count": len(keys),
            "valid_count": len(valid_keys),
            "valid_keys": valid_keys,
            "total": len(keys),
        })

    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "UNAUTHENTICATED" in err_str or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_str:
            msg = "API Key không hợp lệ hoặc sai loại (Lỗi 401 UNAUTHENTICATED). Key Google AI Studio chuẩn bắt đầu bằng 'AIzaSy...'. Vui lòng lấy key miễn phí tại: https://aistudio.google.com/app/apikey"
        elif "API_KEY_INVALID" in err_str or "API key not valid" in err_str or "400" in err_str:
            msg = "API Key không hợp lệ. Vui lòng kiểm tra lại trên Google AI Studio (https://aistudio.google.com/app/apikey)."
        elif "PERMISSION_DENIED" in err_str or "403" in err_str:
            msg = "API Key bị từ chối quyền truy cập (Permission Denied)."
        elif "RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "quota" in err_str.lower():
            msg = "API Key đã hết hạn mức (Quota limit/Rate limit)."
        elif "Connection" in err_str or "timeout" in err_str.lower() or "wsasend" in err_str.lower() or "wsarecv" in err_str.lower():
            msg = "Lỗi kết nối mạng đến máy chủ Google Gemini. Vui lòng kiểm tra Internet/VPN."
        else:
            msg = f"Lỗi API: {err_str[:200]}"
        return jsonify({"error": msg}), 400


# --- Translation & Batch Endpoints ---------------------------------------------

@app.route("/api/translate", methods=["POST"])
def translate():
    data = request.json or {}
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "current_lines": 0,
        "total_lines": 0,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "speed_lps": 0.0,
        "eta_sec": 0.0,
        "log": [],
        "output_file": None,
        "input_file_path": None,
        "out_file_path": None,
        "error": None,
        "start_time": time.time(),
        "process": None,
        "stop_requested": False,
    }
    t = threading.Thread(target=_run_translation, args=(job_id, data), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/batch_translate", methods=["POST"])
def batch_translate():
    """Handle queue of multiple files translating sequentially."""
    data = request.json or {}
    files_list, files_error = validate_batch_files(data.get("files") or [])
    if files_error:
        return jsonify({"error": files_error}), 400
    if not files_list:
        return jsonify({"error": "No files provided in batch"}), 400

    keys_pool = collect_keys(data)
    valid_keys, _invalid = validate_keys(keys_pool)
    if not valid_keys:
        return jsonify({"error": "Không có API Key hoạt động. Vui lòng kiểm tra lại key (đúng định dạng AIza... và chưa hết quota)."}), 400
    key_pool = KeyPool(valid_keys)
    key_pool.total_entered = len(keys_pool)
    speed_mode = (data.get("speed_mode") or DEFAULT_SPEED_MODE).strip().lower()
    parallel_workers = resolve_parallel_workers(speed_mode, valid_keys)

    batch_id = str(uuid.uuid4())
    batch_jobs = []

    for f_info in files_list:
        job_id = str(uuid.uuid4())
        job_data = {**data, **f_info}
        jobs[job_id] = {
            "status": "pending",
            "progress": 0,
            "current_lines": 0,
            "total_lines": f_info.get("line_count", 0),
            "speed_lps": 0.0,
            "eta_sec": 0.0,
            "log": [],
            "output_file": None,
            "original_name": f_info.get("original", "subtitle.srt"),
            "input_file": f_info.get("filename"),
            "error": None,
            "start_time": time.time(),
            "process": None,
            "stop_requested": False,
        }
        batch_jobs.append({"job_id": job_id, "data": job_data, "name": f_info.get("original")})

    batch_queues[batch_id] = {
        "batch_id": batch_id,
        "jobs": batch_jobs,
        "status": "running",
        "current_index": 0,
        "total_files": len(batch_jobs),
        "failed_files": [],
        "keys_pool": keys_pool,
        "key_pool": key_pool,
        "parallel_workers": parallel_workers,
        "start_time": time.time(),
    }

    t = threading.Thread(target=_run_batch_worker, args=(batch_id,), daemon=True)
    t.start()

    return jsonify({
        "batch_id": batch_id,
        "total_files": len(batch_jobs),
        "parallel_workers": parallel_workers,
        "jobs": [{"job_id": j["job_id"], "name": j["name"]} for j in batch_jobs]
    })


def _run_batch_worker(batch_id):
    batch = batch_queues.get(batch_id)
    if not batch:
        return

    key_pool = batch.get("key_pool")
    workers = batch.get("parallel_workers") or 1
    items = batch["jobs"]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_run_batch_job, item, index, key_pool)
            for index, item in enumerate(items)
        ]
        for future in futures:
            future.result()

    batch["current_index"] = len(items)
    batch["failed_files"] = [
        str(item.get("name") or "unknown")
        for item in items
        if jobs.get(item["job_id"], {}).get("status") == "error"
    ]
    if batch.get("status") != "stopped":
        batch["status"] = "done"


@app.route("/api/batch_status/<batch_id>")
def batch_status(batch_id):
    batch = batch_queues.get(batch_id)
    if not batch:
        return jsonify({"error": "Batch queue not found"}), 404

    jobs_summary = []
    completed_count = 0
    failed_count = 0
    stopped_count = 0
    total_lines = 0
    translated_lines = 0

    for item in batch["jobs"]:
        jid = item["job_id"]
        j = jobs.get(jid, {})
        status = j.get("status", "pending")
        if status == "done":
            completed_count += 1
        elif status == "error":
            failed_count += 1
        elif status == "stopped":
            stopped_count += 1
        total_lines += j.get("total_lines", 0)
        translated_lines += j.get("current_lines", 0)

        jobs_summary.append({
            "job_id": jid,
            "name": item["name"],
            "status": status,
            "progress": j.get("progress", 0),
            "output_file": j.get("output_file"),
            "error": j.get("error"),
            "social_metadata": get_social_metadata_safe(jid, j),
        })

    processed_count = completed_count + failed_count + stopped_count
    overall_pct = int((processed_count / batch["total_files"]) * 100) if batch["total_files"] > 0 else 0

    failed_files = list(batch.get("failed_files") or [])
    for item in batch["jobs"]:
        if jobs.get(item["job_id"], {}).get("status") == "error":
            name = str(item.get("name") or "unknown")
            if name not in failed_files:
                failed_files.append(name)

    return jsonify({
        "batch_id": batch_id,
        "status": batch["status"],
        "completed_files": completed_count,
        "failed_files": failed_files,
        "stopped_files": stopped_count,
        "total_files": batch["total_files"],
        "overall_progress": overall_pct,
        "total_lines": total_lines,
        "translated_lines": translated_lines,
        "jobs": jobs_summary,
    })


def get_social_metadata_safe(job_id: str, job: dict | None = None) -> dict | None:
    """Retrieve or compute social metadata (title, hashtags, description) for a completed job."""
    if not job:
        job = jobs.get(job_id, {})
    if not job:
        return None

    # Check if job already has social_metadata cached
    if "social_metadata" in job and isinstance(job["social_metadata"], dict):
        return job["social_metadata"]

    filename = job.get("original_name") or job.get("original") or (os.path.basename(job.get("input_file_path") or "") if job.get("input_file_path") else "") or "video"
    base_title = os.path.splitext(filename)[0] if filename else "Video"

    meta_candidates = []
    meta_candidates.append(os.path.join(OUTPUT_FOLDER, f"meta_{job_id}.json"))

    out_file = job.get("out_file_path") or (os.path.join(OUTPUT_FOLDER, job.get("output_file")) if job.get("output_file") else None)
    if out_file:
        meta_candidates.append(os.path.join(os.path.dirname(out_file), "youtube", "youtube_metadata.json"))
        meta_candidates.append(os.path.join(os.path.dirname(out_file), "youtube_metadata.json"))
        meta_candidates.append(os.path.join(os.path.dirname(os.path.dirname(out_file)), "youtube", "youtube_metadata.json"))

    input_file = job.get("input_file_path")
    if input_file:
        meta_candidates.append(os.path.join(os.path.dirname(input_file), "youtube", "youtube_metadata.json"))
        meta_candidates.append(os.path.join(os.path.dirname(input_file), "youtube_metadata.json"))

    meta_data = {}
    for cand in meta_candidates:
        if os.path.isfile(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and (data.get("title") or data.get("hashtags")):
                    meta_data = data
                    break
            except Exception:
                pass

    title = meta_data.get("title") or ""
    description = meta_data.get("description") or ""
    hashtags = meta_data.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = [h.strip() for h in hashtags.split() if h.strip()]
    elif not isinstance(hashtags, list):
        hashtags = []

    formatted_tags = []
    for tag in hashtags:
        t = str(tag).strip()
        if t:
            if not t.startswith("#"):
                t = "#" + t
            formatted_tags.append(t)

    # Fallback default title/tags when job is finished
    if not title and job.get("status") == "done":
        clean_name = re.sub(r"[_\-]+", " ", base_title).strip()
        title = f"{clean_name.title()} — Bản Lồng Tiếng Việt"
        if not formatted_tags:
            formatted_tags = ["#shorts", "#reviewphim", "#trending", "#viral", "#xuhuong", "#phimhay"]

    if not title and not formatted_tags:
        return None

    hashtags_str = " ".join(formatted_tags)
    full_text = f"Tiêu đề: {title}\n\nMô tả: {description}\n\nHashtags:\n{hashtags_str}".strip()

    social_meta = {
        "filename": filename,
        "title": title,
        "description": description,
        "hashtags": formatted_tags,
        "hashtags_str": hashtags_str,
        "full_text": full_text,
    }
    job["social_metadata"] = social_meta
    return social_meta


@app.route("/api/status/<job_id>")
def job_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    job = jobs[job_id]

    now = time.time()
    elapsed = max(0.1, now - job["start_time"])
    progress = job["progress"]
    total = job["total_lines"]
    current = job["current_lines"]

    if current == 0 and total > 0 and progress > 0:
        current = int((progress / 100.0) * total)

    speed = (current / elapsed) if (elapsed > 0 and current > 0) else 0.0
    
    eta = 0.0
    if job["status"] == "running":
        if speed > 0 and total > current:
            eta = (total - current) / speed
        elif progress > 0 and progress < 100:
            total_est = elapsed / (progress / 100.0)
            eta = max(0.0, total_est - elapsed)

    include_subtitles = request.args.get("include_subtitles", "1") != "0"

    # Load live subtitle lines
    subtitles = []
    if include_subtitles:
        input_path = job.get("input_file_path")
        out_path = job.get("out_file_path")

        orig_subs = load_subtitles_safe(input_path) if input_path else []
        trans_subs = load_subtitles_safe(out_path) if out_path else []

        max_len = max(len(orig_subs), len(trans_subs))
        if max_len > 0:
            for idx in range(max_len):
                orig_ev = orig_subs[idx] if idx < len(orig_subs) else None
                trans_ev = trans_subs[idx] if idx < len(trans_subs) else None

                start_ms = orig_ev.start if orig_ev else (trans_ev.start if trans_ev else 0)
                end_ms = orig_ev.end if orig_ev else (trans_ev.end if trans_ev else 0)

                orig_text = orig_ev.text.replace(r"\N", "\n") if orig_ev else ""
                trans_text = trans_ev.text.replace(r"\N", "\n") if trans_ev else ""

                duration_sec = max(0.1, (end_ms - start_ms) / 1000.0)
                cps = round(len(trans_text) / duration_sec, 1) if trans_text else 0.0

                subtitles.append({
                    "index": idx + 1,
                    "start": format_timestamp(start_ms),
                    "end": format_timestamp(end_ms),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "cps": cps,
                    "original": orig_text,
                    "translated": trans_text,
                })

    return jsonify({
        "status":        job["status"],
        "progress":      job["progress"],
        "current_lines": current,
        "total_lines":   total,
        "speed_lps":     round(speed, 1),
        "eta_sec":       round(eta, 1),
        "elapsed_sec":   round(elapsed, 1),
        "prompt_tokens": job.get("prompt_tokens", 0),
        "output_tokens": job.get("output_tokens", 0),
        "log":           job["log"][-200:],
        "output_file":   job["output_file"],
        "error":         job["error"],
        "subtitles":     subtitles,
        "social_metadata": get_social_metadata_safe(job_id, job),
    })


def _terminate_job_process(job):
    for proc in job.get("processes") or []:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    proc = job.get("process")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass


@app.route("/api/stop/<job_id>", methods=["POST"])
def stop_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job["stop_requested"] = True
    if job.get("status") in ("running", "pending"):
        job["status"] = "stopped"
    _terminate_job_process(job)
    append_log(job_id, "Đã dừng theo yêu cầu người dùng.")
    return jsonify({"success": True, "status": job["status"]})


@app.route("/api/batch_stop/<batch_id>", methods=["POST"])
def stop_batch(batch_id):
    batch = batch_queues.get(batch_id)
    if not batch:
        return jsonify({"error": "Batch queue not found"}), 404

    batch["status"] = "stopped"
    for item in batch["jobs"]:
        job = jobs.get(item["job_id"])
        if not job:
            continue
        job["stop_requested"] = True
        if job.get("status") in ("running", "pending"):
            job["status"] = "stopped"
        _terminate_job_process(job)

    return jsonify({"success": True, "status": batch["status"]})


@app.route("/api/save_subtitles", methods=["POST"])
def save_subtitles():
    """Save user edits to the translated subtitle file."""
    data = request.json or {}
    filename = (data.get("filename") or "").strip()
    items = data.get("subtitles") or []

    if not filename:
        return jsonify({"error": "No filename provided"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "No subtitle items provided"}), 400

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return jsonify({"error": f"subtitles[{i}] must be an object"}), 400
        for key in ("start_ms", "end_ms"):
            if key in item:
                try:
                    int(item[key])
                except (TypeError, ValueError, OverflowError):
                    return jsonify({"error": f"subtitles[{i}].{key} must be an integer"}), 400

    safe_name = secure_filename(filename)
    filepath = os.path.join(OUTPUT_FOLDER, safe_name)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found on server"}), 404

    try:
        subs = load_subtitles_safe(filepath)
        if not subs:
            subs = pysubs2.SSAFile()

        while len(subs) < len(items):
            subs.append(pysubs2.SSAEvent(start=0, end=0, text=""))

        for i, item in enumerate(items):
            if i < len(subs):
                if "start_ms" in item:
                    subs[i].start = int(item["start_ms"])
                if "end_ms" in item:
                    subs[i].end = int(item["end_ms"])
                text = (item.get("translated") or item.get("text") or "").replace("\n", r"\N")
                subs[i].text = text

        subs.save(filepath, encoding="utf-8")
        return jsonify({"success": True, "count": len(items)})

    except Exception as e:
        return jsonify({"error": f"Failed to save subtitles: {e}"}), 500


@app.route("/api/shift_timing", methods=["POST"])
def shift_timing():
    """Shift subtitle timecodes by offset_ms."""
    data = request.json or {}
    filename = (data.get("filename") or "").strip()

    try:
        offset_ms = int(data.get("offset_ms", 0))
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "offset_ms must be an integer"}), 400

    if not filename or offset_ms == 0:
        return jsonify({"error": "Invalid filename or zero offset"}), 400

    safe_name = secure_filename(filename)
    filepath = os.path.join(OUTPUT_FOLDER, safe_name)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    try:
        subs = load_subtitles_safe(filepath)
        subs.shift(ms=offset_ms)
        subs.save(filepath, encoding="utf-8")
        return jsonify({"success": True, "shifted_ms": offset_ms})
    except Exception as e:
        return jsonify({"error": f"Failed to shift timing: {e}"}), 500


@app.route("/api/export_format", methods=["GET"])
def export_format():
    """Export subtitle in desired format (.srt, .ass, .vtt, .txt)."""
    filename = request.args.get("filename", "")
    target_format = request.args.get("format", "srt").lower().strip()
    allowed_formats = {"srt", "vtt", "ass", "txt_bilingual", "txt_plain"}

    if not filename:
        return jsonify({"error": "Filename required"}), 400
    if target_format not in allowed_formats:
        return jsonify({"error": f"Unsupported export format: {target_format}"}), 400

    safe = secure_filename(filename)
    filepath = os.path.join(OUTPUT_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    base_name = safe[33:] if len(safe) > 33 else safe
    base_no_ext = os.path.splitext(base_name)[0]

    subs = load_subtitles_safe(filepath)
    if not subs:
        return jsonify({"error": "Cannot load subtitle file"}), 500

    def temp_export_path(out_name):
        return os.path.join(OUTPUT_FOLDER, f"temp_{uuid.uuid4().hex}_{out_name}")

    if target_format == "srt":
        out_name = f"{base_no_ext}.srt"
        out_path = temp_export_path(out_name)
        subs.save(out_path, format_="srt", encoding="utf-8")
        return send_file(out_path, as_attachment=True, download_name=out_name)

    if target_format == "vtt":
        out_name = f"{base_no_ext}.vtt"
        out_path = temp_export_path(out_name)
        subs.save(out_path, format_="vtt", encoding="utf-8")
        return send_file(out_path, as_attachment=True, download_name=out_name)

    if target_format == "ass":
        out_name = f"{base_no_ext}.ass"
        out_path = temp_export_path(out_name)
        subs.save(out_path, format_="ass", encoding="utf-8")
        return send_file(out_path, as_attachment=True, download_name=out_name)

    if target_format == "txt_bilingual":
        out_name = f"{base_no_ext}_bilingual.txt"
        out_path = temp_export_path(out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            for i, ev in enumerate(subs, 1):
                clean_text = ev.text.replace(r"\N", "\n")
                f.write(f"[{i}] {format_timestamp(ev.start)} --> {format_timestamp(ev.end)}\n{clean_text}\n\n")
        return send_file(out_path, as_attachment=True, download_name=out_name)

    out_name = f"{base_no_ext}_plain.txt"
    out_path = temp_export_path(out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        for ev in subs:
            clean_text = ev.text.replace(r"\N", " ")
            f.write(f"{clean_text}\n")
    return send_file(out_path, as_attachment=True, download_name=out_name)


@app.route("/api/export_zip", methods=["POST"])
def export_zip():
    """Bundle translated files into a single ZIP archive."""
    data = request.json or {}
    filenames = data.get("filenames") or []
    if not filenames:
        return jsonify({"error": "No filenames provided"}), 400

    zip_uuid = uuid.uuid4().hex
    zip_filename = f"Gemini_Subtitles_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{zip_uuid[:6]}.zip"
    zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for fname in filenames:
            safe = secure_filename(fname)
            fpath = os.path.join(OUTPUT_FOLDER, safe)
            if os.path.exists(fpath):
                display = safe[33:] if len(safe) > 33 else safe
                zipf.write(fpath, arcname=display)

    return jsonify({"zip_url": f"/api/download/{zip_filename}", "filename": zip_filename})


@app.route("/api/download/<path:filename>")
def download_file(filename):
    safe = secure_filename(filename)
    filepath = os.path.join(OUTPUT_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    display_name = safe[33:] if len(safe) > 33 else safe
    return send_file(filepath, as_attachment=True, download_name=display_name)


# --- Translation Worker --------------------------------------------------------

def _build_gst_cmd(is_sub, input_path, out_path, target_lang, model_name,
                   description, effective_batch_size, temperature, start_line, no_context):
    cmd = [GST_EXE, "translate"]
    if is_sub:
        cmd += ["-i", input_path]
    else:
        cmd += ["-v", input_path]

    cmd += [
        "-l", target_lang,
        "-o", out_path,
        "--model", model_name,
        "--no-colors",
        "--skip-upgrade",
        "--no-resume",
        "--no-streaming",
    ]

    if "2.5" in model_name and "flash" in model_name:
        cmd += ["--thinking-budget", "0"]
    elif "2.5" in model_name and "pro" in model_name:
        cmd += ["--thinking-budget", "128"]

    if description:
        cmd += ["--description", description]
    if effective_batch_size:
        cmd += ["--batch-size", str(effective_batch_size)]
    if temperature:
        try:
            float(temperature)
            cmd += ["--temperature", temperature]
        except ValueError:
            pass
    if start_line and str(start_line).isdigit() and int(start_line) > 0:
        cmd += ["--start-line", str(start_line)]
    if no_context:
        cmd += ["--no-context"]
    return cmd


def _build_env(api_key, api_key2=None):
    env = {
        **os.environ,
        "GEMINI_API_KEY": api_key,
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    if api_key2:
        env["GEMINI_API_KEY2"] = api_key2
    return env


def _run_gst_process(job_id, job, cmd, env, out_path, on_progress=None):
    """Run a single gst subprocess, streaming output into the job log.

    Returns {"ok": bool, "stopped": bool, "error": str|None}.
    """
    state = {"last_count": -1, "last_pct": -1}

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    job["process"] = proc
    job.setdefault("processes", []).append(proc)

    for raw_line in proc.stdout:
        if job.get("stop_requested"):
            break
        line = strip_ansi(raw_line).rstrip()
        if not line or line.startswith("Validating token size") or line.startswith("Token size validated"):
            continue

        m_tok = re.search(r"Prompt Tokens:\s*(\d+).*?Output Tokens:\s*(\d+)", line)
        if m_tok:
            with _stats_lock:
                job["prompt_tokens"] = job.get("prompt_tokens", 0) + int(m_tok.group(1))
                job["output_tokens"] = job.get("output_tokens", 0) + int(m_tok.group(2))

        m_count = re.search(r"\((\d+)/(\d+)\)", line)
        if m_count:
            cur, tot = int(m_count.group(1)), int(m_count.group(2))
            if on_progress:
                on_progress(cur, tot)
            else:
                job["current_lines"] = cur
                job["total_lines"] = tot
                if tot > 0:
                    job["progress"] = min(100, int((cur / tot) * 100))
            if cur <= state["last_count"]:
                continue
            state["last_count"] = cur
            append_log(job_id, line)
            continue

        m_pct = re.search(r"(\d{1,3})\s*%", line)
        if m_pct:
            pct = int(m_pct.group(1))
            if 0 <= pct <= 100:
                if on_progress:
                    on_progress(pct, None)
                else:
                    job["progress"] = pct
                    if job["total_lines"] > 0:
                        job["current_lines"] = int((pct / 100.0) * job["total_lines"])
                if pct <= state["last_pct"]:
                    continue
                state["last_pct"] = pct
                append_log(job_id, line)
                continue

        append_log(job_id, line)

    proc.wait()

    if job.get("stop_requested"):
        return {"ok": False, "stopped": True, "error": None}

    if proc.returncode != 0:
        last = "\n".join(job["log"][-15:])
        return {"ok": False, "stopped": False, "error": f"exit code {proc.returncode}: {last}"}

    if not os.path.exists(out_path):
        return {"ok": False, "stopped": False, "error": "Không tìm thấy file kết quả sau khi dịch xong."}

    return {"ok": True, "stopped": False, "error": None}


def _plan_chunk_count(total_lines, alive_keys, preset_parallel):
    k = min(preset_parallel, alive_keys)
    if k <= 1 or total_lines < CHUNK_MIN_LINES:
        return 1
    while k > 1 and (total_lines / k) < CHUNK_MIN_LINES:
        k -= 1
    return k


def _translate_chunked(job_id, job, key_pool, orig_subs, out_path,
                       target_lang, model_name, description, effective_batch_size,
                       temperature, no_context, preset_parallel):
    """Split a subtitle file into chunks, translate them in parallel with
    distinct API keys, then merge the results back in order."""
    total = len(orig_subs)
    k = _plan_chunk_count(total, key_pool.alive_count(), preset_parallel)
    if k <= 1:
        return {"ok": False, "stopped": False, "error": "Phân luồng không khả dụng"}

    base = math.ceil(total / k)
    chunks = []
    for i in range(k):
        core_start = i * base
        if core_start >= total:
            break
        core_end = min(total, core_start + base)
        input_start = max(0, core_start - CHUNK_OVERLAP)
        chunks.append({
            "i": i,
            "core_start": core_start,
            "core_end": core_end,
            "input_start": input_start,
        })
    k = len(chunks)

    append_log(job_id, f"Phân luồng song song: {total} dòng -> {k} đoạn (mỗi đoạn ~{base} dòng) dùng {k} API Keys")

    # Write chunk input files
    for c in chunks:
        chunk_subs = pysubs2.SSAFile()
        for ev in orig_subs[c["input_start"]:c["core_end"]]:
            chunk_subs.append(ev)
        c["in_path"] = os.path.join(OUTPUT_FOLDER, f"temp_{job_id[:8]}_in{c['i']}.srt")
        c["out_path"] = os.path.join(OUTPUT_FOLDER, f"temp_{job_id[:8]}_out{c['i']}.srt")
        chunk_subs.save(c["in_path"], format_="srt", encoding="utf-8")

    # Assign a distinct key to each chunk
    chunk_keys = [key_pool.next_key() for _ in range(k)]

    progress_lock = threading.Lock()
    chunk_done = {c["i"]: 0 for c in chunks}

    def make_progress_cb(c):
        def cb(val, tot):
            with progress_lock:
                if tot is not None:
                    chunk_done[c["i"]] = val
                else:
                    chunk_done[c["i"]] = int((val / 100.0) * (c["core_end"] - c["input_start"]))
                done = sum(chunk_done.values())
                job["current_lines"] = min(total, done)
                job["progress"] = min(100, int((done / total) * 100)) if total else 0
        return cb

    def run_chunk(c, key):
        cmd = _build_gst_cmd(True, c["in_path"], c["out_path"], target_lang, model_name,
                             description, effective_batch_size, temperature, None, no_context)
        env = _build_env(key, None)
        res = _run_gst_process(job_id, job, cmd, env, c["out_path"], on_progress=make_progress_cb(c))
        return c, key, res

    results = {}
    try:
        with ThreadPoolExecutor(max_workers=k) as executor:
            futures = [executor.submit(run_chunk, c, chunk_keys[idx]) for idx, c in enumerate(chunks)]
            for fut in futures:
                c, key, res = fut.result()
                results[c["i"]] = (c, key, res)
                if not res["ok"] and not res["stopped"]:
                    key_pool.mark_error(key, res["error"] or "")
                    append_log(job_id, f"Đoạn {c['i'] + 1} lỗi (key {KeyPool.mask(key)}): {res['error']}")

        if job.get("stop_requested"):
            return {"ok": False, "stopped": True, "error": None}

        errors = []
        for c in chunks:
            _, key, res = results[c["i"]]
            if not res["ok"]:
                errors.append(f"Đoạn {c['i'] + 1} (key {KeyPool.mask(key)}): {res.get('error')}")
        if errors:
            return {"ok": False, "stopped": False, "error": " ; ".join(errors)}

        # Merge translated chunks in order
        merged = pysubs2.SSAFile()
        for c in chunks:
            out_subs = load_subtitles_safe(c["out_path"])
            offset = c["core_start"] - c["input_start"]
            keep = c["core_end"] - c["core_start"]
            if len(out_subs) < offset + keep:
                append_log(job_id, f"Cảnh báo: đoạn {c['i'] + 1} có {len(out_subs)} dòng, dự kiến {offset + keep}")
            for ev in out_subs[offset:offset + keep]:
                merged.append(ev)

        merged.save(out_path, encoding="utf-8")
        job["total_lines"] = total
        return {"ok": True, "stopped": False, "error": None}
    finally:
        for c in chunks:
            for p in (c.get("in_path"), c.get("out_path")):
                if p:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass


def _has_cjk(text):
    """Return True if text contains a significant amount of CJK (Chinese/Japanese/Korean) characters."""
    if not text:
        return False
    cjk_count = sum(
        1 for c in text
        if (0x4E00 <= ord(c) <= 0x9FFF)    # CJK Unified Ideographs (Chinese/Japanese)
        or (0x3400 <= ord(c) <= 0x4DBF)    # CJK Extension A
        or (0xAC00 <= ord(c) <= 0xD7AF)    # Korean Hangul syllables
        or (0x3040 <= ord(c) <= 0x30FF)    # Hiragana + Katakana
    )
    return cjk_count >= 2  # at least 2 CJK chars = likely untranslated


def _retranslate_untranslated(job_id, out_path, target_lang, model_name, key_pool):
    """Scan completed SRT for lines still containing CJK characters and re-translate them.

    This handles the case where gst skipped batches due to repeated errors
    (Expected N lines, got N-1) or 503 overload — those lines remain in the
    source language in the output file.
    """
    try:
        subs = pysubs2.load(out_path, encoding="utf-8")
    except Exception as e:
        append_log(job_id, f"[Hậu xử lý] Không đọc được file output: {e}")
        return

    # Collect indices of untranslated lines
    untranslated_idx = [
        i for i, s in enumerate(subs)
        if _has_cjk(s.plaintext.strip())
    ]

    if not untranslated_idx:
        return

    append_log(job_id, "-" * 50)
    append_log(job_id, f"[Hậu xử lý] Phát hiện {len(untranslated_idx)} dòng còn sót chữ CJK — đang dịch lại...")

    # Re-translate in batches of 10
    BATCH = 10
    translated_count = 0
    try:
        from google import genai as _genai
    except ImportError:
        append_log(job_id, "[Hậu xử lý] Không import được google-genai, bỏ qua.")
        return

    for start in range(0, len(untranslated_idx), BATCH):
        chunk_idx = untranslated_idx[start:start + BATCH]
        lines_payload = [
            {"index": str(ci), "text": subs[ci].plaintext.strip()}
            for ci in chunk_idx
        ]
        key = key_pool.next_key() if key_pool else None
        if not key:
            append_log(job_id, "[Hậu xử lý] Không còn API key hoạt động, dừng dịch lại.")
            break
        try:
            client = _genai.Client(api_key=key)
            prompt = (
                f"Translate ONLY the 'text' field of each JSON object to {target_lang}.\n"
                f"Return a JSON array with the same structure (keep 'index' unchanged).\n"
                f"Do NOT add explanations. Return ONLY valid JSON.\n\n"
                + __import__('json').dumps(lines_payload, ensure_ascii=False)
            )
            import json as _json
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            raw = (response.text or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = _json.loads(raw)
            if not isinstance(result, list):
                raise ValueError("Response không phải list JSON")
            for item in result:
                ci = int(item.get("index", -1))
                new_text = (item.get("text") or "").strip()
                if 0 <= ci < len(subs) and new_text:
                    subs[ci].text = new_text
                    translated_count += 1
            append_log(job_id, f"[Hậu xử lý] Dịch lại dòng {[ci+1 for ci in chunk_idx]}: OK")
        except Exception as e:
            append_log(job_id, f"[Hậu xử lý] Lỗi dịch lại batch {chunk_idx}: {e}")
            key_pool.mark_error(key, str(e))

    if translated_count > 0:
        try:
            subs.save(out_path, encoding="utf-8")
            append_log(job_id, f"[Hậu xử lý] ✅ Đã dịch lại {translated_count} dòng sót, lưu file thành công.")
        except Exception as e:
            append_log(job_id, f"[Hậu xử lý] Lỗi lưu file sau khi dịch lại: {e}")
    else:
        append_log(job_id, "[Hậu xử lý] Không dịch lại được dòng nào (có thể lỗi API).")



def _run_translation(job_id, data):
    job = jobs[job_id]

    try:
        key_pool = data.get("key_pool")
        is_batch = bool(data.get("_batch"))
        if key_pool is None:
            keys_pool = collect_keys(data)
            valid_keys, _invalid_keys = validate_keys(keys_pool)
            if valid_keys:
                key_pool = KeyPool(valid_keys)
                key_pool.total_entered = len(keys_pool)
            else:
                key_pool = None
        else:
            keys_pool = list(key_pool.keys)
            key_pool.total_entered = getattr(key_pool, "total_entered", len(keys_pool))

        target_lang = (data.get("target_language") or "Vietnamese").strip()
        speed_mode  = (data.get("speed_mode") or DEFAULT_SPEED_MODE).strip().lower()
        preset      = get_speed_preset(speed_mode)

        model_name  = (data.get("model_name") or preset["model"]).strip()
        if not model_name or model_name == "default":
            model_name = preset["model"]

        description = (data.get("description") or "").strip()
        glossary_items = data.get("glossary") or []

        if glossary_items:
            glossary_lines = []
            if isinstance(glossary_items, list):
                for item in glossary_items:
                    if isinstance(item, dict) and item.get("src") and item.get("tgt"):
                        glossary_lines.append(f"- {item['src']} -> {item['tgt']}")
                    elif isinstance(item, str) and item.strip():
                        glossary_lines.append(f"- {item.strip()}")
            elif isinstance(glossary_items, str):
                glossary_lines = [f"- {l.strip()}" for l in glossary_items.splitlines() if l.strip()]

            if glossary_lines:
                glossary_text = "\n[BẢNG TỪ ĐIỂN THUẬT NGỮ CỐ ĐỊNH - BẮT BUỘC TUÂN THỦ]:\n" + "\n".join(glossary_lines)
                description = (description + "\n" + glossary_text).strip() if description else glossary_text.strip()

        batch_size  = str(data.get("batch_size") or "").strip()
        temperature = str(data.get("temperature") or "").strip()
        start_line  = str(data.get("start_line") or "").strip()
        if "no_context" in data:
            no_context = bool(data.get("no_context", False))
        else:
            no_context = preset["no_context"]
        input_file_key = (data.get("input_file") or "").strip()
        original_name  = (data.get("original_name") or "translated.srt").strip()

        if not key_pool or key_pool.alive_count() == 0:
            raise ValueError("Không có API Key hoạt động. Vui lòng kiểm tra lại key (đúng định dạng AIza... và chưa hết quota).")
        if not input_file_key:
            raise ValueError("Chưa chọn file đầu vào")
        if not GST_EXE:
            raise RuntimeError("Không tìm thấy gst CLI. Hãy đảm bảo gemini-srt-translator đã được cài đặt.")

        input_path = os.path.join(UPLOAD_FOLDER, input_file_key)
        if not os.path.exists(input_path):
            raise FileNotFoundError("Không tìm thấy file tải lên: " + input_path)

        base, ext = os.path.splitext(original_name)
        out_ext = ".ass" if ext.lower() == ".ass" else ".srt"
        out_filename = uuid.uuid4().hex + "_" + base + "_translated" + out_ext
        out_path = os.path.join(OUTPUT_FOLDER, out_filename)

        job["input_file_path"] = input_path
        job["out_file_path"] = out_path

        is_sub = ext.lower() in SUBTITLE_EXTENSIONS
        orig_subs = None
        if is_sub:
            orig_subs = load_subtitles_safe(input_path)
            job["total_lines"] = len(orig_subs)
            if job["total_lines"] > 0:
                append_log(job_id, f"Tổng số dòng phụ đề: {job['total_lines']} dòng")

        batch_arg = batch_size if batch_size.isdigit() and int(batch_size) > 0 else ""
        effective_batch_size = resolve_batch_size(batch_arg, job["total_lines"], preset["batch_size"])

        primary = None
        secondary = None
        if is_batch:
            primary = data.get("api_key") or key_pool.next_key()
            secondary = data.get("api_key2") or None
        else:
            primary = key_pool.next_key()
            secondary = key_pool.next_key() if key_pool.alive_count() > 1 else None

        append_log(job_id, f"Bắt đầu dịch: {original_name}")
        append_log(job_id, f"Ngôn ngữ đích: {target_lang} | Model: {model_name}")
        total_entered = getattr(key_pool, "total_entered", len(key_pool.keys))
        valid_count = key_pool.alive_count()
        append_log(job_id, f"Chế độ: {speed_mode} | Batch size: {effective_batch_size} | Số key hợp lệ: {valid_count}/{total_entered}")
        if valid_count < total_entered:
            append_log(job_id, f"Cảnh báo: {total_entered - valid_count} key không hoạt động/sai định dạng, đã bỏ qua.")
        if glossary_items:
            append_log(job_id, f"Từ điển thuật ngữ: {len(glossary_lines)} quy tắc cố định")
        append_log(job_id, "-" * 50)

        can_chunk = (
            is_sub
            and not is_batch
            and ext.lower() in {".srt", ".vtt"}
            and preset["parallel"] > 1
            and key_pool.alive_count() > 1
            and job["total_lines"] >= CHUNK_MIN_LINES
            and not (start_line and start_line.isdigit() and int(start_line) > 0)
        )

        if can_chunk:
            append_log(job_id, "Kích hoạt phân luồng song song (multi-key chunking)...")
            res = _translate_chunked(job_id, job, key_pool, orig_subs, out_path,
                                     target_lang, model_name, description, effective_batch_size,
                                     temperature, no_context, preset["parallel"])
            if res["stopped"]:
                job["status"] = "stopped"
                append_log(job_id, "Đã dừng theo yêu cầu người dùng.")
                return
            if not res["ok"]:
                raise RuntimeError(res["error"])
        else:
            if not primary:
                raise ValueError("Vui lòng nhập ít nhất 1 Gemini API Key")
            if not is_batch:
                append_log(job_id, f"Key: {KeyPool.mask(primary)}" + (f" + {KeyPool.mask(secondary)}" if secondary else ""))
            cmd = _build_gst_cmd(is_sub, input_path, out_path, target_lang, model_name,
                                 description, effective_batch_size, temperature, start_line, no_context)
            env = _build_env(primary, secondary)
            res = _run_gst_process(job_id, job, cmd, env, out_path)
            if res["stopped"]:
                job["status"] = "stopped"
                append_log(job_id, "Đã dừng theo yêu cầu người dùng.")
                return
            if not res["ok"]:
                key_pool.mark_error(primary, res["error"] or "")
                raise RuntimeError(f"Quá trình dịch dừng lại.\nChi tiết log:\n{res['error']}")

        if not os.path.exists(out_path):
            raise FileNotFoundError("Không tìm thấy file kết quả sau khi dịch xong. Vui lòng kiểm tra log.")

        # ── Post-processing: re-translate any lines still in source language ──
        _retranslate_untranslated(job_id, out_path, target_lang, model_name, key_pool)

        job["status"]        = "done"
        job["progress"]      = 100
        job["current_lines"] = job["total_lines"]
        job["output_file"]   = out_filename
        elapsed = max(0.1, time.time() - job["start_time"])
        job["speed_lps"] = round(job["total_lines"] / elapsed, 2)
        append_log(job_id, "-" * 50)
        append_log(job_id, f"Tốc độ: {job['speed_lps']} dòng/s | Thời gian: {round(elapsed, 1)}s")
        # Đồng bộ kết quả về dự án VoxDub nếu có work_dir
        work_dir = data.get("work_dir")
        if work_dir and os.path.isdir(work_dir):
            try:
                dub_srt_dst = os.path.join(work_dir, "transcript_dub_vi.srt")
                shutil.copy2(out_path, dub_srt_dst)
                parsed_subs = pysubs2.load(out_path, encoding="utf-8")
                segs = []
                for idx, ev in enumerate(parsed_subs):
                    txt_clean = ev.text.replace(r"\N", "\n").strip()
                    segs.append({
                        "id": idx + 1,
                        "start": ev.start / 1000.0,
                        "end": ev.end / 1000.0,
                        "text": txt_clean,
                        "text_vi": txt_clean,
                    })
                with open(os.path.join(work_dir, "transcript_dub_vi.json"), "w", encoding="utf-8") as jf:
                    import json
                    json.dump(segs, jf, ensure_ascii=False, indent=2)
                append_log(job_id, f"✅ Đã đồng bộ bản dịch vào thư mục dự án VoxDub: {work_dir}")
            except Exception as sync_err:
                append_log(job_id, f"⚠️ Không thể đồng bộ sang thư mục dự án: {sync_err}")

        append_log(job_id, f"Hoàn tất dịch file {original_name}!")

    except Exception as exc:
        job["status"] = "error"
        job["error"]  = str(exc)
        append_log(job_id, "LỖI: " + str(exc))




def get_static_folder() -> str:
    return STATIC_DIR


def create_app(env_path=None):
    return app


if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)
