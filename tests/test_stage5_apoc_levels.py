"""Stage 5 — APOC / pAPOC level tests.

Covers:
- Disabled / gate behavior (true no-op, no validation).
- Output column contract (exactly APOC and pAPOC).
- APOC correctness (correct POC, NaN before A-period completion).
- pAPOC correctness (prior-session APOC, frozen, NaN when no prior APOC).
- RTH / ETH behavior (ETH bars excluded; non-RTH bars emit NaN).
- Tie-breaking / consistency (matches profile.py np.argmax on sorted bins).
- Point-in-time / future-shock tests.
- Regression safety (existing level outputs unchanged).

APOC and pAPOC are profile/POC levels, not Single Print levels.
They are computed in ``thesistester/levels/apoc.py`` and are independent
of the Single Print logic in ``thesistester/levels/tpo.py``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_apoc_levels, compute_tpo_levels
from thesistester.levels.apoc import COL_APOC, COL_PAPOC
from thesistester.levels.tpo import SINGLE_PRINT_COLUMNS

TZ = "America/New_York"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rth_bar(
    ts: pd.Timestamp,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "RTH",
    }


def _eth_bar(
    ts: pd.Timestamp,
    high: float,
    low: float,
    close: float,
    volume: float = 5.0,
) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "ETH",
    }


def _rth_ts(session_date: str, h: int, m: int) -> pd.Timestamp:
    return pd.Timestamp(f"{session_date} {h:02d}:{m:02d}:00", tz=TZ)


def _naive_df() -> pd.DataFrame:
    """Minimal DataFrame with naive (tz-unaware) timestamps."""
    ts = pd.date_range("2026-06-02 09:30", periods=5, freq="1min")
    n = len(ts)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 1.0,
            "session": "RTH",
        }
    )


def _base_df(
    start: str = "2026-06-02 09:30:00",
    periods: int = 20,
    freq: str = "1min",
) -> pd.DataFrame:
    ts = pd.date_range(start=start, periods=periods, freq=freq, tz=TZ)
    n = len(ts)
    vals = np.arange(n, dtype=float) + 100.0
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": vals,
            "high": vals + 0.5,
            "low": vals - 0.5,
            "close": vals + 0.25,
            "volume": np.arange(n, dtype=float) + 1.0,
        }
    )


# ---------------------------------------------------------------------------
# Fixtures: single-session with known A-period POC
# ---------------------------------------------------------------------------
#
# Session 2026-06-02:
#   Bar at 09:30 (in A-period): high=100.50, low=99.50, close=100.00, vol=100
#     typical = (100.50 + 99.50 + 100.00) / 3 = 100.00  → bin 100.00, vol 100
#   Bar at 09:45 (in A-period): high=101.00, low=100.50, close=100.75, vol=200
#     typical = (101.00 + 100.50 + 100.75) / 3 = 100.75 → bin 100.75, vol 200
#   POC = 100.75 (higher volume at bin 100.75)
#
#   A-period ends at 10:00 → APOC available at rows with timestamp >= 10:00.
#   Bars at 09:30 and 09:45 → NaN.
#   Bars at 10:00 and later → APOC = 100.75.

EXPECTED_APOC_S1 = 100.75


def _single_session_fixture(date: str = "2026-06-02") -> pd.DataFrame:
    """Single RTH session with known A-period POC = 100.75."""
    rows = [
        _rth_bar(_rth_ts(date, 9, 30), high=100.50, low=99.50, close=100.00, volume=100),
        _rth_bar(_rth_ts(date, 9, 45), high=101.00, low=100.50, close=100.75, volume=200),
        _rth_bar(_rth_ts(date, 10, 0), high=101.00, low=100.00, close=100.50, volume=50),
        _rth_bar(_rth_ts(date, 10, 30), high=101.25, low=100.75, close=101.00, volume=50),
        _rth_bar(_rth_ts(date, 11, 0), high=101.25, low=100.75, close=101.00, volume=50),
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures: two-session
# ---------------------------------------------------------------------------
#
# Session 1 (2026-06-02): APOC = 100.75 (see above)
# Session 2 (2026-06-03):
#   Bar at 09:30: high=105.00, low=104.00, close=104.50, vol=50
#     typical = (105+104+104.5)/3 = 104.50 → bin 104.50, vol 50
#   Bar at 09:45: high=106.00, low=105.00, close=105.50, vol=80
#     typical = (106+105+105.5)/3 = 105.50 → bin 105.50, vol 80
#   POC = 105.50 (higher volume at bin 105.50)
#
#   pAPOC in session 2 = APOC of session 1 = 100.75

EXPECTED_APOC_S2 = 105.50
EXPECTED_PAPOC_S2 = EXPECTED_APOC_S1


def _two_session_fixture() -> pd.DataFrame:
    """Two RTH sessions with ETH bars between them."""
    rows = []
    s1 = "2026-06-02"
    s2 = "2026-06-03"

    # Session 1
    rows.append(_rth_bar(_rth_ts(s1, 9, 30), high=100.50, low=99.50, close=100.00, volume=100))
    rows.append(_rth_bar(_rth_ts(s1, 9, 45), high=101.00, low=100.50, close=100.75, volume=200))
    rows.append(_rth_bar(_rth_ts(s1, 10, 0), high=101.00, low=100.00, close=100.50, volume=50))
    rows.append(_rth_bar(_rth_ts(s1, 10, 30), high=101.25, low=100.75, close=101.00, volume=40))
    rows.append(_rth_bar(_rth_ts(s1, 11, 0), high=101.25, low=100.75, close=101.00, volume=40))

    # ETH gap between sessions
    rows.append(_eth_bar(pd.Timestamp(f"{s1} 17:00", tz=TZ), 101.0, 100.0, 100.5))
    rows.append(_eth_bar(pd.Timestamp(f"{s2} 08:00", tz=TZ), 102.0, 101.0, 101.5))

    # Session 2
    rows.append(_rth_bar(_rth_ts(s2, 9, 30), high=105.00, low=104.00, close=104.50, volume=50))
    rows.append(_rth_bar(_rth_ts(s2, 9, 45), high=106.00, low=105.00, close=105.50, volume=80))
    rows.append(_rth_bar(_rth_ts(s2, 10, 0), high=106.00, low=105.00, close=105.50, volume=30))
    rows.append(_rth_bar(_rth_ts(s2, 10, 30), high=106.50, low=106.00, close=106.25, volume=30))
    rows.append(_rth_bar(_rth_ts(s2, 11, 0), high=106.50, low=106.00, close=106.25, volume=30))

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Disabled / gate behavior
# ---------------------------------------------------------------------------


def test_disabled_returns_empty_df():
    df = _base_df()
    result = compute_apoc_levels(df, enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0
    assert len(result) == len(df)


def test_disabled_preserves_input_index():
    df = _base_df()
    result = compute_apoc_levels(df, enabled=False)
    pd.testing.assert_index_equal(result.index, df.index)


def test_disabled_accepts_naive_timestamps():
    result = compute_apoc_levels(_naive_df(), enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_disabled_accepts_unsupported_instrument():
    df = _base_df()
    result = compute_apoc_levels(df, instrument="UNSUPPORTED", enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_compute_all_levels_apoc_disabled_no_apoc_columns():
    df = tag_session(_base_df(), "ES")
    out = compute_all_levels(df, instrument="ES", apoc_enabled=False)
    assert "APOC" not in out.columns
    assert "pAPOC" not in out.columns


# ---------------------------------------------------------------------------
# 2. Output columns
# ---------------------------------------------------------------------------


def test_apoc_enabled_returns_exactly_apoc_and_papoc():
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)
    assert set(result.columns) == {COL_APOC, COL_PAPOC}


def test_apoc_column_names_are_exact():
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)
    assert COL_APOC in result.columns
    assert COL_PAPOC in result.columns


def test_apoc_output_no_extra_columns():
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)
    assert len(result.columns) == 2


def test_apoc_column_dtypes_are_float():
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)
    assert result[COL_APOC].dtype == np.float64
    assert result[COL_PAPOC].dtype == np.float64


def test_compute_all_levels_sp_and_apoc_enabled_six_independent_columns():
    """single_prints_enabled=True + apoc_enabled=True → exactly six independent columns."""
    df = _two_session_fixture()
    out = compute_all_levels(
        df,
        instrument="ES",
        single_prints_enabled=True,
        apoc_enabled=True,
    )
    for col in SINGLE_PRINT_COLUMNS:
        assert col in out.columns, f"Missing Single Print column: {col}"
    assert COL_APOC in out.columns
    assert COL_PAPOC in out.columns
    new_cols = [c for c in out.columns if c in set(SINGLE_PRINT_COLUMNS) | {COL_APOC, COL_PAPOC}]
    assert len(new_cols) == 6, f"Expected 6 new columns, got {len(new_cols)}: {new_cols}"


# ---------------------------------------------------------------------------
# 3. APOC correctness
# ---------------------------------------------------------------------------


def test_apoc_is_nan_before_a_period_completion():
    """APOC must be NaN for bars before timestamp >= RTH_open + 30min."""
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    # Rows are returned in sorted timestamp order.
    # Rows 0 and 1 correspond to 09:30 and 09:45 (both inside A-period, before 10:00).
    assert math.isnan(result[COL_APOC].iloc[0]), "09:30 bar should have NaN APOC"
    assert math.isnan(result[COL_APOC].iloc[1]), "09:45 bar should have NaN APOC"


def test_apoc_appears_at_a_period_completion():
    """APOC must appear at or after RTH_open + 30min (timestamp >= 10:00)."""
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    # Row 2 corresponds to 10:00 (first bar at/after A-period completion).
    assert not math.isnan(result[COL_APOC].iloc[2]), "10:00 bar should have non-NaN APOC"


def test_apoc_correct_value_matches_profile_poc():
    """APOC must equal the POC computed from A-period bars using the profile approximation."""
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    # All bars from 10:00 onward should have APOC = 100.75.
    for i in range(2, len(result)):
        assert result[COL_APOC].iloc[i] == pytest.approx(EXPECTED_APOC_S1, abs=1e-9), (
            f"Row {i}: expected APOC={EXPECTED_APOC_S1}, got {result[COL_APOC].iloc[i]}"
        )


def test_apoc_does_not_change_for_later_rth_bars():
    """APOC must not change after A-period completion — it is frozen for the session."""
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    apoc_values = result[COL_APOC].iloc[2:].dropna()
    assert (apoc_values == apoc_values.iloc[0]).all(), "APOC must remain constant after A-period"


def test_apoc_zero_volume_a_period_returns_nan():
    """When all A-period bars have volume=0, APOC must be NaN."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.5, low=99.5, close=100.0, volume=0),
        _rth_bar(_rth_ts("2026-06-02", 9, 45), high=100.75, low=100.25, close=100.5, volume=0),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=101.0, low=100.0, close=100.5, volume=10),
        _rth_bar(_rth_ts("2026-06-02", 10, 30), high=101.0, low=100.0, close=100.5, volume=10),
    ]
    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    # All bars (including post-A-period) should have NaN APOC since A-period had no volume.
    assert result[COL_APOC].isna().all(), "Zero-volume A-period should produce NaN APOC"


def test_apoc_missing_a_period_returns_nan():
    """When no bars fall in the A-period window, APOC must be NaN."""
    rows = [
        # Bars start at 10:30 — after the A-period window.
        _rth_bar(_rth_ts("2026-06-02", 10, 30), high=101.0, low=100.0, close=100.5, volume=10),
        _rth_bar(_rth_ts("2026-06-02", 11, 0), high=101.0, low=100.0, close=100.5, volume=10),
    ]
    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    assert result[COL_APOC].isna().all(), "No A-period bars → NaN APOC for all rows"


# ---------------------------------------------------------------------------
# 4. pAPOC correctness
# ---------------------------------------------------------------------------


def test_papoc_in_session2_equals_session1_apoc():
    """Session 2 pAPOC must equal session 1 APOC."""
    df = _two_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    s2_rth_mask = (sorted_df["session"] == "RTH") & (
        sorted_df["timestamp"] >= pd.Timestamp("2026-06-03 09:30:00", tz=TZ)
    )
    s2_papoc = result[COL_PAPOC][s2_rth_mask]
    assert np.allclose(s2_papoc.values, EXPECTED_PAPOC_S2, atol=1e-9), (
        f"Session 2 pAPOC should equal session 1 APOC={EXPECTED_PAPOC_S2}, got {s2_papoc.values}"
    )


def test_papoc_appears_from_session2_rth_open():
    """pAPOC must be available from the first RTH bar of session 2."""
    df = _two_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    s2_first_rth_idx = sorted_df[
        (sorted_df["session"] == "RTH")
        & (sorted_df["timestamp"] >= pd.Timestamp("2026-06-03 09:30:00", tz=TZ))
    ].index[0]

    assert not math.isnan(result[COL_PAPOC].iloc[s2_first_rth_idx]), (
        "pAPOC must not be NaN at the first RTH bar of session 2"
    )


def test_papoc_remains_frozen_through_session2():
    """pAPOC must remain constant for all RTH bars in session 2."""
    df = _two_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    s2_rth_mask = (sorted_df["session"] == "RTH") & (
        sorted_df["timestamp"] >= pd.Timestamp("2026-06-03 09:30:00", tz=TZ)
    )
    s2_papoc = result[COL_PAPOC][s2_rth_mask]
    first_val = s2_papoc.iloc[0]
    assert np.allclose(s2_papoc.values, first_val, atol=1e-9), (
        "pAPOC must remain frozen throughout session 2"
    )


def test_papoc_nan_when_no_prior_session():
    """Session 1 pAPOC must be NaN (no prior session exists)."""
    df = _single_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    rth_rows = result[COL_PAPOC]
    assert rth_rows.isna().all(), "pAPOC must be NaN for session 1 (no prior session)"


def test_papoc_nan_when_prior_session_has_no_valid_apoc():
    """If session 1 had no valid APOC, session 2 pAPOC must be NaN."""
    rows = []
    s1 = "2026-06-02"
    s2 = "2026-06-03"

    # Session 1: only a bar after A-period (no A-period bars → NaN APOC)
    rows.append(_rth_bar(_rth_ts(s1, 10, 30), high=101.0, low=100.0, close=100.5, volume=10))
    rows.append(_rth_bar(_rth_ts(s1, 11, 0), high=101.0, low=100.0, close=100.5, volume=10))

    # ETH gap
    rows.append(_eth_bar(pd.Timestamp(f"{s1} 17:00", tz=TZ), 101.0, 100.0, 100.5))

    # Session 2: normal A-period bars
    rows.append(_rth_bar(_rth_ts(s2, 9, 30), high=105.0, low=104.0, close=104.5, volume=50))
    rows.append(_rth_bar(_rth_ts(s2, 10, 0), high=106.0, low=105.0, close=105.5, volume=30))
    rows.append(_rth_bar(_rth_ts(s2, 11, 0), high=106.0, low=105.0, close=105.5, volume=30))

    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    s2_rth_mask = (sorted_df["session"] == "RTH") & (
        sorted_df["timestamp"] >= pd.Timestamp("2026-06-03 09:30:00", tz=TZ)
    )
    s2_papoc = result[COL_PAPOC][s2_rth_mask]
    assert s2_papoc.isna().all(), "pAPOC must be NaN when prior session had no valid APOC"


# ---------------------------------------------------------------------------
# 5. RTH / ETH behavior
# ---------------------------------------------------------------------------


def test_eth_bars_do_not_contribute_to_apoc():
    """ETH bars in the A-period time window must not contribute to APOC."""
    rows = []
    s = "2026-06-02"
    # One RTH bar in A-period.
    rows.append(_rth_bar(_rth_ts(s, 9, 30), high=100.5, low=99.5, close=100.0, volume=10))
    # ETH bar at same time window with very high volume — should not affect POC.
    rows.append(_eth_bar(_rth_ts(s, 9, 35), high=110.0, low=109.0, close=109.5, volume=99999))
    # Bar after A-period.
    rows.append(_rth_bar(_rth_ts(s, 10, 0), high=100.5, low=99.5, close=100.0, volume=10))

    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    post_a_mask = (sorted_df["session"] == "RTH") & (
        sorted_df["timestamp"] >= pd.Timestamp(f"{s} 10:00:00", tz=TZ)
    )
    apoc_vals = result[COL_APOC][post_a_mask].dropna()

    # APOC from the single RTH A-period bar: typical = (100.5+99.5+100)/3 = 100.0
    expected = 100.0
    assert np.allclose(apoc_vals.values, expected, atol=1e-9), (
        f"ETH bar should not affect APOC. Expected {expected}, got {apoc_vals.values}"
    )


def test_non_rth_bars_emit_nan():
    """Non-RTH (ETH) bars must have NaN for both APOC and pAPOC."""
    df = _two_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    eth_mask = sorted_df["session"] == "ETH"
    assert result[COL_APOC][eth_mask].isna().all(), "ETH bars must have NaN APOC"
    assert result[COL_PAPOC][eth_mask].isna().all(), "ETH bars must have NaN pAPOC"


def test_session_column_absent_derives_from_instrument_config():
    """compute_apoc_levels must work when session column is absent."""
    df = _single_session_fixture()
    df_no_session = df.drop(columns=["session"])
    result = compute_apoc_levels(df_no_session, instrument="ES", enabled=True)

    assert set(result.columns) == {COL_APOC, COL_PAPOC}
    # Should still produce valid APOC at 10:00+.
    sorted_df = df_no_session.sort_values("timestamp").reset_index(drop=True)
    post_a_mask = sorted_df["timestamp"] >= pd.Timestamp("2026-06-02 10:00:00", tz=TZ)
    assert not result[COL_APOC][post_a_mask].isna().any(), (
        "APOC must be valid after A-period when session is derived from config"
    )


# ---------------------------------------------------------------------------
# 6. Tie-breaking / consistency with profile.py
# ---------------------------------------------------------------------------
#
# _compute_profile uses np.argmax on a bins-sorted-ascending volume array.
# When two bins have equal volume, np.argmax returns the FIRST (lowest-price)
# bin.  APOC must exhibit the same tie-breaking behavior.


def test_apoc_tie_breaking_uses_lowest_price_bin():
    """Equal-volume bins → APOC = lowest bin price (np.argmax on sorted array)."""
    rows = [
        # bar1: typical = (100.125 + 99.875 + 100.00) / 3 = 100.00 → bin 100.00
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.125, low=99.875, close=100.00, volume=100),
        # bar2: typical = (100.375 + 100.125 + 100.25) / 3 = 100.25 → bin 100.25
        _rth_bar(_rth_ts("2026-06-02", 9, 45), high=100.375, low=100.125, close=100.25, volume=100),
        # post A-period bar
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.5, low=100.0, close=100.25, volume=10),
    ]
    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="ES", enabled=True)

    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    post_a_mask = sorted_df["timestamp"] >= pd.Timestamp("2026-06-02 10:00:00", tz=TZ)
    apoc_val = result[COL_APOC][post_a_mask].iloc[0]

    # Bins: 100.00 (vol=100) and 100.25 (vol=100) — equal.
    # np.argmax([100, 100]) = 0 → lowest bin = 100.00.
    assert apoc_val == pytest.approx(100.00, abs=1e-9), (
        f"Tie-breaking: expected POC=100.00 (lowest bin), got {apoc_val}"
    )


# ---------------------------------------------------------------------------
# 7. Point-in-time / future-shock
# ---------------------------------------------------------------------------


def test_future_shock_appending_current_session_bars_does_not_change_apoc():
    """Appending more bars to the current session must not alter prior APOC values."""
    df_base = _single_session_fixture()
    result_base = compute_apoc_levels(df_base, instrument="ES", enabled=True)

    # Append a future bar in the same session with very different price/volume.
    extra = pd.DataFrame(
        [_rth_bar(_rth_ts("2026-06-02", 14, 0), high=200.0, low=150.0, close=175.0, volume=9999)]
    )
    df_extended = pd.concat([df_base, extra], ignore_index=True)
    result_extended = compute_apoc_levels(df_extended, instrument="ES", enabled=True)

    # Values for the original rows (first 5 rows when sorted) must be unchanged.
    orig_len = len(df_base)
    for i in range(orig_len):
        orig_apoc = result_base[COL_APOC].iloc[i]
        ext_apoc = result_extended[COL_APOC].iloc[i]
        if math.isnan(orig_apoc):
            assert math.isnan(ext_apoc), f"Row {i}: APOC was NaN, should stay NaN"
        else:
            assert orig_apoc == pytest.approx(ext_apoc, abs=1e-9), (
                f"Row {i}: APOC changed after appending future bar"
            )


def test_future_shock_appending_next_session_bars_does_not_change_papoc():
    """Appending next-session bars must not alter prior session APOC/pAPOC values."""
    df_two = _two_session_fixture()
    result_two = compute_apoc_levels(df_two, instrument="ES", enabled=True)

    # Append a bar in a third session.
    extra = pd.DataFrame(
        [_rth_bar(_rth_ts("2026-06-04", 9, 30), high=200.0, low=150.0, close=175.0, volume=9999)]
    )
    df_extended = pd.concat([df_two, extra], ignore_index=True)
    result_extended = compute_apoc_levels(df_extended, instrument="ES", enabled=True)

    # All original rows' APOC and pAPOC values must be unchanged.
    orig_len = len(df_two)
    for i in range(orig_len):
        for col in (COL_APOC, COL_PAPOC):
            orig_val = result_two[col].iloc[i]
            ext_val = result_extended[col].iloc[i]
            if math.isnan(orig_val):
                assert math.isnan(ext_val), f"Row {i} {col}: was NaN, should stay NaN"
            else:
                assert orig_val == pytest.approx(ext_val, abs=1e-9), (
                    f"Row {i} {col}: changed after appending future session bar"
                )


# ---------------------------------------------------------------------------
# 8. Regression safety
# ---------------------------------------------------------------------------


def test_existing_level_outputs_unchanged_when_apoc_disabled():
    """Disabling APOC must not change any existing level column values."""
    df = tag_session(_base_df(), "ES")

    out_without_apoc = compute_all_levels(
        df,
        instrument="ES",
        sma_lengths=[3],
        ema_lengths=[3],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        apoc_enabled=False,
    )
    out_with_apoc = compute_all_levels(
        df,
        instrument="ES",
        sma_lengths=[3],
        ema_lengths=[3],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        apoc_enabled=True,
    )

    shared_cols = [c for c in out_without_apoc.columns if c in out_with_apoc.columns]
    for col in shared_cols:
        pd.testing.assert_series_equal(
            out_without_apoc[col].reset_index(drop=True),
            out_with_apoc[col].reset_index(drop=True),
            check_names=False,
            obj=f"Column {col!r} changed when apoc_enabled toggled",
        )


def test_single_print_outputs_unchanged_when_apoc_enabled():
    """Enabling APOC must not change Single Print column values."""
    df = _two_session_fixture()

    out_sp_only = compute_all_levels(df, instrument="ES", single_prints_enabled=True, apoc_enabled=False)
    out_sp_and_apoc = compute_all_levels(df, instrument="ES", single_prints_enabled=True, apoc_enabled=True)

    for col in SINGLE_PRINT_COLUMNS:
        if col in out_sp_only.columns and col in out_sp_and_apoc.columns:
            pd.testing.assert_series_equal(
                out_sp_only[col].reset_index(drop=True),
                out_sp_and_apoc[col].reset_index(drop=True),
                check_names=False,
                obj=f"Single Print column {col!r} changed when apoc_enabled=True",
            )


def test_no_apoc_columns_without_explicit_enable():
    """APOC columns must not appear unless apoc_enabled=True."""
    df = tag_session(_base_df(), "ES")
    out = compute_all_levels(df, instrument="ES")
    assert COL_APOC not in out.columns
    assert COL_PAPOC not in out.columns


def test_compute_tpo_levels_sp_enabled_unchanged_by_stage5():
    """compute_tpo_levels(single_prints_enabled=True) must produce exactly the four SP columns."""
    df = _two_session_fixture()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    assert set(result.columns) == set(SINGLE_PRINT_COLUMNS)


def test_compute_tpo_levels_apoc_enabled_raises_value_error():
    """compute_tpo_levels must raise ValueError when apoc_enabled=True."""
    df = _single_session_fixture()
    with pytest.raises(ValueError, match="compute_apoc_levels"):
        compute_tpo_levels(df, instrument="ES", apoc_enabled=True)


def test_apoc_column_present_when_enabled_via_compute_all():
    """APOC and pAPOC columns must be present when apoc_enabled=True in compute_all_levels."""
    df = tag_session(_base_df(), "ES")
    out = compute_all_levels(df, instrument="ES", apoc_enabled=True)
    assert COL_APOC in out.columns
    assert COL_PAPOC in out.columns


# ---------------------------------------------------------------------------
# 9. Validation
# ---------------------------------------------------------------------------


def test_enabled_requires_tz_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_apoc_levels(_naive_df(), enabled=True)


def test_enabled_requires_supported_instrument():
    df = tag_session(_base_df(), "ES")
    with pytest.raises(ValueError, match="Unsupported instrument"):
        compute_apoc_levels(df, instrument="UNSUPPORTED", enabled=True)


def test_nq_instrument_supported():
    """NQ must be a supported instrument."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=18050.0, low=17950.0, close=18000.0, volume=100),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=18050.0, low=17950.0, close=18000.0, volume=50),
    ]
    df = pd.DataFrame(rows)
    result = compute_apoc_levels(df, instrument="NQ", enabled=True)
    assert set(result.columns) == {COL_APOC, COL_PAPOC}


def test_output_index_length_matches_sorted_input():
    """Output row count must equal input row count."""
    df = _two_session_fixture()
    result = compute_apoc_levels(df, instrument="ES", enabled=True)
    assert len(result) == len(df)


def test_compute_apoc_levels_exported_from_package():
    """compute_apoc_levels must be importable from thesistester.levels."""
    from thesistester.levels import compute_apoc_levels as fn
    assert callable(fn)


def test_compute_apoc_levels_in_all_list():
    """compute_apoc_levels must be in thesistester.levels.__all__."""
    import thesistester.levels as lvl
    assert "compute_apoc_levels" in lvl.__all__


def test_apoc_constants_exported_from_module():
    """APOC constants must be importable from apoc.py."""
    from thesistester.levels.apoc import A_PERIOD_MINUTES, APOC_COLUMNS, COL_APOC, COL_PAPOC
    assert A_PERIOD_MINUTES == 30
    assert COL_APOC == "APOC"
    assert COL_PAPOC == "pAPOC"
    assert set(APOC_COLUMNS) == {"APOC", "pAPOC"}
