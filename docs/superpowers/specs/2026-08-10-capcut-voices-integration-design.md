# Design Spec: CapCut Voices Integration

**Date**: 2026-08-10  
**Status**: Approved  
**Topic**: CapCut Voices Catalog Update & Audio Quality & Speed Control (24 Vietnamese Voices)

---

## 1. Overview & Goals

The goal of this change is to update the CapCut voice catalog in `lphvsub-main` by porting all CapCut voices from `DouyinVietsubTool` (`D:\DouyinVietsubTool`), while ensuring full support for audio speed control (rate) and high-quality audio output synthesis.

This expands the Vietnamese voice choices from 22 to 24 voices (adding `vi-VN-HoaiMyNeural` and `vi-VN-NamMinhNeural`), while maintaining complete backward compatibility, robust catalog lookup, and standardized voice metadata.

---

## 2. Catalog Changes (`Voice.json`)

- **Location**: `autodub/speech/tts/capcut_api/Voice.json`
- **Total entries**: 129 entries (up from 127 entries).
- **Vietnamese entries**: 24 entries (`vi-VN`).
- **Formatting**: Standardize `display_name` to follow `"Name - Description"` format:
  - `vi-VN-HoaiMyNeural` -> `"Hoài Mỹ - Nữ truyền cảm"`
  - `vi-VN-NamMinhNeural` -> `"Nam Minh - Nam truyền cảm"`
  - Preserves standard display names for all existing 22 Vietnamese voices.

---

## 3. Audio Speed & Output Quality Controls

- **Speech Speed Control (Rate)**:
  - Pass the speech rate parameter (`rate`, default `1.0`, supports flexible adjustment e.g. `0.5` to `2.0`) in the SSML `<prosody rate="{rate}">` block during CapCut API requests.
- **Audio Output Quality**:
  - Receive high-bitrate MP3 audio from CapCut servers.
  - Automatically convert MP3 to **44.1 kHz, 16-bit Mono PCM WAV** via `ffmpeg` to guarantee lossless compatibility with the audio dubbing pipeline and video rendering stages.

---

## 4. Catalog Traversal & Robust Lookup (`capcut_catalog.py`)

- **Robust Lookup**: Ensure `lookup(name)` in `autodub/speech/tts/capcut_catalog.py` matches by:
  1. Extracted short name (e.g. `"Hoài Mỹ"`, `"Thanh Lan"`, `"Minh Trang"`).
  2. Full display name (e.g. `"Hoài Mỹ - Nữ truyền cảm"`).
  3. Raw `voice_type` identifier (e.g. `"vi-VN-HoaiMyNeural"`).
- **Default Voice**: Ensure `DEFAULT_CAPCUT_VOICE = "Minh Trang"` remains intact and resolvable.

---

## 5. Verification & Testing

- **Unit Tests**:
  - `tests/test_capcut_tts.py`: Add test assertions for `vi-VN-HoaiMyNeural` and `vi-VN-NamMinhNeural` lookups and catalog entries.
  - `tests/test_voices.py`: Ensure catalog resolution, audio rate parameter, and filter logic correctly process all 24 Vietnamese CapCut voices.
- **Automated Command**:
  - Run `python -m pytest tests/test_capcut_tts.py tests/test_voices.py` and confirm 100% pass rate.

---

## 6. Security & Isolation

- All voice catalog reads remain offline static JSON parsing without network calls.
- Device profile rotation and security token handling remain unchanged.
