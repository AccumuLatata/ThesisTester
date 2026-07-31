from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from thesistester.engine.intrabar import resolve_ohlc_bar
from thesistester.engine.sim_core import BarData, resolve_trade_bar


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=2, freq="1min"),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
        }
    )


def test_bar_data_snapshots_ohlc_without_mutating_source():
    source = _bars()
    before = source.copy(deep=True)

    bars = BarData.from_frame(source)

    assert bars.at(1).open == 101.0
    assert bars.at(1).high == 103.0
    assert_frame_equal(source, before)


def test_serial_core_resolution_matches_legacy_ohlc_resolver():
    bars = BarData.from_frame(_bars())
    bar, actual = resolve_trade_bar(
        bars,
        bar_index=0,
        intrabar_model="sl_first",
        subtimeframe_context=None,
        stop_price=99.5,
        target_price=101.5,
        direction="long",
        entry_activation_price=None,
    )
    expected = resolve_ohlc_bar(
        open_price=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        stop_price=99.5,
        target_price=101.5,
        direction="long",
        model="sl_first",
        entry_price=None,
    )

    assert actual == expected
