import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_indicator_levels, compute_profile_levels


TZ = "America/New_York"


def _base_df(start: str, periods: int, freq: str = "1min") -> pd.DataFrame:
    """Build deterministic OHLCV test data.

    Parameters
    ----------
    start : str
        Start timestamp for the generated index.
    periods : int
        Number of bars to generate.
    freq : str, default "1min"
        Pandas frequency string for the bar spacing.
    """
    ts = pd.date_range(start=start, periods=periods, freq=freq, tz=TZ)
    vals = np.arange(periods, dtype=float) + 100.0
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": vals,
            "high": vals + 0.5,
            "low": vals - 0.5,
            "close": vals + 0.25,
            "volume": np.arange(periods, dtype=float) + 1.0,
        }
    )


def test_indicator_columns_exist_and_align():
    df = _base_df("2026-06-02 09:30:00", periods=6)
    out = compute_indicator_levels(df, sma_lengths=[2], ema_lengths=[3], vwap_windows=["15min"])

    assert list(out["timestamp"]) == list(df["timestamp"])
    assert "SMA_2" in out.columns
    assert "EMA_3" in out.columns
    assert "VWAP_rolling_15min" in out.columns


def test_indicator_levels_preserve_backward_compatible_names_without_timeframes():
    df = _base_df("2026-06-02 09:30:00", periods=8)
    out = compute_indicator_levels(df, sma_lengths=[2], ema_lengths=[3], vwap_windows=[])

    assert "SMA_2" in out.columns
    assert "EMA_3" in out.columns
    assert "SMA_2_1min" not in out.columns
    assert "EMA_3_1min" not in out.columns


def test_indicator_levels_create_sma_columns_for_selected_timeframes():
    df = _base_df("2026-06-02 09:30:00", periods=80)
    out = compute_indicator_levels(
        df,
        sma_lengths=[20],
        ema_lengths=[],
        sma_timeframes=["1min", "5min", "30min"],
        vwap_windows=[],
    )

    for col in ["SMA_20_1min", "SMA_20_5min", "SMA_20_30min"]:
        assert col in out.columns


def test_indicator_levels_create_ema_columns_for_selected_timeframes():
    df = _base_df("2026-06-02 09:30:00", periods=80)
    out = compute_indicator_levels(
        df,
        sma_lengths=[],
        ema_lengths=[20],
        ema_timeframes=["1min", "5min", "30min"],
        vwap_windows=[],
    )

    for col in ["EMA_20_1min", "EMA_20_5min", "EMA_20_30min"]:
        assert col in out.columns


def test_higher_timeframe_indicator_alignment_has_no_lookahead():
    df = _base_df("2026-06-02 09:30:00", periods=31, freq="1min")
    out = compute_indicator_levels(
        df,
        sma_lengths=[1],
        ema_lengths=[],
        sma_timeframes=["30min"],
        vwap_windows=[],
    )

    assert pd.isna(out.loc[out["timestamp"] == pd.Timestamp("2026-06-02 09:59:00", tz=TZ), "SMA_1_30min"]).all()
    value_at_close = out.loc[out["timestamp"] == pd.Timestamp("2026-06-02 10:00:00", tz=TZ), "SMA_1_30min"].iloc[0]
    assert value_at_close == pytest.approx(df.loc[df["timestamp"] == pd.Timestamp("2026-06-02 09:59:00", tz=TZ), "close"].iloc[0])


def test_indicator_levels_raise_on_unsupported_upsampling_request():
    df = _base_df("2026-06-02 09:30:00", periods=20, freq="5min")
    with pytest.raises(ValueError, match="Cannot compute 1min SMA from 5min source data"):
        compute_indicator_levels(
            df,
            sma_lengths=[2],
            ema_lengths=[],
            sma_timeframes=["1min"],
            vwap_windows=[],
        )


def test_rolling_vwap_correctness_on_small_dataset():
    ts = pd.date_range("2026-06-02 09:30:00", periods=4, freq="1min", tz=TZ)
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [10.0, 20.0, 30.0, 40.0],
            "high": [10.0, 20.0, 30.0, 40.0],
            "low": [10.0, 20.0, 30.0, 40.0],
            "close": [10.0, 20.0, 30.0, 40.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )
    out = compute_indicator_levels(df, sma_lengths=[], ema_lengths=[], vwap_windows=["3min"])
    expected = np.array([10.0, 15.0, 20.0, 30.0])
    assert np.allclose(out["VWAP_rolling_3min"].to_numpy(), expected)


def test_rolling_poc_correctness_on_simple_dataset():
    ts = pd.date_range("2026-06-02 09:00:00", periods=4, freq="10min", tz=TZ)
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0, 100.25, 100.0, 100.5],
            "high": [100.0, 100.25, 100.0, 100.5],
            "low": [100.0, 100.25, 100.0, 100.5],
            "close": [100.0, 100.25, 100.0, 100.5],
            "volume": [10.0, 5.0, 20.0, 1.0],
        }
    )
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    assert out["POC_rolling_30min"].iloc[-1] == 100.0


def test_prior_day_profile_levels_use_completed_prior_day_only():
    day1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:30:00", periods=3, freq="1h", tz=TZ),
            "open": [100.0, 100.25, 100.5],
            "high": [100.0, 100.25, 100.5],
            "low": [100.0, 100.25, 100.5],
            "close": [100.0, 100.25, 100.5],
            "volume": [10.0, 30.0, 5.0],
        }
    )
    day2 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-02 09:30:00", periods=2, freq="1h", tz=TZ),
            "open": [101.0, 101.25],
            "high": [101.0, 101.25],
            "low": [101.0, 101.25],
            "close": [101.0, 101.25],
            "volume": [8.0, 9.0],
        }
    )
    df = pd.concat([day1, day2], ignore_index=True)
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])

    first_day = out[out["timestamp"].dt.date == pd.Timestamp("2026-06-01").date()]
    second_day = out[out["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert first_day["pdPOC"].isna().all()
    assert np.allclose(second_day["pdPOC"].to_numpy(), [100.25, 100.25])


def test_value_area_returns_sensible_bounds_around_poc():
    day1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:30:00", periods=4, freq="1h", tz=TZ),
            "open": [99.75, 100.0, 100.25, 100.5],
            "high": [99.75, 100.0, 100.25, 100.5],
            "low": [99.75, 100.0, 100.25, 100.5],
            "close": [99.75, 100.0, 100.25, 100.5],
            "volume": [20.0, 40.0, 30.0, 10.0],
        }
    )
    day2 = _base_df("2026-06-02 09:30:00", periods=2, freq="1h")
    df = pd.concat([day1, day2], ignore_index=True)

    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"], value_area_pct=0.70)
    second_day = out[out["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert np.allclose(second_day["pdPOC"].to_numpy(), [100.0, 100.0])
    assert np.allclose(second_day["pdVAL"].to_numpy(), [100.0, 100.0])
    assert np.allclose(second_day["pdVAH"].to_numpy(), [100.25, 100.25])


def test_compute_all_levels_includes_session_indicator_and_profile_columns():
    df = tag_session(_base_df("2026-06-02 09:30:00", periods=20), "ES")
    out = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
    )

    for col in ["RTH_Open", "SMA_2", "EMA_2", "VWAP_rolling_15min", "POC_rolling_30min", "pdVAH", "pdPOC"]:
        assert col in out.columns
