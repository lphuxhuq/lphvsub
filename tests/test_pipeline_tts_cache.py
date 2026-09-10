import os
from unittest import mock
from pathlib import Path
import pytest

from autodub.config import Settings
from autodub.languages import get_target
from autodub.pipeline import DubPipeline
import autodub.pipeline_cache as pc


def _create_wav(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"RIFF\x24\x01\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x01\x00\x00" + b"\x00" * 256)


class DummySynthResult:
    def __init__(self, path):
        self.path = path

    def to_dict(self):
        return {
            "path": self.path,
            "actual_duration": 1.25,
            "speed_adjusted": False,
            "rate_applied": "normal",
        }


class DummySynth:
    def __init__(self):
        self.call_count = 0
        self.recommended_threads = 1

    def synthesize(self, text, output_path, target_duration=None):
        self.call_count += 1
        _create_wav(output_path)
        return DummySynthResult(output_path)


def test_pipeline_tts_global_cache_integration(tmp_path):
    proj1_seg_dir = str(tmp_path / "proj1" / "data" / "segments")
    proj2_seg_dir = str(tmp_path / "proj2" / "data" / "segments")
    os.makedirs(proj1_seg_dir, exist_ok=True)
    os.makedirs(proj2_seg_dir, exist_ok=True)

    segments = [
        {"id": 1, "text_vi": "Xin chào thế giới", "speaker_id": 0},
        {"id": 2, "text_vi": "Hôm nay thời tiết đẹp", "speaker_id": 0},
    ]

    target = get_target("vi")
    settings = Settings()
    pipeline = DubPipeline(settings)

    dummy_synth = DummySynth()

    # 1. First run: cold synthesis -> calls synth.synthesize
    res1 = pipeline._synthesize_segments(
        target=target,
        voice="nam_bac_1",
        segments=segments,
        seg_dir=proj1_seg_dir,
        synth=dummy_synth,
    )
    assert len(res1) == 2
    assert dummy_synth.call_count == 2
    assert os.path.exists(res1[0]["path"])

    # 2. Second run: brand new project segment directory with same texts and voice
    # -> Must hit UPC TTS cache without calling synth.synthesize!
    dummy_synth.call_count = 0
    res2 = pipeline._synthesize_segments(
        target=target,
        voice="nam_bac_1",
        segments=segments,
        seg_dir=proj2_seg_dir,
        synth=dummy_synth,
    )
    assert len(res2) == 2
    assert dummy_synth.call_count == 0, "TTS synth must NOT be called on UPC cache hit"
    assert os.path.exists(res2[0]["path"])
    from autodub.utils import seg_wav_path
    assert res2[0]["path"] == seg_wav_path(proj2_seg_dir, 1)
    assert res2[1]["path"] == seg_wav_path(proj2_seg_dir, 2)
