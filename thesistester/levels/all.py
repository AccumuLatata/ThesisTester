"""Combined full level computation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .apoc import compute_apoc_levels
from .apoc_tick import APOC_PROFILE_SOURCE_TYPICAL_MVP_V1
from .indicators import compute_indicator_levels
from .pivots import compute_pivot_levels
from .prev30m_vwap import compute_prev30m_vwap_levels
from .profile import compute_profile_levels
from .rolling_poc_tick import ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
from .session_vwap import compute_session_vwap_levels
from .sessions import compute_session_levels
from .tpo import compute_tpo_levels

if TYPE_CHECKING:
    from .apoc_tick import APeriodTickProfileTable
    from .tick_vap import PriorProfileTable


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
    prior_profile_table: PriorProfileTable | None = None,
    # --- Stage 1 settings gates (all disabled by default) ---
    pivots_enabled: bool = False,
    pivot_timeframes: list[str] | tuple[str, ...] | None = None,
    pivot_left: int = 2,
    pivot_right: int = 2,
    session_vwap_enabled: bool = False,
    session_vwap_anchor: str = "RTH",
    single_prints_enabled: bool = False,
    apoc_enabled: bool = False,
    apoc_profile_source: str = APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
    apoc_tick_table: APeriodTickProfileTable | None = None,
    tick_paths: Sequence[str | Path] | None = None,
    prev30m_vwap_enabled: bool = False,
    prev30m_vwap_validity_periods: int = 1,
    rolling_poc_profile_source: str = ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
) -> pd.DataFrame:
    """Compute Phase 2 + Phase 3 levels in one timeline-aligned DataFrame.

    New level families (pivots, session VWAP, TPO single prints, APOC/pAPOC) are
    wired in here but controlled by the following gates, all disabled by default:

    - ``pivots_enabled`` — fractal pivot levels (Stage 2, **implemented**)
    - ``session_vwap_enabled`` — developing session VWAPs (Stage 3 / WMV1):
      ``dVWAP_RTH`` (RTH-anchored), ``dVWAP`` (full CME session),
      ``wVWAP`` (current trading week), and ``mVWAP`` (current trading month);
      ``session_vwap_anchor`` remains ``"RTH"`` for the RTH column gate
    - ``single_prints_enabled`` — TPO single print nearest-above/below
      (Stage 4, **implemented**)
    - ``apoc_enabled`` — APOC / pAPOC profile-based levels (Stage 5 / AP2,
      **implemented**; routes to ``compute_apoc_levels``, independent of
      ``single_prints_enabled``). Library default source is
      ``typical_mvp_v1``. ``tick_last_volume_v1`` is an explicit opt-in and
      requires Quantower Tick–Tick–Last inputs (or a prebuilt A-period
      table). ``apoc_enabled=False`` remains a true no-op.
    - ``prev30m_vwap_enabled`` — previous 30m VWAP (``prev30mVWAP``) with
        early-window hit diagnostics; ``prev30m_vwap_validity_periods > 1``
        also emits stack columns ``prev30mVWAP_2``…``_N`` (Stage 8 /
        Phases 1–3, **implemented**)
    - Rolling POC is tick Last×Volume by default (``tick_last_volume_v1``).
      Missing ticks emit all-NaN ``POC_rolling_*``; they never fall back to
      typical. APOC library default remains typical (separate follow-up).

    With all new gates at their defaults, session / indicator / VA-omit /
    APOC-off output matches the pre-Stage-1 additive contract. Rolling POC
    is the exception: default is now tick (NaN without ``tick_paths``).

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
        prior_profile_table=prior_profile_table,
        rolling_poc_profile_source=rolling_poc_profile_source,
        tick_paths=tick_paths,
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
        apoc_profile_source=apoc_profile_source,
        apoc_tick_table=apoc_tick_table,
        tick_paths=tick_paths,
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
