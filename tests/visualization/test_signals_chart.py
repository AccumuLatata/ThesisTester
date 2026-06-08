from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from thesistester.visualization import build_signals_chart


def _levels_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "close": 100.0,
                "L1": 99.5,
                "L2": 99.8,
                "L3": 100.1,
                "L4": 100.4,
                "L5": 100.7,
                "L6": 101.0,
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00"),
                "close": 100.5,
                "L1": 100.0,
                "L2": 100.2,
                "L3": 100.4,
                "L4": 100.6,
                "L5": 100.8,
                "L6": 101.1,
            },
        ]
    )


def _signals_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "direction": "long",
                "status": "candidate",
                "entry_reference_price": 100.0,
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00"),
                "direction": "short",
                "status": "filled",
                "entry_reference_price": 100.5,
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00"),
                "direction": "long",
                "status": "void",
                "entry_reference_price": 99.8,
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "direction": "short",
                "status": "void",
                "entry_reference_price": 100.7,
            },
        ]
    )


def test_signals_chart_adds_close_selected_levels_and_signal_markers():
    fig = build_signals_chart(
        levels_df=_levels_df(),
        signals=_signals_df(),
        selected_levels=["L1", "L2", "L3", "L4", "L5", "L6"],
    )

    trace_names = [trace.name for trace in fig.data]
    assert "close" in trace_names
    assert trace_names.count("L1") == 1
    assert trace_names.count("L5") == 1
    assert "L6" not in trace_names
    assert "long (candidate/filled)" in trace_names
    assert "short (candidate/filled)" in trace_names
    assert "long void" in trace_names
    assert "short void" in trace_names


def test_signals_chart_handles_none_and_empty_signals():
    fig_none = build_signals_chart(_levels_df(), None, ["L1"])
    fig_empty = build_signals_chart(_levels_df(), pd.DataFrame(), ["L1"])

    assert [trace.name for trace in fig_none.data] == ["close", "L1"]
    assert [trace.name for trace in fig_empty.data] == ["close", "L1"]


def test_signals_chart_does_not_mutate_input_dataframes():
    levels_df = _levels_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    signals_df = _signals_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    levels_before = levels_df.copy(deep=True)
    signals_before = signals_df.copy(deep=True)

    build_signals_chart(levels_df, signals_df, ["L1", "L2"])

    assert_frame_equal(levels_df, levels_before)
    assert_frame_equal(signals_df, signals_before)
