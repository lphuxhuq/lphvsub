"""Unit tests cho GlobalModelPool và model_preloader."""
import threading
import time
from unittest import mock

import pytest

from autodub.config import Settings
from autodub.model_preloader import (
    GlobalModelPool,
    close_global_models,
    get_global_demucs_cache,
    get_global_lama_engine,
    get_global_model_pool,
    get_global_paraformer_cache,
    get_global_synth_cache,
    get_global_whisper_cache,
)


def test_global_model_pool_singleton():
    pool = get_global_model_pool()
    assert pool is not None
    assert get_global_paraformer_cache() is pool.get_paraformer_cache()
    assert get_global_whisper_cache() is pool.get_whisper_cache()
    assert get_global_demucs_cache() is pool.get_demucs_cache()
    assert get_global_synth_cache() is pool.get_synth_cache()
    assert get_global_lama_engine() is pool.get_lama_engine()


def test_preload_order_paraformer_first():
    """Đảm bảo Paraformer được nạp ĐẦU TIÊN (Step 1) trong quy trình preload."""
    pool = GlobalModelPool()
    settings = Settings()

    load_order = []

    mock_pf = mock.Mock()
    mock_pf._ensure.side_effect = lambda s: load_order.append("paraformer") or True

    mock_whisper = mock.Mock()
    mock_whisper.get.side_effect = lambda s: load_order.append("whisper") or mock.Mock()

    mock_demucs = mock.Mock()
    mock_demucs._ensure.side_effect = lambda: load_order.append("demucs") or True

    mock_synth = mock.Mock()
    mock_synth.get.side_effect = lambda t, s: load_order.append("vieneu") or mock.Mock()

    mock_lama = mock.Mock()
    mock_lama._ensure_session.side_effect = lambda: load_order.append("lama")

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock_whisper), \
         mock.patch.object(pool, "get_demucs_cache", return_value=mock_demucs), \
         mock.patch.object(pool, "get_synth_cache", return_value=mock_synth), \
         mock.patch.object(pool, "get_lama_engine", return_value=mock_lama), \
         mock.patch("autodub.model_preloader.os.path.isfile", return_value=True), \
         mock.patch("autodub.media.vocal_separator.gpu_venv_python", return_value="dummy_python"), \
         mock.patch.object(settings, "paraformer_configured", return_value=True), \
         mock.patch.object(settings, "vieneu_configured", return_value=True):

        steps = []
        done_event = threading.Event()
        final_res = {}

        def on_step(k, v):
            steps.append((k, v))

        def on_done(status):
            final_res.update(status)
            done_event.set()

        pool.preload_all_async(settings, on_step=on_step, on_done=on_done)
        assert done_event.wait(timeout=5.0)

        # Kiểm tra thứ tự nạp: Paraformer phải là model đầu tiên!
        assert len(load_order) == 5
        assert load_order[0] == "paraformer"
        assert load_order[1] == "whisper"
        assert load_order[2] == "demucs"
        assert load_order[3] == "vieneu"
        assert load_order[4] == "lama"

        assert final_res["paraformer"] == "ready"
        assert final_res["whisper"] == "ready"
        assert final_res["demucs"] == "ready"
        assert final_res["vieneu"] == "ready"
        assert final_res["lama"] == "ready"


def test_preload_error_isolation():
    """Nếu 1 model gặp lỗi, các model khác vẫn được nạp tiếp tục bình thường."""
    pool = GlobalModelPool()
    settings = Settings()

    mock_pf = mock.Mock()
    mock_pf._ensure.side_effect = RuntimeError("Paraformer crash")

    mock_whisper = mock.Mock()
    mock_whisper.get.return_value = mock.Mock()

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock_whisper), \
         mock.patch("autodub.media.vocal_separator.gpu_venv_python", return_value=""), \
         mock.patch("autodub.model_preloader.os.path.isfile", return_value=False), \
         mock.patch.object(settings, "paraformer_configured", return_value=True), \
         mock.patch.object(settings, "vieneu_configured", return_value=False):

        done_event = threading.Event()
        final_res = {}

        def on_done(status):
            final_res.update(status)
            done_event.set()

        pool.preload_all_async(settings, on_done=on_done)
        assert done_event.wait(timeout=5.0)

        assert final_res["paraformer"] == "failed"
        assert final_res["whisper"] == "ready"


def test_close_all_cleans_up():
    pool = GlobalModelPool()
    mock_pf = mock.Mock()
    mock_whisper = mock.Mock()
    mock_demucs = mock.Mock()
    mock_synth = mock.Mock()

    pool._paraformer_cache = mock_pf
    pool._whisper_cache = mock_whisper
    pool._demucs_cache = mock_demucs
    pool._synth_cache = mock_synth
    pool._status["whisper"] = "ready"

    pool.close_all()

    mock_pf.close.assert_called_once()
    mock_whisper.close.assert_called_once()
    mock_demucs.close.assert_called_once()
    mock_synth.close.assert_called_once()
    assert pool._status["whisper"] == "idle"
    assert pool._paraformer_cache is None
