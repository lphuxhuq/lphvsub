import json
import logging
import os
import sys
import tempfile
import threading
import time


def app_root() -> str:
    """Thư mục gốc chứa ``models/``, ``.env``, ``output/`` và các venv phụ.

    - Bản đóng gói: thư mục chứa tệp .exe — dữ liệu ngoài luôn nằm CẠNH ứng
      dụng, không bao giờ nằm trong gói.
    - Bản mã nguồn: thư mục gốc dự án (thư mục cha của gói ``autodub``).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


#: Venv được dò khi cần bản torch có CUDA (tách nhạc nền bằng card đồ họa,
#: và các thư viện cuBLAS/cuDNN cho Whisper).
GPU_VENVS = (".venv-gpu",)


def gpu_venv_dir() -> str:
    """Thư mục venv có torch bản CUDA, hoặc chuỗi rỗng nếu không có."""
    for venv in GPU_VENVS:
        path = os.path.join(app_root(), venv)
        if os.path.isdir(path):
            return path
    return ""


def bundled_file(*relative: str) -> str:
    """Path of a file shipped inside the app bundle (worker scripts, assets).

    Frozen: resolves under PyInstaller's ``_internal`` dir (``sys._MEIPASS``);
    source checkout: under the project root.
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.join(base, *relative)
    return os.path.join(app_root(), *relative)


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
    return logger


#: Số ngày giữ lại log cũ; quá hạn thì tệp tự bị xóa khi xoay vòng.
LOG_RETENTION_DAYS = 14

_FILE_HANDLER: logging.Handler | None = None


def logs_dir() -> str:
    """Thư mục log của ứng dụng: ``<app_root>/logs`` (cạnh exe khi đóng gói)."""
    return ensure_dir(os.path.join(app_root(), "logs"))


def init_file_logging() -> str:
    """Ghi mọi log ``autodub.*`` ra tệp, xoay vòng theo ngày.

    Gọi một lần lúc khởi động (GUI hoặc CLI); gọi lại là vô hại — chỉ có một
    trình ghi tệp duy nhất cho cả tiến trình. Trả về đường dẫn tệp log hiện
    tại để hiện cho người dùng khi cần.
    """
    global _FILE_HANDLER
    if _FILE_HANDLER is not None:
        return _FILE_HANDLER.baseFilename
    from logging.handlers import TimedRotatingFileHandler

    path = os.path.join(logs_dir(), "voxdub.log")
    # delay=True: chưa ghi dòng nào thì chưa tạo tệp (mở app rồi tắt ngay
    # không để lại tệp rỗng).
    handler = TimedRotatingFileHandler(
        path, when="midnight", backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s"))
    root = logging.getLogger("autodub")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _FILE_HANDLER = handler
    return path


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def save_json_atomic(data: object, path: str) -> None:
    """Crash-safe JSON save: write to a temp file then ``os.replace``.

    A crash/disk-full mid-write must never destroy files that are expensive
    to recreate (translated transcripts, batch state).
    """
    dir_name = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def fonts_dir() -> str:
    """Thư mục font kèm app: ``<app_root>/fonts`` (cạnh exe khi đóng gói).

    Nằm NGOÀI bundle PyInstaller có chủ đích: người dùng tự thả thêm file
    .ttf/.otf (ví dụ tải từ fonts.google.com) là app nhận ngay, không cần
    build lại. Cả GUI (QFontDatabase) lẫn ffmpeg/libass (fontsdir) cùng đọc
    thư mục này nên font chọn trong app luôn render đúng trên video.
    """
    return os.path.join(app_root(), "fonts")


def bundled_font_files() -> list[str]:
    """Mọi file font trong :func:`fonts_dir` (rỗng khi thư mục chưa có)."""
    d = fonts_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if f.lower().endswith((".ttf", ".otf", ".ttc"))
    )


def seg_wav_path(seg_dir: str, seg_id: int) -> str:
    """Canonical per-segment WAV path (5-digit zero-padded id).

    Older work dirs used 3-digit names (``seg_001.wav``); if such a file
    already exists it wins, so resuming a pre-migration dir keeps reusing
    (and overwriting) the legacy names instead of mixing both widths in one
    directory. 5 digits covers 1-2 h videos (the old 3-digit format broke
    ordering above 999 segments).
    """
    new = os.path.join(seg_dir, f"seg_{seg_id:05d}.wav")
    if os.path.exists(new):
        return new
    old = os.path.join(seg_dir, f"seg_{seg_id:03d}.wav")
    if os.path.exists(old):
        return old
    return new


def ffmpeg_timeout_s(duration_s: float | None, floor: int = 300) -> int:
    """Trần thời gian cho một lệnh ffmpeg xử lý ``duration_s`` giây media.

    ffmpeg treo (codec lỗi, file bị khóa trên Windows, driver NVENC kẹt) mà
    không có timeout thì pipeline đứng vĩnh viễn và không hủy được — mọi
    ``subprocess.run`` gọi ffmpeg phải đặt ``timeout=``. Quy tắc: gấp 4 lần
    thời lượng media (encode chậm nhất vẫn nhanh hơn nhiều), tối thiểu
    ``floor`` giây; không biết thời lượng thì dùng trần rộng 1 giờ.
    """
    if not duration_s or duration_s <= 0:
        return 3600
    return max(floor, int(duration_s * 4))


def format_timestamp(seconds: float) -> str:
    """SRT timestamp ``HH:MM:SS,mmm``.

    Derived from total milliseconds so fractions like 59.9996 carry into the
    seconds field instead of producing an invalid ``,1000`` millisecond part.
    """
    ms_total = max(0, int(round(seconds * 1000)))
    secs_total, millis = divmod(ms_total, 1000)
    hours, rem = divmod(secs_total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_eta(seconds: float | None) -> str:
    """Đổi số giây thành chuỗi thời gian ước tính thân thiện (vd: '45s', '1m 30s', '1h 15m')."""
    if seconds is None or seconds <= 0:
        return "0s"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s" if s > 0 else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def ffmpeg_escape_path(path: str) -> str:
    """Thoát đường dẫn an toàn để dùng làm giá trị trong bộ lọc (filtergraph) FFmpeg.

    Trên Windows và các hệ điều hành:
    1. Đổi dấu gạch chéo ngược ``\\`` thành ``/`` (FFmpeg chấp nhận và tránh bị hiểu là ký tự escape).
    2. Thoát dấu hai chấm ``:`` của ổ đĩa (vd: ``C\\:``) để FFmpeg không nhầm với dấu phân cách tham số bộ lọc.
    3. Thoát dấu nháy đơn ``'`` bằng ``'\\''`` (đóng nháy, chèn nháy thoát, mở lại nháy) để an toàn khi bọc trong ``'...'``.
    """
    if not path:
        return ""
    escaped = str(path).replace("\\", "/")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", r"'\''")
    return escaped


class ProgressTracker:
    """Theo dõi và định dạng tiến độ đồng nhất cho mọi khâu trong pipeline.

    Hỗ trợ đa luồng an toàn (thread-safe), tự động tính phần trăm (%),
    tốc độ (items/s hoặc x thời gian thực) và thời gian ước tính còn lại (ETA).
    """

    def __init__(
        self,
        total: int | float,
        step_name: str,
        unit: str = "câu",
        log_step: int | None = None,
        min_log_interval: float = 3.0,
    ):
        self.total = max(0.001, float(total))
        self.step_name = step_name
        self.unit = unit
        self.min_log_interval = min_log_interval
        self.start_time = time.time()
        self.last_log_time = self.start_time
        self.done = 0.0
        self._logged_first = False
        self._lock = threading.Lock()

        if log_step is not None:
            self.log_step = max(1, log_step)
        elif self.unit == "s":
            self.log_step = max(5, int(self.total // 20)) or 10
        elif self.total <= 20:
            self.log_step = 2
        elif self.total <= 100:
            self.log_step = 10
        elif self.total <= 300:
            self.log_step = 20
        else:
            self.log_step = 25

    def _check_log_locked(self, detail: str = "", forced: bool = False) -> tuple[bool, str]:
        n = self.done
        now = time.time()
        elapsed = now - self.start_time
        is_first = False
        if not self._logged_first and n > 0:
            is_first = True
            self._logged_first = True

        is_milestone = (
            forced
            or is_first
            or (int(n) % self.log_step == 0 and int(n) > 0)
            or n >= self.total
            or (now - self.last_log_time >= self.min_log_interval)
        )
        if is_milestone:
            self.last_log_time = now
            pct = min(100.0, (n / self.total) * 100.0)
            rate = n / elapsed if elapsed > 0 else 0.0
            rem_n = max(0.0, self.total - n)
            rem_s = rem_n / rate if rate > 0 else 0.0
            eta_str = f"còn ~{format_eta(rem_s)}" if rem_n > 0 else "hoàn tất"
            speed_str = f"{rate:.1f}x" if self.unit == "s" else f"{rate:.1f} {self.unit}/s"
            detail_str = f" | {detail}" if detail else ""
            n_str = f"{int(n)}" if self.unit == "câu" else f"{n:.1f}"
            total_str = f"{int(self.total)}" if self.unit == "câu" else f"{self.total:.1f}"
            msg = (
                f"{self.step_name}: {n_str}/{total_str} {self.unit} ({pct:.1f}%) | "
                f"Tốc độ: {speed_str} ({eta_str}){detail_str}"
            )
            return True, msg
        return False, ""

    def step(self, count: int | float = 1, detail: str = "") -> tuple[bool, str]:
        """Tăng tiến độ thêm count đơn vị.
        Trả về (should_log, message). should_log là True khi chạm mốc milestone
        hoặc khi đã trôi qua quá min_log_interval giây.
        """
        with self._lock:
            self.done += count
            return self._check_log_locked(detail=detail)

    def update_to(self, current: int | float, detail: str = "") -> tuple[bool, str]:
        """Cập nhật tiến độ tới mốc tuyệt đối current (thường dùng cho mốc giây audio/video)."""
        with self._lock:
            self.done = min(self.total, max(0.0, float(current)))
            return self._check_log_locked(detail=detail, forced=(self.done >= self.total))

    def summary(self) -> str:
        """Tạo chuỗi tổng kết khi hoàn tất công việc."""
        with self._lock:
            elapsed = time.time() - self.start_time
            rate = self.total / elapsed if elapsed > 0 else 0.0
            total_str = f"{int(self.total)}" if self.unit == "câu" else f"{self.total:.1f}"
            speed_str = f"{rate:.1f}x" if self.unit == "s" else f"{rate:.1f} {self.unit}/s"
            return (
                f"{self.step_name} hoàn tất: {total_str} {self.unit} "
                f"trong {format_eta(elapsed)} (trung bình {speed_str})"
            )


