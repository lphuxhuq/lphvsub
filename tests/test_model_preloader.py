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


def test_preload_models_order():
    """Đảm bảo nạp trước Paraformer (ĐẦU TIÊN), sau đó đến Whisper và Demucs."""
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
    mock_lama = mock.Mock()

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock_whisper), \
         mock.patch.object(pool, "get_demucs_cache", return_value=mock_demucs), \
         mock.patch.object(pool, "get_synth_cache", return_value=mock_synth), \
         mock.patch.object(pool, "get_lama_engine", return_value=mock_lama), \
         mock.patch("autodub.media.vocal_separator.gpu_venv_python", return_value="dummy_python"), \
         mock.patch.object(settings, "paraformer_configured", return_value=True):

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

        # Kiểm tra thứ tự nạp: Paraformer đầu tiên, tiếp theo là Whisper và Demucs
        assert len(load_order) == 3
        assert load_order[0] == "paraformer"
        assert load_order[1] == "whisper"
        assert load_order[2] == "demucs"

        assert final_res["paraformer"] == "ready"
        assert final_res["whisper"] == "ready"
        assert final_res["demucs"] == "ready"
        assert final_res["vieneu"] == "idle"
        assert final_res["lama"] == "idle"

        # Các model khác không bị gọi preload
        mock_synth.get.assert_not_called()
        mock_lama._ensure_session.assert_not_called()


def test_preload_error_isolation():
    """Nếu 1 model gặp lỗi, các model còn lại vẫn được nạp bình thường."""
    pool = GlobalModelPool()
    settings = Settings()

    mock_pf = mock.Mock()
    mock_pf._ensure.side_effect = RuntimeError("Paraformer crash")

    mock_whisper = mock.Mock()
    mock_whisper.get.return_value = mock.Mock()

    mock_demucs = mock.Mock()
    mock_demucs._ensure.return_value = True

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock_whisper), \
         mock.patch.object(pool, "get_demucs_cache", return_value=mock_demucs), \
         mock.patch("autodub.media.vocal_separator.gpu_venv_python", return_value="dummy_python"), \
         mock.patch.object(settings, "paraformer_configured", return_value=True):

        done_event = threading.Event()
        final_res = {}

        def on_done(status):
            final_res.update(status)
            done_event.set()

        pool.preload_all_async(settings, on_done=on_done)
        assert done_event.wait(timeout=5.0)

        assert final_res["paraformer"] == "failed"
        assert final_res["whisper"] == "ready"
        assert final_res["demucs"] == "ready"


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


def test_get_global_align_model():
    """Kiểm tra get_align_model trả về singleton và duy trì 1 model duy nhất."""
    from autodub.model_preloader import get_global_align_model
    from autodub.speech.align import unload_align_model

    pool = GlobalModelPool()
    dummy_model = mock.Mock()

    try:
        with mock.patch("autodub.speech.align._create_whisper_align_model", return_value=(dummy_model, "cpu", 2)):
            m1, dev1, w1 = pool.get_align_model()
            m2, dev2, w2 = pool.get_align_model()

            assert m1 is m2
            assert m1 is dummy_model
            assert dev1 == "cpu"
            assert w1 == 2

        # Global function cũng lấy từ pool
        with mock.patch("autodub.speech.align._create_whisper_align_model", return_value=(dummy_model, "cpu", 2)):
            gm1, _, _ = get_global_align_model()
            gm2, _, _ = get_global_align_model()
            assert gm1 is gm2
    finally:
        unload_align_model()


def test_model_preloader_qt_signals_safe(qtbot):
    """Xác nhận callback nạp model qua Qt Signals được dispatch về đúng Main Thread an toàn."""
    import threading
    from PySide6.QtCore import QObject, Signal

    class Receiver(QObject):
        step_signal = Signal(str, str)
        done_signal = Signal(dict)

        def __init__(self):
            super().__init__()
            self.step_thread_id = None
            self.done_thread_id = None
            self.step_signal.connect(self.on_step)
            self.done_signal.connect(self.on_done)

        def on_step(self, k, v):
            self.step_thread_id = threading.get_ident()

        def on_done(self, s):
            self.done_thread_id = threading.get_ident()

    rcv = Receiver()
    main_id = threading.get_ident()

    # Giả lập worker thread emit signals
    def worker():
        rcv.step_signal.emit("whisper", "ready")
        rcv.done_signal.emit({"whisper": "ready"})

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    # Chờ Qt xử lý queued event loop
    qtbot.wait(100)

    # Cả hai slot phải được thực thi trên main GUI thread
    assert rcv.step_thread_id == main_id
    assert rcv.done_thread_id == main_id


def test_preload_concurrent_calls_ignored():
    """Gọi preload_all_async khi đang nạp thì lần thứ hai bị bỏ qua."""
    pool = GlobalModelPool()
    settings = Settings()

    gate = threading.Event()
    worker_started = threading.Event()
    load_count = 0

    def mock_pf_ensure(s):
        nonlocal load_count
        load_count += 1
        worker_started.set()
        gate.wait(timeout=2.0)
        return True

    mock_pf = mock.Mock()
    mock_pf._ensure.side_effect = mock_pf_ensure

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock.Mock()), \
         mock.patch.object(pool, "get_demucs_cache", return_value=mock.Mock()), \
         mock.patch.object(settings, "paraformer_configured", return_value=True):

        # Lần 1
        pool.preload_all_async(settings)
        assert worker_started.wait(timeout=2.0)

        # Lần 2 (khi lần 1 đang chạy dở)
        pool.preload_all_async(settings)

        gate.set()
        if pool._preload_thread:
            pool._preload_thread.join(timeout=2.0)

        # Chỉ có 1 lần worker thực sự chạy
        assert load_count == 1


def test_preload_early_cancellation():
    """close_all() trong lúc preload_all_async đang chạy phải hủy ngang sạch sẽ."""
    pool = GlobalModelPool()
    settings = Settings()

    pf_started = threading.Event()
    can_proceed = threading.Event()

    def mock_pf_ensure(s):
        pf_started.set()
        can_proceed.wait(timeout=2.0)
        return True

    mock_pf = mock.Mock()
    mock_pf._ensure.side_effect = mock_pf_ensure
    mock_whisper = mock.Mock()

    with mock.patch.object(pool, "get_paraformer_cache", return_value=mock_pf), \
         mock.patch.object(pool, "get_whisper_cache", return_value=mock_whisper), \
         mock.patch.object(settings, "paraformer_configured", return_value=True):

        pool.preload_all_async(settings)
        assert pf_started.wait(timeout=2.0)

        # Gọi close_all() ngay khi bước 1 đang chạy
        pool.close_all()
        can_proceed.set()

        if pool._preload_thread:
            pool._preload_thread.join(timeout=2.0)

        # Whisper không được phép gọi sau khi đã bị cancel
        mock_whisper.get.assert_not_called()
        # Status sau close_all phải là idle
        assert pool.status()["whisper"] == "idle"


def test_whisper_cache_thread_safety():
    """Nhiều luồng gọi WhisperCache.get đồng thời chỉ nạp model đúng 1 lần."""
    from autodub.speech.transcriber import WhisperCache

    cache = WhisperCache()
    settings = Settings()
    load_calls = 0
    dummy_model = mock.Mock()

    def fake_load(key, s):
        nonlocal load_calls
        time.sleep(0.01)
        load_calls += 1
        return dummy_model, "cpu"

    with mock.patch("autodub.speech.transcriber._load_whisper_model", side_effect=fake_load):
        threads = []
        results = [None] * 5

        def worker(idx):
            results[idx] = cache.get(settings)

        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=3.0)

        assert load_calls == 1
        for res in results:
            assert res is dummy_model


def test_synth_cache_thread_safety():
    """Nhiều luồng gọi SynthCache.get đồng thời cùng voice chỉ tạo 1 synthesizer."""
    from autodub.speech.tts import SynthCache

    cache = SynthCache()
    settings = Settings()
    from autodub.languages import get_target
    target = get_target("vi")

    create_calls = 0
    dummy_synth = mock.Mock()

    def fake_get_synth(t, s, v):
        nonlocal create_calls
        time.sleep(0.01)
        create_calls += 1
        return dummy_synth

    with mock.patch("autodub.speech.tts.get_synthesizer", side_effect=fake_get_synth), \
         mock.patch("autodub.speech.tts.voice_catalog.resolve", return_value="test_voice"):

        threads = []
        results = [None] * 5

        def worker(idx):
            results[idx] = cache.get(target, settings, "test_voice")

        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=3.0)

        assert create_calls == 1
        for res in results:
            assert res is dummy_synth



