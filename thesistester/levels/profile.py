"""Volume-profile and rolling POC level computations."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from .common import normalized_window_label, require_tz_aware_timestamp
from .rolling_poc_tick import (
    ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    compute_rolling_poc_tick_levels,
    resolve_rolling_poc_profile_source,
)
from .tick_requirements import ROLLING_POC_REQUIRES_TICKS, tick_paths_present
from .session_date import trading_session_date

if TYPE_CHECKING:
    from .tick_vap import PriorProfileTable

DEFAULT_ROLLING_POC_WINDOWS: tuple[str, ...] = ("30min", "1h", "4h")


def _bucket_prices(prices: pd.Series, tick_size: float) -> pd.Series:
    return (np.round(prices / tick_size) * tick_size).round(10)


def _validate_aggregation_ticks(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def _compute_profile(
    prices: Sequence[float],
    volumes: Sequence[float],
    tick_size: float,
    value_area_pct: float,
) -> tuple[float, float, float]:
    profile = pd.DataFrame({"price": prices, "volume": volumes})
    profile = profile.dropna(subset=["price", "volume"])
    profile = profile[profile["volume"] > 0]
    if profile.empty:
        return (np.nan, np.nan, np.nan)

    profile["bin"] = _bucket_prices(profile["price"], tick_size)
    vol_by_bin = profile.groupby("bin", sort=True)["volume"].sum()
    if vol_by_bin.empty:
        return (np.nan, np.nan, np.nan)

    prices_sorted = vol_by_bin.index.to_numpy(dtype="float64")
    volumes_sorted = vol_by_bin.to_numpy(dtype="float64")
    poc_idx = int(np.argmax(volumes_sorted))
    poc = float(prices_sorted[poc_idx])

    total_volume = float(volumes_sorted.sum())
    if total_volume <= 0:
        return (np.nan, np.nan, poc)

    target = total_volume * value_area_pct
    selected_indices = {poc_idx}
    cumulative = float(volumes_sorted[poc_idx])
    left = poc_idx - 1
    right = poc_idx + 1
    while cumulative < target and (left >= 0 or right < len(prices_sorted)):
        left_vol = volumes_sorted[left] if left >= 0 else -1.0
        right_vol = volumes_sorted[right] if right < len(prices_sorted) else -1.0

        if right_vol > left_vol:
            selected_indices.add(right)
            cumulative += float(right_vol)
            right += 1
        else:
            if left >= 0:
                selected_indices.add(left)
                cumulative += float(left_vol)
                left -= 1
            elif right < len(prices_sorted):
                selected_indices.add(right)
                cumulative += float(right_vol)
                right += 1

    selected_prices = prices_sorted[sorted(selected_indices)]
    return (float(selected_prices.max()), float(selected_prices.min()), poc)


def _rolling_poc(
    out: pd.DataFrame,
    prices: pd.Series,
    volumes: pd.Series,
    tick_size: float,
    window: str | pd.Timedelta,
    value_area_pct: float,
) -> pd.Series:
    # Readable MVP implementation; can be vectorized/Numba-accelerated later.
    timestamps = out["timestamp"]
    window_td = pd.to_timedelta(window)
    out_series = pd.Series(np.nan, index=out.index, dtype="float64")
    for i, now in enumerate(timestamps):
        start = now - window_td
        in_window = (timestamps > start) & (timestamps <= now)
        _, _, poc = _compute_profile(
            prices[in_window],
            volumes[in_window],
            tick_size=tick_size,
            value_area_pct=value_area_pct,
        )
        out_series.iat[i] = poc
    return out_series


def compute_profile_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    rolling_windows: list[str] | tuple[str, ...] | None = None,
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = 1,
    prior_week_aggregation_ticks: int = 1,
    prior_month_aggregation_ticks: int = 1,
    prior_profile_table: PriorProfileTable | None = None,
    rolling_poc_profile_source: str = ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    tick_paths: Sequence[str | Path] | None = None,
) -> pd.DataFrame:
    """Compute rolling POC and, when a tick table is supplied, prior-profile VA.

    Rolling POC is tick Last×Volume on ``[now - W + 1min, now + 1min)``
    (desk default ``tick_last_volume_v1``). Missing or empty ``tick_paths``
    refuse with ``rolling POC requires ticks`` when windows are in play;
    they never fall back to typical ``_rolling_poc``. Unsound prints still
    emit ``NaN`` for that bar. ``PriorProfileTable`` is not a rolling tick
    input. The nine ``pd*`` / ``pw*`` / ``pm*`` VA columns are tick
    Last×Volume when ``prior_profile_table`` is set and **absent** when it is
    ``None``.

    ``prior_*_aggregation_ticks`` remain on the signature for API compatibility.
    Day/week/month bin width is applied when the table is built, not when it is
    joined. ``rolling_poc_profile_source`` / ``tick_paths`` are trailing.
    """
    require_tz_aware_timestamp(df)
    if instrument not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {instrument}")
    if not 0 < value_area_pct <= 1:
        raise ValueError("value_area_pct must be in (0, 1].")

    prior_day_aggregation_ticks = _validate_aggregation_ticks(
        "prior_day_aggregation_ticks", prior_day_aggregation_ticks
    )
    prior_week_aggregation_ticks = _validate_aggregation_ticks(
        "prior_week_aggregation_ticks", prior_week_aggregation_ticks
    )
    prior_month_aggregation_ticks = _validate_aggregation_ticks(
        "prior_month_aggregation_ticks", prior_month_aggregation_ticks
    )

    inst = INSTRUMENTS[instrument]
    exchange_tz = getattr(inst, "exchange_tz", "America/New_York")
    eth_start = getattr(inst, "eth_start", "") or ""
    rolling_windows = (
        DEFAULT_ROLLING_POC_WINDOWS if rolling_windows is None else tuple(rolling_windows)
    )
    if rolling_windows and not tick_paths_present(tick_paths):
        raise ValueError(f"{ROLLING_POC_REQUIRES_TICKS}: tick_paths is missing or empty")

    out = df.sort_values("timestamp").reset_index(drop=True).copy()
    levels = pd.DataFrame(index=out.index)
    resolve_rolling_poc_profile_source(rolling_poc_profile_source)
    tick_levels = compute_rolling_poc_tick_levels(
        out,
        tick_paths=tick_paths,
        windows=rolling_windows,
        instrument=instrument,
    )
    for window in rolling_windows:
        label = normalized_window_label(window)
        levels[f"POC_rolling_{label}"] = tick_levels[f"POC_rolling_{label}"]

    if prior_profile_table is not None:
        # Lazy import: tick_vap.py already imports this module's expander.
        from .tick_vap import map_shifted_prior_profile

        local_ts = out["timestamp"].dt.tz_convert(exchange_tz)
        day_key = trading_session_date(local_ts, eth_start)
        day_key_ts = pd.to_datetime(day_key)
        week_key = day_key_ts.dt.to_period("W-SUN")
        month_key = day_key_ts.dt.to_period("M")
        levels = levels.join(map_shifted_prior_profile(day_key, prior_profile_table, family="pd"))
        levels = levels.join(map_shifted_prior_profile(week_key, prior_profile_table, family="pw"))
        levels = levels.join(map_shifted_prior_profile(month_key, prior_profile_table, family="pm"))

    return out.join(levels)
