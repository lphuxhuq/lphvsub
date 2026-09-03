import unicodedata
from autodub.text.vi_numbers import normalize_vi_text


def test_unicode_nfd_to_nfc():
    # Chuỗi NFD (ký tự phân rã e + dấu sắc)
    nfd_text = unicodedata.normalize("NFD", "Tiếng Việt lồng tiếng")
    assert unicodedata.is_normalized("NFD", nfd_text)
    res = normalize_vi_text(nfd_text)
    assert unicodedata.is_normalized("NFC", res)
    assert "Tiếng Việt lồng tiếng" in res


def test_remove_subtitle_audio_tags():
    assert normalize_vi_text("[Âm nhạc] Xin chào các bạn") == "Xin chào các bạn"
    assert normalize_vi_text("(tiếng cười) Hôm nay rất vui") == "Hôm nay rất vui"
    assert normalize_vi_text("Thật tuyệt vời *vỗ tay*") == "Thật tuyệt vời"
    assert normalize_vi_text("(thở dài)") == ""


def test_currency_and_shorthand():
    # 100k -> một trăm nghìn (không phải một trămk)
    assert "nghìn" in normalize_vi_text("Giá chỉ 100k")
    assert "một trăm nghìn" in normalize_vi_text("Giá chỉ 100k")
    assert "năm mươi nghìn đồng" in normalize_vi_text("50k VNĐ")
    assert "hai trăm triệu" in normalize_vi_text("Căn nhà giá 200tr")
    assert "năm mươi nghìn đồng" in normalize_vi_text("50.000đ")
    assert "một trăm đô la" in normalize_vi_text("Thu nhập $100")
    assert "năm mươi đô la" in normalize_vi_text("Giá 50$")


def test_time_and_fractions():
    assert "mười giờ ba mươi phút" in normalize_vi_text("Hẹn gặp lúc 10h30")
    assert "tám giờ" in normalize_vi_text("Lúc 8h sáng")
    assert "một phần hai" in normalize_vi_text("Ăn hết 1/2 cái bánh")
    assert "ba phần tư" in normalize_vi_text("Chiếm 3/4 thị phần")


def test_rankings_and_abbreviations():
    assert "tốp một" in normalize_vi_text("Đạt top 1 server")
    assert "số một" in normalize_vi_text("Vị trí No.1")
    assert "A I" in normalize_vi_text("Trí tuệ nhân tạo AI")
    assert "C P U" in normalize_vi_text("Chip CPU Intel")
    assert "ô kê" in normalize_vi_text("Mọi thứ đều OK")
    assert "vân vân" in normalize_vi_text("Sách, báo, v.v.")
    assert "bác sĩ" in normalize_vi_text("Gặp Dr. Nam")


def test_symbols_and_ranges():
    assert "một đến hai ngày" in normalize_vi_text("Trong khoảng 1-2 ngày")
    assert "cộng" in normalize_vi_text("1 + 1 = 2")
    assert "bằng" in normalize_vi_text("1 + 1 = 2")
    assert "a còng" in normalize_vi_text("Gửi vào email test@gmail.com")
