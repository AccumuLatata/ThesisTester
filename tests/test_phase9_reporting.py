"""Phase 9 tests: reporting/export helpers and artifact rendering."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from thesistester.reporting import (
    build_markdown_report,
    build_research_artifact,
    dataframe_to_csv_bytes,
    dataframe_to_json_records,
    to_jsonable,
)


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

    for key in ("metadata", "configuration", "results", "tables", "caveats"):
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
