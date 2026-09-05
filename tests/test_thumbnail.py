import os
import sys
from PIL import Image, ImageDraw
import pytest

from autodub.media.thumbnail import (
    render_thumbnail,
    generate_high_ctr_thumbnail,
    score_frame_quality,
    detect_badge_from_context,
    extract_info_from_link_or_text,
    PRESETS,
)


def test_no_gui_imports_in_thumbnail():
    """Nguyên tắc 1: Core engine phải 100% headless, không import PyQt/PySide."""
    import autodub.media.thumbnail as thumb_mod

    # Kiểm tra các module GUI không được nằm trong thumb_mod globals hoặc sys.modules liên quan tới thumbnail
    prohibited = ["PySide6", "PySide2", "PyQt6", "PyQt5", "tkinter"]
    for mod_name in prohibited:
        assert mod_name not in thumb_mod.__dict__


def test_frame_scoring_dark_vs_sharp():
    """Nguyên tắc 3: Chấm điểm thực tế - phạt frame đen và ưu tiên frame sắc nét/rực rỡ."""
    # 1. Frame đen hoàn toàn (fade to black)
    black_img = Image.new("RGB", (640, 360), color=(5, 5, 5))
    score_black = score_frame_quality(black_img)
    assert not score_black.is_valid
    assert score_black.total_score < 0

    # 2. Frame trắng xóa cháy sáng
    white_img = Image.new("RGB", (640, 360), color=(250, 250, 250))
    score_white = score_frame_quality(white_img)
    assert not score_white.is_valid
    assert score_white.total_score < 0

    # 3. Frame sắc nét, rực màu, có chi tiết hình vẽ (Manhwa/Anime pattern)
    sharp_img = Image.new("RGB", (640, 360), color=(50, 120, 200))
    draw = ImageDraw.Draw(sharp_img)
    # Vẽ các hoa văn độ tương phản cao và rực rỡ
    for i in range(0, 640, 20):
        draw.line([(i, 0), (i, 360)], fill=(255, 200, 0), width=4)
        draw.rectangle([i, 100, i + 15, 260], fill=(220, 30, 70), outline=(255, 255, 255))

    score_sharp = score_frame_quality(sharp_img)
    assert score_sharp.is_valid
    assert score_sharp.total_score > 50.0
    assert score_sharp.sharpness > 5.0
    assert score_sharp.total_score > score_black.total_score


def test_render_thumbnail_basic(tmp_path):
    frame_path = os.path.join(tmp_path, "frame.jpg")
    img = Image.new("RGB", (1280, 720), color=(40, 40, 80))
    img.save(frame_path)

    out_path = os.path.join(tmp_path, "thumbnail.jpg")
    res = render_thumbnail(
        frame_path=frame_path,
        title="BÍ MẬT KINH HOÀNG TRONG BÓNG TỐI",
        output_path=out_path,
        width=1280,
        height=720,
        badge_text="CỰC SỐC",
    )
    assert os.path.exists(res)
    assert os.path.getsize(res) > 1000
    with Image.open(res) as out_img:
        assert out_img.size == (1280, 720)


def test_render_thumbnail_portrait(tmp_path):
    frame_path = os.path.join(tmp_path, "frame_vertical.jpg")
    img = Image.new("RGB", (720, 1280), color=(60, 20, 50))
    img.save(frame_path)

    out_path = os.path.join(tmp_path, "thumbnail_9_16.jpg")
    res = render_thumbnail(
        frame_path=frame_path,
        title="5 Mẹo Sống Còn Bạn Phải Biết",
        output_path=out_path,
        width=720,
        height=1280,
    )
    assert os.path.exists(res)
    with Image.open(res) as out_img:
        assert out_img.size == (720, 1280)


def test_render_3_presets_distinct(tmp_path):
    """Xác nhận cả 3 preset Cổ Đại, Quân Sư, Chiến Thần render ra kết quả khác nhau."""
    frame_path = os.path.join(tmp_path, "base_frame.jpg")
    img = Image.new("RGB", (1280, 720), color=(50, 50, 70))
    img.save(frame_path)

    results = {}
    for preset_name in ("co_dai", "quan_su", "chien_than"):
        out_file = os.path.join(tmp_path, f"thumb_{preset_name}.jpg")
        res = render_thumbnail(
            frame_path=frame_path,
            title="",
            top_title="Xuyên Không Về Thời Cổ Đại",
            bottom_title="DÙNG TƯ DUY HIỆN ĐẠI LÀM GIÀU",
            badge_text="TẬP 1-100",
            output_path=out_file,
            preset=preset_name,
        )
        assert os.path.exists(res)
        with open(res, "rb") as f:
            results[preset_name] = f.read()

    # Các file của các preset khác nhau phải có dữ liệu byte khác nhau (visual signature riêng)
    assert results["co_dai"] != results["quan_su"]
    assert results["quan_su"] != results["chien_than"]
    assert results["co_dai"] != results["chien_than"]


def test_detect_badge_from_context_all_scenarios():
    """Kiểm tra độ chính xác thuật toán nhận diện số tập từ link, tiêu đề và thời lượng."""
    cases = [
        # 1. Link Bilibili
        ({"source_url": "https://www.bilibili.com/video/BV1xx411c7mD?p=17"}, "TẬP 17"),
        ({"source_url": "https://www.bilibili.com/video/BV1xx411c7mD/?p=5"}, "TẬP 5"),
        # 2. Link YouTube
        ({"source_url": "https://www.youtube.com/watch?v=abc&list=xyz&index=12"}, "TẬP 12"),
        ({"source_url": "https://www.youtube.com/watch?v=abc?ep=8"}, "TẬP 8"),
        # 3. Link Douyin
        ({"source_url": "https://www.douyin.com/video/7234567890?part=15"}, "TẬP 15"),
        # 4. Tiêu đề tiếng Trung & Anime
        ({"title": "【4月/独家】仙逆 第42话【1080P+】"}, "TẬP 42"),
        ({"title": "全职高手 第2季 全12集"}, "1-12"),
        ({"title": "斗破苍穹 第十七回"}, "TẬP 17"),
        ({"title": "百炼成神 第105期"}, "TẬP 105"),
        ({"title": "万界独尊 第125集"}, "TẬP 125"),
        # 5. Dải tập video dài (Range)
        ({"title": "Võ Thần Chúa Tể Tập 1-100 Full Trọn Bộ"}, "1-100"),
        ({"title": "Thôn Phệ Tinh Không Full 1~50 Thuyết Minh"}, "1-50"),
        ({"title": "Đấu La Đại Lục 01-30 Vietsub"}, "1-30"),
        # 6. Tập lẻ tiếng Việt & Anh
        ({"title": "[Vietsub] Đấu Phá Thương Khung - Tập 24 (Thuyết Minh 4K)"}, "TẬP 24"),
        ({"title": "Solo Leveling Ep.05 1080p"}, "TẬP 5"),
        ({"title": "Tây Du Ký Part 3 HD"}, "TẬP 3"),
        ({"title": "Thế Giới Hoàn Mỹ [88] Bản Đẹp"}, "TẬP 88"),
        # 7. Từ khóa đặc biệt
        ({"title": "Tập Cuối | Cái Kết Bất Ngờ Của Nhân Vật Chính"}, "TẬP CUỐI"),
        ({"title": "Đại Kết Cục Phim Cổ Đại Hay Nhất"}, "TẬP CUỐI"),
        ({"title": "Trọn Bộ Phim Hành Động Chiếu Rạp 2026"}, "TRỌN BỘ"),
        # 8. Tên file
        ({"filename": "dau_pha_thuong_khung_ep08.mp4"}, "TẬP 8"),
        ({"filename": "tay_du_ky_tap_25.mkv"}, "TẬP 25"),
        ({"filename": "tien_nghich_1_100.mp4"}, "1-100"),
        # 9. Fallback theo thời lượng
        ({"duration_sec": 4200.0}, "1-100"),
        ({"duration_sec": 2000.0}, "TRỌN BỘ"),
        ({"duration_sec": 600.0}, "TẬP 1"),
    ]

    for kwargs, expected in cases:
        actual = detect_badge_from_context(**kwargs)
        assert actual == expected, f"Lỗi nhận diện cho {kwargs}: kỳ vọng {expected}, thực tế {actual}"


def test_extract_info_from_link_or_text():
    """Kiểm tra hàm rút trích thông tin toàn diện từ link và văn bản chia sẻ Douyin/YouTube."""
    # 1. Văn bản chia sẻ Douyin kèm tiêu đề trong ngoặc vuông
    douyin_text = (
        "7.28 03/24 l@d.cl 复制打开Douyin，看看【万界仙踪 第88集】 "
        "https://v.douyin.com/iJabcde/ 精彩动漫"
    )
    res_douyin = extract_info_from_link_or_text(douyin_text)
    assert res_douyin["platform"] == "Douyin"
    assert res_douyin["badge"] == "TẬP 88"
    assert "万界仙踪" in res_douyin["suggested_title"]
    assert res_douyin["url"] == "https://v.douyin.com/iJabcde/"

    # 2. Link YouTube kèm playlist index
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=25"
    res_yt = extract_info_from_link_or_text(yt_url)
    assert res_yt["platform"] == "YouTube"
    assert res_yt["badge"] == "TẬP 25"
    assert res_yt["url"] == yt_url

    # 3. Link Bilibili
    bili_url = "https://www.bilibili.com/video/BV1xx411c7mD?p=17"
    res_bili = extract_info_from_link_or_text(bili_url)
    assert res_bili["platform"] == "Bilibili"
    assert res_bili["badge"] == "TẬP 17"

