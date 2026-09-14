"""Shared pytest fixtures.

B-13 / QI-10-05: ``isolate_apptest_globals`` promoted from
``tests/test_assistant_page_render.py`` so every AppTest module shares one
``sys.modules["__main__"]`` + ``sys.path`` restore (QI-10 §3.6 rule 3).

B-15 / QI-11-05: warn-first class markers. Unmarked items become ``unit``;
``serial`` without a class (AppTest) becomes ``integration`` so ``-m unit``
stays off the Streamlit harness.
"""

from __future__ import annotations

import importlib
import sys

import pytest

# Session-start Streamlit (real package). Helper stubs replace
# ``sys.modules["streamlit"]`` without restore; AppTest.run then does
# ``import streamlit as st`` and dies on missing ``.secrets``.
_REAL_STREAMLIT = importlib.import_module("streamlit")

_CLASS_MARKERS = frozenset({"unit", "integration", "golden", "eval", "benchmark", "oracle"})


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Warn-first default class (B-15 / QI-11-05).

    Explicit class markers win. ``serial`` without a class is integration.
    Unmarked tests are not an error — they become unit. Required CI stays
    the full suite (no ``-m``).
    """
    for item in items:
        names = {marker.name for marker in item.iter_markers()}
        if names & _CLASS_MARKERS:
            continue
        if "serial" in names:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)


def _restore_real_streamlit() -> None:
    """Put the session-start Streamlit module back in ``sys.modules``."""
    sys.modules["streamlit"] = _REAL_STREAMLIT


@pytest.fixture(autouse=True)
def isolate_apptest_globals():
    """Undo process-global Streamlit mutation that breaks later AppTest.

    AppTest installs the page as ``sys.modules["__main__"]`` and puts the
    page directory on ``sys.path``. Helper-unit stubs also replace
    ``sys.modules["streamlit"]`` (no ``.secrets``). ``AppTest.run`` does
    ``import streamlit as st`` and then reads ``st.secrets`` (QI-10 §3.6
    suite-order). Restore streamlit *before* the test as well as after —
    collection or a prior helper can leave a stub before the first
    AppTest runs. Snapshot ``__main__`` / ``sys.path`` at setup (pytest
    may have extended path after session start) and restore both after.
    """
    _restore_real_streamlit()
    main_module = sys.modules.get("__main__")
    path_snapshot = list(sys.path)
    try:
        yield
    finally:
        if main_module is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = main_module
        _restore_real_streamlit()
        sys.path[:] = path_snapshot
