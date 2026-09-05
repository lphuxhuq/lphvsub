import hashlib
import os
import struct
import tempfile
import pytest

from autodub.media.metadata import (
    calculate_file_hash,
    randomize_file_hash,
    build_clean_metadata_args,
)


def test_calculate_file_hash(tmp_path):
    test_file = tmp_path / "test.dat"
    content = b"Hello, Antigravity metadata test content!"
    test_file.write_bytes(content)

    expected_md5 = hashlib.md5(content).hexdigest()
    expected_sha256 = hashlib.sha256(content).hexdigest()

    assert calculate_file_hash(str(test_file), "md5") == expected_md5
    assert calculate_file_hash(str(test_file), "sha256") == expected_sha256


def test_randomize_file_hash_changes_hash_and_preserves_content(tmp_path):
    test_file = tmp_path / "video.mp4"
    orig_content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"
    test_file.write_bytes(orig_content)

    initial_md5 = calculate_file_hash(str(test_file), "md5")
    initial_sha256 = calculate_file_hash(str(test_file), "sha256")

    # Run randomize
    salt_len = 32
    new_md5 = randomize_file_hash(str(test_file), salt_length=salt_len)
    new_sha256 = calculate_file_hash(str(test_file), "sha256")

    # Hash MUST change
    assert new_md5 != initial_md5
    assert new_sha256 != initial_sha256

    # Original header must be perfectly intact
    data_after = test_file.read_bytes()
    assert data_after.startswith(orig_content)

    # File size should increase by exactly 8 (header) + salt_len bytes
    expected_box_size = 8 + salt_len
    assert len(data_after) == len(orig_content) + expected_box_size

    # The appended atom must be an ISO standard 'free' atom
    atom_size, atom_type = struct.unpack(">I4s", data_after[len(orig_content):len(orig_content) + 8])
    assert atom_size == expected_box_size
    assert atom_type == b"free"


def test_randomize_file_hash_multiple_runs_yield_distinct_hashes(tmp_path):
    test_file = tmp_path / "sample.mp4"
    test_file.write_bytes(b"some mp4 bytes")

    hashes = set()
    for _ in range(5):
        h = randomize_file_hash(str(test_file))
        assert h not in hashes, "Each randomization must produce a unique hash"
        hashes.add(h)


def test_build_clean_metadata_args():
    args = build_clean_metadata_args()
    assert "-map_metadata" in args
    idx = args.index("-map_metadata")
    assert args[idx + 1] == "-1"

    # Check creation_time, title, comment, handler_name
    joined = " ".join(args)
    assert "creation_time=" in joined
    assert "title=" in joined
    assert "comment=" in joined
    assert "handler_name=VideoHandler" in joined
    assert "handler_name=SoundHandler" in joined
