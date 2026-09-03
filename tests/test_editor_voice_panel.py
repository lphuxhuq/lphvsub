import pytest
from PySide6.QtWidgets import QApplication

from autodub_gui.pages.editor_panels import VoicePanel


def test_voice_panel_speaker_director(qtbot):
    panel = VoicePanel()
    qtbot.addWidget(panel)
    panel.show()

    segments = [
        {"id": 1, "speaker_id": 0, "text": "Câu 1"},
        {"id": 2, "speaker_id": 0, "text": "Câu 2"},
        {"id": 3, "speaker_id": 1, "text": "Câu 3"},
    ]
    speaker_voices = {0: "nam_bac_1", 1: "nu_bac_1"}
    speaker_profiles = {
        0: {"gender": "male", "role": "narrator"},
        1: {"gender": "female", "role": "character"},
    }

    panel.set_speakers(segments, speaker_voices, speaker_profiles)

    assert panel.cb_auto_director.isVisible() is True
    assert panel.speakers_container.isVisible() is True
    assert len(panel._speaker_pickers) == 2

    vals = panel.values()
    assert "auto_voice_director_enabled" in vals
    assert vals["auto_voice_director_enabled"] is True
    assert vals["speaker_voices"][0] == "nam_bac_1"
    assert vals["speaker_voices"][1] == "nu_bac_1"

    # Toggle OFF
    panel.cb_auto_director.setChecked(False)
    assert panel.speakers_container.isVisible() is False
    assert panel.values()["auto_voice_director_enabled"] is False
