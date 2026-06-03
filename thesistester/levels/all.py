"""Combined full level computation helpers."""
from __future__ import annotations

import pandas as pd

from .indicators import compute_indicator_levels
from .profile import compute_profile_levels
from .sessions import compute_session_levels


def compute_all_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    opening_range_minutes: int = 30,
    sma_lengths: list[int] | tuple[int, ...] | None = None,
    ema_lengths: list[int] | tuple[int, ...] | None = None,
    vwap_windows: list[str] | tuple[str, ...] | None = None,
    poc_windows: list[str] | tuple[str, ...] | None = None,
    value_area_pct: float = 0.70,
) -> pd.DataFrame:
    """Compute Phase 2 + Phase 3 levels in one timeline-aligned DataFrame."""
    session_df = compute_session_levels(df, instrument=instrument, opening_range_minutes=opening_range_minutes)
    indicator_df = compute_indicator_levels(
        df,
        sma_lengths=sma_lengths,
        ema_lengths=ema_lengths,
        vwap_windows=vwap_windows,
    )
    profile_df = compute_profile_levels(
        df,
        instrument=instrument,
        rolling_windows=poc_windows,
        value_area_pct=value_area_pct,
    )

    base_columns = set(df.columns)
    out = session_df.copy()

    indicator_cols = [col for col in indicator_df.columns if col not in base_columns and col not in out.columns]
    profile_cols = [col for col in profile_df.columns if col not in base_columns and col not in out.columns]
    out = out.join(indicator_df[indicator_cols])
    out = out.join(profile_df[profile_cols])
    return out
