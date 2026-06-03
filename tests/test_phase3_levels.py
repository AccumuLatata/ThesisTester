import numpy as np
import pandas as pd

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_indicator_levels, compute_profile_levels


TZ = "America/New_York"


def _base_df(start: str, periods: int, freq: str = "1min") -> pd.DataFrame:
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
