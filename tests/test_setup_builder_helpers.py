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


def test_sync_editor_widget_state_overwrites_for_loaded_setup():
    setup_builder.st.session_state = {}
    warnings = setup_builder._sync_editor_widget_state(
        {
            "name": "Loaded setup",
            "description": "from library",
            "confluence_mode": "global_cluster",
            "selected_levels": ["ONH"],
            "tolerance_ticks": 3.5,
            "min_confluences": 2,
            "max_confluences": 4,
            "naked_only": True,
            "naked_requirement": "all",
            "trigger": "reject",
            "trigger_timeframe": "5min",
            "direction": "long",
        },
        ["ONH", "ONL"],
        overwrite=True,
    )
    assert warnings == []
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SETUP_NAME] == "Loaded setup"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TRIGGER] == "reject"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SELECTED_LEVELS] == ["ONH"]


def test_sync_editor_widget_state_invalid_legacy_values_fallback_with_warnings():
    setup_builder.st.session_state = {}
    warnings = setup_builder._sync_editor_widget_state(
        {
            "name": 123,
            "description": {"invalid": "description"},
            "confluence_mode": "bad-mode",
            "selected_levels": "ONH",
            "tolerance_ticks": -10,
            "min_confluences": "bad",
            "max_confluences": 99,
            "naked_requirement": "bad",
            "trigger": "bad",
            "trigger_timeframe": "bad",
            "direction": "bad",
            "trigger_params": {
                "entry_retrace_ticks": -1,
                "max_entry_wait_bars_after_reversal": "oops",
            },
        },
        ["ONH", "ONL"],
        overwrite=True,
    )
    assert any("confluence mode is invalid" in message for message in warnings)
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_CONFLUENCE_MODE] == "Global cluster"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TRIGGER] == "touch"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_DIRECTION] == "both"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TRIGGER_TIMEFRAME] == "Base/current timeframe"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SELECTED_LEVELS] == ["ONH", "ONL"]
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TOLERANCE_TICKS] == 0.0


def test_sync_editor_widget_state_invalid_selected_levels_uses_default_selection():
    setup_builder.st.session_state = {}
    warnings = setup_builder._sync_editor_widget_state(
        {"selected_levels": "ONH"},
        ["ONH", "ONL"],
        overwrite=True,
    )

    assert "Loaded selected levels are invalid; using default level selection." in warnings
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SELECTED_LEVELS] == ["ONH", "ONL"]


def test_unavailable_level_references_detected_for_save_guard():
    unavailable = setup_builder._unavailable_level_references(
        {
            "confluence_mode": "anchor_rules",
            "anchor_level": "MISSING_ANCHOR",
            "confluence_rules": [{"level": "ONH"}, {"level": "MISSING_RULE"}],
        },
        ["ONH", "ONL"],
    )
    assert unavailable["anchor_level"] == ["MISSING_ANCHOR"]
    assert unavailable["confluence_rules"] == ["MISSING_RULE"]
    assert setup_builder._has_unavailable_level_references(unavailable) is True


def test_current_editor_config_uses_current_candidate_not_stale_loaded_config():
    stale_loaded = {
        "setup_id": "setup-123",
        "confluence_mode": "global_cluster",
        "selected_levels": ["ONH", "MISSING"],
    }
    stale_missing = setup_builder._unavailable_level_references(stale_loaded, ["ONH", "ONL"])

    current_candidate = setup_builder._build_current_editor_config(
        editor_seed=stale_loaded,
        instrument="ES",
        current_dataset_id="dataset-a",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        trigger_timeframe="base",
        direction="both",
        confluence_mode="global_cluster",
        anchor_level=None,
        confluence_rules=[],
        min_valid_confluences=1,
        trigger_params={},
        setup_name="Edited setup",
        description="",
    )
    current_missing = setup_builder._unavailable_level_references(current_candidate, ["ONH", "ONL"])

    assert stale_missing["selected_levels"] == ["MISSING"]
    assert current_missing["selected_levels"] == []
    assert current_candidate["setup_id"] == "setup-123"
    assert current_candidate["dataset_id"] == "dataset-a"


def test_current_editor_config_still_reports_missing_levels_when_candidate_is_invalid():
    current_candidate = setup_builder._build_current_editor_config(
        editor_seed={},
        instrument="ES",
        current_dataset_id="dataset-a",
        selected_levels=["ONH", "MISSING"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        trigger_timeframe="base",
        direction="both",
        confluence_mode="global_cluster",
        anchor_level=None,
        confluence_rules=[],
        min_valid_confluences=1,
        trigger_params={},
        setup_name="Edited setup",
        description="",
    )

    current_missing = setup_builder._unavailable_level_references(current_candidate, ["ONH", "ONL"])

    assert current_missing["selected_levels"] == ["MISSING"]
    assert setup_builder._has_unavailable_level_references(current_missing) is True
