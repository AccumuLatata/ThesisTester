from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd


def _make_streamlit_stub(session_state: dict) -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    def _cache_data(*args, **kwargs):
        def _decorator(fn):
            return fn
        return _decorator

    for name in (
        "title",
        "caption",
        "subheader",
        "warning",
        "success",
        "error",
        "info",
        "markdown",
        "stop",
        "rerun",
        "selectbox",
        "button",
        "radio",
        "multiselect",
        "file_uploader",
        "dataframe",
        "metric",
        "text_input",
        "columns",
        "divider",
    ):
        setattr(st, name, _noop)
    st.cache_data = _cache_data  # type: ignore[assignment]
    st.session_state = session_state  # type: ignore[assignment]
    return st


def _import_data_page_module(session_state: dict):
    stub = _make_streamlit_stub(session_state)
    sys.modules["streamlit"] = stub
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "1_Data.py"
    spec = importlib.util.spec_from_file_location("data_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        pass
    return mod


def test_set_active_dataset_state_clears_mismatched_active_setup(monkeypatch):
    session_state = {
        "dataset_id": "dataset-old",
        "setup_config": {"name": "old setup", "dataset_id": "dataset-old"},
        "_setup_builder_editor_config": {"name": "draft setup", "dataset_id": "dataset-old"},
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "_clear_dataset_dependent_state", lambda: None)
    monkeypatch.setattr(data_page, "ensure_display_timezone", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)

    df = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    data_page._set_active_dataset_state(
        df,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        resampled_data={},
        saved_dataset_id="dataset-new",
    )

    assert "setup_config" not in session_state
    assert "_setup_builder_editor_config" not in session_state
