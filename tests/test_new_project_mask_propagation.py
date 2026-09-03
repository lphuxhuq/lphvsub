import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest
from autodub_gui.pages.new_project_page import NewProjectPage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dub_request_mask_defaults_and_explicit():
    # Default values must be backward-compatible
    req_default = DubRequest()
    assert req_default.mask_method == "blur"
    assert req_default.inpaint_engine == "lama_onnx"
    assert req_default.inpaint_device == "auto"

    # Explicit values
    req_ai = DubRequest(
        mask_method="ai_inpaint",
        inpaint_engine="lama_onnx",
        inpaint_device="cpu",
    )
    assert req_ai.mask_method == "ai_inpaint"
    assert req_ai.inpaint_engine == "lama_onnx"
    assert req_ai.inpaint_device == "cpu"


def test_new_project_page_values_default(qapp):
    settings = Settings()
    page = NewProjectPage(settings_provider=lambda: settings)

    vals = page.values()
    assert vals["mask_method"] == "blur"
    assert vals["inpaint_engine"] == "lama_onnx"
    assert vals["inpaint_device"] == "auto"


def test_new_project_page_values_explicit_ai(qapp):
    settings = Settings()
    page = NewProjectPage(settings_provider=lambda: settings)

    page._mask_method = "ai_inpaint"
    page._inpaint_engine = "lama_onnx"
    page._inpaint_device = "cpu"

    vals = page.values()
    assert vals["mask_method"] == "ai_inpaint"
    assert vals["inpaint_engine"] == "lama_onnx"
    assert vals["inpaint_device"] == "cpu"


def test_new_project_page_build_request_preserves_ai(qapp, tmp_path):
    settings = Settings()
    page = NewProjectPage(settings_provider=lambda: settings)

    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.write_bytes(b"video content")
    page.step_video.set_file(str(dummy_video))

    page._mask_method = "ai_inpaint"
    page._inpaint_engine = "lama_onnx"
    page._inpaint_device = "cuda"

    req = page._build_request()
    assert req is not None
    assert req.mask_method == "ai_inpaint"
    assert req.inpaint_engine == "lama_onnx"
    assert req.inpaint_device == "cuda"


def test_new_project_page_draft_compatibility(qapp, tmp_path):
    settings = Settings()
    page = NewProjectPage(settings_provider=lambda: settings)

    # 1. Old draft without mask keys
    old_draft = {"url": "https://example.com/video.mp4"}
    page._blur_regions = []
    page._mask_method = old_draft.get("mask_method")
    page._inpaint_engine = old_draft.get("inpaint_engine")
    page._inpaint_device = old_draft.get("inpaint_device")

    vals = page.values()
    assert vals["mask_method"] == "blur"
    assert vals["inpaint_engine"] == "lama_onnx"
    assert vals["inpaint_device"] == "auto"

    # 2. Draft with explicit AI settings
    ai_draft = {
        "mask_method": "ai_inpaint",
        "inpaint_engine": "lama_onnx",
        "inpaint_device": "directml",
    }
    page._mask_method = ai_draft.get("mask_method")
    page._inpaint_engine = ai_draft.get("inpaint_engine")
    page._inpaint_device = ai_draft.get("inpaint_device")

    vals_ai = page.values()
    assert vals_ai["mask_method"] == "ai_inpaint"
    assert vals_ai["inpaint_engine"] == "lama_onnx"
    assert vals_ai["inpaint_device"] == "directml"


@patch("autodub.media.video.merge_video")
@patch("autodub.text.subtitles.refresh_subtitles", return_value=("", ""))
def test_pipeline_export_phase_preserves_ai_options(mock_refresh, mock_merge_video, tmp_path):
    settings = Settings()
    pipeline = DubPipeline(settings)

    state = {
        "segments": [],
        "tts_results": [],
        "merge_dir": str(tmp_path),
        "video_path": str(tmp_path / "video.mp4"),
        "merged_audio_path": str(tmp_path / "audio.wav"),
        "audio_path": str(tmp_path / "audio.wav"),
        "folder_name": "test_folder",
        "lang_code": "zh",
        "target": "vi",
        "subtitle_style": {},
        "deferred_speed": None,
        "mask_method": "ai_inpaint",
        "inpaint_engine": "lama_onnx",
        "inpaint_device": "cpu",
    }

    target = MagicMock()
    target.key = "vi"
    target.iso639_2 = "vie"

    dummy_report = {
        "total_segments": 0,
        "total_original_duration": 0.0,
        "total_tts_duration": 0.0,
        "segments_speed_adjusted": 0,
        "session_id": "test_folder",
        "source_url": "",
    }
    with patch.object(pipeline, "_generate_content", return_value={}), \
         patch.object(pipeline, "_build_report", return_value=dummy_report), \
         patch.object(pipeline, "_build_timing_guide", return_value={}):
        pipeline._export_phase(state, str(tmp_path), target)

    mock_merge_video.assert_called_once()
    kwargs = mock_merge_video.call_args[1]
    assert kwargs["mask_method"] == "ai_inpaint"
    assert kwargs["inpaint_engine"] == "lama_onnx"
    assert kwargs["inpaint_device"] == "cpu"


def test_new_project_page_build_request_default(qapp, tmp_path):
    settings = Settings()
    page = NewProjectPage(settings_provider=lambda: settings)

    dummy_video = tmp_path / "dummy_default.mp4"
    dummy_video.write_bytes(b"video content")
    page.step_video.set_file(str(dummy_video))

    req = page._build_request()
    assert req is not None
    assert req.mask_method == "blur"
    assert req.inpaint_engine == "lama_onnx"
    assert req.inpaint_device == "auto"


@patch("autodub.media.video.merge_video")
@patch("autodub.text.subtitles.refresh_subtitles", return_value=("", ""))
def test_pipeline_export_phase_defaults_boxblur(mock_refresh, mock_merge_video, tmp_path):
    settings = Settings()
    pipeline = DubPipeline(settings)

    # State from an older run without any mask keys
    state = {
        "segments": [],
        "tts_results": [],
        "merge_dir": str(tmp_path),
        "video_path": str(tmp_path / "video.mp4"),
        "merged_audio_path": str(tmp_path / "audio.wav"),
        "audio_path": str(tmp_path / "audio.wav"),
        "folder_name": "test_folder",
        "lang_code": "zh",
        "target": "vi",
        "subtitle_style": {},
        "deferred_speed": None,
    }

    target = MagicMock()
    target.key = "vi"
    target.iso639_2 = "vie"

    dummy_report = {
        "total_segments": 0,
        "total_original_duration": 0.0,
        "total_tts_duration": 0.0,
        "segments_speed_adjusted": 0,
        "session_id": "test_folder",
        "source_url": "",
    }
    with patch.object(pipeline, "_generate_content", return_value={}), \
         patch.object(pipeline, "_build_report", return_value=dummy_report), \
         patch.object(pipeline, "_build_timing_guide", return_value={}):
        pipeline._export_phase(state, str(tmp_path), target)

    mock_merge_video.assert_called_once()
    kwargs = mock_merge_video.call_args[1]
    assert kwargs["mask_method"] == "blur"
    assert kwargs["inpaint_engine"] == "lama_onnx"
    assert kwargs["inpaint_device"] == "auto"

