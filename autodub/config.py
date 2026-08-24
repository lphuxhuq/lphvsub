"""Cấu hình ứng dụng — đọc từ biến môi trường / tệp ``.env``.

An toàn với giao diện: nạp module này (hay gọi ``Settings.load()``) không bao
giờ làm thoát tiến trình. API Key chỉ được kiểm tra vào lúc một bước thật
sự cần tới, qua :meth:`Settings.require`, và lỗi thiếu cấu hình là
:class:`ConfigError` để giao diện bắt và hiển thị tử tế.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from autodub.utils import app_root


class ConfigError(Exception):
    """Ném ra khi một mục cấu hình bắt buộc còn trống ngay lúc cần dùng."""


def _auto_vieneu_workers() -> int:
    """Số tiến trình giọng đọc mặc định — theo RAM trống và số nhân CPU.

    Mỗi tiến trình VieNeu chiếm ~1.5 GB RAM. Máy 8 GB mà chạy 3 tiến trình
    (4.5 GB) cộng Demucs + giao diện là tràn bộ nhớ, hệ điều hành swap và
    MỌI THỨ chậm đi — 3 luồng lúc đó còn chậm hơn 1 luồng. VIENEU_MAX_WORKERS
    trong .env khai báo tường minh luôn thắng giá trị tự tính này.
    """
    from autodub.sysinfo import available_ram_gb

    cores = os.cpu_count() or 4
    by_cpu = max(1, cores // 2)

    avail = available_ram_gb()
    # ~1.5 GB/tiến trình, chừa ~3 GB cho giao diện + Demucs + hệ điều hành.
    # Công thức này giữ nguyên số luồng của máy 6-10 GB như trước, nhưng máy
    # khỏe (24-32 GB, nhiều nhân) không còn bị kẹp ở 3 nữa — TTS là bước lâu
    # nhất nên trần thấp làm mất phần lớn hiệu năng sẵn có.
    if avail is None:          # không đọc được RAM — giữ mặc định an toàn
        by_ram = 3
    else:
        by_ram = max(1, int((avail - 3.0) // 1.5))

    workers = max(1, min(_VIENEU_WORKER_CEILING, by_ram, by_cpu))
    if workers < _VIENEU_WORKER_CEILING:
        _log_governor_once(workers, avail, cores)
    return workers


#: Trần cho số tiến trình giọng đọc tự tính. Trên mức này lợi ích giảm nhanh
#: (tranh nhân CPU giữa các tiến trình ONNX) mà RAM vẫn tăng tuyến tính.
_VIENEU_WORKER_CEILING = 6


_governor_logged = False


def _log_governor_once(workers: int, avail: float | None, cores: int) -> None:
    """Báo MỘT lần mỗi phiên khi tự hạ số luồng giọng đọc (tránh spam log
    vì Settings.load() được giao diện gọi lại mỗi lần lưu cài đặt)."""
    global _governor_logged
    if _governor_logged:
        return
    _governor_logged = True
    from autodub.utils import setup_logging

    ram_txt = f"{avail:.1f} GB RAM trống" if avail is not None else "RAM không rõ"
    setup_logging("autodub.config").info(
        f"Máy này ({ram_txt}, {cores} nhân) — chạy {workers} luồng giọng đọc "
        f"để không tràn bộ nhớ. Đặt VIENEU_MAX_WORKERS trong .env nếu muốn khác."
    )




def _one_of(value: str, allowed: tuple[str, ...], default: str) -> str:
    """Chuẩn hóa một mục kiểu danh sách, sai chính tả thì lấy giá trị mặc định.

    Gõ nhầm trong .env không được phép làm sập giao diện, nên hàm này dễ tính.
    """
    v = value.strip().lower()
    return v if v in allowed else default


# Mức chất lượng — MỘT nút vặn (QUALITY_PRESET) đặt sẵn giá trị mặc định cho
# các mục chi tiết bên dưới. Biến môi trường khai báo tường minh luôn thắng.
_PRESETS: dict[str, dict[str, str]] = {
    # Nhanh: ưu tiên tốc độ, chấp nhận chất lượng thấp hơn.
    "fast": {
        "whisper_model": "medium",
        "hq_background": "false",
        "translate_analysis": "false",
        "translate_review": "false",
        "karaoke_alignment": "false",
    },
    # Cân bằng (mặc định): mọi cải tiến chất lượng chính, chi phí vừa phải.
    "balanced": {
        "whisper_model": "auto",
        "hq_background": "true",
        "translate_analysis": "true",
        "translate_review": "true",
        "karaoke_alignment": "true",
    },
    # Chất lượng cao: chấp nhận chậm — ASR lớn, đủ mọi lượt kiểm tra.
    "quality": {
        "whisper_model": "auto",
        "hq_background": "true",
        "translate_analysis": "true",
        "translate_review": "true",
        "karaoke_alignment": "true",
    },
}

@dataclass
class Settings:
    # Mức chất lượng: một nút vặn đặt mặc định hợp lý cho các mục chi tiết
    # ("fast" | "balanced" | "quality"). Biến môi trường riêng vẫn ghi đè.
    quality_preset: str = "balanced"

    # --- Nghe và chép lời (ASR) -------------------------------------------
    # Whisper chạy trên máy, miễn phí. Model lớn hơn = đúng hơn nhưng chậm hơn.
    # "auto" = large-v3 khi có CUDA, medium khi chỉ có CPU.
    whisper_model: str = "auto"
    # Bộ nhận dạng: "whisper" (mặc định, mọi ngôn ngữ) | "paraformer" (chuyên
    # tiếng Trung, chạy CPU/ONNX trong .venv-asr — cài bằng
    # scripts/setup_paraformer.py; tự quay về Whisper khi chưa cài).
    asr_engine: str = "whisper"
    asr_venv_python: str = ""       # mặc định: <app>/.venv-asr/Scripts/python.exe
    paraformer_model_dir: str = ""  # mặc định: <app>/models/paraformer-zh
    asr_num_threads: int = 4
    # Đệm (giây) hai bên mỗi VAD chunk trước khi decode — silero hay cắt mất
    # vài trăm ms đầu/cuối câu. Timestamp vẫn lấy biên VAD gốc nên timeline
    # không trượt. 0 = tắt.
    asr_vad_pad_s: float = 0.3
    # Beam size của Whisper (1–10). 5 là mặc định của thư viện — giữ nguyên
    # chất lượng. Máy CPU yếu có thể hạ (vd 1) để nhanh gấp 2–3 lần, đổi lại
    # kém chính xác hơn một chút — đây là lựa chọn CHỦ ĐỘNG, không tự hạ.
    whisper_beam_size: int = 5
    # Whisper chạy trong venv riêng (.venv-whisper) khi đã cài
    # scripts/setup_whisper.py — faster-whisper + ctranslate2 không cần bundle
    # trong exe, giảm ~112 MB. Khi venv chưa có, app tự dùng faster-whisper
    # đã cài trong môi trường hiện tại (dev) hoặc báo lỗi nếu thiếu (exe).
    whisper_venv_python: str = ""   # mặc định: <app>/.venv-whisper/Scripts/python.exe
    whisper_model_dir: str = ""     # mặc định: <app>/models/whisper (cache HuggingFace)

    # --- OCR hard-sub (selective fallback cho ASR) --------------------------
    # Tắt mặc định — bật khi video Douyin có hard-sub Trung và Paraformer bỏ
    # sót chữ. RapidOCR chạy CPU/ONNX trong .venv-ocr (scripts/setup_ocr.py),
    # chỉ OCR các suspect window chứ không quét cả video.
    ocr_enabled: bool = False
    ocr_venv_python: str = ""       # mặc định: <app>/.venv-ocr/Scripts/python.exe
    ocr_fps: int = 3                # frame/giây khi OCR suspect window
    ocr_region_height: float = 0.18  # vùng phụ đề: 18% chiều cao dưới cùng

    # --- Giọng đọc tiếng Việt (VieNeu — bộ giọng DUY NHẤT) -----------------
    # Chạy trong venv riêng (.venv-vieneu) qua tiến trình con — cài một lần
    # bằng scripts/setup_vieneu.py. Chạy CPU/ONNX nên không tốn VRAM và không
    # tranh card đồ họa với Whisper/Demucs.
    vieneu_venv_python: str = ""   # mặc định: <app>/.venv-vieneu/Scripts/python.exe
    vieneu_model_dir: str = ""     # mặc định: <app>/models/vieneu
    #: Tên giọng mặc định cho dự án mới (xem autodub.speech.tts.voices).
    vieneu_voice: str = ""
    vieneu_style: str = "tu_nhien"   # "tu_nhien" | "tin_tuc" | "doc_truyen"
    # Số tiến trình con chạy song song (~1.5 GB RAM mỗi cái). Chạy trên CPU
    # nên tăng số luồng là nhanh lên gần như tuyến tính, tới khi hết nhân.
    vieneu_max_workers: int = 3

    # Hiệu năng: số luồng cho các bước nặng (gửi việc cho bộ giọng, nhóm
    # ffmpeg atempo, dịch qua mạng). Tự tính theo CPU lúc nạp cấu hình;
    # PARALLEL_WORKERS trong .env là lối thoát hiểm cho người biết việc.
    parallel_workers: int = 4
    # Số câu tạo giọng CapCut song song qua Device Pool (1–16, mặc định 8 luồng)
    capcut_threads: int = 8

    # --- Tải video ---------------------------------------------------------
    # Batch: số video tải trước bằng cửa sổ trượt (1 = hành vi cũ, chỉ video
    # kế tiếp). 2 giấu hoàn toàn thời gian tải sau thời gian xử lý pipeline;
    # tốn đĩa tối đa ~2 video (1-2GB với video dài).
    batch_prefetch_depth: int = 2
    # Trang Tải video: số URL tải song song (1 = tuần tự như cũ). Trần 4 —
    # nhiều hơn dễ bị CDN bóp băng thông từng kết nối.
    download_page_workers: int = 2

    # Nút vặn thời lượng LEGACY — mặc định tắt ảnh hưởng (voice-sync):
    # scheduler timing.py fit tempo TỪNG câu theo slot speech thật, video
    # giữ tốc độ gốc. VIDEO_SPEED ≠ 1 làm chậm cả hình (môi không khớp);
    # VOICE_SPEED áp một hệ số chung cho mọi câu (bật qua voice_speed_legacy).
    video_speed: float = 1.0    # 1.0 = giữ nguyên (mặc định, khuyến nghị)
    voice_speed: float = 1.0    # chỉ dùng khi voice_speed_legacy=true
    # Bật lại hành vi cũ: VOICE_SPEED áp atempo toàn cục cho mọi clip.
    voice_speed_legacy: bool = False

    # Ngân sách dịch (số ký tự trên mỗi giây khung thời gian). Số nhỏ hơn ép
    # bản dịch ngắn lại nên ít tràn hơn.
    translate_cps_budget: float = 12.5

    # --- Chất lượng âm thanh ----------------------------------------------
    # Nhạc nền chất lượng cao: rút thêm original_audio_hq.wav 44.1 kHz stereo
    # riêng cho Demucs + bản trộn cuối (bản 16 kHz mono chỉ dành cho ASR).
    hq_background: bool = True
    # Chuẩn hóa âm lượng + fade từng câu (EBU R128 loudnorm, highpass 80 Hz,
    # fade 15 ms). Tắt = giữ nguyên bản thô từ bộ giọng.
    voice_postprocess: bool = True
    voice_target_lufs: float = -16.0
    # Nhạc nền tự nhỏ đi khi có giọng và hồi lại ở khoảng lặng. 0 = tắt.
    bg_duck_voice_db: float = -7.0
    # --- Dubbing thực tế (bg_mode="duck") -----------------------------------
    # Mức TỔNG của tiếng gốc khi nhân vật ĐANG NÓI (duck theo speech segment
    # tiếng gốc). Ngoài speech nền giữ mức bg_duck_db của dự án.
    # Preset: NATURAL −16 · CLEAR VIETNAMESE −20 · BALANCED −12.
    original_voice_duck_db: float = -16.0
    duck_attack_ms: int = 80      # thời gian trượt xuống khi bắt đầu nói
    duck_release_ms: int = 140    # thời gian trượt lên khi hết nói
    # Đẩy sớm onset giọng Việt so với speech_start (ms). 0 = đúng onset.
    dub_pre_roll_ms: int = 0
    # Chống chồng tiếng "mềm": câu dài hơn khung thì DỒN TRỄ các câu sau vào
    # khoảng lặng kế tiếp (có trần tổng), tuyệt đối không đổi tốc độ đọc từng
    # câu. Chỉ khi kịch trần mới nén nhẹ và đều, với trần thấp.
    soft_timing_fit: bool = True
    # Thu hẹp biên VAD thô về biên speech thật bằng RMS energy trước khi
    # tính slot dịch/TTS (speech/boundaries.py). 0 cost khi transcript đã tốt.
    speech_boundary_refine: bool = True
    # Quét lại khoảng trống giữa các chunk VAD (decode thẳng, không qua VAD)
    # — bắt lời nói mờ/ngắn bị silero bỏ sót (thoại chìm dưới nhạc nền).
    asr_gap_rescan: bool = True
    # Cho phép kéo dài giọng đọc (atempo < 1.0, chặn tại voice_fit_min_speed)
    # để lấp bớt khoảng lặng cuối câu khi clip TTS ngắn hơn khung thoại gốc.
    voice_fit_stretch: bool = False
    # Trần drift start của MỖI câu khi đặt dub (voice-sync scheduler mới).
    # 0.15s ≈ ngưỡng lip-sync cảm nhận; scheduler cũ dùng 1.5s (quá rộng).
    timing_max_start_drift_s: float = 0.15
    # Khoảng [min, max] tempo per-segment khi fit TTS vào slot. KHÔNG kéo
    # dài (min chỉ là chặn dưới hợp đồng — stretch bị vô hiệu).
    voice_fit_min_speed: float = 0.90
    voice_fit_max_speed: float = 1.15
    timing_max_drift_s: float = 1.5     # trần dồn trễ tích lũy
    timing_min_gap_s: float = 0.12      # khoảng thở tối thiểu giữa hai câu
    timing_max_atempo: float = 1.1      # trần nén bất khả kháng (mỗi câu)

    # --- Ngữ cảnh dịch do người dùng cung cấp (đều không bắt buộc) ---------
    translate_domain: str = ""       # chủ đề, vd "review công nghệ"
    translate_context: str = ""      # mô tả tự do (nhiều dòng)
    translate_pronouns: str = ""     # quy ước xưng hô, vd "mình – các bạn"
    translate_glossary: str = ""     # thuật ngữ cố định, mỗi dòng "gốc = dịch"
    translate_style_notes: str = ""  # yêu cầu thêm về giọng văn
    # Tiêu đề video gốc — KHÔNG nạp từ .env: pipeline tự bơm mỗi lượt chạy
    # (đọc data/video_meta.json do downloader ghi) vào bản sao Settings để
    # prompt dịch/phân tích biết video nói về gì ngay từ tiêu đề.
    translate_video_title: str = ""

    # --- Dịch hai lượt ----------------------------------------------------
    # Lượt 0 "hiểu video": trước khi dịch, gửi toàn bộ lời thoại gốc để rút ra
    # tóm tắt + nhân vật/xưng hô + thuật ngữ, rồi tự bơm vào ngữ cảnh dịch
    # (mục người dùng điền tay luôn được ưu tiên hơn).
    translate_analysis: bool = True
    # Lượt rà soát: sau khi dịch, soát các câu nghi vấn (vượt ngân sách nhiều,
    # còn ký tự CJK, quá ngắn so với câu gốc) rồi dịch lại đúng các câu đó.
    translate_review: bool = True

    # --- Chung ------------------------------------------------------------
    default_source_lang: str = "zh-CN"
    audio_sample_rate: int = 16000
    output_dir: str = "./output"
    vietnamese_output_dir: str = ""
    # Tự dọn tệp trung gian ngay khi xuất video xong. Tắt mặc định vì dọn
    # rồi thì không sửa từng câu hay xuất lại dự án đó được nữa.
    auto_clean_intermediates: bool = False

    # --- Cập nhật và hỗ trợ -----------------------------------------------
    # Kho GitHub chứa bản phát hành (dạng "chủ/kho") — dùng để báo bản mới.
    update_repo: str = "ttthanh2044/voxdub"
    # Đường dẫn biểu mẫu nhận báo lỗi và góp ý từ người dùng.
    support_url: str = "https://github.com/ttthanh2044/voxdub/issues"

    # Liên kết video mặc định (dùng khi giao diện/chạy hàng loạt không đưa nguồn)
    video_url: str = ""

    # --- Nội dung đăng bài ------------------------------------------------
    # Tạo tiêu đề/mô tả/hashtag sau mỗi lần lồng tiếng (máy chủ viết).
    # Tắt = bỏ hẳn bước này (và không tốn Vox).
    generate_metadata: bool = True

    # --- Dịch tự động -----------------------------------------------------
    translate_enabled: bool = True
    # Số câu mỗi lượt gửi lên máy chủ (trần cứng phía máy chủ là 120).
    translate_batch_size: int = 40
    # Số luồng dịch song song qua API trực tiếp (0 = tự động theo số key).
    translate_direct_workers: int = 0
    # Để model Gemini 2.5 "suy nghĩ" trước khi dịch — chậm hơn nhiều lần,
    # mặc định tắt (dịch theo schema JSON không cần thinking).
    translate_thinking: bool = False
    # Khóa API của các dịch vụ dịch AI (tự động đồng bộ sang máy chủ khi chạy)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    custom_ai_base_url: str = "https://hhtechapi.net/v1"
    custom_ai_api_key: str = ""
    custom_ai_model: str = "deepseek-v4-flash"

    # --- Dịch qua Google AI Studio (trình duyệt, miễn phí) ---------------
    ai_studio_enabled: bool = False
    ai_studio_headless: bool = False
    ai_studio_single_chat: bool = True
    ai_studio_chrome_profile: str = ""

    # --- Phụ đề -----------------------------------------------------------
    # Kiểu mặc định: "none" | "soft" (tệp rời) | "burn" (ghi thẳng vào hình)
    subtitle_mode: str = "none"
    #: Bộ kiểu chữ dựng sẵn (xem autodub.media.subtitle.PRESETS).
    subtitle_preset: str = "clean"
    subtitle_position: str = "bottom"   # "bottom" | "middle" | "top"
    subtitle_font: str = "Arial"
    subtitle_font_size: int = 22
    subtitle_margin_v: int = 40         # khoảng cách tới mép (điểm ảnh ASS)
    subtitle_outline: int = 2           # độ dày viền chữ
    subtitle_shadow: int = 0            # độ đổ bóng
    subtitle_bold: bool = True
    subtitle_color: str = "#FFFFFF"
    subtitle_outline_color: str = "#000000"
    # Nền sau chữ: "none" (chỉ viền) | "box" (khối nền đặc kiểu CapCut)
    subtitle_box: str = "none"
    subtitle_box_color: str = "#000000"
    subtitle_box_opacity: int = 60      # 0–100, chỉ có nghĩa khi box = "box"
    # Số CHỮ mỗi hàng do người dùng chốt. 0 = tự xuống dòng theo bề rộng chuẩn.
    subtitle_line_words: int = 0
    subtitle_max_lines: int = 2
    subtitle_all_caps: bool = False

    # --- Phụ đề theo cụm chữ (nhảy theo giọng đọc, chỉ chế độ ghi vào hình) -
    # "sentence" (cả câu) | "karaoke" (cụm chữ .ass)
    subtitle_display: str = "sentence"
    karaoke_words_per_cue: int = 3      # 1-5 chữ mỗi cụm
    karaoke_effect: str = "pop"         # "pop" | "fade" | "karaoke" | "none"
    karaoke_highlight_color: str = "#FFD54A"
    # Khớp mốc chữ THẬT bằng Whisper nghe lại giọng đọc (~30-60s/video).
    # Tắt = ước lượng theo âm tiết (nhanh, kém chính xác hơn một chút).
    karaoke_alignment: bool = True

    # Danh sách vùng làm mờ/che phụ đề mặc định (dạng chuỗi JSON)
    blur_regions: str = ""

    # Bố cục tỷ lệ khung hình xuất video: "original" | "tiktok_9_16" | "youtube_16_9" | "square_1_1"
    video_aspect_preset: str = "original"


    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, env_file: str | None = None, override: bool = False) -> "Settings":
        """Dựng Settings từ môi trường (sau khi nạp ``.env``).

        ``override=True`` đọc lại .env đè lên biến môi trường đã đặt — giao
        diện dùng để nạp nóng cài đặt ngay sau khi lưu tệp.
        """
        if env_file:
            load_dotenv(env_file, override=override)
        else:
            # Luôn là tệp .env nằm cạnh ứng dụng (thư mục chứa exe khi đã
            # đóng gói) — không phụ thuộc thư mục người dùng đang đứng.
            load_dotenv(os.path.join(app_root(), ".env"), override=override)

        def env(key: str, default: str = "", *aliases: str) -> str:
            for k in (key, *aliases):
                value = os.environ.get(k)
                if value is not None:
                    return value
            return default

        def env_int(key: str, default: str) -> int:
            try:
                return int(float(env(key, default)))
            except ValueError:
                return int(float(default))

        def env_float(key: str, default: str) -> float:
            try:
                return float(env(key, default))
            except ValueError:
                return float(default)

        def env_dir(key: str, default: str) -> str:
            """Mục thư mục; đường dẫn tương đối neo vào thư mục ứng dụng."""
            value = env(key, default).strip()
            if value and not os.path.isabs(value):
                value = os.path.normpath(os.path.join(app_root(), value))
            return value

        def env_multiline(key: str) -> str:
            """Mục nhiều dòng, lưu trên một dòng .env với ký tự \\n."""
            return env(key).replace("\\n", "\n").strip()

        def env_bool(key: str, default: str) -> bool:
            return env(key, default).strip().lower() in ("1", "true", "yes")

        # Mức chất lượng: nền mặc định cho các mục chi tiết. Biến môi trường
        # tường minh vẫn thắng (env() đọc chúng trước khi dùng tới preset).
        preset = _one_of(env("QUALITY_PRESET", "balanced"),
                         ("fast", "balanced", "quality"), "balanced")
        _p = _PRESETS[preset]

        # Tự tính số luồng theo CPU: một nửa số nhân logic, kẹp trong 2–8.
        auto_workers = str(min(8, max(2, (os.cpu_count() or 4) // 2)))

        return cls(
            quality_preset=preset,
            whisper_model=env("WHISPER_MODEL", _p["whisper_model"]),
            asr_engine=_one_of(env("ASR_ENGINE", "whisper"),
                               ("whisper", "paraformer"), "whisper"),
            asr_venv_python=env("ASR_VENV_PYTHON"),
            paraformer_model_dir=env("PARAFORMER_MODEL_DIR"),
            asr_num_threads=max(1, min(16, env_int("ASR_NUM_THREADS", "4"))),
            asr_vad_pad_s=min(1.0, max(0.0,
                env_float("ASR_VAD_PAD_S", "0.3"))),
            whisper_beam_size=max(1, min(10, env_int("WHISPER_BEAM_SIZE", "5"))),
            ocr_enabled=env_bool("OCR_ENABLED", "false"),
            ocr_venv_python=env("OCR_VENV_PYTHON"),
            ocr_fps=max(1, min(10, env_int("OCR_FPS", "3"))),
            ocr_region_height=min(0.5, max(0.05,
                env_float("OCR_REGION_HEIGHT", "0.18"))),
            vieneu_venv_python=env("VIENEU_VENV_PYTHON"),
            vieneu_model_dir=env("VIENEU_MODEL_DIR"),
            vieneu_voice=env("VIENEU_VOICE", "").strip(),
            vieneu_style=_one_of(env("VIENEU_STYLE", "tu_nhien"),
                                 ("tu_nhien", "tin_tuc", "doc_truyen"),
                                 "tu_nhien"),
            # Người dùng đặt tay thì tôn trọng; chưa đặt thì tự tính theo
            # RAM trống + số nhân (xem _auto_vieneu_workers).
            vieneu_max_workers=max(1, min(8, env_int(
                "VIENEU_MAX_WORKERS",
                "3" if env("VIENEU_MAX_WORKERS")
                else str(_auto_vieneu_workers())))),
            parallel_workers=max(1, min(16, env_int("PARALLEL_WORKERS",
                                                    auto_workers))),
            capcut_threads=max(1, min(16, env_int("CAPCUT_THREADS", "8"))),
            batch_prefetch_depth=max(1, min(5,
                env_int("BATCH_PREFETCH_DEPTH", "2"))),
            download_page_workers=max(1, min(4,
                env_int("DOWNLOAD_PAGE_WORKERS", "2"))),
            video_speed=min(1.0, max(0.5, env_float("VIDEO_SPEED", "1.0"))),
            voice_speed=min(2.0, max(0.5, env_float("VOICE_SPEED", "1.0"))),
            voice_speed_legacy=env_bool("VOICE_SPEED_LEGACY", "false"),
            translate_cps_budget=env_float("TRANSLATE_CPS_BUDGET", "12.5"),
            hq_background=env_bool("HQ_BACKGROUND", _p["hq_background"]),
            voice_postprocess=env_bool("VOICE_POSTPROCESS", "true"),
            voice_target_lufs=env_float("VOICE_TARGET_LUFS", "-16.0"),
            bg_duck_voice_db=min(0.0, max(-24.0,
                env_float("BG_DUCK_VOICE_DB", "-7.0"))),
            original_voice_duck_db=min(0.0, max(-30.0,
                env_float("ORIGINAL_VOICE_DUCK_DB", "-16.0"))),
            duck_attack_ms=max(10, min(500,
                env_int("DUCK_ATTACK_MS", "80"))),
            duck_release_ms=max(10, min(1000,
                env_int("DUCK_RELEASE_MS", "140"))),
            dub_pre_roll_ms=max(0, min(80,
                env_int("DUB_PRE_ROLL_MS", "0"))),
            soft_timing_fit=env_bool("SOFT_TIMING_FIT", "true"),
            speech_boundary_refine=env_bool("SPEECH_BOUNDARY_REFINE", "true"),
            asr_gap_rescan=env_bool("ASR_GAP_RESCAN", "true"),
            voice_fit_stretch=env_bool("VOICE_FIT_STRETCH", "false"),
            timing_max_start_drift_s=min(1.5, max(0.0,
                env_float("TIMING_MAX_START_DRIFT_S", "0.15"))),
            voice_fit_min_speed=min(1.0, max(0.5,
                env_float("VOICE_FIT_MIN_SPEED", "0.90"))),
            voice_fit_max_speed=min(1.3, max(1.0,
                env_float("VOICE_FIT_MAX_SPEED", "1.15"))),
            timing_max_drift_s=min(5.0, max(0.0,
                env_float("TIMING_MAX_DRIFT_S", "1.5"))),
            timing_min_gap_s=min(1.0, max(0.0,
                env_float("TIMING_MIN_GAP_S", "0.12"))),
            timing_max_atempo=min(1.3, max(1.0,
                env_float("TIMING_MAX_ATEMPO", "1.1"))),
            translate_analysis=env_bool("TRANSLATE_ANALYSIS",
                                        _p["translate_analysis"]),
            translate_review=env_bool("TRANSLATE_REVIEW",
                                      _p["translate_review"]),
            translate_domain=env("TRANSLATE_DOMAIN").strip(),
            translate_context=env_multiline("TRANSLATE_CONTEXT"),
            translate_pronouns=env("TRANSLATE_PRONOUNS").strip(),
            translate_glossary=env_multiline("TRANSLATE_GLOSSARY"),
            translate_style_notes=env_multiline("TRANSLATE_STYLE_NOTES"),
            default_source_lang=env("DEFAULT_SOURCE_LANG", "zh-CN"),
            audio_sample_rate=env_int("AUDIO_SAMPLE_RATE", "16000"),
            output_dir=env_dir("OUTPUT_DIR", "./output"),
            vietnamese_output_dir=env_dir("VIETNAMESE_OUTPUT_DIR", ""),
            auto_clean_intermediates=env_bool("AUTO_CLEAN_INTERMEDIATES",
                                              "false"),
            update_repo=env("UPDATE_REPO",
                            "ttthanh2044/voxdub").strip(),
            support_url=env("SUPPORT_URL",
                            "https://github.com/ttthanh2044/voxdub/issues").strip(),
            video_url=env("VIDEO_URL"),
            generate_metadata=env("GENERATE_METADATA", "true").strip().lower()
                              not in ("0", "false", "no"),
            translate_enabled=env("TRANSLATE_ENABLED", "true").strip().lower()
                              not in ("0", "false", "no"),
            translate_batch_size=max(1, min(100,
                env_int("TRANSLATE_BATCH_SIZE", "40"))),
            translate_direct_workers=max(0, min(8,
                env_int("TRANSLATE_DIRECT_WORKERS", "0"))),
            translate_thinking=env_bool("TRANSLATE_THINKING", "false"),
            gemini_api_key=env("GEMINI_API_KEY", "", "GOOGLE_API_KEY", "SEED_GEMINI_API_KEY").strip(),
            gemini_model=env("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            openrouter_api_key=env("OPENROUTER_API_KEY", "", "SEED_OPENROUTER_API_KEY").strip(),
            openai_api_key=env("OPENAI_API_KEY", "", "SEED_OPENAI_API_KEY").strip(),
            deepseek_api_key=env("DEEPSEEK_API_KEY", "", "SEED_DEEPSEEK_API_KEY").strip(),
            custom_ai_base_url=env("CUSTOM_AI_BASE_URL", "https://hhtechapi.net/v1", "HHTECH_BASE_URL", "OPENAI_COMPAT_BASE_URL").strip() or "https://hhtechapi.net/v1",
            custom_ai_api_key=env("CUSTOM_AI_API_KEY", "", "HHTECH_API_KEY", "OPENAI_COMPAT_API_KEY").strip(),
            custom_ai_model=env("CUSTOM_AI_MODEL", "deepseek-v4-flash", "HHTECH_MODEL", "OPENAI_COMPAT_MODEL").strip() or "deepseek-v4-flash",
            ai_studio_enabled=env_bool("AI_STUDIO_ENABLED", "false"),
            ai_studio_headless=env_bool("AI_STUDIO_HEADLESS", "false"),
            ai_studio_single_chat=env_bool("AI_STUDIO_SINGLE_CHAT", "true"),
            ai_studio_chrome_profile=env("AI_STUDIO_CHROME_PROFILE").strip(),
            subtitle_mode=_one_of(env("SUBTITLE_MODE", "none"),
                                  ("none", "soft", "burn"), "none"),
            subtitle_preset=env("SUBTITLE_PRESET", "clean").strip() or "clean",
            subtitle_position=_one_of(env("SUBTITLE_POSITION", "bottom"),
                                      ("bottom", "middle", "top"), "bottom"),
            subtitle_font=env("SUBTITLE_FONT", "Arial"),
            subtitle_font_size=env_int("SUBTITLE_FONT_SIZE", "22"),
            subtitle_margin_v=env_int("SUBTITLE_MARGIN_V", "40"),
            subtitle_outline=env_int("SUBTITLE_OUTLINE", "2"),
            subtitle_shadow=max(0, min(8, env_int("SUBTITLE_SHADOW", "0"))),
            subtitle_bold=env_bool("SUBTITLE_BOLD", "true"),
            subtitle_color=env("SUBTITLE_COLOR", "#FFFFFF"),
            subtitle_outline_color=env("SUBTITLE_OUTLINE_COLOR", "#000000"),
            subtitle_box=_one_of(env("SUBTITLE_BOX", "none"),
                                 ("none", "box"), "none"),
            subtitle_box_color=env("SUBTITLE_BOX_COLOR", "#000000"),
            subtitle_box_opacity=max(0, min(100,
                env_int("SUBTITLE_BOX_OPACITY", "60"))),
            subtitle_line_words=max(0, min(12,
                env_int("SUBTITLE_LINE_WORDS", "0"))),
            subtitle_max_lines=max(1, min(4,
                env_int("SUBTITLE_MAX_LINES", "2"))),
            subtitle_all_caps=env_bool("SUBTITLE_ALL_CAPS", "false"),
            subtitle_display=_one_of(env("SUBTITLE_DISPLAY", "sentence"),
                                     ("sentence", "karaoke"), "sentence"),
            karaoke_words_per_cue=max(1, min(5,
                env_int("KARAOKE_WORDS_PER_CUE", "3"))),
            karaoke_effect=_one_of(env("KARAOKE_EFFECT", "pop"),
                                   ("pop", "fade", "karaoke", "none"), "pop"),
            karaoke_highlight_color=env("KARAOKE_HIGHLIGHT_COLOR",
                                        "#FFD54A").strip() or "#FFD54A",
            karaoke_alignment=env_bool("KARAOKE_ALIGNMENT",
                                       _p["karaoke_alignment"]),
            blur_regions=env("BLUR_REGIONS", "").strip(),
        )

    def blur_regions_list(self) -> list[dict]:
        """Danh sách vùng làm mờ phụ đề mặc định."""
        if not self.blur_regions:
            return []
        try:
            val = json.loads(self.blur_regions)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    # --- Kiểm tra cấu hình -------------------------------------------------

    def require(self, *fields: str) -> None:
        """Ném ConfigError nếu một trong các mục được nêu còn trống."""
        missing = [f for f in fields if not getattr(self, f)]
        if missing:
            env_names = ", ".join(f.upper() for f in missing)
            raise ConfigError(
                f"Thiếu cấu hình bắt buộc: {env_names}. "
                f"Điền vào trang Cài đặt (hoặc tệp .env) rồi chạy lại."
            )

    # --- Phụ đề ------------------------------------------------------------

    def subtitle_style(self) -> dict:
        """Kiểu phụ đề truyền cho ffmpeg/libass.

        Đây là "đường ống" DUY NHẤT đưa lựa chọn phụ đề từ Cài đặt qua
        pipeline tới trình chỉnh sửa (render_opts.json).
        """
        return {
            "preset": self.subtitle_preset,
            "position": self.subtitle_position,
            "font": self.subtitle_font,
            "font_size": self.subtitle_font_size,
            "margin_v": self.subtitle_margin_v,
            "outline": self.subtitle_outline,
            "shadow": self.subtitle_shadow,
            "bold": self.subtitle_bold,
            "color": self.subtitle_color,
            "outline_color": self.subtitle_outline_color,
            "box": self.subtitle_box,
            "box_color": self.subtitle_box_color,
            "box_opacity": self.subtitle_box_opacity,
            "line_words": self.subtitle_line_words,
            "max_lines": self.subtitle_max_lines,
            "all_caps": self.subtitle_all_caps,
            "display": self.subtitle_display,
            "words_per_cue": self.karaoke_words_per_cue,
            "effect": self.karaoke_effect,
            "highlight_color": self.karaoke_highlight_color,
        }

    # --- Đường dẫn của các bộ chạy riêng ------------------------------------

    def asr_venv_python_path(self) -> str:
        """Trình thông dịch Python của venv dành riêng cho Paraformer."""
        if self.asr_venv_python:
            return self.asr_venv_python
        exe = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return os.path.join(app_root(), ".venv-asr", *exe.split("/"))

    def paraformer_model_dir_path(self) -> str:
        """Thư mục chứa model Paraformer + silero-VAD (+ chấm câu)."""
        if self.paraformer_model_dir:
            return self.paraformer_model_dir
        return os.path.join(app_root(), "models", "paraformer-zh")

    def paraformer_configured(self) -> bool:
        """venv ASR và dấu hiệu cài đặt xong đều có mặt hay chưa."""
        return (os.path.isfile(self.asr_venv_python_path())
                and os.path.isfile(os.path.join(self.paraformer_model_dir_path(),
                                                "installed_ok.json")))

    def ocr_venv_python_path(self) -> str:
        """Trình thông dịch Python của venv dành riêng cho RapidOCR."""
        if self.ocr_venv_python:
            return self.ocr_venv_python
        exe = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return os.path.join(app_root(), ".venv-ocr", *exe.split("/"))

    def whisper_venv_python_path(self) -> str:
        """Trình thông dịch Python của venv dành riêng cho Whisper."""
        if self.whisper_venv_python:
            return self.whisper_venv_python
        exe = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return os.path.join(app_root(), ".venv-whisper", *exe.split("/"))

    def whisper_model_dir_path(self) -> str:
        """Thư mục cache model Whisper (HuggingFace)."""
        if self.whisper_model_dir:
            return self.whisper_model_dir
        return os.path.join(app_root(), "models", "whisper")

    def whisper_venv_configured(self) -> bool:
        """venv Whisper đã cài và có marker hay chưa."""
        return (os.path.isfile(self.whisper_venv_python_path())
                and os.path.isfile(os.path.join(self.whisper_model_dir_path(),
                                                "installed_ok.json")))

    def vieneu_venv_python_path(self) -> str:
        """Trình thông dịch Python của venv dành riêng cho VieNeu."""
        if self.vieneu_venv_python:
            return self.vieneu_venv_python
        exe = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return os.path.join(app_root(), ".venv-vieneu", *exe.split("/"))

    def vieneu_model_dir_path(self) -> str:
        """Thư mục chứa các tệp model VieNeu đã tải về."""
        if self.vieneu_model_dir:
            return self.vieneu_model_dir
        return os.path.join(app_root(), "models", "vieneu")

    def vieneu_custom_voices_path(self) -> str:
        """Tệp JSON chứa giọng người dùng tự thêm.

        Nằm trong models/vieneu cạnh ứng dụng (không nằm trong gói mã) nên
        cập nhật ứng dụng không làm mất giọng đã học.
        """
        return os.path.join(self.vieneu_model_dir_path(), "custom_voices.json")

    def vieneu_configured(self) -> bool:
        """venv VieNeu và dấu hiệu cài đặt xong đều có mặt hay chưa."""
        return (os.path.isfile(self.vieneu_venv_python_path())
                and os.path.isfile(os.path.join(self.vieneu_model_dir_path(),
                                                "installed_ok.json")))

    def vi_output_dir(self) -> str:
        """Thư mục kết quả: VIETNAMESE_OUTPUT_DIR hoặc OUTPUT_DIR/VN."""
        if self.vietnamese_output_dir:
            return self.vietnamese_output_dir
        return os.path.join(self.output_dir, "VN")

    def resolved_whisper_model(self, cuda_available: bool, vram_gb: float | None = None) -> str:
        """Tên model Whisper thật khi chọn "auto" (large-v3 GPU / medium CPU / small GPU ít VRAM).

        large-v3 int8/float16 cần khoảng 3-4 GB VRAM. Nếu card đồ họa có ít hơn
        3.5 GB VRAM khả dụng, tự động hạ cấp xuống "medium" hoặc "small" để tránh
        lỗi CUDA Out-Of-Memory (OOM).
        """
        if self.whisper_model.strip().lower() != "auto":
            return self.whisper_model
        if not cuda_available:
            return "medium"
        if vram_gb is not None and vram_gb < 3.5:
            return "medium" if vram_gb >= 2.0 else "small"
        return "large-v3"

