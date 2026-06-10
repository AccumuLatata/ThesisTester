"""Stage 1 regression and plumbing tests.

Verifies:
- New modules are importable.
- ``compute_pivot_levels``, ``compute_session_vwap_levels``, and ``compute_tpo_levels``
  return empty DataFrames (no new columns) when all gates are disabled (the default).
- ``compute_all_levels`` output is identical to pre-Stage-1 behavior when all new
  settings are absent or explicitly disabled.
- No new level columns appear with default settings.
- Existing level columns are unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import (
    compute_all_levels,
    compute_pivot_levels,
    compute_session_vwap_levels,
    compute_tpo_levels,
)
from thesistester.levels.pivots import (
    DEFAULT_PIVOT_LEFT,
    DEFAULT_PIVOT_RIGHT,
    SUPPORTED_PIVOT_TIMEFRAMES,
)
from thesistester.levels.session_vwap import (
    DEFAULT_VWAP_ANCHOR,
    SUPPORTED_VWAP_ANCHORS,
)
from thesistester.levels.tpo import (
    TPO_BRACKET_MINUTES,
)


TZ = "America/New_York"

# -------------------------------------------------------------------
# Shared fixtures
# -------------------------------------------------------------------

def _base_df(start: str = "2026-06-02 09:30:00", periods: int = 20, freq: str = "1min") -> pd.DataFrame:
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


# -------------------------------------------------------------------
# 1. Import / public API surface
# -------------------------------------------------------------------

def test_new_modules_importable():
    """All three Stage 1 modules must be importable without errors."""
    import thesistester.levels.pivots as p
    import thesistester.levels.session_vwap as sv
    import thesistester.levels.tpo as t

    assert callable(p.compute_pivot_levels)
    assert callable(sv.compute_session_vwap_levels)
    assert callable(t.compute_tpo_levels)


def test_new_modules_exported_from_package():
    """New compute functions must be re-exported from ``thesistester.levels``."""
    from thesistester.levels import (
        compute_pivot_levels,
        compute_session_vwap_levels,
        compute_tpo_levels,
    )

    assert callable(compute_pivot_levels)
    assert callable(compute_session_vwap_levels)
    assert callable(compute_tpo_levels)


def test_new_modules_in_all_list():
    import thesistester.levels as lvl

    assert "compute_pivot_levels" in lvl.__all__
    assert "compute_session_vwap_levels" in lvl.__all__
    assert "compute_tpo_levels" in lvl.__all__


# -------------------------------------------------------------------
# 2. Settings constants are well-defined
# -------------------------------------------------------------------

def test_pivot_defaults():
    assert DEFAULT_PIVOT_LEFT == 2
    assert DEFAULT_PIVOT_RIGHT == 2
    assert "1min" in SUPPORTED_PIVOT_TIMEFRAMES
    assert "5min" in SUPPORTED_PIVOT_TIMEFRAMES
    assert "30min" in SUPPORTED_PIVOT_TIMEFRAMES
    assert "4h" in SUPPORTED_PIVOT_TIMEFRAMES


def test_vwap_defaults():
    assert DEFAULT_VWAP_ANCHOR == "RTH"
    assert "RTH" in SUPPORTED_VWAP_ANCHORS


def test_tpo_bracket_minutes():
    assert TPO_BRACKET_MINUTES == 30


# -------------------------------------------------------------------
# 3. Disabled (default) stubs return empty DataFrames
# -------------------------------------------------------------------

def test_compute_pivot_levels_disabled_returns_empty_df():
    df = _base_df()
    result = compute_pivot_levels(df, enabled=False)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0
    assert len(result) == len(df)


def test_compute_pivot_levels_default_is_disabled():
    df = _base_df()
    result = compute_pivot_levels(df)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_compute_session_vwap_levels_disabled_returns_empty_df():
    df = _base_df()
    result = compute_session_vwap_levels(df, enabled=False)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0
    assert len(result) == len(df)


def test_compute_session_vwap_levels_default_is_disabled():
    df = _base_df()
    result = compute_session_vwap_levels(df)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_compute_tpo_levels_both_disabled_returns_empty_df():
    df = _base_df()
    result = compute_tpo_levels(df, single_prints_enabled=False, apoc_enabled=False)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0
    assert len(result) == len(df)


def test_compute_tpo_levels_default_is_disabled():
    df = _base_df()
    result = compute_tpo_levels(df)

    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


# -------------------------------------------------------------------
# 4. compute_all_levels regression: no new columns with default settings
# -------------------------------------------------------------------

_KNOWN_LEVEL_COLUMNS = [
    "RTH_Open",
    "pONH",
    "pONL",
    "pRTH_Open",
    "SMA_2",
    "EMA_2",
    "VWAP_rolling_15min",
    "POC_rolling_30min",
    "pdVAH",
    "pdPOC",
]


def _compute_baseline(df):
    """Reference call matching pre-Stage-1 signature."""
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


def test_compute_all_levels_no_new_columns_with_default_settings():
    df = tag_session(_base_df(), "ES")
    out_before = _compute_baseline(df)

    # Stage 1 new args all default to disabled — result must be identical.
    out_after = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
        # All new Stage 1 gates explicitly disabled (matching defaults):
        pivots_enabled=False,
        session_vwap_enabled=False,
        single_prints_enabled=False,
        apoc_enabled=False,
    )

    assert set(out_before.columns) == set(out_after.columns)


def test_compute_all_levels_existing_columns_unchanged():
    df = tag_session(_base_df(), "ES")
    out = _compute_baseline(df)

    for col in _KNOWN_LEVEL_COLUMNS:
        assert col in out.columns, f"Expected column {col!r} missing from output"


def test_compute_all_levels_new_stage1_settings_absent_produce_no_pivot_columns():
    df = tag_session(_base_df(), "ES")
    out = _compute_baseline(df)

    pivot_cols = [c for c in out.columns if c.startswith("Pivot_")]
    assert pivot_cols == [], f"Unexpected pivot columns: {pivot_cols}"


def test_compute_all_levels_new_stage1_settings_absent_produce_no_vwap_columns():
    df = tag_session(_base_df(), "ES")
    out = _compute_baseline(df)

    dvwap_cols = [c for c in out.columns if c.startswith("dVWAP_")]
    assert dvwap_cols == [], f"Unexpected dVWAP columns: {dvwap_cols}"


def test_compute_all_levels_new_stage1_settings_absent_produce_no_sp_columns():
    df = tag_session(_base_df(), "ES")
    out = _compute_baseline(df)

    sp_cols = [c for c in out.columns if "SinglePrint" in c]
    assert sp_cols == [], f"Unexpected SinglePrint columns: {sp_cols}"


def test_compute_all_levels_new_stage1_settings_absent_produce_no_apoc_columns():
    df = tag_session(_base_df(), "ES")
    out = _compute_baseline(df)

    apoc_cols = [c for c in out.columns if c in ("APOC", "pAPOC")]
    assert apoc_cols == [], f"Unexpected APOC columns: {apoc_cols}"


# -------------------------------------------------------------------
# 5. Explicit disabled gates in compute_all_levels also produce no new columns
# -------------------------------------------------------------------

def test_explicit_disabled_gates_no_new_columns():
    df = tag_session(_base_df(), "ES")
    out = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        ema_lengths=[2],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        value_area_pct=0.70,
        pivots_enabled=False,
        session_vwap_enabled=False,
        single_prints_enabled=False,
        apoc_enabled=False,
    )

    new_cols = [
        c for c in out.columns
        if c.startswith("Pivot_")
        or c.startswith("dVWAP_")
        or "SinglePrint" in c
        or c in ("APOC", "pAPOC")
    ]
    assert new_cols == [], f"Unexpected new level columns with all gates disabled: {new_cols}"


# -------------------------------------------------------------------
# 6. Other enabled Stage 1 stubs still raise NotImplementedError
# -------------------------------------------------------------------


def test_compute_session_vwap_levels_enabled_returns_dvwap_column():
    # Stage 3 is now implemented: enabled=True should return a DataFrame with
    # dVWAP_RTH rather than raising NotImplementedError.
    from thesistester.data.sessions import tag_session as _tag
    df = _tag(_base_df(), "ES")
    result = compute_session_vwap_levels(df, enabled=True)
    assert isinstance(result, pd.DataFrame)
    assert "dVWAP_RTH" in result.columns


def test_compute_tpo_levels_single_prints_enabled_returns_sp_columns():
    # Stage 4 is now implemented: single_prints_enabled=True should return a
    # DataFrame with the four Single Print columns rather than raising NotImplementedError.
    from thesistester.data.sessions import tag_session as _tag
    df = _tag(_base_df(), "ES")
    result = compute_tpo_levels(df, single_prints_enabled=True)
    assert isinstance(result, pd.DataFrame)
    sp_cols = {"dSinglePrint_30m_NearestAbove", "dSinglePrint_30m_NearestBelow",
               "pSinglePrint_30m_NearestAbove", "pSinglePrint_30m_NearestBelow"}
    assert sp_cols.issubset(set(result.columns))


def test_compute_tpo_levels_apoc_enabled_raises_value_error():
    """After Stage 5, apoc_enabled=True in compute_tpo_levels must raise ValueError."""
    df = _base_df()
    with pytest.raises(ValueError, match="compute_apoc_levels"):
        compute_tpo_levels(df, apoc_enabled=True)


# -------------------------------------------------------------------
# 7. Timestamp validation: disabled stubs are true no-ops;
#    enabled stubs require tz-aware timestamp
# -------------------------------------------------------------------

def _naive_df() -> pd.DataFrame:
    """DataFrame with a naive (tz-unaware) timestamp column."""
    df = _base_df()
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return df


# 7a. Disabled stubs accept naive timestamps (no validation when disabled).

def test_compute_pivot_levels_disabled_accepts_naive_timestamp():
    result = compute_pivot_levels(_naive_df(), enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_compute_session_vwap_levels_disabled_accepts_naive_timestamp():
    result = compute_session_vwap_levels(_naive_df(), enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


def test_compute_tpo_levels_disabled_accepts_naive_timestamp():
    result = compute_tpo_levels(_naive_df(), single_prints_enabled=False, apoc_enabled=False)
    assert isinstance(result, pd.DataFrame)
    assert len(result.columns) == 0


# 7b. Enabled stubs raise ValueError for naive timestamps.

def test_compute_pivot_levels_enabled_requires_tz_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_pivot_levels(_naive_df(), enabled=True)


def test_compute_session_vwap_levels_enabled_requires_tz_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_session_vwap_levels(_naive_df(), enabled=True)


def test_compute_tpo_levels_single_prints_enabled_requires_tz_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_tpo_levels(_naive_df(), single_prints_enabled=True)


def test_compute_tpo_levels_apoc_enabled_raises_value_error_for_naive():
    """apoc_enabled=True must raise ValueError immediately, even for naive timestamps."""
    with pytest.raises(ValueError, match="compute_apoc_levels"):
        compute_tpo_levels(_naive_df(), apoc_enabled=True)


# -------------------------------------------------------------------
# 8. Index alignment: empty stubs have the same length as input
# -------------------------------------------------------------------

def test_disabled_stubs_preserve_index_length():
    df = _base_df(periods=50)
    for fn, kwargs in [
        (compute_pivot_levels, {"enabled": False}),
        (compute_session_vwap_levels, {"enabled": False}),
        (compute_tpo_levels, {"single_prints_enabled": False, "apoc_enabled": False}),
    ]:
        result = fn(df, **kwargs)
        assert len(result) == len(df), f"{fn.__name__} length mismatch"
