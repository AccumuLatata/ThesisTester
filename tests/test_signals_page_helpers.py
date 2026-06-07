"""Tests for pure helper functions extracted from pages/6_Signals.py.

We import the helpers by loading the module source directly so we avoid
triggering Streamlit runtime side-effects that occur at page import time.
"""
from __future__ import annotations

import importlib
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
        "title", "header", "subheader", "info", "warning", "error",
        "success", "caption", "stop", "spinner", "dataframe", "metric",
        "plotly_chart", "checkbox", "toggle", "radio", "selectbox",
        "multiselect", "number_input", "slider", "button",
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

    import importlib.util, pathlib
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
        {"level": "VWAP", "price": 4499.0, "tolerance_ticks": 4, "distance_ticks": 1.0,
         "required": True, "valid": True, "reason": "ok"},
        {"level": "pdLow", "price": 4495.0, "tolerance_ticks": 8, "distance_ticks": 20.0,
         "required": False, "valid": False, "reason": "too far"},
    ]
    df = _zones(rule_results=[json.dumps(rules)])
    result = _parse_anchor_rule_results(df)
    assert len(result) == 2
    assert list(result["rule_level"]) == ["VWAP", "pdLow"]


def test_parse_multiple_zones():
    rule = {"level": "VWAP", "price": 4500.0, "tolerance_ticks": 4, "distance_ticks": 1.0,
            "required": True, "valid": True, "reason": "ok"}
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
                json.dumps([{"level": "VWAP", "price": 4500.0, "tolerance_ticks": 4,
                             "distance_ticks": 1.0, "required": True, "valid": True, "reason": "ok"}]),
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
    rule = {"level": "VWAP", "price": 4500.0, "tolerance_ticks": 4, "distance_ticks": 1.0,
            "required": True, "valid": True, "reason": "ok"}
    df = _zones(rule_results=[json.dumps([rule])])
    result = _parse_anchor_rule_results(df)
    expected = {
        "zone_row", "timestamp", "bar_index", "anchor_level", "anchor_price",
        "rule_level", "rule_price", "distance_ticks", "tolerance_ticks",
        "required", "valid", "reason",
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
    assert caption == "Trigger=touch • Direction=both • Confluences=2–5 • Trigger TF=base"


def test_saved_setup_caption_anchor_mode():
    caption = _saved_setup_caption(
        {
            "confluence_mode": "anchor_rules",
            "anchor_level": "pdHigh",
            "confluence_rules": [{"level": "VWAP"}, {"level": "ONH"}],
            "min_valid_confluences": 2,
        }
    )
    assert caption == "Mode=anchor_rules • Anchor=pdHigh • Rules=2 • Min valid=2 • Trigger TF=base"


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
            "setup_config": {"confluence_mode": "global_cluster", "trigger": "touch", "direction": "both"},
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
        "and per-rule tolerances."
    )
