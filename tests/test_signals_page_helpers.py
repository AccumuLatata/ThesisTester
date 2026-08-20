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
        "spinner",
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
        mod._normalize_3c_params,
        mod._safe_float,
        mod._safe_int,
        mod._safe_bool,
        mod._safe_dict,
        mod._safe_list,
        mod._normalize_signal_settings_for_hash,
        mod._try_normalize_signal_settings_for_hash,
        mod._resolve_loaded_signal_identity,
        mod._validate_signal_artifact_identity_for_save,
        mod._IDENTITY_STATUS_TRUSTED,
        mod._IDENTITY_STATUS_INVALID,
        mod._IDENTITY_STATUS_UNAVAILABLE,
        mod._SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY,
        mod._SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY,
        mod._OTF_INVALID_ARTIFACT_BLOCKER,
        mod._SIGNAL_CONTROLS_CHANGED_WARNING,
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
    _normalize_3c_params,
    _safe_float,
    _safe_int,
    _safe_bool,
    _safe_dict,
    _safe_list,
    _normalize_signal_settings_for_hash,
    _try_normalize_signal_settings_for_hash,
    _resolve_loaded_signal_identity,
    _validate_signal_artifact_identity_for_save,
    _IDENTITY_STATUS_TRUSTED,
    _IDENTITY_STATUS_INVALID,
    _IDENTITY_STATUS_UNAVAILABLE,
    _SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY,
    _SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY,
    _OTF_INVALID_ARTIFACT_BLOCKER,
    _SIGNAL_CONTROLS_CHANGED_WARNING,
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
# _normalize_3c_params — safe coercion tests
# ---------------------------------------------------------------------------


def test_normalize_3c_params_none_returns_defaults():
    result = _normalize_3c_params(None)
    assert result["entry_retrace_ticks"] == 4.0
    assert result["max_entry_wait_bars_after_reversal"] == 5
    assert result["arrival_tolerance_ticks"] == 0.0


def test_normalize_3c_params_non_dict_string_returns_defaults():
    result = _normalize_3c_params("bad")
    assert result["entry_retrace_ticks"] == 4.0
    assert result["max_entry_wait_bars_after_reversal"] == 5
    assert result["arrival_tolerance_ticks"] == 0.0


def test_normalize_3c_params_bad_entry_retrace_returns_default():
    result = _normalize_3c_params({"entry_retrace_ticks": "bad"})
    assert result["entry_retrace_ticks"] == 4.0
    assert result["max_entry_wait_bars_after_reversal"] == 5


def test_normalize_3c_params_bad_max_wait_bars_returns_default():
    result = _normalize_3c_params({"max_entry_wait_bars_after_reversal": "bad"})
    assert result["entry_retrace_ticks"] == 4.0
    assert result["max_entry_wait_bars_after_reversal"] == 5


def test_normalize_3c_params_valid_values_are_preserved():
    result = _normalize_3c_params(
        {"entry_retrace_ticks": 6.0, "max_entry_wait_bars_after_reversal": 10}
    )
    assert result["entry_retrace_ticks"] == 6.0
    assert result["max_entry_wait_bars_after_reversal"] == 10


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
