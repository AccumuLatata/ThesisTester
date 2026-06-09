"""Stage 4 — TPO 30m Single Print level tests.

Covers:
- Disabled / gate behavior (true no-op, no validation).
- Output column contract (exactly the four scalar columns).
- TPO binning correctness (tick-size bins, single-touch vs multi-touch).
- Developing Single Prints (completed brackets only, nearest-above/below).
- Prior-session Single Prints (frozen, mapped to next session).
- RTH/ETH behavior (ETH bars excluded; emit NaN outside RTH).
- Point-in-time / future-shock tests.
- Regression safety (existing level outputs unchanged).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_tpo_levels
from thesistester.levels.tpo import (
    COL_D_ABOVE,
    COL_D_BELOW,
    COL_P_ABOVE,
    COL_P_BELOW,
    SINGLE_PRINT_COLUMNS,
    TPO_BRACKET_MINUTES,
)

TZ = "America/New_York"
TICK = 0.25  # ES tick size

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rth_bar(ts: pd.Timestamp, high: float, low: float, close: float, volume: float = 10.0) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "RTH",
    }


def _eth_bar(ts: pd.Timestamp, high: float, low: float, close: float, volume: float = 5.0) -> dict:
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


def _base_df(start: str = "2026-06-02 09:30:00", periods: int = 20, freq: str = "1min") -> pd.DataFrame:
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
# Fixture: two-session synthetic data with known SP structure
# ---------------------------------------------------------------------------
# Session 1 (2026-06-02):
#   Bracket A (09:30-10:00): prices 100.00 - 101.00  (touch bins 400-404)
#   Bracket B (10:00-10:30): prices 101.25 - 102.00  (touch bins 405-408)
#   Bracket C (10:30-11:00): prices 100.00 - 101.00  (touch bins 400-404 again)
#
# After brackets A+B+C complete:
#   Bins 400-404 are touched by brackets A and C → NOT Single Prints.
#   Bins 405-408 are touched by bracket B only   → Single Prints.
#   SP prices: 101.25, 101.50, 101.75, 102.00
#
# Session 2 (2026-06-03):
#   Prior-session SP prices = [101.25, 101.50, 101.75, 102.00]
#   Bracket D (09:30-10:00): prices 105.00 - 106.00 (bins 420-424)
#   Bracket E (10:00-10:30): prices 107.00 - 108.00 (bins 428-432)
#   After D+E: all bins touched by exactly 1 bracket → all are SP.


def _sp_fixture_session1() -> pd.DataFrame:
    """Six 30-minute bars building three known brackets in session 1."""
    rows = []
    s = "2026-06-02"

    # Bracket A: 09:30-10:00 — one representative bar (30 min bar)
    rows.append(_rth_bar(_rth_ts(s, 9, 30), high=101.00, low=100.00, close=100.50))
    # Bracket B: 10:00-10:30
    rows.append(_rth_bar(_rth_ts(s, 10, 0), high=102.00, low=101.25, close=101.50))
    # Bracket C: 10:30-11:00 — overlaps bins of bracket A
    rows.append(_rth_bar(_rth_ts(s, 10, 30), high=101.00, low=100.00, close=100.25))
    # Three bars after bracket C to represent ongoing RTH bars.
    rows.append(_rth_bar(_rth_ts(s, 11, 0), high=101.25, low=100.75, close=101.00))
    rows.append(_rth_bar(_rth_ts(s, 11, 1), high=101.25, low=100.75, close=101.00))
    rows.append(_rth_bar(_rth_ts(s, 11, 2), high=101.25, low=100.75, close=101.00))
    return pd.DataFrame(rows)


def _sp_fixture_two_sessions() -> pd.DataFrame:
    """Two-session fixture with known SP structure."""
    rows = []
    s1 = "2026-06-02"
    s2 = "2026-06-03"

    # --- Session 1 ---
    rows.append(_rth_bar(_rth_ts(s1, 9, 30), high=101.00, low=100.00, close=100.50))
    rows.append(_rth_bar(_rth_ts(s1, 10, 0), high=102.00, low=101.25, close=101.50))
    rows.append(_rth_bar(_rth_ts(s1, 10, 30), high=101.00, low=100.00, close=100.25))
    rows.append(_rth_bar(_rth_ts(s1, 11, 0), high=101.25, low=100.75, close=101.00))
    rows.append(_rth_bar(_rth_ts(s1, 11, 1), high=101.25, low=100.75, close=101.00))
    # ETH gap between sessions
    rows.append(_eth_bar(pd.Timestamp(f"{s1} 17:00", tz=TZ), high=101.0, low=100.0, close=100.5))
    rows.append(_eth_bar(pd.Timestamp(f"{s2} 08:00", tz=TZ), high=102.0, low=101.0, close=101.5))

    # --- Session 2 ---
    rows.append(_rth_bar(_rth_ts(s2, 9, 30), high=106.00, low=105.00, close=105.50))
    rows.append(_rth_bar(_rth_ts(s2, 10, 0), high=108.00, low=107.00, close=107.50))
    rows.append(_rth_bar(_rth_ts(s2, 10, 30), high=108.00, low=107.00, close=107.50))
    rows.append(_rth_bar(_rth_ts(s2, 11, 0), high=106.50, low=106.00, close=106.25))
    rows.append(_rth_bar(_rth_ts(s2, 11, 1), high=106.50, low=106.00, close=106.25))

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Disabled / gate behavior
# ---------------------------------------------------------------------------


def test_both_disabled_returns_empty_df():
    df = _base_df()
    result = compute_tpo_levels(df, single_prints_enabled=False, apoc_enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0
    assert len(result) == len(df)


def test_disabled_accepts_naive_timestamps():
    result = compute_tpo_levels(_naive_df(), single_prints_enabled=False, apoc_enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_disabled_accepts_unsupported_instrument():
    df = _base_df()
    result = compute_tpo_levels(df, instrument="UNSUPPORTED", single_prints_enabled=False, apoc_enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_apoc_enabled_raises_not_implemented():
    df = tag_session(_base_df(), "ES")
    with pytest.raises(NotImplementedError):
        compute_tpo_levels(df, apoc_enabled=True)


def test_apoc_and_sp_enabled_raises_not_implemented():
    """When apoc_enabled=True, raise NotImplementedError even if single_prints_enabled=True."""
    df = tag_session(_base_df(), "ES")
    with pytest.raises(NotImplementedError):
        compute_tpo_levels(df, single_prints_enabled=True, apoc_enabled=True)


def test_compute_all_levels_sp_disabled_no_sp_columns():
    df = tag_session(_base_df(), "ES")
    out = compute_all_levels(df, instrument="ES", single_prints_enabled=False)
    sp_cols = [c for c in out.columns if "SinglePrint" in c]
    assert sp_cols == []


# ---------------------------------------------------------------------------
# 2. Output column contract
# ---------------------------------------------------------------------------


def test_sp_enabled_produces_exactly_four_columns():
    df = tag_session(_base_df(), "ES")
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    assert set(result.columns) == set(SINGLE_PRINT_COLUMNS)


def test_sp_enabled_produces_exact_column_names():
    df = tag_session(_base_df(), "ES")
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    for col in SINGLE_PRINT_COLUMNS:
        assert col in result.columns, f"Missing column: {col}"


def test_no_dynamic_sp_columns():
    df = tag_session(_base_df(), "ES")
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    dynamic = [c for c in result.columns if c not in SINGLE_PRINT_COLUMNS and "SinglePrint" in c]
    assert dynamic == []


def test_output_index_length_matches_input():
    df = tag_session(_base_df(periods=45), "ES")
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    assert len(result) == len(df)


def test_sp_column_dtypes_are_float():
    df = tag_session(_base_df(), "ES")
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    for col in SINGLE_PRINT_COLUMNS:
        assert result[col].dtype == np.float64, f"{col} should be float64"


# ---------------------------------------------------------------------------
# 3. TPO binning correctness
# ---------------------------------------------------------------------------


def test_single_bracket_all_bins_are_sp():
    """With only one completed bracket, every bin it touches is a Single Print."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
    ]
    # One bar at 09:30 → bracket completes at 10:00.
    # Add a bar after 10:00 to allow bracket completion.
    rows.append(_rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.00))
    rows.append(_rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.25, low=100.00, close=100.00))
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # At the row at 10:01, bracket A is complete.
    # Bracket A bins: 100.00/0.25=400, 100.50/0.25=402 → ticks 400..402 = prices 100.0,100.25,100.5
    row_10_01 = result.iloc[2]
    assert not math.isnan(row_10_01[COL_D_ABOVE]) or not math.isnan(row_10_01[COL_D_BELOW])


def test_bin_touched_by_two_brackets_is_not_sp():
    """A bin touched by both bracket A and bracket C is excluded from Single Prints."""
    df = _sp_fixture_session1()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # After all three brackets complete (after 11:00), check row at 11:00.
    # Brackets A and C both cover bins 400-404 (prices 100.0-101.0).
    # Only bracket B's bins (405-408, prices 101.25-102.0) are Single Prints.
    row_after_c = result.iloc[3]  # row at 11:00 — bracket C completed at 11:00
    d_above = row_after_c[COL_D_ABOVE]
    d_below = row_after_c[COL_D_BELOW]
    close_at_row = df.iloc[3]["close"]  # 101.00

    # SP prices are 101.25, 101.50, 101.75, 102.00 (bracket B bins only).
    # NearestAbove > 101.00 → should be 101.25
    assert not math.isnan(d_above), "NearestAbove should not be NaN after bracket B completes"
    assert abs(d_above - 101.25) < 1e-9, f"Expected 101.25, got {d_above}"
    # NearestBelow < 101.00: bracket B bins are all ≥ 101.25, so no SP below 101.00 → NaN
    assert math.isnan(d_below), f"NearestBelow should be NaN (no SP below close {close_at_row}), got {d_below}"


def test_binning_uses_tick_size():
    """Bins are determined by instrument tick size (ES = 0.25)."""
    # Build a bracket that spans exactly two tick bins: 100.00 and 100.25.
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.10),
    ]
    rows.append(_rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.00))
    rows.append(_rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.25, low=100.00, close=100.00))
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    row = result.iloc[2]
    # With close=100.00, NearestAbove should be 100.25 (the only bin above close).
    assert abs(row[COL_D_ABOVE] - 100.25) < 1e-9


def test_binning_is_deterministic():
    """Running twice on the same data produces identical results."""
    df = _sp_fixture_session1()
    r1 = compute_tpo_levels(df.copy(), instrument="ES", single_prints_enabled=True)
    r2 = compute_tpo_levels(df.copy(), instrument="ES", single_prints_enabled=True)
    pd.testing.assert_frame_equal(r1, r2)


# ---------------------------------------------------------------------------
# 4. Developing Single Prints
# ---------------------------------------------------------------------------


def test_no_developing_sp_before_first_completed_bracket():
    """Before the first 30-min bracket completes, all developing SP columns are NaN."""
    rows = [
        # All bars within bracket A (09:30 - just before 10:00).
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 9, 31), high=100.75, low=100.25, close=100.50),
        _rth_bar(_rth_ts("2026-06-02", 9, 59), high=101.00, low=100.50, close=100.75),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    assert result[COL_D_ABOVE].isna().all(), "dNearestAbove must be NaN before bracket completes"
    assert result[COL_D_BELOW].isna().all(), "dNearestBelow must be NaN before bracket completes"


def test_developing_sp_appear_after_first_bracket_completes():
    """After one bracket completes, developing SP columns become non-NaN (if bins exist)."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.50, low=100.00, close=100.00),
        _rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.50, low=100.00, close=100.25),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    # Bracket A completes at 10:00.  Rows at 10:00 and 10:01 have bracket A complete.
    assert not math.isnan(result.iloc[1][COL_D_ABOVE]) or not math.isnan(result.iloc[1][COL_D_BELOW])
    assert not math.isnan(result.iloc[2][COL_D_ABOVE]) or not math.isnan(result.iloc[2][COL_D_BELOW])


def test_current_incomplete_bracket_is_excluded():
    """Bars within the current incomplete bracket don't affect NearestAbove/Below."""
    rows = [
        # Bracket A: 09:30-10:00
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
        # Bracket B (current, incomplete): 10:00-10:30
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=105.00, low=104.00, close=104.50),
        _rth_bar(_rth_ts("2026-06-02", 10, 15), high=105.00, low=104.00, close=104.50),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # At 10:00 and 10:15 (inside bracket B):
    # Only bracket A is complete → SP prices are 100.00, 100.25, 100.50.
    # Bracket B's bins (104.xx) should NOT influence the SP set.
    for i in [1, 2]:
        above = result.iloc[i][COL_D_ABOVE]
        below = result.iloc[i][COL_D_BELOW]
        # SP prices from bracket A are around 100.0-100.5; close is 104.50.
        # NearestAbove: no SP > 104.50 → NaN.
        assert math.isnan(above), f"Row {i}: NearestAbove should be NaN (no SP above 104.50), got {above}"
        # NearestBelow: closest SP < 104.50 is 100.50.
        assert abs(below - 100.50) < 1e-9, f"Row {i}: NearestBelow should be 100.50, got {below}"


def test_nearest_above_strict_comparison():
    """NearestAbove uses strict > comparison; price equal to close is excluded."""
    rows = [
        # Bracket A: single bin exactly at close price.
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.25),
        # After bracket A completes, with close exactly at 100.25 → no SP strictly above.
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.25, low=100.00, close=100.25),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    # close = 100.25; SP bins include 100.0 and 100.25.
    # NearestAbove: no SP strictly > 100.25 → NaN.
    assert math.isnan(result.iloc[2][COL_D_ABOVE])
    # NearestBelow: closest SP < 100.25 → 100.00.
    assert abs(result.iloc[2][COL_D_BELOW] - 100.00) < 1e-9


def test_nearest_below_strict_comparison():
    """NearestBelow uses strict < comparison; price equal to close is excluded."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.00),
        _rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.25, low=100.00, close=100.00),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    # close = 100.00; SP bins include 100.0 and 100.25.
    # NearestBelow: no SP strictly < 100.00 → NaN.
    assert math.isnan(result.iloc[2][COL_D_BELOW])
    # NearestAbove: closest SP > 100.00 → 100.25.
    assert abs(result.iloc[2][COL_D_ABOVE] - 100.25) < 1e-9


def test_developing_sp_update_as_new_bracket_completes():
    """Developing SP values change (causally) when a new 30-min bracket completes."""
    df = _sp_fixture_session1()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # Before bracket B completes (rows 0: 09:30 bar):
    # Only bracket A has bins 400-404 (100.0-101.0). All are SP (only 1 bracket).
    # After bracket C completes at 11:00 (row 3):
    # Brackets A and C overlap → bins 400-404 no longer SP. Only B's bins (405-408) are SP.

    # Row 0 (09:30): bracket A not yet complete → NaN.
    assert math.isnan(result.iloc[0][COL_D_ABOVE])

    # Row 3 (11:00, after bracket C completes):
    # Only bracket B bins remain as SP → NearestAbove above close 101.00 = 101.25
    d_above_row3 = result.iloc[3][COL_D_ABOVE]
    assert not math.isnan(d_above_row3)
    assert abs(d_above_row3 - 101.25) < 1e-9


# ---------------------------------------------------------------------------
# 5. Prior-session Single Prints
# ---------------------------------------------------------------------------


def test_prior_session_sp_maps_to_next_session():
    """Prior-session SP prices become available in session 2 RTH bars."""
    df = _sp_fixture_two_sessions()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # Session 2 starts at row 7 (09:30 on 2026-06-03).
    # Prior session (session 1) had SP prices from bracket B: 101.25, 101.50, 101.75, 102.00.
    # close at s2 row 0 = 105.50 → pNearestAbove = NaN (no SP above 105.50).
    # pNearestBelow = 102.00 (closest SP below 105.50).
    s2_row0 = result.iloc[7]  # session 2 first RTH bar
    p_below = s2_row0[COL_P_BELOW]
    assert not math.isnan(p_below), "pNearestBelow should be set from prior session"
    assert abs(p_below - 102.00) < 1e-9, f"Expected 102.00, got {p_below}"
    assert math.isnan(s2_row0[COL_P_ABOVE]), "pNearestAbove should be NaN (no prior SP above 105.50)"


def test_prior_session_values_are_frozen():
    """Prior-session SP values do not change as current-session bars arrive."""
    df = _sp_fixture_two_sessions()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # Session 2 RTH rows are at indices 7, 8, 9, 10, 11.
    # pNearestBelow depends only on the prior-session SP set and the current close.
    # The prior-session SP *set* must not change between rows 7-11 (it's frozen).
    # But NearestBelow changes with close, which is correct (same SP set, different bar).
    # Verify pNearestBelow at row 8 (close=107.50 → prior SP below 107.50 = 102.00).
    s2_row1 = result.iloc[8]
    assert abs(s2_row1[COL_P_BELOW] - 102.00) < 1e-9


def test_prior_session_nan_when_no_prior_sp():
    """If the prior session had no Single Prints, prior-session columns are NaN."""
    rows = [
        # Session 1: only one bracket, but two bars with identical H/L (same bins in bracket A only).
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.10),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.10),
        _rth_bar(_rth_ts("2026-06-02", 10, 30), high=100.25, low=100.00, close=100.10),
        # Session 1 bracket A and C are identical bins → NOT SP.
        # Session 1 bracket B is unique → those are SP. But in this fixture we have:
        # Actually let me make session 1 have NO unique brackets:
        # A: 100.00-100.25, B: 100.00-100.25, C: 100.00-100.25 (all overlap) → 0 SP.
    ]
    # Override with truly overlapping brackets.
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.10),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.10),
        _rth_bar(_rth_ts("2026-06-02", 10, 30), high=100.25, low=100.00, close=100.10),
        _rth_bar(_rth_ts("2026-06-02", 11, 0), high=100.25, low=100.00, close=100.10),
        # ETH gap
        _eth_bar(pd.Timestamp("2026-06-02 17:00", tz=TZ), 100.0, 99.0, 99.5),
        # Session 2
        _rth_bar(_rth_ts("2026-06-03", 9, 30), high=103.00, low=102.00, close=102.50),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    # Session 1 brackets A, B, C all cover 100.0-100.25 → all bins touched 3 times → 0 SP.
    # Session 2 prior SP = empty → pNearestAbove and pNearestBelow must be NaN.
    s2_row = result.iloc[5]
    assert math.isnan(s2_row[COL_P_ABOVE]), "pNearestAbove should be NaN (no prior SP)"
    assert math.isnan(s2_row[COL_P_BELOW]), "pNearestBelow should be NaN (no prior SP)"


# ---------------------------------------------------------------------------
# 6. RTH / ETH behavior
# ---------------------------------------------------------------------------


def test_eth_bars_do_not_contribute_to_sp():
    """ETH bars are excluded from the bracket computation."""
    rows = [
        # ETH bar with extreme range that would dominate if included.
        _eth_bar(_rth_ts("2026-06-02", 8, 0), high=200.00, low=50.00, close=125.00),
        # RTH bracket A
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.25, low=100.00, close=100.10),
        # After bracket A completes
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.25, low=100.00, close=100.00),
        _rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.25, low=100.00, close=100.00),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)

    # ETH bar at 08:00 should not contribute.
    # SP prices should come only from bracket A (100.00-100.25 bins).
    # At row 2 (10:00, close=100.00):
    row_after = result.iloc[2]
    # NearestAbove should be 100.25 (from bracket A only).
    assert not math.isnan(row_after[COL_D_ABOVE])
    assert abs(row_after[COL_D_ABOVE] - 100.25) < 1e-9
    # NearestAbove must NOT be something extreme like 200.00.
    assert row_after[COL_D_ABOVE] < 150.0


def test_eth_bars_emit_nan_for_developing_sp():
    """Non-RTH bars emit NaN for developing Single Print columns."""
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.50, low=100.00, close=100.00),
        _eth_bar(pd.Timestamp("2026-06-02 16:30", tz=TZ), high=100.25, low=99.75, close=100.00),
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    eth_row = result.iloc[2]
    assert math.isnan(eth_row[COL_D_ABOVE])
    assert math.isnan(eth_row[COL_D_BELOW])


def test_eth_bars_emit_nan_for_prior_session_sp():
    """Non-RTH bars emit NaN for prior Single Print columns."""
    df = _sp_fixture_two_sessions()
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    # Rows 5 and 6 are ETH bars.
    for i in [5, 6]:
        eth_row = result.iloc[i]
        assert math.isnan(eth_row[COL_P_ABOVE]), f"Row {i}: pNearestAbove should be NaN in ETH"
        assert math.isnan(eth_row[COL_P_BELOW]), f"Row {i}: pNearestBelow should be NaN in ETH"


def test_session_column_can_be_absent():
    """When session column is absent, it is derived from instrument config."""
    # Build a DataFrame without a session column — compute_tpo_levels should derive it.
    rows = [
        {
            "timestamp": pd.Timestamp("2026-06-02 09:30", tz=TZ),
            "open": 100.0, "high": 100.50, "low": 100.00, "close": 100.25, "volume": 10.0,
        },
        {
            "timestamp": pd.Timestamp("2026-06-02 10:00", tz=TZ),
            "open": 100.0, "high": 100.50, "low": 100.00, "close": 100.00, "volume": 10.0,
        },
        {
            "timestamp": pd.Timestamp("2026-06-02 10:01", tz=TZ),
            "open": 100.0, "high": 100.50, "low": 100.00, "close": 100.00, "volume": 10.0,
        },
    ]
    df = pd.DataFrame(rows)
    result = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == set(SINGLE_PRINT_COLUMNS)


# ---------------------------------------------------------------------------
# 7. Point-in-time / future-shock
# ---------------------------------------------------------------------------


def test_future_shock_appending_current_session_bars_does_not_change_prior_values():
    """Appending future bars to the current session must not alter earlier SP values."""
    base_rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), high=100.50, low=100.00, close=100.25),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), high=100.75, low=100.25, close=100.50),
        _rth_bar(_rth_ts("2026-06-02", 10, 1), high=100.75, low=100.25, close=100.50),
    ]
    future_rows = [
        _rth_bar(_rth_ts("2026-06-02", 10, 30), high=102.00, low=101.00, close=101.50),
        _rth_bar(_rth_ts("2026-06-02", 11, 0), high=102.00, low=101.00, close=101.50),
        _rth_bar(_rth_ts("2026-06-02", 11, 1), high=102.00, low=101.00, close=101.50),
    ]

    df_base = pd.DataFrame(base_rows)
    df_extended = pd.DataFrame(base_rows + future_rows)

    result_base = compute_tpo_levels(df_base, instrument="ES", single_prints_enabled=True)
    result_extended = compute_tpo_levels(df_extended, instrument="ES", single_prints_enabled=True)

    # Values at the three base rows must not change when future rows are appended.
    for i in range(len(base_rows)):
        for col in SINGLE_PRINT_COLUMNS:
            v_base = result_base.iloc[i][col]
            v_ext = result_extended.iloc[i][col]
            both_nan = math.isnan(v_base) and math.isnan(v_ext)
            if not both_nan:
                assert abs(v_base - v_ext) < 1e-9, (
                    f"Row {i}, {col}: future-shock mismatch. "
                    f"base={v_base}, extended={v_ext}"
                )


def test_future_shock_appending_next_session_bars_does_not_change_prior_session_sp():
    """Appending next-session bars must not alter prior-session SP values at earlier timestamps."""
    df_base = _sp_fixture_two_sessions()
    # Add more session-2 bars.
    extra_rows = [
        _rth_bar(_rth_ts("2026-06-03", 11, 30), high=110.00, low=109.00, close=109.50),
        _rth_bar(_rth_ts("2026-06-03", 12, 0), high=110.00, low=109.00, close=109.50),
    ]
    df_extended = pd.concat([df_base, pd.DataFrame(extra_rows)], ignore_index=True)

    result_base = compute_tpo_levels(df_base, instrument="ES", single_prints_enabled=True)
    result_extended = compute_tpo_levels(df_extended, instrument="ES", single_prints_enabled=True)

    # Verify prior-session SP columns at all rows in the original fixture are unchanged.
    for i in range(len(df_base)):
        for col in [COL_P_ABOVE, COL_P_BELOW]:
            v_base = result_base.iloc[i][col]
            v_ext = result_extended.iloc[i][col]
            both_nan = math.isnan(v_base) and math.isnan(v_ext)
            if not both_nan:
                assert abs(v_base - v_ext) < 1e-9, (
                    f"Row {i}, {col}: future-shock mismatch in prior-session values."
                )


def test_unsorted_input_produces_same_result_as_sorted_input():
    """Output is consistent regardless of input row order (internal sort is applied)."""
    df = _sp_fixture_two_sessions()
    df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)

    result_sorted = compute_tpo_levels(df, instrument="ES", single_prints_enabled=True)
    result_shuffled = compute_tpo_levels(df_shuffled, instrument="ES", single_prints_enabled=True)

    # Both results are sorted by timestamp internally → same values in timestamp order.
    # The indices may differ (RangeIndex based on sorted order), so compare by merging on timestamp.
    ts_sorted = df.sort_values("timestamp").reset_index(drop=True)["timestamp"]
    ts_shuffled = df_shuffled.sort_values("timestamp").reset_index(drop=True)["timestamp"]
    pd.testing.assert_series_equal(ts_sorted, ts_shuffled, check_names=False)

    for col in SINGLE_PRINT_COLUMNS:
        vals_sorted = result_sorted[col].values
        vals_shuffled = result_shuffled[col].values
        for v1, v2 in zip(vals_sorted, vals_shuffled):
            both_nan = math.isnan(v1) and math.isnan(v2)
            if not both_nan:
                assert abs(v1 - v2) < 1e-9, f"{col}: sorted vs shuffled mismatch"


# ---------------------------------------------------------------------------
# 8. Settings validation
# ---------------------------------------------------------------------------


def test_sp_enabled_naive_timestamp_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_tpo_levels(_naive_df(), instrument="ES", single_prints_enabled=True)


def test_sp_enabled_unsupported_instrument_raises():
    df = tag_session(_base_df(), "ES")
    df["instrument"] = "FAKE"  # column irrelevant; pass as kwarg
    with pytest.raises(ValueError, match="Unsupported instrument"):
        compute_tpo_levels(df, instrument="FAKE", single_prints_enabled=True)


def test_nq_instrument_supported():
    df = tag_session(_base_df(), "NQ")
    result = compute_tpo_levels(df, instrument="NQ", single_prints_enabled=True)
    assert set(result.columns) == set(SINGLE_PRINT_COLUMNS)


# ---------------------------------------------------------------------------
# 9. Regression safety
# ---------------------------------------------------------------------------


def _compute_baseline(df: pd.DataFrame) -> pd.DataFrame:
    return compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
    )


def test_sp_disabled_existing_outputs_unchanged():
    """Existing level output columns are identical whether SP is disabled (default) or not."""
    df = tag_session(_base_df(), "ES")
    baseline = _compute_baseline(df)
    with_sp_disabled = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
        single_prints_enabled=False,
    )
    assert set(baseline.columns) == set(with_sp_disabled.columns)
    for col in baseline.columns:
        pd.testing.assert_series_equal(baseline[col], with_sp_disabled[col], check_names=True)


def test_pivots_and_dvwap_unchanged_when_sp_enabled():
    """Enabling SP does not change pivots or dVWAP columns."""
    df = tag_session(_base_df(), "ES")

    out_base = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        pivots_enabled=True,
        session_vwap_enabled=True,
        single_prints_enabled=False,
    )
    out_with_sp = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        pivots_enabled=True,
        session_vwap_enabled=True,
        single_prints_enabled=True,
    )

    # Pivot columns must be identical.
    pivot_cols = [c for c in out_base.columns if c.startswith("Pivot_")]
    for col in pivot_cols:
        pd.testing.assert_series_equal(out_base[col], out_with_sp[col])

    # dVWAP_RTH must be identical.
    assert "dVWAP_RTH" in out_base.columns
    pd.testing.assert_series_equal(out_base["dVWAP_RTH"], out_with_sp["dVWAP_RTH"])


def test_compute_all_levels_sp_enabled_adds_only_sp_columns():
    """Enabling SP in compute_all_levels adds exactly and only the four SP columns."""
    df = tag_session(_base_df(), "ES")
    baseline = _compute_baseline(df)
    with_sp = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
        single_prints_enabled=True,
    )
    new_cols = set(with_sp.columns) - set(baseline.columns)
    assert new_cols == set(SINGLE_PRINT_COLUMNS), f"Unexpected new columns: {new_cols}"
