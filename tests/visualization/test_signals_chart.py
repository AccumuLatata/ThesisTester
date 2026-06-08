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


def _levels_ohlc_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "open": 99.7,
                "high": 100.2,
                "low": 99.5,
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
                "open": 100.0,
                "high": 100.8,
                "low": 99.9,
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


def _zones_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00"),
                "zone_low": 99.7,
                "zone_high": 100.1,
                "zone_mid": 99.9,
                "level_count": 2,
                "level_names": "L1,L2",
            },
            {
                "timestamp": pd.Timestamp("2026-01-02 09:31:00"),
                "zone_low": 100.2,
                "zone_high": 100.6,
                "zone_mid": 100.4,
                "level_count": 3,
                "level_names": "L2,L3,L4",
            },
        ]
    )


def _trace_by_name(fig, name: str):
    return next(trace for trace in fig.data if trace.name == name)


def test_signals_chart_uses_candlestick_when_ohlc_available():
    fig = build_signals_chart(_levels_ohlc_df(), _signals_df(), ["L1"])

    assert fig.data[0].type == "candlestick"
    assert fig.data[0].name == "OHLC"


def test_signals_chart_falls_back_to_close_when_ohlc_unavailable():
    fig = build_signals_chart(_levels_df(), _signals_df(), ["L1"])

    assert fig.data[0].type == "scatter"
    assert fig.data[0].name == "close"


def test_signals_chart_use_candles_false_forces_close_line():
    fig = build_signals_chart(_levels_ohlc_df(), _signals_df(), ["L1"], use_candles=False)

    assert fig.data[0].type == "scatter"
    assert fig.data[0].name == "close"


def test_signals_chart_adds_close_selected_levels_and_signal_markers():
    fig = build_signals_chart(
        levels_df=_levels_df(),
        signals=_signals_df(),
        selected_levels=["L1", "L2", "L3", "L4", "L5", "L6"],
        use_candles=False,
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
    fig_none = build_signals_chart(_levels_df(), None, ["L1"], use_candles=False)
    fig_empty = build_signals_chart(_levels_df(), pd.DataFrame(), ["L1"], use_candles=False)

    assert [trace.name for trace in fig_none.data] == ["close", "L1"]
    assert [trace.name for trace in fig_empty.data] == ["close", "L1"]


def test_signals_chart_adds_single_confluence_zone_trace():
    fig = build_signals_chart(_levels_df(), _signals_df(), ["L1"], confluence_zones=_zones_df(), use_candles=False)

    zone_trace = _trace_by_name(fig, "Confluence zones")
    assert zone_trace.mode == "lines"
    assert list(zone_trace.x) == [
        pd.Timestamp("2026-01-02 09:30:00"),
        pd.Timestamp("2026-01-02 09:30:00"),
        None,
        pd.Timestamp("2026-01-02 09:31:00"),
        pd.Timestamp("2026-01-02 09:31:00"),
        None,
    ]
    assert list(zone_trace.y) == [99.7, 100.1, None, 100.2, 100.6, None]


def test_signals_chart_hides_confluence_zone_trace_when_disabled():
    fig = build_signals_chart(
        _levels_df(),
        _signals_df(),
        ["L1"],
        confluence_zones=_zones_df(),
        show_confluence_zones=False,
        use_candles=False,
    )

    assert "Confluence zones" not in [trace.name for trace in fig.data]


def test_signals_chart_rejects_invalid_confluence_zone_columns():
    zones = _zones_df().drop(columns=["zone_high"])

    try:
        build_signals_chart(_levels_df(), _signals_df(), ["L1"], confluence_zones=zones)
    except ValueError as exc:
        assert "confluence_zones is missing required columns: zone_high" == str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing confluence zone columns")


def test_signals_chart_sets_marker_hovertemplate_with_optional_fields():
    fig = build_signals_chart(_levels_df(), _signals_df(), ["L1"], use_candles=False)

    for name in ["long (candidate/filled)", "short (candidate/filled)", "long void", "short void"]:
        trace = _trace_by_name(fig, name)
        assert trace.hovertemplate == "%{text}<extra></extra>"
        assert trace.text is not None


def test_signals_chart_does_not_mutate_input_dataframes():
    levels_df = _levels_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    signals_df = _signals_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    zones_df = _zones_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    levels_before = levels_df.copy(deep=True)
    signals_before = signals_df.copy(deep=True)
    zones_before = zones_df.copy(deep=True)

    build_signals_chart(levels_df, signals_df, ["L1", "L2"], confluence_zones=zones_df)

    assert_frame_equal(levels_df, levels_before)
    assert_frame_equal(signals_df, signals_before)
    assert_frame_equal(zones_df, zones_before)
