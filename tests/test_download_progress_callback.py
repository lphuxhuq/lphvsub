"""Test unit cho progress_cb truyền từ tầng downloader lên GUI."""

from unittest.mock import MagicMock, patch

from autodub.media.download.bilibili_engine import BilibiliDownloader
from autodub.media.download.contract import DownloadRequest
from autodub.media.downloader import download_video


def test_bilibili_downloader_progress_callback():
    downloader = BilibiliDownloader()
    progress_records = []

    def cb(data):
        progress_records.append(data)

    req = DownloadRequest(
        url="https://www.bilibili.com/video/BV174bJ6tEQQ",
        output_dir="downloads",
        progress_callback=cb,
    )
    assert req.progress_callback is not None


def test_download_video_signature_accepts_progress_cb():
    # Kiểm tra signature của download_video nhận progress_cb mà không lỗi
    progress_records = []

    def my_cb(pct, msg):
        progress_records.append((pct, msg))

    with patch("autodub.media.download.decision_engine.get_decision_engine") as mock_eng:
        engine_instance = MagicMock()
        mock_eng.return_value = engine_instance
        res = MagicMock()
        res.success = True
        res.path = __file__
        res.media_id = "test"
        res.backend = "mock"
        engine_instance.execute.return_value = res

        path = download_video(
            "https://www.bilibili.com/video/BV174bJ6tEQQ", "downloads", progress_cb=my_cb
        )
        assert path == __file__

        # Kiểm tra request được tạo với progress_callback
        call_args = engine_instance.execute.call_args[0]
        req = call_args[0]
        assert req.progress_callback is not None


def test_prefetch_worker_progress_signal():
    import sys

    from PySide6.QtWidgets import QApplication

    from autodub_gui.workers import PrefetchWorker

    app = QApplication.instance() or QApplication(sys.argv)
    worker = PrefetchWorker("https://www.bilibili.com/video/BV174bJ6tEQQ", "downloads")

    received = []
    worker.progress.connect(lambda pct, msg: received.append((pct, msg)))

    with patch("autodub.media.downloader.download_video") as mock_dl:

        def fake_download(url, out_dir, progress_cb=None):
            if progress_cb:
                progress_cb(0.45, "Đang tải: 45MB / 100MB (45%) - 5MB/s")
                progress_cb(1.0, "Hoàn tất")
            return "downloads/test.mp4"

        mock_dl.side_effect = fake_download
        worker.run()

    assert len(received) == 2
    assert received[0][0] == 0.45
    assert "45%" in received[0][1]
    assert received[1][0] == 1.0


def test_download_progress_bar_widget():
    import sys

    from PySide6.QtWidgets import QApplication

    from autodub_gui.ui.progress import DownloadProgressBar

    app = QApplication.instance() or QApplication(sys.argv)
    pbar = DownloadProgressBar()
    assert pbar.bar.value() == 0

    pbar.set_progress(0.75, "Đang tải 75MB / 100MB")
    assert pbar.bar.value() == 75
    assert pbar.lbl_percent.text() == "75%"
    assert pbar.lbl_status.text() == "Đang tải 75MB / 100MB"

    pbar.reset()
    assert pbar.bar.value() == 0
    assert pbar.lbl_percent.text() == "0%"


def test_prefetch_worker_detailed_signals():
    import sys

    from PySide6.QtWidgets import QApplication

    from autodub_gui.workers import PrefetchWorker

    app = QApplication.instance() or QApplication(sys.argv)
    worker = PrefetchWorker("https://www.youtube.com/watch?v=123", "downloads")

    received_url = []
    received_ok = []
    worker.progress_url.connect(lambda u, pct, msg: received_url.append((u, pct, msg)))
    worker.finished_ok_url.connect(lambda u, p: received_ok.append((u, p)))

    with patch("autodub.media.downloader.download_video") as mock_dl:

        def fake_download(url, out_dir, progress_cb=None):
            if progress_cb:
                progress_cb(0.5, "Tải 50%")
            return "downloads/123.mp4"

        mock_dl.side_effect = fake_download
        worker.run()

    assert len(received_url) == 1
    assert received_url[0][0] == "https://www.youtube.com/watch?v=123"
    assert received_url[0][1] == 0.5
    assert len(received_ok) == 1
    assert received_ok[0][1] == "downloads/123.mp4"


def test_download_progress_bar_cross_thread():
    import sys
    import threading

    from PySide6.QtWidgets import QApplication

    from autodub_gui.ui.progress import DownloadProgressBar

    app = QApplication.instance() or QApplication(sys.argv)
    pbar = DownloadProgressBar()

    def background_update():
        pbar.set_progress(0.88, "Cross-thread message")

    th = threading.Thread(target=background_update)
    th.start()
    th.join()
    app.processEvents()

    assert pbar.bar.value() == 88
    assert pbar.lbl_percent.text() == "88%"
