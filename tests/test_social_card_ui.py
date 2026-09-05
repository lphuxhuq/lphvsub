"""Kiểm thử cho component SocialMetadataCard và tích hợp hiển thị metadata trên NewProjectPage."""
import os
import pytest
from PySide6.QtWidgets import QApplication
from autodub.pipeline import DubResult
from autodub_gui.ui.social_card import SocialMetadataCard


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_social_card_initial_state(qapp):
    card = SocialMetadataCard()
    assert hasattr(card, "btn_copy_title")
    assert hasattr(card, "btn_copy_caption")
    assert hasattr(card, "btn_copy_tags")
    assert hasattr(card, "btn_copy_all")
    assert hasattr(card, "btn_open_video")
    assert hasattr(card, "btn_open_folder")
    assert hasattr(card, "btn_edit")


def test_social_card_set_metadata(qapp):
    card = SocialMetadataCard()
    meta = {
        "title": "Tóm Tắt Phim Mới Nhất 2026",
        "caption": "Phim cực hay và gay cấn, xem ngay kẻo lỡ!",
        "hashtags": ["#shorts", "#reviewphim", "#trending"],
        "hashtags_str": "#shorts #reviewphim #trending",
    }
    card.set_metadata(
        meta=meta,
        video_name="tap_1.mp4",
        video_path="D:/Project/tap_1_dubbed.mp4",
        work_dir="D:/Project/workdir",
    )

    assert card.isVisible() or not card.isHidden()
    assert card.title_text() == "Tóm Tắt Phim Mới Nhất 2026"
    assert card.caption_text() == "Phim cực hay và gay cấn, xem ngay kẻo lỡ!"
    assert "#reviewphim" in card.hashtags_text()


def test_social_card_copy_actions(qapp, monkeypatch):
    card = SocialMetadataCard()
    meta = {
        "title": "Tóm Tắt Phim Mới Nhất",
        "caption": "Mô tả nội dung phim",
        "hashtags": ["#shorts", "#trending"],
        "hashtags_str": "#shorts #trending",
    }
    card.set_metadata(meta=meta, video_name="video.mp4")

    copied_texts = []
    original_set_text = card._set_clipboard_text

    def mock_set_text(text: str):
        copied_texts.append(text)
        try:
            original_set_text(text)
        except Exception:
            pass

    monkeypatch.setattr(card, "_set_clipboard_text", mock_set_text)

    # Chép Tiêu đề
    card.btn_copy_title.click()
    assert copied_texts[-1] == "Tóm Tắt Phim Mới Nhất"

    # Chép Caption
    card.btn_copy_caption.click()
    assert copied_texts[-1] == "Mô tả nội dung phim"

    # Chép Hashtags
    card.btn_copy_tags.click()
    assert "#shorts" in copied_texts[-1]

    # Chép Toàn bộ
    card.btn_copy_all.click()
    full_text = copied_texts[-1]
    assert "Tóm Tắt Phim Mới Nhất" in full_text
    assert "Mô tả nội dung phim" in full_text
    assert "#shorts #trending" in full_text


def test_social_card_flow_layout_wrapping(qapp):
    card = SocialMetadataCard()
    card.setFixedWidth(450)
    tags = [
        "#KienTrucCoDai", "#NhaVanNam", "#ThietKe", "#XayDung", "#LichSu",
        "#KhamPha", "#BiMat", "#VanHoa", "#KienTruc", "#DocLa"
    ]
    meta = {
        "title": "Bí mật xây nhà cổ đại chống trộm, chống ẩm ở Vân Nam: Kiến trúc",
        "caption": "Sốc! Ngôi nhà cổ đại Vân Nam này chống trộm, chống ẩm đỉnh cao thế nào?",
        "hashtags": tags,
    }
    card.set_metadata(meta)
    card.show()
    qapp.processEvents()

    # Xác nhận chiều cao title và caption không bị xén bớt
    assert card.lbl_title.height() >= 44
    assert card.lbl_caption.height() >= 38

    # Xác nhận các nút tag không bị ép co (tất cả các tag có độ dài chữ đầy đủ, width >= 50px)
    assert card.tags_layout.count() == 10
    for i in range(card.tags_layout.count()):
        item = card.tags_layout.itemAt(i)
        assert item is not None and item.widget() is not None
        btn = item.widget()
        assert btn.width() >= 50
        assert btn.text() == tags[i]

    # Xác nhận các tag đã được bẻ dòng tự động (chiều cao container lớn hơn 1 dòng đơn)
    assert card.tags_container.height() >= 48


def test_new_project_page_shows_social_card_on_complete(qapp, tmp_path):
    from autodub_gui.pages.new_project_page import NewProjectPage
    from autodub.config import Settings
    from autodub.workdir import save_social_metadata

    # Tạo mock work_dir có metadata
    work_dir = str(tmp_path / "test_proj")
    os.makedirs(os.path.join(work_dir, "youtube"), exist_ok=True)
    video_out = os.path.join(work_dir, "video_dubbed.mp4")
    with open(video_out, "w") as f:
        f.write("mock video")

    save_social_metadata(work_dir, {
        "title": "Video Dự Án Test",
        "caption": "Caption test hoàn chỉnh",
        "hashtags": ["#test", "#viral"],
    })

    page = NewProjectPage(lambda: Settings(), None)
    assert hasattr(page, "social_card")
    assert hasattr(page, "btn_toggle_log")

    result = DubResult(
        work_dir=work_dir,
        status="done",
        report={
            "files": {"dubbed_video": video_out},
            "total_segments": 10,
        },
    )

    page._show_completed(result)

    assert not page.social_card.isHidden()
    assert page.social_card.title_text() == "Video Dự Án Test"
    assert "Caption test hoàn chỉnh" in page.social_card.caption_text()

    # Kiểm tra các widget khác đã được ẩn để nhường chỗ
    assert page.preview.isHidden()
    assert page.steps.isHidden()
    assert page.run_stats.isHidden()
    assert page.log.isHidden()
    assert not page.btn_toggle_log.isHidden()

    # Nút bật/tắt nhật ký hoạt động chính xác
    page.btn_toggle_log.click()
    assert not page.log.isHidden()
    assert "Ẩn nhật ký" in page.btn_toggle_log.text()

    page.btn_toggle_log.click()
    assert page.log.isHidden()
    assert "Xem nhật ký" in page.btn_toggle_log.text()

    # Khi worker kết thúc (_set_running(False)), không vô tình hiện lại preview đè lên social_card
    page._set_running(False)
    assert not page.social_card.isHidden()
    assert page.preview.isHidden()
