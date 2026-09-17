"""Bộ định nghĩa phong cách dịch thuật chuyên sâu cho lồng tiếng video.

Mỗi phong cách có System Prompt chi tiết: vai trò, đại từ xưng hô,
vốn từ vựng, nhịp điệu ngắt nghỉ cho TTS và ví dụ đối chiếu.
"""

from __future__ import annotations

# Danh mục 11 phong cách dịch thực chiến: (Nhãn hiển thị, Mã định danh, Mô tả ngắn)
TRANSLATE_STYLE_DEFINITIONS: list[tuple[str, str, str]] = [
    (
        "Tự nhiên, gần gũi (mặc định)",
        "natural",
        "Giọng người sáng tạo nội dung YouTube/TikTok tự nhiên, thân thiện, câu từ gãy gọn.",
    ),
    (
        "Review phim / Kể chuyện điện ảnh",
        "movie_review",
        "Gay cấn, kịch tính, nhịp nhanh, hook mạnh, xưng hô ngôi thứ 3, cuốn hút người nghe.",
    ),
    (
        "Cổ trang / Kiếm hiệp / Tiên hiệp",
        "wuxia",
        "Âm hưởng Hán-Việt truyền thống, xưng hô chuẩn mực kiếm hiệp/tu chân, chiêu thức trau chuốt.",
    ),
    (
        "Anime / Manga / Hoạt hình",
        "anime_manga",
        "Nhiệt huyết, giàu cảm xúc, trẻ trung, xưng hô thân mật đặc trưng hoạt hình.",
    ),
    (
        "Hài hước / Gen Z / Châm biếm",
        "humorous",
        "Tếu táo, dí dỏm, bắt trend giới trẻ duyên dáng (toang, bá đạo, cạn lời), gây cười tự nhiên.",
    ),
    (
        "Hợp mạng xã hội (Shorts, TikTok)",
        "social",
        "Cực ngắn gọn (dưới 10 từ/câu), nhịp dồn dập, đập thẳng vào tai, loại bỏ từ đệm.",
    ),
    (
        "Trang trọng / Thời sự / Phóng sự",
        "formal",
        "Từ ngữ chuẩn mực, nghiêm túc, phong cách truyền hình quốc gia, xưng hô lịch thiệp.",
    ),
    (
        "Bán hàng / Review sản phẩm",
        "commercial",
        "Thuyết phục, kích thích tò mò, nhấn mạnh lợi ích và giải pháp, thúc đẩy hành động.",
    ),
    (
        "Khoa học / Công nghệ / Tài liệu",
        "tech_documentary",
        "Chính xác thuật ngữ chuyên môn (giữ chuẩn Latin), mạch lạc, dễ hiểu với đại chúng.",
    ),
    (
        "Sáng tạo / Phóng tác nghệ thuật",
        "creative",
        "Giàu hình tượng, nhịp điệu bay bổng, giàu chất thơ và cảm xúc, câu chữ mượt mà.",
    ),
    (
        "Sát nghĩa / Đối chiếu nguyên tác",
        "literal",
        "Bám sát cấu trúc ngữ pháp và nghĩa đen từng câu; phục vụ học ngoại ngữ, tra cứu.",
    ),
]

# Hướng dẫn chi tiết cho từng phong cách gửi tới LLM
STYLE_PROMPTS: dict[str, str] = {
    "natural": """### PHONG CÁCH: TỰ NHIÊN, ĐỜI THƯỜNG (YOUTUBE / TIKTOK CREATOR)
- **Mục tiêu**: Lời thoại nghe như một người Việt Nam đang trò chuyện trực tiếp, tự nhiên và thân mật.
- **Xưng hô**: Người dẫn chuyện xưng "mình" hoặc "tôi", gọi khán giả là "bạn" hoặc "các bạn". Đối thoại nhân vật tùy lứa tuổi (anh/em, cậu/tớ).
- **Văn phong**: Diễn đạt thuần Việt 100%, câu từ gãy gọn. Lược bỏ hoàn toàn các hư từ tiếng Trung/nước ngoài (a, nha, ba, lạp, ma...).""",
    "movie_review": """### PHONG CÁCH: REVIEW PHIM / TÓM TẮT PHIM KỊCH TÍNH (MOVIE RECAP)
- **Mục tiêu**: Kể chuyện điện ảnh gay cấn, lôi cuốn, tạo sự tò mò và hồi hộp cao độ.
- **Xưng hô**: Người kể chuyện xưng "tôi" hoặc ẩn ngôi. Gọi nhân vật: "anh chàng", "cô gái", "gã phản diện", "ông trùm", "tên sát thủ".
- **Văn phong**: Nhịp điệu nhanh, câu văn đanh thép. Dùng động từ mạnh: "ngay lập tức", "không ngờ rằng", "chết lặng", "bi kịch ập đến".""",
    "wuxia": """### PHONG CÁCH: CỔ TRANG / KIẾM HIỆP / TIÊN HIỆP / HUYỀN HUYỄN
- **Mục tiêu**: Mang đậm phong vị kiếm hiệp Kim Dung, Cổ Long và văn học tu chân kỳ ảo.
- **Xưng hô**: Tuyệt đối tuân thủ xưng hô cổ trang: tại hạ / các hạ, huynh / đệ, sư phụ / đồ nhi, bệ hạ / thần, bổn tọa, thiếu hiệp, chưởng môn, công tử.
- **Văn phong**: Tận dụng vốn từ Hán-Việt tinh tế, trang trọng, hào sảng. Tên chiêu thức, võ công, pháp bảo dịch Hán-Việt chuẩn xác.""",
    "anime_manga": """### PHONG CÁCH: ANIME / MANGA / HOẠT HÌNH THANH XUÂN
- **Mục tiêu**: Trẻ trung, giàu cảm xúc, nhiệt huyết, mang đậm hơi thở văn hóa Anime/ACG.
- **Xưng hô**: Cậu - tớ, anh - em, tiền bối - hậu bối, đại ca.
- **Văn phong**: Cảm xúc dạt dào, câu cảm thán sống động ("Thật tuyệt vời!", "Không thể tin được!", "Cố lên!"). Tên nhân vật giữ chuẩn Latin.""",
    "humorous": """### PHONG CÁCH: HÀI HƯỚC / GEN Z / CHÂM BIẾM DUYÊN DÁNG
- **Mục tiêu**: Gây cười tự nhiên, tếu táo, dí dỏm, biến thoại khô khan thành những câu đùa hóm hỉnh.
- **Xưng hô**: Tếu táo: "các đồng chí", "chị đẹp", "anh tài", "thánh này", "hảo hán".
- **Văn phong**: Bắt trend giới trẻ Việt: "toang thật rồi", "bá đạo", "cạn lời", "đỉnh nóc kịch trần", "gánh còng lưng", "hết nước chấm".""",
}

STYLE_PROMPTS.update(
    {
        "social": """### PHONG CÁCH: VIRAL SHORTS / TIKTOK / REELS (SIÊU NGẮN & ĐANH GỌN)
- **Mục tiêu**: Giữ chân người xem khi lướt video ngắn; câu thoại cực ngắn, đập thẳng vào tâm trí.
- **Xưng hô**: Trực diện: "Xem ngay", "Bạn có biết", "Cảnh báo", "Bí mật này".
- **Văn phong**: Mỗi câu tối đa 8 - 12 từ. Ngắt nhịp cực nhanh (1.5 - 2.5s/câu). Cắt bỏ 100% từ đệm rườm rà. Dùng động từ mạnh ngay đầu câu.""",
        "formal": """### PHONG CÁCH: TRANG TRỌNG / THỜI SỰ / PHÓNG SỰ BÁO CHÍ
- **Mục tiêu**: Chuẩn mực, nghiêm túc, khách quan, độ tin cậy cao như bản tin đài truyền hình quốc gia.
- **Xưng hô**: Lịch thiệp: "Kính thưa quý vị", "chúng tôi", "ông/bà" kèm theo chức vụ/học hàm.
- **Văn phong**: Từ ngữ chính luận, diễn đạt sáng rõ. Tuyệt đối không dùng tiếng lóng, khẩu ngữ xuề xòa.""",
        "commercial": """### PHONG CÁCH: QUẢNG CÁO / BÁN HÀNG / REVIEW SẢN PHẨM
- **Mục tiêu**: Thuyết phục, kích thích tò mò, nhấn mạnh lợi ích và giải pháp của sản phẩm.
- **Xưng hô**: Thân tình, chăm sóc: "mình khuyên các bạn", "trải nghiệm thực tế".
- **Văn phong**: Nhấn mạnh điểm đau khách hàng và kết quả vượt trội. Kết thúc bằng lời kêu gọi hành động (Call to action) mượt mà.""",
        "tech_documentary": """### PHONG CÁCH: KHOA HỌC / CÔNG NGHỆ / PHIM TÀI LIỆU
- **Mục tiêu**: Chính xác, khoa học, giải thích hiện tượng phức tạp một cách dễ hiểu cho đại chúng.
- **Xưng hô**: Khách quan, dẫn dắt: "chúng ta hãy cùng tìm hiểu", "các nhà nghiên cứu phát hiện...".
- **Văn phong**: Giữ nguyên tên chuẩn Latin cho thuật ngữ quốc tế (CPU, bán dẫn, thuật toán, AI, gen). Mạch lạc, chuẩn mực.""",
        "creative": """### PHONG CÁCH: SÁNG TẠO / PHÓNG TÁC NGHỆ THUẬT / VĂN HỌC
- **Mục tiêu**: Giàu hình tượng, nhịp điệu bay bổng, giàu chất thơ và cảm xúc, mang tính nghệ thuật cao.
- **Văn phong**: Trau chuốt nhạc tính tiếng Việt, câu văn mượt mà êm ái. Dịch thoáng để câu chữ thăng hoa, ưu tiên chiều sâu tâm trạng.""",
        "literal": """### PHONG CÁCH: SÁT NGHĨA / ĐỐI CHIẾU NGUYÊN TÁC
- **Mục tiêu**: Bám sát cấu trúc ngữ pháp và nghĩa đen của từng từ, phục vụ học ngoại ngữ và đối chiếu tài liệu.
- **Văn phong**: Giữ nguyên cấu trúc câu khi tiếng Việt vẫn hiểu được. Trung thành tối đa với bản gốc, không tự ý phóng tác.""",
    }
)


def get_style_prompt(style_key: str) -> str:
    """Lấy System Prompt chi tiết của phong cách dịch theo mã."""
    key = (style_key or "").strip().lower()
    return STYLE_PROMPTS.get(key, STYLE_PROMPTS["natural"])


def get_style_note(style_key: str) -> str:
    """Lấy mô tả ngắn gọn của phong cách dịch (dùng cho UI/Settings)."""
    key = (style_key or "").strip().lower()
    for _label, k, note in TRANSLATE_STYLE_DEFINITIONS:
        if k == key:
            return note
    return ""
