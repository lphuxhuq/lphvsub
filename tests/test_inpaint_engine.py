import threading
import numpy as np
import pytest
from unittest.mock import MagicMock

from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine


def test_lama_onnx_missing_model_telea_fallback(tmp_path):
    engine = LaMaOnnxEngine(model_path=str(tmp_path / "non_existent_model.onnx"))
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[40:60, 30:70] = 255
    res = engine.inpaint_frame(frame, mask)
    assert res.shape == (100, 100, 3)
    assert res.dtype == np.uint8



def test_lama_onnx_inpaint_frame_mock_session():
    engine = LaMaOnnxEngine(model_path="dummy.onnx")

    # Mock session
    mock_session = MagicMock()
    mock_input_img = MagicMock()
    mock_input_img.name = "image"
    mock_input_mask = MagicMock()
    mock_input_mask.name = "mask"
    mock_output = MagicMock()
    mock_output.name = "output"

    mock_session.get_inputs.return_value = [mock_input_img, mock_input_mask]
    mock_session.get_outputs.return_value = [mock_output]

    # Model trả về tensor ảnh trắng (1.0)
    def mock_run(output_names, inputs):
        img_shape = inputs["image"].shape  # (1, 3, H_pad, W_pad)
        h_pad, w_pad = img_shape[2], img_shape[3]
        out = np.ones((1, 3, h_pad, w_pad), dtype=np.float32)
        return [out]

    mock_session.run.side_effect = mock_run

    engine._session = mock_session
    engine._input_names = ["image", "mask"]
    engine._output_name = "output"

    # Test ảnh kích thước không chia hết cho 8 (vd 65x73)
    frame = np.zeros((65, 73, 3), dtype=np.uint8)  # ảnh đen hoàn toàn
    mask = np.zeros((65, 73), dtype=np.uint8)
    mask[10:30, 20:50] = 255  # đặt vùng cần xóa

    result = engine.inpaint_frame(frame, mask)

    assert result.shape == (65, 73, 3)
    assert result.dtype == np.uint8
    # Vùng ngoài mask (giữ nguyên màu đen 0)
    assert result[5, 5, 0] == 0
    # Vùng trong mask (được thay bằng màu trắng 255 từ model)
    assert result[20, 30, 0] == 255


def test_lama_onnx_empty_frame():
    engine = LaMaOnnxEngine()
    empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
    empty_mask = np.zeros((0, 0), dtype=np.uint8)
    res = engine.inpaint_frame(empty_frame, empty_mask)
    assert res.shape == (0, 0, 3)


def test_lama_onnx_fixed_512_shape_scaling():
    engine = LaMaOnnxEngine(model_path="dummy_512.onnx")

    mock_session = MagicMock()
    mock_input_img = MagicMock()
    mock_input_img.name = "image"
    mock_input_img.shape = [1, 3, 512, 512]
    mock_input_mask = MagicMock()
    mock_input_mask.name = "mask"
    mock_input_mask.shape = [1, 1, 512, 512]
    mock_output = MagicMock()
    mock_output.name = "output"

    mock_session.get_inputs.return_value = [mock_input_img, mock_input_mask]
    mock_session.get_outputs.return_value = [mock_output]

    def mock_run(output_names, inputs):
        img_shape = inputs["image"].shape
        assert img_shape == (1, 3, 512, 512), f"Expected 512x512 input but got {img_shape}"
        mask_shape = inputs["mask"].shape
        assert mask_shape == (1, 1, 512, 512), f"Expected 512x512 mask but got {mask_shape}"
        out = np.ones((1, 3, 512, 512), dtype=np.float32)
        return [out]

    mock_session.run.side_effect = mock_run

    engine._session = mock_session
    engine._input_names = ["image", "mask"]
    engine._input_shapes = [[1, 3, 512, 512], [1, 1, 512, 512]]
    engine._output_name = "output"

    # Frame gốc bất kỳ (ví dụ 100x300)
    frame = np.zeros((100, 300, 3), dtype=np.uint8)
    mask = np.zeros((100, 300), dtype=np.uint8)
    mask[20:50, 40:150] = 255

    res = engine.inpaint_frame(frame, mask)
    assert res.shape == (100, 300, 3)
    assert res.dtype == np.uint8
    # Vùng ngoài mask giữ đen (0)
    assert res[5, 5, 0] == 0
    # Vùng trong mask thành trắng (255)
    assert res[30, 80, 0] == 255

