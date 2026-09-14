"""Shared pytest fixtures.

B-13 / QI-10-05: ``isolate_apptest_globals`` promoted from
``tests/test_assistant_page_render.py`` so every AppTest module shares one
``sys.modules["__main__"]`` + ``sys.path`` restore (QI-10 §3.6 rule 3).
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def isolate_apptest_globals():
    """Undo Streamlit script-runner mutation of ``__main__`` and ``sys.path``.

    AppTest installs the page as ``sys.modules["__main__"]`` and puts the
    page directory on ``sys.path``. Left in place, a later ``spawn``-context
    ``run_batch`` pool re-imports that page as its main module and dies.
    Autouse keeps the suite order-safe; per-run restore in helpers is
    defence in depth.
    """
    main_module = sys.modules.get("__main__")
    path_snapshot = list(sys.path)
    try:
        yield
    finally:
        if main_module is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = main_module
        sys.path[:] = path_snapshot
