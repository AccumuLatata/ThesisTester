from __future__ import annotations

import pandas as pd
import pandas.testing as pdt
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_pivot_levels


TZ = "America/New_York"


def _bars_from_highs_lows(
    highs: list[float],
    lows: list[float] | None = None,
    *,
    start: str | pd.Timestamp = "2026-06-02 09:30:00",
    freq: str = "1min",
) -> pd.DataFrame:
    if lows is None:
        lows = [high - 1.0 for high in highs]

    start_ts = pd.Timestamp(start)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize(TZ)
    else:
        start_ts = start_ts.tz_convert(TZ)

    ts = pd.date_range(start=start_ts, periods=len(highs), freq=freq)
    open_ = [(high + low) / 2.0 for high, low in zip(highs, lows)]
    close = [low + 0.25 for low in lows]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": [100.0] * len(highs),
        }
    )


def _minute_bars_from_bucket_highs(
    bucket_highs: list[float],
    *,
    bucket_minutes: int,
    start: str = "2026-06-02 09:30:00",
) -> pd.DataFrame:
    rows: list[dict] = []
    start_ts = pd.Timestamp(start, tz=TZ)
    for bucket_index, bucket_high in enumerate(bucket_highs):
        bucket_start = start_ts + pd.Timedelta(minutes=bucket_index * bucket_minutes)
        for minute in range(bucket_minutes):
            ts = bucket_start + pd.Timedelta(minutes=minute)
            rows.append(
                {
                    "timestamp": ts,
                    "open": bucket_high - 0.5,
                    "high": bucket_high,
                    "low": bucket_high - 1.0,
                    "close": bucket_high - 0.25,
                    "volume": 100.0,
                }
            )
    return pd.DataFrame(rows)


def test_compute_pivot_levels_disabled_is_true_noop_with_naive_timestamps():
    df = _bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0])
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)

    result = compute_pivot_levels(df, enabled=False)

    assert list(result.columns) == []
    assert len(result) == len(df)


def test_compute_all_levels_with_pivots_disabled_has_no_pivot_columns():
    df = tag_session(_bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 1.0]))

    out = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        pivots_enabled=False,
    )

    assert [col for col in out.columns if col.startswith("Pivot_")] == []


def test_compute_pivot_levels_defaults_to_all_supported_columns():
    df = _bars_from_highs_lows([1.0, 2.0, 5.0, 3.0, 2.0, 4.0, 3.0, 2.0])

    result = compute_pivot_levels(df, enabled=True, pivot_left=1, pivot_right=1)

    assert list(result.columns) == [
        "Pivot_1m_High",
        "Pivot_1m_Low",
        "Pivot_5m_High",
        "Pivot_5m_Low",
        "Pivot_30m_High",
        "Pivot_30m_Low",
        "Pivot_4h_High",
        "Pivot_4h_Low",
    ]


def test_native_1min_pivot_high_tracks_latest_confirmed_level():
    df = _bars_from_highs_lows(
        [1.0, 2.0, 5.0, 3.0, 2.0, 6.0, 4.0, 3.0, 2.0],
        [0.5, 1.0, 1.5, 1.0, 0.8, 1.2, 1.0, 0.9, 0.7],
    )

    result = compute_pivot_levels(df, enabled=True, pivot_timeframes=["1min"])

    expected = [float("nan")] * 5 + [5.0, 5.0, 5.0, 6.0]
    assert result["Pivot_1m_High"].tolist() == pytest.approx(expected, nan_ok=True)


def test_native_1min_pivot_low_respects_confirmation_delay():
    df = _bars_from_highs_lows(
        [5.0, 4.0, 3.0, 4.0, 5.0, 6.0, 5.0, 4.0],
        [5.0, 4.0, 1.0, 3.0, 4.0, 6.0, 5.0, 4.0],
    )

    result = compute_pivot_levels(df, enabled=True, pivot_timeframes=["1min"])

    expected = [float("nan")] * 5 + [1.0, 1.0, 1.0]
    assert result["Pivot_1m_Low"].tolist() == pytest.approx(expected, nan_ok=True)


def test_5min_pivot_from_1min_source_is_hidden_until_confirmation():
    df = _minute_bars_from_bucket_highs([10.0, 20.0, 15.0, 12.0, 11.0], bucket_minutes=5)

    result = compute_pivot_levels(
        df,
        enabled=True,
        pivot_timeframes=["5min"],
        pivot_left=1,
        pivot_right=1,
    )

    assert result["Pivot_5m_High"].iloc[:15].isna().all()
    assert result["Pivot_5m_High"].iloc[15:].eq(20.0).all()


def test_30min_pivot_from_1min_source_is_hidden_until_confirmation():
    df = _minute_bars_from_bucket_highs([10.0, 20.0, 30.0, 15.0, 12.0], bucket_minutes=30)

    result = compute_pivot_levels(
        df,
        enabled=True,
        pivot_timeframes=["30min"],
        pivot_left=1,
        pivot_right=1,
    )

    assert result["Pivot_30m_High"].iloc[:120].isna().all()
    assert result["Pivot_30m_High"].iloc[120:].eq(30.0).all()


@pytest.mark.parametrize("timeframe", [["2min"], ["1m"]])
def test_invalid_pivot_timeframe_raises_value_error(timeframe):
    df = _bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0])

    with pytest.raises(ValueError, match="Unsupported pivot timeframe"):
        compute_pivot_levels(df, enabled=True, pivot_timeframes=timeframe)


@pytest.mark.parametrize("pivot_left", [0, -1])
def test_invalid_pivot_left_raises_value_error(pivot_left):
    df = _bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0])

    with pytest.raises(ValueError, match="pivot_left must be a positive integer"):
        compute_pivot_levels(df, enabled=True, pivot_left=pivot_left)


@pytest.mark.parametrize("pivot_right", [0, -1])
def test_invalid_pivot_right_raises_value_error(pivot_right):
    df = _bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0])

    with pytest.raises(ValueError, match="pivot_right must be a positive integer"):
        compute_pivot_levels(df, enabled=True, pivot_right=pivot_right)


def test_cannot_compute_smaller_timeframe_than_source():
    df = _bars_from_highs_lows([1.0, 2.0, 3.0, 2.0, 1.0], freq="5min")

    with pytest.raises(ValueError, match="Cannot compute 1min pivots from 5min source data"):
        compute_pivot_levels(df, enabled=True, pivot_timeframes=["1min"])


def test_pivot_levels_are_point_in_time_safe_under_future_shock():
    base = _minute_bars_from_bucket_highs([10.0, 20.0, 15.0, 12.0, 11.0, 10.0], bucket_minutes=5)
    before = compute_pivot_levels(
        base,
        enabled=True,
        pivot_timeframes=["5min"],
        pivot_left=1,
        pivot_right=1,
    )
    cutoff = base["timestamp"].iloc[-1]

    shock = _bars_from_highs_lows(
        [999.0, 998.0, 997.0, 996.0, 995.0],
        [1.0, 1.0, 1.0, 1.0, 1.0],
        start=cutoff + pd.Timedelta(minutes=1),
    )
    extended = pd.concat([base, shock], ignore_index=True)
    after = compute_pivot_levels(
        extended,
        enabled=True,
        pivot_timeframes=["5min"],
        pivot_left=1,
        pivot_right=1,
    )

    pdt.assert_frame_equal(
        before.reset_index(drop=True),
        after.loc[after.index < len(base)].reset_index(drop=True),
        check_exact=False,
    )
