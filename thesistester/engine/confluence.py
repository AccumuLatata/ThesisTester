"""Confluence / cluster zone detection engine."""
from __future__ import annotations

import numpy as np
import pandas as pd


_ZONE_COLUMNS: list[str] = [
    "timestamp",
    "bar_index",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "level_prices",
]


def _empty_zones_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_ZONE_COLUMNS)


def detect_confluence_zones(
    df: pd.DataFrame,
    level_columns: list[str],
    tick_size: float,
    tolerance_ticks: int | float,
    min_confluences: int = 2,
    max_confluences: int = 5,
) -> pd.DataFrame:
    """Find price-level cluster zones for each bar.

    For each bar, collect the non-NaN values of the selected level columns,
    sort them by price, and apply a greedy sliding-window algorithm to emit
    groups of levels whose price range fits within *tolerance_ticks* ticks.
    Only groups with at least *min_confluences* levels are returned.

    Parameters
    ----------
    df:
        DataFrame containing at least a ``timestamp`` column and the level
        columns listed in *level_columns*.  Must include canonical OHLCV
        columns when used upstream of signal generation.
    level_columns:
        Names of level columns to include in confluence search.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES/NQ).
    tolerance_ticks:
        Cluster tolerance in ticks.  Levels are grouped when their price
        range (max − min) is ``<= tolerance_ticks * tick_size``.
    min_confluences:
        Minimum number of levels required in a cluster to emit a zone row.
        Default 2.
    max_confluences:
        Maximum number of levels to include per emitted zone.  Capped at 5.

    Returns
    -------
    pd.DataFrame
        One row per detected zone per bar with columns: ``timestamp``,
        ``bar_index``, ``zone_low``, ``zone_high``, ``zone_mid``,
        ``level_count``, ``level_names`` (``|``-separated), ``level_prices``
        (``|``-separated).  Returns an empty DataFrame with the correct
        schema when no zones are found.

    Notes
    -----
    - This function does not look ahead; only levels present at bar *i* are
      used when evaluating bar *i*.
    - The greedy algorithm emits non-overlapping zones: once a window is
      emitted, the next search begins past its end.
    - Duplicate level values (same price, different column names) are each
      treated as an independent contributor to the count.
    """
    if not level_columns:
        return _empty_zones_df()

    max_confluences = min(int(max_confluences), 5)
    tol = float(tolerance_ticks) * float(tick_size)

    present_cols = [c for c in level_columns if c in df.columns]
    if not present_cols:
        return _empty_zones_df()

    df_reset = df.reset_index(drop=True)
    zones: list[dict] = []

    for bar_idx in range(len(df_reset)):
        row = df_reset.iloc[bar_idx]

        # Collect non-NaN level prices for this bar
        price_map: dict[str, float] = {}
        for col in present_cols:
            val = row[col]
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                try:
                    price_map[col] = float(val)
                except (TypeError, ValueError):
                    pass

        if len(price_map) < min_confluences:
            continue

        # Sort levels by price
        sorted_items = sorted(price_map.items(), key=lambda x: x[1])
        names = [item[0] for item in sorted_items]
        prices = [item[1] for item in sorted_items]
        n = len(prices)

        # Greedy sliding window: emit largest non-overlapping clusters
        j = 0
        while j < n:
            # Expand window [j, k) while price range <= tol
            k = j + 1
            while k < n and prices[k] - prices[j] <= tol:
                k += 1
            window_size = k - j

            if window_size >= min_confluences:
                cap = min(window_size, max_confluences)
                z_names = names[j : j + cap]
                z_prices = prices[j : j + cap]

                ts = row["timestamp"] if "timestamp" in df_reset.columns else pd.NaT

                zones.append(
                    {
                        "timestamp": ts,
                        "bar_index": bar_idx,
                        "zone_low": z_prices[0],
                        "zone_high": z_prices[-1],
                        "zone_mid": (z_prices[0] + z_prices[-1]) / 2.0,
                        "level_count": cap,
                        "level_names": "|".join(z_names),
                        "level_prices": "|".join(str(p) for p in z_prices),
                    }
                )
                j = k  # advance past this window (non-overlapping)
            else:
                j += 1

    if not zones:
        return _empty_zones_df()
    return pd.DataFrame(zones)
