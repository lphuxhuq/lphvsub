"""Tests for PartialDownloadManager and HTTP Range resume functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from autodub.media.download.partial_manager import (
    DownloadProgressState,
    PartialDownloadManager,
)


@pytest.fixture
def manager():
    return PartialDownloadManager(buffer_size=128)


def test_progress_state_persistence(manager, tmp_path):
    target = tmp_path / "video.mp4"
    state = DownloadProgressState(
        url="https://cdn.example.com/video.mp4",
        target_path=str(target),
        part_path=str(tmp_path / "video.mp4.part"),
        total_bytes=1000,
        downloaded_bytes=500,
    )
    manager.save_state(state)

    loaded = manager.load_state(target)
    assert loaded is not None
    assert loaded.url == "https://cdn.example.com/video.mp4"
    assert loaded.downloaded_bytes == 500
    assert loaded.total_bytes == 1000


def test_download_progressive_from_scratch(manager, tmp_path):
    target = tmp_path / "scratch.mp4"
    payload = b"X" * 1024

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": "1024"}
    mock_resp.iter_content.return_value = [payload[:512], payload[512:]]

    session = MagicMock()
    session.get.return_value = mock_resp

    res_path = manager.download_progressive_stream(
        url="https://example.com/test.mp4",
        target_path=target,
        session=session,
    )
    assert res_path.exists()
    assert res_path.read_bytes() == payload
    # Artifacts should be cleaned up
    assert not manager.get_part_path(target).exists()
    assert not manager.get_progress_meta_path(target).exists()


def test_download_progressive_resume_206(manager, tmp_path):
    target = tmp_path / "resumable.mp4"
    part_file = manager.get_part_path(target)
    initial_bytes = b"FIRST_HALF_"
    part_file.write_bytes(initial_bytes)

    second_half = b"SECOND_HALF"
    total_len = len(initial_bytes) + len(second_half)

    mock_resp = MagicMock()
    mock_resp.status_code = 206
    mock_resp.headers = {
        "Content-Range": f"bytes {len(initial_bytes)}-{total_len - 1}/{total_len}",
        "Content-Length": str(len(second_half)),
    }
    mock_resp.iter_content.return_value = [second_half]

    session = MagicMock()
    session.get.return_value = mock_resp

    res_path = manager.download_progressive_stream(
        url="https://example.com/resume.mp4",
        target_path=target,
        session=session,
    )
    assert res_path.exists()
    assert res_path.read_bytes() == initial_bytes + second_half

    # Verify session.get was called with Range header
    called_headers = session.get.call_args[1]["headers"]
    assert called_headers["Range"] == f"bytes={len(initial_bytes)}-"


def test_partial_files_preserved_on_network_failure(manager, tmp_path):
    target = tmp_path / "flaky.mp4"
    part_file = manager.get_part_path(target)

    def failing_iter(*args, **kwargs):
        yield b"CHUNK_ONE_"
        raise requests.exceptions.ConnectionError("Connection lost mid-transfer")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": "2000"}
    mock_resp.iter_content = failing_iter

    session = MagicMock()
    session.get.return_value = mock_resp

    with pytest.raises(requests.exceptions.ConnectionError):
        manager.download_progressive_stream(
            url="https://example.com/flaky.mp4",
            target_path=target,
            session=session,
        )

    # Partial file MUST be preserved!
    assert part_file.exists()
    assert part_file.read_bytes() == b"CHUNK_ONE_"
    # Progress metadata MUST be preserved!
    assert manager.get_progress_meta_path(target).exists()


def test_download_cancellation_preserves_partial(manager, tmp_path):
    target = tmp_path / "cancelled.mp4"
    part_file = manager.get_part_path(target)

    cancelled = False

    def content_gen():
        nonlocal cancelled
        yield b"DATA1"
        cancelled = True
        yield b"DATA2"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": "100"}
    mock_resp.iter_content.return_value = content_gen()

    session = MagicMock()
    session.get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="cancelled"):
        manager.download_progressive_stream(
            url="https://example.com/cancel.mp4",
            target_path=target,
            session=session,
            is_cancelled=lambda: cancelled,
        )

    assert part_file.exists()
