"""Regression tests for trigger-timeframe handling across DST boundaries."""
from __future__ import annotations

import pandas as pd

from thesistester.engine.signals import _prepare_trigger_dataframe, generate_signals

TZ = "America/New_York"


def _dst_fallback_df() -> pd.DataFrame:
    timestamps = pd.date_range("2024-11-03 05:55", periods=20, freq="1min", tz="UTC").tz_convert(TZ)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 100.0,
        }
    )


def _zone_for_base_bar(df: pd.DataFrame, bar_index: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "bar_index": bar_index,
                "timestamp": df.loc[bar_index, "timestamp"],
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "L1",
                "level_prices": "100.0",
            }
        ]
    )


def test_generate_signals_non_base_trigger_timeframe_is_dst_safe():
    df = _dst_fallback_df()
    offset_seconds = {timestamp.utcoffset().total_seconds() for timestamp in df["timestamp"]}
    assert -4 * 60 * 60 in offset_seconds
    assert -5 * 60 * 60 in offset_seconds

    trigger_df = _prepare_trigger_dataframe(df, "5min")
    zones = _zone_for_base_bar(df, int(trigger_df.iloc[0]["base_end_bar_index"]))

    signals = generate_signals(
        df,
        zones=zones,
        trigger="touch",
        direction="both",
        tick_size=0.25,
        trigger_timeframe="5min",
    )

    assert isinstance(signals, pd.DataFrame)
    assert not signals.empty
    assert {"signal_id", "timestamp", "trigger_timestamp", "trigger_timeframe", "trigger", "direction"}.issubset(
        signals.columns
    )
    assert set(signals["trigger_timeframe"]) == {"5min"}


def test_generate_signals_base_trigger_timeframe_still_works_across_dst_fallback():
    df = _dst_fallback_df()
    zones = _zone_for_base_bar(df, 0)

    signals = generate_signals(
        df,
        zones=zones,
        trigger="touch",
        direction="both",
        tick_size=0.25,
        trigger_timeframe="base",
    )

    assert isinstance(signals, pd.DataFrame)
    assert not signals.empty
    assert set(signals["trigger_timeframe"]) == {"base"}
