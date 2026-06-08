from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from thesistester.visualization import build_levels_chart


def _levels_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2026-01-02 09:30:00"), "close": 100.0, "L1": 99.5, "L2": 101.0},
            {"timestamp": pd.Timestamp("2026-01-02 09:31:00"), "close": 100.5, "L1": 100.0, "L2": 101.5},
        ]
    )


def _levels_ohlc_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "open": 99.8,
                "high": 100.3,
                "low": 99.4,
                "close": 100.0,
                "L1": 99.5,
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00"),
                "open": 100.0,
                "high": 100.7,
                "low": 99.9,
                "close": 100.5,
                "L1": 100.0,
            },
        ]
    )


def test_levels_chart_uses_candlestick_when_ohlc_available():
    fig = build_levels_chart(_levels_ohlc_df(), ["L1"])

    assert fig.data[0].type == "candlestick"
    assert fig.data[0].name == "OHLC"
    assert [trace.name for trace in fig.data[1:]] == ["L1"]


def test_levels_chart_falls_back_to_close_when_ohlc_unavailable():
    fig = build_levels_chart(_levels_df(), ["L1"])

    assert fig.data[0].type == "scatter"
    assert fig.data[0].name == "close"


def test_levels_chart_falls_back_to_close_when_ohlc_incomplete():
    levels_df = _levels_ohlc_df()
    levels_df.loc[0, "low"] = float("nan")

    fig = build_levels_chart(levels_df, ["L1"])

    assert fig.data[0].type == "scatter"
    assert fig.data[0].name == "close"


def test_levels_chart_use_candles_false_forces_close_line():
    fig = build_levels_chart(_levels_ohlc_df(), ["L1"], use_candles=False)

    assert fig.data[0].type == "scatter"
    assert fig.data[0].name == "close"


def test_levels_chart_adds_close_and_selected_level_traces():
    fig = build_levels_chart(_levels_df(), ["L1", "L2"], use_candles=False)

    assert [trace.name for trace in fig.data] == ["close", "L1", "L2"]


def test_levels_chart_ignores_missing_selected_levels():
    fig = build_levels_chart(_levels_df(), ["L1", "MISSING"], use_candles=False)

    assert [trace.name for trace in fig.data] == ["close", "L1"]


def test_levels_chart_does_not_mutate_input_dataframe():
    levels_df = _levels_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    before = levels_df.copy(deep=True)

    build_levels_chart(levels_df, ["L1"])

    assert_frame_equal(levels_df, before)
