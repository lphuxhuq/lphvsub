"""Regression test: autodub core must be importable without PySide6/GUI.

Phase 2 fix: checkpoint_store.py used to import from autodub_gui.env_store,
which requires PySide6. Now it imports from autodub.env_io (core).
"""

import importlib


def test_headless_import_autodub():
    """``import autodub`` must not pull in PySide6."""
    # If PySide6 happens to be importable in the test env, we don't block it.
    # We only assert that autodub itself doesn't REQUIRE it.
    mod = importlib.import_module("autodub")
    assert hasattr(mod, "DubPipeline")
    assert hasattr(mod, "Settings")


def test_headless_import_checkpoint_store():
    """checkpoint_store must work without autodub_gui."""
    mod = importlib.import_module("autodub.checkpoint_store")
    assert hasattr(mod, "load_checkpoints")
    assert hasattr(mod, "bool_to_env")
    assert mod.bool_to_env(True) == "true"
    assert mod.bool_to_env(False) == "false"


def test_headless_import_env_io():
    """autodub.env_io must exist and export core env functions."""
    mod = importlib.import_module("autodub.env_io")
    assert hasattr(mod, "read_env")
    assert hasattr(mod, "write_env")
    assert hasattr(mod, "bool_to_env")
    assert hasattr(mod, "env_bool")
    assert mod.env_bool("true") is True
    assert mod.env_bool("false") is False


def test_checkpoint_store_no_gui_import():
    """Verify checkpoint_store does not import autodub_gui at module level."""
    import ast
    import inspect

    import autodub.checkpoint_store as cs

    source = inspect.getsource(cs)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in getattr(node, "names", [])]
            full = module + " " + " ".join(names)
            assert "autodub_gui" not in full, (
                f"checkpoint_store.py still imports from autodub_gui: {full}"
            )
