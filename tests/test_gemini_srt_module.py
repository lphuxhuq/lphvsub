import os
import pytest

def test_gemini_srt_module_importable():
    from autodub.tools.gemini_srt_ui import create_app
    app = create_app()
    assert app is not None
    assert "gemini" in app.name or "autodub" in app.name

def test_gemini_srt_static_index_exists():
    from autodub.tools.gemini_srt_ui import get_static_folder
    static_dir = get_static_folder()
    assert os.path.isdir(static_dir)
    assert os.path.isfile(os.path.join(static_dir, "index.html"))
