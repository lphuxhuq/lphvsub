"""Khai báo mọi mục trong trang Cài đặt.

Mỗi mục được mô tả một lần ở đây rồi dùng lại cho việc dựng ô nhập, nạp giá
trị, lưu lại và khôi phục mặc định. Nhờ vậy không bao giờ có chuyện thêm ô
mới mà quên lưu, hoặc đổi tên khóa ở một chỗ mà quên chỗ kia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autodub.media.subtitle import PRESET_CHOICES
from autodub_gui import dub_constants as consts
from autodub_gui import tokens

# Tên sáu thẻ của trang Cài đặt. TAB_BASIC phải luôn đứng đầu vì
# focus_display_name() nhảy thẳng về thẻ số 0.
TAB_BASIC = "Cơ bản"
TAB_VOICE = "Giọng đọc"
TAB_SUBTITLE = "Phụ đề"
TAB_PERF = "Hiệu suất"
#: Thẻ "Dịch thuật" — mọi API Key đã lên máy chủ, ở đây chỉ còn NGỮ CẢNH:
#: những gì người dùng biết về video mà máy chủ không thể tự đoán.
TAB_TRANSLATE = "Dịch thuật"
TAB_ADVANCED = "Nâng cao"

TABS = (TAB_BASIC, TAB_VOICE, TAB_SUBTITLE, TAB_PERF, TAB_TRANSLATE, TAB_ADVANCED)

# Ba thẻ Giọng đọc, Phụ đề và Dịch thuật đã tách thành trang Công cụ riêng
# trên thanh bên, nên trang Cài đặt chỉ còn giữ những thẻ dưới đây để khỏi trùng.
SETTINGS_TABS = (TAB_BASIC, TAB_PERF, TAB_ADVANCED)

# Kiểu ô nhập
COMBO = "combo"
TEXT = "text"
CHECK = "check"
SLIDER = "slider"
NUMBER = "number"
FOLDER = "folder"
FILE = "file"
MULTILINE = "multiline"
FONT = "font"
COLOR = "color"


@dataclass
class Field:
    """Một mục cấu hình: khóa trong tệp cấu hình và cách hiển thị của nó."""

    key: str
    kind: str
    label: str
    tab: str
    group: str
    default: str = ""
    hint: str = ""
    placeholder: str = ""
    suffix: str = ""
    minimum: float = 0.0
    maximum: float = 1.0
    step: float = 0.1
    decimals: int = 2
    options: list[tuple[str, str]] = field(default_factory=list)


_QUALITY_PRESETS = [
    ("Nhanh — ưu tiên tốc độ", "fast"),
    ("Cân bằng (khuyên dùng)", "balanced"),
    ("Chất lượng cao — chạy chậm hơn", "quality"),
]

_SUBTITLE_POSITIONS = [
    ("Dưới màn hình", "bottom"),
    ("Giữa màn hình", "middle"),
    ("Trên màn hình", "top"),
]

_SUBTITLE_DISPLAY = [
    ("Hiện cả câu", "sentence"),
    ("Hiện theo cụm chữ, sáng dần", "karaoke"),
]

_SUBTITLE_BOX = [
    ("Chỉ viền chữ", "none"),
    ("Khối nền mờ sau chữ", "box"),
]

_KARAOKE_EFFECTS = [
    ("Chữ bật lên", "pop"),
    ("Mờ dần", "fade"),
    ("Đổi màu theo lời đọc", "karaoke"),
    ("Không hiệu ứng", "none"),
]


# Toàn bộ các mục, xếp theo thẻ rồi theo nhóm.
FIELDS: tuple[Field, ...] = (
    # -- Thẻ Cơ bản ---------------------------------------------------
    Field("QUALITY_PRESET", COMBO, "Mức chất lượng", TAB_BASIC,
          "Chất lượng tổng thể", "balanced",
          "Chọn một mức là đủ, ứng dụng tự đặt các chi tiết bên dưới. "
          "Ô nào bạn tự chỉnh thì giá trị của bạn được ưu tiên.",
          options=_QUALITY_PRESETS),
    Field("ASR_ENGINE", COMBO, "Bộ nhận dạng", TAB_BASIC,
          "Nghe và chép lời video gốc", "whisper",
          "Whisper nghe được mọi ngôn ngữ. Paraformer chính xác hơn với "
          "video tiếng Trung nhưng phải cài thêm một lần.",
          options=consts.ASR_ENGINES),
    Field("WHISPER_MODEL", COMBO, "Độ chính xác", TAB_BASIC,
          "Nghe và chép lời video gốc", "auto",
          "Mức càng cao nghe càng đúng nhưng chạy lâu hơn và tải về nặng hơn.",
          options=consts.WHISPER_MODELS),
    Field("DEFAULT_SOURCE_LANG", COMBO, "Ngôn ngữ gốc mặc định", TAB_BASIC,
          "Nghe và chép lời video gốc", "zh-CN",
          "Ngôn ngữ được chọn sẵn mỗi khi bạn tạo dự án mới.",
          options=consts.SOURCE_LANGS),
    Field("ASR_GAP_RESCAN", CHECK, "Quét lại khoảng lặng bắt lời bị bỏ sót",
          TAB_BASIC, "Nghe và chép lời video gốc", "true",
          "Sau khi nghe chính, ứng dụng quét thử các khoảng lặng dài giữa "
          "các câu — bắt lại những câu nói nhỏ lẫn trong nhạc nền mà bước "
          "nghe thường bỏ qua. Tắt đi nếu video có nhiều tiếng ồn nền."),
    Field("VIDEO_SPEED", SLIDER, "Tốc độ video", TAB_BASIC,
          "Tốc độ", "1.00",
          "Làm chậm toàn bộ video để giọng tiếng Việt có đủ chỗ. "
          "0.82 nghĩa là video dài thêm khoảng 22 phần trăm. "
          "1.00 là giữ nguyên.",
          suffix="x", minimum=0.5, maximum=1.0, step=0.02),
    Field("VOICE_SPEED", SLIDER, "Tốc độ giọng đọc", TAB_BASIC,
          "Tốc độ", "1.00",
          "1.00 là tốc độ tự nhiên. Tăng lên khi câu tiếng Việt dài hơn câu "
          "gốc và bị chồng sang câu sau.",
          suffix="x", minimum=0.5, maximum=2.0, step=0.05),
    Field("OUTPUT_DIR", FOLDER, "Thư mục lưu video", TAB_BASIC,
          "Nơi lưu kết quả", "./output",
          "Mọi dự án sẽ được lưu vào thư mục này.",
          placeholder="./output"),
    Field("DISPLAY_NAME", TEXT, "Tên hiển thị", TAB_BASIC, "Hiển thị", "",
          "Tên này hiện ở lời chào trên Trang chủ. Để trống thì dùng tên "
          "đăng nhập của máy.",
          placeholder="ví dụ: Dylan"),

    # (Thẻ Giọng đọc không khai báo ô ở đây — toàn bộ thẻ là thư viện giọng
    #  riêng, xem pages/voice_library.py. VIENEU_STYLE render trong đó.)

    # -- Thẻ Phụ đề ---------------------------------------------------
    Field("SUBTITLE_MODE", COMBO, "Kiểu phụ đề mặc định", TAB_SUBTITLE,
          "Mặc định", "none",
          "Kiểu được chọn sẵn mỗi khi bạn tạo dự án mới.",
          options=consts.SUBTITLE_MODES),
    Field("SUBTITLE_PRESET", COMBO, "Bộ kiểu chữ", TAB_SUBTITLE,
          "Mặc định", "clean",
          "Chọn một bộ có sẵn là xong. Muốn tự quyết từng thông số thì chọn "
          "Tự chỉnh rồi sửa các ô bên dưới.",
          options=PRESET_CHOICES),
    Field("SUBTITLE_POSITION", COMBO, "Vị trí chữ", TAB_SUBTITLE,
          "Kiểu chữ", "bottom", "Chữ nằm ở đâu trên khung hình.",
          options=_SUBTITLE_POSITIONS),
    Field("SUBTITLE_FONT", FONT, "Phông chữ", TAB_SUBTITLE, "Kiểu chữ", "",
          "Chỉ liệt kê phông trong thư mục phông của dự án, vì chỉ những "
          "phông này mới chắc chắn hiện đúng trên mọi máy."),
    Field("SUBTITLE_FONT_SIZE", NUMBER, "Cỡ chữ", TAB_SUBTITLE, "Kiểu chữ",
          "22", "Cỡ chữ phụ đề trên video.",
          minimum=8, maximum=96, step=1, decimals=0),
    Field("SUBTITLE_BOLD", CHECK, "Chữ đậm", TAB_SUBTITLE, "Kiểu chữ", "true",
          "Chữ đậm dễ đọc hơn khi video được xem trên điện thoại."),
    Field("SUBTITLE_MARGIN_V", NUMBER, "Cách mép màn hình", TAB_SUBTITLE,
          "Kiểu chữ", "40", "Khoảng cách từ chữ tới mép trên hoặc mép dưới.",
          suffix=" điểm ảnh", minimum=0, maximum=400, step=5, decimals=0),
    Field("SUBTITLE_OUTLINE", NUMBER, "Độ dày viền chữ", TAB_SUBTITLE,
          "Kiểu chữ", "2",
          "Viền giúp chữ đọc được cả khi nền video sáng.",
          minimum=0, maximum=8, step=1, decimals=0),
    Field("SUBTITLE_SHADOW", NUMBER, "Độ đổ bóng", TAB_SUBTITLE, "Kiểu chữ",
          "0", "Bóng nhẹ phía sau chữ. Đặt 0 để tắt.",
          minimum=0, maximum=8, step=1, decimals=0),
    Field("SUBTITLE_COLOR", COLOR, "Màu chữ", TAB_SUBTITLE, "Kiểu chữ",
          tokens.SUBTITLE_TEXT_DEFAULT, "Màu của chữ phụ đề."),
    Field("SUBTITLE_OUTLINE_COLOR", COLOR, "Màu viền chữ", TAB_SUBTITLE,
          "Kiểu chữ", tokens.SUBTITLE_OUTLINE_DEFAULT,
          "Màu viền bao quanh chữ."),
    Field("SUBTITLE_BOX", COMBO, "Nền sau chữ", TAB_SUBTITLE, "Nền chữ",
          "none",
          "Khối nền mờ giúp chữ đọc được trên nền video nhiều chi tiết.",
          options=_SUBTITLE_BOX),
    Field("SUBTITLE_BOX_COLOR", COLOR, "Màu nền", TAB_SUBTITLE, "Nền chữ",
          tokens.SUBTITLE_BOXFILL_DEFAULT, "Màu của khối nền sau chữ."),
    Field("SUBTITLE_BOX_OPACITY", NUMBER, "Độ đục của nền", TAB_SUBTITLE,
          "Nền chữ", "60",
          "0 là trong suốt hẳn, 100 là che kín hoàn toàn.",
          suffix=" phần trăm", minimum=0, maximum=100, step=5, decimals=0),
    Field("SUBTITLE_LINE_WORDS", NUMBER, "Số chữ mỗi dòng", TAB_SUBTITLE,
          "Cách ngắt dòng", "0",
          "Đặt 0 để ứng dụng tự ngắt dòng theo độ dài câu. Video dọc nên đặt "
          "4 tới 6 chữ cho chữ khỏi tràn mép.",
          minimum=0, maximum=20, step=1, decimals=0),
    Field("SUBTITLE_MAX_LINES", NUMBER, "Số dòng tối đa", TAB_SUBTITLE,
          "Cách ngắt dòng", "2",
          "Mỗi lần hiện nhiều nhất bấy nhiêu dòng chữ.",
          minimum=1, maximum=4, step=1, decimals=0),
    Field("SUBTITLE_ALL_CAPS", CHECK, "Viết hoa toàn bộ", TAB_SUBTITLE,
          "Cách ngắt dòng", "false",
          "Chữ hoa hết nhìn mạnh hơn nhưng đọc chậm hơn, hợp video ngắn."),
    Field("SUBTITLE_DISPLAY", COMBO, "Cách hiện chữ", TAB_SUBTITLE,
          "Hiện theo cụm chữ", "sentence",
          "Hiện cả câu là kiểu phụ đề thường. Hiện theo cụm chữ giống lời "
          "bài hát, từng cụm sáng lên theo lời đọc.",
          options=_SUBTITLE_DISPLAY),
    Field("KARAOKE_WORDS_PER_CUE", NUMBER, "Số chữ mỗi cụm", TAB_SUBTITLE,
          "Hiện theo cụm chữ", "3",
          "Mỗi lần hiện bao nhiêu chữ khi dùng kiểu sáng dần.",
          minimum=1, maximum=5, step=1, decimals=0),
    Field("KARAOKE_EFFECT", COMBO, "Hiệu ứng", TAB_SUBTITLE,
          "Hiện theo cụm chữ", "pop", "Cách chữ xuất hiện.",
          options=_KARAOKE_EFFECTS),
    Field("KARAOKE_HIGHLIGHT_COLOR", COLOR, "Màu chữ đang đọc", TAB_SUBTITLE,
          "Hiện theo cụm chữ", tokens.SUBTITLE_HIGHLIGHT_DEFAULT,
          "Màu tô lên cụm chữ đang được đọc."),
    Field("KARAOKE_ALIGNMENT", CHECK, "Canh chữ theo lời đọc", TAB_SUBTITLE,
          "Hiện theo cụm chữ", "true",
          "Bật để từng chữ sáng lên đúng lúc được đọc."),

    Field("AUTO_MASK_HARDSUB", CHECK, "Tự động phát hiện và làm mờ phụ đề gốc",
          TAB_SUBTITLE, "Làm mờ phụ đề gốc", "false",
          "Mặc định TẮT: Không tự động làm mờ khung hình. Chỉ làm mờ khi bạn chủ động vẽ vùng che trong mục Tùy chỉnh phụ đề."),

    # -- Thẻ Hiệu suất ------------------------------------------------
    Field("PARALLEL_WORKERS", NUMBER, "Số việc chạy cùng lúc", TAB_PERF,
          "Hiệu năng", "0",
          "Đặt 0 để ứng dụng tự chọn theo cấu hình máy. Chỉ đổi khi bạn biết "
          "rõ mình cần gì.", minimum=0, maximum=32, step=1, decimals=0),
    Field("VIENEU_MAX_WORKERS", NUMBER, "Số giọng chạy cùng lúc",
          TAB_PERF, "Hiệu năng", "0",
          "Đặt 0 để tự chọn. Mỗi luồng tốn khoảng 1,5 GB bộ nhớ.",
          minimum=0, maximum=8, step=1, decimals=0),
    Field("CAPCUT_THREADS", NUMBER, "Số luồng tạo giọng CapCut",
          TAB_PERF, "Hiệu năng", "8",
          "Số câu tạo giọng CapCut song song qua Device Pool. Mặc định 8 luồng siêu tốc.",
          minimum=1, maximum=16, step=1, decimals=0),
    Field("HQ_BACKGROUND", CHECK, "Giữ nhạc nền chất lượng cao",
          TAB_PERF, "Hiệu năng", "true",
          "Tắt đi thì chạy nhanh hơn nhưng nhạc nền kém hơn một chút."),
    Field("BATCH_PREFETCH_DEPTH", NUMBER, "Số video tải trước trong hàng đợi",
          TAB_PERF, "Tải video", "2",
          "Khi chạy hàng đợi, ứng dụng tải sẵn bấy nhiêu video kế tiếp "
          "trong lúc video hiện tại đang xử lý — gần như hết thời gian "
          "chờ tải. Số càng lớn càng tốn chỗ đĩa (mỗi video tới vài GB).",
          minimum=1, maximum=5, step=1, decimals=0),
    Field("DOWNLOAD_PAGE_WORKERS", NUMBER, "Số video tải cùng lúc",
          TAB_PERF, "Tải video", "2",
          "Ở trang Tải video, nhiều liên kết được tải song song với nhau. "
          "1 là tải lần lượt như trước. Quá 2-3 dễ bị trang web bóp băng "
          "thông từng đường truyền.",
          minimum=1, maximum=4, step=1, decimals=0),

    # -- Thẻ Nâng cao -------------------------------------------------
    Field("DIARIZATION_ENABLED", CHECK, "Phân tách người nói (Speaker Diarization)",
          TAB_ADVANCED, "Phân tách người nói", "true",
          "Tự động nhận diện và phân biệt các nhân vật khác nhau trong video để gán giọng riêng."),
    Field("DIARIZATION_NUM_SPEAKERS", NUMBER, "Số người nói cố định",
          TAB_ADVANCED, "Phân tách người nói", "0",
          "Đặt 0 để tự động ước lượng. Hoặc nhập số cố định (ví dụ 2).",
          minimum=0, maximum=16, step=1, decimals=0),
    Field("DIARIZATION_MAX_SPEAKERS", NUMBER, "Số người nói tối đa",
          TAB_ADVANCED, "Phân tách người nói", "4",
          "Giới hạn số người nói tối đa khi tự động nhận diện.",
          minimum=2, maximum=16, step=1, decimals=0),
    Field("DIARIZATION_THRESHOLD", SLIDER, "Độ nhạy phân tách",
          TAB_ADVANCED, "Phân tách người nói", "0.30",
          "Ngưỡng khoảng cách âm học (Cosine Distance). Càng nhỏ càng dễ tách nhiều nhân vật.",
          minimum=0.05, maximum=0.80, step=0.05, decimals=2),

    # -- Logo / Watermark thương hiệu --
    Field("LOGO_PATH", FILE, "Tệp logo mặc định", TAB_ADVANCED,
          "Logo thương hiệu", "",
          "Đường dẫn đến tệp hình ảnh logo (.png, .jpg, .webp). Để trống nếu không chèn logo."),
    Field("LOGO_POSITION", COMBO, "Vị trí hiển thị logo", TAB_ADVANCED,
          "Logo thương hiệu", "top_right",
          "Vị trí chèn logo lên khung hình video.",
          options=[
              ("Góc trên bên phải (Khuyên dùng)", "top_right"),
              ("Góc trên bên trái", "top_left"),
              ("Góc dưới bên phải", "bottom_right"),
              ("Góc dưới bên trái", "bottom_left"),
              ("Trên cùng ở giữa", "top_center"),
              ("Dưới cùng ở giữa", "bottom_center"),
              ("Chính giữa video", "center"),
          ]),
    Field("LOGO_SCALE", SLIDER, "Kích thước logo", TAB_ADVANCED,
          "Logo thương hiệu", "0.12",
          "Tỷ lệ chiều rộng logo so với chiều rộng khung hình video (mặc định 12%).",
          minimum=0.04, maximum=0.40, step=0.01, decimals=2),
    Field("LOGO_OPACITY", SLIDER, "Độ trong suốt logo", TAB_ADVANCED,
          "Logo thương hiệu", "0.85",
          "Độ rõ nét của logo (1.0 là rõ nét 100%, 0.5 là mờ 50%).",
          minimum=0.10, maximum=1.0, step=0.05, decimals=2),
    Field("LOGO_MARGIN", NUMBER, "Khoảng cách lề", TAB_ADVANCED,
          "Logo thương hiệu", "24",
          "Khoảng cách từ mép khung hình video đến logo (pixel).",
          suffix=" px", minimum=0, maximum=200, step=2, decimals=0),
    Field("LOGO_MOTION", COMBO, "Hiệu ứng logo", TAB_ADVANCED,
          "Logo thương hiệu", "static",
          "Hiệu ứng hiển thị logo trên video.",
          options=[
              ("Cố định tại vị trí đã chọn", "static"),
              ("Chạy nảy mượt mà xung quanh video (Bouncing)", "bounce"),
          ]),

    # -- Watermark chữ chìm chuyển động --
    Field("WATERMARK_TEXT", TEXT, "Chữ watermark chìm", TAB_ADVANCED,
          "Watermark chống reup", "",
          "Dòng chữ watermark chìm chạy quanh video (ví dụ: @KenhCuaBan, SĐT, ID). Để trống nếu không dùng."),
    Field("WATERMARK_OPACITY", SLIDER, "Độ mờ watermark chìm", TAB_ADVANCED,
          "Watermark chống reup", "0.28",
          "Độ mờ / trong suốt của chữ watermark (0.15 - 0.35 là chìm nhẹ tinh tế).",
          minimum=0.08, maximum=0.60, step=0.02, decimals=2),
    Field("WATERMARK_FONT_SIZE", NUMBER, "Cỡ chữ watermark", TAB_ADVANCED,
          "Watermark chống reup", "26",
          "Kích thước phông chữ của watermark chìm.",
          suffix=" px", minimum=14, maximum=72, step=2, decimals=0),
    Field("WATERMARK_SPEED", NUMBER, "Tốc độ di chuyển", TAB_ADVANCED,
          "Watermark chống reup", "40",
          "Tốc độ chạy chuyển động quanh khung hình (pixel/giây).",
          suffix=" px/s", minimum=10, maximum=200, step=5, decimals=0),
    Field("WATERMARK_MOTION", COMBO, "Kiểu chuyển động", TAB_ADVANCED,
          "Watermark chống reup", "bounce",
          "Quỹ đạo di chuyển của watermark trên video.",
          options=[
              ("Chạy nảy mượt mà quanh 4 góc video (Khuyên dùng)", "bounce"),
              ("Cố định góc trên bên phải", "top_right"),
              ("Cố định góc dưới bên phải", "bottom_right"),
              ("Cố định góc dưới bên trái", "bottom_left"),
              ("Cố định góc trên bên trái", "top_left"),
          ]),

    # -- Chống quét bản quyền & Reup (Anti-Content ID) --
    Field("SMART_FLIP", CHECK, "Lật gương thông minh (Smart Flip)", TAB_ADVANCED,
          "Chống quét bản quyền (Anti-Content ID)", "false",
          "Lật ngang hình ảnh video để tránh quét nhận diện bản quyền nhưng tự động giữ nguyên phụ đề tiếng Việt và logo không bị ngược chữ."),
    Field("MICRO_ZOOM", CHECK, "Zoom động & Trượt góc máy (Micro-zoom)", TAB_ADVANCED,
          "Chống quét bản quyền (Anti-Content ID)", "false",
          "Tự động phóng to nhẹ 103% và trượt camera vi mô liên tục để phá vỡ thuật toán quét khuôn hình bản quyền."),
    Field("COLOR_FILTER", COMBO, "Bộ lọc màu điện ảnh (Color Grading)", TAB_ADVANCED,
          "Chống quét bản quyền (Anti-Content ID)", "none",
          "Áp dụng phong cách chỉnh màu điện ảnh chuyên nghiệp cho video.",
          options=[
              ("Nguyên bản (Không lọc màu)", "none"),
              ("Cinematic Warm (Ấm áp điện ảnh)", "cinematic_warm"),
              ("Teal & Orange (Phim bom tấn Hollywood)", "teal_orange"),
              ("Vintage Retro (Hoài niệm cổ điển)", "vintage"),
              ("Moody Dark (Tương phản cao sâu lắng)", "moody_dark"),
              ("Clean Film (Trong trẻo sắc nét)", "clean_film"),
          ]),

    Field("TRANSLATE_ANALYSIS", CHECK, "Đọc hiểu video trước khi dịch",
          TAB_ADVANCED, "Chất lượng dịch", "true",
          "Ứng dụng đọc qua toàn bộ lời thoại để nắm bối cảnh, nhờ vậy xưng "
          "hô và thuật ngữ nhất quán hơn."),
    Field("TRANSLATE_REVIEW", CHECK, "Rà lại bản dịch một lượt nữa",
          TAB_ADVANCED, "Chất lượng dịch", "true",
          "Chạy thêm một lượt để sửa câu ngượng. Tốn thêm thời gian."),
    Field("TRANSLATE_CPS_BUDGET", SLIDER, "Số chữ mỗi giây", TAB_ADVANCED,
          "Chất lượng dịch", "12.5",
          "Giới hạn độ dài câu dịch để đọc kịp. Càng nhỏ thì câu càng ngắn "
          "gọn.", minimum=8.0, maximum=20.0, step=0.5, decimals=1),
    Field("VOICE_POSTPROCESS", CHECK, "Làm đều độ lớn giọng đọc",
          TAB_ADVANCED, "Xử lý âm thanh", "true",
          "Cân bằng để câu nào cũng nghe rõ như nhau, không câu to câu nhỏ."),
    Field("VOICE_TARGET_LUFS", SLIDER, "Độ lớn giọng đọc", TAB_ADVANCED,
          "Xử lý âm thanh", "-16.0",
          "Càng gần 0 thì giọng càng to. Mức thường dùng cho video là -16.",
          suffix=" dB", minimum=-24.0, maximum=-10.0, step=0.5, decimals=1),
    Field("BG_DUCK_VOICE_DB", SLIDER, "Giảm nhạc nền khi có lời",
          TAB_ADVANCED, "Xử lý âm thanh", "-8.0",
          "Nhạc nền tự nhỏ đi bấy nhiêu mỗi khi có lời thoại tiếng Việt.",
          suffix=" dB", minimum=-24.0, maximum=0.0, step=0.5, decimals=1),
    Field("ORIGINAL_VOICE_DUCK_DB", SLIDER, "Giảm tiếng gốc khi nhân vật nói",
          TAB_ADVANCED, "Xử lý âm thanh", "-16.0",
          "Chế độ nhạc nền Giữ âm gốc: khi nhân vật đang nói, tiếng gốc chìm "
          "xuống bấy nhiêu để giọng Việt nổi lên mà vẫn nghe rõ nền — cảm "
          "giác thuyết minh chân thật. Mức gợi ý: tự nhiên -16, rõ tiếng "
          "Việt -20, cân bằng -12.",
          suffix=" dB", minimum=-30.0, maximum=0.0, step=0.5, decimals=1),
    Field("DUCK_ATTACK_MS", NUMBER, "Thời gian chìm tiếng gốc", TAB_ADVANCED,
          "Xử lý âm thanh", "80",
          "Tiếng gốc trượt xuống trong bao nhiêu mili-giây khi nhân vật bắt "
          "đầu nói — ngắn là đột ngột, dài là mềm mà hơi trễ.",
          suffix=" mili-giây", minimum=10, maximum=500, step=10, decimals=0),
    Field("DUCK_RELEASE_MS", NUMBER, "Thời gian hồi tiếng gốc", TAB_ADVANCED,
          "Xử lý âm thanh", "140",
          "Tiếng gốc trượt lại lên sau khi nhân vật ngừng nói.",
          suffix=" mili-giây", minimum=10, maximum=1000, step=10, decimals=0),
    Field("DUB_PRE_ROLL_MS", NUMBER, "Đẩy sớm giọng Việt", TAB_ADVANCED,
          "Căn thời gian", "0",
          "Bắt đầu giọng Việt sớm hơn chút xíu so với lúc nhân vật ngừng "
          "lặng (0-80). 0 là bám đúng khoảnh khắc nhân vật cất tiếng.",
          suffix=" mili-giây", minimum=0, maximum=80, step=5, decimals=0),
    Field("SOFT_TIMING_FIT", CHECK, "Tự căn lại thời điểm từng câu",
          TAB_ADVANCED, "Căn thời gian", "true",
          "Dịch nhẹ thời điểm các câu để lời thoại không chồng lên nhau."),
    Field("TIMING_MAX_DRIFT_S", SLIDER, "Cho phép lệch tối đa", TAB_ADVANCED,
          "Căn thời gian", "1.5",
          "Mỗi câu được dịch đi nhiều nhất bấy nhiêu giây so với bản gốc.",
          suffix=" giây", minimum=0.0, maximum=5.0, step=0.1, decimals=1),
    Field("TIMING_MIN_GAP_S", SLIDER, "Khoảng nghỉ tối thiểu", TAB_ADVANCED,
          "Căn thời gian", "0.08",
          "Khoảng lặng ngắn giữa hai câu liền nhau cho dễ nghe.",
          suffix=" giây", minimum=0.0, maximum=1.0, step=0.01),
    Field("TIMING_MAX_ATEMPO", SLIDER, "Mức nén lời tối đa", TAB_ADVANCED,
          "Căn thời gian", "1.15",
          "Câu quá dài có thể được đọc nhanh hơn tối đa bấy nhiêu lần.",
          suffix="x", minimum=1.0, maximum=1.6, step=0.01),
    Field("VOICE_FIT_STRETCH", CHECK, "Kéo dài giọng đọc lấp khoảng lặng",
          TAB_ADVANCED, "Căn thời gian", "false",
          "Câu tiếng Việt đọc xong sớm hơn lời gốc thì đọc chậm lại một chút "
          "(tối đa 10 phần trăm) cho hết khoảng lặng cuối câu. Giọng nghe "
          "chậm hơn nhẹ — chỉ bật khi bạn thấy khoảng lặng cuối câu nhiều "
          "quá."),
    Field("AUTO_CLEAN_INTERMEDIATES", CHECK, "Tự dọn tệp trung gian sau khi xuất",
          TAB_ADVANCED, "Dung lượng đĩa", "false",
          "Xuất video xong là dọn ngay các tệp trung gian nặng. Tiết kiệm "
          "đĩa, nhưng dự án đó sẽ không sửa từng câu hay xuất lại được nữa."),

    # -- Thẻ Dịch thuật ------------------------------------------------
    Field("TRANSLATE_ENABLED", CHECK, "Bật dịch tự động", TAB_TRANSLATE,
          "Dịch tự động", "true",
          "Bật: ứng dụng gọi API dịch toàn bộ. Tắt: dừng ở bước dịch và hướng dẫn bạn dịch tay."),
    Field("TRANSLATE_BATCH_SIZE", NUMBER, "Số câu mọi lượt gửi", TAB_TRANSLATE,
          "Dịch tự động", "40",
          "Lô nhỏ hơn thì chậm hơn một chút nhưng mạch dịch bám ngữ cảnh sát "
          "hơn.",
          minimum=1, maximum=100, step=5, decimals=0),
    Field("TRANSLATE_DIRECT_WORKERS", NUMBER, "Số luồng dịch song song",
          TAB_TRANSLATE, "Dịch tự động", "0",
          "0 để tự chọn theo số API Key (tối thiểu 2). Nhiều luồng dịch "
          "nhanh hơn nhiều; đặt quá cao dễ bị hạn tốc 429.",
          minimum=0, maximum=8, step=1, decimals=0),
    Field("TRANSLATE_THINKING", CHECK, "Để AI suy nghĩ kỹ trước khi dịch",
          TAB_TRANSLATE, "Dịch tự động", "false",
          "Bật để model Gemini 2.5 suy nghĩ nhiều bước trước khi dịch — chậm "
          "hơn gấp nhiều lần, chỉ đáng bật khi bản dịch hay sai nghĩa."),

    # Khóa API dịch AI
    Field("GEMINI_API_KEY", MULTILINE, "Danh sách Google Gemini API Key", TAB_TRANSLATE,
          "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)", "",
          "Nhập 1 hoặc NHIỀU API Key (mỗi key một dòng hoặc cách nhau bằng dấu phẩy). Ứng dụng sẽ tự động chia luồng song song tương ứng với số lượng Key để tăng tốc độ dịch tối đa!",
          placeholder="AIzaSyKey1...\nAIzaSyKey2...\nAIzaSyKey3..."),
    Field("GEMINI_MODEL", COMBO, "Mô hình Gemini", TAB_TRANSLATE,
          "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)", "gemini-2.5-flash",
          "Mô hình Gemini dùng để dịch trực tiếp và viết tiêu đề/mô tả.",
          options=[
              ("Gemini 2.5 Flash (Mới nhất, nhanh và dịch chuẩn)", "gemini-2.5-flash"),
              ("Gemini 1.5 Flash (Ổn định, tốc độ cao)", "gemini-1.5-flash"),
              ("Gemini 2.5 Pro (Thông minh, văn phong cao cấp)", "gemini-2.5-pro"),
          ]),
    Field("OPENROUTER_API_KEY", TEXT, "OpenRouter API Key", TAB_TRANSLATE,
          "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)", "",
          "Khóa API OpenRouter (dùng được nhiều mô hình tại openrouter.ai).",
          placeholder="sk-or-v1-..."),
    Field("OPENAI_API_KEY", TEXT, "OpenAI API Key", TAB_TRANSLATE,
          "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)", "",
          "Khóa API OpenAI chính thức từ platform.openai.com.",
          placeholder="sk-..."),
    Field("DEEPSEEK_API_KEY", TEXT, "DeepSeek API Key", TAB_TRANSLATE,
          "Khóa API dịch AI (Gọi trực tiếp & Chia luồng song song)", "",
          "Khóa API DeepSeek từ platform.deepseek.com.",
          placeholder="sk-..."),

    Field("TRANSLATE_DOMAIN", TEXT, "Chủ đề video", TAB_TRANSLATE,
          "Ngữ cảnh video", "",
          "Càng cụ thể thì bản dịch càng đúng ngữ cảnh. Để trống thì máy chủ "
          "tự đoán từ lời thoại.",
          placeholder="ví dụ: review công nghệ, phim cổ trang, vlog ẩm thực"),
    Field("TRANSLATE_CONTEXT", MULTILINE, "Ngữ cảnh", TAB_TRANSLATE,
          "Ngữ cảnh video", "",
          "Mô tả kênh nói về gì, người xem là ai.",
          placeholder="ví dụ: Kênh đập hộp linh kiện máy tính giá rẻ, "
                      "người xem là dân tự lắp máy."),
    Field("TRANSLATE_PRONOUNS", TEXT, "Cách xưng hô", TAB_TRANSLATE,
          "Ngữ cảnh video", "",
          "Giúp bản dịch xưng hô nhất quán từ đầu tới cuối.",
          placeholder="ví dụ: mình – các bạn  |  tôi – anh em"),
    Field("TRANSLATE_GLOSSARY", MULTILINE, "Thuật ngữ cố định", TAB_TRANSLATE,
          "Ngữ cảnh video", "",
          "Mỗi dòng một cặp, viết dạng gốc = bản dịch.",
          placeholder="显卡 = card đồ họa\n翻车 = toang"),
    Field("TRANSLATE_STYLE_NOTES", TEXT, "Yêu cầu khác cho người dịch",
          TAB_TRANSLATE, "Ngữ cảnh video", "",
          "Ghi chú này được gửi kèm mỗi lần dịch.",
          placeholder="ví dụ: giọng hài hước, giữ tên nhân vật Hán Việt"),

    Field("GENERATE_METADATA", CHECK,
          "Tạo tiêu đề, mô tả và thẻ cho mạng xã hội", TAB_TRANSLATE,
          "Nội dung đăng bài", "true",
          "Kết quả lưu vào thư mục dự án, tệp youtube_post.txt. Tắt đi nếu bạn tự viết."),

    Field("CUSTOM_AI_BASE_URL", TEXT, "Địa chỉ API dịch AI", TAB_TRANSLATE,
          "Dịch AI tùy chỉnh", "https://hhtechapi.net/v1",
          "Địa chỉ máy chủ API tương thích OpenAI dùng cho dịch thuật."),
    Field("CUSTOM_AI_API_KEY", TEXT, "Khóa API dịch AI", TAB_TRANSLATE,
          "Dịch AI tùy chỉnh", "",
          "Khóa API nếu sử dụng máy chủ dịch thuật riêng."),
    Field("CUSTOM_AI_MODEL", TEXT, "Mô hình dịch AI", TAB_TRANSLATE,
          "Dịch AI tùy chỉnh", "deepseek-v4-flash",
          "Tên mô hình AI dùng để dịch thuật (ví dụ deepseek-v4-flash)."),

    Field("AI_STUDIO_ENABLED", CHECK,
          "Dịch qua Google AI Studio (miễn phí, không cần API Key)",
          TAB_TRANSLATE, "Dịch qua AI Studio (Trình duyệt)", "false",
          "Dùng Google AI Studio qua trình duyệt Chrome để dịch — tận dụng "
          "tài khoản Google miễn phí, không cần API Key. Chậm hơn API trực "
          "tiếp nhưng không tốn phí. Cần đăng nhập Google lần đầu. "
          "Nếu ô Gemini/DeepSeek/OpenRouter/OpenAI còn API Key, pipeline vẫn "
          "đi phương thức 1 — hãy xóa key hoặc chọn AI Studio ở bước tạo dự án. "
          "Model miễn phí: Gemini 2.5 Flash / 2.0 Flash / 1.5 Flash."),
    Field("AI_STUDIO_HEADLESS", CHECK,
          "Chạy ẩn Chrome khi dịch", TAB_TRANSLATE,
          "Dịch qua AI Studio (Trình duyệt)", "false",
          "Bật: Chrome chạy ngầm (headless). Tắt: hiển thị cửa sổ Chrome "
          "để quan sát quá trình dịch."),
    Field("AI_STUDIO_SINGLE_CHAT", CHECK,
          "Dịch toàn bộ trong 1 cuộc trò chuyện", TAB_TRANSLATE,
          "Dịch qua AI Studio (Trình duyệt)", "true",
          "Gửi toàn bộ phụ đề cùng prompt trong 1 chat AI Studio. Nhanh hơn, "
          "ít lỗi Permission Denied. Tắt nếu video dài/quá nhiều câu."),
    Field("AI_STUDIO_CHROME_PROFILE", TEXT, "Thư mục Chrome Profile",
          TAB_TRANSLATE, "Dịch qua AI Studio (Trình duyệt)", "",
          "Để trống = tự động dùng %LOCALAPPDATA%\\lphvsub\\ChromeProfile_AIStudio. "
          "Thay đổi nếu muốn dùng profile Chrome khác.",
          placeholder=r"%LOCALAPPDATA%\lphvsub\ChromeProfile_AIStudio"),
)

# Khóa do ứng dụng tự tính hoặc chỉ dùng nội bộ, không hiện thành ô nhập chữ.
# Mỗi khóa đều phải kèm lý do rõ ràng.
EXEMPT_KEYS: dict[str, str] = {
    "VIENEU_VOICE": "chọn ở thẻ Giọng đọc bằng thẻ giọng, không phải ô nhập chữ",
    "VIENEU_STYLE": "chọn ở cột phải của thẻ Giọng đọc",
    "VOICE_RECENT": "ứng dụng tự ghi lại các giọng dùng gần đây",
    "WHISPER_BEAM_SIZE": "nút vặn nâng cao cho người biết việc (đổi tốc độ "
                         "lấy độ chính xác); mặc định giữ nguyên chất lượng, "
                         "ai cần thì sửa thẳng trong .env",
    "UPDATE_REPO": "địa chỉ kho phát hành cố định của ứng dụng, người dùng "
                   "không cần đổi; ai cần thì sửa thẳng trong .env",
    "SUPPORT_URL": "đường dẫn biểu mẫu báo lỗi cố định, chỉ hiện ở nút Gửi "
                   "báo lỗi chứ không phải cấu hình của người dùng",
    "VOXDUB_API_URL": "địa chỉ máy chủ được nhúng cứng vào bản đóng gói; "
                      "chỉ đọc từ .env khi chạy từ mã nguồn (dev), người "
                      "dùng cuối không đổi được và không cần đổi",
    "VIDEO_ASPECT_PRESET": "tỷ lệ khung hình chọn trực tiếp trên giao diện tạo dự án",
    "VOICE_COMPACT_TRANSLATE_ENABLED": "tùy chọn kỹ thuật đồng bộ giọng đọc tự động",
    "VOICE_SCENE_GUARD_ENABLED": "tùy chọn kỹ thuật chống tràn giọng qua chuyển cảnh",
    "VOICE_VAD_TRIM_ENABLED": "tùy chọn kỹ thuật cắt khoảng lặng thừa của file TTS",
    "WATERMARK_COLOR": "chọn trực tiếp trong hộp thoại tùy chỉnh kiểu phụ đề & hiệu ứng",
}


def fields_of(tab: str) -> list[Field]:
    """Các mục thuộc một thẻ, giữ nguyên thứ tự khai báo."""
    return [f for f in FIELDS if f.tab == tab]


def groups_of(tab: str) -> list[str]:
    """Tên các nhóm trong một thẻ, không lặp lại."""
    seen: list[str] = []
    for item in fields_of(tab):
        if item.group not in seen:
            seen.append(item.group)
    return seen


def defaults() -> dict[str, str]:
    """Giá trị mặc định của mọi mục."""
    return {item.key: item.default for item in FIELDS}


def field_keys() -> set[str]:
    """Tập khóa mà trang Cài đặt quản lý."""
    return {item.key for item in FIELDS}
