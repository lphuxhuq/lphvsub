from autodub.media.encoder_profile import EncoderProfile, QualityMode


def test_encoder_profile_nvenc():
    fast = EncoderProfile.get_args("NVIDIA NVENC", QualityMode.FAST)
    assert "-preset" in fast and "p1" in fast
    assert "-cq" in fast and "23" in fast

    bal = EncoderProfile.get_args("NVIDIA NVENC", QualityMode.BALANCED)
    assert "-preset" in bal and "p2" in bal
    assert "-cq" in bal and "22" in bal

    qual = EncoderProfile.get_args("NVIDIA NVENC", QualityMode.QUALITY)
    assert "-preset" in qual and "p4" in qual
    assert "-cq" in qual and "20" in qual


def test_encoder_profile_cpu():
    fast = EncoderProfile.get_args("CPU (libx264)", QualityMode.FAST)
    assert "-preset" in fast and "ultrafast" in fast
    assert "-crf" in fast and "23" in fast
