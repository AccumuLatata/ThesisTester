"""Naked / untested level detection."""
from __future__ import annotations

import numpy as np
import pandas as pd


def flag_naked_levels(
    df: pd.DataFrame,
    level_columns: list[str],
    tick_size: float,
    touch_tolerance_ticks: int | float = 0,
) -> pd.DataFrame:
    """Append ``<level>_naked`` boolean columns to *df*.

    A level is **naked** (untested / virgin) when, after it first appears or
    its value changes, price has not yet traded back to it.

    Parameters
    ----------
    df:
        DataFrame with at least ``high`` and ``low`` columns, plus the
        level columns listed in *level_columns*.
    level_columns:
        Names of level columns to evaluate.  Unknown columns are silently
        skipped.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES/NQ).
    touch_tolerance_ticks:
        Number of ticks around the level price that counts as a touch.
        Default 0 means the bar's high-low range must literally bracket the
        level price.

    Returns
    -------
    pd.DataFrame
        Copy of *df* (reset integer index) with additional ``<level>_naked``
        boolean columns appended.  For example, if *level_columns* contains
        ``"ONH"`` and ``"pdPOC"`` the output will include ``"ONH_naked"``
        and ``"pdPOC_naked"``.

    Notes
    -----
    **MVP approximation.**  Formation is detected when a level column value
    either becomes non-NaN for the first time or its value changes from the
    prior bar.  The formation bar itself is never marked as tested — testing
    can only occur on subsequent bars.  Once a touch is detected the naked
    flag clears immediately on that bar.

    A touch at bar *i* satisfies:

    .. code-block:: text

        bar_low  <= level_price + touch_tolerance_ticks * tick_size
        bar_high >= level_price - touch_tolerance_ticks * tick_size

    Later versions may require formation timestamps specific to each level
    family (e.g. OR_High is only formed after the opening-range window
    closes, whereas pdHigh is known at the start of each new day).
    """
    tol = float(touch_tolerance_ticks) * float(tick_size)
    out = df.reset_index(drop=True).copy()

    highs = out["high"].to_numpy(dtype=float)
    lows = out["low"].to_numpy(dtype=float)
    n = len(out)

    for col in level_columns:
        if col not in out.columns:
            continue

        level_vals = out[col].to_numpy(dtype=float)
        naked = np.zeros(n, dtype=bool)

        is_naked = False
        current_price = np.nan

        for i in range(n):
            price = level_vals[i]

            if np.isnan(price):
                # Level absent; reset state
                is_naked = False
                current_price = np.nan
                naked[i] = False
                continue

            prev_price = level_vals[i - 1] if i > 0 else np.nan
            is_formation = np.isnan(prev_price) or (prev_price != price)

            if is_formation:
                # New or changed level: mark naked, skip touch check this bar
                current_price = price
                is_naked = True
            elif is_naked:
                # Check whether this bar touches the existing naked level
                if lows[i] <= current_price + tol and highs[i] >= current_price - tol:
                    is_naked = False

            naked[i] = is_naked

        out[col + "_naked"] = naked

    return out
