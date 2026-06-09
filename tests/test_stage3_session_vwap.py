"""Stage 3 — dVWAP_RTH tests.

Covers:
- Disabled behavior (true no-op, no validation).
- Basic correctness (exact bar-by-bar cumulative VWAP values).
- Session reset across two RTH sessions.
- Outside-RTH bars emit NaN.
- Zero-volume behavior.
- Settings validation (unsupported anchor, unsupported instrument, naive timestamp).
- Regression safety (existing levels unchanged; no dVWAP_RTH without explicit enable).
- Point-in-time / future-shock test.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_session_vwap_levels


TZ = "America/New_York"


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _rth_bar(ts: pd.Timestamp, high: float, low: float, close: float, volume: float) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "RTH",
    }


def _eth_bar(ts: pd.Timestamp, high: float, low: float, close: float, volume: float) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "ETH",
    }


def _rth_fixture(
    n_bars: int = 5,
    *,
    session_date: str = "2026-06-02",
    rth_start: str = "09:30",
    freq: str = "1min",
) -> pd.DataFrame:
    """Synthetic RTH-only fixture with controlled OHLCV values."""
    start = pd.Timestamp(f"{session_date} {rth_start}", tz=TZ)
    rows = []
    for i in range(n_bars):
        ts = start + pd.Timedelta(minutes=i)
        h = float(100 + i)
        l = float(100 + i - 1)
        c = float(100 + i - 0.5)
        v = float(i + 1)  # volume 1, 2, 3, ...
        rows.append(_rth_bar(ts, h, l, c, v))
    return pd.DataFrame(rows)


def _two_session_fixture() -> pd.DataFrame:
    """Two RTH sessions separated by an ETH gap."""
    rows = []
    # Session 1: 2026-06-02 RTH 09:30 – 09:32 (3 bars)
    s1_start = pd.Timestamp("2026-06-02 09:30", tz=TZ)
    for i in range(3):
        ts = s1_start + pd.Timedelta(minutes=i)
        rows.append(_rth_bar(ts, 100.0 + i, 99.0 + i, 99.5 + i, 10.0))
    # Session 1 ETH close (after RTH)
    rows.append(_eth_bar(pd.Timestamp("2026-06-02 16:30", tz=TZ), 99.0, 98.0, 98.5, 5.0))
    # Session 2 ETH pre-open
    rows.append(_eth_bar(pd.Timestamp("2026-06-03 08:00", tz=TZ), 105.0, 104.0, 104.5, 5.0))
    # Session 2: 2026-06-03 RTH 09:30 – 09:31 (2 bars)
    s2_start = pd.Timestamp("2026-06-03 09:30", tz=TZ)
    for i in range(2):
        ts = s2_start + pd.Timedelta(minutes=i)
        rows.append(_rth_bar(ts, 200.0 + i, 199.0 + i, 199.5 + i, 20.0))
    return pd.DataFrame(rows)


def _naive_df() -> pd.DataFrame:
    df = _rth_fixture()
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return df


def _full_session_fixture() -> pd.DataFrame:
    """RTH + ETH bars for one calendar day."""
    rows = []
    # ETH pre-open
    for i in range(3):
        ts = pd.Timestamp("2026-06-02 08:00", tz=TZ) + pd.Timedelta(minutes=i * 30)
        rows.append(_eth_bar(ts, 99.0, 98.0, 98.5, 5.0))
    # RTH
    for i in range(4):
        ts = pd.Timestamp("2026-06-02 09:30", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_rth_bar(ts, 100.0 + i, 99.0 + i, 99.5 + i, 10.0 * (i + 1)))
    # ETH post-close
    for i in range(2):
        ts = pd.Timestamp("2026-06-02 16:30", tz=TZ) + pd.Timedelta(minutes=i * 30)
        rows.append(_eth_bar(ts, 103.0, 102.0, 102.5, 3.0))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Disabled behavior
# ---------------------------------------------------------------------------

def test_disabled_returns_empty_dataframe():
    df = _rth_fixture()
    result = compute_session_vwap_levels(df, enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == []
    assert len(result) == len(df)


def test_disabled_accepts_naive_timestamps():
    result = compute_session_vwap_levels(_naive_df(), enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == []


def test_compute_all_levels_session_vwap_disabled_produces_no_dvwap_column():
    df = tag_session(_rth_fixture(), "ES")
    out = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        session_vwap_enabled=False,
    )
    assert "dVWAP_RTH" not in out.columns


# ---------------------------------------------------------------------------
# 2. Basic correctness — bar-by-bar cumulative VWAP
# ---------------------------------------------------------------------------

def test_dvwap_rth_exact_values():
    """Verify exact cumulative VWAP computation bar by bar."""
    # Build 4 RTH bars with controlled values.
    rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), high=101.0, low=99.0,  close=100.0, volume=10.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:31", tz=TZ), high=102.0, low=100.0, close=101.0, volume=20.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:32", tz=TZ), high=103.0, low=101.0, close=102.0, volume=30.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:33", tz=TZ), high=104.0, low=102.0, close=103.0, volume=40.0),
    ]
    df = pd.DataFrame(rows)

    result = compute_session_vwap_levels(df, enabled=True)
    v = result["dVWAP_RTH"]

    # typical_price = (high + low + close) / 3
    tp = [(101 + 99 + 100) / 3, (102 + 100 + 101) / 3, (103 + 101 + 102) / 3, (104 + 102 + 103) / 3]
    vols = [10.0, 20.0, 30.0, 40.0]
    # cumulative VWAP
    expected = []
    cum_pv = 0.0
    cum_v = 0.0
    for t, vol in zip(tp, vols):
        cum_pv += t * vol
        cum_v += vol
        expected.append(cum_pv / cum_v)

    assert v.tolist() == pytest.approx(expected, rel=1e-9)


def test_dvwap_output_column_name_is_dvwap_rth():
    df = _rth_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    assert list(result.columns) == ["dVWAP_RTH"]


def test_dvwap_index_length_matches_input():
    df = _rth_fixture(n_bars=10)
    result = compute_session_vwap_levels(df, enabled=True)
    assert len(result) == len(df)


# ---------------------------------------------------------------------------
# 3. Session reset
# ---------------------------------------------------------------------------

def test_dvwap_resets_at_second_session():
    """dVWAP_RTH must reset at each new RTH session open."""
    df = _two_session_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    v = result["dVWAP_RTH"]

    rth_mask = df["session"].eq("RTH")
    rth_vals = v[rth_mask].values

    # Session 1 bars (indices 0-2) and Session 2 bars (indices -2, -1 in rth_vals)
    # The first bar of session 2 should equal its own single-bar VWAP.
    # Build expected session-2 first-bar VWAP
    s2_first = df[rth_mask].iloc[3]  # 4th RTH bar = first of session 2
    tp_s2_first = (s2_first["high"] + s2_first["low"] + s2_first["close"]) / 3.0
    assert rth_vals[3] == pytest.approx(tp_s2_first, rel=1e-9)


def test_dvwap_session1_last_value_does_not_carry_to_session2():
    """Session 2 starting value must NOT include session 1 bars."""
    df = _two_session_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    v = result["dVWAP_RTH"]

    rth = df["session"].eq("RTH")
    rth_vals = v[rth].values
    # Session 1 has 3 bars; session 2 first bar is rth_vals[3].
    # The first bar of session 2 VWAP uses only that bar's typical price.
    s2_first_row = df[rth].iloc[3]
    expected_s2_vwap_bar0 = (s2_first_row["high"] + s2_first_row["low"] + s2_first_row["close"]) / 3.0
    # Session 1 last VWAP is definitely different (lower prices).
    assert rth_vals[3] != pytest.approx(rth_vals[2], rel=1e-3)
    assert rth_vals[3] == pytest.approx(expected_s2_vwap_bar0, rel=1e-9)


# ---------------------------------------------------------------------------
# 4. Outside-RTH behavior (NaN outside RTH)
# ---------------------------------------------------------------------------

def test_eth_bars_before_rth_emit_nan():
    df = _full_session_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    eth_before = df["session"].eq("ETH") & (df["timestamp"] < pd.Timestamp("2026-06-02 09:30", tz=TZ))
    assert result.loc[eth_before, "dVWAP_RTH"].isna().all()


def test_eth_bars_after_rth_close_emit_nan():
    df = _full_session_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    eth_after = df["session"].eq("ETH") & (df["timestamp"] >= pd.Timestamp("2026-06-02 16:00", tz=TZ))
    assert result.loc[eth_after, "dVWAP_RTH"].isna().all()


def test_only_rth_bars_have_non_nan_dvwap():
    df = _full_session_fixture()
    result = compute_session_vwap_levels(df, enabled=True)
    is_rth = df["session"].eq("RTH")
    # RTH bars: all non-NaN
    assert result.loc[is_rth, "dVWAP_RTH"].notna().all()
    # ETH bars: all NaN
    assert result.loc[~is_rth, "dVWAP_RTH"].isna().all()


# ---------------------------------------------------------------------------
# 5. Zero-volume behavior
# ---------------------------------------------------------------------------

def test_zero_volume_single_bar_emits_nan():
    rows = [_rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0, 100.0, 0.0)]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, enabled=True)
    assert result["dVWAP_RTH"].iloc[0] != result["dVWAP_RTH"].iloc[0]  # NaN check


def test_zero_volume_then_positive_volume():
    """NaN when cumulative volume=0; valid VWAP once cumulative volume becomes positive."""
    rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0, 100.0, 0.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:31", tz=TZ), 102.0, 100.0, 101.0, 10.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, enabled=True)
    assert np.isnan(result["dVWAP_RTH"].iloc[0])
    assert not np.isnan(result["dVWAP_RTH"].iloc[1])


def test_zero_volume_multiple_bars_then_valid():
    rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0, 100.0, 0.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:31", tz=TZ), 101.0, 99.0, 100.0, 0.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:32", tz=TZ), 104.0, 100.0, 102.0, 5.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, enabled=True)
    assert np.isnan(result["dVWAP_RTH"].iloc[0])
    assert np.isnan(result["dVWAP_RTH"].iloc[1])
    tp = (104.0 + 100.0 + 102.0) / 3.0
    assert result["dVWAP_RTH"].iloc[2] == pytest.approx(tp, rel=1e-9)


# ---------------------------------------------------------------------------
# 6. Settings validation
# ---------------------------------------------------------------------------

def test_unsupported_anchor_raises_value_error():
    df = _rth_fixture()
    with pytest.raises(ValueError, match="Unsupported VWAP anchor"):
        compute_session_vwap_levels(df, anchor="ETH", enabled=True)


def test_unsupported_anchor_with_weird_string_raises_value_error():
    df = _rth_fixture()
    with pytest.raises(ValueError, match="Unsupported VWAP anchor"):
        compute_session_vwap_levels(df, anchor="DAILY", enabled=True)


def test_unsupported_instrument_raises_value_error():
    df = _rth_fixture()
    with pytest.raises(ValueError, match="Unsupported instrument"):
        compute_session_vwap_levels(df, instrument="XX", enabled=True)


def test_naive_timestamp_raises_value_error():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_session_vwap_levels(_naive_df(), enabled=True)


def test_disabled_accepts_naive_timestamp_no_validation():
    # Disabled mode must not raise even for naive timestamps.
    result = compute_session_vwap_levels(_naive_df(), enabled=False)
    assert list(result.columns) == []


def test_disabled_accepts_unsupported_anchor():
    df = _rth_fixture()
    result = compute_session_vwap_levels(df, anchor="BOGUS", enabled=False)
    assert list(result.columns) == []


def test_disabled_accepts_unsupported_instrument():
    df = _rth_fixture()
    result = compute_session_vwap_levels(df, instrument="ZZ", enabled=False)
    assert list(result.columns) == []


# ---------------------------------------------------------------------------
# 7. Regression safety
# ---------------------------------------------------------------------------

def test_existing_level_columns_unchanged_when_vwap_disabled():
    df = tag_session(
        pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-06-02 09:30", periods=10, freq="1min", tz=TZ),
                "open": np.ones(10) * 100,
                "high": np.ones(10) * 101,
                "low": np.ones(10) * 99,
                "close": np.ones(10) * 100,
                "volume": np.ones(10) * 50,
            }
        ),
        "ES",
    )
    out_no_vwap = compute_all_levels(
        df, instrument="ES", opening_range_minutes=5, sma_lengths=[2], session_vwap_enabled=False
    )
    out_with_vwap = compute_all_levels(
        df, instrument="ES", opening_range_minutes=5, sma_lengths=[2], session_vwap_enabled=True, session_vwap_anchor="RTH"
    )

    # All columns from the disabled run must be present and identical in the enabled run.
    for col in out_no_vwap.columns:
        assert col in out_with_vwap.columns
        pd.testing.assert_series_equal(
            out_no_vwap[col].reset_index(drop=True),
            out_with_vwap[col].reset_index(drop=True),
            check_names=False,
        )


def test_no_dvwap_column_without_session_vwap_enabled():
    df = tag_session(_rth_fixture(), "ES")
    out = compute_all_levels(df, instrument="ES", opening_range_minutes=5)
    assert "dVWAP_RTH" not in out.columns


def test_dvwap_column_present_when_enabled():
    df = tag_session(_rth_fixture(), "ES")
    out = compute_all_levels(
        df, instrument="ES", opening_range_minutes=5, session_vwap_enabled=True, session_vwap_anchor="RTH"
    )
    assert "dVWAP_RTH" in out.columns


# ---------------------------------------------------------------------------
# 8. Point-in-time / future-shock test
# ---------------------------------------------------------------------------

def test_dvwap_rth_future_shock():
    """Appending future bars must not change dVWAP_RTH values at prior timestamps."""
    base_rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0,  100.0, 10.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:31", tz=TZ), 102.0, 100.0, 101.0, 20.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:32", tz=TZ), 103.0, 101.0, 102.0, 30.0),
    ]
    base_df = pd.DataFrame(base_rows)

    before = compute_session_vwap_levels(base_df, enabled=True)

    # Append future RTH bars with extreme values.
    future_rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:33", tz=TZ), 999.0, 1.0, 500.0, 10000.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:34", tz=TZ), 999.0, 1.0, 500.0, 10000.0),
    ]
    extended_df = pd.concat([base_df, pd.DataFrame(future_rows)], ignore_index=True)
    after = compute_session_vwap_levels(extended_df, enabled=True)

    # Values at original rows must be identical.
    pd.testing.assert_series_equal(
        before["dVWAP_RTH"].reset_index(drop=True),
        after["dVWAP_RTH"].iloc[: len(base_df)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_dvwap_rth_future_shock_across_sessions():
    """Future ETH and next-session bars must not affect prior-session dVWAP_RTH."""
    base_rows = [
        _rth_bar(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0, 100.0, 10.0),
        _rth_bar(pd.Timestamp("2026-06-02 09:31", tz=TZ), 102.0, 100.0, 101.0, 20.0),
    ]
    base_df = pd.DataFrame(base_rows)
    before = compute_session_vwap_levels(base_df, enabled=True)

    future_rows = [
        _eth_bar(pd.Timestamp("2026-06-02 17:00", tz=TZ), 90.0, 88.0, 89.0, 5.0),
        _rth_bar(pd.Timestamp("2026-06-03 09:30", tz=TZ), 50.0, 48.0, 49.0, 100.0),
    ]
    extended_df = pd.concat([base_df, pd.DataFrame(future_rows)], ignore_index=True)
    after = compute_session_vwap_levels(extended_df, enabled=True)

    pd.testing.assert_series_equal(
        before["dVWAP_RTH"].reset_index(drop=True),
        after["dVWAP_RTH"].iloc[: len(base_df)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


# ---------------------------------------------------------------------------
# 9. Session column derived when absent
# ---------------------------------------------------------------------------

def test_session_column_derived_from_instrument_config():
    """When session column is absent, RTH membership is derived from timestamps."""
    # Build a DataFrame with both RTH and ETH bars but no 'session' column.
    rows_no_session = []
    # 08:00 ETH bar
    rows_no_session.append({
        "timestamp": pd.Timestamp("2026-06-02 08:00", tz=TZ),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 5.0,
    })
    # 09:30 RTH bar
    rows_no_session.append({
        "timestamp": pd.Timestamp("2026-06-02 09:30", tz=TZ),
        "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0,
    })
    # 09:31 RTH bar
    rows_no_session.append({
        "timestamp": pd.Timestamp("2026-06-02 09:31", tz=TZ),
        "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 20.0,
    })
    df = pd.DataFrame(rows_no_session)
    assert "session" not in df.columns

    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)

    # ETH bar at 08:00 should be NaN
    assert np.isnan(result["dVWAP_RTH"].iloc[0])
    # RTH bars should have valid values
    assert not np.isnan(result["dVWAP_RTH"].iloc[1])
    assert not np.isnan(result["dVWAP_RTH"].iloc[2])


# ---------------------------------------------------------------------------
# 10. NQ instrument support
# ---------------------------------------------------------------------------

def test_nq_instrument_is_supported():
    df = _rth_fixture()
    result = compute_session_vwap_levels(df, instrument="NQ", enabled=True)
    assert "dVWAP_RTH" in result.columns
