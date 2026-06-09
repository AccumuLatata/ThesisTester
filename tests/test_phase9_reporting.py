"""Phase 9 tests: reporting/export helpers and artifact rendering."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from thesistester.data.loader import load_ohlcv
from thesistester.reporting import (
    build_markdown_report,
    build_execution_cost_assumptions,
    build_exposure_policy_assumptions,
    build_research_artifact,
    build_session_exit_policy_assumptions,
    dataframe_to_csv_bytes,
    dataframe_to_json_records,
    exposure_policy_assumptions_markdown,
    execution_cost_assumptions_markdown,
    session_exit_policy_assumptions_markdown,
    to_jsonable,
)
from thesistester.timezone_display import convert_dataframe_timestamps_for_display


def _sample_session_state() -> dict:
    signals = pd.DataFrame(
        {
            "signal_id": [1, 2],
            "timestamp": [
                pd.Timestamp("2026-06-01T13:30:00Z"),
                pd.Timestamp("2026-06-01T14:00:00Z"),
            ],
            "trigger": ["touch", "reject"],
        }
    )
    trades = pd.DataFrame(
        {
            "trade_id": [10, 11],
            "r_multiple": [1.0, -0.5],
            "entry_timestamp": [
                pd.Timestamp("2026-06-01T13:31:00Z"),
                pd.Timestamp("2026-06-01T14:01:00Z"),
            ],
        }
    )

    return {
        "instrument": "ES",
        "setup_config": {
            "name": "Phase9 setup",
            "selected_levels": ["ONH", "ONL"],
            "trigger": "touch",
            "direction": "both",
            "naked_only": False,
            "min_confluences": 2,
            "max_confluences": 4,
            "tolerance_ticks": 4.0,
        },
        "last_signal_setup": {"name": "Phase9 setup"},
        "signals": signals,
        "trades": trades,
        "trade_summary": {
            "trade_count": 2,
            "win_rate": 0.5,
            "avg_r": 0.25,
            "total_r": 0.5,
            "profit_factor": 2.0,
            "max_drawdown_r": 0.5,
        },
        "equity_curve": pd.DataFrame(
            {
                "trade_id": [10, 11],
                "exit_timestamp": [
                    pd.Timestamp("2026-06-01T13:40:00Z"),
                    pd.Timestamp("2026-06-01T14:10:00Z"),
                ],
                "cum_r": [1.0, 0.5],
            }
        ),
        "grid_results": pd.DataFrame(
            {
                "stop_loss_ticks": [4.0, 8.0],
                "take_profit_ticks": [8.0, 16.0],
                "expectancy_r": [0.2, 0.1],
            }
        ),
        "best_grid_result": {
            "stop_loss_ticks": 4.0,
            "take_profit_ticks": 8.0,
            "expectancy_r": 0.2,
        },
        "time_grouped_summary": pd.DataFrame(
            {
                "entry_hour_bucket": ["09:00", "10:00"],
                "trade_count": [1, 1],
                "avg_r": [1.0, -0.5],
            }
        ),
        "validation_summary": {
            "bootstrap": {
                "ci_lower": -0.1,
                "ci_upper": 0.6,
                "probability_positive": 0.77,
            },
            "permutation": {"p_value_positive": 0.08},
            "trade_count": {"status": "insufficient"},
            "grid_overfit": {"risk_level": "low"},
        },
        "data": pd.DataFrame({"x": [1, 2, 3]}),
        "levels": pd.DataFrame({"y": [4, 5, 6]}),
    }


def test_to_jsonable_handles_supported_types():
    df = pd.DataFrame({"a": [1], "ts": [pd.Timestamp("2026-06-01T00:00:00Z")]})
    series = pd.Series({"x": np.int64(5), "y": np.nan})
    nested = {
        "timestamp": pd.Timestamp("2026-06-01T12:00:00Z"),
        "numpy_scalar": np.float64(1.25),
        "nan": np.nan,
        "inf": float("inf"),
        "df": df,
        "series": series,
        "nested": [np.int64(2), {"k": pd.Timestamp("2026-06-01")}, np.array([1, 2])],
    }

    result = to_jsonable(nested)

    assert isinstance(result["timestamp"], str)
    assert result["numpy_scalar"] == 1.25
    assert result["nan"] is None
    assert result["inf"] is None
    assert isinstance(result["df"], list)
    assert isinstance(result["series"], dict)
    assert result["nested"][0] == 2
    assert isinstance(result["nested"][1]["k"], str)
    assert result["nested"][2] == [1, 2]


def test_to_jsonable_handles_pandas_missing_scalars():
    assert to_jsonable(pd.NA) is None
    assert to_jsonable(pd.NaT) is None


def test_dataframe_to_csv_bytes_returns_bytes_with_header():
    df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
    csv_bytes = dataframe_to_csv_bytes(df)

    assert isinstance(csv_bytes, bytes)
    assert b"col1,col2" in csv_bytes


def test_dataframe_to_json_records_serializes_timestamps():
    df = pd.DataFrame(
        {
            "id": [1],
            "timestamp": [pd.Timestamp("2026-06-01T10:00:00Z")],
        }
    )
    records = dataframe_to_json_records(df)

    assert isinstance(records, list)
    assert isinstance(records[0], dict)
    assert isinstance(records[0]["timestamp"], str)


def test_dataframe_helpers_handle_empty_dataframe_safely():
    df = pd.DataFrame(columns=["a", "b"])
    assert dataframe_to_csv_bytes(df) == b""
    assert dataframe_to_json_records(df) == []
    assert dataframe_to_csv_bytes(None) == b""
    assert dataframe_to_json_records(None) == []


def test_build_research_artifact_has_required_top_level_keys():
    artifact = build_research_artifact(_sample_session_state())

    for key in ("metadata", "timezone_contract", "configuration", "results", "tables", "caveats"):
        assert key in artifact


def test_build_research_artifact_handles_missing_keys_gracefully():
    artifact = build_research_artifact({})

    assert artifact["results"]["signal_count"] == 0
    assert artifact["results"]["trade_count"] == 0
    assert artifact["tables"]["signals"] == []
    assert artifact["tables"]["trades"] == []


def test_build_research_artifact_counts_match_signals_and_trades():
    artifact = build_research_artifact(_sample_session_state())

    assert artifact["results"]["signal_count"] == 2
    assert artifact["results"]["trade_count"] == 2
    assert len(artifact["tables"]["signals"]) == 2
    assert len(artifact["tables"]["trades"]) == 2


def test_build_research_artifact_excludes_raw_data_and_levels_tables():
    artifact = build_research_artifact(_sample_session_state())

    assert "data" not in artifact["tables"]
    assert "levels" not in artifact["tables"]
    assert "data" not in artifact
    assert "levels" not in artifact


def test_research_artifact_is_strict_json_serializable_with_missing_values():
    state = _sample_session_state()
    state["signals"] = pd.DataFrame(
        {
            "signal_id": [1],
            "timestamp": [pd.NaT],
            "notes": [pd.NA],
        }
    )

    artifact = build_research_artifact(state)

    payload = json.dumps(artifact, allow_nan=False)
    assert isinstance(payload, str)


def test_build_markdown_report_returns_string_and_required_sections():
    artifact = build_research_artifact(_sample_session_state())
    markdown = build_markdown_report(artifact)

    assert isinstance(markdown, str)
    assert "# ThesisTester Research Report" in markdown
    assert "## Setup Configuration" in markdown
    assert "## Backtest Summary" in markdown
    assert "## Validation Diagnostics" in markdown
    assert "## Caveats" in markdown


def test_build_markdown_report_handles_missing_sections_gracefully():
    markdown = build_markdown_report(
        {
            "metadata": {"generated_at": datetime.now(timezone.utc).isoformat()},
            "configuration": {},
            "results": {},
            "tables": {},
            "caveats": [],
        }
    )

    assert isinstance(markdown, str)
    assert "# ThesisTester Research Report" in markdown


def test_artifact_export_uses_display_timezone_for_timestamp_columns():
    trades = pd.DataFrame(
        {
            "trade_id": [1],
            "entry_timestamp": [pd.Timestamp("2026-06-02 09:30:00", tz="America/New_York")],
            "exit_timestamp": [pd.Timestamp("2026-06-02 09:45:00", tz="America/New_York")],
            "r_multiple": [1.0],
        }
    )
    state = {
        "exchange_timezone": "America/New_York",
        "source_timezone": "Europe/Berlin",
        "display_timezone": "Europe/Berlin",
        "trades": trades,
    }
    artifact = build_research_artifact(state)
    exported_entry = artifact["tables"]["trades"][0]["entry_timestamp"]
    exported_exit = artifact["tables"]["trades"][0]["exit_timestamp"]
    assert exported_entry.endswith("+02:00")
    assert exported_exit.endswith("+02:00")


def test_artifact_export_defaults_to_exchange_timezone_when_display_missing():
    trades = pd.DataFrame(
        {
            "trade_id": [1],
            "entry_timestamp": [pd.Timestamp("2026-06-02 09:30:00", tz="America/New_York")],
            "r_multiple": [1.0],
        }
    )
    artifact = build_research_artifact(
        {
            "exchange_timezone": "America/New_York",
            "source_timezone": "Europe/Berlin",
            "trades": trades,
        }
    )
    exported_entry = artifact["tables"]["trades"][0]["entry_timestamp"]
    assert exported_entry.endswith("-04:00")


def test_export_conversion_does_not_mutate_original_dataframe():
    original = pd.DataFrame(
        {
            "entry_timestamp": [pd.Timestamp("2026-06-02 09:30:00", tz="America/New_York")],
            "r_multiple": [1.0],
        }
    )
    before = original.copy(deep=True)
    converted, _ = convert_dataframe_timestamps_for_display(
        original,
        display_timezone="Europe/Berlin",
        canonical_timezone="America/New_York",
    )
    assert str(original["entry_timestamp"].iloc[0]) == str(before["entry_timestamp"].iloc[0])
    assert str(converted["entry_timestamp"].iloc[0]).endswith("+02:00")


def test_round_trip_timezone_semantics_for_naive_berlin_csv(tmp_path):
    path = tmp_path / "berlin_naive.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-06-02 15:30:00,1,2,0.5,1.5,10",
                "2026-06-02 15:31:00,1.5,2.5,1,2,20",
            ]
        )
    )
    canonical = load_ohlcv(
        path,
        source_tz="Europe/Berlin",
        target_tz="America/New_York",
    )
    round_trip, _ = convert_dataframe_timestamps_for_display(
        canonical,
        display_timezone="Europe/Berlin",
        canonical_timezone="America/New_York",
    )
    expected = pd.to_datetime(
        ["2026-06-02 15:30:00", "2026-06-02 15:31:00"]
    ).tz_localize("Europe/Berlin")
    pd.testing.assert_series_equal(
        round_trip["timestamp"].reset_index(drop=True),
        pd.Series(expected, name="timestamp"),
    )


def test_export_conversion_warns_and_keeps_ambiguous_naive_timestamps():
    df = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2026-10-25 02:30:00"]),
            "r_multiple": [1.0],
        }
    )
    converted, warnings = convert_dataframe_timestamps_for_display(
        df,
        display_timezone="America/New_York",
        canonical_timezone="Europe/Berlin",
    )
    assert any("ambiguous naive timestamps" in warning for warning in warnings)
    pd.testing.assert_series_equal(converted["entry_timestamp"], df["entry_timestamp"])


def test_export_conversion_warns_and_keeps_nonexistent_naive_timestamps():
    df = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2026-03-29 02:30:00"]),
            "r_multiple": [1.0],
        }
    )
    converted, warnings = convert_dataframe_timestamps_for_display(
        df,
        display_timezone="America/New_York",
        canonical_timezone="Europe/Berlin",
    )
    assert any("nonexistent naive timestamps" in warning for warning in warnings)
    pd.testing.assert_series_equal(converted["entry_timestamp"], df["entry_timestamp"])


def test_execution_cost_assumptions_backtest_only_costs():
    state = _sample_session_state()
    state["grid_results"] = pd.DataFrame()
    state["best_grid_result"] = {}
    state["backtest_execution_costs"] = {"commission_per_side": 1.25, "slippage_ticks": 1.0}

    artifact = build_research_artifact(state)
    assumptions = build_execution_cost_assumptions(state)
    if assumptions["backtest"]["available"] or assumptions["grid"]["available"]:
        artifact["execution_cost_assumptions"] = assumptions

    assert assumptions["backtest"]["available"] is True
    assert assumptions["backtest"]["commission_per_side"] == 1.25
    assert assumptions["backtest"]["slippage_ticks"] == 1.0
    assert assumptions["grid"]["available"] is False
    assert artifact["execution_cost_assumptions"]["backtest"]["available"] is True


def test_execution_cost_assumptions_grid_only_costs():
    state = _sample_session_state()
    state["trades"] = pd.DataFrame()
    state["trade_summary"] = {}
    state["grid_execution_costs"] = {"commission_per_side": 0.5, "slippage_ticks": 0.25}

    artifact = build_research_artifact(state)
    assumptions = build_execution_cost_assumptions(state)
    if assumptions["backtest"]["available"] or assumptions["grid"]["available"]:
        artifact["execution_cost_assumptions"] = assumptions

    assert assumptions["grid"]["available"] is True
    assert assumptions["grid"]["commission_per_side"] == 0.5
    assert assumptions["grid"]["slippage_ticks"] == 0.25
    assert assumptions["backtest"]["available"] is False
    assert artifact["execution_cost_assumptions"]["grid"]["available"] is True


def test_execution_cost_assumptions_preserves_distinct_backtest_and_grid_values():
    state = _sample_session_state()
    state["backtest_execution_costs"] = {"commission_per_side": 1.25, "slippage_ticks": 1.0}
    state["grid_execution_costs"] = {"commission_per_side": 0.5, "slippage_ticks": 0.25}

    artifact = build_research_artifact(state)
    assumptions = build_execution_cost_assumptions(state)
    if assumptions["backtest"]["available"] or assumptions["grid"]["available"]:
        artifact["execution_cost_assumptions"] = assumptions

    assert assumptions["backtest"]["available"] is True
    assert assumptions["grid"]["available"] is True
    assert assumptions["backtest"]["commission_per_side"] == 1.25
    assert assumptions["grid"]["commission_per_side"] == 0.5
    assert assumptions["backtest"]["slippage_ticks"] == 1.0
    assert assumptions["grid"]["slippage_ticks"] == 0.25
    assert artifact["execution_cost_assumptions"]["backtest"]["commission_per_side"] == 1.25
    assert artifact["execution_cost_assumptions"]["grid"]["commission_per_side"] == 0.5


def test_execution_cost_assumptions_ignores_stale_backtest_costs_without_results():
    state = _sample_session_state()
    state["trades"] = pd.DataFrame()
    state["trade_summary"] = {}
    state["backtest_execution_costs"] = {"commission_per_side": 1.25, "slippage_ticks": 1.0}

    artifact = build_research_artifact(state)
    assumptions = build_execution_cost_assumptions(state)
    if assumptions["backtest"]["available"] or assumptions["grid"]["available"]:
        artifact["execution_cost_assumptions"] = assumptions

    assert assumptions["backtest"]["available"] is False
    assert assumptions["backtest"]["commission_per_side"] is None
    assert assumptions["backtest"]["slippage_ticks"] is None
    assert "execution_cost_assumptions" not in artifact


def test_execution_cost_assumptions_markdown_has_scoped_headings_and_values():
    assumptions = {
        "backtest": {
            "available": True,
            "commission_per_side": 1.25,
            "slippage_ticks": 1.0,
            "metrics_basis": "net-of-cost",
        },
        "grid": {
            "available": True,
            "commission_per_side": 0.5,
            "slippage_ticks": 0.25,
            "metrics_basis": "net-of-cost",
        },
    }

    markdown = execution_cost_assumptions_markdown(assumptions)

    assert "## Execution Cost Assumptions" in markdown
    assert "### Backtest" in markdown
    assert "### Grid Search" in markdown
    assert "1.2500" in markdown
    assert "0.5000" in markdown


def test_session_exit_policy_assumptions_backtest_scope_exported():
    state = _sample_session_state()
    state["backtest_session_exit_policy"] = {
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "no_new_entries_after": "15:45",
    }
    assumptions = build_session_exit_policy_assumptions(state)
    assert assumptions["backtest"]["available"] is True
    assert assumptions["backtest"]["flat_by_session_close"] is True
    assert assumptions["backtest"]["session_close_time"] == "16:00"
    assert assumptions["backtest"]["session_timezone"] == "America/New_York"
    assert assumptions["backtest"]["no_new_entries_after"] == "15:45"


def test_session_exit_policy_assumptions_grid_scope_exported_separately():
    state = _sample_session_state()
    state["grid_session_exit_policy"] = {
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "no_new_entries_after": None,
    }
    assumptions = build_session_exit_policy_assumptions(state)
    assert assumptions["grid"]["available"] is True
    assert assumptions["grid"]["flat_by_session_close"] is True
    assert assumptions["grid"]["session_close_time"] == "16:00"
    assert assumptions["grid"]["session_timezone"] == "America/New_York"
    assert assumptions["grid"]["no_new_entries_after"] is None


def test_session_exit_policy_assumptions_ignores_stale_scope_without_results():
    state = _sample_session_state()
    state["trades"] = pd.DataFrame()
    state["trade_summary"] = {}
    state["backtest_session_exit_policy"] = {
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "no_new_entries_after": "15:45",
    }
    assumptions = build_session_exit_policy_assumptions(state)
    assert assumptions["backtest"]["available"] is False
    assert assumptions["backtest"]["session_close_time"] is None


def test_session_exit_policy_assumptions_markdown_has_scoped_headings():
    assumptions = {
        "backtest": {
            "available": True,
            "flat_by_session_close": True,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": "15:45",
        },
        "grid": {
            "available": True,
            "flat_by_session_close": False,
            "session_close_time": "16:00",
            "session_timezone": "America/New_York",
            "no_new_entries_after": None,
        },
    }
    markdown = session_exit_policy_assumptions_markdown(assumptions)
    assert "## Session Exit Policy Assumptions" in markdown
    assert "### Backtest" in markdown
    assert "### Grid Search" in markdown


def test_exposure_policy_assumptions_backtest_scope_exported():
    state = _sample_session_state()
    state["exposure_policy"] = {
        "exposure_policy": "single_position",
        "cooldown_bars_after_exit": 2,
    }
    state["skipped_signals"] = pd.DataFrame({"signal_id": [1, 2, 3]})
    assumptions = build_exposure_policy_assumptions(state)
    assert assumptions["backtest"]["available"] is True
    assert assumptions["backtest"]["exposure_policy"] == "single_position"
    assert assumptions["backtest"]["cooldown_bars_after_exit"] == 2
    assert assumptions["backtest"]["skipped_signal_count"] == 3


def test_exposure_policy_assumptions_grid_scope_exported():
    state = _sample_session_state()
    state["grid_exposure_policy"] = {
        "exposure_policy": "single_direction",
        "cooldown_bars_after_exit": 1,
    }
    assumptions = build_exposure_policy_assumptions(state)
    assert assumptions["grid"]["available"] is True
    assert assumptions["grid"]["exposure_policy"] == "single_direction"
    assert assumptions["grid"]["cooldown_bars_after_exit"] == 1


def test_exposure_policy_assumptions_ignores_stale_scope_without_results():
    state = _sample_session_state()
    state["trades"] = pd.DataFrame()
    state["trade_summary"] = {}
    state["exposure_policy"] = {
        "exposure_policy": "single_position",
        "cooldown_bars_after_exit": 2,
    }
    assumptions = build_exposure_policy_assumptions(state)
    assert assumptions["backtest"]["available"] is False
    assert assumptions["backtest"]["exposure_policy"] is None


def test_exposure_policy_assumptions_markdown_has_scoped_headings():
    assumptions = {
        "backtest": {
            "available": True,
            "exposure_policy": "single_position",
            "cooldown_bars_after_exit": 2,
            "skipped_signal_count": 14,
        },
        "grid": {
            "available": True,
            "exposure_policy": "single_position",
            "cooldown_bars_after_exit": 2,
        },
    }
    markdown = exposure_policy_assumptions_markdown(assumptions)
    assert "## Exposure Policy Assumptions" in markdown
    assert "### Backtest" in markdown
    assert "### Grid Search" in markdown
    assert "single_position" in markdown
