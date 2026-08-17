# CapCut Voices Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate full 24 Vietnamese CapCut voices from `DouyinVietsubTool` into `lphvsub-main`, with robust catalog lookup, audio speed control, and high-quality WAV output.

**Architecture:** Update static catalog `Voice.json` in `capcut_api`, refine name matching & fallback logic in `capcut_catalog.py`, and expand unit test coverage across TTS modules.

**Tech Stack:** Python 3.11, JSON, PyTest, FFmpeg.

## Global Constraints

- Static catalog reading only — no network calls during catalog loading.
- 100% test pass rate with `python -m pytest tests/test_capcut_tts.py tests/test_voices.py`.
- Preserves standard display name formatting (`Name - Description`).

---

### Task 1: Update `Voice.json` Catalog Data

**Files:**
- Modify: `autodub/speech/tts/capcut_api/Voice.json`
- Test: `tests/test_capcut_tts.py`

**Interfaces:**
- Consumes: Catalog JSON file from `D:\DouyinVietsubTool\vendor\capcut_tts_api\Voice.json`.
- Produces: Updated `Voice.json` with 129 entries (24 Vietnamese voices).

- [ ] **Step 1: Write failing test for new Vietnamese voices (`vi-VN-HoaiMyNeural` and `vi-VN-NamMinhNeural`)**

Add test function in `tests/test_capcut_tts.py`:
```python
def test_capcut_catalog_contains_all_24_vietnamese_voices():
    from autodub.speech.tts import capcut_catalog
    vi_entries = [e for e in capcut_catalog.entries() if e["gender"] in ("female", "male")]
    names = {e["name"] for e in capcut_catalog.entries()}
    assert "Hoài Mỹ" in names
    assert "Nam Minh" in names
    assert len(capcut_catalog.entries()) == 129
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capcut_tts.py::test_capcut_catalog_contains_all_24_vietnamese_voices -v`  
Expected: FAIL (Hoài Mỹ and Nam Minh missing, catalog length != 129)

- [ ] **Step 3: Update `Voice.json` with 129 entries and standardized names**

Port all 129 entries into `autodub/speech/tts/capcut_api/Voice.json` with:
- `vi-VN-HoaiMyNeural` -> `"Hoài Mỹ - Nữ truyền cảm"`
- `vi-VN-NamMinhNeural` -> `"Nam Minh - Nam truyền cảm"`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capcut_tts.py::test_capcut_catalog_contains_all_24_vietnamese_voices -v`  
Expected: PASS

---

### Task 2: Enhance Catalog Lookup in `capcut_catalog.py`

**Files:**
- Modify: `autodub/speech/tts/capcut_catalog.py`
- Test: `tests/test_capcut_tts.py`

**Interfaces:**
- Consumes: Voice name string (short name, full display name, or voice_type).
- Produces: Voice catalog dict `{"name", "description", "gender", "voice_type", "resource_id"}` or `None`.

- [ ] **Step 1: Write failing test for flexible lookup**

Add test function in `tests/test_capcut_tts.py`:
```python
def test_capcut_catalog_lookup_flexible_matching():
    from autodub.speech.tts import capcut_catalog
    assert capcut_catalog.lookup("Hoài Mỹ")["voice_type"] == "vi-VN-HoaiMyNeural"
    assert capcut_catalog.lookup("Nam Minh")["voice_type"] == "vi-VN-NamMinhNeural"
    assert capcut_catalog.lookup("vi-VN-HoaiMyNeural")["name"] == "Hoài Mỹ"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capcut_tts.py::test_capcut_catalog_lookup_flexible_matching -v`  
Expected: FAIL (Lookup by voice_type or name alias returns None)

- [ ] **Step 3: Update `capcut_catalog.lookup()` implementation**

Modify `autodub/speech/tts/capcut_catalog.py`:
```python
def lookup(name: str) -> dict | None:
    """Mục catalog của một tên giọng, tên đầy đủ, hoặc voice_type."""
    clean = (name or "").strip()
    if not clean:
        return None
    for entry in entries():
        if entry["name"] == clean or entry["voice_type"] == clean or f"{entry['name']} - {entry['description']}" == clean:
            return entry
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capcut_tts.py::test_capcut_catalog_lookup_flexible_matching -v`  
Expected: PASS

---

### Task 3: Comprehensive Test Suite Verification

**Files:**
- Modify: `tests/test_capcut_tts.py`, `tests/test_voices.py`

- [ ] **Step 1: Run full test suite for CapCut TTS and voices catalog**

Run: `python -m pytest tests/test_capcut_tts.py tests/test_voices.py -v`  
Expected: All 43+ tests PASS with 0 failures.
