"""Volume-profile and rolling POC level computations."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from .common import normalized_window_label, require_tz_aware_timestamp

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
        _, _, poc = _compute_profile(prices[in_window], volumes[in_window], tick_size=tick_size, value_area_pct=value_area_pct)
        out_series.iat[i] = poc
    return out_series


def _map_prior_profile_levels(
    out: pd.DataFrame,
    period_key: pd.Series,
    prices: pd.Series,
    volumes: pd.Series,
    tick_size: float,
    value_area_pct: float,
    prefix: str,
) -> pd.DataFrame:
    periods = pd.Index(period_key.unique()).sort_values()
    prior_levels = pd.DataFrame(index=periods, columns=[f"{prefix}VAH", f"{prefix}VAL", f"{prefix}POC"], dtype="float64")

    for period in periods:
        mask = period_key == period
        vah, val, poc = _compute_profile(prices[mask], volumes[mask], tick_size=tick_size, value_area_pct=value_area_pct)
        prior_levels.loc[period, f"{prefix}VAH"] = vah
        prior_levels.loc[period, f"{prefix}VAL"] = val
        prior_levels.loc[period, f"{prefix}POC"] = poc

    shifted = prior_levels.shift(1)
    return pd.DataFrame(
        {
            f"{prefix}VAH": period_key.map(shifted[f"{prefix}VAH"]),
            f"{prefix}VAL": period_key.map(shifted[f"{prefix}VAL"]),
            f"{prefix}POC": period_key.map(shifted[f"{prefix}POC"]),
        },
        index=out.index,
        dtype="float64",
    )


def compute_profile_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    rolling_windows: list[str] | tuple[str, ...] | None = None,
    value_area_pct: float = 0.70,
    prior_day_aggregation_ticks: int = 1,
    prior_week_aggregation_ticks: int = 1,
    prior_month_aggregation_ticks: int = 1,
) -> pd.DataFrame:
    """Compute rolling POC and prior day/week/month profile levels.

    Notes
    -----
    MVP approximation: each bar allocates its full bar volume to a single price bin
    using bar typical price ``(high + low + close) / 3``. This avoids look-ahead and
    keeps behavior deterministic with CSV OHLCV-only input. When true volume-at-price
    data is added later, this function can replace bar-level allocation with intrabar
    bin allocation while keeping the same output column contract.
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
    rolling_windows = DEFAULT_ROLLING_POC_WINDOWS if rolling_windows is None else tuple(rolling_windows)

    out = df.sort_values("timestamp").reset_index(drop=True).copy()
    levels = pd.DataFrame(index=out.index)
    volumes = pd.to_numeric(out["volume"], errors="coerce")
    prices = (
        pd.to_numeric(out["high"], errors="coerce")
        + pd.to_numeric(out["low"], errors="coerce")
        + pd.to_numeric(out["close"], errors="coerce")
    ) / 3.0

    for window in rolling_windows:
        label = normalized_window_label(window)
        levels[f"POC_rolling_{label}"] = _rolling_poc(
            out,
            prices,
            volumes,
            tick_size=inst.tick_size,
            window=window,
            value_area_pct=value_area_pct,
        )

    local_ts = out["timestamp"].dt.tz_convert(inst.exchange_tz)
    day_key = local_ts.dt.date
    naive_local = local_ts.dt.tz_localize(None)
    week_key = naive_local.dt.to_period("W-SUN")
    month_key = naive_local.dt.to_period("M")

    levels = levels.join(
        _map_prior_profile_levels(
            out,
            period_key=day_key,
            prices=prices,
            volumes=volumes,
            tick_size=inst.tick_size * prior_day_aggregation_ticks,
            value_area_pct=value_area_pct,
            prefix="pd",
        )
    )
    levels = levels.join(
        _map_prior_profile_levels(
            out,
            period_key=week_key,
            prices=prices,
            volumes=volumes,
            tick_size=inst.tick_size * prior_week_aggregation_ticks,
            value_area_pct=value_area_pct,
            prefix="pw",
        )
    )
    levels = levels.join(
        _map_prior_profile_levels(
            out,
            period_key=month_key,
            prices=prices,
            volumes=volumes,
            tick_size=inst.tick_size * prior_month_aggregation_ticks,
            value_area_pct=value_area_pct,
            prefix="pm",
        )
    )

    return out.join(levels)
