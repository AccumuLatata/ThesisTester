"""Pivot level computation stubs — Stage 1 plumbing only.

Full pivot logic (confirmed fractal pivots, multi-timeframe alignment, non-repainting
confirmation delay) will be implemented in Stage 2.  Until then every public function
in this module returns an empty DataFrame so that ``compute_all_levels`` can wire these
calls behind settings gates without any behaviour change.

Planned output columns (Stage 2):
    Pivot_1m_High, Pivot_1m_Low
    Pivot_5m_High, Pivot_5m_Low
    Pivot_30m_High, Pivot_30m_Low
    Pivot_4h_High, Pivot_4h_Low

Each column will hold the most-recent confirmed pivot level for that timeframe and side.
A pivot at candle k becomes visible only after R right-side candles have closed
(default left=2, right=2).  No repainting.
"""
from __future__ import annotations

import pandas as pd

from .common import require_tz_aware_timestamp

# Timeframes that will be supported when Stage 2 is implemented.
SUPPORTED_PIVOT_TIMEFRAMES: tuple[str, ...] = ("1min", "5min", "30min", "4h")

# Default fractal-window sizes (left/right candle count for confirmation).
DEFAULT_PIVOT_LEFT: int = 2
DEFAULT_PIVOT_RIGHT: int = 2


def compute_pivot_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    pivot_timeframes: list[str] | tuple[str, ...] | None = None,
    pivot_left: int = DEFAULT_PIVOT_LEFT,
    pivot_right: int = DEFAULT_PIVOT_RIGHT,
    *,
    enabled: bool = False,
) -> pd.DataFrame:
    """Return pivot level columns aligned to *df*'s index.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column.  Must already
        have its index set (or the timestamp column available) so the returned
        DataFrame can be joined back by the caller.
    instrument:
        Instrument key (e.g. ``"ES"``).  Reserved for Stage 2 tick-size/session
        configuration.
    pivot_timeframes:
        Timeframes for which to compute pivots.  Supported values (Stage 2):
        ``"1min"``, ``"5min"``, ``"30min"``, ``"4h"``.  ``None`` means all
        supported timeframes.
    pivot_left:
        Number of left-side candles required for fractal confirmation.
    pivot_right:
        Number of right-side candles required for fractal confirmation.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately so that no new columns are added by ``compute_all_levels``.

    Returns
    -------
    pd.DataFrame
        Empty DataFrame when ``enabled=False`` (Stage 1 no-op).
        Will return pivot columns aligned to *df*'s index in Stage 2.
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)

    # Stage 2 implementation will go here.
    raise NotImplementedError(  # pragma: no cover
        "Pivot level computation is not yet implemented.  "
        "Set enabled=False (the default) until Stage 2 is merged."
    )
