import pytest
from autodub.media.hardsub_detector import (
    HardsubRegion,
    FrameSample,
    TextCandidate,
)


def test_hardsub_region_valid():
    reg = HardsubRegion(
        x=0.15,
        y=0.82,
        width=0.70,
        height=0.10,
        start=2.0,
        end=5.5,
        confidence=0.92,
    )
    assert reg.x == 0.15
    assert reg.y == 0.82
    assert reg.width == 0.70
    assert reg.height == 0.10
    assert reg.start == 2.0
    assert reg.end == 5.5
    assert reg.confidence == 0.92

    # Chuyển đổi sang schema blur_regions của hệ thống
    blur_dict = reg.to_blur_region()
    assert blur_dict == {
        "x": 0.15,
        "y": 0.82,
        "w": 0.70,
        "h": 0.10,
        "t_start": 2.0,
        "t_end": 5.5,
    }


def test_hardsub_region_validation_rejections():
    with pytest.raises(ValueError):
        HardsubRegion(x=-0.1, y=0.5, width=0.5, height=0.1, start=0.0, end=1.0, confidence=0.8)

    with pytest.raises(ValueError):
        HardsubRegion(x=0.1, y=0.5, width=0.0, height=0.1, start=0.0, end=1.0, confidence=0.8)

    with pytest.raises(ValueError):
        HardsubRegion(x=0.1, y=0.5, width=0.5, height=0.1, start=0.0, end=1.0, confidence=1.5)

    with pytest.raises(ValueError):
        HardsubRegion(x=0.1, y=0.5, width=0.5, height=0.1, start=5.0, end=2.0, confidence=0.8)


def test_frame_sample_model():
    sample = FrameSample(timestamp=3.5, frame_index=7)
    assert sample.timestamp == 3.5
    assert sample.frame_index == 7


def test_text_candidate_model():
    cand = TextCandidate(
        x=100, y=300, w=400, h=35,
        edge_score=0.8,
        contrast_score=0.7,
        density_score=0.75,
        position_score=0.9,
    )
    assert cand.x == 100
    assert cand.confidence > 0.7
