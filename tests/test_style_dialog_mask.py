import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from autodub_gui.style_dialog import StyleDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_style_dialog_mask_options_defaults(qapp):
    style = {"font_size": 20, "position": "bottom"}
    dialog = StyleDialog(
        video_path=None,
        style=style,
        regions=[],
    )

    mask_opts = dialog.mask_options()
    assert mask_opts["mask_method"] == "blur"
    assert mask_opts["inpaint_engine"] == "lama_onnx"
    assert mask_opts["inpaint_device"] == "auto"


def test_style_dialog_mask_options_custom(qapp):
    style = {"font_size": 20, "position": "bottom"}
    custom_mask = {
        "mask_method": "ai_inpaint",
        "inpaint_engine": "vsr_cli",
        "inpaint_device": "cuda",
    }
    dialog = StyleDialog(
        video_path=None,
        style=style,
        regions=[],
        mask_options=custom_mask,
    )

    # Kiểm tra UI nạp đúng trạng thái
    assert dialog.rb_mask_ai.isChecked()
    assert not dialog.rb_mask_blur.isChecked()
    assert dialog.cb_inpaint_engine.currentData() == "vsr_cli"
    assert dialog.cb_inpaint_device.currentData() == "cuda"

    # Kiểm tra mask_options() trả về đúng
    mask_opts = dialog.mask_options()
    assert mask_opts["mask_method"] == "ai_inpaint"
    assert mask_opts["inpaint_engine"] == "vsr_cli"
    assert mask_opts["inpaint_device"] == "cuda"


def test_style_dialog_mask_options_toggle(qapp):
    style = {"font_size": 20, "position": "bottom"}
    dialog = StyleDialog(
        video_path=None,
        style=style,
        regions=[],
    )

    # Chuyển sang AI Inpainting trên UI
    dialog.rb_mask_ai.setChecked(True)
    dialog.cb_inpaint_engine.setCurrentIndex(dialog.cb_inpaint_engine.findData("lama_onnx"))
    dialog.cb_inpaint_device.setCurrentIndex(dialog.cb_inpaint_device.findData("directml"))

    mask_opts = dialog.mask_options()
    assert mask_opts["mask_method"] == "ai_inpaint"
    assert mask_opts["inpaint_engine"] == "lama_onnx"
    assert mask_opts["inpaint_device"] == "directml"
