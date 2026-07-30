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
    assert (
        setup_builder.st.session_state[setup_builder.WIDGET_KEY_CONFLUENCE_MODE] == "Global cluster"
    )
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TRIGGER] == "touch"
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_DIRECTION] == "both"
    assert (
        setup_builder.st.session_state[setup_builder.WIDGET_KEY_TRIGGER_TIMEFRAME]
        == "Base/current timeframe"
    )
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SELECTED_LEVELS] == [
        "ONH",
        "ONL",
    ]
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_TOLERANCE_TICKS] == 0.0


def test_sync_editor_widget_state_invalid_selected_levels_uses_default_selection():
    setup_builder.st.session_state = {}
    warnings = setup_builder._sync_editor_widget_state(
        {"selected_levels": "ONH"},
        ["ONH", "ONL"],
        overwrite=True,
    )

    assert "Loaded selected levels are invalid; using default level selection." in warnings
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_SELECTED_LEVELS] == [
        "ONH",
        "ONL",
    ]


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
        otf_filter={"enabled": False, "timeframes": []},
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
        otf_filter={"enabled": False, "timeframes": []},
        setup_name="Edited setup",
        description="",
    )

    current_missing = setup_builder._unavailable_level_references(current_candidate, ["ONH", "ONL"])

    assert current_missing["selected_levels"] == ["MISSING"]
    assert setup_builder._has_unavailable_level_references(current_missing) is True


def test_sync_editor_widget_state_legacy_setup_hydrates_otf_disabled_defaults():
    setup_builder.st.session_state = {}
    setup_builder._sync_editor_widget_state({}, ["ONH", "ONL"], overwrite=True)
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_ENABLED] is False
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_TIMEFRAMES] == []
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS] == 3


def test_sync_editor_widget_state_hydrates_enabled_otf_values():
    setup_builder.st.session_state = {}
    setup_builder._sync_editor_widget_state(
        {
            "otf_filter": {
                "enabled": True,
                "timeframes": ["30m", "5m"],
                "alignment_mode": "all",
                "minimum_consecutive_bars": 5,
                "directional": True,
                "use_completed_bars_only": True,
                "session_reset": "session",
            }
        },
        ["ONH", "ONL"],
        overwrite=True,
    )
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_ENABLED] is True
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_TIMEFRAMES] == ["30m", "5m"]
    assert setup_builder.st.session_state[setup_builder.WIDGET_KEY_OTF_MIN_CONSECUTIVE_BARS] == 5


# ---------------------------------------------------------------------------
# _resolve_otf_for_ui — UI-safe OTF resolution helper
# ---------------------------------------------------------------------------


def test_resolve_otf_for_ui_valid_disabled_config_returns_no_warning():
    config = {"otf_filter": None}
    otf_config, warning = setup_builder._resolve_otf_for_ui(config)
    assert warning is None
    assert otf_config["enabled"] is False


def test_resolve_otf_for_ui_valid_enabled_config_returns_no_warning():
    config = {
        "otf_filter": {
            "enabled": True,
            "timeframes": ["15m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    }
    otf_config, warning = setup_builder._resolve_otf_for_ui(config)
    assert warning is None
    assert otf_config["enabled"] is True


def test_resolve_otf_for_ui_invalid_config_returns_disabled_and_warning():
    config = {
        "otf_filter": {
            "enabled": True,
            "timeframes": [],
        }  # invalid: enabled OTF requires at least one timeframe
    }
    otf_config, warning = setup_builder._resolve_otf_for_ui(config)
    assert otf_config["enabled"] is False  # fallen back to disabled
    assert isinstance(warning, str) and len(warning) > 0


def test_resolve_otf_for_ui_does_not_mutate_caller_dict():
    original = {
        "otf_filter": {"enabled": True, "timeframes": []}  # invalid
    }
    original_copy = dict(original)
    setup_builder._resolve_otf_for_ui(original)
    assert original == original_copy  # caller's dict is unchanged


# ---------------------------------------------------------------------------
# _seed_editor_config — malformed OTF safety
# ---------------------------------------------------------------------------


def test_seed_editor_config_malformed_otf_does_not_crash():
    """Malformed active OTF config must not crash editor seeding."""
    malformed = {
        "name": "Malformed",
        "otf_filter": {"enabled": True, "timeframes": []},  # invalid
    }
    seeded = setup_builder._seed_editor_config(
        active_setup=malformed,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert isinstance(seeded, dict)


def test_seed_editor_config_malformed_otf_hydrates_disabled_defaults():
    """Malformed active OTF config must hydrate disabled widget defaults."""
    malformed = {
        "name": "Malformed",
        "otf_filter": {"enabled": True, "timeframes": []},  # invalid
    }
    seeded = setup_builder._seed_editor_config(
        active_setup=malformed,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert seeded["otf_filter"]["enabled"] is False
    assert seeded["otf_filter"]["timeframes"] == []


def test_seed_editor_config_malformed_otf_includes_repair_warning():
    """Malformed OTF config must produce a repair warning in the returned dict."""
    malformed = {
        "name": "Malformed",
        "otf_filter": {
            "enabled": True,
            "timeframes": [],
        },  # invalid: enabled OTF requires at least one timeframe
    }
    seeded = setup_builder._seed_editor_config(
        active_setup=malformed,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert setup_builder._OTF_REPAIR_DICT_KEY in seeded
    assert isinstance(seeded[setup_builder._OTF_REPAIR_DICT_KEY], str)


def test_seed_editor_config_valid_enabled_otf_unchanged():
    """Valid enabled OTF setup hydration must remain unchanged."""
    valid_setup = {
        "name": "Valid",
        "otf_filter": {
            "enabled": True,
            "timeframes": ["15m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 4,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        },
    }
    seeded = setup_builder._seed_editor_config(
        active_setup=valid_setup,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert seeded["otf_filter"]["enabled"] is True
    assert seeded["otf_filter"]["timeframes"] == ["15m"]
    assert seeded["otf_filter"]["minimum_consecutive_bars"] == 4
    assert setup_builder._OTF_REPAIR_DICT_KEY not in seeded


def test_seed_editor_config_repaired_setup_has_canonical_hash():
    """After seeding with malformed OTF, the resulting dict must have a valid canonical hash."""
    from thesistester.persistence.local_store import compute_otf_config_hash

    malformed = {
        "name": "Malformed",
        "otf_filter": {"enabled": True, "timeframes": []},
    }
    seeded = setup_builder._seed_editor_config(
        active_setup=malformed,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    # The hash must be recomputable from the repaired otf_filter
    expected_hash = compute_otf_config_hash(seeded["otf_filter"])
    assert seeded["otf_config_hash"] == expected_hash


def test_seed_editor_config_does_not_mutate_active_setup():
    """_seed_editor_config must not mutate the caller-supplied active_setup dict."""
    active = {
        "name": "Original",
        "otf_filter": {"enabled": True, "timeframes": []},  # invalid
    }
    original_active = dict(active)
    setup_builder._seed_editor_config(
        active_setup=active,
        instrument="ES",
        defaults=["ONH", "ONL"],
        dataset_id="dataset-a",
    )
    assert active == original_active
