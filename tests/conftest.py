"""Shared pytest fixtures.

B-13 / QI-10-05: ``isolate_apptest_globals`` promoted from
``tests/test_assistant_page_render.py`` so every AppTest module shares one
``sys.modules["__main__"]`` + ``sys.path`` restore (QI-10 §3.6 rule 3).
"""

from __future__ import annotations

import importlib
import sys

import pytest

# Session-start Streamlit (real package). Helper stubs replace
# ``sys.modules["streamlit"]`` without restore; AppTest.run then does
# ``import streamlit as st`` and dies on missing ``.secrets``.
_REAL_STREAMLIT = importlib.import_module("streamlit")


@pytest.fixture(autouse=True)
def isolate_apptest_globals():
    """Undo process-global Streamlit mutation that breaks later AppTest.

    AppTest installs the page as ``sys.modules["__main__"]`` and puts the
    page directory on ``sys.path``. Helper-unit stubs also replace
    ``sys.modules["streamlit"]`` (no ``.secrets``). ``AppTest.run`` does
    ``import streamlit as st`` and then reads ``st.secrets`` (QI-10 §3.6
    suite-order). Restore all three so spawn-context ``run_batch`` and
    later AppTest stay green.
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
        sys.modules["streamlit"] = _REAL_STREAMLIT
        sys.path[:] = path_snapshot
