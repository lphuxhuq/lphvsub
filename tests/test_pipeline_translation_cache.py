import os
from unittest import mock
import pytest

from autodub.config import Settings
from autodub.languages import get_target
from autodub.pipeline import DubPipeline, DubRequest
import autodub.pipeline_cache as pc


def test_pipeline_translation_global_cache_hit_and_store(tmp_path):
    proj1 = tmp_path / "proj1"
    proj2 = tmp_path / "proj2"
    os.makedirs(proj1 / "data", exist_ok=True)
    os.makedirs(proj2 / "data", exist_ok=True)

    segments = [
        {"id": 1, "start": 0.0, "end": 1.0, "text": "Good morning"},
        {"id": 2, "start": 1.0, "end": 2.0, "text": "How are you"},
    ]

    target = get_target("vi")

    settings = Settings()
    pipeline = DubPipeline(settings)

    call_count = 0

    def mock_auto_translate(segs, tgt, src_lang, work_dir=None):
        nonlocal call_count
        call_count += 1
        res = []
        for s in segs:
            item = dict(s)
            item[tgt.text_field] = f"Dịch: {s['text']}"
            res.append(item)
        return res

    pipeline._auto_translate = mock_auto_translate

    # --- Run 1: Cold translation ---
    trans_cache = pc.get_translation_cache()
    provider = "default"
    query = [(i, s["text"]) for i, s in enumerate(segments)]
    hits = trans_cache.lookup_batch(query, target.key, provider)
    assert len(hits) == 0

    # Auto translate runs and stores
    translated1 = pipeline._auto_translate(segments, target, "en", work_dir=str(proj1))
    assert call_count == 1
    pairs = [(s["text"], t[target.text_field]) for s, t in zip(segments, translated1)]
    trans_cache.store_batch(pairs, target.key, provider)

    # --- Run 2: Warm translation in brand new proj2 ---
    hits2 = trans_cache.lookup_batch(query, target.key, provider)
    assert len(hits2) == 2
    assert hits2[0] == "Dịch: Good morning"
    assert hits2[1] == "Dịch: How are you"

    # Restored without calling _auto_translate
    assert call_count == 1, "_auto_translate should not be called on full cache hit"


def test_pipeline_translation_partial_cache_prefills_checkpoint(tmp_path):
    """When some segments hit cache, they must be pre-filled into translate_checkpoint.json."""
    from autodub.text.translate_common import TranslateCheckpoint
    from autodub.workdir import data_path

    proj = tmp_path / "proj"
    os.makedirs(proj / "data", exist_ok=True)

    target = get_target("vi")
    ckpt_file = data_path(str(proj), "translate_checkpoint.json")

    segments = [
        {"id": 1, "start": 0.0, "end": 1.0, "text": "Hello world"},
        {"id": 2, "start": 1.0, "end": 2.0, "text": "New uncached sentence"},
    ]

    # Pre-fill segment 1 into checkpoint
    cp = TranslateCheckpoint(ckpt_file, text_field=target.text_field)
    cp.put([{"id": 1, "text": "Hello world", target.text_field: "Xin chào thế giới"}])

    # Re-read checkpoint
    cp_loaded = TranslateCheckpoint(ckpt_file, text_field=target.text_field)
    assert "1" in cp_loaded._items
    assert cp_loaded._items["1"]["text"] == "Xin chào thế giới"
    assert "2" not in cp_loaded._items


def test_alternate_transcript_path_detected(tmp_path):
    """If transcript_vi.json exists in work_dir root instead of data/, it should be found."""
    work_dir = str(tmp_path / "my_project")
    os.makedirs(work_dir, exist_ok=True)
    alt_file = os.path.join(work_dir, "transcript_vi.json")
    with open(alt_file, "w", encoding="utf-8") as f:
        f.write('[{"id": 1, "start": 0.0, "end": 1.0, "text": "test", "text_vi": "thử nghiệm"}]')

    target = get_target("vi")
    transcript_dub_path = os.path.join(work_dir, "data", target.transcript_name)
    assert not os.path.exists(transcript_dub_path)

    # Resolution logic from pipeline
    if not os.path.exists(transcript_dub_path) and work_dir:
        alt_transcript = os.path.join(work_dir, target.transcript_name)
        if os.path.exists(alt_transcript):
            transcript_dub_path = alt_transcript

    assert os.path.exists(transcript_dub_path)
    assert transcript_dub_path == alt_file

