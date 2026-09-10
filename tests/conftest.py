"""Global pytest configuration for test isolation."""
import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_pipeline_cache(tmp_path, monkeypatch):
    """Isolate UPC pipeline cache directory to tmp_path for each test."""
    test_cache = tmp_path / "_test_upc_cache"
    monkeypatch.setenv("LPHVSub_PIPELINE_CACHE", str(test_cache))
    try:
        import autodub.pipeline_cache as pc
        old_root = pc._ROOT
        pc._ROOT = test_cache
        yield
        pc._ROOT = old_root
    except ImportError:
        yield
