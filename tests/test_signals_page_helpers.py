"""Tests for pure helper functions extracted from pages/6_Signals.py.

We import the helpers by loading the module source directly so we avoid
triggering Streamlit runtime side-effects that occur at page import time.
"""

from __future__ import annotations

import json
import sys
import types

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Minimal Streamlit stub so the page module can be imported without a running
# Streamlit server.
# ---------------------------------------------------------------------------


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        pass

    for name in (
        "title",
        "header",
        "subheader",
        "info",
        "warning",
        "error",
        "success",
        "caption",
        "stop",
        "dataframe",
        "metric",
        "plotly_chart",
        "checkbox",
        "toggle",
        "radio",
        "selectbox",
        "multiselect",
        "number_input",
        "slider",
        "button",
    ):
        setattr(st, name, _noop)

    # session_state as simple dict-like
    st.session_state = {}  # type: ignore[assignment]

    # columns returns dummy objects
    class _Col:
        def metric(self, *a, **kw):
            pass

    def _columns(n, **kw):
        return [_Col() for _ in range(n)]

    st.columns = _columns  # type: ignore[assignment]

    # sidebar context manager
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def __getattr__(self, item):
            return _noop

    st.sidebar = _Ctx()  # type: ignore[assignment]
    st.spinner = lambda *a, **k: _Ctx()  # type: ignore[assignment]

    return st


def _import_page_helpers():
    """Return selected pure helpers from the page module."""
    stub = _make_streamlit_stub()
    sys.modules.setdefault("streamlit", stub)

    import importlib.util
    import pathlib

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "6_Signals.py"
    spec = importlib.util.spec_from_file_location("signals_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # prevent the page-level code from running (st.session_state lookups etc.)
    # by patching st.session_state so `get` returns safe defaults
    stub.session_state = {  # type: ignore[assignment]
        "levels": pd.DataFrame({"timestamp": [], "close": []}),
    }
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except SystemExit:
        pass  # st.stop() raises SystemExit in some Streamlit versions
    except Exception:
        pass  # page-level errors are acceptable; we only need the helpers

    return (
        mod._parse_anchor_rule_results,
        mod._render_anchor_diagnostics,
        mod._dataset_relation_label,
        mod._prioritize_saved_setups,
        mod._saved_setup_option_label,
        mod._filter_saved_setups_for_signals,
        mod._saved_setup_compatibility_issues,
        mod._extract_setup_snapshot_from_signal_run,
        mod._saved_setup_caption,
        mod._no_zones_message,
        mod._saved_setup_generation_blockers,
        mod._generate_setup_from_page_fields,
        mod._safe_float,
        mod._safe_int,
        mod._safe_bool,
        mod._safe_dict,
        mod._safe_list,
        mod._normalize_signal_settings_for_hash,
        mod._try_normalize_signal_settings_for_hash,
        mod._resolve_loaded_signal_identity,
        mod._validate_signal_artifact_identity_for_save,
        mod._controls_changed_warning_for_view,
        mod._IDENTITY_STATUS_TRUSTED,
        mod._IDENTITY_STATUS_INVALID,
        mod._IDENTITY_STATUS_UNAVAILABLE,
        mod._SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY,
        mod._SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY,
        mod._OTF_INVALID_ARTIFACT_BLOCKER,
        mod._SIGNAL_CONTROLS_CHANGED_WARNING,
        mod.ANCHOR_DIAGNOSTIC_COLUMNS,
        mod._get_stored_signal_settings,
        mod._typed_signals_error_message,
        mod._signal_generation_admission_error,
        mod._run_signal_generation,
        mod._render_signals_chart,
        mod._signal_table_display_cols,
    )


(
    _parse_anchor_rule_results,
    _render_anchor_diagnostics,
    _dataset_relation_label,
    _prioritize_saved_setups,
    _saved_setup_option_label,
    _filter_saved_setups_for_signals,
    _saved_setup_compatibility_issues,
    _extract_setup_snapshot_from_signal_run,
    _saved_setup_caption,
    _no_zones_message,
    _saved_setup_generation_blockers,
    _generate_setup_from_page_fields,
    _safe_float,
    _safe_int,
    _safe_bool,
    _safe_dict,
    _safe_list,
    _normalize_signal_settings_for_hash,
    _try_normalize_signal_settings_for_hash,
    _resolve_loaded_signal_identity,
    _validate_signal_artifact_identity_for_save,
    _controls_changed_warning_for_view,
    _IDENTITY_STATUS_TRUSTED,
    _IDENTITY_STATUS_INVALID,
    _IDENTITY_STATUS_UNAVAILABLE,
    _SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY,
    _SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY,
    _OTF_INVALID_ARTIFACT_BLOCKER,
    _SIGNAL_CONTROLS_CHANGED_WARNING,
    ANCHOR_DIAGNOSTIC_COLUMNS,
    _get_stored_signal_settings,
    _typed_signals_error_message,
    _signal_generation_admission_error,
    _run_signal_generation,
    _render_signals_chart,
    _signal_table_display_cols,
) = _import_page_helpers()


# ---------------------------------------------------------------------------
# _parse_anchor_rule_results tests
# ---------------------------------------------------------------------------

TZ = "America/New_York"


def _zones(**extra) -> pd.DataFrame:
    base = {
        "timestamp": [pd.Timestamp("2026-06-02 09:30:00", tz=TZ)],
        "bar_index": [0],
        "anchor_level": ["pdHigh"],
        "anchor_price": [4500.0],
        "valid_confluence_count": [1],
    }
    base.update(extra)
    return pd.DataFrame(base)


def test_parse_empty_zones_returns_empty():
    result = _parse_anchor_rule_results(pd.DataFrame())
    assert result.empty


def test_parse_zones_without_rule_results_column_returns_empty():
    df = _zones()
    result = _parse_anchor_rule_results(df)
    assert result.empty


def test_parse_single_valid_rule():
    rule = {
        "level": "VWAP_rolling_1h",
        "price": 4498.0,
        "tolerance_ticks": 4,
        "distance_ticks": 2.0,
        "required": True,
        "valid": True,
        "reason": "within tolerance",
    }
    df = _zones(rule_results=[json.dumps([rule])])
    result = _parse_anchor_rule_results(df)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["rule_level"] == "VWAP_rolling_1h"
    assert row["rule_price"] == 4498.0
    assert row["valid"] == True  # noqa: E712
    assert row["anchor_level"] == "pdHigh"


def test_parse_multiple_rules_per_zone():
    rules = [
        {
            "level": "VWAP",
            "price": 4499.0,
            "tolerance_ticks": 4,
            "distance_ticks": 1.0,
            "required": True,
            "valid": True,
            "reason": "ok",
        },
        {
            "level": "pdLow",
            "price": 4495.0,
            "tolerance_ticks": 8,
            "distance_ticks": 20.0,
            "required": False,
            "valid": False,
            "reason": "too far",
        },
    ]
    df = _zones(rule_results=[json.dumps(rules)])
    result = _parse_anchor_rule_results(df)
    assert len(result) == 2
    assert list(result["rule_level"]) == ["VWAP", "pdLow"]


def test_parse_multiple_zones():
    rule = {
        "level": "VWAP",
        "price": 4500.0,
        "tolerance_ticks": 4,
        "distance_ticks": 1.0,
        "required": True,
        "valid": True,
        "reason": "ok",
    }
    df = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                pd.Timestamp("2026-06-02 09:31:00", tz=TZ),
            ],
            "bar_index": [0, 1],
            "anchor_level": ["pdHigh", "pdHigh"],
            "anchor_price": [4500.0, 4502.0],
            "valid_confluence_count": [1, 1],
            "rule_results": [json.dumps([rule]), json.dumps([rule])],
        }
    )
    result = _parse_anchor_rule_results(df)
    assert len(result) == 2


def test_parse_malformed_json_skips_row():
    df = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                pd.Timestamp("2026-06-02 09:31:00", tz=TZ),
            ],
            "bar_index": [0, 1],
            "anchor_level": ["pdHigh", "pdHigh"],
            "anchor_price": [4500.0, 4502.0],
            "valid_confluence_count": [1, 1],
            "rule_results": [
                "not-valid-json{{{",
                json.dumps(
                    [
                        {
                            "level": "VWAP",
                            "price": 4500.0,
                            "tolerance_ticks": 4,
                            "distance_ticks": 1.0,
                            "required": True,
                            "valid": True,
                            "reason": "ok",
                        }
                    ]
                ),
            ],
        }
    )
    result = _parse_anchor_rule_results(df)
    # Only the valid row contributes
    assert len(result) == 1
    assert result.iloc[0]["rule_level"] == "VWAP"


def test_parse_none_json_skips_row():
    df = _zones(rule_results=[None])
    result = _parse_anchor_rule_results(df)
    assert result.empty


def test_parse_result_columns():
    rule = {
        "level": "VWAP",
        "price": 4500.0,
        "tolerance_ticks": 4,
        "distance_ticks": 1.0,
        "required": True,
        "valid": True,
        "reason": "ok",
    }
    df = _zones(rule_results=[json.dumps([rule])])
    result = _parse_anchor_rule_results(df)
    expected = {
        "zone_row",
        "timestamp",
        "bar_index",
        "anchor_level",
        "anchor_price",
        "rule_level",
        "rule_price",
        "distance_ticks",
        "tolerance_ticks",
        "required",
        "valid",
        "reason",
    }
    assert expected.issubset(set(result.columns))


def test_saved_setup_caption_global_mode():
    caption = _saved_setup_caption(
        {
            "trigger": "touch",
            "direction": "both",
            "min_confluences": 2,
            "max_confluences": 5,
        }
    )
    assert (
        caption
        == "Trigger=touch • Direction=both • Confluences=2–5 • Trigger TF=base • OTF=disabled"
    )


def test_saved_setup_caption_anchor_mode():
    caption = _saved_setup_caption(
        {
            "confluence_mode": "anchor_rules",
            "anchor_level": "pdHigh",
            "confluence_rules": [{"level": "VWAP"}, {"level": "ONH"}],
            "min_valid_confluences": 2,
        }
    )
    assert (
        caption
        == "Mode=anchor_rules • Anchor=pdHigh • Rules=2 • Min valid=2 • Trigger TF=base • OTF=disabled"
    )


def test_dataset_relation_labels():
    assert _dataset_relation_label("dataset-a", "dataset-a") == "current dataset"
    assert _dataset_relation_label(None, "dataset-a") == "global/no dataset"
    assert _dataset_relation_label("dataset-b", "dataset-a") == "other dataset"


def test_saved_setup_prioritization_current_then_global_then_other():
    setups = [
        {"setup_id": "other", "dataset_id": "dataset-b"},
        {"setup_id": "global", "dataset_id": None},
        {"setup_id": "current", "dataset_id": "dataset-a"},
    ]
    prioritized = _prioritize_saved_setups(setups, current_dataset_id="dataset-a")
    assert [item["setup_id"] for item in prioritized] == ["current", "global", "other"]


def test_filter_saved_setups_defaults_to_current_and_global():
    setups = [
        {"setup_id": "other", "dataset_id": "dataset-b"},
        {"setup_id": "global", "dataset_id": None},
        {"setup_id": "current", "dataset_id": "dataset-a"},
    ]
    filtered = _filter_saved_setups_for_signals(
        setups,
        current_dataset_id="dataset-a",
        include_other_datasets=False,
    )
    assert [item["setup_id"] for item in filtered] == ["current", "global"]


def test_saved_setup_option_label_includes_dataset_relation():
    label = _saved_setup_option_label(
        {
            "name": "My setup",
            "instrument": "ES",
            "updated_at": "2026-06-07T00:00:00Z",
            "dataset_id": None,
            "setup_config": {
                "confluence_mode": "global_cluster",
                "trigger": "touch",
                "direction": "both",
            },
        },
        "dataset-a",
    )
    assert "My setup · ES · 2026-06-07" in label
    assert "mode=global_cluster" in label
    assert "trigger=touch" in label
    assert "direction=both" in label
    assert "global/no dataset" in label


def test_saved_setup_compatibility_detects_global_missing_levels():
    issues = _saved_setup_compatibility_issues(
        {
            "confluence_mode": "global_cluster",
            "selected_levels": ["ONH", "MISSING"],
        },
        ["ONH", "ONL"],
    )
    assert issues["selected_levels"] == ["MISSING"]
    assert issues["anchor_level"] == []
    assert issues["confluence_rules"] == []


def test_saved_setup_compatibility_detects_anchor_missing_levels():
    issues = _saved_setup_compatibility_issues(
        {
            "confluence_mode": "anchor_rules",
            "anchor_level": "MISSING_ANCHOR",
            "confluence_rules": [{"level": "ONH"}, {"level": "MISSING_RULE"}],
        },
        ["ONH", "ONL"],
    )
    assert issues["selected_levels"] == []
    assert issues["anchor_level"] == ["MISSING_ANCHOR"]
    assert issues["confluence_rules"] == ["MISSING_RULE"]


def test_saved_setup_compatibility_valid_setup_has_no_issues():
    issues = _saved_setup_compatibility_issues(
        {
            "confluence_mode": "anchor_rules",
            "anchor_level": "ONH",
            "confluence_rules": [{"level": "ONL"}],
        },
        ["ONH", "ONL"],
    )
    assert issues == {"selected_levels": [], "anchor_level": [], "confluence_rules": []}


def test_extract_setup_snapshot_prefers_signal_settings_snapshot():
    snapshot = _extract_setup_snapshot_from_signal_run(
        {
            "signal_settings": {"setup_snapshot": {"name": "from-settings"}},
            "last_signal_setup": {"name": "fallback"},
        }
    )
    assert snapshot == {"name": "from-settings"}


def test_extract_setup_snapshot_falls_back_to_last_signal_setup():
    snapshot = _extract_setup_snapshot_from_signal_run(
        {
            "signal_settings": {"setup_snapshot": None},
            "last_signal_setup": {"name": "fallback"},
        }
    )
    assert snapshot == {"name": "fallback"}


def test_extract_setup_snapshot_handles_missing_snapshot():
    snapshot = _extract_setup_snapshot_from_signal_run(
        {"signal_settings": {}, "last_signal_setup": {}}
    )
    assert snapshot is None


def test_no_zones_message_global_mode():
    assert _no_zones_message("global_cluster") == (
        "No confluence zones found with the current settings. "
        "Try increasing tolerance or selecting more levels."
    )


def test_no_zones_message_anchor_mode():
    assert _no_zones_message("anchor_rules") == (
        "No confluence zones found with the current settings. "
        "For anchor setups, review the anchor level, confluence rules, "
        "and per-rule tolerances. A missing finite anchor price also "
        "yields no zones."
    )


# ---------------------------------------------------------------------------
# _saved_setup_generation_blockers tests
# ---------------------------------------------------------------------------

_VALID_GLOBAL_CONFIG = {
    "name": "My Setup",
    "confluence_mode": "global_cluster",
    "selected_levels": ["ONH", "ONL"],
    "tolerance_ticks": 4.0,
    "min_confluences": 2,
    "max_confluences": 5,
    "naked_only": False,
    "naked_requirement": "any",
    "trigger": "touch",
    "trigger_timeframe": "base",
    "direction": "both",
    "trigger_params": {},
}


def test_generation_blockers_valid_global_setup_returns_no_blockers():
    blockers = _saved_setup_generation_blockers(
        _VALID_GLOBAL_CONFIG,
        ["ONH", "ONL", "VWAP"],
    )
    assert blockers == []


def test_generation_blockers_invalid_confluence_mode():
    config = {**_VALID_GLOBAL_CONFIG, "confluence_mode": "unsupported_mode"}
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("confluence mode" in b.lower() for b in blockers)


def test_generation_blockers_global_empty_selected_levels():
    config = {**_VALID_GLOBAL_CONFIG, "selected_levels": []}
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("level" in b.lower() for b in blockers)


def test_generation_blockers_anchor_missing_anchor_level():
    config = {
        "name": "Anchor Setup",
        "confluence_mode": "anchor_rules",
        "anchor_level": "",
        "confluence_rules": [{"level": "ONL", "tolerance_ticks": 4.0, "required": False}],
        "min_valid_confluences": 1,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
    }
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("anchor" in b.lower() for b in blockers)


def test_generation_blockers_anchor_empty_confluence_rules():
    config = {
        "name": "Anchor Setup",
        "confluence_mode": "anchor_rules",
        "anchor_level": "ONH",
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
    }
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("confluence rule" in b.lower() for b in blockers)


def test_generation_blockers_anchor_empty_rules_min_valid_zero_ok():
    config = {
        "name": "Anchor Setup",
        "confluence_mode": "anchor_rules",
        "anchor_level": "ONH",
        "confluence_rules": [],
        "min_valid_confluences": 0,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
    }
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert not any("confluence rule" in b.lower() for b in blockers)


def test_generation_blockers_min_valid_confluences_exceeds_rules():
    config = {
        "name": "Anchor Setup",
        "confluence_mode": "anchor_rules",
        "anchor_level": "ONH",
        "confluence_rules": [{"level": "ONL", "tolerance_ticks": 4.0, "required": False}],
        "min_valid_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
    }
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("minimum valid confluences" in b.lower() for b in blockers)


def test_generation_blockers_malformed_confluence_rule():
    config = {
        "name": "Anchor Setup",
        "confluence_mode": "anchor_rules",
        "anchor_level": "ONH",
        "confluence_rules": ["not-a-dict"],
        "min_valid_confluences": 1,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
    }
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("rule" in b.lower() for b in blockers)


def test_generation_blockers_missing_available_level_references():
    config = {**_VALID_GLOBAL_CONFIG, "selected_levels": ["ONH", "MISSING_LEVEL"]}
    blockers = _saved_setup_generation_blockers(config, ["ONH", "ONL"])
    assert any("MISSING_LEVEL" in b for b in blockers)


# ---------------------------------------------------------------------------
# C-4 / QI-03-10 — generate path uses build_setup_config
# ---------------------------------------------------------------------------


def _page6_saved_ao1_3c_kwargs() -> dict:
    return {
        "name": "ao1_3c",
        "description": "C-4 AO1 probe",
        "instrument": "ES",
        "selected_levels": ["ONH"],
        "tolerance_ticks": 4.0,
        "min_confluences": 1,
        "max_confluences": 2,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "3c",
        "trigger_timeframe": "base",
        "direction": "both",
        "confluence_mode": "anchor_rules",
        "anchor_level": "ONH",
        "confluence_rules": [],
        "min_valid_confluences": 0,
        "trigger_params": {
            "entry_retrace_ticks": 6.0,
            "max_entry_wait_bars_after_reversal": 10,
            "arrival_tolerance_ticks": 1.0,
        },
        "otf_filter": None,
        "entry_window": None,
    }


def test_page6_generate_setup_hashes_equal_build_setup_config():
    """Page-6 kwargs vs ``build_setup_config`` hash, incl. 3c + AO1 min_valid=0."""
    from thesistester.setup import build_setup_config, build_setup_kwargs_from_mapping

    kwargs = _page6_saved_ao1_3c_kwargs()
    page_setup = _generate_setup_from_page_fields(**kwargs)
    so_t = build_setup_config(**build_setup_kwargs_from_mapping(kwargs))
    assert page_setup == so_t
    assert json.dumps(page_setup, sort_keys=True, default=str) == json.dumps(
        so_t, sort_keys=True, default=str
    )
    assert so_t["min_valid_confluences"] == 0
    assert so_t["trigger_params"]["entry_retrace_ticks"] == 6.0
    assert so_t["trigger_params"]["max_entry_wait_bars_after_reversal"] == 10
    assert so_t["trigger_params"]["arrival_tolerance_ticks"] == 0.0
    assert "_source_mode" not in so_t["trigger_params"]


def test_page6_source_mapping_keeps_ao1_when_field_omitted():
    """Saved mapping supplies AO1 ``min_valid=0`` when page fields omit it."""
    kwargs = _page6_saved_ao1_3c_kwargs()
    source = {**kwargs, "setup_id": "drop-me", "min_valid_confluences": 0}
    fields = {key: value for key, value in kwargs.items() if key != "min_valid_confluences"}
    page_setup = _generate_setup_from_page_fields(source_mapping=source, **fields)
    assert page_setup["min_valid_confluences"] == 0
    assert "_source_mode" not in page_setup["trigger_params"]


def test_page6_3c_none_params_use_bsc_defaults():
    kwargs = _page6_saved_ao1_3c_kwargs()
    kwargs["trigger_params"] = None
    setup = _generate_setup_from_page_fields(**kwargs)
    assert setup["trigger_params"]["entry_retrace_ticks"] == 4.0
    assert setup["trigger_params"]["max_entry_wait_bars_after_reversal"] == 5
    assert setup["trigger_params"]["arrival_tolerance_ticks"] == 0.0
    assert "_source_mode" not in setup["trigger_params"]


def test_page6_bsc_rejects_non_numeric_3c_retrace():
    kwargs = _page6_saved_ao1_3c_kwargs()
    kwargs["trigger_params"] = {
        "entry_retrace_ticks": "bad",
        "max_entry_wait_bars_after_reversal": 5,
    }
    with pytest.raises(ValueError):
        _generate_setup_from_page_fields(**kwargs)


def test_page6_settings_trigger_params_omit_source_mode():
    """Identity hash uses BSC trigger_params; ``_source_mode`` is generate-only."""
    kwargs = _page6_saved_ao1_3c_kwargs()
    kwargs["trigger_params"] = {
        **kwargs["trigger_params"],
        "_source_mode": "anchor_rules",
    }
    generate_setup = _generate_setup_from_page_fields(**kwargs)
    trigger_params = dict(generate_setup["trigger_params"])
    assert "_source_mode" not in trigger_params
    settings = _normalize_signal_settings_for_hash(
        {
            "confluence_mode": generate_setup["confluence_mode"],
            "selected_levels": generate_setup["selected_levels"],
            "anchor_level": generate_setup["anchor_level"],
            "confluence_rules": generate_setup["confluence_rules"],
            "min_valid_confluences": generate_setup["min_valid_confluences"],
            "tolerance_ticks": generate_setup["tolerance_ticks"],
            "min_confluences": generate_setup["min_confluences"],
            "max_confluences": generate_setup["max_confluences"],
            "naked_only": generate_setup["naked_only"],
            "naked_requirement": generate_setup["naked_requirement"],
            "trigger": generate_setup["trigger"],
            "trigger_timeframe": generate_setup["trigger_timeframe"],
            "direction": generate_setup["direction"],
            "trigger_params": trigger_params,
            "use_saved_setup": True,
            "setup_snapshot": generate_setup,
        }
    )
    assert "_source_mode" not in settings["trigger_params"]


def test_signals_page_generate_uses_bsc_not_run_experiment():
    import ast
    from pathlib import Path

    page_text = (Path(__file__).parent.parent / "pages" / "6_Signals.py").read_text()
    tree = ast.parse(page_text)
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "_generate_setup_from_page_fields" in defined
    assert "_normalize_3c_params" not in defined
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    assert "build_setup_config" in imported
    assert "build_setup_config" in called
    assert "build_setup_kwargs_from_mapping" in imported
    assert "build_setup_kwargs_from_mapping" in called
    assert "run_experiment" not in imported
    assert "run_experiment" not in called
    assert page_text.count('trigger_params["_source_mode"]') == 1


# ---------------------------------------------------------------------------
# _saved_setup_generation_blockers — malformed setup no-crash tests
# ---------------------------------------------------------------------------

_MALFORMED_GLOBAL_SETUP = {
    "name": "Bad setup",
    "confluence_mode": "global_cluster",
    "selected_levels": "ONH",  # wrong type — should be list
    "tolerance_ticks": "bad",
    "min_confluences": "bad",
    "max_confluences": "bad",
    "naked_only": "bad",
    "naked_requirement": "bad",
    "trigger": "3c",
    "trigger_timeframe": "base",
    "direction": "both",
    "trigger_params": "bad",  # wrong type — should be dict
}

_MALFORMED_ANCHOR_SETUP = {
    "name": "Bad anchor setup",
    "confluence_mode": "anchor_rules",
    "anchor_level": "ONH",
    "confluence_rules": None,  # wrong type — should be list
    "min_valid_confluences": "bad",
    "trigger": "touch",
    "trigger_timeframe": "base",
    "direction": "both",
}


def test_generation_blockers_malformed_global_setup_does_not_crash():
    """Malformed global setup must return blockers, not raise."""
    blockers = _saved_setup_generation_blockers(_MALFORMED_GLOBAL_SETUP, ["ONH", "ONL"])
    assert len(blockers) > 0


def test_generation_blockers_malformed_anchor_setup_does_not_crash():
    """Malformed anchor setup (confluence_rules=None) must return blockers, not raise."""
    blockers = _saved_setup_generation_blockers(_MALFORMED_ANCHOR_SETUP, ["ONH", "ONL"])
    assert len(blockers) > 0


# ---------------------------------------------------------------------------
# Safe coercion helpers
# ---------------------------------------------------------------------------


def test_safe_float_none_returns_default():
    assert _safe_float(None, 4.0) == 4.0


def test_safe_float_bad_string_returns_default():
    assert _safe_float("bad", 4.0) == 4.0


def test_safe_float_valid_string_converts():
    assert _safe_float("3.5", 4.0) == 3.5


def test_safe_int_none_returns_default():
    assert _safe_int(None, 5) == 5


def test_safe_int_bad_string_returns_default():
    assert _safe_int("bad", 5) == 5


def test_safe_int_valid_float_string_converts():
    assert _safe_int("7.9", 5) == 7


def test_safe_bool_bool_passthrough():
    assert _safe_bool(True, False) is True
    assert _safe_bool(False, True) is False


def test_safe_bool_bad_string_returns_default():
    assert _safe_bool("bad", False) is False


def test_safe_dict_dict_passthrough():
    d = {"a": 1}
    assert _safe_dict(d) is d


def test_safe_dict_non_dict_returns_empty():
    assert _safe_dict("bad") == {}
    assert _safe_dict(None) == {}


def test_safe_list_list_passthrough():
    lst = [1, 2]
    assert _safe_list(lst) is lst


def test_safe_list_non_list_returns_empty():
    assert _safe_list(None) == []
    assert _safe_list("bad") == []


# ---------------------------------------------------------------------------
# _normalize_signal_settings_for_hash / _try_normalize_signal_settings_for_hash
# OTF identity strictness tests
# ---------------------------------------------------------------------------


def _base_signal_settings(**overrides) -> dict:
    settings = {
        "confluence_mode": "global_cluster",
        "selected_levels": ["ONH", "ONL"],
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
        "use_saved_setup": False,
        "setup_snapshot": None,
    }
    settings.update(overrides)
    return settings


def test_normalize_signal_settings_invalid_explicit_otf_raises():
    """Explicit invalid top-level OTF config must make normalization raise."""
    settings = _base_signal_settings()
    settings["otf_filter"] = {"enabled": True, "timeframes": []}  # enabled with no timeframes
    with pytest.raises(ValueError):
        _normalize_signal_settings_for_hash(settings)


def test_normalize_signal_settings_invalid_setup_snapshot_otf_raises():
    """Invalid setup_snapshot OTF config must make normalization raise."""
    settings = _base_signal_settings(
        use_saved_setup=True,
        setup_snapshot={"name": "A", "otf_filter": {"enabled": True, "timeframes": []}},
    )
    with pytest.raises(ValueError):
        _normalize_signal_settings_for_hash(settings)


def test_normalize_signal_settings_missing_otf_resolves_to_disabled():
    """Settings without otf_filter resolve to canonical disabled defaults."""
    settings = _base_signal_settings()  # no otf_filter key
    normalized = _normalize_signal_settings_for_hash(settings)
    assert normalized["otf_filter"]["enabled"] is False
    assert normalized["otf_filter"]["timeframes"] == []


def test_normalize_signal_settings_valid_enabled_otf_preserved():
    """Valid enabled OTF config is normalized and preserved."""
    settings = _base_signal_settings()
    settings["otf_filter"] = {
        "enabled": True,
        "timeframes": ["15m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
        "directional": True,
        "use_completed_bars_only": True,
        "session_reset": "session",
    }
    normalized = _normalize_signal_settings_for_hash(settings)
    assert normalized["otf_filter"]["enabled"] is True
    assert "15m" in normalized["otf_filter"]["timeframes"]


def test_try_normalize_signal_settings_returns_none_and_error_for_invalid_otf():
    """_try_normalize_signal_settings_for_hash returns (None, message) for invalid OTF."""
    settings = _base_signal_settings()
    settings["otf_filter"] = {"enabled": True, "timeframes": []}
    normalized, err = _try_normalize_signal_settings_for_hash(settings)
    assert normalized is None
    assert isinstance(err, str) and len(err) > 0


def test_try_normalize_signal_settings_returns_normalized_for_valid_settings():
    """_try_normalize_signal_settings_for_hash returns (normalized, None) for valid settings."""
    settings = _base_signal_settings()
    normalized, err = _try_normalize_signal_settings_for_hash(settings)
    assert normalized is not None
    assert err is None
    assert "otf_filter" in normalized


def test_try_normalize_does_not_produce_disabled_hash_for_invalid_otf():
    """Invalid OTF never normalizes at all — no fallback disabled hash is produced."""
    invalid = _base_signal_settings()
    invalid["otf_filter"] = {"enabled": True, "timeframes": []}
    normalized, err = _try_normalize_signal_settings_for_hash(invalid)
    assert normalized is None  # no hash-able state produced


def test_try_normalize_valid_legacy_settings_resolve_to_disabled():
    """Valid legacy settings (no otf_filter) normalize to disabled defaults."""
    settings = _base_signal_settings()
    normalized, err = _try_normalize_signal_settings_for_hash(settings)
    assert err is None
    assert normalized is not None
    assert normalized["otf_filter"]["enabled"] is False


def test_try_normalize_alias_and_canonical_enabled_produce_same_hash():
    """Alias timeframe labels and canonical labels produce the same normalized result."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    canonical = _base_signal_settings()
    canonical["otf_filter"] = {
        "enabled": True,
        "timeframes": ["15m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
        "directional": True,
        "use_completed_bars_only": True,
        "session_reset": "session",
    }
    alias = _base_signal_settings()
    alias["otf_filter"] = {**canonical["otf_filter"], "timeframes": ["15min"]}

    assert compute_signal_settings_hash(canonical) == compute_signal_settings_hash(alias)


# ---------------------------------------------------------------------------
# _resolve_loaded_signal_identity tests
# ---------------------------------------------------------------------------


def _valid_loaded_settings(**overrides) -> dict:
    settings = _base_signal_settings()
    settings.update(overrides)
    return settings


def test_resolve_loaded_identity_valid_settings_returns_trusted():
    """Valid settings with no persisted hash → trusted identity with recomputed hash."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    settings = _valid_loaded_settings()
    normalized, _ = _try_normalize_signal_settings_for_hash(settings)
    expected_hash = compute_signal_settings_hash(normalized)
    identity = _resolve_loaded_signal_identity(settings, None)
    assert identity["status"] == _IDENTITY_STATUS_TRUSTED
    assert identity["settings"] == normalized
    assert identity["hash"] == expected_hash
    assert identity["error"] is None


def test_resolve_loaded_identity_none_settings_returns_unavailable():
    """None loaded_settings → unavailable (no settings record)."""
    identity = _resolve_loaded_signal_identity(None, None)
    assert identity["status"] == _IDENTITY_STATUS_UNAVAILABLE
    assert identity["settings"] is None
    assert identity["hash"] is None
    assert isinstance(identity["error"], str)


def test_resolve_loaded_identity_non_dict_settings_returns_unavailable():
    """Non-dict loaded_settings → unavailable."""
    identity = _resolve_loaded_signal_identity("not-a-dict", None)
    assert identity["status"] == _IDENTITY_STATUS_UNAVAILABLE
    assert identity["settings"] is None


def test_resolve_loaded_identity_invalid_otf_returns_invalid():
    """Settings with invalid OTF → invalid identity."""
    settings = _valid_loaded_settings()
    settings["otf_filter"] = {"enabled": True, "timeframes": []}  # invalid
    identity = _resolve_loaded_signal_identity(settings, None)
    assert identity["status"] == _IDENTITY_STATUS_INVALID
    assert identity["settings"] is None
    assert identity["hash"] is None
    assert isinstance(identity["error"], str) and len(identity["error"]) > 0


def test_resolve_loaded_identity_matching_persisted_hash_returns_trusted():
    """Settings with persisted hash that matches recomputed → trusted; settings normalized."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    settings = _valid_loaded_settings()
    normalized, _ = _try_normalize_signal_settings_for_hash(settings)
    good_hash = compute_signal_settings_hash(normalized)
    identity = _resolve_loaded_signal_identity(settings, good_hash)
    assert identity["status"] == _IDENTITY_STATUS_TRUSTED
    assert identity["hash"] == good_hash
    assert identity["settings"] == normalized


def test_resolve_loaded_identity_mismatched_persisted_hash_returns_invalid():
    """Settings with persisted hash that does NOT match recomputed → invalid."""
    settings = _valid_loaded_settings()
    identity = _resolve_loaded_signal_identity(settings, "definitely-wrong-hash-value")
    assert identity["status"] == _IDENTITY_STATUS_INVALID
    assert identity["settings"] is None
    assert identity["hash"] is None
    assert isinstance(identity["error"], str)


def test_resolve_loaded_identity_empty_persisted_hash_is_ignored():
    """Empty/blank persisted hash is treated as absent → trusted with recomputed hash."""
    settings = _valid_loaded_settings()
    identity = _resolve_loaded_signal_identity(settings, "")
    assert identity["status"] == _IDENTITY_STATUS_TRUSTED


def test_resolve_loaded_identity_never_returns_disabled_fallback_for_invalid_otf():
    """Invalid OTF → invalid, not a disabled-fallback trusted identity."""
    settings = _valid_loaded_settings()
    settings["otf_filter"] = {"enabled": True, "timeframes": []}
    identity = _resolve_loaded_signal_identity(settings, None)
    assert identity["status"] == _IDENTITY_STATUS_INVALID
    assert identity["hash"] is None  # no hash produced at all


def test_resolve_loaded_identity_missing_otf_produces_trusted_disabled_identity():
    """Settings without otf_filter → trusted with canonical disabled OTF hash."""
    settings = _valid_loaded_settings()
    settings.pop("otf_filter", None)
    identity = _resolve_loaded_signal_identity(settings, None)
    assert identity["status"] == _IDENTITY_STATUS_TRUSTED
    assert identity["settings"]["otf_filter"]["enabled"] is False


def test_resolve_loaded_identity_does_not_mutate_input():
    """_resolve_loaded_signal_identity must not mutate the caller's dict."""
    settings = _valid_loaded_settings()
    original_copy = dict(settings)
    _resolve_loaded_signal_identity(settings, None)
    assert settings == original_copy


# ---------------------------------------------------------------------------
# _validate_signal_artifact_identity_for_save tests
# ---------------------------------------------------------------------------


def _trusted_session_state(settings_override=None) -> dict:
    """Return a session state dict representing a trusted artifact."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    settings = settings_override if settings_override is not None else _valid_loaded_settings()
    normalized, _ = _try_normalize_signal_settings_for_hash(settings)
    trusted_hash = compute_signal_settings_hash(normalized)
    return {
        _SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY: _IDENTITY_STATUS_TRUSTED,
        "signal_settings": normalized,
        "signal_settings_hash": trusted_hash,
    }


def test_validate_save_trusted_identity_matching_controls_can_save():
    """Trusted artifacts with matching current controls → can save."""
    ss = _trusted_session_state()
    current = _valid_loaded_settings()
    can_save, err = _validate_signal_artifact_identity_for_save(ss, current)
    assert can_save is True
    assert err is None


def test_validate_save_invalid_status_blocks_save():
    """Invalid identity status → blocked with artifact blocker message."""
    ss = _trusted_session_state()
    ss[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = _IDENTITY_STATUS_INVALID
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_unavailable_status_blocks_save():
    """Unavailable identity status → blocked."""
    ss = _trusted_session_state()
    ss[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = _IDENTITY_STATUS_UNAVAILABLE
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_missing_status_blocks_save():
    """No identity status key in session state → blocked."""
    ss = _trusted_session_state()
    del ss[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY]
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_missing_stored_settings_blocks_save():
    """Trusted status but stored signal_settings missing → blocked."""
    ss = _trusted_session_state()
    del ss["signal_settings"]
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_missing_stored_hash_blocks_save():
    """Trusted status but stored signal_settings_hash missing → blocked."""
    ss = _trusted_session_state()
    del ss["signal_settings_hash"]
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_stored_hash_mismatch_blocks_save():
    """Trusted status but stored hash does not match recomputed hash → blocked."""
    ss = _trusted_session_state()
    ss["signal_settings_hash"] = "tampered-hash-value"
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_none_current_settings_blocks_save():
    """Trusted artifacts but current_settings is None (invalid OTF) → blocked."""
    ss = _trusted_session_state()
    can_save, err = _validate_signal_artifact_identity_for_save(ss, None)
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_view_warning_surfaces_controls_changed_when_signals_drifted():
    """QI-03-12 / D-2: leftover candidates show the save-path warning on view."""
    ss = _trusted_session_state()
    ss["signals"] = pd.DataFrame({"signal_id": [1]})
    stored_trigger = ss["signal_settings"].get("trigger", "touch")
    different_settings = _valid_loaded_settings()
    different_settings["trigger"] = "reject" if stored_trigger == "touch" else "touch"
    assert (
        _controls_changed_warning_for_view(ss, different_settings)
        == _SIGNAL_CONTROLS_CHANGED_WARNING
    )
    assert _controls_changed_warning_for_view(ss, _valid_loaded_settings()) is None
    ss.pop("signals")
    assert _controls_changed_warning_for_view(ss, different_settings) is None


def test_view_warning_fail_closed_when_leftover_identity_missing():
    """Leftover signals with no hash / no current controls must not stay unflagged."""
    ss = _trusted_session_state()
    ss["signals"] = pd.DataFrame({"signal_id": [1]})
    ss.pop("signal_settings_hash")
    assert (
        _controls_changed_warning_for_view(ss, _valid_loaded_settings())
        == _SIGNAL_CONTROLS_CHANGED_WARNING
    )
    ss = _trusted_session_state()
    ss["signals"] = pd.DataFrame({"signal_id": [1]})
    assert _controls_changed_warning_for_view(ss, None) == _SIGNAL_CONTROLS_CHANGED_WARNING


def test_qi0312_view_warning_bound_on_signals_page():
    """AST-bind view warning on page body before Save buttons. Comment needles fail-closed."""
    import ast
    import pathlib

    source = pathlib.Path("pages/6_Signals.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    warning_assign = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_view_controls_warning"
            for target in node.targets
        ):
            continue
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "_controls_changed_warning_for_view"
        ):
            warning_assign = node
            break
    if warning_assign is None:
        raise AssertionError(
            "page 6 must assign _controls_changed_warning_for_view on the page body"
        )

    warned = False
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Name):
            continue
        if node.test.id != "_view_controls_warning":
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "warning"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "st"
            ):
                warned = True
    assert warned, "page 6 must st.warning the view-helper result"

    def _button_label(call: ast.AST) -> str | None:
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            return None
        if call.func.attr != "button" or not call.args:
            return None
        arg0 = call.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            return arg0.value
        return None

    copy_bound = False
    save_linenos: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
            continue
        label = _button_label(node.test)
        if label == "Save current signals":
            save_linenos.append(node.lineno)
        if label == "Copy setup to Setup Builder":
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "pop_setup_mutation_signal_keys"
                ):
                    copy_bound = True
    assert copy_bound, "Copy setup to Setup Builder must pop setup-mutation signal keys"
    assert save_linenos, "missing Save current signals button"
    assert warning_assign.lineno < min(save_linenos), (
        "view warning must render before Save current signals"
    )


def test_validate_save_controls_drift_returns_controls_changed_message():
    """Trusted artifacts but current controls differ → blocked with controls-changed message."""
    ss = _trusted_session_state()
    # The stored settings use trigger="touch" (default in _valid_loaded_settings).
    # Use a different trigger so the hash differs from the stored hash.
    stored_trigger = ss["signal_settings"].get("trigger", "touch")
    different_settings = _valid_loaded_settings()
    different_settings["trigger"] = "reject" if stored_trigger == "touch" else "touch"
    can_save, err = _validate_signal_artifact_identity_for_save(ss, different_settings)
    assert can_save is False
    assert err == _SIGNAL_CONTROLS_CHANGED_WARNING


def test_validate_save_invalid_stored_otf_blocks_save():
    """Stored settings with invalid OTF config (can't normalize) → blocked."""
    ss = _trusted_session_state()
    # Enabled OTF with no timeframes is invalid — verify normalization rejects it.
    settings_with_invalid_otf = {"otf_filter": {"enabled": True, "timeframes": []}}
    normalized, err = _try_normalize_signal_settings_for_hash(settings_with_invalid_otf)
    assert normalized is None, "Sanity: corrupted settings must be invalid"
    ss["signal_settings"] = settings_with_invalid_otf
    can_save, err = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert can_save is False
    assert err == _OTF_INVALID_ARTIFACT_BLOCKER


def test_validate_save_does_not_mutate_session_state():
    """_validate_signal_artifact_identity_for_save must not mutate session state."""
    ss = _trusted_session_state()
    original_keys = set(ss.keys())
    _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert set(ss.keys()) == original_keys


def test_validate_save_both_paths_use_same_helper():
    """Both save paths share the same eligibility contract (verified by testing the helper)."""
    # Valid trusted state → can save
    ss = _trusted_session_state()
    ok1, _ = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    ok2, _ = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert ok1 is True and ok2 is True

    # Invalid state → both fail identically
    ss[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = _IDENTITY_STATUS_INVALID
    fail1, msg1 = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    fail2, msg2 = _validate_signal_artifact_identity_for_save(ss, _valid_loaded_settings())
    assert fail1 is False and fail2 is False
    assert msg1 == msg2 == _OTF_INVALID_ARTIFACT_BLOCKER


# ---------------------------------------------------------------------------
# Regression: existing hash and normalization behavior unchanged
# ---------------------------------------------------------------------------


def test_regression_strict_compute_signal_settings_hash_still_raises_on_invalid_otf():
    """Existing strict behavior: invalid explicit OTF raises ValueError."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    settings = _base_signal_settings()
    settings["otf_filter"] = {"enabled": True, "timeframes": []}
    with pytest.raises(ValueError):
        compute_signal_settings_hash(settings)


def test_regression_missing_otf_still_hashes_as_disabled():
    """Existing behavior: missing otf_filter hashes as canonical disabled."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    missing = _base_signal_settings()
    missing.pop("otf_filter", None)
    disabled = _base_signal_settings()
    disabled["otf_filter"] = {
        "enabled": False,
        "timeframes": [],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
        "directional": True,
        "use_completed_bars_only": True,
        "session_reset": "session",
    }
    assert compute_signal_settings_hash(missing) == compute_signal_settings_hash(disabled)


def test_regression_valid_alias_and_canonical_still_equivalent():
    """Existing behavior: alias and canonical timeframe labels hash identically."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    base_otf = {
        "enabled": True,
        "timeframes": ["15m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
        "directional": True,
        "use_completed_bars_only": True,
        "session_reset": "session",
    }
    canonical = _base_signal_settings()
    canonical["otf_filter"] = base_otf
    alias = _base_signal_settings()
    alias["otf_filter"] = {**base_otf, "timeframes": ["15min"]}
    assert compute_signal_settings_hash(canonical) == compute_signal_settings_hash(alias)


def test_signals_page_has_no_stale_pre_pr5_otf_copy():
    import pathlib

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "6_Signals.py"
    text = page_path.read_text(encoding="utf-8")
    stale_snippets = (
        "metadata only in PR 4",
        "not filtered by OTF until PR 5",
        "until PR 5",
    )
    for snippet in stale_snippets:
        assert snippet not in text, f"Stale OTF copy still present: {snippet!r}"
    assert "complete candidate population" in text
    assert "OTF admission is applied later" in text


def test_c4_cai_signals_byte_identical_page6_bsc_vs_api(tmp_path):
    """CAI fixture: page-6 ``build_setup_config`` path == ``api.generate_signals``."""
    import hashlib

    from thesistester.api import compute_levels, generate_signals as api_generate_signals
    from thesistester.api import load_dataset
    from thesistester.config import INSTRUMENTS
    from thesistester.engine import (
        detect_confluence_zones,
        flag_naked_levels,
        generate_signals as engine_generate_signals,
    )
    from thesistester.setup import build_setup_config, build_setup_kwargs_from_mapping
    from tests.fixtures.cai_baseline import cai_run_spec, write_cai_bars

    bars = write_cai_bars(tmp_path / "cai.csv", kind="small")
    spec = cai_run_spec(dataset_path=str(bars), kind="small")
    data = load_dataset(
        bars,
        instrument=spec["dataset"]["instrument"],
        source_timezone=spec["dataset"]["source_timezone"],
        exchange_timezone=spec["dataset"]["exchange_timezone"],
        format_profile=spec["dataset"]["format_profile"],
    )
    levels = compute_levels(data, instrument=spec["dataset"]["instrument"], config=spec["levels"])[
        "levels"
    ]
    kwargs = build_setup_kwargs_from_mapping(spec["setup"])
    page_setup = _generate_setup_from_page_fields(**kwargs)
    so_t = build_setup_config(**kwargs)
    assert page_setup == so_t

    tick_size = INSTRUMENTS[spec["dataset"]["instrument"]].tick_size
    api_result = api_generate_signals(levels, so_t, instrument=spec["dataset"]["instrument"])
    zones = detect_confluence_zones(
        levels,
        level_columns=list(page_setup["selected_levels"]),
        tick_size=tick_size,
        tolerance_ticks=float(page_setup["tolerance_ticks"]),
        min_confluences=int(page_setup["min_confluences"]),
        max_confluences=int(page_setup["max_confluences"]),
    )
    naked_flags = flag_naked_levels(
        levels,
        level_columns=list(page_setup["selected_levels"]),
        tick_size=tick_size,
        touch_tolerance_ticks=0,
    )
    trigger_params = dict(page_setup["trigger_params"])
    if page_setup["trigger"] == "3c":
        trigger_params["_source_mode"] = page_setup["confluence_mode"]
    page_signals = engine_generate_signals(
        levels,
        zones=zones,
        trigger=str(page_setup["trigger"]),
        direction=str(page_setup["direction"]),
        tick_size=tick_size,
        trigger_timeframe=str(page_setup["trigger_timeframe"]),
        trigger_params=trigger_params,
        naked_only=bool(page_setup["naked_only"]),
        naked_flags=naked_flags if page_setup["naked_only"] else None,
        naked_requirement=str(page_setup["naked_requirement"]),
    )
    page_signals = page_signals.copy()
    page_signals["setup_name"] = page_setup["name"]
    pd.testing.assert_frame_equal(api_result["signals"], page_signals, check_dtype=False)
    api_hash = hashlib.sha256(api_result["signals"].to_csv(index=False).encode()).hexdigest()
    page_hash = hashlib.sha256(page_signals.to_csv(index=False).encode()).hexdigest()
    assert api_hash == page_hash


# ---------------------------------------------------------------------------
# QI-03-05 / D-8 — typed generate/chart errors + unused-helper wiring
# ---------------------------------------------------------------------------


def test_typed_signals_error_message_includes_valueerror_text():
    generate_msg = _typed_signals_error_message(
        ValueError("trigger must be one of ['3c'], got 'nope'"),
        surface="generate",
    )
    assert "trigger must be one of" in generate_msg
    assert "traceback" not in generate_msg.lower()
    chart_msg = _typed_signals_error_message(
        ValueError("levels_df is missing required columns: close"),
        surface="chart",
    )
    assert "levels_df is missing required columns: close" in chart_msg
    assert "Signal tables above remain available." in chart_msg


def test_signal_generation_admission_errors_stay_typed():
    levels = pd.DataFrame({"timestamp": [], "close": [], "ONH": []})
    assert (
        _signal_generation_admission_error(
            confluence_mode="anchor_rules",
            selected_levels=[],
            anchor_level=None,
            confluence_rules=[],
            min_valid_confluences=1,
            levels_df=levels,
        )
        == "Anchor mode requires an anchor level."
    )
    assert (
        _signal_generation_admission_error(
            confluence_mode="anchor_rules",
            selected_levels=[],
            anchor_level="ONH",
            confluence_rules=[],
            min_valid_confluences=1,
            levels_df=levels,
        )
        == "Anchor mode requires at least one confluence rule."
    )
    missing = _signal_generation_admission_error(
        confluence_mode="anchor_rules",
        selected_levels=[],
        anchor_level="ONH",
        confluence_rules=[{"level": "MISSING"}],
        min_valid_confluences=0,
        levels_df=levels,
    )
    assert missing is not None
    assert "MISSING" in missing
    assert (
        _signal_generation_admission_error(
            confluence_mode="global_cluster",
            selected_levels=[],
            anchor_level=None,
            confluence_rules=[],
            min_valid_confluences=0,
            levels_df=levels,
        )
        == "Please select at least one level column."
    )
    assert (
        _signal_generation_admission_error(
            confluence_mode="global_cluster",
            selected_levels=["ONH"],
            anchor_level=None,
            confluence_rules=[],
            min_valid_confluences=0,
            levels_df=levels,
        )
        is None
    )


def _generation_kwargs(**overrides) -> dict:
    kwargs = {
        "levels_df": pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-06-02 09:30:00"]),
                "open": [4500.0],
                "high": [4501.0],
                "low": [4499.0],
                "close": [4500.0],
                "volume": [10.0],
                "ONH": [4500.0],
            }
        ),
        "tick_size": 0.25,
        "confluence_mode": "global_cluster",
        "selected_levels": ["ONH"],
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "tolerance_ticks": 4.0,
        "min_confluences": 1,
        "max_confluences": 2,
        "naked_only": False,
        "naked_requirement": "any",
        "trigger": "touch",
        "trigger_timeframe": "base",
        "direction": "both",
        "trigger_params": {},
        "use_saved_setup": False,
        "saved_setup": None,
        "signal_settings": None,
        "session_state": {},
    }
    kwargs.update(overrides)
    return kwargs


def test_run_signal_generation_admission_raises_typed_valueerror():
    state: dict = {}
    with pytest.raises(ValueError, match="Anchor mode requires an anchor level"):
        _run_signal_generation(
            **_generation_kwargs(
                levels_df=pd.DataFrame({"timestamp": [], "close": []}),
                confluence_mode="anchor_rules",
                selected_levels=[],
                session_state=state,
            )
        )
    assert state == {}


def test_run_signal_generation_engine_valueerror_is_atomic():
    """Typed generate refusal must not commit zones/flags beside stale signals."""
    state = {"signals": pd.DataFrame({"signal_id": [1]})}
    with pytest.raises(ValueError, match="trigger must be one of"):
        _run_signal_generation(**_generation_kwargs(trigger="not_a_trigger", session_state=state))
    assert list(state) == ["signals"]
    assert list(state["signals"]["signal_id"]) == [1]


def test_run_signal_generation_commits_session_on_success():
    from thesistester.persistence.local_store import compute_signal_settings_hash

    settings, _ = _try_normalize_signal_settings_for_hash(_valid_loaded_settings())
    state: dict = {}
    _run_signal_generation(**_generation_kwargs(signal_settings=settings, session_state=state))
    assert isinstance(state["confluence_zones"], pd.DataFrame)
    assert isinstance(state["naked_flags"], pd.DataFrame)
    assert isinstance(state["signals"], pd.DataFrame)
    assert state["signal_settings"] is settings
    assert state["signal_settings_hash"] == compute_signal_settings_hash(settings)
    assert state["signal_context"]["confluence_mode"] == "global_cluster"
    assert "last_signal_setup" not in state


def test_get_stored_signal_settings_reads_session_dict():
    ss = _trusted_session_state()
    stored, stored_hash = _get_stored_signal_settings(ss)
    assert stored == ss["signal_settings"]
    assert stored_hash == ss["signal_settings_hash"]
    assert _get_stored_signal_settings({}) == (None, None)


def test_get_stored_signal_settings_recomputes_hash_not_echo_stored():
    from thesistester.persistence.local_store import compute_signal_settings_hash

    ss = _trusted_session_state()
    expected = compute_signal_settings_hash(ss["signal_settings"])
    ss["signal_settings_hash"] = "tampered-hash-value"
    stored, helper_hash = _get_stored_signal_settings(ss)
    assert stored == ss["signal_settings"]
    assert helper_hash == expected
    assert helper_hash != "tampered-hash-value"
    assert _get_stored_signal_settings({"signal_settings": "bad"}) == (None, None)


def test_view_warning_fail_closed_when_stored_settings_unreadable():
    """Leftover signals whose stored settings cannot be normalized must be flagged."""
    from thesistester.persistence.local_store import compute_signal_settings_hash

    current = _valid_loaded_settings()
    normalized, _ = _try_normalize_signal_settings_for_hash(current)
    current_hash = compute_signal_settings_hash(normalized)
    ss = {
        "signals": pd.DataFrame({"signal_id": [1]}),
        "signal_settings": {"otf_filter": {"enabled": True, "timeframes": []}},
        "signal_settings_hash": current_hash,
    }
    assert _controls_changed_warning_for_view(ss, current) == _SIGNAL_CONTROLS_CHANGED_WARNING


def test_view_warning_fail_closed_when_stored_hash_does_not_match_settings():
    """Session hash matching current controls is not enough if stored settings differ."""
    ss = _trusted_session_state()
    ss["signals"] = pd.DataFrame({"signal_id": [1]})
    current = _valid_loaded_settings()
    current["trigger"] = "reject" if ss["signal_settings"].get("trigger") == "touch" else "touch"
    from thesistester.persistence.local_store import compute_signal_settings_hash

    current_norm, _ = _try_normalize_signal_settings_for_hash(current)
    ss["signal_settings_hash"] = compute_signal_settings_hash(current_norm)
    assert _controls_changed_warning_for_view(ss, current) == _SIGNAL_CONTROLS_CHANGED_WARNING


def test_render_signals_chart_maps_valueerror_without_raising():
    _render_signals_chart(
        levels_df=pd.DataFrame({"foo": [1]}),
        signals=None,
        selected_levels=[],
        confluence_zones=None,
        show_confluence_zones=False,
    )


def test_anchor_diagnostic_columns_drive_summary_contract():
    assert "anchor_level" in ANCHOR_DIAGNOSTIC_COLUMNS
    assert "rule_results" in ANCHOR_DIAGNOSTIC_COLUMNS
    assert "level_names" in ANCHOR_DIAGNOSTIC_COLUMNS


def test_page6_has_no_st_exception_and_splits_render_vs_sync():
    """QI-03-05 exit: 0 st.exception on page 6; generate blockers stay typed."""
    import ast
    from pathlib import Path

    source = Path("pages/6_Signals.py").read_text(encoding="utf-8")
    assert "st.exception(" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        names: list[str] = []
        if isinstance(node.type, ast.Name):
            names = [node.type.id]
        elif isinstance(node.type, ast.Tuple):
            names = [elt.id for elt in node.type.elts if isinstance(elt, ast.Name)]
        assert "Exception" not in names
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    assert "_run_signal_generation" in called
    assert "_render_signals_chart" in called
    assert "_typed_signals_error_message" in called
    assert "_get_stored_signal_settings" in called
    assert "_signal_generation_admission_error" in called


def _preview_frame(**extra: object) -> pd.DataFrame:
    base = {
        "signal_id": ["s1"],
        "timestamp": [pd.Timestamp("2026-06-02 09:31:00", tz=TZ)],
        "bar_index": [1],
        "trigger": ["touch"],
        "direction": ["long"],
    }
    base.update(extra)
    return pd.DataFrame(base)


def test_signal_table_display_cols_includes_htf_3c_when_non_null():
    """QI-03-11 / E-8: preview shows Decision T + tested price when present."""
    frame = _preview_frame(
        trigger_timestamp=[pd.Timestamp("2026-06-02 09:35:00", tz=TZ)],
        trigger_timeframe=["5min"],
        tested_level_price=[5200.125],
        approach_side=["above"],
    )
    cols = _signal_table_display_cols(frame)
    assert "trigger_timestamp" in cols
    assert "trigger_timeframe" in cols
    assert "tested_level_price" in cols
    assert "approach_side" not in cols
    assert cols.index("timestamp") < cols.index("trigger_timestamp")


def test_signal_table_display_cols_omits_all_null_htf_3c_columns():
    frame = _preview_frame(
        trigger_timestamp=[pd.NaT],
        trigger_timeframe=[None],
        tested_level_price=[float("nan")],
    )
    cols = _signal_table_display_cols(frame)
    assert "trigger_timestamp" not in cols
    assert "trigger_timeframe" not in cols
    assert "tested_level_price" not in cols


def test_signal_table_display_cols_omits_absent_htf_3c_columns():
    cols = _signal_table_display_cols(_preview_frame())
    assert "trigger_timestamp" not in cols
    assert "trigger_timeframe" not in cols
    assert "tested_level_price" not in cols
    assert "approach_side" not in cols
    assert "signal_id" in cols
    assert "timestamp" in cols


def test_signal_table_display_cols_does_not_mutate_engine_signal_columns():
    """E-8 exit: `_SIGNAL_COLUMNS` stays the engine contract (DA4)."""
    from thesistester.engine.signals import _SIGNAL_COLUMNS

    before = list(_SIGNAL_COLUMNS)
    _signal_table_display_cols(
        _preview_frame(
            trigger_timestamp=[pd.Timestamp("2026-06-02 09:35:00", tz=TZ)],
            approach_side=["above"],
        )
    )
    assert list(_SIGNAL_COLUMNS) == before
    assert "approach_side" not in _SIGNAL_COLUMNS
    assert "trigger_timestamp" in _SIGNAL_COLUMNS
    assert "trigger_timeframe" in _SIGNAL_COLUMNS
    assert "tested_level_price" in _SIGNAL_COLUMNS


def test_page6_signal_table_uses_display_cols_helper():
    from pathlib import Path

    source = Path("pages/6_Signals.py").read_text(encoding="utf-8")
    assert "display_cols = _signal_table_display_cols(signals)" in source
    assert "_SIGNAL_TABLE_OPTIONAL_HTF_3C_COLS" in source
