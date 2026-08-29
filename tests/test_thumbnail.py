import os
from PIL import Image
from autodub.media.thumbnail import render_thumbnail, generate_high_ctr_thumbnail


def test_render_thumbnail_basic(tmp_path):
    # Tạo frame ảnh mẫu
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
