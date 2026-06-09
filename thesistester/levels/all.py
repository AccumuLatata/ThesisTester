"""Combined full level computation helpers."""
from __future__ import annotations

import pandas as pd

from .indicators import compute_indicator_levels
from .pivots import compute_pivot_levels
from .profile import compute_profile_levels
from .session_vwap import compute_session_vwap_levels
from .sessions import compute_session_levels
from .tpo import compute_tpo_levels


def compute_all_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    opening_range_minutes: int = 30,
    sma_lengths: list[int] | tuple[int, ...] | None = None,
    ema_lengths: list[int] | tuple[int, ...] | None = None,
    sma_timeframes: list[str] | tuple[str, ...] | None = None,
    ema_timeframes: list[str] | tuple[str, ...] | None = None,
    vwap_windows: list[str] | tuple[str, ...] | None = None,
    poc_windows: list[str] | tuple[str, ...] | None = None,
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = 1,
    prior_week_aggregation_ticks: int = 1,
    prior_month_aggregation_ticks: int = 1,
    # --- Stage 1 settings gates (all disabled by default) ---
    pivots_enabled: bool = False,
    pivot_timeframes: list[str] | tuple[str, ...] | None = None,
    pivot_left: int = 2,
    pivot_right: int = 2,
    session_vwap_enabled: bool = False,
    session_vwap_anchor: str = "RTH",
    single_prints_enabled: bool = False,
    apoc_enabled: bool = False,
) -> pd.DataFrame:
    """Compute Phase 2 + Phase 3 levels in one timeline-aligned DataFrame.

    New level families (pivots, session VWAP, TPO single prints, APOC/pAPOC) are
    wired in here but controlled by the following gates, all disabled by default:

    - ``pivots_enabled`` — fractal pivot levels (Stage 2)
    - ``session_vwap_enabled`` — developing session VWAP (Stage 3)
    - ``single_prints_enabled`` — TPO single print nearest-above/below (Stage 4)
    - ``apoc_enabled`` — APOC / pAPOC (Stage 5)

    Enabling any of these gates will raise ``NotImplementedError`` until the
    corresponding implementation stage is merged.  With all new gates at their
    defaults the output is **identical** to the pre-Stage-1 output.
    """
    session_df = compute_session_levels(df, instrument=instrument, opening_range_minutes=opening_range_minutes)
    indicator_df = compute_indicator_levels(
        df,
        sma_lengths=sma_lengths,
        ema_lengths=ema_lengths,
        sma_timeframes=sma_timeframes,
        ema_timeframes=ema_timeframes,
        vwap_windows=vwap_windows,
    )
    profile_df = compute_profile_levels(
        df,
        instrument=instrument,
        rolling_windows=poc_windows,
        value_area_pct=value_area_pct,
        prior_day_aggregation_ticks=prior_day_aggregation_ticks,
        prior_week_aggregation_ticks=prior_week_aggregation_ticks,
        prior_month_aggregation_ticks=prior_month_aggregation_ticks,
    )
    pivot_df = compute_pivot_levels(
        df,
        instrument=instrument,
        pivot_timeframes=pivot_timeframes,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        enabled=pivots_enabled,
    )
    session_vwap_df = compute_session_vwap_levels(
        df,
        instrument=instrument,
        anchor=session_vwap_anchor,
        enabled=session_vwap_enabled,
    )
    tpo_df = compute_tpo_levels(
        df,
        instrument=instrument,
        single_prints_enabled=single_prints_enabled,
        apoc_enabled=apoc_enabled,
    )

    base_columns = set(df.columns)
    out = session_df.copy()

    for extra_df in (indicator_df, profile_df, pivot_df, session_vwap_df, tpo_df):
        new_cols = [col for col in extra_df.columns if col not in base_columns and col not in out.columns]
        if new_cols:
            out = out.join(extra_df[new_cols])

    return out
