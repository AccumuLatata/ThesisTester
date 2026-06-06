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


def _profile_period_df(day: str, prices: list[float], volumes: list[float]) -> pd.DataFrame:
    timestamps = pd.date_range(f"{day} 09:30:00", periods=len(prices), freq="1h", tz=TZ)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": volumes,
        }
    )


def _multi_period_profile_df() -> pd.DataFrame:
    return pd.concat(
        [
            _profile_period_df("2026-06-29", [100.0, 100.25, 100.75], [10.0, 30.0, 5.0]),
            _profile_period_df("2026-07-01", [101.0, 101.25, 101.75], [8.0, 25.0, 4.0]),
            _profile_period_df("2026-07-06", [102.0, 102.25, 102.75], [7.0, 20.0, 6.0]),
            _profile_period_df("2026-07-07", [103.0, 103.25], [9.0, 11.0]),
        ],
        ignore_index=True,
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


def test_sma_5min_no_lookahead_from_non_boundary_start():
    df = _base_df("2026-06-02 09:31:00", periods=12, freq="1min")
    out = compute_indicator_levels(
        df,
        sma_lengths=[1],
        ema_lengths=[],
        sma_timeframes=["5min"],
        vwap_windows=[],
    )

    pre_completion = out[out["timestamp"] < pd.Timestamp("2026-06-02 09:35:00", tz=TZ)]
    assert pre_completion["SMA_1_5min"].isna().all()

    first_non_null = out.loc[out["SMA_1_5min"].notna(), ["timestamp", "SMA_1_5min"]].iloc[0]
    assert first_non_null["timestamp"] == pd.Timestamp("2026-06-02 09:35:00", tz=TZ)
    assert first_non_null["SMA_1_5min"] == pytest.approx(
        df.loc[df["timestamp"] == pd.Timestamp("2026-06-02 09:34:00", tz=TZ), "close"].iloc[0]
    )


def test_sma_30min_no_lookahead_from_non_boundary_start():
    df = _base_df("2026-06-02 09:31:00", periods=40, freq="1min")
    out = compute_indicator_levels(
        df,
        sma_lengths=[1],
        ema_lengths=[],
        sma_timeframes=["30min"],
        vwap_windows=[],
    )

    pre_completion = out[out["timestamp"] < pd.Timestamp("2026-06-02 10:00:00", tz=TZ)]
    assert pre_completion["SMA_1_30min"].isna().all()

    first_non_null = out.loc[out["SMA_1_30min"].notna(), ["timestamp", "SMA_1_30min"]].iloc[0]
    assert first_non_null["timestamp"] == pd.Timestamp("2026-06-02 10:00:00", tz=TZ)
    assert first_non_null["SMA_1_30min"] == pytest.approx(
        df.loc[df["timestamp"] == pd.Timestamp("2026-06-02 09:59:00", tz=TZ), "close"].iloc[0]
    )


def test_ema_5min_no_lookahead_from_non_boundary_start():
    df = _base_df("2026-06-02 09:31:00", periods=12, freq="1min")
    out = compute_indicator_levels(
        df,
        sma_lengths=[],
        ema_lengths=[1],
        ema_timeframes=["5min"],
        vwap_windows=[],
    )

    pre_completion = out[out["timestamp"] < pd.Timestamp("2026-06-02 09:35:00", tz=TZ)]
    assert pre_completion["EMA_1_5min"].isna().all()

    first_non_null = out.loc[out["EMA_1_5min"].notna(), ["timestamp", "EMA_1_5min"]].iloc[0]
    assert first_non_null["timestamp"] == pd.Timestamp("2026-06-02 09:35:00", tz=TZ)
    assert first_non_null["EMA_1_5min"] == pytest.approx(
        df.loc[df["timestamp"] == pd.Timestamp("2026-06-02 09:34:00", tz=TZ), "close"].iloc[0]
    )


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


def test_indicator_levels_raise_on_unknown_timeframe_option():
    df = _base_df("2026-06-02 09:30:00", periods=20, freq="1min")
    with pytest.raises(ValueError, match="Unsupported SMA timeframe"):
        compute_indicator_levels(
            df,
            sma_lengths=[2],
            ema_lengths=[],
            sma_timeframes=["2min"],
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


def test_prior_day_profile_levels_use_trading_session_boundary():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-01 18:00:00",
                    "2026-06-02 09:30:00",
                    "2026-06-02 10:30:00",
                    "2026-06-02 18:00:00",
                    "2026-06-03 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [100.0, 101.0, 102.0, 200.0, 201.0],
            "high": [100.0, 101.0, 102.0, 200.0, 201.0],
            "low": [100.0, 101.0, 102.0, 200.0, 201.0],
            "close": [100.0, 101.0, 102.0, 200.0, 201.0],
            "volume": [10.0, 30.0, 5.0, 50.0, 10.0],
        }
    )
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    session2 = out[out["timestamp"] >= pd.Timestamp("2026-06-02 18:00:00", tz=TZ)]

    assert np.allclose(session2["pdPOC"].to_numpy(), [101.0, 101.0])
    assert np.allclose(session2["pdVAH"].to_numpy(), [101.0, 101.0])
    assert np.allclose(session2["pdVAL"].to_numpy(), [100.0, 100.0])


def test_prior_week_profile_levels_use_trading_session_week_boundary():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-05 09:30:00",
                    "2026-06-05 10:30:00",
                    "2026-06-05 11:30:00",
                    "2026-06-07 18:00:00",
                    "2026-06-08 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [100.0, 101.0, 102.0, 200.0, 201.0],
            "high": [100.0, 101.0, 102.0, 200.0, 201.0],
            "low": [100.0, 101.0, 102.0, 200.0, 201.0],
            "close": [100.0, 101.0, 102.0, 200.0, 201.0],
            "volume": [10.0, 30.0, 5.0, 50.0, 10.0],
        }
    )
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    new_week = out[out["timestamp"] >= pd.Timestamp("2026-06-07 18:00:00", tz=TZ)]

    assert np.allclose(new_week["pwPOC"].to_numpy(), [101.0, 101.0])
    assert np.allclose(new_week["pwVAH"].to_numpy(), [101.0, 101.0])
    assert np.allclose(new_week["pwVAL"].to_numpy(), [100.0, 100.0])


def test_prior_month_profile_levels_use_trading_session_month_boundary():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-30 09:30:00",
                    "2026-06-30 10:30:00",
                    "2026-06-30 11:30:00",
                    "2026-06-30 18:00:00",
                    "2026-07-01 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [100.0, 101.0, 102.0, 200.0, 201.0],
            "high": [100.0, 101.0, 102.0, 200.0, 201.0],
            "low": [100.0, 101.0, 102.0, 200.0, 201.0],
            "close": [100.0, 101.0, 102.0, 200.0, 201.0],
            "volume": [10.0, 30.0, 5.0, 50.0, 10.0],
        }
    )
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    new_month = out[out["timestamp"] >= pd.Timestamp("2026-06-30 18:00:00", tz=TZ)]

    assert np.allclose(new_month["pmPOC"].to_numpy(), [101.0, 101.0])
    assert np.allclose(new_month["pmVAH"].to_numpy(), [101.0, 101.0])
    assert np.allclose(new_month["pmVAL"].to_numpy(), [100.0, 100.0])


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


def test_prior_profile_aggregation_defaults_preserve_existing_behavior():
    df = _multi_period_profile_df()

    baseline = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"], value_area_pct=0.70)
    explicit_defaults = compute_profile_levels(
        df,
        instrument="ES",
        rolling_windows=["30min"],
        value_area_pct=0.70,
        prior_day_aggregation_ticks=1,
        prior_week_aggregation_ticks=1,
        prior_month_aggregation_ticks=1,
    )

    profile_columns = [
        "POC_rolling_30min",
        "pdVAH",
        "pdVAL",
        "pdPOC",
        "pwVAH",
        "pwVAL",
        "pwPOC",
        "pmVAH",
        "pmVAL",
        "pmPOC",
    ]
    pd.testing.assert_frame_equal(baseline[profile_columns], explicit_defaults[profile_columns])


def test_prior_day_aggregation_changes_only_prior_day_profile_levels():
    df = _multi_period_profile_df()

    baseline = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"], value_area_pct=0.70)
    changed = compute_profile_levels(
        df,
        instrument="ES",
        rolling_windows=["30min"],
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
    )

    july_7_mask = changed["timestamp"].dt.date == pd.Timestamp("2026-07-07").date()
    assert not np.allclose(
        baseline.loc[july_7_mask, ["pdVAH", "pdVAL", "pdPOC"]].to_numpy(),
        changed.loc[july_7_mask, ["pdVAH", "pdVAL", "pdPOC"]].to_numpy(),
        equal_nan=True,
    )
    pd.testing.assert_frame_equal(
        baseline[["pwVAH", "pwVAL", "pwPOC", "pmVAH", "pmVAL", "pmPOC"]],
        changed[["pwVAH", "pwVAL", "pwPOC", "pmVAH", "pmVAL", "pmPOC"]],
    )


@pytest.mark.parametrize(
    ("kwargs", "changed_prefix", "unchanged_columns"),
    [
        (
            {"prior_day_aggregation_ticks": 4},
            "pd",
            ["pwVAH", "pwVAL", "pwPOC", "pmVAH", "pmVAL", "pmPOC"],
        ),
        (
            {"prior_week_aggregation_ticks": 4},
            "pw",
            ["pdVAH", "pdVAL", "pdPOC", "pmVAH", "pmVAL", "pmPOC"],
        ),
        (
            {"prior_month_aggregation_ticks": 4},
            "pm",
            ["pdVAH", "pdVAL", "pdPOC", "pwVAH", "pwVAL", "pwPOC"],
        ),
    ],
)
def test_prior_profile_aggregation_settings_are_independent(kwargs, changed_prefix, unchanged_columns):
    df = _multi_period_profile_df()

    baseline = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"], value_area_pct=0.70)
    changed = compute_profile_levels(
        df,
        instrument="ES",
        rolling_windows=["30min"],
        value_area_pct=0.70,
        **kwargs,
    )

    changed_columns = [f"{changed_prefix}VAH", f"{changed_prefix}VAL", f"{changed_prefix}POC"]
    changed_mask = baseline[changed_columns].notna().all(axis=1)
    assert changed_mask.any()
    assert not np.allclose(
        baseline.loc[changed_mask, changed_columns].to_numpy(),
        changed.loc[changed_mask, changed_columns].to_numpy(),
        equal_nan=True,
    )
    pd.testing.assert_frame_equal(baseline[unchanged_columns], changed[unchanged_columns])


def test_rolling_poc_is_unaffected_by_prior_profile_aggregation_settings():
    df = _multi_period_profile_df()

    baseline = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"], value_area_pct=0.70)
    changed = compute_profile_levels(
        df,
        instrument="ES",
        rolling_windows=["30min"],
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=10,
        prior_month_aggregation_ticks=10,
    )

    pd.testing.assert_series_equal(baseline["POC_rolling_30min"], changed["POC_rolling_30min"])


@pytest.mark.parametrize(
    ("arg_name", "value"),
    [
        ("prior_day_aggregation_ticks", 0),
        ("prior_week_aggregation_ticks", -1),
        ("prior_month_aggregation_ticks", 1.5),
    ],
)
def test_prior_profile_aggregation_ticks_validate_positive_integers(arg_name, value):
    df = _base_df("2026-06-02 09:30:00", periods=4)

    with pytest.raises(ValueError, match="must be a positive integer"):
        compute_profile_levels(df, instrument="ES", **{arg_name: value})


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


def test_compute_all_levels_passes_prior_profile_aggregation_settings_through():
    df = tag_session(_multi_period_profile_df(), "ES")

    baseline = compute_all_levels(df, instrument="ES", poc_windows=["30min"], sma_lengths=[], ema_lengths=[], vwap_windows=[])
    changed = compute_all_levels(
        df,
        instrument="ES",
        poc_windows=["30min"],
        sma_lengths=[],
        ema_lengths=[],
        vwap_windows=[],
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=4,
        prior_month_aggregation_ticks=4,
    )

    assert not np.allclose(
        baseline[["pdPOC", "pwPOC", "pmPOC"]].to_numpy(),
        changed[["pdPOC", "pwPOC", "pmPOC"]].to_numpy(),
        equal_nan=True,
    )
    pd.testing.assert_series_equal(baseline["POC_rolling_30min"], changed["POC_rolling_30min"])
