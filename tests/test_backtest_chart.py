from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from thesistester.visualization import build_backtest_candlestick_chart


TZ = "America/New_York"


def _ohlcv_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000.0,
                "session": "RTH",
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "open": 100.5,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1100.0,
                "session": "RTH",
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ),
                "open": 101.5,
                "high": 102.5,
                "low": 101.0,
                "close": 102.0,
                "volume": 1200.0,
                "session": "RTH",
            },
        ]
    )


def _trades_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "entry_timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "entry_price": 100.5,
                "exit_timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ),
                "exit_price": 101.5,
                "direction": "long",
                "stop_price": 99.5,
                "target_price": 101.5,
                "zone_low": 100.0,
                "zone_high": 101.0,
                "level_names": "A|B",
            },
            {
                "entry_timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ),
                "entry_price": 101.5,
                "exit_timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ),
                "exit_price": 100.5,
                "direction": "short",
                "stop_price": 102.5,
                "target_price": 100.5,
                "zone_low": 101.0,
                "zone_high": 102.0,
                "level_names": "C|D",
            },
        ]
    )


def _levels_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ), "A": 100.0, "B": 99.5},
            {"timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ), "A": 100.5, "B": 100.0},
            {"timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ), "A": 101.0, "B": 100.5},
        ]
    )


def _confluence_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "zone_low": 100.0,
                "zone_high": 101.0,
                "level_names": "A|B",
            }
        ]
    )


def test_valid_ohlcv_creates_one_candlestick_trace():
    fig = build_backtest_candlestick_chart(_ohlcv_df(), pd.DataFrame(), show_sessions=False)

    assert len(fig.data) == 1
    assert fig.data[0].type == "candlestick"
    assert fig.data[0].name == "OHLC"


def test_empty_trades_do_not_fail():
    fig = build_backtest_candlestick_chart(_ohlcv_df(), pd.DataFrame(), show_sessions=False)

    assert len(fig.data) == 1


def test_long_and_short_entries_create_marker_traces():
    fig = build_backtest_candlestick_chart(_ohlcv_df(), _trades_df(), show_sessions=False)

    traces = {trace.name: trace for trace in fig.data}
    assert traces["Long entries"].marker.symbol == "triangle-up"
    assert traces["Short entries"].marker.symbol == "triangle-down"


def test_stop_and_target_lines_are_added_as_shapes():
    fig = build_backtest_candlestick_chart(_ohlcv_df(), _trades_df().iloc[:1], show_sessions=False)

    assert len(fig.layout.shapes) == 2
    assert {shape.line.color for shape in fig.layout.shapes} == {"crimson", "seagreen"}


def test_missing_ohlc_columns_raise_value_error():
    ohlcv = _ohlcv_df().drop(columns=["close"])

    with pytest.raises(ValueError, match="close"):
        build_backtest_candlestick_chart(ohlcv, pd.DataFrame(), show_sessions=False)


def test_input_dataframes_are_not_mutated():
    ohlcv = _ohlcv_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    trades = _trades_df().assign(
        entry_timestamp=lambda df: df["entry_timestamp"].astype(str),
        exit_timestamp=lambda df: df["exit_timestamp"].astype(str),
    )
    levels = pd.DataFrame(
        [
            {"timestamp": "2026-01-02 09:30:00-05:00", "A": 100.0},
            {"timestamp": "2026-01-02 09:31:00-05:00", "A": 100.5},
        ]
    )
    confluence_zones = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02 09:30:00-05:00",
                "zone_low": 100.0,
                "zone_high": 101.0,
                "level_names": "A|B",
            }
        ]
    )

    ohlcv_before = ohlcv.copy(deep=True)
    trades_before = trades.copy(deep=True)
    levels_before = levels.copy(deep=True)
    zones_before = confluence_zones.copy(deep=True)

    build_backtest_candlestick_chart(
        ohlcv,
        trades,
        levels=levels,
        confluence_zones=confluence_zones,
        show_sessions=False,
    )

    assert_frame_equal(ohlcv, ohlcv_before)
    assert_frame_equal(trades, trades_before)
    assert_frame_equal(levels, levels_before)
    assert_frame_equal(confluence_zones, zones_before)


def test_trade_linked_confluence_zones_are_preferred():
    confluence_zones = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                "zone_low": 100.0,
                "zone_high": 101.0,
                "level_names": "A|B",
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "zone_low": 105.0,
                "zone_high": 106.0,
                "level_names": "X|Y",
            },
        ]
    )

    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        _trades_df().iloc[:1],
        confluence_zones=confluence_zones,
        show_sessions=False,
    )

    zone_trace = next(trace for trace in fig.data if trace.name == "Confluence zones")
    assert len(zone_trace.x) == 3


def test_confluence_zones_are_capped_without_trade_links():
    confluence_zones = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ) + pd.Timedelta(minutes=index),
                "zone_low": 100.0 + index,
                "zone_high": 100.5 + index,
            }
            for index in range(30)
        ]
    )

    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        pd.DataFrame(),
        confluence_zones=confluence_zones,
        show_sessions=False,
    )

    zone_trace = next(trace for trace in fig.data if trace.name == "Confluence zones")
    assert len(zone_trace.x) == 72


def test_defaults_include_levels_confluence_and_sl_tp():
    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        _trades_df(),
        levels=_levels_df(),
        confluence_zones=_confluence_df(),
    )

    trace_names = [trace.name for trace in fig.data]
    assert trace_names[0] == "OHLC"
    assert "Long entries" in trace_names
    assert "Short entries" in trace_names
    assert "Exits" in trace_names
    assert any(name.startswith("Level: ") for name in trace_names)
    assert "Confluence zones" in trace_names
    assert fig.layout.shapes is not None
    assert any(shape.line.color == "crimson" for shape in fig.layout.shapes)
    assert any(shape.line.color == "seagreen" for shape in fig.layout.shapes)


def test_show_sessions_false_removes_session_shapes():
    fig = build_backtest_candlestick_chart(_ohlcv_df(), pd.DataFrame(), show_sessions=False)

    assert not fig.layout.shapes


def test_show_levels_false_removes_level_traces():
    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        _trades_df(),
        levels=_levels_df(),
        show_levels=False,
        show_sessions=False,
    )

    assert not any(trace.name.startswith("Level: ") for trace in fig.data)


def test_show_confluence_zones_false_removes_zone_trace():
    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        _trades_df(),
        confluence_zones=_confluence_df(),
        show_confluence_zones=False,
        show_sessions=False,
    )

    assert "Confluence zones" not in {trace.name for trace in fig.data}


def test_show_sl_tp_false_keeps_entries_and_exits_without_sl_tp_shapes():
    fig = build_backtest_candlestick_chart(
        _ohlcv_df(),
        _trades_df(),
        show_sl_tp=False,
        show_sessions=False,
    )

    trace_names = {trace.name for trace in fig.data}
    assert {"Long entries", "Short entries", "Exits"}.issubset(trace_names)
    assert not fig.layout.shapes
