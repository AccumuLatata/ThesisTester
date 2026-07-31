from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from thesistester.visualization import (
    build_trade_review_chart,
    export_worst_loser_review_pngs,
    selected_trade_time_window,
    select_worst_losers,
    trade_excursion_price_levels,
)


def _ohlcv() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-02 09:30", periods=25, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index * 0.1 for index in range(len(timestamps))],
            "high": [101.0 + index * 0.1 for index in range(len(timestamps))],
            "low": [99.0 + index * 0.1 for index in range(len(timestamps))],
            "close": [100.5 + index * 0.1 for index in range(len(timestamps))],
            "volume": [100.0] * len(timestamps),
            "session": ["RTH"] * len(timestamps),
        }
    )


def _trade(direction: str = "long") -> pd.Series:
    return pd.Series(
        {
            "trade_id": 7,
            "direction": direction,
            "entry_timestamp": pd.Timestamp("2026-01-02 09:40", tz="America/New_York"),
            "entry_price": 101.0,
            "exit_timestamp": pd.Timestamp("2026-01-02 09:45", tz="America/New_York"),
            "exit_price": 101.5,
            "stop_price": 99.0,
            "target_price": 103.0,
            "final_stop_price": 100.0,
            "mae_points": 0.75,
            "mfe_points": 1.25,
            "r_multiple": -1.5,
        }
    )


def test_selected_trade_window_is_bounded_by_requested_buffer():
    start, end = selected_trade_time_window(_trade(), ohlcv_df=_ohlcv(), buffer_rows=3)

    assert start == pd.Timestamp("2026-01-02 09:37")
    assert end == pd.Timestamp("2026-01-02 09:48")


def test_trade_excursion_levels_respect_direction():
    long_levels = trade_excursion_price_levels(_trade("long"))
    short_levels = trade_excursion_price_levels(_trade("short"))

    assert long_levels == {"entry_price": 101.0, "mae_price": 100.25, "mfe_price": 102.25}
    assert short_levels == {"entry_price": 101.0, "mae_price": 101.75, "mfe_price": 99.75}


def test_trade_review_figure_has_terminal_envelopes_and_single_trade_markers():
    ohlcv = _ohlcv()
    trade = _trade()
    ohlcv_before = ohlcv.copy(deep=True)
    trade_before = trade.copy(deep=True)

    figure = build_trade_review_chart(
        ohlcv,
        trade,
        show_sessions=False,
        show_final_stop=True,
    )

    assert {"OHLC", "Long entries", "Exits"} <= {trace.name for trace in figure.data}
    assert len(figure.layout.shapes) == 5
    assert {shape.type for shape in figure.layout.shapes} == {"line", "rect"}
    assert "Trade review #7" in figure.layout.title.text
    assert "candlestick" in figure.to_json()
    assert_frame_equal(ohlcv, ohlcv_before)
    pd.testing.assert_series_equal(trade, trade_before)


def test_worst_losers_are_stably_sorted_and_exclude_non_losses():
    trades = pd.DataFrame(
        [
            {"trade_id": 3, "r_multiple": -1.0},
            {"trade_id": 2, "r_multiple": -2.0},
            {"trade_id": 1, "r_multiple": -2.0},
            {"trade_id": 4, "r_multiple": 0.5},
        ]
    )

    selected = select_worst_losers(trades, count=3)

    assert selected["trade_id"].tolist() == [1, 2, 3]


def test_worst_loser_export_contains_bounded_pngs():
    pytest.importorskip("kaleido")
    second_loss = _trade()
    second_loss["trade_id"] = 8
    second_loss["r_multiple"] = -0.5
    losses = pd.DataFrame([_trade(), second_loss])

    export = export_worst_loser_review_pngs(
        losses,
        _ohlcv(),
        count=2,
        buffer_rows=3,
    )

    with zipfile.ZipFile(io.BytesIO(export)) as archive:
        assert archive.namelist() == ["trade_7_-1.50R.png", "trade_8_-0.50R.png"]
        assert all(archive.read(name).startswith(b"\x89PNG") for name in archive.namelist())
