from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    for name in (
        "title",
        "caption",
        "subheader",
        "warning",
        "info",
        "error",
        "success",
        "markdown",
        "stop",
        "rerun",
        "button",
        "toggle",
        "radio",
        "selectbox",
        "multiselect",
        "number_input",
        "slider",
        "text_input",
        "text_area",
        "columns",
    ):
        setattr(st, name, _noop)
    st.session_state = {"levels": pd.DataFrame({"ONH": [], "ONL": []})}  # type: ignore[assignment]
    return st


def _import_setup_builder_module():
    stub = _make_streamlit_stub()
    sys.modules.setdefault("streamlit", stub)

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "2_Setup_Builder.py"
    spec = importlib.util.spec_from_file_location("setup_builder_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        pass
    return mod


setup_builder = _import_setup_builder_module()


def test_seed_editor_config_hydrates_from_active_setup():
    seeded = setup_builder._seed_editor_config(
        active_setup={"name": "Loaded", "trigger": "reject", "selected_levels": ["ONH"]},
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert seeded["name"] == "Loaded"
    assert seeded["trigger"] == "reject"
    assert seeded["selected_levels"] == ["ONH"]


def test_seed_editor_config_uses_defaults_when_no_active_setup():
    seeded = setup_builder._seed_editor_config(
        active_setup=None,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert seeded["name"] == "Untitled setup"
    assert seeded["trigger"] == "touch"
    assert seeded["selected_levels"] == ["ONH", "ONL"]


def test_render_setup_level_warnings_reports_missing_levels_without_crashing(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(setup_builder.st, "warning", lambda message: warnings.append(message))
    setup_builder._render_setup_level_warnings(
        {"confluence_mode": "global_cluster", "selected_levels": ["ONH", "MISSING"]},
        ["ONH", "ONL"],
    )
    assert warnings
    assert "MISSING" in warnings[0]

