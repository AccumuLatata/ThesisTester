"""Combined full level computation helpers."""

from __future__ import annotations

import pandas as pd

from .apoc import compute_apoc_levels
from .indicators import compute_indicator_levels
from .pivots import compute_pivot_levels
from .prev30m_vwap import compute_prev30m_vwap_levels
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
    prev30m_vwap_enabled: bool = False,
    prev30m_vwap_validity_periods: int = 1,
) -> pd.DataFrame:
    """Compute Phase 2 + Phase 3 levels in one timeline-aligned DataFrame.

    New level families (pivots, session VWAP, TPO single prints, APOC/pAPOC) are
    wired in here but controlled by the following gates, all disabled by default:

    - ``pivots_enabled`` — fractal pivot levels (Stage 2, **implemented**)
    - ``session_vwap_enabled`` — developing session VWAPs (Stage 3):
      ``dVWAP_RTH`` (RTH-anchored) and ``dVWAP`` (full CME session);
      ``session_vwap_anchor`` remains ``"RTH"`` for the RTH column gate
    - ``single_prints_enabled`` — TPO single print nearest-above/below
      (Stage 4, **implemented**)
    - ``apoc_enabled`` — APOC / pAPOC profile-based levels (Stage 5,
      **implemented**; routes to ``compute_apoc_levels``, independent of
      ``single_prints_enabled``)
    - ``prev30m_vwap_enabled`` — previous 30m VWAP (``prev30mVWAP``) with
      early-window hit diagnostics; ``prev30m_vwap_validity_periods > 1``
      also emits stack columns ``prev30mVWAP_2``…``_N`` (Stage 8 /
      Phases 1–3, **implemented**)

    With all new gates at their defaults the output is **identical** to the
    pre-Stage-1 output.

    Single Prints and APOC/pAPOC are independent level families.  Single Prints
    are TPO auction-structure levels implemented in ``tpo.py``.  APOC/pAPOC are
    profile/POC levels implemented in ``apoc.py``.  They may share session and
    tick-size utilities, but APOC is not derived from Single Prints.
    """
    session_df = compute_session_levels(
        df, instrument=instrument, opening_range_minutes=opening_range_minutes
    )
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
    # Single Prints: TPO auction-structure levels (tpo.py).
    tpo_df = compute_tpo_levels(
        df,
        instrument=instrument,
        single_prints_enabled=single_prints_enabled,
    )
    # APOC / pAPOC: profile-based levels (apoc.py) — independent of Single Prints.
    apoc_df = compute_apoc_levels(
        df,
        instrument=instrument,
        enabled=apoc_enabled,
    )
    prev30m_df = compute_prev30m_vwap_levels(
        df,
        instrument=instrument,
        enabled=prev30m_vwap_enabled,
        validity_periods=prev30m_vwap_validity_periods,
    )

    base_columns = set(df.columns)
    out = session_df.copy()

    for extra_df in (
        indicator_df,
        profile_df,
        pivot_df,
        session_vwap_df,
        tpo_df,
        apoc_df,
        prev30m_df,
    ):
        new_cols = [
            col for col in extra_df.columns if col not in base_columns and col not in out.columns
        ]
        if new_cols:
            out = out.join(extra_df[new_cols])

    return out
